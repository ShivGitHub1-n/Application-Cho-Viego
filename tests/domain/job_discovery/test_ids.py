from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from resume_tailor.domain.job_discovery.ids import (
    job_id,
    recommendation_id,
    run_id,
    saved_job_id,
)


def _digest(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:24]


def test_ids_use_the_plan_hash_inputs_and_prefixes() -> None:
    started_at = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
    run = run_id("user-1", "profile-1", 2, 3, started_at)
    recommendation = recommendation_id(run, "job-1", 2, 3)

    assert job_id("greenhouse", "board-1", "123") == (
        "job-" + _digest("greenhouse", "board-1", "123")
    )
    assert run == "run-" + _digest("user-1", "profile-1", "2", "3", started_at.isoformat())
    assert recommendation == "rec-" + _digest(run, "job-1", "2", "3")
    assert saved_job_id("user-1", "job-1") == "saved-" + _digest("user-1", "job-1")
