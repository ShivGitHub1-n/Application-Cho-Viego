import sqlite3

import pytest

from resume_tailor.domain.models import ContactHyperlink, ContactInfo, MasterProfile
from resume_tailor.infrastructure.profile_repository import (
    CorruptStoredProfileError,
    SQLiteMasterProfileRepository,
)


def _profile(profile_id: str = "profile-1", display_name: str = "Candidate") -> MasterProfile:
    return MasterProfile(
        id=profile_id,
        user_id="local-user",
        display_name=display_name,
        experiences=[{"id": "entry-1", "title": "Engineer", "kind": "experience"}],
        evidence=[{"id": "evidence-1", "entity_id": "entry-1", "source_text": "Built tools."}],
    )


def test_profile_round_trips_and_replaces_across_store_instances(tmp_path) -> None:
    database = tmp_path / "profiles.sqlite3"
    first = SQLiteMasterProfileRepository(database)
    first.save(_profile())
    assert SQLiteMasterProfileRepository(database).get("profile-1") == _profile()

    first.save(_profile(display_name="Updated Candidate"))
    loaded = SQLiteMasterProfileRepository(database).get("profile-1")
    assert loaded is not None
    assert loaded.display_name == "Updated Candidate"


def test_missing_profile_returns_none(tmp_path) -> None:
    assert SQLiteMasterProfileRepository(tmp_path / "profiles.sqlite3").get("missing") is None


def test_profile_hyperlink_semantics_round_trip_through_persistence(tmp_path) -> None:
    profile = _profile().model_copy(
        update={
            "contact": ContactInfo(
                links=[
                    "https://code.example.test/candidate",
                    "https://portfolio.example.test/work",
                ],
                hyperlinks=[
                    ContactHyperlink(
                        display_text="Code",
                        destination="https://code.example.test/candidate",
                    ),
                    ContactHyperlink(
                        display_text="Selected work",
                        destination="https://portfolio.example.test/work",
                    ),
                ],
            )
        }
    )
    database = tmp_path / "hyperlinks.sqlite3"

    SQLiteMasterProfileRepository(database).save(profile)
    loaded = SQLiteMasterProfileRepository(database).get(profile.id)

    assert loaded is not None
    assert loaded.contact == profile.contact


def test_corrupt_or_schema_invalid_profile_is_reported(tmp_path) -> None:
    database = tmp_path / "profiles.sqlite3"
    repository = SQLiteMasterProfileRepository(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO master_profiles(profile_id, schema_version, payload) VALUES (?, ?, ?)",
            ("broken", 1, "{not-json"),
        )
    with pytest.raises(CorruptStoredProfileError):
        repository.get("broken")

    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO master_profiles(profile_id, schema_version, payload) VALUES (?, ?, ?)",
            ("invalid", 1, '{"id":"invalid"}'),
        )
    with pytest.raises(CorruptStoredProfileError):
        repository.get("invalid")
