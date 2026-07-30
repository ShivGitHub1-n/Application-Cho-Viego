from __future__ import annotations

import ipaddress
import socket

import httpx
import pytest

from resume_tailor.domain.company_research import ApprovedCompanySource, CompanySourceType
from resume_tailor.infrastructure.company_research import (
    CompanySourceFetchError,
    HttpxOfficialCompanySourceFetcher,
)


@pytest.fixture(autouse=True)
def _controlled_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    def getaddrinfo(
        host: str,
        port: int,
        *,
        type: socket.SocketKind,
    ) -> list[tuple[object, object, object, str, tuple[str, int]]]:
        del type
        try:
            address = str(ipaddress.ip_address(host))
        except ValueError:
            address = "93.184.216.34"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)


def _source(url: str = "https://example.com/engineering") -> ApprovedCompanySource:
    return ApprovedCompanySource(
        url=url,
        source_type=CompanySourceType.OFFICIAL_ENGINEERING,
    )


def test_fetcher_reads_only_bounded_verified_first_party_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=(
                "<html><title>Engineering</title><body>Example Robotics builds embedded "
                "firmware and sensor test systems for autonomous robots.</body></html>"
            ),
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    document = HttpxOfficialCompanySourceFetcher(client).fetch(
        _source(),
        company_domain="example.com",
    )

    assert document.verified_source
    assert document.title == "Engineering"
    assert "embedded firmware" in document.text


def test_fetcher_rejects_cross_domain_source_before_request() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, text="should not be fetched", request=request)

    fetcher = HttpxOfficialCompanySourceFetcher(
        httpx.Client(transport=httpx.MockTransport(handler))
    )

    with pytest.raises(CompanySourceFetchError, match="outside the approved"):
        fetcher.fetch(_source("https://other.example.org/page"), company_domain="example.com")
    assert calls == 0


def test_fetcher_validates_redirect_destination_before_following() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(
            302,
            headers={"location": "https://127.0.0.1/private"},
            request=request,
        )

    fetcher = HttpxOfficialCompanySourceFetcher(
        httpx.Client(transport=httpx.MockTransport(handler))
    )

    with pytest.raises(CompanySourceFetchError, match="outside|non-public"):
        fetcher.fetch(_source(), company_domain="example.com")
    assert calls == ["https://example.com/engineering"]


def test_fetcher_rejects_oversized_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            content=b"a" * 1_000_001,
            request=request,
        )

    fetcher = HttpxOfficialCompanySourceFetcher(
        httpx.Client(transport=httpx.MockTransport(handler))
    )

    with pytest.raises(CompanySourceFetchError, match="response-size limit"):
        fetcher.fetch(_source(), company_domain="example.com")
