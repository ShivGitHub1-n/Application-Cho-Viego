from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Timer

import pytest

from resume_tailor.domain.job_discovery.models import ConnectorType, SupportedJobSource
from resume_tailor.infrastructure import job_discovery_migrations
from resume_tailor.infrastructure.config import Settings
from resume_tailor.infrastructure.dependencies import create_job_discovery_services
from resume_tailor.infrastructure.job_discovery_sqlite import SQLiteSupportedJobSourceRepository


def _settings(database: Path) -> Settings:
    return Settings(
        app_data_directory=database.parent,
        profile_store_filename=database.name,
        job_discovery_source_registry_path=None,
    )


def test_current_schema_initialization_skips_write_transaction(tmp_path, monkeypatch) -> None:
    database = tmp_path / "job-discovery.sqlite3"
    job_discovery_migrations.initialize_job_discovery_database(database)
    statements: list[str] = []
    real_connect = sqlite3.connect

    class _ObservedConnection:
        def __init__(self, connection: sqlite3.Connection) -> None:
            self._connection = connection

        def execute(self, statement: str, *args: object):
            statements.append(statement.strip().upper())
            return self._connection.execute(statement, *args)

        def __getattr__(self, name: str):
            return getattr(self._connection, name)

    monkeypatch.setattr(
        job_discovery_migrations.sqlite3,
        "connect",
        lambda *args, **kwargs: _ObservedConnection(real_connect(*args, **kwargs)),
    )

    job_discovery_migrations.initialize_job_discovery_database(database)

    assert "BEGIN IMMEDIATE" not in statements


def test_service_bundle_initializes_schema_once_before_repository_fanout(
    tmp_path, monkeypatch
) -> None:
    database = tmp_path / "job-discovery.sqlite3"
    calls: list[Path] = []
    original = job_discovery_migrations.initialize_job_discovery_database

    def observe(path: str | Path) -> None:
        calls.append(Path(path).resolve())
        original(path)

    monkeypatch.setattr(
        "resume_tailor.infrastructure.dependencies.initialize_job_discovery_database", observe
    )
    bundle = create_job_discovery_services(_settings(database))
    try:
        assert calls == [database.resolve()]
    finally:
        bundle.close()


def test_concurrent_initialization_waits_for_a_short_writer_and_preserves_schema(tmp_path) -> None:
    database = tmp_path / "job-discovery.sqlite3"
    job_discovery_migrations.initialize_job_discovery_database(database)
    holder = sqlite3.connect(
        database, timeout=5.0, isolation_level=None, check_same_thread=False
    )
    holder.execute("BEGIN IMMEDIATE")
    release = Timer(0.1, holder.commit)
    release.start()
    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            errors = list(
                executor.map(
                    job_discovery_migrations.initialize_job_discovery_database,
                    [database] * 4,
                )
            )
        assert errors == [None] * 4
    finally:
        release.cancel()
        holder.rollback()
        holder.close()
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3


def test_failed_initialization_remains_retryable(tmp_path, monkeypatch) -> None:
    database = tmp_path / "job-discovery.sqlite3"
    original = job_discovery_migrations._create_version_two_schema
    attempts = 0

    def fail_once(connection: sqlite3.Connection) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("synthetic migration failure")
        original(connection)

    monkeypatch.setattr(job_discovery_migrations, "_create_version_two_schema", fail_once)
    with pytest.raises(RuntimeError, match="synthetic migration failure"):
        job_discovery_migrations.initialize_job_discovery_database(database)
    job_discovery_migrations.initialize_job_discovery_database(database)
    assert attempts == 2


def test_reopening_all_repositories_preserves_existing_source_data(tmp_path) -> None:
    database = tmp_path / "job-discovery.sqlite3"
    first = create_job_discovery_services(_settings(database))
    try:
        source_repository = SQLiteSupportedJobSourceRepository(database, initialize=False)
        source_repository.save(
            SupportedJobSource(
                source_id="example-greenhouse",
                connector_type=ConnectorType.GREENHOUSE,
                company_name="Example Robotics",
                board_token="example",
                enabled=True,
                official_base_url="https://example.com",
            )
        )
        assert first.source_refresh is not None
    finally:
        first.close()
    second = create_job_discovery_services(_settings(database))
    try:
        assert second.source_refresh is not None
        reopened = SQLiteSupportedJobSourceRepository(database, initialize=False)
        assert [source.source_id for source in reopened.list_enabled()] == [
            "example-greenhouse"
        ]
    finally:
        second.close()
