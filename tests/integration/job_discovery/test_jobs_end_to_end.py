from __future__ import annotations

from datetime import UTC, datetime

from resume_tailor.api.job_discovery import _feed_response
from resume_tailor.application.job_discovery.feed_services import FeedAssemblyService
from resume_tailor.application.job_discovery.handoff import PrepareTailoringHandoffService
from resume_tailor.application.job_discovery.retrieval import RetrievalService
from resume_tailor.application.job_discovery.saved import (
    CheckSavedJobAvailabilityService,
    SaveJobService,
)
from resume_tailor.domain.job_discovery.deduplication import deduplicate_jobs
from resume_tailor.domain.job_discovery.evaluation import (
    InternalDiagnostics,
    JobEvaluation,
    ProvisionalAssessment,
    RoleRelevanceAssessment,
)
from resume_tailor.domain.job_discovery.models import (
    ConnectorType,
    DiscoveredJob,
    DiscoveryRun,
    DiscoveryRunStatus,
    EligibilityAssessment,
    EligibilityStatus,
    FitGrade,
    JobLevel,
    JobSearchPreferences,
    NormalizedLocation,
    RecommendationVisibility,
    SavedJobAvailability,
    SourceJobRecord,
    SupportedJobSource,
    VerificationConfidence,
    VerificationResult,
    VerificationStatus,
    WorkArrangement,
    WorkArrangementPreferenceMode,
)
from resume_tailor.domain.job_discovery.normalization import normalize_job_record
from resume_tailor.domain.job_discovery.providers import (
    JobSourcePage,
    ProviderCapabilities,
)
from resume_tailor.domain.job_discovery.queries import FeedKind, TailoredJobQuery
from resume_tailor.domain.models import MasterProfile, RoleFamily
from resume_tailor.infrastructure.job_discovery_sqlite import (
    SQLiteAtomicJobDiscoveryPersistence,
    SQLiteJobRecommendationRepository,
    SQLiteSavedJobRepository,
)

NOW = datetime(2026, 7, 30, 12, tzinfo=UTC)


def _source(source_id: str = "source-a") -> SupportedJobSource:
    return SupportedJobSource(
        source_id=source_id,
        connector_type=ConnectorType.GREENHOUSE,
        company_name="Example Robotics",
        board_token=source_id,
        enabled=True,
        official_base_url="https://boards.greenhouse.io",
    )


def _record(
    external_id: str,
    *,
    source_id: str = "source-a",
    url_id: str | None = None,
    posted_at: datetime | None = NOW,
    description: str = "Build Python services and test reliable systems.",
) -> SourceJobRecord:
    url_suffix = url_id or external_id
    return SourceJobRecord(
        external_job_id=external_id,
        title="Software Engineer",
        company_name="Example Robotics",
        description=description,
        official_url=f"https://boards.greenhouse.io/{source_id}/jobs/{url_suffix}",
        location_raw="Toronto, ON, Canada",
        work_arrangement=WorkArrangement.REMOTE,
        posted_at=posted_at,
        source_payload={"requisition_id": f"REQ-{url_suffix}"},
    )


def _job(
    external_id: str,
    *,
    source_id: str = "source-a",
    url_id: str | None = None,
    posted_at: datetime | None = NOW,
    description: str = "Build Python services and test reliable systems.",
) -> DiscoveredJob:
    return normalize_job_record(
        _record(
            external_id,
            source_id=source_id,
            url_id=url_id,
            posted_at=posted_at,
            description=description,
        ),
        _source(source_id),
        fetched_at=NOW,
    )


def _evaluation(
    job: DiscoveredJob,
    grade: FitGrade,
    *,
    eligibility: EligibilityStatus = EligibilityStatus.ELIGIBLE,
    total: float = 50,
    provisional: bool = False,
) -> JobEvaluation:
    unresolved = (
        ["Work authorization is not stated."]
        if eligibility is EligibilityStatus.UNKNOWN
        else []
    )
    return JobEvaluation(
        job_id=job.id,
        eligibility=EligibilityAssessment(
            status=eligibility,
            verification_confidence=VerificationConfidence.HIGH,
            unresolved_facts=unresolved,
        ),
        role_relevance=RoleRelevanceAssessment(relevant=True),
        fit_grade=grade,
        diagnostics=InternalDiagnostics(total=total),
        provisional=ProvisionalAssessment(
            is_provisional=provisional,
            unresolved_facts=["Posting date is not stated."] if provisional else [],
        ),
    )


def _preferences() -> JobSearchPreferences:
    return JobSearchPreferences(
        user_id="local-user",
        profile_id="profile-1",
        version=1,
        role_family_priority=[RoleFamily.SOFTWARE_DATA_ENGINEERING],
        target_titles=["Software Engineer"],
        related_title_variants=[],
        technical_themes=["python"],
        career_interests=["software"],
        job_levels=[JobLevel.MID],
        locations=[NormalizedLocation(raw="Toronto", city="toronto", country_code="CA")],
        work_arrangement=WorkArrangement.REMOTE,
        work_arrangement_mode=WorkArrangementPreferenceMode.PREFERRED,
        preferred_companies=[],
        created_at=NOW,
        confirmed_at=NOW,
    )


def _run(run_id: str, feed_kind: FeedKind) -> DiscoveryRun:
    return DiscoveryRun(
        id=run_id,
        user_id="local-user",
        profile_id="profile-1",
        preference_version=1,
        status=DiscoveryRunStatus.COMPLETED_WITH_WARNINGS,
        started_at=NOW,
        completed_at=NOW,
        source_count=2,
        retrieved_count=3,
        record_count=3,
        warning_count=1,
        source_warnings=[f"{feed_kind.value} source warning"],
        source_outcomes=[{"source_id": "source-b", "status": "failed"}],
    )


def _recommendations(feed_kind: FeedKind) -> tuple[list[DiscoveredJob], list]:
    excellent = _job("excellent", posted_at=datetime(2026, 7, 25, tzinfo=UTC))
    unknown = _job("unknown", posted_at=datetime(2026, 7, 29, tzinfo=UTC))
    excluded = _job("excluded", posted_at=datetime(2026, 7, 30, tzinfo=UTC))
    assessed = [
        (
            unknown,
            _evaluation(
                unknown,
                FitGrade.GOOD,
                eligibility=EligibilityStatus.UNKNOWN,
                total=70,
                provisional=True,
            ),
        ),
        (
            excluded,
            _evaluation(
                excluded,
                FitGrade.DONT_MATCH,
                eligibility=EligibilityStatus.INELIGIBLE,
                total=100,
            ),
        ),
        (excellent, _evaluation(excellent, FitGrade.EXCELLENT, total=20)),
    ]
    result = FeedAssemblyService().build_recommendations(
        f"run-{feed_kind.value}",
        profile=MasterProfile.model_construct(id="profile-1", user_id="local-user", version=1),
        preferences=_preferences(),
        assessed=assessed,
        feed_kind=feed_kind,
        created_at=NOW,
    )
    return [excellent, unknown, excluded], result.recommendations


def test_offline_feeds_persist_separately_with_backend_order_and_visibility(tmp_path) -> None:
    tailored_jobs, tailored = _recommendations(FeedKind.TAILORED)
    explore_jobs, explore = _recommendations(FeedKind.EXPLORE)
    database = tmp_path / "jobs.sqlite3"
    persistence = SQLiteAtomicJobDiscoveryPersistence(database)
    persistence.persist_refresh(_run("run-tailored", FeedKind.TAILORED), tailored_jobs, tailored)
    persistence.persist_refresh(_run("run-explore", FeedKind.EXPLORE), explore_jobs, explore)

    repository = SQLiteJobRecommendationRepository(database)
    tailored_visible = repository.list_for_feed("local-user", FeedKind.TAILORED.value)
    explore_visible = repository.list_for_feed("local-user", FeedKind.EXPLORE.value)
    tailored_all = repository.list_for_feed(
        "local-user", FeedKind.TAILORED.value, include_excluded=True
    )

    assert [item.score.fit_grade for item in tailored_visible] == [
        FitGrade.EXCELLENT,
        FitGrade.GOOD,
    ]
    assert [item.score.fit_grade for item in explore_visible] == [
        FitGrade.GOOD,
        FitGrade.EXCELLENT,
    ]
    assert [item.feed_kind for item in tailored_visible] == [FeedKind.TAILORED] * 2
    assert len(tailored_all) == 3
    assert tailored_all[-1].visibility is RecommendationVisibility.EXCLUDED
    assert tailored_all[0].provisional is False
    assert tailored_all[1].eligibility.status is EligibilityStatus.UNKNOWN
    assert tailored_all[1].unresolved_facts == ["Work authorization is not stated."]


def test_offline_retrieval_keeps_surviving_source_and_dedup_provenance() -> None:
    good_source = _source("source-a")
    bad_source = _source("source-b")

    class Connector:
        def __init__(self, source: SupportedJobSource, failure: bool = False) -> None:
            self.source = source
            self.failure = failure
            self.queries: list[object] = []

        def capabilities(self, source: SupportedJobSource) -> ProviderCapabilities:
            return ProviderCapabilities(
                connector_type=source.connector_type,
                supports_title_or_keyword=False,
                supports_sector=False,
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
            self.queries.append(query)
            if self.failure:
                raise RuntimeError("offline source failure")
            return JobSourcePage(
                source=source,
                records=[_record("same", source_id=source.source_id, url_id="shared")],
            )

    good = Connector(good_source)
    bad = Connector(bad_source, failure=True)
    outcome = RetrievalService(
        sources=[bad_source, good_source],
        connectors={ConnectorType.GREENHOUSE: {"source-a": good, "source-b": bad}},
    ).retrieve(TailoredJobQuery(preferences=_preferences()), fetched_at=NOW)

    assert outcome.partial_success is True
    assert [item.record.external_job_id for item in outcome.records] == ["same"]
    assert outcome.records[0].provenance.source_id == "source-a"
    statuses = {item.source_id: item.status.value for item in outcome.source_outcomes}
    assert statuses == {"source-a": "success", "source-b": "failed"}

    first = _job("same", source_id="source-a", url_id="shared")
    second = _job("same", source_id="source-b", url_id="shared")
    deduplicated = deduplicate_jobs([first, second])
    assert len(deduplicated.jobs) == 1
    assert {item.source_id for item in deduplicated.jobs[0].source_provenance} == {
        "source-a",
        "source-b",
    }
    assert {item.id for item in deduplicated.groups[0].aliases} == {second.id}


def test_saved_snapshot_and_availability_refresh_change_only_status_metadata(tmp_path) -> None:
    job = _job("saved", description="Original immutable description.")
    class Jobs:
        def get(self, job_id: str) -> DiscoveredJob | None:
            return job if job_id == job.id else None

    database = tmp_path / "saved.sqlite3"
    saved_repository = SQLiteSavedJobRepository(database)
    save_service = SaveJobService(Jobs(), saved_repository)
    saved = save_service.save("local-user", job.id, saved_at=NOW)

    class Sources:
        def list_enabled(self) -> list[SupportedJobSource]:
            return [job.source]  # type: ignore[list-item]

    class Checker:
        def check(self, source: SupportedJobSource, external_job_id: str) -> VerificationResult:
            return VerificationResult(
                status=VerificationStatus.UNAVAILABLE,
                confidence=VerificationConfidence.HIGH,
                checked_at=NOW,
                message="posting removed",
            )

    checked = CheckSavedJobAvailabilityService(
        saved_repository,
        Sources(),
        {ConnectorType.GREENHOUSE: Checker()},
    ).check("local-user", saved.id, checked_at=NOW)

    assert checked.availability is SavedJobAvailability.UNAVAILABLE
    assert checked.posting_snapshot.description == "Original immutable description."
    assert checked.posting_snapshot.official_url == job.official_url
    assert checked.saved_at == NOW


def test_api_and_handoff_boundaries_preserve_feed_kind_and_prepare_only_inputs() -> None:
    _, tailored = _recommendations(FeedKind.TAILORED)
    _, explore = _recommendations(FeedKind.EXPLORE)
    tailored_response = _feed_response(
        feed_kind=FeedKind.TAILORED,
        run=None,
        recommendations=tailored,
    )
    explore_response = _feed_response(
        feed_kind=FeedKind.EXPLORE,
        run=None,
        recommendations=explore,
    )
    assert tailored_response.feed_kind is FeedKind.TAILORED
    assert explore_response.feed_kind is FeedKind.EXPLORE
    assert all(item.feed_kind is FeedKind.TAILORED for item in tailored_response.items)
    assert all(item.feed_kind is FeedKind.EXPLORE for item in explore_response.items)

    job = _job("handoff")

    class Jobs:
        def get(self, job_id: str) -> DiscoveredJob | None:
            return job if job_id == job.id else None

    class Saved:
        def get(self, user_id: str, saved_id: str):
            return None

    handoff = PrepareTailoringHandoffService(Jobs(), Saved()).from_discovered(
        job.id, profile_id="profile-1"
    )
    assert handoff.title == job.title
    assert handoff.description == job.description
    assert handoff.official_url == job.official_url
    assert not hasattr(handoff, "plan")
    assert not hasattr(handoff, "resume")
    assert not hasattr(handoff, "cover_letter")
