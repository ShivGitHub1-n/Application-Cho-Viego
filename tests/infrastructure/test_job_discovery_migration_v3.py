# ruff: noqa: E501

import sqlite3

from resume_tailor.infrastructure.job_discovery_migrations import initialize_job_discovery_database


def test_fresh_database_contains_runtime_state_aliases_and_locks(tmp_path) -> None:
    path = tmp_path / "jobs.sqlite3"
    initialize_job_discovery_database(path)
    with sqlite3.connect(path) as migrated:
        assert migrated.execute("PRAGMA user_version").fetchone()[0] == 3
        tables = {
            row[0] for row in migrated.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {"source_runtime_state", "job_identity_aliases", "refresh_locks"} <= tables


def test_alias_identity_is_unique_by_source_kind_and_value(tmp_path) -> None:
    path = tmp_path / "jobs.sqlite3"
    initialize_job_discovery_database(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO job_identity_aliases(source_id, identity_kind, identity_value, canonical_detail_identity) VALUES (?, ?, ?, ?)",
            ("rocket-lab", "canonical_detail", "detail-1", "detail-1"),
        )
        try:
            connection.execute(
                "INSERT INTO job_identity_aliases(source_id, identity_kind, identity_value, canonical_detail_identity) VALUES (?, ?, ?, ?)",
                ("rocket-lab", "canonical_detail", "detail-1", "detail-1"),
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("alias uniqueness was not enforced")
