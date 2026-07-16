from datetime import UTC, datetime

from resume_tailor.application.job_discovery.confirmation import (
    ConfirmJobSearchPreferencesService,
)
from resume_tailor.domain.job_discovery.models import JobSearchPreferences, WorkArrangement
from resume_tailor.domain.models import MasterProfile, RoleFamily
from resume_tailor.infrastructure.job_discovery_sqlite import SQLiteJobSearchPreferencesRepository

WHEN = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


class Profiles:
    def get(self, profile_id: str):
        return MasterProfile(id=profile_id, user_id="user-1", display_name="Candidate")


def preferences(**updates) -> JobSearchPreferences:
    value = JobSearchPreferences(
        user_id="user-1",
        profile_id="profile-1",
        version=1,
        role_family_priority=[RoleFamily.SOFTWARE_DATA_ENGINEERING],
        target_titles=["Software Engineer"],
        related_title_variants=[],
        technical_themes=[],
        career_interests=[],
        job_levels=[],
        locations=[],
        work_arrangement=WorkArrangement.UNKNOWN,
        preferred_companies=[],
        created_at=WHEN,
        confirmed_at=WHEN,
    )
    return value.model_copy(update=updates)


def test_confirmation_is_idempotent_and_allocates_from_persisted_latest(tmp_path):
    repository = SQLiteJobSearchPreferencesRepository(tmp_path / "preferences.sqlite3")
    service = ConfirmJobSearchPreferencesService(Profiles(), repository)

    first = service.confirm(preferences())
    same = service.confirm(preferences(version=1, created_at=WHEN.replace(hour=13)))
    second = service.confirm(preferences(target_titles=["Backend Engineer"]))
    third = service.confirm(preferences(target_titles=["Data Engineer"]))

    assert first.version == 1
    assert same.version == 1
    assert second.version == 2
    assert third.version == 3

    recreated = SQLiteJobSearchPreferencesRepository(tmp_path / "preferences.sqlite3")
    assert recreated.get_current("user-1", "profile-1").version == 3
