from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from resume_tailor.domain.job_discovery.deduplication import (
    JobDeduplicator,
    deduplicate_jobs,
)
from resume_tailor.domain.job_discovery.models import (
    ConnectorType,
    SourceJobRecord,
    SupportedJobSource,
    WorkArrangement,
)
from resume_tailor.domain.job_discovery.normalization import normalize_job_record

WHEN = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


def _source(source_id: str = "acme-board") -> SupportedJobSource:
    return SupportedJobSource(
        source_id=source_id,
        connector_type=ConnectorType.GREENHOUSE,
        company_name="Acme Robotics",
        board_token="acme",
        enabled=True,
        official_base_url="https://boards.greenhouse.io",
    )


def _job(
    *,
    external_job_id: str,
    title: str = "Software Engineer",
    url: str = "https://boards.greenhouse.io/acme/jobs/1",
    location: str | None = "Toronto, ON, Canada",
    description: str = "Build Python services.",
    requisition_id: str = "REQ-1",
    source_id: str = "acme-board",
):
    record = SourceJobRecord(
        external_job_id=external_job_id,
        title=title,
        company_name="Acme Robotics",
        description=description,
        official_url=url,
        location_raw=location,
        work_arrangement=WorkArrangement.UNKNOWN,
        posted_at=datetime(2026, 7, 1, tzinfo=UTC),
        source_updated_at=None,
        application_deadline=None,
        source_payload={"requisition_id": requisition_id},
    )
    return normalize_job_record(record, _source(source_id), fetched_at=WHEN)


def test_duplicate_grouping_uses_conservative_layered_identity() -> None:
    same_external_id = _job(external_job_id="1", url="https://example.test/first")
    same_url = _job(
        external_job_id="1",
        url="https://boards.greenhouse.io/acme/jobs/1",
        requisition_id="REQ-1",
    )
    same_fallback = _job(
        external_job_id="3",
        url="https://example.test/third",
        requisition_id="REQ-1",
    )
    distinct_location = _job(
        external_job_id="4",
        url="https://example.test/fourth",
        location="Austin, TX, United States",
        requisition_id="REQ-4",
    )

    result = JobDeduplicator().resolve(
        [same_fallback, distinct_location, same_external_id, same_url]
    )

    assert len(result.jobs) == 2
    assert result.duplicate_count == 2
    assert len(result.groups) == 2
    assert {alias.external_job_id for alias in result.groups[0].aliases} | {
        alias.external_job_id for alias in result.groups[1].aliases
    } == {"1", "3"}
    assert {job.location.city for job in result.jobs} == {"toronto", "austin"}


def test_canonical_selection_and_output_are_input_order_independent() -> None:
    sparse = _job(external_job_id="1", description="", requisition_id="REQ-1")
    complete = _job(
        external_job_id="2",
        description="Build Python services with Docker.",
        requisition_id="REQ-1",
    )

    first = deduplicate_jobs([sparse, complete])
    second = deduplicate_jobs([complete, sparse])

    assert first == second
    assert first.jobs[0].external_job_id == "2"
    assert {alias.external_job_id for alias in first.groups[0].aliases} == {"1"}


def test_alias_merge_refreshes_derived_fields() -> None:
    canonical_candidate = _job(
        external_job_id="9",
        location=None,
        description="Build Python services.",
        requisition_id="REQ-9",
        url="https://example.test/nine-a",
    )
    alias = _job(
        external_job_id="9",
        location="Toronto, ON, Canada",
        description="",
        requisition_id="REQ-9",
        url="https://example.test/nine-b",
    )

    result = deduplicate_jobs([canonical_candidate, alias])

    merged = result.jobs[0]
    assert merged.location.parseable is True
    assert "missing_or_unparseable_location" not in merged.completeness
    expected_hash = hashlib.sha256(b"build python services").hexdigest()
    assert merged.canonical_description_hash == expected_hash


def test_same_external_id_with_conflicting_location_or_description_stays_distinct() -> None:
    first = _job(
        external_job_id="10",
        location="Toronto, ON, Canada",
        description="Build Python services.",
        requisition_id="REQ-10",
        url="https://example.test/ten-a",
    )
    second = _job(
        external_job_id="10",
        location="Austin, TX, United States",
        description="Research computer vision models.",
        requisition_id="REQ-10",
        url="https://example.test/ten-b",
    )

    result = deduplicate_jobs([first, second])

    assert len(result.jobs) == 2


def test_similar_titles_with_different_requisitions_or_descriptions_stay_distinct() -> None:
    first = _job(external_job_id="1", requisition_id="REQ-1", description="Build Python APIs.")
    second = _job(
        external_job_id="2",
        requisition_id="REQ-2",
        description="Research computer vision models.",
        url="https://example.test/second",
    )

    result = deduplicate_jobs([first, second])

    assert len(result.jobs) == 2
    assert result.duplicate_count == 0

    same_description_first = _job(
        external_job_id="5",
        requisition_id="REQ-5",
        description="Build Python APIs.",
        url="https://example.test/fifth",
    )
    same_description_second = _job(
        external_job_id="6",
        requisition_id="REQ-6",
        description="Build Python APIs.",
        url="https://example.test/sixth",
    )

    distinct_requisitions = deduplicate_jobs(
        [same_description_first, same_description_second]
    )

    assert len(distinct_requisitions.jobs) == 2

    same_url_distinct_requisitions = deduplicate_jobs(
        [
            _job(
                external_job_id="7",
                requisition_id="REQ-7",
                url="https://example.test/shared",
            ),
            _job(
                external_job_id="8",
                requisition_id="REQ-8",
                url="https://example.test/shared",
            ),
        ]
    )

    assert len(same_url_distinct_requisitions.jobs) == 2
