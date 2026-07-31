"""The single permanent SQLite migration boundary for Jobs feeds."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 3
LEGACY_SCHEMA_VERSION = 1
PREVIOUS_SCHEMA_VERSION = 2


def initialize_job_discovery_database(database_path: str | Path) -> None:
    resolved = Path(database_path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(resolved)
    try:
        connection.execute("BEGIN IMMEDIATE")
        current = connection.execute("PRAGMA user_version").fetchone()[0]
        if current == 0:
            _create_version_two_schema(connection)
            _migrate_version_two_to_three(connection)
        elif current == LEGACY_SCHEMA_VERSION:
            _migrate_version_one_to_two(connection)
            _migrate_version_two_to_three(connection)
        elif current == PREVIOUS_SCHEMA_VERSION:
            _migrate_version_two_to_three(connection)
        elif current != SCHEMA_VERSION:
            raise RuntimeError(f"unsupported job-discovery schema version {current}")
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _create_version_two_schema(connection: sqlite3.Connection) -> None:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS job_search_preferences (
            user_id TEXT NOT NULL, profile_id TEXT NOT NULL, version INTEGER NOT NULL,
            payload_json TEXT NOT NULL, schema_version INTEGER NOT NULL,
            created_at TEXT NOT NULL, confirmed_at TEXT,
            PRIMARY KEY (user_id, profile_id, version)
        );
        CREATE INDEX IF NOT EXISTS idx_job_search_preferences_current
            ON job_search_preferences(user_id, profile_id, version DESC);
        CREATE TABLE IF NOT EXISTS discovered_jobs (
            job_id TEXT PRIMARY KEY, external_job_id TEXT NOT NULL, source_id TEXT NOT NULL,
            payload_json TEXT NOT NULL, schema_version INTEGER NOT NULL, fetched_at TEXT NOT NULL,
            UNIQUE(source_id, external_job_id)
        );
        CREATE INDEX IF NOT EXISTS idx_discovered_jobs_source_external
            ON discovered_jobs(source_id, external_job_id);
        CREATE TABLE IF NOT EXISTS discovery_runs (
            run_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, profile_id TEXT NOT NULL,
            preference_version INTEGER NOT NULL, status TEXT NOT NULL, payload_json TEXT NOT NULL,
            started_at TEXT NOT NULL, completed_at TEXT, warning_count INTEGER NOT NULL,
            error_json TEXT NOT NULL, source_outcomes_json TEXT NOT NULL DEFAULT '[]'
        );
        CREATE INDEX IF NOT EXISTS idx_discovery_runs_user_profile_started
            ON discovery_runs(user_id, profile_id, started_at DESC, run_id);
        CREATE TABLE IF NOT EXISTS job_recommendations (
            recommendation_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, job_id TEXT NOT NULL,
            group_name TEXT NOT NULL, rank INTEGER NOT NULL, payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL, feed_kind TEXT NOT NULL DEFAULT 'tailored',
            visibility TEXT NOT NULL DEFAULT 'visible', UNIQUE(run_id, job_id)
        );
        CREATE INDEX IF NOT EXISTS idx_job_recommendations_run_rank
            ON job_recommendations(run_id, rank, created_at, recommendation_id);
        CREATE INDEX IF NOT EXISTS idx_job_recommendations_feed_visibility
            ON job_recommendations(feed_kind, visibility, run_id, rank);
        CREATE TABLE IF NOT EXISTS saved_jobs (
            saved_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, job_id TEXT NOT NULL,
            availability TEXT NOT NULL, snapshot_json TEXT NOT NULL,
            snapshot_schema_version INTEGER NOT NULL, saved_at TEXT NOT NULL, checked_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_saved_jobs_user_saved
            ON saved_jobs(user_id, saved_at DESC, saved_id);
        CREATE TABLE IF NOT EXISTS supported_job_sources (
            source_id TEXT PRIMARY KEY, connector_type TEXT NOT NULL, company_name TEXT NOT NULL,
            board_token TEXT NOT NULL, official_base_url TEXT NOT NULL,
            lever_api_region TEXT, enabled INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_supported_job_sources_enabled
            ON supported_job_sources(enabled, company_name COLLATE NOCASE, source_id);
        """,
    ]
    for statement in statements:
        for command in statement.split(";"):
            if command.strip():
                connection.execute(command)


def _migrate_version_one_to_two(connection: sqlite3.Connection) -> None:
    connection.execute(
        "ALTER TABLE discovery_runs ADD COLUMN source_outcomes_json TEXT NOT NULL DEFAULT '[]'"
    )
    connection.execute(
        "ALTER TABLE job_recommendations ADD COLUMN feed_kind TEXT NOT NULL DEFAULT 'tailored'"
    )
    connection.execute(
        "ALTER TABLE job_recommendations ADD COLUMN visibility TEXT NOT NULL DEFAULT 'visible'"
    )
    connection.execute("UPDATE job_search_preferences SET schema_version = 2")
    connection.execute("UPDATE discovered_jobs SET schema_version = 2")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_job_recommendations_feed_visibility "
        "ON job_recommendations(feed_kind, visibility, run_id, rank)"
    )


def _migrate_version_two_to_three(connection: sqlite3.Connection) -> None:
    """Add runtime observations without copying editable registry authority."""

    statements = [
        "UPDATE job_search_preferences SET schema_version = 3",
        "UPDATE discovered_jobs SET schema_version = 3",
        """
        CREATE TABLE IF NOT EXISTS source_runtime_state (
            source_id TEXT PRIMARY KEY,
            last_attempted_at TEXT,
            last_successful_at TEXT,
            last_complete_at TEXT,
            last_outcome TEXT NOT NULL DEFAULT 'never_run',
            diagnostic_codes_json TEXT NOT NULL DEFAULT '[]',
            consecutive_failure_count INTEGER NOT NULL DEFAULT 0,
            next_eligible_refresh_at TEXT,
            content_fingerprint TEXT,
            source_state_fingerprint TEXT,
            audit_version TEXT,
            registry_plan_hash TEXT,
            extraction_profile_hash TEXT,
            conditional_validators_json TEXT NOT NULL DEFAULT '{}',
            browser_required INTEGER NOT NULL DEFAULT 0,
            source_health TEXT NOT NULL DEFAULT 'unknown',
            incomplete_static INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS job_identity_aliases (
            alias_id INTEGER PRIMARY KEY,
            source_id TEXT NOT NULL,
            identity_kind TEXT NOT NULL,
            identity_value TEXT NOT NULL,
            external_identity TEXT,
            requisition_identity TEXT,
            application_identity TEXT,
            canonical_detail_identity TEXT,
            job_id TEXT,
            created_at TEXT NOT NULL DEFAULT '',
            UNIQUE(source_id, identity_kind, identity_value)
        );
        CREATE INDEX IF NOT EXISTS idx_job_identity_aliases_job
            ON job_identity_aliases(job_id, source_id);
        CREATE TABLE IF NOT EXISTS refresh_locks (
            source_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            acquired_at TEXT NOT NULL,
            heartbeat_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_source_runtime_due
            ON source_runtime_state(next_eligible_refresh_at, source_id);
        """,
    ]
    for statement in statements:
        for command in statement.split(";"):
            if command.strip():
                connection.execute(command)


__all__ = [
    "LEGACY_SCHEMA_VERSION",
    "SCHEMA_VERSION",
    "initialize_job_discovery_database",
]
