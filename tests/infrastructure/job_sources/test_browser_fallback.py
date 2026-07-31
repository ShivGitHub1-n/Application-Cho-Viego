# ruff: noqa: E501

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

import resume_tailor.infrastructure.job_sources.browser_playwright as browser_playwright_module
from resume_tailor.domain.job_discovery.company_sources import BrowserActionSpec, PageFetchMode
from resume_tailor.domain.job_discovery.models import FirstPartySource
from resume_tailor.domain.job_discovery.providers import ProviderCursor
from resume_tailor.domain.job_discovery.queries import ExploreJobQuery
from resume_tailor.infrastructure.job_sources.browser_fallback import BoundedBrowserFallback
from resume_tailor.infrastructure.job_sources.browser_playwright import (
    PlaywrightBrowserSession,
    PlaywrightBrowserSessionFactory,
)
from resume_tailor.infrastructure.job_sources.first_party import (
    FirstPartyCareerConnector,
    FirstPartySourceError,
)
from resume_tailor.infrastructure.job_sources.registry import (
    compile_runtime_sources,
    load_company_source_registry,
)


def _source() -> FirstPartySource:
    registry = load_company_source_registry(
        Path("config/approved-job-sources.json"), reference_date=datetime(2026, 7, 26).date()
    )
    source = next(
        item for item in compile_runtime_sources(registry) if item.source_id == "rocket-lab"
    )
    assert isinstance(source, FirstPartySource)
    return source


def test_injected_unavailable_runtime_is_reported_without_download() -> None:
    source = _source().model_copy(
        update={
            "browser_rendering_allowed": True,
            "source_plan": _source().source_plan.model_copy(
                update={"detail_fetch_mode": PageFetchMode.BROWSER}
            ),
        }
    )
    attempted = False

    class UnavailableFactory:
        def __call__(self, _: FirstPartySource) -> object:
            nonlocal attempted
            attempted = True
            raise FirstPartySourceError(
                "browser_unavailable", "browser runtime is unavailable"
            )

    connector = FirstPartyCareerConnector(
        fetcher=lambda url: httpx.Response(
            200, headers={"content-type": "text/html"}, text="<button>Load more</button>"
        ),
        browser_fallback=BoundedBrowserFallback(session_factory=UnavailableFactory()),
    )

    with pytest.raises(FirstPartySourceError, match="browser runtime") as error:
        connector.fetch_page(
            source,
            ExploreJobQuery(sectors=["Software Engineering"]).to_provider_query(),
            ProviderCursor(),
            fetched_at=datetime(2026, 7, 26, tzinfo=UTC),
        )
    assert error.value.code == "browser_unavailable"
    assert attempted


def test_playwright_adapter_reports_unavailable_when_driver_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_playwright() -> object:
        raise ImportError("playwright is unavailable")

    monkeypatch.setattr(browser_playwright_module, "sync_playwright", missing_playwright)

    with pytest.raises(FirstPartySourceError, match="browser runtime") as error:
        PlaywrightBrowserSession(_source())

    assert error.value.code == "browser_unavailable"


def test_playwright_adapter_reports_unavailable_when_executable_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakePlaywright:
        class chromium:
            executable_path = "C:/missing/playwright/chromium.exe"

        def stop(self) -> None:
            return None

    class FakePlaywrightContext:
        def start(self) -> FakePlaywright:
            return FakePlaywright()

    monkeypatch.setattr(
        browser_playwright_module,
        "sync_playwright",
        lambda: FakePlaywrightContext(),
    )
    monkeypatch.setattr(browser_playwright_module, "_trusted_browser_executable", lambda: None)

    with pytest.raises(FirstPartySourceError, match="browser") as error:
        PlaywrightBrowserSession(_source())

    assert error.value.code == "browser_unavailable"


def test_fallback_propagates_test_only_insecure_origin_to_injected_factory() -> None:
    origin = "http://127.0.0.1:50123"
    factory = PlaywrightBrowserSessionFactory(test_only_allowed_origin=origin)

    BoundedBrowserFallback(
        session_factory=factory,
        test_only_allow_insecure_origin=True,
    )

    assert factory.test_only_allow_insecure_origin is True


def test_authorized_browser_fallback_uses_same_static_extraction_and_closes_context() -> None:
    source = _source().model_copy(
        update={
            "browser_rendering_allowed": True,
            "source_plan": _source().source_plan.model_copy(
                update={"detail_fetch_mode": PageFetchMode.BROWSER}
            ),
        }
    )
    closed = False
    index = "<button>Load more</button>"
    rendered_index = "<a class='job-card' href='/careers/positions/flight-software-engineer/'>Flight</a>"
    rendered_detail = """<script type='application/ld+json'>{\"@type\":\"JobPosting\",\"title\":\"Flight Software Engineer\",\"description\":\"Build flight software.\",\"url\":\"https://rocketlabcorp.com/careers/positions/flight-software-engineer/\"}</script>"""

    class Session:
        def get(self, url: str) -> httpx.Response:
            body = rendered_index if url.endswith("positions/") else rendered_detail
            return httpx.Response(200, headers={"content-type": "text/html"}, text=body)

        def close(self) -> None:
            nonlocal closed
            closed = True

    fallback = BoundedBrowserFallback(session_factory=lambda _: Session())
    connector = FirstPartyCareerConnector(
        fetcher=lambda _: httpx.Response(200, headers={"content-type": "text/html"}, text=index),
        browser_fallback=fallback,
    )
    page = connector.fetch_page(
        source,
        ExploreJobQuery(sectors=["Software Engineering"]).to_provider_query(),
        ProviderCursor(),
        fetched_at=datetime(2026, 7, 26, tzinfo=UTC),
    )

    assert [record.title for record in page.records] == ["Flight Software Engineer"]
    assert closed


def test_browser_action_attempts_obey_global_action_limit() -> None:
    source = _source().model_copy(
        update={
            "source_plan": _source().source_plan.model_copy(update={"max_browser_actions": 3})
        }
    )
    session = PlaywrightBrowserSession.__new__(PlaywrightBrowserSession)
    session._source = source
    session.action_count = 0

    class Locator:
        def __init__(self) -> None:
            self.clicks = 0

        def click(self, *, timeout: int) -> None:
            self.clicks += 1

        def inner_text(self, *, timeout: int) -> str:
            return "unchanged"

    locator = Locator()

    class Page:
        def locator(self, selector: str) -> Locator:
            return locator

    session._page = Page()
    with pytest.raises(FirstPartySourceError, match="action limit"):
        session._run_action(
            BrowserActionSpec(action_type="click", selector=".load-more", max_attempts=10)
        )
    assert locator.clicks == 3
    assert session.action_count == 3


def test_load_more_stops_when_bounded_dom_is_unchanged() -> None:
    source = _source().model_copy(
        update={
            "source_plan": _source().source_plan.model_copy(update={"max_browser_actions": 3})
        }
    )
    session = PlaywrightBrowserSession.__new__(PlaywrightBrowserSession)
    session._source = source
    session.action_count = 0

    class Locator:
        def click(self, *, timeout: int) -> None:
            return None

        def inner_text(self, *, timeout: int) -> str:
            return "same listing"

    class Page:
        def locator(self, selector: str) -> Locator:
            return Locator()

    session._page = Page()
    session._run_action(
        BrowserActionSpec(action_type="load_more", selector=".load-more", max_attempts=10)
    )
    assert session.action_count == 1


def test_denied_browser_listing_does_not_launch_a_session() -> None:
    source = _source().model_copy(
        update={
            "browser_rendering_allowed": True,
            "source_plan": _source().source_plan.model_copy(
                update={"detail_fetch_mode": PageFetchMode.BROWSER}
            ),
        }
    )
    launched = False

    def factory(_: FirstPartySource) -> object:
        nonlocal launched
        launched = True
        raise AssertionError("browser must not launch when robots denies listing")

    fallback = BoundedBrowserFallback(
        session_factory=factory,
        robots_checker=lambda _: False,
    )
    with pytest.raises(FirstPartySourceError, match="robots"):
        fallback.fetch_page(
            source,
            ExploreJobQuery(sectors=["Software Engineering"]).to_provider_query(),
            ProviderCursor(),
            fetched_at=datetime(2026, 7, 26, tzinfo=UTC),
        )
    assert not launched
