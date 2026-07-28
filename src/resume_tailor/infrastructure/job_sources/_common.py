from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from pydantic import AnyHttpUrl, TypeAdapter, ValidationError

from resume_tailor.domain.job_discovery.models import (
    SourceJobRecord,
    SourceRecordWarning,
    SourceRecordWarningCode,
    SupportedJobSource,
    WorkArrangement,
)
from resume_tailor.domain.job_discovery.normalization import _canonical_url

_HTTP_URL = TypeAdapter(AnyHttpUrl)


@dataclass(frozen=True)
class _Origin:
    scheme: str
    hostname: str
    port: int


def _normalize_origin(value: str) -> _Origin | None:
    parsed = urlsplit(value)
    if (
        parsed.scheme.casefold() not in {"http", "https"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or parsed.hostname is None
        or parsed.hostname.casefold().rstrip(".") not in {"127.0.0.1", "localhost"}
    ):
        return None
    try:
        port = parsed.port or (443 if parsed.scheme.casefold() == "https" else 80)
    except ValueError:
        return None
    if not 1 <= port <= 65535:
        return None
    return _Origin(parsed.scheme.casefold(), parsed.hostname.casefold().rstrip("."), port)


def _url_origin(value: str) -> _Origin | None:
    parsed = urlsplit(value)
    if parsed.username or parsed.password or parsed.hostname is None:
        return None
    try:
        port = parsed.port or (443 if parsed.scheme.casefold() == "https" else 80)
    except ValueError:
        return None
    if not 1 <= port <= 65535:
        return None
    return _Origin(parsed.scheme.casefold(), parsed.hostname.casefold().rstrip("."), port)


def parse_timestamp(value: Any) -> tuple[datetime | None, bool]:
    if value is None:
        return None, False
    if not isinstance(value, str) or not value.strip():
        return None, True
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None, True
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC), False


def warning(
    external_job_id: str | None,
    code: SourceRecordWarningCode,
    message: str,
) -> SourceRecordWarning:
    return SourceRecordWarning(external_job_id=external_job_id, code=code, message=message)


def sorted_warnings(warnings: list[SourceRecordWarning]) -> list[SourceRecordWarning]:
    return sorted(
        warnings,
        key=lambda item: (item.external_job_id or "", item.code.value, item.message),
    )


def canonical_url(value: Any, source: SupportedJobSource) -> AnyHttpUrl | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = _canonical_url(value, source)
    try:
        parsed = _HTTP_URL.validate_python(candidate)
    except ValidationError:
        return None
    return parsed


def arrangement(value: Any, *text_values: str) -> WorkArrangement:
    if isinstance(value, str):
        normalized = re.sub(r"[-_]+", " ", value.casefold()).strip()
        if normalized in {"remote", "fully remote"}:
            return WorkArrangement.REMOTE
        if normalized in {"hybrid", "flexible hybrid"}:
            return WorkArrangement.HYBRID
        if normalized in {"onsite", "on site", "on-site", "in office"}:
            return WorkArrangement.ONSITE
    text = " ".join(text_values).casefold()
    if re.search(r"\bhybrid\b", text):
        return WorkArrangement.HYBRID
    if re.search(r"\b(remote|work from home)\b", text):
        return WorkArrangement.REMOTE
    if re.search(r"\b(on[- ]site|onsite|in office)\b", text):
        return WorkArrangement.ONSITE
    return WorkArrangement.UNKNOWN


def build_record(
    *,
    external_job_id: str,
    title: str,
    company_name: str,
    description: str,
    official_url: AnyHttpUrl,
    application_url: AnyHttpUrl | None = None,
    location_raw: str | None,
    work_arrangement: WorkArrangement,
    posted_at: datetime | None,
    source_updated_at: datetime | None,
    application_deadline: datetime | None,
    source_payload: dict[str, Any],
) -> SourceJobRecord:
    return SourceJobRecord(
        external_job_id=external_job_id,
        title=title,
        company_name=company_name,
        description=description,
        official_url=official_url,
        application_url=application_url,
        location_raw=location_raw,
        work_arrangement=work_arrangement,
        posted_at=posted_at,
        source_updated_at=source_updated_at,
        application_deadline=application_deadline,
        source_payload=source_payload,
    )
