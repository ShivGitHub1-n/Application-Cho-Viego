from __future__ import annotations

from datetime import UTC, datetime

from resume_tailor.domain.job_discovery.evaluation import JobEvaluator
from resume_tailor.domain.job_discovery.models import (
    ConnectorType,
    FitGrade,
    JobSearchPreferences,
    ProfileCapabilityIndex,
    SourceJobRecord,
    SupportedJobSource,
    WorkArrangement,
)
from resume_tailor.domain.job_discovery.normalization import normalize_job_record
from resume_tailor.domain.models import RoleFamily

NOW = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)


def _job(description: str):
    source = SupportedJobSource(
        source_id="source",
        connector_type=ConnectorType.GREENHOUSE,
        company_name="Example",
        board_token="example",
        enabled=True,
        official_base_url="https://example.test",
    )
    return normalize_job_record(
        SourceJobRecord(
            external_job_id="job-1",
            title="Backend Engineer",
            company_name="Example",
            description=description,
            official_url="https://example.test/jobs/job-1",
            location_raw="Toronto, ON, Canada",
            work_arrangement=WorkArrangement.REMOTE,
            posted_at=NOW,
        ),
        source,
        fetched_at=NOW,
    )


def _preferences() -> JobSearchPreferences:
    return JobSearchPreferences(
        user_id="user",
        profile_id="profile",
        version=1,
        role_family_priority=[RoleFamily.SOFTWARE_DATA_ENGINEERING],
        target_titles=["Backend Engineer"],
        related_title_variants=[],
        technical_themes=["python"],
        career_interests=["robotics"],
        job_levels=[],
        locations=[],
        work_arrangement=WorkArrangement.UNKNOWN,
        preferred_companies=["Example"],
        created_at=NOW,
    )


def test_evaluation_keeps_fit_grade_and_provisional_independent() -> None:
    evaluation = JobEvaluator().evaluate(
        _job("Build Python services and review API changes.").model_copy(
            update={"verification_status": "verified_active", "verification_confidence": "high"}
        ),
        _preferences(),
        ProfileCapabilityIndex(terms={"python": []}),
        as_of=NOW,
    )

    assert evaluation.fit_grade in set(FitGrade)
    assert evaluation.provisional.is_provisional is False
    assert evaluation.evaluation_policy_version
    assert evaluation.diagnostics.total >= 0
