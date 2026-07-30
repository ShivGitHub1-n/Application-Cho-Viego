from __future__ import annotations

import ipaddress
import re
import socket
from datetime import date
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

from resume_tailor.domain.company_research import ApprovedCompanySource, CompanySourceDocument

_MAX_RESPONSE_BYTES = 1_000_000


class CompanySourceFetchError(ValueError):
    pass


class _ReadableHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._in_title = False
        self._ignored_depth = 0
        self._parts: list[str] = []

    @property
    def text(self) -> str:
        return " ".join(" ".join(self._parts).split())

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        normalized = tag.casefold()
        if normalized in {"script", "style", "noscript", "svg"}:
            self._ignored_depth += 1
        elif normalized == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.casefold()
        if normalized in {"script", "style", "noscript", "svg"} and self._ignored_depth:
            self._ignored_depth -= 1
        elif normalized == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        cleaned = " ".join(data.split())
        if not cleaned:
            return
        if self._in_title:
            self.title = f"{self.title} {cleaned}".strip()
        else:
            self._parts.append(cleaned)


class HttpxOfficialCompanySourceFetcher:
    """Fetch only explicit, bounded, allowlisted public company pages."""

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        timeout_seconds: float = 8.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("Company-source timeout must be positive")
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=False,
            headers={"User-Agent": "Application-Viego/0.1 company-research"},
        )

    def fetch(
        self,
        source: ApprovedCompanySource,
        *,
        company_domain: str,
    ) -> CompanySourceDocument:
        expected_domain = self._normalized_domain(company_domain)
        current_url = source.url
        final_url = source.url
        try:
            for redirect_count in range(4):
                self._validate_url(
                    current_url,
                    expected_domain=expected_domain,
                    approved_third_party=source.approved_third_party,
                )
                with self._client.stream(
                    "GET",
                    current_url,
                    follow_redirects=False,
                ) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location or redirect_count == 3:
                            raise CompanySourceFetchError(
                                "Approved company source exceeded the redirect limit"
                            )
                        current_url = urljoin(str(response.url), location)
                        continue
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").casefold()
                    if not any(value in content_type for value in ("text/html", "text/plain")):
                        raise CompanySourceFetchError(
                            "Approved source did not return readable text"
                        )
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > _MAX_RESPONSE_BYTES:
                            raise CompanySourceFetchError(
                                "Approved source exceeded the response-size limit"
                            )
                    final_url = str(response.url)
                    break
            else:
                raise CompanySourceFetchError("Approved company source exceeded the redirect limit")
        except (httpx.HTTPError, OSError) as error:
            raise CompanySourceFetchError("Approved company source could not be fetched") from error
        decoded = bytes(body).decode("utf-8", errors="replace")
        if "text/html" in content_type:
            parser = _ReadableHtmlParser()
            parser.feed(decoded)
            text = parser.text
            title = parser.title
        else:
            text = " ".join(decoded.split())
            title = ""
        if len(text) < 35:
            raise CompanySourceFetchError(
                "Approved company source contained no useful readable text"
            )
        host = urlparse(final_url).hostname or expected_domain
        return CompanySourceDocument(
            source_url=final_url,
            title=title or host,
            publisher=host,
            source_type=source.source_type,
            retrieved_on=date.today(),
            text=text,
            verified_source=True,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    @classmethod
    def _validate_url(
        cls,
        value: str,
        *,
        expected_domain: str,
        approved_third_party: bool,
    ) -> None:
        parsed = urlparse(value)
        if parsed.scheme.casefold() != "https" or not parsed.hostname:
            raise CompanySourceFetchError("Company sources require a public HTTPS URL")
        host = cls._normalized_domain(parsed.hostname)
        if not approved_third_party and not cls._same_domain(host, expected_domain):
            raise CompanySourceFetchError("Company source is outside the approved company domain")
        cls._reject_private_host(host)

    @staticmethod
    def _normalized_domain(value: str) -> str:
        normalized = value.strip().casefold().rstrip(".")
        normalized = re.sub(r"^https?://", "", normalized).split("/", 1)[0]
        if not normalized or normalized == "localhost":
            raise CompanySourceFetchError("A public company domain is required")
        return normalized.encode("idna").decode("ascii")

    @staticmethod
    def _same_domain(host: str, expected: str) -> bool:
        return host == expected or host.endswith(f".{expected}")

    @staticmethod
    def _reject_private_host(host: str) -> None:
        try:
            addresses = {
                item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            }
        except OSError as error:
            raise CompanySourceFetchError("Company source host could not be resolved") from error
        for value in addresses:
            address = ipaddress.ip_address(value)
            if not address.is_global:
                raise CompanySourceFetchError("Company source resolved to a non-public address")


__all__ = ["CompanySourceFetchError", "HttpxOfficialCompanySourceFetcher"]
