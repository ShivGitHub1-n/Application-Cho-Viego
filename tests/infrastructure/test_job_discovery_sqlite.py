from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import pytest

from resume_tailor.domain.job_discovery.models import (
    ConnectorType,
    DiscoveredJob,
    DiscoveryRun,
    DiscoveryRunStatus,
    EligibilityAssessment,
    EligibilityStatus,
    JobRecommendation,
    JobScoreBreakdown,
    JobSearchPreferences,
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
from resume_tailor.domain.models import RoleFamily
from resume_tailor.infrastructure.job_discovery_sqlite import (
    CorruptStoredJobDiscoveryError,
    SQLiteDiscoveredJobRepository,
    SQLiteDiscoveryRunRepository,
    SQLiteJobRecommendationRepository,
    SQLiteJobSearchPreferencesRepository,
    SQLiteSavedJobRepository,
    SQLiteSupportedJobSourceRepository,
    initialize_job_discovery_database,
)
from resume_tailor.ports.job_discovery import PreferenceVersionConflictError

WHEN = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)


def _source(source_id: str = "acme") -> SupportedJobSource:
    return SupportedJobSource(
        source_id=source_id,
        connector_type=ConnectorType.GREENHOUSE,
        company_name="Acme Robotics",
        board_token="acme",
        enabled=True,
        official_base_url="https://boards.greenhouse.io",
    )


def _preferences(version: int = 1) -> JobSearchPreferences:
    return JobSearchPreferences(
        user_id="u1",
        profile_id="p1",
        version=version,
        role_family_priority=[RoleFamily.SOFTWARE_DATA_ENGINEERING],
        target_titles=["Software Engineer"],
        related_title_variants=[],
        technical_themes=["python"],
        career_interests=["software"],
        job_levels=[],
        locations=[],
        work_arrangement=WorkArrangement.UNKNOWN,
        preferred_companies=[],
        created_at=WHEN,
        confirmed_at=WHEN,
    )


def _job(job_id: str = "job-1", description: str = "Build software.") -> DiscoveredJob:
    return DiscoveredJob(
        id=job_id,
        source=_source(),
        external_job_id=job_id,
        title="Software Engineer",
        company_name="Acme Robotics",
        description=description,
        official_url="https://boards.greenhouse.io/acme/jobs/1",
        location=NormalizedLocation(raw="Toronto, ON, Canada", parseable=True),
        work_arrangement=WorkArrangement.REMOTE,
        role_family=RoleFamily.SOFTWARE_DATA_ENGINEERING,
        verification_status=VerificationStatus.VERIFIED_ACTIVE,
        verification_confidence=VerificationConfidence.HIGH,
        fetched_at=WHEN,
    )


def _recommendation(run_id: str, job_id: str = "job-1", rank: int = 1) -> JobRecommendation:
    return JobRecommendation(
        id=f"rec-{run_id}-{job_id}",
        run_id=run_id,
        user_id="u1",
        profile_id="p1",
        profile_version=3,
        preference_version=1,
        job_id=job_id,
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
        ),
        rank=rank,
        created_at=WHEN,
    )


def _run(run_id: str, status: DiscoveryRunStatus = DiscoveryRunStatus.RUNNING) -> DiscoveryRun:
    return DiscoveryRun(
        id=run_id,
        user_id="u1",
        profile_id="p1",
        preference_version=1,
        status=status,
        started_at=WHEN,
        completed_at=None if status is DiscoveryRunStatus.RUNNING else LATER,
        source_count=1,
        record_count=1,
        warning_count=0,
        error_messages=[],
    )


def test_schema_initialization_is_idempotent_and_has_schema_version_one(tmp_path) -> None:
    database = tmp_path / "discovery.sqlite3"
    initialize_job_discovery_database(database)
    initialize_job_discovery_database(database)

    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert tables == {
            "job_search_preferences",
            "discovered_jobs",
            "discovery_runs",
            "job_recommendations",
            "saved_jobs",
            "supported_job_sources",
        }
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        expected_columns = {
            "job_search_preferences": {
                "user_id", "profile_id", "version", "payload_json", "schema_version",
                "created_at", "confirmed_at",
            },
            "discovered_jobs": {
                "job_id", "external_job_id", "source_id", "payload_json", "schema_version",
                "fetched_at",
            },
            "discovery_runs": {
                "run_id", "user_id", "profile_id", "preference_version", "status",
                "payload_json", "started_at", "completed_at", "warning_count", "error_json",
            },
            "job_recommendations": {
                "recommendation_id", "run_id", "job_id", "group_name", "rank",
                "payload_json", "created_at",
            },
            "saved_jobs": {
                "saved_id", "user_id", "job_id", "availability", "snapshot_json",
                "snapshot_schema_version", "saved_at", "checked_at",
            },
            "supported_job_sources": {
                "source_id", "connector_type", "company_name", "board_token",
                "official_base_url", "lever_api_region", "enabled",
            },
        }
        for table, columns in expected_columns.items():
            actual = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            assert actual == columns
        indexes = {
            row[1]
            for row in connection.execute(
                "SELECT type, name FROM sqlite_master WHERE type = 'index'"
            )
            if not row[1].startswith("sqlite_autoindex")
        }
        assert indexes == {
            "idx_job_search_preferences_current",
            "idx_discovered_jobs_source_external",
            "idx_discovery_runs_user_profile_started",
            "idx_job_recommendations_run_rank",
            "idx_saved_jobs_user_saved",
            "idx_supported_job_sources_enabled",
        }


def test_preferences_round_trip_and_current_selection_is_by_highest_version(tmp_path) -> None:
    repository = SQLiteJobSearchPreferencesRepository(tmp_path / "one.sqlite3")
    repository.save_confirmed(_preferences(2))
    repository.save_confirmed(_preferences(1))

    assert repository.get_current("u1", "p1") == _preferences(2)


def test_preference_version_conflict_is_rejected_without_overwriting_payload(tmp_path) -> None:
    repository = SQLiteJobSearchPreferencesRepository(tmp_path / "preferences.sqlite3")
    repository.save_confirmed(_preferences(1))

    conflicting = _preferences(1).model_copy(update={"target_titles": ["Data Engineer"]})
    with pytest.raises(PreferenceVersionConflictError):
        repository.save_confirmed(conflicting)

    assert repository.get_current("u1", "p1") == _preferences(1)


def test_discovered_job_upsert_and_read_round_trip(tmp_path) -> None:
    repository = SQLiteDiscoveredJobRepository(tmp_path / "discovery.sqlite3")
    repository.upsert(_job())

    assert repository.get("job-1") == _job()

    repository.upsert(_job(description="Updated description."))
    assert repository.get("job-1").description == "Updated description."


def test_discovery_run_create_complete_and_read_preserve_identity(tmp_path) -> None:
    repository = SQLiteDiscoveryRunRepository(tmp_path / "discovery.sqlite3")
    running = _run("run-1")
    repository.create(running)
    complete = running.model_copy(
        update={
            "status": DiscoveryRunStatus.COMPLETED,
            "completed_at": LATER,
        }
    )
    repository.complete(complete)

    assert repository.get("run-1") == complete


def test_recommendation_replacement_isolated_and_deterministically_ordered(tmp_path) -> None:
    repository = SQLiteJobRecommendationRepository(tmp_path / "discovery.sqlite3")
    repository.replace_for_run(
        "run-1",
        [_recommendation("run-1", "job-2", 2), _recommendation("run-1", "job-1", 1)],
    )
    repository.replace_for_run("run-2", [_recommendation("run-2")])

    assert [item.job_id for item in repository.list_for_run("run-1")] == ["job-1", "job-2"]
    assert [item.run_id for item in repository.list_for_run("run-2")] == ["run-2"]


def test_recommendation_replacement_rolls_back_complete_operation_on_failure(tmp_path) -> None:
    repository = SQLiteJobRecommendationRepository(tmp_path / "discovery.sqlite3")
    original = _recommendation("run-1", "job-1")
    repository.replace_for_run("run-1", [original])
    duplicate = _recommendation("run-1", "job-2")
    duplicate = duplicate.model_copy(update={"id": original.id})

    with pytest.raises(sqlite3.IntegrityError):
        repository.replace_for_run("run-1", [duplicate, _recommendation("run-1", "job-3")])

    assert repository.list_for_run("run-1") == [original]


def test_saved_job_round_trip_and_snapshot_is_immutable(tmp_path) -> None:
    repository = SQLiteSavedJobRepository(tmp_path / "discovery.sqlite3")
    first = SavedJob(
        id="saved-1",
        user_id="u1",
        job_id="job-1",
        availability=SavedJobAvailability.AVAILABLE,
        saved_at=WHEN,
        snapshot_schema_version=1,
        posting_snapshot=_job(description="Original description."),
    )
    second = first.model_copy(
        update={
            "availability": SavedJobAvailability.UNKNOWN,
            "saved_at": LATER,
            "posting_snapshot": _job(description="Changed description."),
        }
    )
    repository.save(first)
    repository.save(second)

    saved = repository.get("u1", "saved-1")
    assert saved is not None
    assert saved.posting_snapshot.description == "Original description."
    assert saved.availability is SavedJobAvailability.UNKNOWN


def test_saved_availability_update_preserves_snapshot(tmp_path) -> None:
    repository = SQLiteSavedJobRepository(tmp_path / "discovery.sqlite3")
    saved = SavedJob(
        id="saved-1",
        user_id="u1",
        job_id="job-1",
        availability=SavedJobAvailability.UNKNOWN,
        saved_at=WHEN,
        snapshot_schema_version=1,
        posting_snapshot=_job(),
    )
    repository.save(saved)
    repository.update_availability("saved-1", SavedJobAvailability.UNAVAILABLE, LATER)

    updated = repository.get("u1", "saved-1")
    assert updated is not None
    assert updated.availability is SavedJobAvailability.UNAVAILABLE
    assert updated.checked_at == LATER
    assert updated.posting_snapshot == saved.posting_snapshot


def test_supported_source_round_trip_and_empty_storage(tmp_path) -> None:
    empty = SQLiteSupportedJobSourceRepository(tmp_path / "empty.sqlite3")
    assert empty.list_enabled() == []

    repository = SQLiteSupportedJobSourceRepository(tmp_path / "sources.sqlite3")
    repository.save(_source())
    disabled = _source("disabled").model_copy(update={"enabled": False})
    repository.save(disabled)
    assert [item.source_id for item in repository.list_enabled()] == ["acme"]


def test_invalid_stored_payload_is_not_returned_as_a_valid_model(tmp_path) -> None:
    database = tmp_path / "discovery.sqlite3"
    repository = SQLiteDiscoveredJobRepository(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO discovered_jobs(job_id, external_job_id, source_id, payload_json, "
            "schema_version, fetched_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("broken", "broken", "acme", "{not-json", 1, WHEN.isoformat()),
        )

    with pytest.raises(CorruptStoredJobDiscoveryError):
        repository.get("broken")


def test_independent_databases_do_not_share_rows(tmp_path) -> None:
    first = SQLiteDiscoveredJobRepository(tmp_path / "first.sqlite3")
    second = SQLiteDiscoveredJobRepository(tmp_path / "second.sqlite3")
    first.upsert(_job())

    assert second.get("job-1") is None
