from datetime import UTC, datetime

import pytest

from resume_tailor.application.job_discovery.preferences import (
    ProfileNotFoundError,
    SuggestJobSearchPreferencesService,
)
from resume_tailor.domain.job_discovery.models import JobSearchPreferenceSuggestion
from resume_tailor.domain.job_discovery.preferences import DeterministicJobSearchPreferenceSuggester
from resume_tailor.domain.models import MasterProfile

WHEN = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


def _profile(*, user_id: str = "user-1") -> MasterProfile:
    return MasterProfile(
        id="profile-1",
        user_id=user_id,
        display_name="Candidate",
        experiences=[{"id": "entry-1", "title": "Software Engineer", "kind": "experience"}],
        evidence=[
            {
                "id": "evidence-1",
                "entity_id": "entry-1",
                "source_text": "Built software systems.",
                "confirmed": True,
            }
        ],
    )


class SpyProfileRepository:
    def __init__(self, profile: MasterProfile | None) -> None:
        self.profile = profile
        self.save_calls = 0

    def get(self, profile_id: str) -> MasterProfile | None:
        if self.profile is not None and self.profile.id == profile_id:
            return self.profile
        return None

    def save(self, profile: MasterProfile) -> None:
        self.save_calls += 1


class SpySuggester:
    def __init__(self) -> None:
        self.calls: list[tuple[MasterProfile, datetime]] = []
        self._delegate = DeterministicJobSearchPreferenceSuggester()

    def suggest(
        self,
        profile: MasterProfile,
        *,
        generated_at: datetime,
    ) -> JobSearchPreferenceSuggestion:
        self.calls.append((profile, generated_at))
        return self._delegate.suggest(profile, generated_at=generated_at)


def test_suggestion_service_verifies_owner_and_does_not_persist():
    repository = SpyProfileRepository(_profile())
    service = SuggestJobSearchPreferencesService(
        repository,
        DeterministicJobSearchPreferenceSuggester(),
    )

    suggestion = service.suggest("user-1", "profile-1", generated_at=WHEN)

    assert suggestion.profile_id == "profile-1"
    assert repository.save_calls == 0


def test_suggestion_service_rejects_owner_mismatch():
    repository = SpyProfileRepository(_profile(user_id="owner-1"))
    service = SuggestJobSearchPreferencesService(
        repository,
        DeterministicJobSearchPreferenceSuggester(),
    )

    with pytest.raises(ProfileNotFoundError):
        service.suggest("different-user", "profile-1", generated_at=WHEN)


def test_suggestion_service_reports_missing_profile():
    service = SuggestJobSearchPreferencesService(
        SpyProfileRepository(None),
        DeterministicJobSearchPreferenceSuggester(),
    )

    with pytest.raises(ProfileNotFoundError):
        service.suggest("user-1", "missing", generated_at=WHEN)


def test_suggestion_service_delegates_loaded_profile_to_injected_suggester():
    profile = _profile()
    repository = SpyProfileRepository(profile)
    suggester = SpySuggester()
    service = SuggestJobSearchPreferencesService(repository, suggester)

    service.suggest("user-1", "profile-1", generated_at=WHEN)

    assert suggester.calls == [(profile, WHEN)]
    assert repository.save_calls == 0
