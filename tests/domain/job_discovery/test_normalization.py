from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

from resume_tailor.domain.job_discovery.models import (
    ConnectorType,
    SourceJobRecord,
    SupportedJobSource,
    WorkArrangement,
)
from resume_tailor.domain.job_discovery.normalization import (
    JobNormalizer,
    normalize_job_record,
)

WHEN = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


def _source() -> SupportedJobSource:
    return SupportedJobSource(
        source_id="acme-board",
        connector_type=ConnectorType.GREENHOUSE,
        company_name="Acme Robotics",
        board_token="acme",
        enabled=True,
        official_base_url="https://boards.greenhouse.io",
    )


def _record(**overrides: object) -> SourceJobRecord:
    values: dict[str, object] = {
        "external_job_id": " 123 ",
        "title": "  Senior   JS/TS Engineer!!! ",
        "company_name": " ACME ROBOTICS ",
        "description": "  Build\r\n\r\n  JavaScript and TypeScript services. ",
        "official_url": "http://boards.greenhouse.io/acme/jobs/123/?utm_source=feed#job",
        "location_raw": " Toronto, ON, Canada ",
        "work_arrangement": WorkArrangement.HYBRID,
        "posted_at": datetime(2026, 7, 1, 12, 0, tzinfo=UTC),
        "source_updated_at": None,
        "application_deadline": None,
        "source_payload": {"requisition_id": "REQ-123", "provider": "greenhouse"},
    }
    values.update(overrides)
    return SourceJobRecord(**values)


def test_normalization_is_deterministic_and_preserves_provenance() -> None:
    record = _record()
    before = deepcopy(record.model_dump(mode="python"))

    normalized = normalize_job_record(record, _source(), fetched_at=WHEN)

    assert normalized.external_job_id == "123"
    assert normalized.title == "Senior JS/TS Engineer!!!"
    assert normalized.normalized_title == "senior javascript typescript engineer"
    assert normalized.normalized_company_name == "acme robotics"
    assert normalized.description == "Build JavaScript and TypeScript services."
    assert normalized.location.city == "toronto"
    assert normalized.location.region == "on"
    assert normalized.location.country_code == "CA"
    assert normalized.official_url == "https://boards.greenhouse.io/acme/jobs/123"
    assert normalized.canonical_description_hash
    assert normalized.source.source_id == "acme-board"
    assert normalized.requisition_id == "REQ-123"
    assert record.model_dump(mode="python") == before


def test_normalizing_normalized_job_is_idempotent() -> None:
    normalized = JobNormalizer().normalize(_record(), _source(), fetched_at=WHEN)

    again = JobNormalizer().normalize(normalized, _source(), fetched_at=WHEN)

    assert again == normalized


def test_missing_optional_fields_remain_unknown_without_fabrication() -> None:
    normalized = normalize_job_record(
        _record(
            description="",
            location_raw=None,
            posted_at=None,
            source_updated_at=None,
            application_deadline=None,
            source_payload={},
        ),
        _source(),
        fetched_at=WHEN,
    )

    assert normalized.description == ""
    assert normalized.location.parseable is False
    assert normalized.posted_at is None
    assert normalized.requisition_id is None
    assert "missing_description" in normalized.completeness
