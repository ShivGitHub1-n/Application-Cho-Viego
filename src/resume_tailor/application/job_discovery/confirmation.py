from __future__ import annotations

from resume_tailor.application.job_discovery.preferences import ProfileNotFoundError
from resume_tailor.domain.job_discovery.models import JobSearchPreferences
from resume_tailor.ports.interfaces import MasterProfileRepository
from resume_tailor.ports.job_discovery import JobSearchPreferencesRepository


class ConfirmJobSearchPreferencesService:
    def __init__(
        self,
        profiles: MasterProfileRepository,
        preferences: JobSearchPreferencesRepository,
    ) -> None:
        self._profiles = profiles
        self._preferences = preferences

    def confirm(self, preferences: JobSearchPreferences) -> JobSearchPreferences:
        profile = self._profiles.get(preferences.profile_id)
        if profile is None or profile.user_id != preferences.user_id:
            raise ProfileNotFoundError(
                f"Profile {preferences.profile_id!r} was not found for user "
                f"{preferences.user_id!r}."
            )
        self._preferences.save_confirmed(preferences)
        return preferences


__all__ = ["ConfirmJobSearchPreferencesService"]
