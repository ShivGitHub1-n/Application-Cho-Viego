"""Deterministic due-source eligibility and priority ordering."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta

from resume_tailor.domain.job_discovery.models import SourceDefinition
from resume_tailor.domain.job_discovery.source_lifecycle import (
    SourceLifecycleOutcome,
    SourceRuntimeState,
)


def select_due_sources(
    sources: Sequence[SourceDefinition],
    states: Mapping[str, SourceRuntimeState],
    *,
    now: datetime,
    max_sources: int,
    force: bool = False,
) -> list[SourceDefinition]:
    if max_sources < 1:
        raise ValueError("maximum sources must be positive")
    due = [
        source
        for source in sources
        if _is_due(source, states.get(source.source_id), now=now, force=force)
    ]
    due.sort(
        key=lambda source: (
            source.priority_tier,
            0 if _toronto_relevance(source) else 1,
            source.source_id,
        )
    )
    return due[:max_sources]


def _is_due(
    source: SourceDefinition,
    state: SourceRuntimeState | None,
    *,
    now: datetime,
    force: bool = False,
) -> bool:
    if not source.enabled:
        return False
    if state is None:
        return True
    if force:
        return True
    if source.registry_plan_hash and state.registry_plan_hash != source.registry_plan_hash:
        return True
    if (
        source.extraction_profile_hash
        and state.extraction_profile_hash != source.extraction_profile_hash
    ):
        return True
    if source.audit_version and state.audit_version != source.audit_version:
        return True
    if state.next_eligible_refresh_at is not None and now < state.next_eligible_refresh_at:
        return False
    if state.last_attempted_at is None:
        return True
    cadence = timedelta(minutes=max(1, source.crawl_cadence_minutes))
    if state.last_outcome is SourceLifecycleOutcome.FAILED:
        backoff = min(
            cadence, timedelta(minutes=15 * (2 ** min(state.consecutive_failure_count, 6)))
        )
        return now >= state.last_attempted_at + backoff
    if state.last_outcome is SourceLifecycleOutcome.PARTIAL:
        return now >= state.last_attempted_at + min(cadence, timedelta(minutes=30))
    return now >= state.last_attempted_at + cadence


def _toronto_relevance(source: SourceDefinition) -> bool:
    return bool(
        getattr(source, "toronto_gta_relevance", False)
        or getattr(getattr(source, "geographic_coverage", None), "toronto_gta_presence", False)
    )


__all__ = ["select_due_sources"]
