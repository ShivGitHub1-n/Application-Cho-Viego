from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from pydantic import ValidationError

from resume_tailor.domain.models import MasterProfile
from resume_tailor.ports.interfaces import MasterProfileRepository


class ProfileStoreError(RuntimeError):
    """Base error for local profile storage failures."""


class CorruptStoredProfileError(ProfileStoreError):
    """Raised when a stored profile cannot be validated against the domain schema."""


class SQLiteMasterProfileRepository(MasterProfileRepository):
    """Single-process local profile store with a replace-by-profile-ID contract."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with sqlite3.connect(self._database_path) as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS master_profiles (
                        profile_id TEXT PRIMARY KEY,
                        schema_version INTEGER NOT NULL,
                        payload TEXT NOT NULL,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
        except sqlite3.Error as error:
            raise ProfileStoreError(f"Unable to initialize profile storage: {error}") from error

    def get(self, profile_id: str) -> MasterProfile | None:
        if not profile_id.strip():
            raise ValueError("Profile ID must not be empty")
        try:
            with sqlite3.connect(self._database_path) as connection:
                row = connection.execute(
                    "SELECT payload FROM master_profiles WHERE profile_id = ?",
                    (profile_id,),
                ).fetchone()
        except sqlite3.Error as error:
            raise ProfileStoreError(f"Unable to load profile: {error}") from error
        if row is None:
            return None
        try:
            payload = json.loads(row[0])
            profile = MasterProfile.model_validate(payload)
        except (json.JSONDecodeError, TypeError, ValidationError, ValueError) as error:
            raise CorruptStoredProfileError(
                f"Stored profile {profile_id!r} is invalid or incompatible"
            ) from error
        if profile.id != profile_id:
            raise CorruptStoredProfileError(
                f"Stored profile ID {profile.id!r} does not match requested ID {profile_id!r}"
            )
        return profile

    def save(self, profile: MasterProfile) -> None:
        validated = MasterProfile.model_validate(profile.model_dump(mode="json"))
        try:
            with sqlite3.connect(self._database_path) as connection:
                connection.execute(
                    """
                    INSERT INTO master_profiles(profile_id, schema_version, payload)
                    VALUES (?, ?, ?)
                    ON CONFLICT(profile_id) DO UPDATE SET
                        schema_version = excluded.schema_version,
                        payload = excluded.payload,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        validated.id,
                        1,
                        json.dumps(validated.model_dump(mode="json"), separators=(",", ":")),
                    ),
                )
        except sqlite3.Error as error:
            raise ProfileStoreError(f"Unable to save profile: {error}") from error
