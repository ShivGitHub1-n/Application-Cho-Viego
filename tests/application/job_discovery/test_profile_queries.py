from __future__ import annotations

from pathlib import Path

from resume_tailor.application.job_discovery.profile_queries import (
    ReviewedProfileQueryService,
)
from resume_tailor.domain.models import MasterProfile
from resume_tailor.infrastructure.profile_repository import SQLiteMasterProfileRepository


def _profile(profile_id: str, display_name: str) -> MasterProfile:
    return MasterProfile(id=profile_id, user_id="local-user", display_name=display_name)


def test_reviewed_profiles_prefer_display_name_and_return_stable_ids(tmp_path: Path) -> None:
    repository = SQLiteMasterProfileRepository(tmp_path / "profiles.sqlite")
    repository.save(_profile("profile-2", "Second Candidate"))
    repository.save(_profile("profile-1", "First Candidate"))

    result = ReviewedProfileQueryService(repository).list_reviewed_profiles()

    assert [item.profile_id for item in result.profiles] == ["profile-1", "profile-2"]
    assert [item.label for item in result.profiles] == [
        "First Candidate",
        "Second Candidate",
    ]


def test_empty_profile_repository_returns_intentional_empty_state(tmp_path: Path) -> None:
    repository = SQLiteMasterProfileRepository(tmp_path / "profiles.sqlite")

    result = ReviewedProfileQueryService(repository).list_reviewed_profiles()

    assert result.profiles == []
    assert result.empty_message == "A reviewed profile is required before discovering jobs."


def test_corrupt_profile_storage_returns_safe_warning(tmp_path: Path) -> None:
    repository = SQLiteMasterProfileRepository(tmp_path / "profiles.sqlite")
    repository.save(_profile("profile-1", "Candidate"))
    repository._database_path.write_bytes(b"not a sqlite database")

    result = ReviewedProfileQueryService(repository).list_reviewed_profiles()

    assert result.profiles == []
    assert result.warning == "Reviewed profiles are temporarily unavailable."
