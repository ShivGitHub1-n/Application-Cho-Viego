# ruff: noqa: E501

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from resume_tailor.domain.job_discovery.models import FirstPartySource
from resume_tailor.domain.job_discovery.providers import ProviderCursor
from resume_tailor.domain.job_discovery.queries import ExploreJobQuery
from resume_tailor.infrastructure.job_sources.first_party import (
    FirstPartyCareerConnector,
    FirstPartySourceError,
)
from resume_tailor.infrastructure.job_sources.registry import (
    compile_runtime_sources,
    load_company_source_registry,
)


def _rocket_source() -> FirstPartySource:
    registry = load_company_source_registry(
        Path("config/approved-job-sources.json"),
        reference_date=datetime(2026, 7, 26, tzinfo=UTC).date(),
    )
    source = next(
        item for item in compile_runtime_sources(registry) if item.source_id == "rocket-lab"
    )
    assert isinstance(source, FirstPartySource)
    return source


def test_first_party_connector_discovers_and_extracts_without_fetching_application_url() -> None:
    source = _rocket_source()
    calls: list[str] = []
    index = """
    <html><body>
      <a class='job-card' href='/careers/positions/flight-software-engineer/'>Relevant</a>
      <a href='https://job-boards.greenhouse.io/rocketlab/jobs/123'>Apply</a>
      <a href='/about/'>Unrelated</a>
    </body></html>
    """
    detail = """
    <html><head><link rel='canonical' href='https://rocketlabcorp.com/careers/positions/flight-software-engineer/'></head>
      <body><script type='application/ld+json'>
      {"@context":"https://schema.org","@type":"JobPosting","title":"Flight Software Engineer",
       "description":"Build flight software for spacecraft.","datePosted":"2026-07-20",
       "hiringOrganization":{"name":"Rocket Lab"},"jobLocation":{"address":{"addressLocality":"Long Beach","addressRegion":"CA","addressCountry":"US"}},
       "identifier":{"value":"flight-software-engineer"},"directApply":true,
       "url":"https://rocketlabcorp.com/careers/positions/flight-software-engineer/",
       "applicationUrl":"https://job-boards.greenhouse.io/rocketlab/jobs/123"}
      </script></body></html>
    """

    def fetch(url: str) -> httpx.Response:
        calls.append(url)
        body = index if url.endswith("/careers/positions/") else detail
        return httpx.Response(200, headers={"content-type": "text/html"}, text=body)

    connector = FirstPartyCareerConnector(fetcher=fetch)
    page = connector.fetch_page(
        source,
        ExploreJobQuery(sectors=["Software Engineering"]).to_provider_query(),
        ProviderCursor(),
        fetched_at=datetime(2026, 7, 26, tzinfo=UTC),
    )

    assert [record.title for record in page.records] == ["Flight Software Engineer"]
    assert page.records[0].external_job_id == "flight-software-engineer"
    assert str(page.records[0].application_url).startswith("https://job-boards.greenhouse.io/")
    assert all("job-boards.greenhouse.io" not in call for call in calls)


def test_denied_robots_stops_listing_before_content_fetch() -> None:
    source = _rocket_source()
    calls: list[str] = []

    def fetch(url: str) -> httpx.Response:
        calls.append(url)
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<a class='job-card' href='/careers/positions/one/'>One</a>",
        )

    connector = FirstPartyCareerConnector(fetcher=fetch, robots_checker=lambda _: False)
    with pytest.raises(FirstPartySourceError, match="robots"):
        connector.fetch_page(
            source,
            ExploreJobQuery(sectors=["Software Engineering"]).to_provider_query(),
            ProviderCursor(),
            fetched_at=datetime(2026, 7, 26, tzinfo=UTC),
        )
    assert calls == []


def test_denied_robots_stops_detail_before_content_fetch() -> None:
    source = _rocket_source()
    calls: list[str] = []

    def robots(url: str) -> bool:
        return url.endswith("positions/")

    def fetch(url: str) -> httpx.Response:
        calls.append(url)
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<a class='job-card' href='/careers/positions/one/'>One</a>",
        )

    connector = FirstPartyCareerConnector(fetcher=fetch, robots_checker=robots)
    page = connector.fetch_page(
        source,
        ExploreJobQuery(sectors=["Software Engineering"]).to_provider_query(),
        ProviderCursor(),
        fetched_at=datetime(2026, 7, 26, tzinfo=UTC),
    )
    assert page.records == []
    assert page.warnings[0].message == "robots_denied"
    assert calls == ["https://rocketlabcorp.com/careers/positions/"]


def test_static_index_uses_job_card_profile_and_rejects_unrelated_same_path_links() -> None:
    source = _rocket_source()
    index = """
    <a class='job-card' href='/careers/positions/approved/'>Approved</a>
    <a href='/careers/positions/unrelated/'>Footer</a>
    """

    def fetch(url: str) -> httpx.Response:
        body = index if url.endswith("positions/") else (
            "<script type='application/ld+json'>{\"@type\":\"JobPosting\","
            "\"title\":\"Approved\",\"description\":\"Build systems.\"}</script>"
        )
        return httpx.Response(200, headers={"content-type": "text/html"}, text=body)

    page = FirstPartyCareerConnector(fetcher=fetch).fetch_page(
        source,
        ExploreJobQuery(sectors=["Software Engineering"]).to_provider_query(),
        ProviderCursor(),
        fetched_at=datetime(2026, 7, 26, tzinfo=UTC),
    )
    assert [record.external_job_id for record in page.records] == ["approved"]
