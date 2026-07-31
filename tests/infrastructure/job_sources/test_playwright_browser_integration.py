from __future__ import annotations

import json
from datetime import UTC, date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from resume_tailor.domain.job_discovery.company_sources import (
    AuditedSourcePlan,
    DetailExtractionMode,
    ExtractionProfileSpec,
    FirstPartyAuditEvidence,
    ListingDiscoveryMode,
    PageFetchMode,
)
from resume_tailor.domain.job_discovery.models import (
    ConnectorType,
    FeedKind,
    FirstPartySource,
)
from resume_tailor.domain.job_discovery.providers import ProviderCursor
from resume_tailor.domain.job_discovery.queries import ProviderJobQuery
from resume_tailor.infrastructure.job_sources.browser_fallback import BoundedBrowserFallback
from resume_tailor.infrastructure.job_sources.browser_playwright import (
    PlaywrightBrowserSession,
    PlaywrightBrowserSessionFactory,
    _normalize_origin,
)
from resume_tailor.infrastructure.job_sources.first_party import (
    FirstPartyCareerConnector,
    FirstPartySourceError,
)


class _RenderedJobsHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/careers/positions/":
            body = """
            <html><body><div id="cards"></div>
            <script>
            document.getElementById('cards').innerHTML =
              '<a class="job-card" href="/careers/positions/platform-engineer/">'
              + 'Platform Engineer</a>';
            </script></body></html>
            """
        elif self.path.rstrip("/") == "/careers/positions/platform-engineer":
            jobposting_json = json.dumps(
                {
                    "@context": "https://schema.org",
                    "@type": "JobPosting",
                    "title": "Platform Engineer",
                    "description": "Build platform systems.",
                    "hiringOrganization": {"name": "Local Browser Company"},
                    "url": f"http://127.0.0.1:{self.server.server_port}{self.path}",
                    "identifier": {"value": "platform-engineer"},
                }
            )
            body = f"""
            <html><head><script type="application/ld+json">{jobposting_json}</script></head>
            <body><div id="job-description"></div><script>
            document.getElementById('job-description').textContent = 'Build platform systems.';
            </script></body></html>
            """
        else:
            self.send_error(404)
            return
        encoded = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        return


def _source(port: int) -> FirstPartySource:
    origin = f"http://127.0.0.1:{port}"
    plan = AuditedSourcePlan.model_construct(
        mechanism="first_party",
        listing_discovery_mode=ListingDiscoveryMode.BROWSER_INDEX,
        detail_fetch_mode=PageFetchMode.BROWSER,
        detail_extraction_mode=DetailExtractionMode.JSON_LD_THEN_HTML,
        provider_configuration=None,
        index_urls=[f"{origin}/careers/positions/"],
        allowed_job_path_patterns=[r"^/careers/positions/.*$"],
        navigation_hosts=["127.0.0.1"],
        redirect_hosts=[],
        browser_resource_hosts=["127.0.0.1"],
        browser_api_hosts=[],
        browser_actions=[],
        max_listing_pages=1,
        max_browser_listing_pages=1,
        max_browser_actions=1,
        max_job_detail_pages=2,
        max_network_requests=20,
        max_total_render_seconds=10,
        audit_version="test-browser-v1",
        audit_date=date(2026, 7, 26),
    )
    audit = FirstPartyAuditEvidence.model_construct(
        canonical_employer_url=f"{origin}/careers/",
        listing_index_urls=[f"{origin}/careers/positions/"],
        navigation_hosts=["127.0.0.1"],
        redirect_hosts=[],
        allowed_listing_path_patterns=[r"^/careers/positions/.*$"],
        allowed_detail_path_patterns=[r"^/careers/positions/.*$"],
        robots_decision="allow",
        listing_discovery_mode=ListingDiscoveryMode.BROWSER_INDEX,
        detail_fetch_mode=PageFetchMode.BROWSER,
        detail_extraction_mode=DetailExtractionMode.JSON_LD_THEN_HTML,
        stable_identity_authority="canonical_detail_url",
        canonical_detail_url_authority="employer_host",
        application_url_authority="terminal_only",
        application_hosts=[],
        completeness_boundary="bounded local test",
        data_authority="employer_host",
        competing_provider_authority=False,
        fixture_index_path="tests/fixtures/local/index.html",
        fixture_detail_path="tests/fixtures/local/detail.html",
        audit_version="test-browser-v1",
        audit_date=date(2026, 7, 26),
    )
    return FirstPartySource.model_construct(
        source_id="local-browser",
        company_id="local-browser-company",
        company_name="Local Browser Company",
        canonical_domain="127.0.0.1",
        connector_type=ConnectorType.FIRST_PARTY,
        mechanism="first_party",
        enabled=True,
        official_base_url=origin,
        allowed_hosts=("127.0.0.1",),
        redirect_hosts=(),
        browser_rendering_allowed=True,
        source_plan=plan,
        first_party_audit=audit,
        extraction_profile=ExtractionProfileSpec(
            profile_id="local-browser-index-v1",
            allowed_link_path_patterns=[r"^/careers/positions/[^/]+/?$"],
            job_card_attributes={"class": "job-card"},
        ),
        audit_version="test-browser-v1",
        registry_plan_hash="test-plan-hash",
        extraction_profile_hash="test-extraction-hash",
    )


def test_real_playwright_browser_renders_and_extracts_local_job() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RenderedJobsHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        source = _source(server.server_port)
        factory = PlaywrightBrowserSessionFactory(
            test_only_allowed_origin=f"http://127.0.0.1:{server.server_port}"
        )
        fallback = BoundedBrowserFallback(
            session_factory=factory,
            test_only_allow_insecure_origin=True,
        )
        connector = FirstPartyCareerConnector(
            fetcher=lambda _: (_ for _ in ()).throw(
                FirstPartySourceError("browser_required", "static fixture requires browser")
            ),
            browser_fallback=fallback,
        )
        page = connector.fetch_page(
            source,
            ProviderJobQuery(feed_kind=FeedKind.TAILORED, page_size=10),
            ProviderCursor(),
            fetched_at=datetime.now(UTC),
        )
        assert len(page.records) == 1
        assert page.records[0].title == "Platform Engineer"
        assert page.records[0].external_job_id
    finally:
        server.shutdown()
        server.server_close()


class _Request:
    def __init__(self, url: str, resource_type: str) -> None:
        self.url = url
        self.resource_type = resource_type


def _policy_session(port: int = 50123) -> PlaywrightBrowserSession:
    session = object.__new__(PlaywrightBrowserSession)
    session._source = _source(port)
    session._test_origin = _normalize_origin(f"http://127.0.0.1:{port}")
    session._allow_insecure_test_origin = True
    return session


def test_test_only_origin_requires_exact_origin_and_source_path() -> None:
    session = _policy_session()
    accepted = "http://127.0.0.1:50123/careers/positions/"

    assert session._allowed_navigation(accepted)
    assert session._allowed_request(_Request(accepted, "document"))
    assert session._allowed_request(_Request(accepted, "script"))
    assert not session._allowed_navigation(
        "http://127.0.0.1:50124/careers/positions/"
    )
    assert not session._allowed_navigation(
        "https://127.0.0.1:50123/careers/positions/"
    )
    assert not session._allowed_navigation(
        "https://127.0.0.1/careers/positions/"
    )
    assert not session._allowed_navigation(
        "http://localhost:50123/careers/positions/"
    )
    assert not session._allowed_navigation(
        "http://127.0.0.1:50123.evil.example/careers/positions/"
    )
    assert not session._allowed_navigation(
        "http://user@127.0.0.1:50123/careers/positions/"
    )
    assert not session._allowed_navigation(
        "http://127.0.0.1:50123/careers/private/"
    )
    assert not session._allowed_navigation("https://evil.example/careers/positions/")
    assert not session._allowed_navigation(
        "https://job-boards.greenhouse.io/local-browser/apply/123"
    )
    assert not session._allowed_navigation(
        "http://127.0.0.1:50123/careers/positions/#fragment"
    )


def test_production_navigation_rejects_http_loopback_and_registry_cannot_set_origin() -> None:
    session = _policy_session()
    session._test_origin = None

    assert not session._allowed_navigation("http://127.0.0.1:50123/careers/positions/")
    assert "test_only_allowed_origin" not in FirstPartySource.model_fields
