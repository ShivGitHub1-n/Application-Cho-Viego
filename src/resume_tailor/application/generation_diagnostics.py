from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from time import perf_counter

from resume_tailor.domain.generated_artifact import (
    GenerationCallCounts,
    GenerationStage,
    StageStatus,
    StageTiming,
)

Clock = Callable[[], float]
StageCallback = Callable[[GenerationStage], None]

_STAGE_ORDER = {stage: index for index, stage in enumerate(GenerationStage)}


@dataclass(frozen=True)
class GenerationTelemetrySnapshot:
    """Point-in-time marker used to isolate one artifact build."""

    event_count: int
    call_counts: GenerationCallCounts


class GenerationTelemetry:
    """Collect typed timings and exact execution counts without delivery dependencies."""

    def __init__(self, clock: Clock = perf_counter) -> None:
        self._clock = clock
        self._timings: dict[GenerationStage, StageTiming] = {}
        self._events: list[StageTiming] = []
        self._counts = GenerationCallCounts()
        self._stage_callback: StageCallback | None = None

    @property
    def clock(self) -> Clock:
        return self._clock

    def reset(self) -> None:
        self._timings.clear()
        self._events.clear()
        self._counts = GenerationCallCounts()

    def set_stage_callback(self, callback: StageCallback | None) -> None:
        self._stage_callback = callback

    @contextmanager
    def measure(
        self,
        stage: GenerationStage,
        *,
        detail: str | None = None,
    ) -> Iterator[None]:
        if self._stage_callback is not None:
            self._stage_callback(stage)
        started = self._clock()
        try:
            yield
        except Exception:
            self.record(
                stage,
                self._clock() - started,
                status=StageStatus.FAILED,
                detail=detail,
            )
            raise
        self.record(stage, self._clock() - started, detail=detail)

    def record(
        self,
        stage: GenerationStage,
        elapsed_seconds: float,
        *,
        status: StageStatus = StageStatus.COMPLETED,
        detail: str | None = None,
    ) -> None:
        elapsed = max(0.0, elapsed_seconds)
        previous = self._timings.get(stage)
        self._timings[stage] = StageTiming(
            stage=stage,
            elapsed_seconds=elapsed + (previous.elapsed_seconds if previous else 0.0),
            invocation_count=1 + (previous.invocation_count if previous else 0),
            status=(
                StageStatus.FAILED
                if status is StageStatus.FAILED
                or (previous is not None and previous.status is StageStatus.FAILED)
                else status
            ),
            detail=detail or (previous.detail if previous else None),
        )
        self._events.append(
            StageTiming(
                stage=stage,
                elapsed_seconds=elapsed,
                invocation_count=1,
                status=status,
                detail=detail,
            )
        )

    def skip(self, stage: GenerationStage, detail: str) -> None:
        if stage not in self._timings:
            self._timings[stage] = StageTiming(
                stage=stage,
                elapsed_seconds=0,
                invocation_count=0,
                status=StageStatus.SKIPPED,
                detail=detail,
            )

    def increment(self, field_name: str, amount: int = 1) -> None:
        current = self._counts.model_dump()
        if field_name not in current:
            raise ValueError(f"Unknown generation call-count field: {field_name}")
        current[field_name] += amount
        self._counts = GenerationCallCounts.model_validate(current)

    def timings(self, *, include_missing: bool = True) -> list[StageTiming]:
        values = dict(self._timings)
        if include_missing:
            for stage in GenerationStage:
                values.setdefault(
                    stage,
                    StageTiming(
                        stage=stage,
                        elapsed_seconds=0,
                        invocation_count=0,
                        status=StageStatus.SKIPPED,
                        detail="Stage did not execute for this generation.",
                    ),
                )
        return sorted(values.values(), key=lambda item: _STAGE_ORDER[item.stage])

    def call_counts(self) -> GenerationCallCounts:
        return self._counts.model_copy(deep=True)

    def snapshot(self) -> GenerationTelemetrySnapshot:
        return GenerationTelemetrySnapshot(
            event_count=len(self._events),
            call_counts=self.call_counts(),
        )

    def call_counts_since(
        self,
        snapshot: GenerationTelemetrySnapshot,
    ) -> GenerationCallCounts:
        current = self._counts.model_dump()
        previous = snapshot.call_counts.model_dump()
        return GenerationCallCounts.model_validate(
            {name: max(0, value - previous[name]) for name, value in current.items()}
        )

    def timings_since(
        self,
        snapshot: GenerationTelemetrySnapshot,
        *,
        include_missing: bool = True,
    ) -> list[StageTiming]:
        timings: dict[GenerationStage, StageTiming] = {}
        for event in self._events[snapshot.event_count :]:
            previous = timings.get(event.stage)
            timings[event.stage] = StageTiming(
                stage=event.stage,
                elapsed_seconds=event.elapsed_seconds
                + (previous.elapsed_seconds if previous else 0.0),
                invocation_count=event.invocation_count
                + (previous.invocation_count if previous else 0),
                status=(
                    StageStatus.FAILED
                    if event.status is StageStatus.FAILED
                    or (previous is not None and previous.status is StageStatus.FAILED)
                    else event.status
                ),
                detail=event.detail or (previous.detail if previous else None),
            )
        if include_missing:
            for stage in GenerationStage:
                timings.setdefault(
                    stage,
                    StageTiming(
                        stage=stage,
                        elapsed_seconds=0,
                        invocation_count=0,
                        status=StageStatus.SKIPPED,
                        detail="Stage did not execute for this artifact build.",
                    ),
                )
        return sorted(timings.values(), key=lambda item: _STAGE_ORDER[item.stage])

    def elapsed_since(
        self,
        stage: GenerationStage,
        snapshot: GenerationTelemetrySnapshot,
    ) -> float:
        return sum(
            event.elapsed_seconds
            for event in self._events[snapshot.event_count :]
            if event.stage is stage
        )

    def elapsed(self, stage: GenerationStage) -> float:
        timing = self._timings.get(stage)
        return timing.elapsed_seconds if timing is not None else 0.0


__all__ = [
    "Clock",
    "GenerationTelemetry",
    "GenerationTelemetrySnapshot",
    "StageCallback",
]
