from __future__ import annotations

from datetime import datetime
from typing import Protocol

from resume_tailor.domain.job_discovery.models import (
    DiscoveredJob,
    DiscoveryRun,
    JobRecommendation,
    JobSearchPreferences,
    JobSourceFetchResult,
    SavedJob,
    SavedJobAvailability,
    SupportedJobSource,
    VerificationResult,
)


class JobSourceEnvelopeError(Exception):
    """A source returned a successful response with an invalid envelope."""


class JobSourceTransportError(Exception):
    """A source could not be reached or returned an unexpected status."""


class JobSourceRateLimitedError(JobSourceTransportError):
    """A source rejected the request because of rate limiting."""


class JobSourceAuthenticationError(JobSourceTransportError):
    """A source rejected the request for authentication or access reasons."""


class JobSourceNotFoundError(JobSourceTransportError):
    """A source reported that a requested resource was absent."""


class PreferenceVersionConflictError(ValueError):
    """A confirmed preference version already contains different data."""


class JobSourceConnector(Protocol):
    def fetch(
        self, source: SupportedJobSource, *, fetched_at: datetime
    ) -> JobSourceFetchResult: ...


class JobSourceAvailabilityChecker(Protocol):
    def check(
        self,
        source: SupportedJobSource,
        external_job_id: str,
    ) -> VerificationResult: ...


class JobSearchPreferencesRepository(Protocol):
    def get_current(self, user_id: str, profile_id: str) -> JobSearchPreferences | None: ...

    def save_confirmed(self, preferences: JobSearchPreferences) -> None: ...


class DiscoveredJobRepository(Protocol):
    def upsert(self, job: DiscoveredJob) -> None: ...

    def get(self, job_id: str) -> DiscoveredJob | None: ...


class JobRecommendationRepository(Protocol):
    def replace_for_run(
        self, run_id: str, recommendations: list[JobRecommendation]
    ) -> None: ...

    def list_for_run(self, run_id: str) -> list[JobRecommendation]: ...


class SavedJobRepository(Protocol):
    def save(self, saved: SavedJob) -> None: ...

    def get(self, user_id: str, saved_id: str) -> SavedJob | None: ...

    def list(self, user_id: str) -> list[SavedJob]: ...

    def update_availability(
        self,
        saved_id: str,
        availability: SavedJobAvailability,
        checked_at: datetime,
    ) -> None: ...


class DiscoveryRunRepository(Protocol):
    def create(self, run: DiscoveryRun) -> None: ...

    def complete(self, run: DiscoveryRun) -> None: ...

    def get(self, run_id: str) -> DiscoveryRun | None: ...


class SupportedJobSourceRepository(Protocol):
    def list_enabled(self) -> list[SupportedJobSource]: ...


__all__ = [
    "DiscoveredJobRepository",
    "DiscoveryRunRepository",
    "JobSourceAuthenticationError",
    "JobSourceAvailabilityChecker",
    "JobSourceConnector",
    "JobSourceEnvelopeError",
    "JobSourceNotFoundError",
    "PreferenceVersionConflictError",
    "JobSourceRateLimitedError",
    "JobSourceTransportError",
    "JobRecommendationRepository",
    "JobSearchPreferencesRepository",
    "SavedJobRepository",
    "SupportedJobSourceRepository",
]
