from datetime import UTC, datetime, timedelta

from resume_tailor.domain.job_discovery.source_lifecycle import (
    SourceHealth,
    SourceLifecycleOutcome,
    SourceRuntimeState,
    fingerprint_content,
)


def test_failed_refresh_preserves_last_success_and_updates_source_state_only() -> None:
    at = datetime(2026, 7, 26, tzinfo=UTC)
    successful = SourceRuntimeState(source_id="rocket-lab").completed(
        at=at,
        outcome=SourceLifecycleOutcome.SUCCESS,
        content=[{"id": "one"}],
    )
    failed = successful.completed(
        at=at + timedelta(hours=1),
        outcome=SourceLifecycleOutcome.FAILED,
        diagnostic_codes=["detail_fetch_failed"],
    )

    assert failed.last_successful_at == successful.last_successful_at
    assert failed.content_fingerprint == successful.content_fingerprint
    assert failed.source_state_fingerprint != successful.source_state_fingerprint
    assert failed.source_health is SourceHealth.UNAVAILABLE


def test_content_and_source_state_fingerprints_are_distinct() -> None:
    at = datetime(2026, 7, 26, tzinfo=UTC)
    first = SourceRuntimeState(source_id="rocket-lab").completed(
        at=at,
        outcome=SourceLifecycleOutcome.SUCCESS,
        content=[{"id": "one"}],
    )
    content_changed = first.completed(
        at=at + timedelta(minutes=1),
        outcome=SourceLifecycleOutcome.SUCCESS,
        content=[{"id": "two"}],
    )

    assert fingerprint_content([{"id": "one"}]) != fingerprint_content([{"id": "two"}])
    assert content_changed.content_fingerprint != first.content_fingerprint
    assert content_changed.source_state_fingerprint != first.source_state_fingerprint
