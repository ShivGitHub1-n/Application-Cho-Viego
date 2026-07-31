"""Bounded Playwright adapter for explicitly authorized first-party pages."""

from __future__ import annotations

import hashlib
import os
import re
import time
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

import httpx
from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    Request,
    Route,
    TimeoutError,
    sync_playwright,
)

from resume_tailor.domain.job_discovery.company_sources import BrowserActionSpec
from resume_tailor.domain.job_discovery.models import FirstPartySource
from resume_tailor.infrastructure.job_sources._common import _normalize_origin, _url_origin
from resume_tailor.infrastructure.job_sources.first_party import FirstPartySourceError

_USER_AGENT = "ResumeTailorJobDiscovery/1.0 (bounded first-party browser)"
_VIEWPORT = {"width": 1280, "height": 900}
_RESOURCE_TYPES = frozenset({"script", "stylesheet", "image", "font", "media"})


def _trusted_browser_executable() -> str | None:
    """Return a known system browser path, never a registry-supplied path."""

    candidates = [
        Path(os.environ.get("ProgramFiles", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft/Edge/Application/msedge.exe",
    ]
    return next((str(path) for path in candidates if path.is_file()), None)


class PlaywrightBrowserSession:
    """One isolated Playwright context owned by a single source attempt."""

    def __init__(
        self,
        source: FirstPartySource,
        *,
        test_only_allowed_origin: str | None = None,
        test_only_allow_insecure_origin: bool = False,
    ) -> None:
        self._source = source
        self._test_origin = (
            _normalize_origin(test_only_allowed_origin)
            if test_only_allowed_origin
            else None
        )
        self._allow_insecure_test_origin = test_only_allow_insecure_origin
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._closed = False
        self.request_count = 0
        self.navigation_count = 0
        self.action_count = 0
        self.browser_version: str | None = None
        self._launch()

    def _launch(self) -> None:
        try:
            self._playwright = sync_playwright().start()
            chromium = self._playwright.chromium
            managed_path = Path(chromium.executable_path)
            executable = (
                str(managed_path) if managed_path.is_file() else _trusted_browser_executable()
            )
            if executable is None:
                raise FirstPartySourceError(
                    "browser_unavailable",
                    "no Playwright-managed or trusted Chromium browser exists",
                )
            self._browser = chromium.launch(
                executable_path=executable,
                headless=True,
                env={
                    key: value
                    for key, value in os.environ.items()
                    if key.casefold() not in {"http_proxy", "https_proxy", "all_proxy"}
                },
            )
            self.browser_version = self._browser.version
            self._context = self._browser.new_context(
                user_agent=_USER_AGENT,
                viewport=cast(Any, _VIEWPORT),
                service_workers="block",
                accept_downloads=False,
                permissions=[],
            )
            self._page = self._context.new_page()
            self._context.route("**/*", self._route)
            self._page.on("popup", self._close_popup)
            self._page.on("download", self._cancel_download)
        except FirstPartySourceError:
            self.close()
            raise
        except Exception as exc:
            self.close()
            raise FirstPartySourceError(
                "browser_unavailable", "the approved browser runtime could not launch"
            ) from exc

    def get(self, url: str) -> httpx.Response:
        if self._closed or self._page is None:
            raise FirstPartySourceError("browser_unavailable", "browser context is closed")
        if not self._allowed_navigation(url):
            raise FirstPartySourceError(
                "browser_url_rejected", "browser navigation is not approved"
            )
        limit = self._source.source_plan.max_network_requests
        if limit < 1 or self.request_count >= limit:
            raise FirstPartySourceError("browser_request_limit", "browser request limit reached")
        self.navigation_count += 1
        if self.navigation_count > max(
            self._source.source_plan.max_browser_listing_pages,
            self._source.source_plan.max_job_detail_pages,
            1,
        ):
            raise FirstPartySourceError("browser_page_limit", "browser page limit reached")
        started = time.monotonic()
        timeout_ms = min(self._source.source_plan.max_total_render_seconds * 1000, 30_000)
        try:
            response = self._page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            self._run_actions()
            elapsed_ms = int((time.monotonic() - started) * 1000)
            if elapsed_ms > timeout_ms:
                raise FirstPartySourceError("browser_timeout", "browser render deadline exceeded")
            body = self._page.content().encode("utf-8")
            if len(body) > 2 * 1024 * 1024:
                raise FirstPartySourceError("response_too_large", "rendered document is too large")
            status = response.status if response is not None else 200
            content_type = response.header_value("content-type") if response is not None else None
            return httpx.Response(
                status,
                headers={"content-type": content_type or "text/html; charset=utf-8"},
                content=body,
                request=httpx.Request("GET", url),
            )
        except FirstPartySourceError:
            raise
        except TimeoutError as exc:
            raise FirstPartySourceError(
                "browser_timeout", "browser render deadline exceeded"
            ) from exc
        except Exception as exc:
            raise FirstPartySourceError(
                "browser_navigation_failed", "browser navigation failed"
            ) from exc

    def _run_actions(self) -> None:
        if self._page is None:
            return
        actions = self._source.source_plan.browser_actions
        for action in actions:
            self._run_action(action)

    def _consume_action(self) -> None:
        if self.action_count >= self._source.source_plan.max_browser_actions:
            raise FirstPartySourceError("browser_action_limit", "browser action limit reached")
        self.action_count += 1

    def _dom_fingerprint(self) -> str:
        if self._page is None:
            return ""
        text = self._page.locator("body").inner_text(timeout=1_000)[:64_000]
        return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()

    def _run_action(self, action: BrowserActionSpec) -> None:
        if self._page is None:
            return
        try:
            if action.action_type == "wait_for_selector":
                self._consume_action()
                self._page.wait_for_selector(action.selector, timeout=action.timeout_ms)
            elif action.action_type in {"click", "load_more"}:
                for _ in range(action.max_attempts):
                    before = self._dom_fingerprint() if action.action_type == "load_more" else None
                    self._consume_action()
                    self._page.locator(action.selector).click(timeout=action.timeout_ms)
                    if action.action_type == "load_more" and self._dom_fingerprint() == before:
                        break
            else:
                raise FirstPartySourceError(
                    "browser_action_rejected", "browser action is not approved"
                )
        except FirstPartySourceError:
            raise
        except TimeoutError as exc:
            raise FirstPartySourceError(
                "browser_action_failed", "approved browser action failed"
            ) from exc

    def _route(self, route: Route, request: Request) -> None:
        self.request_count += 1
        if self.request_count > self._source.source_plan.max_network_requests:
            route.abort("blockedbyclient")
            return
        if self._allowed_request(request):
            route.continue_()
        else:
            route.abort("blockedbyclient")

    def _allowed_request(self, request: Request) -> bool:
        url = request.url
        resource_type = request.resource_type
        if resource_type == "document":
            return self._allowed_navigation(url)
        if self._is_application_url(url):
            return False
        parsed = urlsplit(url)
        if parsed.username or parsed.password or parsed.fragment:
            return False
        if self._test_origin_host_matches(url) and not self._test_origin_matches(url):
            return False
        host = (parsed.hostname or "").casefold().rstrip(".")
        if parsed.scheme != "https":
            return self._allow_insecure_test_origin and self._test_origin_matches(url)
        if resource_type in {"xhr", "fetch"}:
            return host in set(
                self._source.source_plan.browser_api_hosts
            ) or self._test_origin_matches(url)
        if resource_type in _RESOURCE_TYPES or resource_type in {"worker", "websocket"}:
            return host in set(
                self._source.source_plan.browser_resource_hosts
            ) or self._test_origin_matches(url)
        return False

    def _allowed_navigation(self, url: str) -> bool:
        parsed = urlsplit(url)
        if parsed.username or parsed.password or parsed.fragment:
            return False
        if self._test_origin_host_matches(url) and not self._test_origin_matches(url):
            return False
        if parsed.scheme != "https" and not (
            self._allow_insecure_test_origin and self._test_origin_matches(url)
        ):
            return False
        if self._is_application_url(url):
            return False
        host = (parsed.hostname or "").casefold().rstrip(".")
        return host in set(self._source.source_plan.navigation_hosts) and any(
            re.search(pattern, parsed.path or "/") is not None
            for pattern in self._source.source_plan.allowed_job_path_patterns
        )

    def _test_origin_matches(self, url: str) -> bool:
        actual = _url_origin(url)
        if self._test_origin is None or actual is None:
            return False
        return actual == self._test_origin

    def _test_origin_host_matches(self, url: str) -> bool:
        actual = _url_origin(url)
        return self._test_origin is not None and actual is not None and (
            actual.hostname == self._test_origin.hostname
        )

    def _is_application_url(self, url: str) -> bool:
        audit = self._source.first_party_audit
        return bool(audit and audit.is_application_url_allowed(url))

    @staticmethod
    def _close_popup(page: Page) -> None:
        try:
            page.close()
        except Exception:
            return

    @staticmethod
    def _cancel_download(download: Any) -> None:
        try:
            download.cancel()
        except Exception:
            return

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for resource in (self._page, self._context, self._browser):
            if resource is not None:
                try:
                    resource.close()
                except Exception:
                    pass
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass


class PlaywrightBrowserSessionFactory:
    def __init__(
        self,
        *,
        test_only_allowed_origin: str | None = None,
        test_only_allow_insecure_origin: bool = False,
    ) -> None:
        self._test_only_allowed_origin = test_only_allowed_origin
        self._test_only_allow_insecure_origin = test_only_allow_insecure_origin

    @property
    def test_only_allow_insecure_origin(self) -> bool:
        return self._test_only_allow_insecure_origin

    @property
    def test_only_allowed_origin(self) -> str | None:
        return self._test_only_allowed_origin

    def enable_test_only_insecure_origin(self) -> None:
        if _normalize_origin(self._test_only_allowed_origin or "") is not None:
            self._test_only_allow_insecure_origin = True

    def __call__(self, source: FirstPartySource) -> PlaywrightBrowserSession:
        return PlaywrightBrowserSession(
            source,
            test_only_allowed_origin=self._test_only_allowed_origin,
            test_only_allow_insecure_origin=self._test_only_allow_insecure_origin,
        )


__all__ = ["PlaywrightBrowserSession", "PlaywrightBrowserSessionFactory"]
