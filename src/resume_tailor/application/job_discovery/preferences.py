from __future__ import annotations

from datetime import datetime

from resume_tailor.domain.job_discovery.models import JobSearchPreferenceSuggestion
from resume_tailor.domain.job_discovery.preferences import DeterministicJobSearchPreferenceSuggester
from resume_tailor.ports.interfaces import MasterProfileRepository


class ProfileNotFoundError(ValueError):
    pass


class SuggestJobSearchPreferencesService:
    def __init__(
        self,
        profiles: MasterProfileRepository,
        suggester: DeterministicJobSearchPreferenceSuggester,
    ) -> None:
        self._profiles = profiles
        self._suggester = suggester

    def suggest(
        self,
        user_id: str,
        profile_id: str,
        *,
        generated_at: datetime,
    ) -> JobSearchPreferenceSuggestion:
        profile = self._profiles.get(profile_id)
        if profile is None or profile.user_id != user_id:
            raise ProfileNotFoundError(
                f"Profile {profile_id!r} was not found for user {user_id!r}."
            )
        return self._suggester.suggest(profile, generated_at=generated_at)
