from __future__ import annotations

import json
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from threading import Thread

from resume_tailor.infrastructure.job_sources.first_party import (
    FirstPartyCareerConnector,
    _canonical_url,
)
from tests.infrastructure.job_sources.test_playwright_browser_integration import (
    _RenderedJobsHandler,
    _source,
)


def test_relative_detail_url_preserves_listing_origin_scheme_and_port() -> None:
    port = 52614
    origin = f"http://127.0.0.1:{port}"
    source = _source(port)
    connector = FirstPartyCareerConnector(
        fetcher=lambda _: None,
        browser_mode=True,
        allow_insecure_test_origin=True,
        test_only_allowed_origin=origin,
    )

    assert connector._parse_index(
        source,
        f"{origin}/careers/positions/",
        b'<a class="job-card" href="/careers/positions/platform-engineer/">Platform</a>',
    ) == [f"{origin}/careers/positions/platform-engineer"]


def test_detail_identity_preserves_origin_and_ignores_off_origin_jsonld_url() -> None:
    port = 52615
    origin = f"http://127.0.0.1:{port}"
    source = _source(port)
    connector = FirstPartyCareerConnector(
        fetcher=lambda _: None,
        browser_mode=True,
        allow_insecure_test_origin=True,
        test_only_allowed_origin=origin,
    )
    payload = json.dumps(
        {
            "@type": "JobPosting",
            "title": "Platform Engineer",
            "description": "Build platform systems.",
            "url": "https://evil.example/careers/positions/platform-engineer",
            "hiringOrganization": {"name": "Local Browser Company"},
        }
    )

    record = connector._extract_detail(
        source,
        f"{origin}/careers/positions/platform-engineer",
        f'<script type="application/ld+json">{payload}</script>'.encode(),
    )

    assert record is not None
    assert str(record.official_url) == f"{origin}/careers/positions/platform-engineer"
    assert record.external_job_id == "platform-engineer"


def test_canonicalization_preserves_non_default_https_port_and_normalizes_default_port() -> None:
    source = _source(52616)

    assert _canonical_url(
        "https://127.0.0.1:8443/careers/positions/platform-engineer/", source
    ) == "https://127.0.0.1:8443/careers/positions/platform-engineer"
    assert _canonical_url(
        "https://127.0.0.1:443/careers/positions/platform-engineer/", source
    ) == "https://127.0.0.1/careers/positions/platform-engineer"


def test_local_detail_fixture_serves_the_canonicalized_detail_path() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RenderedJobsHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        connection.request("GET", "/careers/positions/platform-engineer")
        response = connection.getresponse()
        assert response.status == 200
        assert "application/ld+json" in response.read().decode("utf-8")
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
