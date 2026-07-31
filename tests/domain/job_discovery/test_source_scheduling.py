# ruff: noqa: E501

from datetime import UTC, datetime, timedelta
from pathlib import Path

from resume_tailor.domain.job_discovery.source_lifecycle import (
    SourceLifecycleOutcome,
    SourceRuntimeState,
)
from resume_tailor.domain.job_discovery.source_scheduling import select_due_sources
from resume_tailor.infrastructure.job_sources.registry import (
    compile_runtime_sources,
    load_company_source_registry,
)


def _sources():
    registry = load_company_source_registry(
        Path("config/approved-job-sources.json"), reference_date=datetime(2026, 7, 26).date()
    )
    return compile_runtime_sources(registry)


def test_due_selection_is_deterministic_and_respects_cadence_and_backoff() -> None:
    sources = _sources()
    now = datetime(2026, 7, 26, 12, tzinfo=UTC)
    first = sources[0]
    successful = SourceRuntimeState(
        source_id=first.source_id,
        last_attempted_at=now - timedelta(minutes=1),
        last_outcome=SourceLifecycleOutcome.SUCCESS,
    )
    failed = SourceRuntimeState(
        source_id="rocket-lab",
        last_attempted_at=now - timedelta(minutes=1),
        last_outcome=SourceLifecycleOutcome.FAILED,
        consecutive_failure_count=1,
    )

    due = select_due_sources(
        sources, {first.source_id: successful, "rocket-lab": failed}, now=now, max_sources=3
    )

    assert "rocket-lab" not in {source.source_id for source in due}
    repeated = select_due_sources(
        sources, {first.source_id: successful, "rocket-lab": failed}, now=now, max_sources=3
    )
    assert [source.source_id for source in due] == [source.source_id for source in repeated]


def test_priority_tier_then_toronto_then_source_id_orders_due_sources() -> None:
    sources = _sources()
    now = datetime(2026, 7, 26, tzinfo=UTC)
    due = select_due_sources(sources, {}, now=now, max_sources=10)

    assert [source.source_id for source in due] == [
        "tenstorrent",
        "waabi",
        "anduril",
        "anthropic",
        "figure",
        "palantir",
        "relativity-space",
        "rocket-lab",
        "spacex",
        "zoox",
    ]


def test_force_bypasses_cadence_but_keeps_source_runnable() -> None:
    sources = _sources()
    now = datetime(2026, 7, 26, tzinfo=UTC)
    source = sources[0]
    state = SourceRuntimeState(
        source_id=source.source_id,
        last_attempted_at=now,
        last_outcome=SourceLifecycleOutcome.SUCCESS,
        next_eligible_refresh_at=now + timedelta(hours=1),
        registry_plan_hash=source.registry_plan_hash,
        audit_version=source.audit_version,
        extraction_profile_hash=source.extraction_profile_hash,
    )

    assert select_due_sources(
        [source], {source.source_id: state}, now=now, max_sources=1
    ) == []
    assert select_due_sources(
        [source], {source.source_id: state}, now=now, max_sources=1, force=True
    ) == [source]


def test_audit_plan_or_extraction_change_makes_source_due() -> None:
    sources = _sources()
    now = datetime(2026, 7, 26, tzinfo=UTC)
    source = sources[0]
    base = {
        "source_id": source.source_id,
        "last_attempted_at": now,
        "last_outcome": SourceLifecycleOutcome.SUCCESS,
        "next_eligible_refresh_at": now + timedelta(hours=1),
        "registry_plan_hash": source.registry_plan_hash,
        "extraction_profile_hash": source.extraction_profile_hash,
        "audit_version": source.audit_version,
    }
    assert select_due_sources([source], {source.source_id: SourceRuntimeState(**base)}, now=now, max_sources=1) == []
    for field in ("registry_plan_hash", "extraction_profile_hash", "audit_version"):
        changed = dict(base)
        changed[field] = "changed"
        assert select_due_sources(
            [source], {source.source_id: SourceRuntimeState(**changed)}, now=now, max_sources=1
        ) == [source]
