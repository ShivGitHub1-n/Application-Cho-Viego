from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx

from resume_tailor.domain.job_discovery.models import (
    ConnectorType,
    JobSourceFetchResult,
    SourceJobRecord,
    SourceRecordWarning,
    SourceRecordWarningCode,
    SupportedJobSource,
    VerificationConfidence,
    VerificationResult,
    VerificationStatus,
)
from resume_tailor.domain.job_discovery.providers import (
    JobSourcePage,
    ProviderCapabilities,
    ProviderCursor,
)
from resume_tailor.domain.job_discovery.queries import ProviderJobQuery
from resume_tailor.infrastructure.job_sources._common import (
    arrangement,
    build_record,
    canonical_url,
    parse_timestamp,
    sorted_warnings,
    warning,
)
from resume_tailor.infrastructure.job_sources.errors import (
    JobSourceEnvelopeError,
    JobSourceNotFoundError,
    request_json,
)


class GreenhouseConnector:
    def __init__(
        self,
        client: httpx.Client,
        *,
        timeout: float = 15.0,
        fetch_details: bool = False,
        api_base_url: str = "https://boards-api.greenhouse.io",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._client = client
        self._timeout = timeout
        self._fetch_details = fetch_details
        self._api_base_url = api_base_url.rstrip("/")
        self._clock = clock or (lambda: datetime.now(UTC))

    def capabilities(self, source: SupportedJobSource) -> ProviderCapabilities:
        self._validate_source(source)
        return ProviderCapabilities(
            connector_type=ConnectorType.GREENHOUSE,
            supports_title_or_keyword=False,
            supports_sector=False,
            supports_location=False,
            supports_work_arrangement=False,
            supports_level=False,
            supports_employment_type=False,
            supports_posting_date_boundary=False,
            supports_pagination=False,
            supports_page_size=False,
            supports_availability_checks=True,
            posted_timestamp_authority="job_detail.first_published",
            updated_timestamp_authority="job.updated_at",
        )

    def fetch_page(
        self,
        source: SupportedJobSource,
        query: ProviderJobQuery,
        cursor: ProviderCursor,
        *,
        fetched_at: datetime,
    ) -> JobSourcePage:
        self._validate_source(source)
        if cursor.value is not None:
            raise JobSourceEnvelopeError("Greenhouse Job Board jobs are not paginated")
        payload = request_json(
            self._client,
            self._list_url(source),
            timeout=self._timeout,
            params={"content": "true"},
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            raise JobSourceEnvelopeError("Greenhouse response must contain a jobs list")

        records = []
        warnings: list[SourceRecordWarning] = []
        for raw in payload["jobs"]:
            record, record_warnings = self._record(raw, source)
            warnings.extend(record_warnings)
            if record is not None:
                records.append(record)
                if self._fetch_details:
                    detail = request_json(
                        self._client,
                        self._detail_url(source, record.external_job_id),
                        timeout=self._timeout,
                    )
                    self._apply_detail(record, detail, warnings)
        records.sort(key=lambda item: item.external_job_id)
        return JobSourcePage(
            source=source,
            cursor=cursor,
            records=records,
            warnings=sorted_warnings(warnings),
            has_more=False,
        )

    def fetch(self, source: SupportedJobSource, *, fetched_at: datetime) -> JobSourceFetchResult:
        page = self.fetch_page(
            source,
            ProviderJobQuery(feed_kind="tailored"),
            ProviderCursor(),
            fetched_at=fetched_at,
        )
        return JobSourceFetchResult(records=page.records, warnings=page.warnings)

    def check(self, source: SupportedJobSource, external_job_id: str) -> VerificationResult:
        self._validate_source(source)
        checked_at = self._clock()
        try:
            payload = request_json(
                self._client,
                self._detail_url(source, external_job_id),
                timeout=self._timeout,
            )
        except JobSourceNotFoundError:
            return VerificationResult(
                status=VerificationStatus.UNAVAILABLE,
                confidence=VerificationConfidence.LOW,
                checked_at=checked_at,
                message="The Greenhouse posting was not found.",
            )
        if not isinstance(payload, dict):
            raise JobSourceEnvelopeError("Greenhouse availability response must be an object")
        identity_valid = (
            isinstance(payload.get("id"), (str, int))
            and bool(str(payload.get("title", "")).strip())
            and canonical_url(payload.get("absolute_url"), source) is not None
        )
        state = _text(payload.get("state") or payload.get("status")).casefold()
        if state in {"closed", "expired", "archived"}:
            status = VerificationStatus.EXPIRED
        elif state in {"active", "open", "published"} and identity_valid:
            status = VerificationStatus.VERIFIED_ACTIVE
        elif not identity_valid:
            status = VerificationStatus.VERIFIED_STATUS_UNKNOWN
        else:
            status = (
                VerificationStatus.VERIFIED_ACTIVE
                if not state
                else VerificationStatus.VERIFIED_STATUS_UNKNOWN
            )
        confidence = (
            VerificationConfidence.HIGH
            if identity_valid and status is not VerificationStatus.VERIFIED_STATUS_UNKNOWN
            else VerificationConfidence.MEDIUM
            if identity_valid
            else VerificationConfidence.LOW
        )
        return VerificationResult(
            status=status,
            confidence=confidence,
            checked_at=checked_at,
            message="The Greenhouse posting is available from the official source."
            if status is VerificationStatus.VERIFIED_ACTIVE
            else "The Greenhouse response returned the posting with limited status information."
            if status is VerificationStatus.VERIFIED_STATUS_UNKNOWN
            else "The Greenhouse source marked the posting expired."
            if identity_valid
            else "The Greenhouse response did not contain all required posting identity fields.",
        )

    def _record(
        self, raw: Any, source: SupportedJobSource
    ) -> tuple[SourceJobRecord | None, list[SourceRecordWarning]]:
        if not isinstance(raw, dict):
            return None, [
                warning(
                    None,
                    SourceRecordWarningCode.INVALID_RECORD_SHAPE,
                    "Greenhouse job is not an object.",
                )
            ]
        external_job_id = _text(raw.get("id"))
        if not external_job_id:
            return None, [
                warning(
                    None,
                    SourceRecordWarningCode.MISSING_EXTERNAL_JOB_ID,
                    "Greenhouse job is missing an id.",
                )
            ]
        title = _text(raw.get("title"))
        if not title:
            return None, [
                warning(
                    external_job_id,
                    SourceRecordWarningCode.MISSING_TITLE,
                    "Greenhouse job is missing a title.",
                )
            ]
        official_url = canonical_url(raw.get("absolute_url"), source)
        if official_url is None:
            return None, [
                warning(
                    external_job_id,
                    SourceRecordWarningCode.INVALID_OFFICIAL_URL,
                    "Greenhouse job has an invalid official URL.",
                )
            ]

        location_raw = _location(raw.get("location"))
        warnings: list[SourceRecordWarning] = []
        if location_raw is None:
            warnings.append(
                warning(
                    external_job_id,
                    SourceRecordWarningCode.INVALID_LOCATION,
                    "Greenhouse job location is invalid.",
                )
            )
        updated_at, invalid_timestamp = parse_timestamp(raw.get("updated_at"))
        if invalid_timestamp:
            warnings.append(
                warning(
                    external_job_id,
                    SourceRecordWarningCode.INVALID_TIMESTAMP,
                    "Greenhouse updated_at is invalid.",
                )
            )
        record = build_record(
            external_job_id=external_job_id,
            title=title,
            company_name=source.company_name,
            description=_text(raw.get("content")) or _text(raw.get("description")),
            official_url=official_url,
            location_raw=location_raw,
            work_arrangement=arrangement(
                raw.get("workplace_type"),
                _text(raw.get("content")),
                location_raw or "",
            ),
            posted_at=None,
            source_updated_at=updated_at,
            application_deadline=None,
            source_payload=dict(raw),
        )
        return record, warnings

    def _apply_detail(
        self,
        record: SourceJobRecord,
        detail: Any,
        warnings: list[SourceRecordWarning],
    ) -> None:
        if not isinstance(detail, dict):
            raise JobSourceEnvelopeError("Greenhouse detail response must be an object")
        posted_at, posted_invalid = parse_timestamp(detail.get("first_published"))
        deadline, deadline_invalid = parse_timestamp(detail.get("application_deadline"))
        if posted_invalid or deadline_invalid:
            warnings.append(
                warning(
                    record.external_job_id,
                    SourceRecordWarningCode.INVALID_TIMESTAMP,
                    "Greenhouse detail timestamp is invalid.",
                )
            )
        record.posted_at = posted_at
        record.application_deadline = deadline

    def _list_url(self, source: SupportedJobSource) -> str:
        return f"{self._api_base_url}/v1/boards/{quote(source.board_token, safe='')}/jobs"

    def _detail_url(self, source: SupportedJobSource, external_job_id: str) -> str:
        return f"{self._list_url(source)}/{quote(external_job_id, safe='')}"

    @staticmethod
    def _validate_source(source: SupportedJobSource) -> None:
        if source.connector_type is not ConnectorType.GREENHOUSE:
            raise ValueError("GreenhouseConnector requires a Greenhouse source")


def _text(value: Any) -> str:
    return (
        value.strip()
        if isinstance(value, str)
        else str(value).strip()
        if isinstance(value, int)
        else ""
    )


def _location(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("name")
    return value.strip() if isinstance(value, str) and value.strip() else None


__all__ = ["GreenhouseConnector"]
