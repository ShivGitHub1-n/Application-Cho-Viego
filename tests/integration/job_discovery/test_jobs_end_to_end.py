from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from inspect import signature

from fastapi.testclient import TestClient

from resume_tailor.api.dependencies import JobDiscoveryServiceBundle, get_job_discovery_services
from resume_tailor.api.main import app
from resume_tailor.application.job_discovery.experience import JobsExperienceService
from resume_tailor.application.job_discovery.feed_services import FeedAssemblyService
from resume_tailor.application.job_discovery.handoff import PrepareTailoringHandoffService
from resume_tailor.application.job_discovery.queries import (
    GetCurrentJobSearchPreferencesService,
    GetDiscoveryRunService,
    GetJobFeedService,
)
from resume_tailor.application.job_discovery.refresh import RefreshJobDiscoveryService
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
    SQLiteDiscoveredJobRepository,
    SQLiteDiscoveryRunRepository,
    SQLiteJobRecommendationRepository,
    SQLiteSavedJobRepository,
    SQLiteSourceIdentityAliasRepository,
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
    location_raw: str | None = "Toronto, ON, Canada",
    company: str = "Example Robotics",
    description: str = "Build Python services and test reliable systems.",
    requisition_id: str | None = None,
) -> SourceJobRecord:
    url_suffix = url_id or external_id
    return SourceJobRecord(
        external_job_id=external_id,
        title="Software Engineer",
        company_name=company,
        description=description,
        official_url=f"https://boards.greenhouse.io/{source_id}/jobs/{url_suffix}",
        location_raw=location_raw,
        work_arrangement=WorkArrangement.REMOTE,
        posted_at=posted_at,
        source_payload={"requisition_id": requisition_id or f"REQ-{url_suffix}"},
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


def _preferences(*, excluded_companies: list[str] | None = None) -> JobSearchPreferences:
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
        excluded_companies=excluded_companies or [],
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


class _ComposedProfileRepository:
    def __init__(self, profile: MasterProfile) -> None:
        self.profile = profile

    def get(self, profile_id: str) -> MasterProfile | None:
        return self.profile if profile_id == self.profile.id else None

    def list_all(self) -> list[MasterProfile]:
        return [self.profile]


class _ComposedPreferencesRepository:
    def __init__(self, preferences: JobSearchPreferences) -> None:
        self.preferences = preferences

    def get_current(self, user_id: str, profile_id: str) -> JobSearchPreferences | None:
        if (user_id, profile_id) != (self.preferences.user_id, self.preferences.profile_id):
            return None
        return self.preferences

    def get(self, user_id: str, profile_id: str) -> JobSearchPreferences:
        preferences = self.get_current(user_id, profile_id)
        if preferences is None:
            raise LookupError("preferences were not found")
        return preferences


class _ComposedSourceRepository:
    def __init__(self, sources: list[SupportedJobSource]) -> None:
        self.sources = sources

    def list_enabled(self) -> list[SupportedJobSource]:
        return list(self.sources)


class _ComposedConnector:
    def __init__(self, records: list[SourceJobRecord], *, failure: bool = False) -> None:
        self.records = records
        self.failure = failure

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
        if self.failure:
            raise RuntimeError("offline source failure")
        return JobSourcePage(source=source, records=list(self.records))


def _composed_system(tmp_path):
    profile = MasterProfile(
        id="profile-1",
        user_id="local-user",
        version=1,
        display_name="Candidate",
        experiences=[
            {
                "id": "entry-1",
                "title": "Software Engineer",
                "kind": "experience",
                "technologies": ["Python"],
            }
        ],
        evidence=[
            {
                "id": "evidence-1",
                "entity_id": "entry-1",
                "source_text": "Built Python software systems.",
                "technologies": ["Python"],
            }
        ],
    )
    preferences = _preferences(excluded_companies=["Excluded Corp"])
    sources = [_source("source-a"), _source("source-b"), _source("source-failed")]
    source_records = {
        "source-a": [
            _record(
                "eligible",
                source_id="source-a",
                description="Required Python. Build eligible systems.",
            ),
            _record(
                "unknown",
                source_id="source-a",
                location_raw=None,
                posted_at=None,
                description="Required Python. Build unknown systems.",
            ),
            _record(
                "excluded",
                source_id="source-a",
                company="Excluded Corp",
                description="Required Python. Build excluded systems.",
            ),
            _record(
                "dont-match",
                source_id="source-a",
                description="Required CUDA and JAX. Build unrelated systems.",
            ),
            _record(
                "duplicate-a",
                source_id="source-a",
                url_id="shared",
                description="Required Python. Build shared systems.",
                requisition_id="REQ-SHARED",
            ),
        ],
        "source-b": [
            _record(
                "duplicate-b",
                source_id="source-b",
                url_id="shared",
                description="Required Python. Build shared systems.",
                requisition_id="REQ-SHARED",
            )
        ],
    }
    database = tmp_path / "composed-jobs.sqlite3"
    profiles = _ComposedProfileRepository(profile)
    preferences_repository = _ComposedPreferencesRepository(preferences)
    source_repository = _ComposedSourceRepository(sources)
    jobs = SQLiteDiscoveredJobRepository(database)
    recommendations = SQLiteJobRecommendationRepository(database)
    runs = SQLiteDiscoveryRunRepository(database)
    aliases = SQLiteSourceIdentityAliasRepository(database)
    connectors = {
        ConnectorType.GREENHOUSE: {
            "source-a": _ComposedConnector(source_records["source-a"]),
            "source-b": _ComposedConnector(source_records["source-b"]),
            "source-failed": _ComposedConnector([], failure=True),
        }
    }
    refresh = RefreshJobDiscoveryService(
        profiles=profiles,
        preferences=preferences_repository,
        sources=source_repository,
        connectors=connectors,
        discovered_jobs=jobs,
        recommendations=recommendations,
        runs=runs,
        atomic_persistence=SQLiteAtomicJobDiscoveryPersistence(database),
        aliases=aliases,
    )
    feed_queries = GetJobFeedService(recommendations, runs)
    handoff = PrepareTailoringHandoffService(jobs, SQLiteSavedJobRepository(database))
    return (
        database,
        profile,
        preferences,
        profiles,
        jobs,
        recommendations,
        runs,
        aliases,
        refresh,
        feed_queries,
        handoff,
    )


def test_composed_refresh_api_presentation_and_handoff_are_offline_and_idempotent(tmp_path) -> None:
    (
        database,
        profile,
        preferences,
        profiles,
        jobs,
        recommendations,
        runs,
        aliases,
        refresh,
        feed_queries,
        handoff,
    ) = _composed_system(tmp_path)

    first_run = refresh.refresh(
        "local-user", profile.id, preferences, started_at=NOW
    )

    def behavioral_feed(feed_kind: FeedKind) -> dict[str, object]:
        visible = feed_queries.get("local-user", feed_kind, profile_id=profile.id)
        excluded = feed_queries.get(
            "local-user", feed_kind, profile_id=profile.id, excluded_only=True
        )
        recommendations = [*visible.items, *excluded.items]
        job_payloads = sorted(
            [jobs.get(item.job_id).model_dump(mode="json") for item in recommendations],
            key=lambda item: str(item["id"]),
        )
        alias_payloads = sorted(
            [
                alias.model_dump(mode="json")
                for source_id in ("source-a", "source-b", "source-failed")
                for alias in aliases.list_for_source(source_id)
            ],
            key=lambda item: (str(item["source_id"]), str(item["identity_value"])),
        )
        return {
            "visible": [item.model_dump(mode="json") for item in visible.items],
            "excluded": [item.model_dump(mode="json") for item in excluded.items],
            "excluded_count": visible.excluded_count,
            "jobs": job_payloads,
            "aliases": alias_payloads,
        }

    first_feed = feed_queries.get("local-user", FeedKind.TAILORED, profile_id=profile.id)
    first_tailored_behavior = behavioral_feed(FeedKind.TAILORED)
    with sqlite3.connect(database) as connection:
        first_recommendation_count = connection.execute(
            "SELECT COUNT(*) FROM job_recommendations WHERE run_id = ?",
            (first_run.id,),
        ).fetchone()[0]
        first_discovered_count = connection.execute(
            "SELECT COUNT(*) FROM discovered_jobs"
        ).fetchone()[0]

    second_run = refresh.refresh(
        "local-user", profile.id, preferences, started_at=NOW
    )
    second_tailored_behavior = behavioral_feed(FeedKind.TAILORED)
    explore_run = refresh.refresh_explore(
        "local-user",
        sectors=["Software Engineering"],
        profile_id=profile.id,
        started_at=NOW,
    )
    explore_feed = feed_queries.get("local-user", FeedKind.EXPLORE, profile_id=profile.id)
    first_explore_behavior = behavioral_feed(FeedKind.EXPLORE)
    repeated_explore_run = refresh.refresh_explore(
        "local-user",
        sectors=["Software Engineering"],
        profile_id=profile.id,
        started_at=NOW,
    )
    repeated_explore_feed = feed_queries.get(
        "local-user", FeedKind.EXPLORE, profile_id=profile.id
    )
    second_explore_behavior = behavioral_feed(FeedKind.EXPLORE)

    assert first_run.id == second_run.id
    assert first_run.model_dump(mode="json") == second_run.model_dump(mode="json")
    assert first_tailored_behavior == second_tailored_behavior
    assert first_explore_behavior == second_explore_behavior
    assert explore_run.id == repeated_explore_run.id
    assert explore_run.model_dump(mode="json") == repeated_explore_run.model_dump(mode="json")
    assert first_run.duplicate_count == 1
    assert second_run.duplicate_count == 1
    assert first_run.failed_sources == ["source-failed"]
    assert second_run.failed_sources == first_run.failed_sources
    assert first_run.status is DiscoveryRunStatus.COMPLETED_WITH_WARNINGS
    assert second_run.status is first_run.status
    assert explore_run.status is DiscoveryRunStatus.COMPLETED_WITH_WARNINGS
    assert repeated_explore_run.status is explore_run.status
    assert first_feed.feed_kind is FeedKind.TAILORED
    assert explore_feed.feed_kind is FeedKind.EXPLORE
    assert repeated_explore_feed.feed_kind is FeedKind.EXPLORE
    assert first_feed.excluded_count >= 1
    assert all(item.visibility is RecommendationVisibility.VISIBLE for item in first_feed.items)
    assert all(item.visibility is RecommendationVisibility.VISIBLE for item in explore_feed.items)
    assert any(item.eligibility.status is EligibilityStatus.UNKNOWN for item in first_feed.items)
    assert len(aliases.list_for_source("source-a")) >= 1
    shared_job = jobs.get(_job("duplicate-a", source_id="source-a", url_id="shared").id)
    assert shared_job is not None
    assert {item.source_id for item in shared_job.source_provenance} == {
        "source-a",
        "source-b",
    }

    with sqlite3.connect(database) as connection:
        second_recommendation_count = connection.execute(
            "SELECT COUNT(*) FROM job_recommendations WHERE run_id = ?",
            (first_run.id,),
        ).fetchone()[0]
        second_discovered_count = connection.execute(
            "SELECT COUNT(*) FROM discovered_jobs"
        ).fetchone()[0]
    assert first_recommendation_count == second_recommendation_count
    assert first_discovered_count == second_discovered_count
    assert second_recommendation_count == len(second_run.source_outcomes) + 2
    assert second_discovered_count == 5
    assert len(second_tailored_behavior["visible"]) == len(
        {item["id"] for item in second_tailored_behavior["visible"]}
    )

    saved_repository = SQLiteSavedJobRepository(database)
    saved = SaveJobService(jobs, saved_repository).save(
        "local-user", first_feed.items[0].job_id, saved_at=NOW
    )
    snapshot_before = saved_repository.get("local-user", saved.id)
    refresh.refresh("local-user", profile.id, preferences, started_at=NOW)
    snapshot_after = saved_repository.get("local-user", saved.id)
    assert snapshot_before is not None
    assert snapshot_after is not None
    assert snapshot_after.posting_snapshot == snapshot_before.posting_snapshot
    assert (
        snapshot_after.posting_snapshot.official_url
        == snapshot_before.posting_snapshot.official_url
    )
    assert snapshot_after.availability is snapshot_before.availability
    assert snapshot_after.posting_snapshot.source_alias_ids == (
        snapshot_before.posting_snapshot.source_alias_ids
    )
    assert snapshot_after.posting_snapshot.source_provenance == (
        snapshot_before.posting_snapshot.source_provenance
    )

    services = JobDiscoveryServiceBundle(
        suggest_preferences=object(),
        refresh=refresh,
        current_preferences=GetCurrentJobSearchPreferencesService(
            _ComposedPreferencesRepository(preferences)
        ),
        runs=GetDiscoveryRunService(runs, recommendations),
        feed_queries=feed_queries,
        save=SaveJobService(jobs, saved_repository),
    )
    experience = JobsExperienceService(
        profiles=profiles,
        services=services,
        jobs=jobs,
        handoff=handoff,
        now=lambda: NOW,
    )
    presentation = experience.load_feed(profile.id, FeedKind.TAILORED)
    assert [item.job_id for item in presentation.visible] == [
        item.job_id for item in first_feed.items
    ]
    selected = presentation.visible[0]
    assert selected.grade in {
        FitGrade.EXCELLENT,
        FitGrade.GOOD,
        FitGrade.WEAK,
        FitGrade.DONT_MATCH,
    }
    assert selected.eligibility is first_feed.items[0].eligibility.status
    assert selected.provisional is first_feed.items[0].provisional
    assert selected.saved is True
    assert selected.official_url == jobs.get(selected.job_id).official_url
    assert selected.job_id == first_feed.items[0].job_id
    assert all("total" not in item.model_dump() for item in presentation.visible)
    assert all(item.feed_kind is FeedKind.TAILORED for item in presentation.visible)
    assert all(item.visibility is RecommendationVisibility.VISIBLE for item in presentation.visible)
    unknown_view = next(
        item for item in presentation.visible if item.eligibility is EligibilityStatus.UNKNOWN
    )
    assert unknown_view.unresolved_facts
    assert unknown_view.provisional is True
    excluded_view = experience.load_excluded(profile.id, FeedKind.TAILORED)
    assert excluded_view
    assert all(item.visibility is RecommendationVisibility.EXCLUDED for item in excluded_view)
    assert {item.job_id for item in excluded_view}.isdisjoint(
        {item.job_id for item in presentation.visible}
    )

    handoff_parameters = set(signature(PrepareTailoringHandoffService.__init__).parameters)
    assert handoff_parameters - {"self", "jobs", "saved_jobs"} == set()
    prepared = experience.prepare_tailoring(first_feed.items[0].job_id, profile.id)
    assert prepared.title == presentation.visible[0].title
    assert prepared.description
    assert prepared.official_url
    assert prepared.posting_id == presentation.visible[0].job_id
    assert prepared.profile_id == profile.id
    assert not hasattr(prepared, "plan")
    assert not hasattr(prepared, "resume")
    assert not hasattr(prepared, "cover_letter")

    app.dependency_overrides[get_job_discovery_services] = lambda: services
    try:
        client = TestClient(app)
        response = client.post(
            "/job-discovery/feeds/tailored/refresh",
            json={"user_id": "local-user", "profile_id": profile.id},
        )
        regular = client.get("/job-discovery/feeds/tailored?user_id=local-user")
        excluded = client.get("/job-discovery/feeds/tailored/excluded?user_id=local-user")
        wrong_profile = client.post(
            "/job-discovery/feeds/tailored/refresh",
            json={"user_id": "local-user", "profile_id": "other-profile"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["feed_kind"] == FeedKind.TAILORED.value
    assert response.json()["partial_success"] is True
    assert all(item["profile_id"] == profile.id for item in response.json()["items"])
    assert regular.status_code == 200
    assert all(
        item["visibility"] == RecommendationVisibility.VISIBLE.value
        for item in regular.json()["items"]
    )
    assert excluded.status_code == 200
    assert excluded.json()["items"]
    assert all(
        item["visibility"] == RecommendationVisibility.EXCLUDED.value
        for item in excluded.json()["items"]
    )
    assert wrong_profile.status_code == 404
