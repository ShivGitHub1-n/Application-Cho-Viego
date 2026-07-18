from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

APPLICATION_DATA_ENV_VAR = "APPLICATION_VIEGO_DATA_DIR"
APPLICATION_DATA_DIRECTORY_NAME = "Application Viego"
LEGACY_DATA_DIRECTORY_NAME = "data"

_MIGRATABLE_TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "master_profiles": (
        "profile_id",
        "schema_version",
        "payload",
        "updated_at",
    ),
    "job_search_preferences": (
        "user_id",
        "profile_id",
        "version",
        "payload_json",
        "schema_version",
        "created_at",
        "confirmed_at",
    ),
    "discovered_jobs": (
        "job_id",
        "external_job_id",
        "source_id",
        "payload_json",
        "schema_version",
        "fetched_at",
    ),
    "discovery_runs": (
        "run_id",
        "user_id",
        "profile_id",
        "preference_version",
        "status",
        "payload_json",
        "started_at",
        "completed_at",
        "warning_count",
        "error_json",
    ),
    "job_recommendations": (
        "recommendation_id",
        "run_id",
        "job_id",
        "group_name",
        "rank",
        "payload_json",
        "created_at",
    ),
    "saved_jobs": (
        "saved_id",
        "user_id",
        "job_id",
        "availability",
        "snapshot_json",
        "snapshot_schema_version",
        "saved_at",
        "checked_at",
    ),
}


@dataclass(frozen=True)
class ApplicationDataMigrationReport:
    source_database: Path | None
    destination_database: Path
    imported_rows: dict[str, int] = field(default_factory=dict)
    issues: tuple[str, ...] = ()

    @property
    def imported_row_count(self) -> int:
        return sum(self.imported_rows.values())


def default_application_data_directory() -> Path:
    """Return the user-level default without creating it."""

    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        return base / APPLICATION_DATA_DIRECTORY_NAME
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg_data_home) if xdg_data_home else Path.home() / ".local" / "share"
    return base / "application-viego"


def application_database_path(data_directory: Path, filename: str) -> Path:
    if not filename.strip() or Path(filename).name != filename:
        raise ValueError("Application database filename must be a plain filename")
    return (data_directory.expanduser() / filename).resolve()


def repository_local_legacy_database(
    repository_root: Path,
    filename: str,
) -> Path:
    root = repository_root.expanduser().resolve()
    candidate = (root / LEGACY_DATA_DIRECTORY_NAME / filename).resolve()
    expected_parent = (root / LEGACY_DATA_DIRECTORY_NAME).resolve()
    if candidate.parent != expected_parent:
        raise ValueError(
            "Legacy application database must stay inside the repository data directory"
        )
    return candidate


def migrate_legacy_application_database(
    source_database: Path | None,
    destination_database: Path,
) -> ApplicationDataMigrationReport:
    """Copy only allowlisted application rows, preserving canonical conflicts."""

    destination = destination_database.expanduser().resolve()
    if source_database is None:
        return ApplicationDataMigrationReport(None, destination)
    source = source_database.expanduser().resolve()
    if source == destination or not source.is_file():
        return ApplicationDataMigrationReport(source, destination)
    try:
        with source.open("rb") as legacy_file:
            header = legacy_file.read(16)
        if header != b"SQLite format 3\x00":
            return ApplicationDataMigrationReport(
                source,
                destination,
                issues=("Legacy data file is not a SQLite database; no rows were imported.",),
            )
    except OSError:
        return ApplicationDataMigrationReport(
            source,
            destination,
            issues=("Legacy data file could not be inspected; no rows were imported.",),
        )

    imported: dict[str, int] = {}
    issues: list[str] = []
    try:
        with (
            sqlite3.connect(source) as source_connection,
            sqlite3.connect(destination) as destination_connection,
        ):
            source_tables = {
                row[0]
                for row in source_connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            destination_tables = {
                row[0]
                for row in destination_connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            for table, columns in _MIGRATABLE_TABLE_COLUMNS.items():
                if table not in source_tables or table not in destination_tables:
                    continue
                source_columns = {
                    row[1] for row in source_connection.execute(f"PRAGMA table_info({table})")
                }
                destination_columns = {
                    row[1] for row in destination_connection.execute(f"PRAGMA table_info({table})")
                }
                required = set(columns)
                if not required.issubset(source_columns) or not required.issubset(
                    destination_columns
                ):
                    issues.append(
                        f"Legacy table {table!r} has an incompatible schema and was not imported."
                    )
                    continue
                column_sql = ", ".join(columns)
                placeholders = ", ".join("?" for _ in columns)
                rows = source_connection.execute(f"SELECT {column_sql} FROM {table}").fetchall()
                before = destination_connection.total_changes
                destination_connection.executemany(
                    f"INSERT OR IGNORE INTO {table} ({column_sql}) VALUES ({placeholders})",
                    rows,
                )
                imported[table] = destination_connection.total_changes - before
    except sqlite3.Error:
        return ApplicationDataMigrationReport(
            source,
            destination,
            imported_rows=imported,
            issues=(
                *issues,
                "Legacy application data could not be read safely; "
                "existing canonical data was preserved.",
            ),
        )
    return ApplicationDataMigrationReport(
        source,
        destination,
        imported_rows=imported,
        issues=tuple(issues),
    )


__all__ = [
    "APPLICATION_DATA_ENV_VAR",
    "ApplicationDataMigrationReport",
    "application_database_path",
    "default_application_data_directory",
    "migrate_legacy_application_database",
    "repository_local_legacy_database",
]
