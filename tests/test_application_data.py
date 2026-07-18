from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from resume_tailor.domain.job_discovery.models import (
    JobLevel,
    JobSearchPreferences,
    NormalizedLocation,
    WorkArrangement,
    WorkArrangementPreferenceMode,
)
from resume_tailor.domain.models import MasterProfile, RoleFamily
from resume_tailor.infrastructure.application_data import (
    APPLICATION_DATA_DIRECTORY_NAME,
    application_database_path,
    default_application_data_directory,
    migrate_legacy_application_database,
)
from resume_tailor.infrastructure.config import Settings
from resume_tailor.infrastructure.dependencies import create_profile_repository
from resume_tailor.infrastructure.job_discovery_sqlite import (
    SQLiteJobSearchPreferencesRepository,
)
from resume_tailor.infrastructure.profile_repository import SQLiteMasterProfileRepository


def _profile(
    profile_id: str = "shiv-arora-master-v1",
    display_name: str = "Reviewed Candidate",
) -> MasterProfile:
    return MasterProfile(
        id=profile_id,
        user_id="local-user",
        display_name=display_name,
        experiences=[
            {
                "id": "experience-1",
                "title": "Engineer",
                "kind": "experience",
            }
        ],
        evidence=[
            {
                "id": "evidence-1",
                "entity_id": "experience-1",
                "source_text": "Built verified systems.",
            }
        ],
    )


def test_default_application_data_directory_is_not_repository_relative(
    monkeypatch,
    tmp_path: Path,
) -> None:
    local_app_data = tmp_path / "user-local-data"
    first_repository = tmp_path / "clone-one"
    second_repository = tmp_path / "worktree-two"
    first_repository.mkdir()
    second_repository.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.delenv("APPLICATION_VIEGO_DATA_DIR", raising=False)
    monkeypatch.delenv("APP_DATA_DIRECTORY", raising=False)

    monkeypatch.chdir(first_repository)
    first = Settings(_env_file=None).app_data_directory
    monkeypatch.chdir(second_repository)
    second = Settings(_env_file=None).app_data_directory

    expected = local_app_data / APPLICATION_DATA_DIRECTORY_NAME
    assert first == expected
    assert second == expected
    assert first_repository not in first.parents
    assert second_repository not in second.parents
    assert default_application_data_directory() == expected


def test_application_data_environment_override_supports_portable_use(
    monkeypatch,
    tmp_path: Path,
) -> None:
    override = tmp_path / "portable-data"
    monkeypatch.setenv("APPLICATION_VIEGO_DATA_DIR", str(override))

    settings = Settings(_env_file=None)

    assert settings.app_data_directory == override
    assert (
        application_database_path(
            settings.app_data_directory,
            settings.profile_store_filename,
        )
        == (override / "resume_tailor.sqlite3").resolve()
    )


def test_saved_profile_loads_from_another_repository_path_with_shared_data_directory(
    monkeypatch,
    tmp_path: Path,
) -> None:
    settings = Settings(
        _env_file=None,
        app_data_directory=tmp_path / "canonical-data",
    )
    first_repository = tmp_path / "clone-one"
    second_repository = tmp_path / "worktree-two"
    first_repository.mkdir()
    second_repository.mkdir()

    monkeypatch.chdir(first_repository)
    create_profile_repository(settings).save(_profile())
    monkeypatch.chdir(second_repository)
    loaded = create_profile_repository(settings).get("shiv-arora-master-v1")

    assert loaded == _profile()


def test_job_search_state_loads_from_another_repository_path(
    monkeypatch,
    tmp_path: Path,
) -> None:
    settings = Settings(
        _env_file=None,
        app_data_directory=tmp_path / "canonical-data",
    )
    database = application_database_path(
        settings.app_data_directory,
        settings.profile_store_filename,
    )
    first_repository = tmp_path / "clone-one"
    second_repository = tmp_path / "worktree-two"
    first_repository.mkdir()
    second_repository.mkdir()
    preferences = JobSearchPreferences(
        user_id="local-user",
        profile_id="shiv-arora-master-v1",
        version=1,
        role_family_priority=[RoleFamily.ROBOTICS_MECHATRONICS],
        target_titles=["Robotics Engineer"],
        related_title_variants=[],
        technical_themes=["robotics"],
        career_interests=["autonomous systems"],
        job_levels=[JobLevel.INTERN],
        locations=[NormalizedLocation(raw="Toronto, Ontario, Canada", parseable=True)],
        work_arrangement=WorkArrangement.UNKNOWN,
        work_arrangement_mode=WorkArrangementPreferenceMode.PREFERRED,
        preferred_companies=[],
        created_at=datetime(2026, 7, 17, tzinfo=UTC),
        confirmed_at=datetime(2026, 7, 17, tzinfo=UTC),
    )

    monkeypatch.chdir(first_repository)
    SQLiteJobSearchPreferencesRepository(database).save_confirmed(preferences)
    monkeypatch.chdir(second_repository)
    loaded = SQLiteJobSearchPreferencesRepository(database).get_current(
        "local-user",
        "shiv-arora-master-v1",
    )

    assert loaded == preferences


def test_repository_local_profile_migration_is_allowlisted_and_non_destructive(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "legacy-clone"
    legacy_database = repository_root / "data" / "resume_tailor.sqlite3"
    legacy = SQLiteMasterProfileRepository(legacy_database)
    legacy.save(_profile())
    legacy.save(_profile(profile_id="legacy-only"))
    unrelated = repository_root / "data" / "credentials.txt"
    unrelated.write_text("must-not-be-copied", encoding="utf-8")
    canonical_directory = tmp_path / "canonical-data"
    settings = Settings(_env_file=None, app_data_directory=canonical_directory)
    canonical_database = canonical_directory / settings.profile_store_filename
    canonical = SQLiteMasterProfileRepository(canonical_database)
    canonical.save(_profile(display_name="Canonical Review Wins"))

    migrated = create_profile_repository(
        settings,
        legacy_repository_root=repository_root,
    )

    loaded = migrated.get("shiv-arora-master-v1")
    assert loaded is not None
    assert loaded.display_name == "Canonical Review Wins"
    assert migrated.get("legacy-only") == _profile(profile_id="legacy-only")
    assert legacy.get("shiv-arora-master-v1") == _profile()
    assert not (canonical_directory / unrelated.name).exists()
    assert migrated.migration_report is not None
    assert migrated.migration_report.source_database == legacy_database.resolve()
    assert migrated.migration_report.imported_rows["master_profiles"] == 1


def test_repository_local_job_search_state_migrates_by_known_table(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "legacy-clone"
    source_database = repository_root / "data" / "resume_tailor.sqlite3"
    destination_database = tmp_path / "canonical-data" / "resume_tailor.sqlite3"
    created_at = datetime(2026, 7, 17, tzinfo=UTC)
    preferences = JobSearchPreferences(
        user_id="local-user",
        profile_id="shiv-arora-master-v1",
        version=1,
        role_family_priority=[RoleFamily.ROBOTICS_MECHATRONICS],
        target_titles=["Robotics Engineer"],
        related_title_variants=[],
        technical_themes=[],
        career_interests=[],
        job_levels=[JobLevel.INTERN],
        locations=[],
        work_arrangement=WorkArrangement.UNKNOWN,
        preferred_companies=[],
        created_at=created_at,
        confirmed_at=created_at,
    )
    SQLiteJobSearchPreferencesRepository(source_database).save_confirmed(preferences)
    destination = SQLiteJobSearchPreferencesRepository(destination_database)

    report = migrate_legacy_application_database(
        source_database,
        destination_database,
    )

    assert destination.get_current("local-user", "shiv-arora-master-v1") == preferences
    assert report.imported_rows["job_search_preferences"] == 1
