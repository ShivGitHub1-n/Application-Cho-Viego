from __future__ import annotations

from datetime import UTC, datetime

from resume_tailor.application.job_discovery.feed_services import FeedAssemblyService
from resume_tailor.domain.job_discovery.evaluation import (
    InternalDiagnostics,
    JobEvaluation,
    ProvisionalAssessment,
    RoleRelevanceAssessment,
)
from resume_tailor.domain.job_discovery.grading import FitGrade
from resume_tailor.domain.job_discovery.models import (
    ConnectorType,
    EligibilityAssessment,
    EligibilityStatus,
    JobSearchPreferences,
    RecommendationVisibility,
    SourceJobRecord,
    SupportedJobSource,
    VerificationConfidence,
    WorkArrangement,
    WorkArrangementPreferenceMode,
)
from resume_tailor.domain.job_discovery.normalization import normalize_job_record
from resume_tailor.domain.job_discovery.queries import FeedKind
from resume_tailor.domain.models import MasterProfile

WHEN = datetime(2026, 7, 24, 12, tzinfo=UTC)


def _job(external_id: str):
    source = SupportedJobSource(
        source_id="source",
        connector_type=ConnectorType.GREENHOUSE,
        company_name="Acme",
        board_token="acme",
        enabled=True,
        official_base_url="https://boards.greenhouse.io",
    )
    return normalize_job_record(
        SourceJobRecord(
            external_job_id=external_id,
            title="Engineer",
            company_name="Acme",
            description="Build systems.",
            official_url=f"https://boards.greenhouse.io/acme/jobs/{external_id}",
            work_arrangement=WorkArrangement.REMOTE,
        ),
        source,
        fetched_at=WHEN,
    )


def _preferences() -> JobSearchPreferences:
    return JobSearchPreferences(
        user_id="user-1",
        profile_id="profile-1",
        version=1,
        role_family_priority=[],
        target_titles=["Engineer"],
        related_title_variants=[],
        technical_themes=[],
        career_interests=[],
        job_levels=[],
        locations=[],
        work_arrangement=WorkArrangement.UNKNOWN,
        work_arrangement_mode=WorkArrangementPreferenceMode.PREFERRED,
        preferred_companies=[],
        created_at=WHEN,
    )


def _evaluation(job, grade: FitGrade, total: float) -> JobEvaluation:
    status = (
        EligibilityStatus.INELIGIBLE
        if grade is FitGrade.DONT_MATCH
        else EligibilityStatus.ELIGIBLE
    )
    return JobEvaluation(
        job_id=job.id,
        eligibility=EligibilityAssessment(
            status=status,
            verification_confidence=VerificationConfidence.HIGH,
        ),
        role_relevance=RoleRelevanceAssessment(relevant=True),
        fit_grade=grade,
        diagnostics=InternalDiagnostics(total=total),
        provisional=ProvisionalAssessment(is_provisional=True, unresolved_facts=["date"]),
        evaluation_policy_version="jobs-fit-v2.1-calibrated",
    )


def test_feed_assembly_persists_every_evaluation_with_visibility_and_feed_kind() -> None:
    candidates = [
        (_job("excellent"), _evaluation(_job("excellent"), FitGrade.EXCELLENT, 90)),
        (_job("good"), _evaluation(_job("good"), FitGrade.GOOD, 70)),
        (_job("weak"), _evaluation(_job("weak"), FitGrade.WEAK, 40)),
        (_job("excluded"), _evaluation(_job("excluded"), FitGrade.DONT_MATCH, 0)),
    ]

    result = FeedAssemblyService().build_recommendations(
        "run-1",
        profile=MasterProfile.model_construct(id="profile-1", user_id="user-1", version=1),
        preferences=_preferences(),
        assessed=candidates,
        feed_kind=FeedKind.EXPLORE,
        created_at=WHEN,
    )

    assert len(result.recommendations) == 4
    assert result.excluded_count == 0
    assert all(item.feed_kind is FeedKind.EXPLORE for item in result.recommendations)
    assert [item.visibility for item in result.recommendations].count(
        RecommendationVisibility.EXCLUDED
    ) == 0
    assert all(
        item.visibility is RecommendationVisibility.VISIBLE
        for item in result.recommendations
    )
    assert result.recommendations[0].score.fit_grade is FitGrade.EXCELLENT
    assert result.recommendations[0].provisional is True

