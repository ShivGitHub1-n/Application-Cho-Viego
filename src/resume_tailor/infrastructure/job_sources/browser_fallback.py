"""Optional isolated browser fallback seam.

Playwright is intentionally not imported here. The runtime is an injected
capability; environments without an installed browser receive a stable
diagnostic and never trigger installation or a download.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

import httpx

from resume_tailor.domain.job_discovery.company_sources import PageFetchMode
from resume_tailor.domain.job_discovery.models import FirstPartySource
from resume_tailor.domain.job_discovery.providers import (
    JobSourcePage,
    ProviderCursor,
)
from resume_tailor.domain.job_discovery.queries import ProviderJobQuery
from resume_tailor.infrastructure.job_sources.browser_playwright import (
    PlaywrightBrowserSessionFactory,
)
from resume_tailor.infrastructure.job_sources.first_party import (
    FirstPartyCareerConnector,
    FirstPartySourceError,
)


class BrowserSession(Protocol):
    def get(self, url: str) -> httpx.Response: ...

    def close(self) -> None: ...


class BoundedBrowserFallback:
    """Run the same first-party extraction using an injected browser session."""

    def __init__(
        self,
        session_factory: Callable[[FirstPartySource], BrowserSession] | None = None,
        *,
        test_only_allow_insecure_origin: bool = False,
        robots_checker: Callable[[str], bool] | None = None,
    ) -> None:
        self._test_only_allow_insecure_origin = test_only_allow_insecure_origin
        self._robots_checker = robots_checker
        self._session_factory = session_factory or PlaywrightBrowserSessionFactory(
            test_only_allow_insecure_origin=test_only_allow_insecure_origin
        )
        if test_only_allow_insecure_origin and isinstance(
            self._session_factory, PlaywrightBrowserSessionFactory
        ):
            self._session_factory.enable_test_only_insecure_origin()

    def fetch_page(
        self,
        source: FirstPartySource,
        query: ProviderJobQuery,
        cursor: ProviderCursor,
        *,
        fetched_at: datetime,
    ) -> JobSourcePage:
        if (
            not source.browser_rendering_allowed
            or source.source_plan.detail_fetch_mode is not PageFetchMode.BROWSER
        ):
            raise FirstPartySourceError(
                "browser_not_authorized",
                "the approved source plan does not authorize browser retrieval",
            )
        if self._robots_checker is not None:
            initial_urls = [
                *[str(url) for url in source.source_plan.index_urls],
                *[str(url) for url in source.source_plan.sitemap_urls],
                *[str(url) for url in source.source_plan.direct_detail_urls],
            ]
            if initial_urls and not all(self._robots_checker(url) for url in initial_urls):
                raise FirstPartySourceError("robots_denied", "robots policy denied the source URL")
        session = self._session_factory(source)
        try:
            connector = FirstPartyCareerConnector(
                fetcher=session.get,
                browser_mode=True,
                allow_insecure_test_origin=self._test_only_allow_insecure_origin,
                robots_checker=self._robots_checker,
                test_only_allowed_origin=(
                    self._session_factory.test_only_allowed_origin
                    if isinstance(self._session_factory, PlaywrightBrowserSessionFactory)
                    else None
                ),
            )
            return connector.fetch_page(source, query, cursor, fetched_at=fetched_at)
        finally:
            session.close()


__all__ = ["BoundedBrowserFallback", "BrowserSession"]
