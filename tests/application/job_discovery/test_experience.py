from __future__ import annotations

from datetime import UTC, datetime

from resume_tailor.api.dependencies import JobDiscoveryServiceBundle
from resume_tailor.application.job_discovery.experience import JobsExperienceService
from resume_tailor.domain.job_discovery.models import (
    ConnectorType,
    DiscoveredJob,
    EligibilityAssessment,
    EligibilityStatus,
    FitGrade,
    JobRecommendation,
    JobScoreBreakdown,
    NormalizedLocation,
    RecommendationGroup,
    RecommendationVisibility,
    SupportedJobSource,
    VerificationConfidence,
    VerificationStatus,
    WorkArrangement,
)
from resume_tailor.domain.job_discovery.queries import FeedKind
from resume_tailor.domain.models import MasterProfile, RoleFamily

NOW = datetime(2026, 7, 28, 12, tzinfo=UTC)


def _profile(profile_id: str = "profile-1") -> MasterProfile:
    return MasterProfile(id=profile_id, user_id="local-user", display_name="Avery Engineer")


def _job(job_id: str) -> DiscoveredJob:
    source = SupportedJobSource(
        source_id="source-1",
        connector_type=ConnectorType.GREENHOUSE,
        company_name="Example Robotics",
        board_token="example",
        enabled=True,
        official_base_url="https://example.com/careers",
    )
    return DiscoveredJob(
        id=job_id,
        source=source,
        external_job_id=job_id,
        title=f"Role {job_id}",
        company_name="Example Robotics",
        description="Exact normalized posting description.",
        official_url=f"https://example.com/jobs/{job_id}",
        location=NormalizedLocation(
            city="Toronto", country_code="CA", raw="Toronto, CA", parseable=True
        ),
        work_arrangement=WorkArrangement.HYBRID,
        role_family=RoleFamily.EMBEDDED_FIRMWARE,
        posted_at=NOW,
        verification_status=VerificationStatus.VERIFIED_ACTIVE,
        verification_confidence=VerificationConfidence.HIGH,
        fetched_at=NOW,
    )


def _recommendation(
    job_id: str, grade: FitGrade, eligibility: EligibilityStatus
) -> JobRecommendation:
    return JobRecommendation(
        id=f"rec-{job_id}",
        run_id="run-1",
        user_id="local-user",
        profile_id="profile-1",
        profile_version=1,
        preference_version=1,
        job_id=job_id,
        group=RecommendationGroup.PRIMARY,
        primary_role_family=RoleFamily.EMBEDDED_FIRMWARE,
        eligibility=EligibilityAssessment(
            status=eligibility,
            verification_confidence=VerificationConfidence.HIGH,
            unresolved_facts=["Work authorization is not stated."]
            if eligibility is EligibilityStatus.UNKNOWN
            else [],
        ),
        score=JobScoreBreakdown(
            demonstrated_technical_evidence=0.1,
            required_coverage=0.2,
            role_alignment=0.3,
            level_alignment=0.1,
            education_coursework=0.1,
            preferred_skill_alignment=0.1,
            recency_completeness=0.1,
            total=0.99,
            label=__import__(
                "resume_tailor.domain.job_discovery.models", fromlist=["MatchLabel"]
            ).MatchLabel.GOOD,
            provisional=True,
            fit_grade=grade,
        ),
        reasons=["Exact supporting evidence from the evaluated posting and profile."],
        gaps=["Material gap from the evaluated posting."],
        rank=1,
        created_at=NOW,
        feed_kind=FeedKind.TAILORED,
        visibility=RecommendationVisibility.VISIBLE,
        unresolved_facts=["Work authorization is not stated."]
        if eligibility is EligibilityStatus.UNKNOWN
        else [],
        provisional=True,
    )


class Profiles:
    def list_all(self) -> list[MasterProfile]:
        return [_profile()]


class Jobs:
    def __init__(self, jobs: list[DiscoveredJob]) -> None:
        self.jobs = {job.id: job for job in jobs}

    def get(self, job_id: str) -> DiscoveredJob | None:
        return self.jobs.get(job_id)


class FeedQueries:
    def __init__(self, recommendations: list[JobRecommendation]) -> None:
        self.recommendations = recommendations

    def get(
        self,
        user_id: str,
        feed_kind: FeedKind,
        *,
        profile_id: str | None = None,
        excluded_only: bool = False,
    ):
        self.profile_id = profile_id
        items = [item for item in self.recommendations if item.feed_kind is feed_kind]
        if excluded_only:
            items = [item for item in items if item.visibility is RecommendationVisibility.EXCLUDED]
        else:
            items = [item for item in items if item.visibility is RecommendationVisibility.VISIBLE]
        return type(
            "Feed", (), {"feed_kind": feed_kind, "items": items, "excluded_count": 1, "run": None}
        )()


class CurrentPreferences:
    def get(self, user_id: str, profile_id: str):
        raise ValueError("not configured")


class FakeHandoff:
    def from_discovered(self, job_id: str, *, profile_id: str):
        return (job_id, profile_id)


def _service(recommendations: list[JobRecommendation]) -> JobsExperienceService:
    services = JobDiscoveryServiceBundle(
        suggest_preferences=object(),
        refresh=object(),
        current_preferences=CurrentPreferences(),
        feed_queries=FeedQueries(recommendations),
    )
    return JobsExperienceService(
        profiles=Profiles(),
        services=services,
        jobs=Jobs([_job(item.job_id) for item in recommendations]),
        handoff=FakeHandoff(),
        now=lambda: NOW,
    )


def test_feed_view_preserves_backend_order_and_hides_numeric_score() -> None:
    recommendations = [
        _recommendation("job-2", FitGrade.GOOD, EligibilityStatus.UNKNOWN),
        _recommendation("job-1", FitGrade.EXCELLENT, EligibilityStatus.ELIGIBLE),
    ]
    result = _service(recommendations).load_feed("profile-1", FeedKind.TAILORED)

    assert [item.job_id for item in result.visible] == ["job-2", "job-1"]
    assert result.visible[0].grade is FitGrade.GOOD
    assert result.visible[0].eligibility is EligibilityStatus.UNKNOWN
    assert result.visible[0].provisional is True
    assert result.visible[0].supporting_evidence == [
        "Exact supporting evidence from the evaluated posting and profile."
    ]
    assert not hasattr(result.visible[0], "score")


def test_detail_preserves_exact_reasons_gaps_and_unresolved_facts() -> None:
    recommendation = _recommendation("job-1", FitGrade.WEAK, EligibilityStatus.UNKNOWN)

    detail = _service([recommendation]).get_job_detail("profile-1", FeedKind.TAILORED, "job-1")

    assert detail is not None
    assert detail.reasons == recommendation.reasons
    assert detail.gaps == recommendation.gaps
    assert detail.unresolved_facts == recommendation.unresolved_facts


def test_excluded_results_are_loaded_separately() -> None:
    excluded = _recommendation(
        "job-x", FitGrade.DONT_MATCH, EligibilityStatus.INELIGIBLE
    ).model_copy(update={"visibility": RecommendationVisibility.EXCLUDED})

    feed = _service([excluded]).load_feed("profile-1", FeedKind.TAILORED)
    expanded = _service([excluded]).load_excluded("profile-1", FeedKind.TAILORED)

    assert feed.visible == []
    assert feed.excluded_count == 1
    assert [item.job_id for item in expanded] == ["job-x"]


def test_feed_query_is_scoped_to_selected_profile() -> None:
    recommendations = [_recommendation("job-1", FitGrade.GOOD, EligibilityStatus.ELIGIBLE)]
    service = _service(recommendations)

    service.load_feed("profile-1", FeedKind.TAILORED)

    assert service._services.feed_queries.profile_id == "profile-1"
