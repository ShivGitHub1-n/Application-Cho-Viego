from __future__ import annotations

import json
from datetime import UTC, datetime

from resume_tailor.application.job_discovery.retrieval import RetrievalService
from resume_tailor.domain.job_discovery.deduplication import deduplicate_jobs
from resume_tailor.domain.job_discovery.evaluation import (
    InternalDiagnostics,
    JobEvaluation,
    ProvisionalAssessment,
    RoleRelevanceAssessment,
)
from resume_tailor.domain.job_discovery.feeds import rank_feed_candidates
from resume_tailor.domain.job_discovery.models import (
    ConnectorType,
    EligibilityAssessment,
    EligibilityStatus,
    FitGrade,
    SourceJobRecord,
    SupportedJobSource,
    VerificationConfidence,
    WorkArrangement,
)
from resume_tailor.domain.job_discovery.normalization import normalize_job_record
from resume_tailor.domain.job_discovery.providers import JobSourcePage, ProviderCapabilities
from resume_tailor.domain.job_discovery.queries import ExploreJobQuery, FeedKind
from resume_tailor.domain.job_discovery.requirements import RequirementExtractor
from resume_tailor.domain.job_discovery.source_lifecycle import (
    SourceLifecycleOutcome,
    SourceRuntimeState,
    fingerprint_content,
)

NOW = datetime(2026, 7, 30, 12, tzinfo=UTC)


def _source(source_id: str) -> SupportedJobSource:
    return SupportedJobSource(
        source_id=source_id,
        connector_type=ConnectorType.GREENHOUSE,
        company_name="Example Robotics",
        board_token=source_id,
        enabled=True,
        official_base_url="https://boards.greenhouse.io",
    )


def _job(source_id: str, external_id: str, *, posted_at: datetime | None = NOW):
    return normalize_job_record(
        SourceJobRecord(
            external_job_id=external_id,
            title="Software Engineer",
            company_name="Example Robotics",
            description="Build Python services and test reliable systems.",
            official_url=f"https://boards.greenhouse.io/{source_id}/jobs/{external_id}",
            location_raw="Toronto, ON, Canada",
            work_arrangement=WorkArrangement.REMOTE,
            posted_at=posted_at,
            source_payload={"requisition_id": f"REQ-{external_id}"},
        ),
        _source(source_id),
        fetched_at=NOW,
    )


def _evaluation(job, grade: FitGrade = FitGrade.GOOD) -> JobEvaluation:
    return JobEvaluation(
        job_id=job.id,
        eligibility=EligibilityAssessment(
            status=EligibilityStatus.ELIGIBLE,
            verification_confidence=VerificationConfidence.HIGH,
        ),
        role_relevance=RoleRelevanceAssessment(relevant=True),
        fit_grade=grade,
        diagnostics=InternalDiagnostics(total=50),
        provisional=ProvisionalAssessment(),
    )


def test_provider_source_page_and_posting_order_is_canonical() -> None:
    sources = [_source("source-b"), _source("source-a")]

    class Connector:
        def capabilities(self, source: SupportedJobSource) -> ProviderCapabilities:
            return ProviderCapabilities(
                connector_type=source.connector_type,
                supports_title_or_keyword=False,
                supports_sector=True,
                supports_location=False,
                supports_work_arrangement=False,
                supports_level=False,
                supports_employment_type=False,
                supports_posting_date_boundary=False,
                supports_pagination=True,
                supports_page_size=True,
                supports_availability_checks=True,
            )

        def fetch_page(self, source, query, cursor, *, fetched_at):
            return JobSourcePage(
                source=source,
                records=[
                    SourceJobRecord(
                        external_job_id="2",
                        title="Software Engineer",
                        company_name="Example Robotics",
                        description="Build systems.",
                        official_url=f"https://boards.greenhouse.io/{source.source_id}/jobs/2",
                    ),
                    SourceJobRecord(
                        external_job_id="1",
                        title="Software Engineer",
                        company_name="Example Robotics",
                        description="Build systems.",
                        official_url=f"https://boards.greenhouse.io/{source.source_id}/jobs/1",
                    ),
                ],
            )

    outcome = RetrievalService(
        sources=sources,
        connectors={ConnectorType.GREENHOUSE: Connector()},
    ).retrieve(
        ExploreJobQuery(sectors=["Software Engineering"]),
        fetched_at=NOW,
    )

    assert [(item.source_id, item.status.value) for item in outcome.source_outcomes] == [
        ("source-a", "success"),
        ("source-b", "success"),
    ]
    assert [
        (item.source.source_id, item.record.external_job_id)
        for item in outcome.records
    ] == [("source-a", "1"), ("source-a", "2"), ("source-b", "1"), ("source-b", "2")]


def test_alias_and_canonical_serialization_is_input_order_independent() -> None:
    first = _job("source-a", "a", posted_at=NOW).model_copy(
        update={"requisition_id": "REQ-SHARED"}
    )
    second = _job("source-b", "b", posted_at=NOW).model_copy(
        update={"requisition_id": "REQ-SHARED"}
    )
    forward = deduplicate_jobs([first, second])
    reverse = deduplicate_jobs([second, first])

    assert forward == reverse
    assert json.dumps(forward.model_dump(mode="json"), sort_keys=True) == json.dumps(
        reverse.model_dump(mode="json"), sort_keys=True
    )
    assert [item.source_id for item in forward.jobs[0].source_provenance] == [
        "source-a",
        "source-b",
    ]


def test_requirement_evidence_and_preference_order_have_stable_serialized_output() -> None:
    extractor = RequirementExtractor()
    first = extractor.extract(
        "Software Engineer",
        "Required experience with Python and Docker. Preferred knowledge of SQL.",
        "Toronto",
        WorkArrangement.REMOTE,
    )
    second = extractor.extract(
        "Software Engineer",
        "Required experience with Python and Docker. Preferred knowledge of SQL.",
        "Toronto",
        WorkArrangement.REMOTE,
    )
    assert first == second
    assert [item.term for item in first.requirements] == sorted(
        [item.term for item in first.requirements],
        key=lambda term: next(
            item.source_start for item in first.requirements if item.term == term
        ),
    )

    content_a = {"provider": ["greenhouse", "lever"], "requirements": ["python", "sql"]}
    content_b = {"requirements": ["python", "sql"], "provider": ["greenhouse", "lever"]}
    assert fingerprint_content(content_a) == fingerprint_content(content_b)
    runtime = SourceRuntimeState(source_id="source-a")
    assert runtime.completed(
        at=NOW,
        outcome=SourceLifecycleOutcome.SUCCESS,
        diagnostic_codes=["z", "a"],
    ).diagnostic_codes == [
        "a",
        "z",
    ]


def test_equal_rank_ties_use_stable_ids_for_tailored_and_explore() -> None:
    jobs = [_job("source-a", "b"), _job("source-a", "a")]
    candidates = [(job, _evaluation(job)) for job in jobs]
    expected = [job.id for job in sorted(jobs, key=lambda job: job.id)]

    tailored = rank_feed_candidates(candidates, feed_kind=FeedKind.TAILORED)
    explore = rank_feed_candidates(candidates, feed_kind=FeedKind.EXPLORE)

    assert [item.job.id for item in tailored.items] == expected
    assert [item.job.id for item in explore.items] == expected
