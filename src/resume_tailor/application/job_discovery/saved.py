from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from resume_tailor.domain.job_discovery.ids import saved_job_id
from resume_tailor.domain.job_discovery.models import (
    ConnectorType,
    SavedJob,
    SavedJobAvailability,
    SupportedJobSource,
    VerificationResult,
    VerificationStatus,
)
from resume_tailor.ports.job_discovery import (
    DiscoveredJobRepository,
    JobSourceAvailabilityChecker,
    JobSourceEnvelopeError,
    JobSourceTransportError,
    SavedJobRepository,
    SupportedJobSourceRepository,
)


class DiscoveredJobNotFoundError(LookupError):
    """Raised when a caller tries to save an unknown discovered job."""


class SavedJobNotFoundError(LookupError):
    """Raised when a saved job is absent or belongs to another user."""


CheckerCollection = Mapping[
    ConnectorType,
    JobSourceAvailabilityChecker | Mapping[str, JobSourceAvailabilityChecker],
]


class SaveJobService:
    def __init__(
        self,
        jobs: DiscoveredJobRepository,
        saved_jobs: SavedJobRepository,
    ) -> None:
        self._jobs = jobs
        self._saved_jobs = saved_jobs

    def save(self, user_id: str, job_id: str, *, saved_at: datetime) -> SavedJob:
        identifier = saved_job_id(user_id, job_id)
        existing = self._saved_jobs.get(user_id, identifier)
        if existing is not None:
            return existing.model_copy(deep=True)

        job = self._jobs.get(job_id)
        if job is None:
            raise DiscoveredJobNotFoundError(f"Discovered job {job_id!r} was not found.")

        snapshot = job.model_copy(deep=True)
        saved = SavedJob(
            id=identifier,
            user_id=user_id,
            job_id=job_id,
            availability=SavedJobAvailability.UNKNOWN,
            saved_at=saved_at,
            posting_snapshot=snapshot,
        )
        self._saved_jobs.save(saved.model_copy(deep=True))
        return saved.model_copy(deep=True)

    def list(self, user_id: str) -> list[SavedJob]:
        return [saved.model_copy(deep=True) for saved in self._saved_jobs.list(user_id)]


class CheckSavedJobAvailabilityService:
    def __init__(
        self,
        saved_jobs: SavedJobRepository,
        sources: SupportedJobSourceRepository,
        checkers: CheckerCollection,
    ) -> None:
        self._saved_jobs = saved_jobs
        self._sources = sources
        self._checkers = checkers

    def check(self, user_id: str, saved_id: str, *, checked_at: datetime) -> SavedJob:
        saved = self._saved_jobs.get(user_id, saved_id)
        if saved is None:
            raise SavedJobNotFoundError(f"Saved job {saved_id!r} was not found.")

        availability = SavedJobAvailability.UNKNOWN
        source = self._configured_source(saved.posting_snapshot.source)
        checker = self._checker_for(source) if source is not None else None
        if checker is not None and source is not None:
            try:
                result = checker.check(source, saved.posting_snapshot.external_job_id)
            except (
                JobSourceEnvelopeError,
                JobSourceTransportError,
                OSError,
                TimeoutError,
                ValueError,
            ):
                # Known provider-boundary failures cannot prove that a posting is gone.
                result = None
            availability = _availability_from_result(result)

        self._saved_jobs.update_availability(saved.id, availability, checked_at)
        return saved.model_copy(
            update={"availability": availability, "checked_at": checked_at},
            deep=True,
        )

    def _configured_source(self, snapshot_source: SupportedJobSource) -> SupportedJobSource | None:
        for source in self._sources.list_enabled():
            if (
                source.source_id == snapshot_source.source_id
                and source.connector_type is snapshot_source.connector_type
            ):
                return source.model_copy(deep=True)
        return None

    def _checker_for(
        self, source: SupportedJobSource
    ) -> JobSourceAvailabilityChecker | None:
        configured = self._checkers.get(source.connector_type)
        if configured is None:
            return None
        if isinstance(configured, Mapping):
            return configured.get(source.source_id)
        return configured


def _availability_from_result(result: VerificationResult | None) -> SavedJobAvailability:
    if result is None:
        return SavedJobAvailability.UNKNOWN
    if result.status is VerificationStatus.VERIFIED_ACTIVE:
        return SavedJobAvailability.AVAILABLE
    if result.status in {VerificationStatus.UNAVAILABLE, VerificationStatus.EXPIRED}:
        return SavedJobAvailability.UNAVAILABLE
    return SavedJobAvailability.UNKNOWN


__all__ = [
    "CheckSavedJobAvailabilityService",
    "DiscoveredJobNotFoundError",
    "SaveJobService",
    "SavedJobNotFoundError",
]
