from __future__ import annotations

from dataclasses import dataclass

from resume_tailor.domain.job_discovery.models import (
    DiscoveryRun,
    JobRecommendation,
    JobSearchPreferences,
)
from resume_tailor.ports.job_discovery import (
    DiscoveryRunRepository,
    JobRecommendationRepository,
    JobSearchPreferencesRepository,
)


class PreferencesNotFoundError(ValueError):
    pass


class DiscoveryRunNotFoundError(ValueError):
    pass


class GetCurrentJobSearchPreferencesService:
    def __init__(self, preferences: JobSearchPreferencesRepository) -> None:
        self._preferences = preferences

    def get(self, user_id: str, profile_id: str) -> JobSearchPreferences:
        preferences = self._preferences.get_current(user_id, profile_id)
        if preferences is None:
            raise PreferencesNotFoundError(
                f"Preferences for profile {profile_id!r} were not found."
            )
        return preferences


@dataclass(frozen=True)
class DiscoveryRunDetails:
    run: DiscoveryRun
    recommendations: list[JobRecommendation]


class GetDiscoveryRunService:
    def __init__(
        self,
        runs: DiscoveryRunRepository,
        recommendations: JobRecommendationRepository,
    ) -> None:
        self._runs = runs
        self._recommendations = recommendations

    def get(self, run_id: str) -> DiscoveryRunDetails:
        run = self._runs.get(run_id)
        if run is None:
            raise DiscoveryRunNotFoundError(f"Discovery run {run_id!r} was not found.")
        return DiscoveryRunDetails(
            run=run,
            recommendations=self._recommendations.list_for_run(run_id),
        )


__all__ = [
    "DiscoveryRunDetails",
    "DiscoveryRunNotFoundError",
    "GetCurrentJobSearchPreferencesService",
    "GetDiscoveryRunService",
    "PreferencesNotFoundError",
]
