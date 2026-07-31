"""Bounded scheduled source refresh orchestration."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from resume_tailor.domain.job_discovery.models import SourceDefinition
from resume_tailor.domain.job_discovery.providers import (
    RetrievalOutcome,
    SourceOutcome,
    SourceOutcomeStatus,
)
from resume_tailor.domain.job_discovery.queries import ExploreJobQuery
from resume_tailor.domain.job_discovery.source_lifecycle import (
    SourceLifecycleOutcome,
    SourceRuntimeState,
)
from resume_tailor.domain.job_discovery.source_scheduling import select_due_sources
from resume_tailor.ports.job_discovery import SourceRuntimeStateRepository


class SourceRefreshSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    status: str
    retrieved_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    diagnostic_codes: list[str] = Field(default_factory=list)
    browser_fallback_used: bool = False


class RefreshRunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    started_at: datetime
    completed_at: datetime
    sources_selected: list[str] = Field(default_factory=list)
    sources_skipped: list[str] = Field(default_factory=list)
    outcomes: list[SourceRefreshSummary] = Field(default_factory=list)
    total_retrieved: int = 0
    total_accepted: int = 0
    partial_success: bool = False
    diagnostic_codes: list[str] = Field(default_factory=list)


class InMemorySourceLock:
    def __init__(self) -> None:
        self._locks: dict[str, tuple[str, datetime]] = {}

    def acquire(
        self, source_id: str, run_id: str, *, now: datetime, stale_after: timedelta
    ) -> bool:
        existing = self._locks.get(source_id)
        if existing is not None and now - existing[1] < stale_after:
            return False
        self._locks[source_id] = (run_id, now)
        return True

    def release(self, source_id: str, run_id: str) -> None:
        if self._locks.get(source_id, (None, None))[0] == run_id:
            self._locks.pop(source_id, None)


class _RetrievalLike(Protocol):
    def retrieve(self, query: ExploreJobQuery, *, fetched_at: datetime) -> RetrievalOutcome: ...


@dataclass(frozen=True)
class _StartedSource:
    source: SourceDefinition
    attempted_state: SourceRuntimeState
    retrieval: RetrievalOutcome
    outcome: SourceOutcome
    diagnostic_codes: list[str]
    records: list[dict[str, Any]]


class SourceRefreshOrchestrator:
    def __init__(
        self,
        *,
        sources: Sequence[SourceDefinition],
        retrieval_factory: Callable[[Sequence[SourceDefinition]], _RetrievalLike],
        runtime_states: SourceRuntimeStateRepository,
        now: Callable[[], datetime],
        max_sources: int = 10,
        lock_manager: InMemorySourceLock | None = None,
        max_run_duration: timedelta | None = timedelta(minutes=30),
        persist_retrieval: Callable[[ExploreJobQuery, RetrievalOutcome, datetime], None]
        | None = None,
    ) -> None:
        self._sources = tuple(sorted(sources, key=lambda source: source.source_id))
        self._retrieval_factory = retrieval_factory
        self._runtime_states = runtime_states
        self._now = now
        self._max_sources = max_sources
        self._locks = lock_manager or InMemorySourceLock()
        if max_run_duration is not None and max_run_duration <= timedelta(0):
            raise ValueError("maximum refresh duration must be positive")
        self._max_run_duration = max_run_duration
        self._persist_retrieval = persist_retrieval

    def refresh(
        self,
        query: ExploreJobQuery,
        *,
        force: bool = False,
        force_source_id: str | None = None,
        force_all: bool = False,
        run_id: str = "source-refresh",
    ) -> RefreshRunSummary:
        started = self._now()
        deadline = started + self._max_run_duration if self._max_run_duration else None
        states = {
            source.source_id: state
            for source in self._sources
            if (state := self._runtime_states.get(source.source_id)) is not None
        }
        if force_source_id is not None:
            selected = [self._source_by_id(force_source_id)]
        elif force_all:
            selected = list(self._sources)[: self._max_sources]
        else:
            selected = select_due_sources(
                self._sources,
                states,
                now=started,
                max_sources=self._max_sources,
                force=force,
            )
        selected_ids = [source.source_id for source in selected]
        skipped: list[str] = []
        diagnostic_codes: list[str] = []
        started_sources: list[_StartedSource] = []
        locked_source_ids: list[str] = []
        persistence_failed = False
        try:
            for source in selected:
                if deadline is not None and self._now() >= deadline:
                    skipped.append(source.source_id)
                    diagnostic_codes.append("global_deadline_exceeded")
                    continue
                if not self._locks.acquire(
                    source.source_id, run_id, now=started, stale_after=timedelta(hours=1)
                ):
                    skipped.append(source.source_id)
                    continue
                locked_source_ids.append(source.source_id)
                state = self._stamped_state(
                    states.get(source.source_id, SourceRuntimeState(source_id=source.source_id)),
                    source,
                ).attempted(started)
                self._runtime_states.upsert(state)
                retrieval = self._retrieval_factory([source]).retrieve(query, fetched_at=started)
                outcome = next(
                    item for item in retrieval.source_outcomes if item.source_id == source.source_id
                )
                codes = sorted({item.code for item in [*outcome.warnings, *outcome.errors]})
                records = [
                    item.record.model_dump(mode="json")
                    for item in retrieval.records
                    if item.source.source_id == source.source_id
                ]
                started_sources.append(
                    _StartedSource(
                        source=source,
                        attempted_state=state,
                        retrieval=retrieval,
                        outcome=outcome,
                        diagnostic_codes=codes,
                        records=records,
                    )
                )
            if started_sources and self._persist_retrieval is not None:
                aggregate = _aggregate_retrieval(
                    item.retrieval for item in started_sources
                )
                try:
                    self._persist_retrieval(query, aggregate, started)
                except Exception:
                    persistence_failed = True
                    diagnostic_codes.append("persistence_failed")

            outcomes = []
            for item in started_sources:
                codes = list(item.diagnostic_codes)
                lifecycle = _lifecycle(item.outcome.status)
                status = item.outcome.status
                if persistence_failed and status is not SourceOutcomeStatus.FAILED:
                    codes.append("persistence_failed")
                    lifecycle = SourceLifecycleOutcome.FAILED
                    status = SourceOutcomeStatus.FAILED
                codes = sorted(set(codes))
                completed_state = item.attempted_state.completed(
                    at=started,
                    outcome=lifecycle,
                    diagnostic_codes=codes,
                    content=item.records,
                    browser_required="browser_required" in codes,
                )
                completed_state = completed_state.model_copy(
                    update={
                        "audit_version": getattr(item.source, "audit_version", None),
                        "registry_plan_hash": getattr(item.source, "registry_plan_hash", None),
                        "extraction_profile_hash": getattr(
                            item.source, "extraction_profile_hash", None
                        ),
                        "next_eligible_refresh_at": _next_eligible_at(
                            started,
                            lifecycle,
                            item.source.crawl_cadence_minutes,
                            completed_state.consecutive_failure_count,
                        ),
                    }
                ).with_state_fingerprint()
                self._runtime_states.upsert(completed_state)
                outcomes.append(
                    SourceRefreshSummary(
                        source_id=item.source.source_id,
                        status=status.value,
                        retrieved_count=item.outcome.records_retrieved,
                        accepted_count=item.outcome.records_accepted,
                        diagnostic_codes=codes,
                        browser_fallback_used="browser_required" in codes,
                    )
                )
        finally:
            for source_id in locked_source_ids:
                self._locks.release(source_id, run_id)
        completed = self._now()
        has_success = any(item.status != SourceOutcomeStatus.FAILED.value for item in outcomes)
        has_failure = any(item.status == SourceOutcomeStatus.FAILED.value for item in outcomes)
        return RefreshRunSummary(
            started_at=started,
            completed_at=completed,
            sources_selected=selected_ids,
            sources_skipped=sorted(skipped),
            outcomes=sorted(outcomes, key=lambda item: item.source_id),
            total_retrieved=sum(item.retrieved_count for item in outcomes),
            total_accepted=sum(item.accepted_count for item in outcomes),
            partial_success=any(
                item.status == SourceOutcomeStatus.PARTIAL.value for item in outcomes
            )
            or (has_success and has_failure),
            diagnostic_codes=sorted(set(diagnostic_codes)),
        )

    @staticmethod
    def _stamped_state(
        state: SourceRuntimeState, source: SourceDefinition
    ) -> SourceRuntimeState:
        return state.model_copy(
            update={
                "audit_version": getattr(source, "audit_version", None),
                "registry_plan_hash": getattr(source, "registry_plan_hash", None),
                "extraction_profile_hash": getattr(source, "extraction_profile_hash", None),
            }
        )

    def _source_by_id(self, source_id: str) -> SourceDefinition:
        for source in self._sources:
            if source.source_id == source_id:
                if not source.enabled:
                    raise ValueError("source is disabled")
                return source
        raise KeyError(source_id)


def _lifecycle(status: SourceOutcomeStatus) -> SourceLifecycleOutcome:
    return {
        SourceOutcomeStatus.SUCCESS: SourceLifecycleOutcome.SUCCESS,
        SourceOutcomeStatus.PARTIAL: SourceLifecycleOutcome.PARTIAL,
        SourceOutcomeStatus.FAILED: SourceLifecycleOutcome.FAILED,
    }[status]


def _aggregate_retrieval(retrievals: Iterable[RetrievalOutcome]) -> RetrievalOutcome:
    retrievals = tuple(retrievals)
    records = [item for retrieval in retrievals for item in retrieval.records]
    source_outcomes = [
        item for retrieval in retrievals for item in retrieval.source_outcomes
    ]
    records.sort(
        key=lambda item: (
            item.source.source_id,
            item.record.external_job_id,
            str(item.record.official_url),
        )
    )
    source_outcomes.sort(key=lambda item: (item.source_id, item.connector_type.value))
    has_success = any(item.status is not SourceOutcomeStatus.FAILED for item in source_outcomes)
    has_failure = any(item.status is SourceOutcomeStatus.FAILED for item in source_outcomes)
    return RetrievalOutcome(
        records=records,
        source_outcomes=source_outcomes,
        partial_success=any(
            item.status is SourceOutcomeStatus.PARTIAL for item in source_outcomes
        )
        or (has_success and has_failure),
        retrieved_count=sum(item.retrieved_count for item in retrievals),
        accepted_count=sum(item.accepted_count for item in retrievals),
    )


def _next_eligible_at(
    at: datetime,
    outcome: SourceLifecycleOutcome,
    cadence_minutes: int,
    failure_count: int,
) -> datetime:
    cadence = timedelta(minutes=max(1, cadence_minutes))
    if outcome is SourceLifecycleOutcome.FAILED:
        delay = min(cadence, timedelta(minutes=15 * (2 ** min(failure_count, 6))))
    elif outcome is SourceLifecycleOutcome.PARTIAL:
        delay = min(cadence, timedelta(minutes=30))
    else:
        delay = cadence
    return at + delay


__all__ = [
    "InMemorySourceLock",
    "RefreshRunSummary",
    "SourceRefreshOrchestrator",
    "SourceRefreshSummary",
]
