"""Static-first retrieval for audited employer career pages.

The module deliberately accepts either the repository's SafeHttpClient or a
project-controlled fetcher in tests. It never follows an application URL.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import datetime
from html.parser import HTMLParser
from typing import Any, cast
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from pydantic import AnyHttpUrl, TypeAdapter, ValidationError

from resume_tailor.domain.job_discovery.models import (
    ConnectorType,
    FeedKind,
    FirstPartySource,
    JobSourceFetchResult,
    SourceJobRecord,
    SourceRecordWarning,
    SourceRecordWarningCode,
)
from resume_tailor.domain.job_discovery.providers import (
    JobSourcePage,
    ProviderCapabilities,
    ProviderCursor,
)
from resume_tailor.domain.job_discovery.queries import ProviderJobQuery
from resume_tailor.infrastructure.job_sources._common import (
    _normalize_origin,
    _Origin,
    _url_origin,
    arrangement,
    build_record,
    parse_timestamp,
    sorted_warnings,
    warning,
)
from resume_tailor.infrastructure.job_sources.safe_http import SafeHttpClient

_HTTP_URL = TypeAdapter(AnyHttpUrl)
_MAX_BODY_BYTES = 2 * 1024 * 1024
_MAX_CURSOR_BYTES = 64 * 1024
_MAX_JSONLD_SCRIPTS = 64
_MAX_JSONLD_BYTES = 512 * 1024
_MAX_SITEMAP_DEPTH = 2
_MAX_SITEMAPS = 20
_MAX_DISCOVERED_URLS = 2_000
_APPROVED_QUERY_FIELDS = frozenset(
    {
        "feed_kind",
        "sectors",
        "role_families",
        "titles",
        "locations",
        "work_arrangements",
        "levels",
        "employment_types",
        "max_posting_age_days",
        "posted_after",
        "source_restrictions",
        "page_size",
        "cursor",
    }
)


class FirstPartySourceError(RuntimeError):
    """A bounded first-party source operation failed safely."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class _HtmlDocument(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.link_attributes: list[tuple[str, dict[str, str | None]]] = []
        self.canonical: str | None = None
        self.scripts: list[str] = []
        self._script_buffer: list[str] = []
        self._in_jsonld = False
        self._suppressed = 0
        self._heading: list[str] = []
        self._description: list[str] = []
        self._in_heading = False
        self._in_description = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        lowered = tag.casefold()
        if lowered in {"script", "style", "noscript", "template"}:
            self._suppressed += 1
        if (
            lowered == "script"
            and (attributes.get("type", "") or "").casefold() == "application/ld+json"
        ):
            self._in_jsonld = True
            self._script_buffer = []
        if lowered == "a" and self._suppressed == 0 and attributes.get("href"):
            href = attributes["href"] or ""
            self.links.append(href)
            self.link_attributes.append((href, attributes))
        if lowered == "link" and (attributes.get("rel", "") or "").casefold() == "canonical":
            self.canonical = attributes.get("href")
        hidden = (
            "hidden" in attributes or (attributes.get("aria-hidden", "") or "").casefold() == "true"
        )
        classes = (attributes.get("class", "") or "").casefold().split()
        self._in_heading = lowered in {"h1", "h2"} and not hidden and self._suppressed == 0
        self._in_description = (
            self._suppressed == 0
            and ("job-description" in classes or "posting-description" in classes)
            and not hidden
        )

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.casefold()
        if lowered == "script" and self._in_jsonld:
            self.scripts.append("".join(self._script_buffer))
            self._in_jsonld = False
            self._script_buffer = []
        self._in_heading = False if lowered in {"h1", "h2"} else self._in_heading
        self._in_description = (
            False if lowered in {"div", "section", "article"} else self._in_description
        )
        if lowered in {"script", "style", "noscript", "template"}:
            self._suppressed = max(self._suppressed - 1, 0)

    def handle_data(self, data: str) -> None:
        if self._in_jsonld:
            self._script_buffer.append(data)
        if self._suppressed:
            return
        if self._in_heading:
            self._heading.append(data)
        if self._in_description:
            self._description.append(data)


def _text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.replace("\xa0", " ").split())


def _canonical_url(
    value: str,
    source: FirstPartySource,
    *,
    test_origin: _Origin | None = None,
) -> str | None:
    parsed = urlsplit(value.strip())
    scheme = parsed.scheme.casefold()
    if parsed.username or parsed.password or parsed.fragment:
        return None
    if scheme != "https" and not (
        test_origin is not None and _url_origin(value) == test_origin
    ):
        return None
    host = (parsed.hostname or "").casefold().rstrip(".")
    if host not in set(source.source_plan.navigation_hosts):
        return None
    path = re.sub(r"/{2,}", "/", parsed.path or "/").rstrip("/") or "/"
    if not any(
        re.search(pattern, path) for pattern in source.source_plan.allowed_job_path_patterns
    ):
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    default_port = 443 if scheme == "https" else 80
    netloc = host if port in (None, default_port) else f"{host}:{port}"
    return urlunsplit((scheme, netloc, path, "", ""))


def _application_url(value: Any, source: FirstPartySource) -> AnyHttpUrl | None:
    candidate = _text(value)
    if not candidate or source.first_party_audit is None:
        return None
    if not source.first_party_audit.is_application_url_allowed(candidate):
        return None
    try:
        return _HTTP_URL.validate_python(candidate)
    except ValidationError:
        return None


def _jobposting(value: Any, *, depth: int = 0) -> list[dict[str, Any]]:
    if depth > 8:
        return []
    if isinstance(value, list):
        output: list[dict[str, Any]] = []
        for item in value[:64]:
            output.extend(_jobposting(item, depth=depth + 1))
        return output
    if not isinstance(value, dict):
        return []
    type_value = value.get("@type")
    types = (
        [type_value]
        if isinstance(type_value, str)
        else type_value
        if isinstance(type_value, list)
        else []
    )
    output = [value] if "JobPosting" in types else []
    graph = value.get("@graph")
    if graph is not None:
        output.extend(_jobposting(graph, depth=depth + 1))
    return output


def _parse_jsonld(document: _HtmlDocument) -> list[dict[str, Any]]:
    if len(document.scripts) > _MAX_JSONLD_SCRIPTS:
        raise FirstPartySourceError("response_too_large", "structured data script count exceeded")
    total = sum(len(script.encode("utf-8")) for script in document.scripts)
    if total > _MAX_JSONLD_BYTES:
        raise FirstPartySourceError("response_too_large", "structured data byte limit exceeded")
    candidates: list[dict[str, Any]] = []
    for script in document.scripts:
        try:
            candidates.extend(_jobposting(json.loads(script)))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    return sorted(candidates, key=lambda item: (_text(item.get("url")), _text(item.get("title"))))


def _first(value: Any) -> Any:
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _location(value: Any) -> str | None:
    value = _first(value)
    if not isinstance(value, dict):
        return _text(value) or None
    address = value.get("address", value)
    if isinstance(address, dict):
        fields = [
            address.get(key)
            for key in (
                "streetAddress",
                "addressLocality",
                "addressRegion",
                "postalCode",
                "addressCountry",
            )
        ]
        return ", ".join(_text(item) for item in fields if _text(item)) or None
    return _text(address) or None


class FirstPartyCareerConnector:
    def __init__(
        self,
        client: SafeHttpClient | None = None,
        *,
        fetcher: Callable[[str], httpx.Response] | None = None,
        robots_checker: Callable[[str], bool] | None = None,
        browser_fallback: Any | None = None,
        max_body_bytes: int = _MAX_BODY_BYTES,
        browser_mode: bool = False,
        allow_insecure_test_origin: bool = False,
        test_only_allowed_origin: str | None = None,
    ) -> None:
        if client is None and fetcher is None:
            raise ValueError("FirstPartyCareerConnector requires the approved safe HTTP client")
        self._client = client
        self._fetcher = fetcher
        self._robots_checker = robots_checker
        self._browser_fallback = browser_fallback
        self._max_body_bytes = max_body_bytes
        self._browser_mode = browser_mode
        self._allow_insecure_test_origin = allow_insecure_test_origin
        self._test_origin_value = test_only_allowed_origin
        self._test_origin = (
            _normalize_origin(test_only_allowed_origin)
            if test_only_allowed_origin
            else None
        )

    def capabilities(self, source: FirstPartySource) -> ProviderCapabilities:
        self._validate_source(source)
        return ProviderCapabilities(
            connector_type=ConnectorType.FIRST_PARTY,
            supports_title_or_keyword=False,
            supports_sector=False,
            supports_location=False,
            supports_work_arrangement=False,
            supports_level=False,
            supports_employment_type=False,
            supports_posting_date_boundary=False,
            supports_pagination=True,
            supports_page_size=True,
            supports_availability_checks=False,
            max_page_size=100,
        )

    def fetch_page(
        self,
        source: FirstPartySource,
        query: ProviderJobQuery,
        cursor: ProviderCursor,
        *,
        fetched_at: datetime,
    ) -> JobSourcePage:
        self._validate_source(source)
        if set(query.model_fields_set) - _APPROVED_QUERY_FIELDS:
            raise FirstPartySourceError("source_plan_invalid", "query contains an unapproved field")
        state = self._decode_cursor(cursor.value)
        if state is None:
            try:
                urls = self._discover(source)
            except FirstPartySourceError as error:
                if error.code == "browser_required" and self._browser_fallback is not None:
                    return cast(
                        JobSourcePage,
                        self._browser_fallback.fetch_page(
                            source, query, cursor, fetched_at=fetched_at
                        ),
                    )
                raise
            offset = 0
        else:
            urls = state["urls"]
            offset = state["offset"]
        page_size = min(query.page_size, 100, source.source_plan.max_job_detail_pages)
        selected = urls[offset : offset + page_size]
        records: list[SourceJobRecord] = []
        warnings: list[SourceRecordWarning] = []
        for url in selected:
            try:
                response = self._get(url, source)
                record = self._extract_detail(source, url, response.content)
            except FirstPartySourceError as error:
                warnings.append(
                    warning(
                        url,
                        SourceRecordWarningCode.INVALID_RECORD_SHAPE,
                        error.code,
                    )
                )
                continue
            if record is not None:
                records.append(record)
        next_offset = offset + len(selected)
        has_more = next_offset < len(urls)
        next_cursor = (
            ProviderCursor(value=self._encode_cursor(urls, next_offset))
            if has_more
            else ProviderCursor()
        )
        records.sort(key=lambda item: (str(item.official_url), item.external_job_id))
        return JobSourcePage(
            source=source,
            cursor=cursor,
            next_cursor=next_cursor,
            records=records,
            warnings=sorted_warnings(warnings),
            has_more=has_more,
        )

    def fetch(self, source: FirstPartySource, *, fetched_at: datetime) -> JobSourceFetchResult:
        records: list[SourceJobRecord] = []
        warnings: list[SourceRecordWarning] = []
        cursor = ProviderCursor()
        for _ in range(source.source_plan.max_listing_pages):
            page = self.fetch_page(
                source,
                ProviderJobQuery(feed_kind=FeedKind.TAILORED, page_size=100),
                cursor,
                fetched_at=fetched_at,
            )
            records.extend(page.records)
            warnings.extend(page.warnings)
            if not page.has_more:
                break
            cursor = page.next_cursor
        return JobSourceFetchResult(records=records, warnings=sorted_warnings(warnings))

    def _discover(self, source: FirstPartySource) -> list[str]:
        mode = source.source_plan.listing_discovery_mode
        if mode is None:
            raise FirstPartySourceError("source_plan_invalid", "listing discovery mode is missing")
        if mode.value == "direct_detail_urls":
            candidates = [str(url) for url in source.source_plan.direct_detail_urls]
        elif mode.value == "sitemap":
            candidates = self._discover_sitemap(source)
        elif mode.value in {"static_index", "browser_index"}:
            if mode.value == "browser_index" and not self._browser_mode:
                raise FirstPartySourceError("browser_required", "browser index is not static")
            candidates = []
            for index_url in source.source_plan.index_urls[: source.source_plan.max_listing_pages]:
                response = self._get(str(index_url), source)
                candidates.extend(self._parse_index(source, str(index_url), response.content))
        else:
            raise FirstPartySourceError("unsupported_fetch_mode", "listing mode is not supported")
        unique = sorted({url for url in candidates if self._validate_detail_url(url, source)})
        if len(unique) > _MAX_DISCOVERED_URLS:
            raise FirstPartySourceError("response_too_large", "discovered URL limit exceeded")
        return unique

    def _discover_sitemap(self, source: FirstPartySource) -> list[str]:
        discovered: set[str] = set()
        pending = [(str(url), 0) for url in source.source_plan.sitemap_urls]
        visited = 0
        while pending and visited < _MAX_SITEMAPS:
            url, depth = pending.pop(0)
            if depth > _MAX_SITEMAP_DEPTH:
                raise FirstPartySourceError(
                    "sitemap_parse_failed", "sitemap nesting depth exceeded"
                )
            response = self._get(url, source, allow_sitemap=True)
            body = response.content
            if b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
                raise FirstPartySourceError(
                    "sitemap_parse_failed", "XML external entities are not permitted"
                )
            try:
                root = ET.fromstring(body)
            except ET.ParseError as exc:
                raise FirstPartySourceError(
                    "sitemap_parse_failed", "sitemap XML is malformed"
                ) from exc
            namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
            tag = root.tag.rsplit("}", 1)[-1]
            locations = [
                node.text.strip()
                for node in root.iter()
                if node.tag == f"{namespace}loc" and node.text and node.text.strip()
            ]
            if tag == "sitemapindex":
                for item in locations:
                    if not self._validate_sitemap_url(item, source):
                        continue
                    pending.append((item, depth + 1))
            elif tag == "urlset":
                for item in locations:
                    if self._validate_detail_url(item, source):
                        discovered.add(_canonical_detail(item, source))
            else:
                raise FirstPartySourceError("sitemap_parse_failed", "unsupported sitemap root")
            visited += 1
            if len(discovered) > _MAX_DISCOVERED_URLS:
                raise FirstPartySourceError("response_too_large", "sitemap URL limit exceeded")
        if pending:
            raise FirstPartySourceError("sitemap_parse_failed", "sitemap count limit exceeded")
        return sorted(discovered)

    def _parse_index(self, source: FirstPartySource, base_url: str, body: bytes) -> list[str]:
        if len(body) > self._max_body_bytes:
            raise FirstPartySourceError("response_too_large", "index response is too large")
        stripped = body.lstrip()
        if stripped.startswith(b"{"):
            try:
                payload = json.loads(body)
            except json.JSONDecodeError as exc:
                raise FirstPartySourceError(
                    "listing_parse_failed", "index JSON is malformed"
                ) from exc
            cards = payload.get("cards", []) if isinstance(payload, dict) else []
            return [
                str(card.get("detail_url"))
                for card in cards[:_MAX_DISCOVERED_URLS]
                if isinstance(card, dict) and isinstance(card.get("detail_url"), str)
            ]
        document = _HtmlDocument()
        try:
            document.feed(body.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise FirstPartySourceError("listing_parse_failed", "index is not UTF-8") from exc
        profile = source.extraction_profile
        if profile is None:
            raise FirstPartySourceError(
                "extraction_profile_mismatch",
                "static index requires an approved extraction profile",
            )
        links: list[str] = []
        for link, attributes in document.link_attributes:
            if profile.job_card_attributes and not _matches_link_attributes(
                attributes, profile.job_card_attributes
            ):
                continue
            candidate = urljoin(base_url, link)
            candidate_path = urlsplit(candidate).path or "/"
            if profile.allowed_link_path_patterns and not any(
                re.search(pattern, candidate_path) for pattern in profile.allowed_link_path_patterns
            ):
                continue
            if self._validate_detail_url(candidate, source):
                links.append(_canonical_detail(candidate, source, self._test_origin))
        if not links:
            if re.search(
                r"load[\s_-]*more|infinite[\s_-]*scroll|javascript",
                body.decode("utf-8", errors="ignore"),
                re.I,
            ):
                raise FirstPartySourceError(
                    "browser_required", "static index requires browser rendering"
                )
            raise FirstPartySourceError(
                "listing_parse_failed", "audited detail selector found no URLs"
            )
        return links

    def _extract_detail(
        self, source: FirstPartySource, detail_url: str, body: bytes
    ) -> SourceJobRecord | None:
        if len(body) > self._max_body_bytes:
            raise FirstPartySourceError("response_too_large", "detail response is too large")
        document = _HtmlDocument()
        try:
            document.feed(body.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise FirstPartySourceError("detail_fetch_failed", "detail is not UTF-8") from exc
        candidates = _parse_jsonld(document)
        candidate = next(
            (
                item
                for item in candidates
                if _canonical_url(
                    _text(item.get("url")), source, test_origin=self._test_origin
                )
                in {
                    None,
                    _canonical_detail(detail_url, source, self._test_origin),
                }
            ),
            candidates[0] if candidates else None,
        )
        candidate_canonical = (
            _canonical_url(_text(candidate.get("url")), source, test_origin=self._test_origin)
            if candidate
            else None
        )
        canonical = candidate_canonical
        if canonical is None:
            canonical = _canonical_url(
                document.canonical or "", source, test_origin=self._test_origin
            )
        if canonical is None:
            canonical = _canonical_detail(detail_url, source, self._test_origin)
        if canonical is None:
            raise FirstPartySourceError(
                "identity_missing", "canonical employer detail URL is missing"
            )
        title = _text(candidate.get("title")) if candidate else _text("".join(document._heading))
        description = (
            _text(candidate.get("description"))
            if candidate
            else _text("".join(document._description))
        )
        if not title:
            raise FirstPartySourceError("required_field_missing", "job title is missing")
        if not description:
            raise FirstPartySourceError("required_field_missing", "job description is missing")
        posted_at, _ = parse_timestamp(candidate.get("datePosted") if candidate else None)
        updated_at, _ = parse_timestamp(candidate.get("dateModified") if candidate else None)
        organization = candidate.get("hiringOrganization") if candidate else None
        if isinstance(organization, dict) and _text(organization.get("name")):
            company = _text(organization.get("name"))
        else:
            company = source.company_name
        location = _location(candidate.get("jobLocation")) if candidate else None
        job_type = _first(candidate.get("employmentType")) if candidate else None
        work = arrangement(
            candidate.get("jobLocationType") if candidate else None, description, location or ""
        )
        application = _application_url(
            candidate.get("applicationUrl") if candidate else None, source
        )
        stable_id = stable_first_party_identity(
            source,
            canonical,
            test_only_allowed_origin=self._test_origin_value,
        )
        payload: dict[str, Any] = {
            "canonical_url": canonical,
            "identity_authority": "employer_detail_url",
        }
        if application is not None:
            payload["application_url"] = str(application)
        if isinstance(job_type, str) and job_type.strip():
            payload["employment_type"] = job_type.strip()
        return build_record(
            external_job_id=stable_id,
            title=title,
            company_name=company,
            description=description,
            official_url=_HTTP_URL.validate_python(canonical),
            application_url=application,
            location_raw=location,
            work_arrangement=work,
            posted_at=posted_at,
            source_updated_at=updated_at,
            application_deadline=None,
            source_payload=payload,
        )

    def _get(
        self, url: str, source: FirstPartySource, *, allow_sitemap: bool = False
    ) -> httpx.Response:
        if not (
            self._validate_sitemap_url(url, source)
            if allow_sitemap
            else self._validate_navigation_url(url, source)
        ):
            raise FirstPartySourceError(
                "detail_url_rejected", "URL is outside approved employer authority"
            )
        if self._robots_checker is not None and not self._robots_checker(url):
            raise FirstPartySourceError("robots_denied", "robots policy denied the source URL")
        if self._fetcher is not None:
            response = self._fetcher(url)
        else:
            assert self._client is not None
            response = self._client.get_sync(url)
        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().casefold()
        if content_type not in {
            "text/html",
            "application/xhtml+xml",
            "application/json",
            "application/xml",
            "text/xml",
            "text/plain",
        }:
            raise FirstPartySourceError(
                "content_type_rejected", "source content type is not approved"
            )
        if response.status_code >= 400:
            raise FirstPartySourceError("detail_fetch_failed", "employer page retrieval failed")
        if len(response.content) > self._max_body_bytes:
            raise FirstPartySourceError("response_too_large", "employer response is too large")
        return response

    @staticmethod
    def _validate_source(source: FirstPartySource) -> None:
        if source.connector_type is not ConnectorType.FIRST_PARTY:
            raise ValueError("FirstPartyCareerConnector requires a first-party source")
        if not source.enabled or source.first_party_audit is None:
            raise FirstPartySourceError("source_plan_invalid", "first-party source is not runnable")

    def _validate_navigation_url(self, url: str, source: FirstPartySource) -> bool:
        parsed = urlsplit(url)
        if parsed.username or parsed.password or parsed.fragment:
            return False
        actual_origin = _url_origin(url)
        if (
            self._test_origin is not None
            and actual_origin is not None
            and actual_origin.hostname == self._test_origin.hostname
            and actual_origin != self._test_origin
        ):
            return False
        if parsed.scheme != "https" and not (
            self._allow_insecure_test_origin
            and self._test_origin is not None
            and _url_origin(url) == self._test_origin
        ):
            return False
        host = (parsed.hostname or "").casefold().rstrip(".")
        return host in set(source.source_plan.navigation_hosts) and any(
            re.search(pattern, parsed.path or "/")
            for pattern in source.source_plan.allowed_job_path_patterns
        )

    def _validate_detail_url(self, url: str, source: FirstPartySource) -> bool:
        return self._validate_navigation_url(url, source)

    @classmethod
    def _validate_sitemap_url(cls, url: str, source: FirstPartySource) -> bool:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.fragment:
            return False
        host = (parsed.hostname or "").casefold().rstrip(".")
        return host in set(source.source_plan.navigation_hosts) and any(
            re.search(pattern, parsed.path or "/")
            for pattern in source.source_plan.sitemap_path_patterns
        )

    @staticmethod
    def _encode_cursor(urls: list[str], offset: int) -> str:
        value = json.dumps({"urls": urls, "offset": offset}, separators=(",", ":"), sort_keys=True)
        if len(value.encode("utf-8")) > _MAX_CURSOR_BYTES:
            raise FirstPartySourceError("response_too_large", "cursor is too large")
        return value

    @staticmethod
    def _decode_cursor(value: str | None) -> dict[str, Any] | None:
        if value is None:
            return None
        if len(value.encode("utf-8")) > _MAX_CURSOR_BYTES:
            raise FirstPartySourceError("source_plan_invalid", "cursor is too large")
        try:
            state = json.loads(value)
        except json.JSONDecodeError as exc:
            raise FirstPartySourceError("source_plan_invalid", "cursor is malformed") from exc
        if (
            not isinstance(state, dict)
            or not isinstance(state.get("urls"), list)
            or not isinstance(state.get("offset"), int)
        ):
            raise FirstPartySourceError("source_plan_invalid", "cursor state is invalid")
        if state["offset"] < 0 or any(not isinstance(item, str) for item in state["urls"]):
            raise FirstPartySourceError("source_plan_invalid", "cursor state is invalid")
        return {"urls": state["urls"][:_MAX_DISCOVERED_URLS], "offset": state["offset"]}

def _matches_link_attributes(
    actual: dict[str, str | None], expected: dict[str, str]
) -> bool:
    for name, value in expected.items():
        actual_value = actual.get(name.casefold()) or ""
        if name.casefold() == "class":
            if value not in actual_value.split():
                return False
        elif actual_value != value:
            return False
    return True


def _canonical_detail(
    url: str,
    source: FirstPartySource,
    test_origin: _Origin | None = None,
) -> str:
    canonical = _canonical_url(url, source, test_origin=test_origin)
    if canonical is None:
        raise FirstPartySourceError(
            "detail_url_rejected", "detail URL is outside approved employer authority"
        )
    return canonical


def _stable_id(canonical: str) -> str:
    path = urlsplit(canonical).path.rstrip("/")
    return path.rsplit("/", 1)[-1] or canonical


def stable_first_party_identity(
    source: FirstPartySource,
    detail_url: str,
    *,
    test_only_allowed_origin: str | None = None,
) -> str:
    test_origin = (
        _normalize_origin(test_only_allowed_origin)
        if test_only_allowed_origin
        else None
    )
    canonical = _canonical_url(detail_url, source, test_origin=test_origin)
    if canonical is None:
        raise FirstPartySourceError(
            "identity_missing", "detail URL is not an approved canonical URL"
        )
    return _stable_id(canonical)


__all__ = ["FirstPartyCareerConnector", "FirstPartySourceError", "stable_first_party_identity"]
