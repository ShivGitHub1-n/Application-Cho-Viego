from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from resume_tailor.domain.job_discovery.models import (
    ConnectorType,
    DiscoveredJob,
    EligibilityAssessment,
    EligibilityStatus,
    JobRecommendation,
    JobScoreBreakdown,
    MatchLabel,
    NormalizedLocation,
    RecommendationGroup,
    SavedJob,
    SavedJobAvailability,
    SupportedJobSource,
    VerificationConfidence,
    VerificationStatus,
    WorkArrangement,
)
from resume_tailor.domain.job_discovery.source_lifecycle import SourceIdentityAlias
from resume_tailor.domain.models import RoleFamily
from resume_tailor.infrastructure import job_discovery_migrations
from resume_tailor.infrastructure.job_discovery_sqlite import (
    SQLiteJobRecommendationRepository,
    SQLiteSavedJobRepository,
    SQLiteSourceIdentityAliasRepository,
)

NOW = datetime(2026, 7, 30, 12, tzinfo=UTC)


def _source() -> SupportedJobSource:
    return SupportedJobSource(
        source_id="source-a",
        connector_type=ConnectorType.GREENHOUSE,
        company_name="Example Robotics",
        board_token="example",
        enabled=True,
        official_base_url="https://boards.greenhouse.io",
    )


def _job(description: str = "Original immutable description.") -> DiscoveredJob:
    return DiscoveredJob(
        id="job-1",
        source=_source(),
        external_job_id="external-1",
        title="Software Engineer",
        company_name="Example Robotics",
        description=description,
        official_url="https://boards.greenhouse.io/example/jobs/1",
        location=NormalizedLocation(raw="Toronto, ON, Canada", parseable=True),
        work_arrangement=WorkArrangement.REMOTE,
        role_family=RoleFamily.SOFTWARE_DATA_ENGINEERING,
        verification_status=VerificationStatus.VERIFIED_ACTIVE,
        verification_confidence=VerificationConfidence.HIGH,
        fetched_at=NOW,
    )


def _recommendation() -> JobRecommendation:
    return JobRecommendation(
        id="recommendation-1",
        run_id="run-1",
        user_id="user-1",
        profile_id="profile-1",
        profile_version=1,
        preference_version=1,
        job_id="job-1",
        group=RecommendationGroup.PRIMARY,
        primary_role_family=RoleFamily.SOFTWARE_DATA_ENGINEERING,
        eligibility=EligibilityAssessment(
            status=EligibilityStatus.ELIGIBLE,
            verification_confidence=VerificationConfidence.HIGH,
        ),
        score=JobScoreBreakdown(
            demonstrated_technical_evidence=30,
            required_coverage=20,
            role_alignment=15,
            level_alignment=15,
            education_coursework=10,
            preferred_skill_alignment=5,
            recency_completeness=5,
            total=100,
            label=MatchLabel.STRONG,
            provisional=False,
            fit_grade=None,
            evaluation_policy_version="jobs-score-legacy-v1",
        ),
        rank=1,
        created_at=NOW,
    )


def _create_version_one_database(path) -> None:
    with sqlite3.connect(path) as connection:
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
                payload_json TEXT NOT NULL, schema_version INTEGER NOT NULL,
                fetched_at TEXT NOT NULL,
                UNIQUE(source_id, external_job_id)
            );
            CREATE TABLE discovery_runs (
                run_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, profile_id TEXT NOT NULL,
                preference_version INTEGER NOT NULL, status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
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
                source_id TEXT PRIMARY KEY, connector_type TEXT NOT NULL,
                company_name TEXT NOT NULL,
                board_token TEXT NOT NULL, official_base_url TEXT NOT NULL,
                lever_api_region TEXT, enabled INTEGER NOT NULL
            );
            INSERT INTO saved_jobs VALUES
                ('saved-1', 'user-1', 'job-1', 'available', '{"immutable":true}', 1,
                 '2026-07-30T12:00:00+00:00', NULL);
            """
        )


def _create_version_two_database(path) -> None:
    _create_version_one_database(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "ALTER TABLE discovery_runs ADD COLUMN source_outcomes_json TEXT NOT NULL DEFAULT '[]'"
        )
        connection.execute(
            "ALTER TABLE job_recommendations ADD COLUMN feed_kind TEXT NOT NULL DEFAULT 'tailored'"
        )
        connection.execute(
            "ALTER TABLE job_recommendations ADD COLUMN visibility TEXT NOT NULL DEFAULT 'visible'"
        )
        connection.execute("PRAGMA user_version = 2")


def test_schema_v1_and_v2_migrations_preserve_snapshot_payloads(tmp_path) -> None:
    for create in (_create_version_one_database, _create_version_two_database):
        database = tmp_path / f"schema-{create.__name__}.sqlite3"
        create(database)
        job_discovery_migrations.initialize_job_discovery_database(database)
        job_discovery_migrations.initialize_job_discovery_database(database)
        with sqlite3.connect(database) as connection:
            assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
            assert connection.execute(
                "SELECT snapshot_json, snapshot_schema_version FROM saved_jobs "
                "WHERE saved_id='saved-1'"
            ).fetchone() == ('{"immutable":true}', 1)
            assert connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='source_runtime_state'"
            ).fetchone() == ("source_runtime_state",)


def test_schema_v3_reads_saved_jobs_and_repeated_migration_is_safe(tmp_path) -> None:
    database = tmp_path / "schema-3.sqlite3"
    job_discovery_migrations.initialize_job_discovery_database(database)
    job_discovery_migrations.initialize_job_discovery_database(database)
    repository = SQLiteSavedJobRepository(database)
    saved = SavedJob(
        id="saved-1",
        user_id="user-1",
        job_id="job-1",
        availability=SavedJobAvailability.AVAILABLE,
        saved_at=NOW,
        posting_snapshot=_job(),
    )
    repository.save(saved)

    loaded = repository.get("user-1", "saved-1")

    assert loaded == saved


def test_legacy_recommendation_is_readable_and_not_silently_rescored(tmp_path) -> None:
    database = tmp_path / "legacy.sqlite3"
    repository = SQLiteJobRecommendationRepository(database)
    current = _recommendation()
    repository.replace_for_run(current.run_id, [current])
    with sqlite3.connect(database) as connection:
        payload = current.model_dump(mode="json")
        payload.pop("feed_kind")
        payload.pop("visibility")
        payload["score"].pop("evaluation_policy_version")
        connection.execute(
            "UPDATE job_recommendations SET payload_json = ? WHERE recommendation_id = ?",
            (json.dumps(payload), current.id),
        )
        connection.commit()

    loaded = repository.list_for_run(current.run_id)[0]

    assert loaded.earlier_policy is True
    assert loaded.legacy_payload is not None
    assert loaded.score.fit_grade is None
    assert loaded.score.historical_label is MatchLabel.STRONG
    assert loaded.evaluation_policy_version is None


def test_saved_snapshot_immutability_and_source_qualified_aliases_survive_updates(tmp_path) -> None:
    database = tmp_path / "snapshot.sqlite3"
    repository = SQLiteSavedJobRepository(database)
    original = SavedJob(
        id="saved-1",
        user_id="user-1",
        job_id="job-1",
        availability=SavedJobAvailability.UNKNOWN,
        saved_at=NOW,
        posting_snapshot=_job(),
    )
    repository.save(original)
    repository.update_availability("saved-1", SavedJobAvailability.UNAVAILABLE, NOW)
    loaded = repository.get("user-1", "saved-1")

    aliases = SQLiteSourceIdentityAliasRepository(database)
    aliases.upsert(
        SourceIdentityAlias(
            source_id="source-a",
            identity_kind="canonical_detail",
            identity_value="https://boards.greenhouse.io/example/jobs/1",
            canonical_detail_identity="https://boards.greenhouse.io/example/jobs/1",
            job_id="job-1",
            created_at=NOW,
        )
    )

    assert loaded is not None
    assert loaded.availability is SavedJobAvailability.UNAVAILABLE
    assert loaded.posting_snapshot.description == original.posting_snapshot.description
    assert loaded.posting_snapshot.official_url == original.posting_snapshot.official_url
    assert aliases.list_for_source("source-a")[0].job_id == "job-1"
