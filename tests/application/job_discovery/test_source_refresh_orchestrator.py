# ruff: noqa: E501

from datetime import UTC, datetime, timedelta
from pathlib import Path

from resume_tailor.application.job_discovery.source_refresh import SourceRefreshOrchestrator
from resume_tailor.domain.job_discovery.models import SourceJobRecord
from resume_tailor.domain.job_discovery.providers import (
    RetrievalOutcome,
    RetrievedSourceRecord,
    SourceOutcome,
    SourceOutcomeStatus,
    SourceProvenance,
)
from resume_tailor.domain.job_discovery.queries import ExploreJobQuery
from resume_tailor.domain.job_discovery.source_scheduling import select_due_sources
from resume_tailor.infrastructure.job_sources.registry import (
    compile_runtime_sources,
    load_company_source_registry,
)


class _StateRepo:
    def __init__(self):
        self.values = {}

    def get(self, source_id):
        return self.values.get(source_id)

    def upsert(self, state):
        self.values[state.source_id] = state


class _Retrieval:
    def __init__(self, source):
        self.source = source

    def retrieve(self, query, *, fetched_at):
        record = SourceJobRecord(
            external_job_id="one",
            title="Software Engineer",
            company_name=self.source.company_name,
            description="Build software.",
            official_url="https://job-boards.greenhouse.io/example/jobs/one",
        )
        return RetrievalOutcome(
            records=[
                RetrievedSourceRecord(
                    source=self.source,
                    record=record,
                    provenance=SourceProvenance(
                        source_id=self.source.source_id,
                        connector_type=self.source.connector_type,
                        external_job_id="one",
                        official_url=str(record.official_url),
                        fetched_at=fetched_at,
                    ),
                )
            ],
            source_outcomes=[
                SourceOutcome(
                    source_id=self.source.source_id,
                    connector_type=self.source.connector_type,
                    status=SourceOutcomeStatus.SUCCESS,
                    records_retrieved=1,
                    records_accepted=1,
                )
            ],
            retrieved_count=1,
            accepted_count=1,
        )


def test_orchestrator_refreshes_due_sources_and_persists_runtime_state() -> None:
    registry = load_company_source_registry(
        Path("config/approved-job-sources.json"), reference_date=datetime(2026, 7, 26).date()
    )
    sources = compile_runtime_sources(registry)
    now = datetime(2026, 7, 26, 12, tzinfo=UTC)
    states = _StateRepo()
    summary = SourceRefreshOrchestrator(
        sources=sources[:1],
        retrieval_factory=lambda selected: _Retrieval(selected[0]),
        runtime_states=states,
        now=lambda: now,
    ).refresh(ExploreJobQuery(sectors=["Software Engineering"]))

    assert summary.sources_selected == [sources[0].source_id]
    assert summary.total_accepted == 1
    assert states.values[sources[0].source_id].last_successful_at == now


def test_successful_refresh_stamps_source_identity_and_next_eligibility() -> None:
    registry = load_company_source_registry(
        Path("config/approved-job-sources.json"), reference_date=datetime(2026, 7, 26).date()
    )
    source = next(
        item for item in compile_runtime_sources(registry) if item.source_id == "rocket-lab"
    )
    now = datetime(2026, 7, 26, 12, tzinfo=UTC)
    states = _StateRepo()
    SourceRefreshOrchestrator(
        sources=[source],
        retrieval_factory=lambda selected: _Retrieval(selected[0]),
        runtime_states=states,
        now=lambda: now,
    ).refresh(ExploreJobQuery(sectors=["Software Engineering"]))

    state = states.values[source.source_id]
    assert state.audit_version == source.audit_version
    assert state.registry_plan_hash == source.registry_plan_hash
    assert state.extraction_profile_hash == source.extraction_profile_hash
    assert state.next_eligible_refresh_at == now + timedelta(minutes=source.crawl_cadence_minutes)
    assert select_due_sources([source], states.values, now=now, max_sources=1) == []


def test_global_deadline_skips_sources_without_marking_them_attempted() -> None:
    registry = load_company_source_registry(
        Path("config/approved-job-sources.json"), reference_date=datetime(2026, 7, 26).date()
    )
    sources = compile_runtime_sources(registry)[:2]
    now = datetime(2026, 7, 26, 12, tzinfo=UTC)
    states = _StateRepo()
    clock_values = iter([now, now, now + timedelta(minutes=31), now + timedelta(minutes=31)])
    summary = SourceRefreshOrchestrator(
        sources=sources,
        retrieval_factory=lambda selected: _Retrieval(selected[0]),
        runtime_states=states,
        now=lambda: next(clock_values),
        max_run_duration=timedelta(minutes=30),
        max_sources=2,
    ).refresh(ExploreJobQuery(sectors=["Software Engineering"]), force=True)

    assert summary.sources_selected == [source.source_id for source in sources]
    assert summary.sources_skipped == [sources[1].source_id]
    assert summary.diagnostic_codes == ["global_deadline_exceeded"]
    assert sources[1].source_id not in states.values


def test_orchestrator_sends_retrieval_to_existing_persistence_seam() -> None:
    registry = load_company_source_registry(
        Path("config/approved-job-sources.json"), reference_date=datetime(2026, 7, 26).date()
    )
    source = compile_runtime_sources(registry)[0]
    now = datetime(2026, 7, 26, 12, tzinfo=UTC)
    persisted: list[tuple[ExploreJobQuery, object]] = []
    orchestrator = SourceRefreshOrchestrator(
        sources=[source],
        retrieval_factory=lambda selected: _Retrieval(selected[0]),
        runtime_states=_StateRepo(),
        now=lambda: now,
        persist_retrieval=lambda query, retrieval, _started: persisted.append((query, retrieval)),
    )

    orchestrator.refresh(ExploreJobQuery(sectors=["Software Engineering"]))

    assert len(persisted) == 1
    assert persisted[0][0].sectors == ["Software Engineering"]


def test_orchestrator_persists_one_aggregate_for_multiple_sources() -> None:
    registry = load_company_source_registry(
        Path("config/approved-job-sources.json"), reference_date=datetime(2026, 7, 26).date()
    )
    sources = compile_runtime_sources(registry)[:2]
    now = datetime(2026, 7, 26, 12, tzinfo=UTC)
    persisted: list[RetrievalOutcome] = []
    orchestrator = SourceRefreshOrchestrator(
        sources=sources,
        retrieval_factory=lambda selected: _Retrieval(selected[0]),
        runtime_states=_StateRepo(),
        now=lambda: now,
        persist_retrieval=lambda _query, retrieval, _started: persisted.append(retrieval),
        max_sources=2,
    )

    summary = orchestrator.refresh(
        ExploreJobQuery(sectors=["Software Engineering"]), force=True, force_all=True
    )

    assert len(persisted) == 1
    assert [item.source_id for item in persisted[0].source_outcomes] == sorted(
        source.source_id for source in sources
    )
    assert summary.sources_selected == sorted(source.source_id for source in sources)


def test_partial_source_failure_persists_successful_records_once() -> None:
    registry = load_company_source_registry(
        Path("config/approved-job-sources.json"), reference_date=datetime(2026, 7, 26).date()
    )
    sources = compile_runtime_sources(registry)[:2]
    now = datetime(2026, 7, 26, 12, tzinfo=UTC)
    states = _StateRepo()
    persisted: list[RetrievalOutcome] = []

    class FailedRetrieval:
        def retrieve(self, _query, *, fetched_at):
            return RetrievalOutcome(
                source_outcomes=[
                    SourceOutcome(
                        source_id=sources[1].source_id,
                        connector_type=sources[1].connector_type,
                        status=SourceOutcomeStatus.FAILED,
                    )
                ]
            )

    def retrieval_factory(selected):
        return FailedRetrieval() if selected[0].source_id == sources[1].source_id else _Retrieval(selected[0])

    summary = SourceRefreshOrchestrator(
        sources=sources,
        retrieval_factory=retrieval_factory,
        runtime_states=states,
        now=lambda: now,
        max_sources=2,
        persist_retrieval=lambda _query, retrieval, _started: persisted.append(retrieval),
    ).refresh(ExploreJobQuery(sectors=["Software Engineering"]), force=True, force_all=True)

    assert len(persisted) == 1
    assert len(persisted[0].records) == 1
    assert summary.partial_success is True
    assert states.values[sources[1].source_id].last_outcome.value == "failed"


def test_persistence_failure_does_not_finalize_source_success() -> None:
    registry = load_company_source_registry(
        Path("config/approved-job-sources.json"), reference_date=datetime(2026, 7, 26).date()
    )
    source = compile_runtime_sources(registry)[0]
    now = datetime(2026, 7, 26, 12, tzinfo=UTC)
    states = _StateRepo()

    summary = SourceRefreshOrchestrator(
        sources=[source],
        retrieval_factory=lambda selected: _Retrieval(selected[0]),
        runtime_states=states,
        now=lambda: now,
        persist_retrieval=lambda _query, _retrieval, _started: (_ for _ in ()).throw(
            RuntimeError("persistence failed")
        ),
    ).refresh(ExploreJobQuery(sectors=["Software Engineering"]), force=True)

    assert summary.outcomes[0].status == "failed"
    assert summary.outcomes[0].diagnostic_codes == ["persistence_failed"]
    assert states.values[source.source_id].last_outcome.value == "failed"
    assert states.values[source.source_id].last_successful_at is None
