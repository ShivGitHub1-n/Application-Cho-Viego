from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx

from resume_tailor.domain.job_discovery.models import (
    ConnectorType,
    JobSourceFetchResult,
    LeverApiRegion,
    SourceJobRecord,
    SourceRecordWarning,
    SourceRecordWarningCode,
    SupportedJobSource,
    VerificationConfidence,
    VerificationResult,
    VerificationStatus,
)
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


class LeverConnector:
    def __init__(
        self,
        client: httpx.Client,
        *,
        timeout: float = 15.0,
        page_size: int = 100,
        max_pages: int = 20,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if page_size <= 0 or max_pages <= 0:
            raise ValueError("Lever pagination bounds must be positive")
        self._client = client
        self._timeout = timeout
        self._page_size = page_size
        self._max_pages = max_pages
        self._clock = clock or (lambda: datetime.now(UTC))

    def fetch(self, source: SupportedJobSource, *, fetched_at: datetime) -> JobSourceFetchResult:
        self._validate_source(source)
        records = []
        warnings: list[SourceRecordWarning] = []
        base_url = self._base_url(source)
        for page_number in range(self._max_pages):
            skip = page_number * self._page_size
            payload = request_json(
                self._client,
                f"{base_url}/v0/postings/{quote(source.board_token, safe='')}",
                timeout=self._timeout,
                params={"mode": "json", "skip": str(skip), "limit": str(self._page_size)},
            )
            if not isinstance(payload, list):
                raise JobSourceEnvelopeError("Lever response must be a postings list")
            for raw in payload:
                record, record_warnings = self._record(raw, source)
                warnings.extend(record_warnings)
                if record is not None:
                    records.append(record)
            if len(payload) < self._page_size:
                break
        records.sort(key=lambda item: item.external_job_id)
        return JobSourceFetchResult(records=records, warnings=sorted_warnings(warnings))

    def check(self, source: SupportedJobSource, external_job_id: str) -> VerificationResult:
        self._validate_source(source)
        checked_at = self._clock()
        try:
            payload = request_json(
                self._client,
                (
                    f"{self._base_url(source)}/v0/postings/"
                    f"{quote(source.board_token, safe='')}/"
                    f"{quote(external_job_id, safe='')}"
                ),
                timeout=self._timeout,
            )
        except JobSourceNotFoundError:
            return VerificationResult(
                status=VerificationStatus.UNAVAILABLE,
                confidence=VerificationConfidence.LOW,
                checked_at=checked_at,
                message="The Lever posting was not found.",
            )
        if not isinstance(payload, dict):
            raise JobSourceEnvelopeError("Lever availability response must be an object")
        identity_valid = (
            bool(str(payload.get("id", "")).strip())
            and bool(str(payload.get("text", "")).strip())
            and canonical_url(payload.get("hostedUrl"), source) is not None
        )
        state = _text(payload.get("state") or payload.get("status")).casefold()
        if state in {"closed", "expired", "archived"}:
            status = VerificationStatus.EXPIRED
        elif state in {"open", "active", "published"} and identity_valid:
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
            message="The Lever posting is available from the official source."
            if status is VerificationStatus.VERIFIED_ACTIVE
            else "The Lever response returned the posting with limited status information."
            if status is VerificationStatus.VERIFIED_STATUS_UNKNOWN
            else "The Lever source marked the posting expired.",
        )

    def _record(
        self, raw: Any, source: SupportedJobSource
    ) -> tuple[SourceJobRecord | None, list[SourceRecordWarning]]:
        if not isinstance(raw, dict):
            return None, [
                warning(
                    None,
                    SourceRecordWarningCode.INVALID_RECORD_SHAPE,
                    "Lever posting is not an object.",
                )
            ]
        external_job_id = _text(raw.get("id"))
        if not external_job_id:
            return None, [
                warning(
                    None,
                    SourceRecordWarningCode.MISSING_EXTERNAL_JOB_ID,
                    "Lever posting is missing an id.",
                )
            ]
        title = _text(raw.get("text"))
        if not title:
            return None, [
                warning(
                    external_job_id,
                    SourceRecordWarningCode.MISSING_TITLE,
                    "Lever posting is missing a title.",
                )
            ]
        official_url = canonical_url(raw.get("hostedUrl"), source)
        if official_url is None:
            return None, [
                warning(
                    external_job_id,
                    SourceRecordWarningCode.INVALID_OFFICIAL_URL,
                    "Lever posting has an invalid official URL.",
                )
            ]

        categories = raw.get("categories")
        if not isinstance(categories, dict):
            categories = {}
        location_raw = _text(categories.get("location")) or None
        warnings: list[SourceRecordWarning] = []
        if location_raw is None:
            warnings.append(
                warning(
                    external_job_id,
                    SourceRecordWarningCode.INVALID_LOCATION,
                    "Lever posting location is invalid.",
                )
            )
        description = _text(raw.get("descriptionPlain")) or _text(raw.get("description"))
        updated_at, invalid_timestamp = parse_timestamp(raw.get("updatedAt"))
        if invalid_timestamp:
            warnings.append(
                warning(
                    external_job_id,
                    SourceRecordWarningCode.INVALID_TIMESTAMP,
                    "Lever updatedAt is invalid.",
                )
            )
        record = build_record(
            external_job_id=external_job_id,
            title=title,
            company_name=source.company_name,
            description=description,
            official_url=official_url,
            location_raw=location_raw,
            work_arrangement=arrangement(raw.get("workplaceType"), description, location_raw or ""),
            posted_at=None,
            source_updated_at=updated_at,
            application_deadline=None,
            source_payload=dict(raw),
        )
        return record, warnings

    @staticmethod
    def _validate_source(source: SupportedJobSource) -> None:
        if source.connector_type is not ConnectorType.LEVER:
            raise ValueError("LeverConnector requires a Lever source")
        if source.lever_api_region is None:
            raise ValueError("Lever source requires an API region")

    @staticmethod
    def _base_url(source: SupportedJobSource) -> str:
        if source.lever_api_region is LeverApiRegion.GLOBAL:
            return "https://api.lever.co"
        if source.lever_api_region is LeverApiRegion.EU:
            return "https://api.eu.lever.co"
        raise ValueError("unsupported Lever API region")


def _text(value: Any) -> str:
    return (
        value.strip()
        if isinstance(value, str)
        else str(value).strip()
        if isinstance(value, int)
        else ""
    )


__all__ = ["LeverConnector"]
