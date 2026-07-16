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
        current = self._preferences.get_current(preferences.user_id, preferences.profile_id)
        if current is not None and _confirmation_payload(
            current
        ) == _confirmation_payload(preferences):
            return current.model_copy(deep=True)

        next_version = 1 if current is None else current.version + 1
        confirmed = preferences.model_copy(update={"version": next_version})
        self._preferences.save_confirmed(confirmed)
        return confirmed


def _confirmation_payload(preferences: JobSearchPreferences) -> dict[str, object]:
    """Return the user-controlled content used to identify a reconfirmation."""

    payload = preferences.model_dump(mode="python")
    payload.pop("version", None)
    payload.pop("created_at", None)
    payload.pop("confirmed_at", None)
    return payload


__all__ = ["ConfirmJobSearchPreferencesService"]
