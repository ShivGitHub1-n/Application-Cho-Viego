from __future__ import annotations

from threading import Event, Lock
from time import monotonic, sleep

from resume_tailor.application.job_discovery.background_refresh import (
    BackgroundJobsRefreshCoordinator,
    BackgroundRefreshStatus,
    refresh_context_key,
)


def _await_terminal(
    coordinator: BackgroundJobsRefreshCoordinator, key: str
):
    deadline = monotonic() + 2
    while monotonic() < deadline:
        snapshot = coordinator.get(key)
        if snapshot is not None and snapshot.status is not BackgroundRefreshStatus.RUNNING:
            return snapshot
        sleep(0.01)
    raise AssertionError("background refresh did not complete")


def test_duplicate_refresh_for_same_context_starts_one_operation() -> None:
    coordinator = BackgroundJobsRefreshCoordinator()
    release = Event()
    calls = 0
    calls_lock = Lock()
    key = refresh_context_key("profile-a", "tailored")

    def operation() -> str:
        nonlocal calls
        with calls_lock:
            calls += 1
        release.wait(timeout=1)
        return "updated"

    first = coordinator.start(key, operation)
    second = coordinator.start(key, operation)
    release.set()
    completed = _await_terminal(coordinator, key)

    assert first.token == second.token
    assert first.started_new is True
    assert second.started_new is False
    assert calls == 1
    assert completed.status is BackgroundRefreshStatus.SUCCEEDED
    assert completed.result == "updated"


def test_refresh_results_remain_scoped_to_the_requested_context() -> None:
    coordinator = BackgroundJobsRefreshCoordinator()
    first_key = refresh_context_key("profile-a", "explore", sector="Software")
    second_key = refresh_context_key("profile-b", "explore", sector="Hardware")

    coordinator.start(first_key, lambda: "profile-a-results")
    coordinator.start(second_key, lambda: "profile-b-results")

    first = _await_terminal(coordinator, first_key)
    second = _await_terminal(coordinator, second_key)
    assert first.result == "profile-a-results"
    assert second.result == "profile-b-results"
    assert first.key != second.key


def test_background_failure_is_sanitized_and_preserves_context_state() -> None:
    coordinator = BackgroundJobsRefreshCoordinator()
    key = refresh_context_key("profile-a", "tailored")

    coordinator.start(key, lambda: (_ for _ in ()).throw(RuntimeError("private token")))
    completed = _await_terminal(coordinator, key)

    assert completed.status is BackgroundRefreshStatus.FAILED
    assert "private token" not in (completed.error_message or "")
    assert "Previously stored recommendations remain available" in (
        completed.error_message or ""
    )
