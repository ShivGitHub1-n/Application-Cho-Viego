from __future__ import annotations

import sqlite3
from copy import deepcopy
from datetime import UTC, datetime

import pytest
from pydantic import AnyHttpUrl

from resume_tailor.application.job_discovery.preferences import ProfileNotFoundError
from resume_tailor.application.job_discovery.refresh import RefreshJobDiscoveryService
from resume_tailor.application.job_discovery.source_refresh import SourceRefreshOrchestrator
from resume_tailor.domain.job_discovery.ids import job_id
from resume_tailor.domain.job_discovery.models import (
    ConnectorType,
    DiscoveryRunStatus,
    JobSearchPreferences,
    JobSourceFetchResult,
    SourceJobRecord,
    SourceRecordWarning,
    SourceRecordWarningCode,
    SupportedJobSource,
    WorkArrangement,
)
from resume_tailor.domain.job_discovery.providers import (
    RetrievalOutcome,
    RetrievedSourceRecord,
    SourceOutcome,
    SourceOutcomeStatus,
    SourceProvenance,
)
from resume_tailor.domain.job_discovery.queries import ExploreJobQuery
from resume_tailor.domain.models import MasterProfile, RoleFamily
from resume_tailor.infrastructure.job_discovery_sqlite import (
    SQLiteAtomicJobDiscoveryPersistence,
    SQLiteDiscoveredJobRepository,
    SQLiteDiscoveryRunRepository,
    SQLiteJobRecommendationRepository,
    SQLiteSourceIdentityAliasRepository,
)
from resume_tailor.infrastructure.job_sources.errors import (
    JobSourceAuthenticationError,
    JobSourceEnvelopeError,
    JobSourceNotFoundError,
    JobSourceRateLimitedError,
    JobSourceTransportError,
)
from resume_tailor.infrastructure.job_sources.registry import (
    compile_runtime_sources,
    load_company_source_registry,
)

WHEN = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


def _profile(*, profile_id: str = "p1", user_id: str = "u1") -> MasterProfile:
    return MasterProfile(
        id=profile_id,
        user_id=user_id,
        version=3,
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


def _preferences(*, preferred_companies: list[str] | None = None) -> JobSearchPreferences:
    return JobSearchPreferences(
        user_id="u1",
        profile_id="p1",
        version=5,
        role_family_priority=[RoleFamily.SOFTWARE_DATA_ENGINEERING],
        target_titles=["Software Engineer"],
        related_title_variants=[],
        technical_themes=["python"],
        career_interests=["software"],
        job_levels=[],
        locations=[],
        work_arrangement=WorkArrangement.UNKNOWN,
        preferred_companies=preferred_companies or [],
        created_at=WHEN,
        confirmed_at=WHEN,
    )


def _source(source_id: str = "source-a") -> SupportedJobSource:
    return SupportedJobSource(
        source_id=source_id,
        connector_type=ConnectorType.GREENHOUSE,
        company_name=source_id,
        board_token=source_id,
        enabled=True,
        official_base_url="https://boards.greenhouse.io",
    )


def _record(
    external_id: str,
    *,
    title: str = "Software Engineer",
    company: str = "Acme Robotics",
    location: str | None = "Toronto, ON, Canada",
) -> SourceJobRecord:
    return SourceJobRecord(
        external_job_id=external_id,
        title=title,
        company_name=company,
        description="Required Python. Build and test software systems.",
        official_url=f"https://boards.greenhouse.io/acme/jobs/{external_id}",
        location_raw=location,
        work_arrangement=WorkArrangement.REMOTE,
        posted_at=WHEN,
    )


class FakeProfileRepository:
    def __init__(self, profile: MasterProfile | None = None) -> None:
        self.profile = profile or _profile()

    def get(self, profile_id: str) -> MasterProfile | None:
        return self.profile if self.profile.id == profile_id else None


class FakePreferencesRepository:
    def get_current(self, user_id: str, profile_id: str) -> JobSearchPreferences | None:
        return None

    def save_confirmed(self, preferences: JobSearchPreferences) -> None:
        pass


class FakeSourceRepository:
    def __init__(self, sources: list[SupportedJobSource]) -> None:
        self.sources = sources

    def list_enabled(self) -> list[SupportedJobSource]:
        return list(self.sources)


class FakeJobRepository:
    def __init__(self) -> None:
        self.jobs = {}

    def upsert(self, job) -> None:
        self.jobs[job.id] = job

    def get(self, job_id: str):
        return self.jobs.get(job_id)


class FakeRecommendationRepository:
    def __init__(self) -> None:
        self.by_run = {}

    def replace_for_run(self, run_id: str, recommendations: list) -> None:
        self.by_run[run_id] = list(recommendations)

    def list_for_run(self, run_id: str) -> list:
        return list(self.by_run.get(run_id, []))


class FakeRunRepository:
    def __init__(self) -> None:
        self.created = []
        self.completed = []
        self.by_id = {}

    def create(self, run) -> None:
        self.created.append(run)
        self.by_id[run.id] = run

    def complete(self, run) -> None:
        self.completed.append(run)
        self.by_id[run.id] = run

    def get(self, run_id: str):
        return self.by_id.get(run_id)


class FakeConnector:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result or JobSourceFetchResult(records=[], warnings=[])
        self.error = error
        self.calls = []

    def fetch(self, source, *, fetched_at):
        self.calls.append((source.source_id, fetched_at))
        if self.error:
            raise self.error
        return self.result.model_copy(deep=True)


def _service(
    sources: list[SupportedJobSource],
    connectors: dict[str, FakeConnector],
    *,
    profile: MasterProfile | None = None,
) -> tuple[
    RefreshJobDiscoveryService,
    FakeRunRepository,
    FakeRecommendationRepository,
    FakeJobRepository,
]:
    runs = FakeRunRepository()
    recommendations = FakeRecommendationRepository()
    jobs = FakeJobRepository()
    service = RefreshJobDiscoveryService(
        profiles=FakeProfileRepository(profile),
        preferences=FakePreferencesRepository(),
        sources=FakeSourceRepository(sources),
        connectors={
            ConnectorType.GREENHOUSE: connectors.get(
                "greenhouse", FakeConnector()
            )
        },
        discovered_jobs=jobs,
        recommendations=recommendations,
        runs=runs,
    )
    return service, runs, recommendations, jobs


def test_refresh_empty_registry_has_explicit_status() -> None:
    service, runs, recommendations, _ = _service([], {})

    run = service.refresh("u1", "p1", _preferences(), started_at=WHEN)

    assert run.status is DiscoveryRunStatus.NO_SOURCES_CONFIGURED
    assert run.error_messages == []
    assert run.warning_count == 0
    assert len(runs.created) == 1
    assert len(runs.completed) == 1
    assert recommendations.list_for_run(run.id) == []


def test_successful_one_source_refresh_persists_jobs_recommendations_and_run() -> None:
    source = _source()
    connector = FakeConnector(JobSourceFetchResult(records=[_record("1")], warnings=[]))
    service, runs, recommendations, jobs = _service(
        [source], {"greenhouse": connector}
    )

    run = service.refresh("u1", "p1", _preferences(), started_at=WHEN)

    assert run.status is DiscoveryRunStatus.COMPLETED
    assert run.record_count == 1
    assert run.normalized_count == 1
    assert run.returned_count == 1
    assert len(jobs.jobs) == 1
    assert [item.rank for item in recommendations.list_for_run(run.id)] == [1]
    recommendation = recommendations.list_for_run(run.id)[0]
    assert (
        recommendation.user_id,
        recommendation.profile_id,
        recommendation.profile_version,
        recommendation.preference_version,
    ) == ("u1", "p1", 3, 5)
    assert runs.created[0].status is DiscoveryRunStatus.RUNNING
    assert runs.completed[-1] == run
    assert connector.calls == [(source.source_id, WHEN)]


def test_refresh_persists_every_evaluation_without_initial_ten_truncation() -> None:
    source = _source()
    connector = FakeConnector(
        JobSourceFetchResult(
            records=[
                _record(str(index)).model_copy(
                    update={"description": f"Required Python. Build system {index}."}
                )
                for index in range(11)
            ],
            warnings=[],
        )
    )
    service, _, recommendations, jobs = _service([source], {"greenhouse": connector})

    run = service.refresh("u1", "p1", _preferences(), started_at=WHEN)

    assert len(jobs.jobs) == 11
    assert run.scored_count == 11
    assert run.returned_count == 11
    assert [item.rank for item in recommendations.list_for_run(run.id)] == list(range(1, 12))


def test_partial_source_failure_keeps_valid_results_and_sorts_warnings() -> None:
    good_source = _source("good")
    bad_source = _source("bad")
    good = FakeConnector(
        JobSourceFetchResult(
            records=[_record("1")],
            warnings=[
                SourceRecordWarning(
                    external_job_id="2",
                    code=SourceRecordWarningCode.MISSING_TITLE,
                    message="missing title",
                ),
                SourceRecordWarning(
                    external_job_id="1",
                    code=SourceRecordWarningCode.INVALID_LOCATION,
                    message="invalid location",
                ),
            ],
        )
    )
    bad = FakeConnector(error=JobSourceRateLimitedError("secret token must not leak"))
    service, _, recommendations, _ = _service(
        [bad_source, good_source], {"greenhouse": good}
    )
    service._connectors = {
        ConnectorType.GREENHOUSE: {
            "bad": bad,
            "good": good,
        }
    }

    run = service.refresh("u1", "p1", _preferences(), started_at=WHEN)

    assert run.status is DiscoveryRunStatus.COMPLETED_WITH_WARNINGS
    assert recommendations.list_for_run(run.id)
    assert run.warning_count == 2
    assert run.source_warnings == [
        "good|invalid_location|1|Provider record had an invalid location.",
        "good|missing_title|2|Provider record was missing a title.",
    ]
    assert "secret token" not in " ".join(run.error_messages)


@pytest.mark.parametrize(
    "error",
    [
        JobSourceAuthenticationError("auth"),
        JobSourceRateLimitedError("rate"),
        JobSourceNotFoundError("missing"),
        JobSourceTransportError("transport"),
        JobSourceEnvelopeError("malformed"),
    ],
)
def test_all_source_failure_is_explicit(error: Exception) -> None:
    source = _source()
    connector = FakeConnector(error=error)
    service, _, recommendations, _ = _service([source], {"greenhouse": connector})

    run = service.refresh("u1", "p1", _preferences(), started_at=WHEN)

    assert run.status is DiscoveryRunStatus.FAILED_ALL_SOURCES
    assert recommendations.list_for_run(run.id) == []
    assert run.error_messages


def test_unexpected_processing_failure_completes_the_persisted_run() -> None:
    source = _source()
    connector = FakeConnector(JobSourceFetchResult(records=[_record("1")], warnings=[]))
    service, runs, recommendations, _ = _service([source], {"greenhouse": connector})
    service._normalizer = type(
        "FailingNormalizer",
        (),
        {"normalize": lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom"))},
    )()

    run = service.refresh("u1", "p1", _preferences(), started_at=WHEN)

    assert run.status is DiscoveryRunStatus.FAILED_ALL_SOURCES
    assert run.error_messages == ["refresh processing failed"]
    assert runs.completed[-1] == run
    assert recommendations.list_for_run(run.id) == []


def test_source_order_does_not_change_recommendation_ids_or_ranks() -> None:
    first = _source("first")
    second = _source("second")
    first_connector = FakeConnector(JobSourceFetchResult(records=[_record("1")], warnings=[]))
    second_connector = FakeConnector(JobSourceFetchResult(records=[_record("2")], warnings=[]))

    service_a, _, recommendations_a, _ = _service(
        [first, second], {"greenhouse": first_connector}
    )
    service_a._connectors = {
        ConnectorType.GREENHOUSE: {"first": first_connector, "second": second_connector}
    }
    run_a = service_a.refresh("u1", "p1", _preferences(), started_at=WHEN)

    service_b, _, recommendations_b, _ = _service(
        [second, first], {"greenhouse": first_connector}
    )
    service_b._connectors = {
        ConnectorType.GREENHOUSE: {"first": first_connector, "second": second_connector}
    }
    run_b = service_b.refresh("u1", "p1", _preferences(), started_at=WHEN)

    assert run_a.id == run_b.id
    assert [item.id for item in recommendations_a.list_for_run(run_a.id)] == [
        item.id for item in recommendations_b.list_for_run(run_b.id)
    ]


def test_refresh_rejects_missing_or_foreign_profile() -> None:
    service, _, _, _ = _service([], {}, profile=_profile(user_id="other"))

    with pytest.raises(ProfileNotFoundError):
        service.refresh("u1", "p1", _preferences(), started_at=WHEN)


def test_refresh_does_not_mutate_preferences_or_profile() -> None:
    source = _source()
    connector = FakeConnector(JobSourceFetchResult(records=[_record("1")], warnings=[]))
    profile = _profile()
    service, _, _, _ = _service([source], {"greenhouse": connector}, profile=profile)
    preferences = _preferences()
    before_preferences = deepcopy(preferences)
    before_profile = deepcopy(profile)

    service.refresh("u1", "p1", preferences, started_at=WHEN)

    assert preferences == before_preferences
    assert profile == before_profile


def test_multi_source_retrieval_persists_one_run_through_existing_pipeline(tmp_path) -> None:
    registry = load_company_source_registry(
        "config/approved-job-sources.json", reference_date=datetime(2026, 7, 26).date()
    )
    first_party = next(
        source for source in compile_runtime_sources(registry) if source.source_id == "rocket-lab"
    )
    provider = _source("provider")
    provider_record = _record("provider-1").model_copy(
        update={
            "application_url": AnyHttpUrl(
                "https://boards.greenhouse.io/acme/jobs/provider-1"
            )
        }
    )
    first_party_record = SourceJobRecord(
        external_job_id="first-party-1",
        title="Software Engineer",
        company_name=first_party.company_name,
        description="Required Python. Build software systems.",
        official_url="https://www.rocketlabusa.com/careers/positions/first-party-1",
        location_raw="Toronto, ON, Canada",
        work_arrangement=WorkArrangement.REMOTE,
        posted_at=WHEN,
    )

    def retrieved(source, record):
        return RetrievedSourceRecord(
            source=source,
            record=record,
            provenance=SourceProvenance(
                source_id=source.source_id,
                connector_type=source.connector_type,
                external_job_id=record.external_job_id,
                official_url=str(record.official_url),
                fetched_at=WHEN,
            ),
        )

    retrieval = RetrievalOutcome(
        records=[retrieved(provider, provider_record), retrieved(first_party, first_party_record)],
        source_outcomes=[
            SourceOutcome(
                source_id=provider.source_id,
                connector_type=provider.connector_type,
                status=SourceOutcomeStatus.SUCCESS,
                records_retrieved=1,
                records_accepted=1,
            ),
            SourceOutcome(
                source_id=first_party.source_id,
                connector_type=first_party.connector_type,
                status=SourceOutcomeStatus.SUCCESS,
                records_retrieved=1,
                records_accepted=1,
            ),
        ],
        retrieved_count=2,
        accepted_count=2,
    )
    database = tmp_path / "multi-source.sqlite3"
    jobs = SQLiteDiscoveredJobRepository(database)
    recommendations = SQLiteJobRecommendationRepository(database)
    runs = SQLiteDiscoveryRunRepository(database)
    aliases = SQLiteSourceIdentityAliasRepository(database)
    service = RefreshJobDiscoveryService(
        profiles=FakeProfileRepository(),
        preferences=FakePreferencesRepository(),
        sources=FakeSourceRepository([provider, first_party]),
        connectors={ConnectorType.GREENHOUSE: FakeConnector()},
        discovered_jobs=jobs,
        recommendations=recommendations,
        runs=runs,
        atomic_persistence=SQLiteAtomicJobDiscoveryPersistence(database),
        aliases=aliases,
    )
    query = ExploreJobQuery(
        sectors=["Software Engineering"], title_keywords=["Software Engineer"]
    )

    class RuntimeStates:
        def __init__(self) -> None:
            self.values = {}

        def get(self, source_id):
            return self.values.get(source_id)

        def upsert(self, state) -> None:
            self.values[state.source_id] = state

    retrieval_by_source = {
        source_id: retrieval.model_copy(
            update={
                "records": [
                    item for item in retrieval.records if item.source.source_id == source_id
                ],
                "source_outcomes": [
                    item for item in retrieval.source_outcomes if item.source_id == source_id
                ],
                "retrieved_count": 1,
                "accepted_count": 1,
            }
        )
        for source_id in (provider.source_id, first_party.source_id)
    }
    retrieval_calls: list[str] = []

    def retrieval_factory(selected):
        source = selected[0]

        class OfflineRetrieval:
            def retrieve(self, _query, *, fetched_at):
                retrieval_calls.append(source.source_id)
                return retrieval_by_source[source.source_id]

        return OfflineRetrieval()

    orchestrator = SourceRefreshOrchestrator(
        sources=[provider, first_party],
        retrieval_factory=retrieval_factory,
        runtime_states=RuntimeStates(),
        now=lambda: WHEN,
        max_sources=2,
        persist_retrieval=lambda persisted_query, persisted_retrieval, started_at: (
            service.persist_retrieval_for_profile(
                "u1",
                "p1",
                query=persisted_query,
                retrieval=persisted_retrieval,
                started_at=started_at,
            )
        ),
    )
    first_summary = orchestrator.refresh(query, force=True, force_all=True)
    second_summary = orchestrator.refresh(query, force=True, force_all=True)

    assert retrieval_calls == ["provider", "rocket-lab", "provider", "rocket-lab"]
    assert first_summary.total_accepted == 2
    assert second_summary.total_accepted == 2
    first_party_job_id = job_id(
        "first_party", "rocket-lab", first_party_record.external_job_id
    )
    provider_job_id = job_id("greenhouse", "provider", provider_record.external_job_id)
    assert jobs.get(first_party_job_id) is not None
    assert jobs.get(provider_job_id) is not None
    assert len(recommendations.list_for_feed("u1", "explore", include_excluded=True)) == 2
    assert len(aliases.list_for_source("rocket-lab")) == 1
    assert aliases.list_for_source("rocket-lab")[0].identity_kind == "canonical_detail"
    assert jobs.get(first_party_job_id).source_provenance[0].source_id == "rocket-lab"
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM discovery_runs").fetchone()[0] == 1
