from __future__ import annotations

import sqlite3

import pytest

from resume_tailor.infrastructure import job_discovery_migrations as migrations


def _create_version_one_database(path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        PRAGMA user_version = 1;
        CREATE TABLE job_search_preferences (
            user_id TEXT NOT NULL, profile_id TEXT NOT NULL, version INTEGER NOT NULL,
            payload_json TEXT NOT NULL, schema_version INTEGER NOT NULL,
            created_at TEXT NOT NULL, confirmed_at TEXT,
            PRIMARY KEY (user_id, profile_id, version)
        );
        CREATE TABLE discovered_jobs (
            job_id TEXT PRIMARY KEY, external_job_id TEXT NOT NULL, source_id TEXT NOT NULL,
            payload_json TEXT NOT NULL, schema_version INTEGER NOT NULL, fetched_at TEXT NOT NULL,
            UNIQUE(source_id, external_job_id)
        );
        CREATE TABLE discovery_runs (
            run_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, profile_id TEXT NOT NULL,
            preference_version INTEGER NOT NULL, status TEXT NOT NULL, payload_json TEXT NOT NULL,
            started_at TEXT NOT NULL, completed_at TEXT, warning_count INTEGER NOT NULL,
            error_json TEXT NOT NULL
        );
        CREATE TABLE job_recommendations (
            recommendation_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, job_id TEXT NOT NULL,
            group_name TEXT NOT NULL, rank INTEGER NOT NULL, payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL, UNIQUE(run_id, job_id)
        );
        CREATE TABLE saved_jobs (
            saved_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, job_id TEXT NOT NULL,
            availability TEXT NOT NULL, snapshot_json TEXT NOT NULL,
            snapshot_schema_version INTEGER NOT NULL, saved_at TEXT NOT NULL, checked_at TEXT
        );
        CREATE TABLE supported_job_sources (
            source_id TEXT PRIMARY KEY, connector_type TEXT NOT NULL, company_name TEXT NOT NULL,
            board_token TEXT NOT NULL, official_base_url TEXT NOT NULL,
            lever_api_region TEXT, enabled INTEGER NOT NULL
        );
        INSERT INTO saved_jobs VALUES
            ('saved-1', 'u1', 'job-1', 'available', '{"immutable":true}', 1,
             '2026-07-24T12:00:00+00:00', NULL);
        """
    )
    connection.commit()
    connection.close()


def test_fresh_initialization_is_version_three_and_idempotent(tmp_path) -> None:
    database = tmp_path / "fresh.sqlite3"

    migrations.initialize_job_discovery_database(database)
    migrations.initialize_job_discovery_database(database)

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        assert "feed_kind" in {
            row[1] for row in connection.execute("PRAGMA table_info(job_recommendations)")
        }
        assert "visibility" in {
            row[1] for row in connection.execute("PRAGMA table_info(job_recommendations)")
        }


def test_version_one_migration_preserves_saved_snapshot_and_adds_runtime_metadata(tmp_path) -> None:
    database = tmp_path / "version-one.sqlite3"
    _create_version_one_database(database)

    migrations.initialize_job_discovery_database(database)

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        assert connection.execute(
            "SELECT snapshot_json, snapshot_schema_version FROM saved_jobs WHERE saved_id='saved-1'"
        ).fetchone() == ('{"immutable":true}', 1)
        assert (
            connection.execute("SELECT feed_kind, visibility FROM job_recommendations").fetchall()
            == []
        )
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='source_runtime_state'"
        ).fetchone() == ("source_runtime_state",)


def test_version_one_migration_rolls_back_schema_changes_on_failure(tmp_path, monkeypatch) -> None:
    database = tmp_path / "rollback.sqlite3"
    _create_version_one_database(database)
    original = migrations._migrate_version_one_to_two

    def fail(connection):
        connection.execute("ALTER TABLE discovery_runs ADD COLUMN transient TEXT")
        raise RuntimeError("migration failure")

    monkeypatch.setattr(migrations, "_migrate_version_one_to_two", fail)
    with pytest.raises(RuntimeError):
        migrations.initialize_job_discovery_database(database)
    monkeypatch.setattr(migrations, "_migrate_version_one_to_two", original)

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert "transient" not in {
            row[1] for row in connection.execute("PRAGMA table_info(discovery_runs)")
        }
