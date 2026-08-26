"""Session-scoped background execution for user-triggered Jobs refreshes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from threading import Lock, Thread
from time import perf_counter
from typing import Any
from uuid import uuid4


class BackgroundRefreshStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class BackgroundRefreshSnapshot:
    key: str
    token: str
    status: BackgroundRefreshStatus
    started_at: datetime
    completed_at: datetime | None = None
    elapsed_seconds: float | None = None
    result: Any | None = None
    error_message: str | None = None
    started_new: bool = False


class BackgroundJobsRefreshCoordinator:
    """Run at most one refresh per feed context without touching UI state."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._snapshots: dict[str, BackgroundRefreshSnapshot] = {}

    def start(self, key: str, operation: Callable[[], Any]) -> BackgroundRefreshSnapshot:
        with self._lock:
            existing = self._snapshots.get(key)
            if existing is not None and existing.status is BackgroundRefreshStatus.RUNNING:
                return replace(existing, started_new=False)
            token = uuid4().hex
            started_at = datetime.now(UTC)
            snapshot = BackgroundRefreshSnapshot(
                key=key,
                token=token,
                status=BackgroundRefreshStatus.RUNNING,
                started_at=started_at,
                started_new=True,
            )
            self._snapshots[key] = snapshot
        Thread(
            target=self._run,
            args=(key, token, started_at, operation),
            daemon=True,
            name=f"jobs-refresh-{token[:8]}",
        ).start()
        return snapshot

    def get(self, key: str) -> BackgroundRefreshSnapshot | None:
        with self._lock:
            return self._snapshots.get(key)

    def _run(
        self,
        key: str,
        token: str,
        started_at: datetime,
        operation: Callable[[], Any],
    ) -> None:
        started = perf_counter()
        try:
            result = operation()
            snapshot = BackgroundRefreshSnapshot(
                key=key,
                token=token,
                status=BackgroundRefreshStatus.SUCCEEDED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                elapsed_seconds=perf_counter() - started,
                result=result,
            )
        except Exception:
            snapshot = BackgroundRefreshSnapshot(
                key=key,
                token=token,
                status=BackgroundRefreshStatus.FAILED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                elapsed_seconds=perf_counter() - started,
                error_message=(
                    "Jobs could not be refreshed. Previously stored recommendations "
                    "remain available."
                ),
            )
        with self._lock:
            current = self._snapshots.get(key)
            if current is not None and current.token == token:
                self._snapshots[key] = snapshot


def refresh_context_key(
    profile_id: str,
    feed_kind: str,
    *,
    sector: str | None = None,
) -> str:
    return ":".join((profile_id, feed_kind, sector or ""))


__all__ = [
    "BackgroundJobsRefreshCoordinator",
    "BackgroundRefreshSnapshot",
    "BackgroundRefreshStatus",
    "refresh_context_key",
]
