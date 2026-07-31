from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from resume_tailor.domain.job_discovery.models import (
    DiscoveredJob,
    DiscoveryRun,
    JobRecommendation,
    JobSearchPreferences,
    SavedJob,
    SavedJobAvailability,
    SupportedJobSource,
)
from resume_tailor.domain.job_discovery.source_lifecycle import (
    SourceIdentityAlias,
    SourceRuntimeState,
)
from resume_tailor.infrastructure.job_discovery_migrations import (
    SCHEMA_VERSION,
    initialize_job_discovery_database,
)
from resume_tailor.ports.job_discovery import (
    AtomicJobDiscoveryPersistence,
    DiscoveredJobRepository,
    DiscoveryRunRepository,
    JobRecommendationRepository,
    JobSearchPreferencesRepository,
    PreferenceVersionConflictError,
    SavedJobRepository,
    SourceIdentityAliasRepository,
    SourceRuntimeStateRepository,
    SupportedJobSourceRepository,
)

SAVED_SNAPSHOT_SCHEMA_VERSION = 1

_ModelT = TypeVar("_ModelT", bound=BaseModel)


class JobDiscoveryStoreError(RuntimeError):
    """Base error for local job-discovery storage failures."""


class CorruptStoredJobDiscoveryError(JobDiscoveryStoreError):
    """Raised when stored job-discovery JSON no longer matches typed models."""


class _SQLiteJobDiscoveryRepository:
    def __init__(self, database_path: str | Path, *, initialize: bool = True) -> None:
        self._database_path = Path(database_path)
        if initialize:
            initialize_job_discovery_database(self._database_path)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._database_path)


class SQLiteJobSearchPreferencesRepository(
    _SQLiteJobDiscoveryRepository, JobSearchPreferencesRepository
):
    def get_current(self, user_id: str, profile_id: str) -> JobSearchPreferences | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json, schema_version
                FROM job_search_preferences
                WHERE user_id = ? AND profile_id = ?
                ORDER BY version DESC
                LIMIT 1
                """,
                (user_id, profile_id),
            ).fetchone()
        if row is None:
            return None
        preferences = _load_versioned_model(
            JobSearchPreferences, row[0], row[1], "job-search preferences"
        )
        if preferences.user_id != user_id or preferences.profile_id != profile_id:
            raise CorruptStoredJobDiscoveryError(
                "Stored job-search preferences do not match requested identity"
            )
        return preferences

    def save_confirmed(self, preferences: JobSearchPreferences) -> None:
        validated = _validate_model(JobSearchPreferences, preferences)
        payload_json = _dump_model(validated)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = connection.execute(
                    """
                    SELECT payload_json
                    FROM job_search_preferences
                    WHERE user_id = ? AND profile_id = ? AND version = ?
                    """,
                    (validated.user_id, validated.profile_id, validated.version),
                ).fetchone()
                if existing is not None and existing[0] != payload_json:
                    raise PreferenceVersionConflictError(
                        f"Preference version {validated.version} already exists"
                    )
                connection.execute(
                    """
                    INSERT INTO job_search_preferences(
                        user_id, profile_id, version, payload_json, schema_version,
                        created_at, confirmed_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, profile_id, version) DO UPDATE SET
                        payload_json = excluded.payload_json,
                        schema_version = excluded.schema_version,
                        created_at = excluded.created_at,
                        confirmed_at = excluded.confirmed_at
                    """,
                    (
                        validated.user_id,
                        validated.profile_id,
                        validated.version,
                        payload_json,
                        SCHEMA_VERSION,
                        validated.created_at.isoformat(),
                        _optional_datetime(validated.confirmed_at),
                    ),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise


class SQLiteDiscoveredJobRepository(_SQLiteJobDiscoveryRepository, DiscoveredJobRepository):
    def upsert(self, job: DiscoveredJob) -> None:
        validated = _validate_model(DiscoveredJob, job)
        payload_json = _dump_model(validated)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    INSERT INTO discovered_jobs(
                        job_id, external_job_id, source_id, payload_json,
                        schema_version, fetched_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(job_id) DO UPDATE SET
                        external_job_id = excluded.external_job_id,
                        source_id = excluded.source_id,
                        payload_json = excluded.payload_json,
                        schema_version = excluded.schema_version,
                        fetched_at = excluded.fetched_at
                    """,
                    (
                        validated.id,
                        validated.external_job_id,
                        validated.source.source_id,
                        payload_json,
                        SCHEMA_VERSION,
                        validated.fetched_at.isoformat(),
                    ),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def get(self, job_id: str) -> DiscoveredJob | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json, schema_version
                FROM discovered_jobs
                WHERE job_id = ?
                """,
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        job = _load_versioned_model(DiscoveredJob, row[0], row[1], f"discovered job {job_id!r}")
        if job.id != job_id:
            raise CorruptStoredJobDiscoveryError(
                f"Stored discovered job {job.id!r} does not match requested ID {job_id!r}"
            )
        return job


class SQLiteDiscoveryRunRepository(_SQLiteJobDiscoveryRepository, DiscoveryRunRepository):
    def create(self, run: DiscoveryRun) -> None:
        validated = _validate_model(DiscoveryRun, run)
        payload_json = _dump_model(validated)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    INSERT INTO discovery_runs(
                        run_id, user_id, profile_id, preference_version, status,
                        payload_json, started_at, completed_at, warning_count,
                        error_json, source_outcomes_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    _run_row(validated, payload_json),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def complete(self, run: DiscoveryRun) -> None:
        validated = _validate_model(DiscoveryRun, run)
        payload_json = _dump_model(validated)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = connection.execute(
                    """
                    UPDATE discovery_runs
                    SET user_id = ?,
                        profile_id = ?,
                        preference_version = ?,
                        status = ?,
                        payload_json = ?,
                        started_at = ?,
                        completed_at = ?,
                        warning_count = ?,
                        error_json = ?,
                        source_outcomes_json = ?
                    WHERE run_id = ?
                    """,
                    (
                        validated.user_id,
                        validated.profile_id,
                        validated.preference_version,
                        validated.status.value,
                        payload_json,
                        validated.started_at.isoformat(),
                        _optional_datetime(validated.completed_at),
                        validated.warning_count,
                        _dump_json_list(validated.error_messages),
                        _dump_model_list(validated.source_outcomes),
                        validated.id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise KeyError(f"Discovery run {validated.id!r} was not found")
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def get(self, run_id: str) -> DiscoveryRun | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json, error_json, source_outcomes_json
                FROM discovery_runs
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        _load_json_list(row[1], f"discovery run {run_id!r} errors")
        _load_model_list(row[2], f"discovery run {run_id!r} source outcomes")
        run = _load_model(DiscoveryRun, row[0], f"discovery run {run_id!r}")
        if run.id != run_id:
            raise CorruptStoredJobDiscoveryError(
                f"Stored discovery run {run.id!r} does not match requested ID {run_id!r}"
            )
        return run


class SQLiteJobRecommendationRepository(_SQLiteJobDiscoveryRepository, JobRecommendationRepository):
    def replace_for_run(self, run_id: str, recommendations: list[JobRecommendation]) -> None:
        validated = [
            _validate_model(JobRecommendation, recommendation) for recommendation in recommendations
        ]
        for recommendation in validated:
            if recommendation.run_id != run_id:
                raise ValueError("Recommendation run_id must match replacement run_id")

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                _raise_for_reused_recommendation_identity(connection, run_id, validated)
                connection.execute(
                    "DELETE FROM job_recommendations WHERE run_id = ?",
                    (run_id,),
                )
                connection.executemany(
                    """
                    INSERT INTO job_recommendations(
                        recommendation_id, run_id, job_id, group_name, rank,
                        payload_json, created_at, feed_kind, visibility
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            recommendation.id,
                            recommendation.run_id,
                            recommendation.job_id,
                            recommendation.group.value,
                            recommendation.rank,
                            _dump_model(recommendation),
                            recommendation.created_at.isoformat(),
                            recommendation.feed_kind.value,
                            recommendation.visibility.value,
                        )
                        for recommendation in validated
                    ],
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def list_for_run(self, run_id: str) -> list[JobRecommendation]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json, group_name, feed_kind, visibility
                FROM job_recommendations
                WHERE run_id = ?
                ORDER BY rank ASC, created_at ASC, recommendation_id ASC
                """,
                (run_id,),
            ).fetchall()
        recommendations: list[JobRecommendation] = []
        for payload_json, group_name, feed_kind, visibility in rows:
            recommendation = _load_model(
                JobRecommendation, payload_json, f"recommendation for run {run_id!r}"
            )
            if (
                recommendation.run_id != run_id
                or recommendation.group.value != group_name
                or recommendation.feed_kind.value != feed_kind
                or recommendation.visibility.value != visibility
            ):
                raise CorruptStoredJobDiscoveryError(
                    "Stored recommendation does not match indexed metadata"
                )
            recommendations.append(recommendation)
        return recommendations

    def list_for_feed(
        self, user_id: str, feed_kind: str, *, include_excluded: bool = False
    ) -> list[JobRecommendation]:
        query = (
            "SELECT payload_json, group_name, feed_kind, visibility "
            "FROM job_recommendations WHERE feed_kind = ? "
        )
        parameters: list[object] = [feed_kind]
        if not include_excluded:
            query += "AND visibility = 'visible' "
        query += "ORDER BY rank ASC, created_at ASC, recommendation_id ASC"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        results: list[JobRecommendation] = []
        for payload_json, group_name, stored_feed_kind, visibility in rows:
            recommendation = _load_model(JobRecommendation, payload_json, "feed recommendation")
            if (
                recommendation.user_id == user_id
                and recommendation.group.value == group_name
                and recommendation.feed_kind.value == stored_feed_kind
                and recommendation.visibility.value == visibility
            ):
                results.append(recommendation)
        return results


class SQLiteAtomicJobDiscoveryPersistence(
    _SQLiteJobDiscoveryRepository, AtomicJobDiscoveryPersistence
):
    """Persist one completed refresh as one SQLite transaction."""

    def persist_refresh(
        self,
        run: DiscoveryRun,
        jobs: list[DiscoveredJob],
        recommendations: list[JobRecommendation],
        aliases: list[SourceIdentityAlias] | None = None,
    ) -> None:
        validated_run = _validate_model(DiscoveryRun, run)
        validated_jobs = [_validate_model(DiscoveredJob, job) for job in jobs]
        validated_recommendations = [
            _validate_model(JobRecommendation, recommendation) for recommendation in recommendations
        ]
        if any(item.run_id != validated_run.id for item in validated_recommendations):
            raise ValueError("Recommendation run_id must match persisted run")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    INSERT INTO discovery_runs(
                        run_id, user_id, profile_id, preference_version, status,
                        payload_json, started_at, completed_at, warning_count,
                        error_json, source_outcomes_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(run_id) DO UPDATE SET
                        user_id=excluded.user_id,
                        profile_id=excluded.profile_id,
                        preference_version=excluded.preference_version,
                        status=excluded.status,
                        payload_json=excluded.payload_json,
                        started_at=excluded.started_at,
                        completed_at=excluded.completed_at,
                        warning_count=excluded.warning_count,
                        error_json=excluded.error_json,
                        source_outcomes_json=excluded.source_outcomes_json
                    """,
                    _run_row(validated_run, _dump_model(validated_run)),
                )
                for job in validated_jobs:
                    connection.execute(
                        """
                        INSERT INTO discovered_jobs(
                            job_id, external_job_id, source_id, payload_json,
                            schema_version, fetched_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(job_id) DO UPDATE SET
                            external_job_id = excluded.external_job_id,
                            source_id = excluded.source_id,
                            payload_json = excluded.payload_json,
                            schema_version = excluded.schema_version,
                            fetched_at = excluded.fetched_at
                        """,
                        (
                            job.id,
                            job.external_job_id,
                            job.source.source_id,
                            _dump_model(job),
                            SCHEMA_VERSION,
                            job.fetched_at.isoformat(),
                        ),
                    )
                _raise_for_reused_recommendation_identity(
                    connection, validated_run.id, validated_recommendations
                )
                connection.execute(
                    "DELETE FROM job_recommendations WHERE run_id = ?",
                    (validated_run.id,),
                )
                connection.executemany(
                    """
                    INSERT INTO job_recommendations(
                        recommendation_id, run_id, job_id, group_name, rank,
                        payload_json, created_at, feed_kind, visibility
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            item.id,
                            item.run_id,
                            item.job_id,
                            item.group.value,
                            item.rank,
                            _dump_model(item),
                            item.created_at.isoformat(),
                            item.feed_kind.value,
                            item.visibility.value,
                        )
                        for item in validated_recommendations
                    ],
                )
                for alias in aliases or []:
                    validated_alias = _validate_model(SourceIdentityAlias, alias)
                    if (
                        validated_alias.identity_kind == "canonical_detail"
                        and not validated_alias.canonical_detail_identity
                    ):
                        raise ValueError("canonical detail identity is required")
                    connection.execute(
                        """
                        INSERT INTO job_identity_aliases(
                            source_id, identity_kind, identity_value, external_identity,
                            requisition_identity, application_identity, canonical_detail_identity,
                            job_id, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(source_id, identity_kind, identity_value) DO UPDATE SET
                            external_identity=excluded.external_identity,
                            requisition_identity=excluded.requisition_identity,
                            application_identity=excluded.application_identity,
                            canonical_detail_identity=excluded.canonical_detail_identity,
                            job_id=excluded.job_id,
                            created_at=excluded.created_at
                        """,
                        (
                            validated_alias.source_id,
                            validated_alias.identity_kind,
                            validated_alias.identity_value,
                            validated_alias.external_identity,
                            validated_alias.requisition_identity,
                            validated_alias.application_identity,
                            validated_alias.canonical_detail_identity,
                            validated_alias.job_id,
                            _optional_datetime(validated_alias.created_at) or "",
                        ),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise


class SQLiteSavedJobRepository(_SQLiteJobDiscoveryRepository, SavedJobRepository):
    def save(self, saved: SavedJob) -> None:
        validated = _validate_model(SavedJob, saved)
        snapshot_json = _dump_model(validated.posting_snapshot)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = connection.execute(
                    "SELECT user_id, job_id FROM saved_jobs WHERE saved_id = ?",
                    (validated.id,),
                ).fetchone()
                if existing is None:
                    connection.execute(
                        """
                        INSERT INTO saved_jobs(
                            saved_id, user_id, job_id, availability, snapshot_json,
                            snapshot_schema_version, saved_at, checked_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            validated.id,
                            validated.user_id,
                            validated.job_id,
                            validated.availability.value,
                            snapshot_json,
                            validated.snapshot_schema_version,
                            validated.saved_at.isoformat(),
                            _optional_datetime(validated.checked_at),
                        ),
                    )
                elif existing[0] != validated.user_id or existing[1] != validated.job_id:
                    raise ValueError("Saved job identity cannot be changed")
                elif validated.checked_at is None:
                    connection.execute(
                        """
                        UPDATE saved_jobs
                        SET availability = ?
                        WHERE saved_id = ?
                        """,
                        (validated.availability.value, validated.id),
                    )
                else:
                    connection.execute(
                        """
                        UPDATE saved_jobs
                        SET availability = ?, checked_at = ?
                        WHERE saved_id = ?
                        """,
                        (
                            validated.availability.value,
                            validated.checked_at.isoformat(),
                            validated.id,
                        ),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def get(self, user_id: str, saved_id: str) -> SavedJob | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT saved_id, user_id, job_id, availability, snapshot_json,
                       snapshot_schema_version, saved_at, checked_at
                FROM saved_jobs
                WHERE user_id = ? AND saved_id = ?
                """,
                (user_id, saved_id),
            ).fetchone()
        if row is None:
            return None
        return _load_saved(row, f"saved job {saved_id!r}")

    def list(self, user_id: str) -> list[SavedJob]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT saved_id, user_id, job_id, availability, snapshot_json,
                       snapshot_schema_version, saved_at, checked_at
                FROM saved_jobs
                WHERE user_id = ?
                ORDER BY saved_at DESC, saved_id ASC
                """,
                (user_id,),
            ).fetchall()
        return [_load_saved(row, f"saved job for user {user_id!r}") for row in rows]

    def update_availability(
        self,
        saved_id: str,
        availability: SavedJobAvailability,
        checked_at: datetime,
    ) -> None:
        _require_timezone_aware(checked_at, "checked_at")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = connection.execute(
                    """
                    UPDATE saved_jobs
                    SET availability = ?, checked_at = ?
                    WHERE saved_id = ?
                    """,
                    (availability.value, checked_at.isoformat(), saved_id),
                )
                if cursor.rowcount != 1:
                    raise KeyError(f"Saved job {saved_id!r} was not found")
                connection.commit()
            except Exception:
                connection.rollback()
                raise


class SQLiteSupportedJobSourceRepository(
    _SQLiteJobDiscoveryRepository, SupportedJobSourceRepository
):
    def save(self, source: SupportedJobSource) -> None:
        validated = _validate_model(SupportedJobSource, source)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    INSERT INTO supported_job_sources(
                        source_id, connector_type, company_name, board_token,
                        official_base_url, lever_api_region, enabled
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_id) DO UPDATE SET
                        connector_type = excluded.connector_type,
                        company_name = excluded.company_name,
                        board_token = excluded.board_token,
                        official_base_url = excluded.official_base_url,
                        lever_api_region = excluded.lever_api_region,
                        enabled = excluded.enabled
                    """,
                    (
                        validated.source_id,
                        validated.connector_type.value,
                        validated.company_name,
                        validated.board_token,
                        str(validated.official_base_url),
                        (
                            validated.lever_api_region.value
                            if validated.lever_api_region is not None
                            else None
                        ),
                        1 if validated.enabled else 0,
                    ),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def list_enabled(self) -> list[SupportedJobSource]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT source_id, connector_type, company_name, board_token,
                       official_base_url, lever_api_region, enabled
                FROM supported_job_sources
                WHERE enabled = 1
                ORDER BY company_name COLLATE NOCASE ASC, source_id ASC
                """
            ).fetchall()
        return [_load_source(row) for row in rows]


class SQLiteSourceRuntimeStateRepository(
    _SQLiteJobDiscoveryRepository, SourceRuntimeStateRepository
):
    def get(self, source_id: str) -> SourceRuntimeState | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT source_id, last_attempted_at, last_successful_at, last_complete_at,
                       last_outcome, diagnostic_codes_json, consecutive_failure_count,
                       next_eligible_refresh_at, content_fingerprint, source_state_fingerprint,
                       audit_version, registry_plan_hash, extraction_profile_hash,
                       conditional_validators_json, browser_required, source_health,
                       incomplete_static, updated_at
                FROM source_runtime_state WHERE source_id = ?
                """,
                (source_id,),
            ).fetchone()
        if row is None:
            return None
        try:
            return SourceRuntimeState.model_validate(
                {
                    "source_id": row[0],
                    "last_attempted_at": row[1],
                    "last_successful_at": row[2],
                    "last_complete_at": row[3],
                    "last_outcome": row[4],
                    "diagnostic_codes": json.loads(row[5]),
                    "consecutive_failure_count": row[6],
                    "next_eligible_refresh_at": row[7],
                    "content_fingerprint": row[8],
                    "source_state_fingerprint": row[9],
                    "audit_version": row[10],
                    "registry_plan_hash": row[11],
                    "extraction_profile_hash": row[12],
                    "conditional_validators": json.loads(row[13]),
                    "browser_required": bool(row[14]),
                    "source_health": row[15],
                    "incomplete_static": bool(row[16]),
                    "updated_at": row[17] or None,
                }
            )
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise CorruptStoredJobDiscoveryError("Stored source runtime state is invalid") from exc

    def upsert(self, state: SourceRuntimeState) -> None:
        validated = _validate_model(SourceRuntimeState, state).with_state_fingerprint()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    INSERT INTO source_runtime_state(
                        source_id, last_attempted_at, last_successful_at, last_complete_at,
                        last_outcome, diagnostic_codes_json, consecutive_failure_count,
                        next_eligible_refresh_at, content_fingerprint, source_state_fingerprint,
                        audit_version, registry_plan_hash, extraction_profile_hash,
                        conditional_validators_json, browser_required, source_health,
                        incomplete_static, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_id) DO UPDATE SET
                        last_attempted_at=excluded.last_attempted_at,
                        last_successful_at=excluded.last_successful_at,
                        last_complete_at=excluded.last_complete_at,
                        last_outcome=excluded.last_outcome,
                        diagnostic_codes_json=excluded.diagnostic_codes_json,
                        consecutive_failure_count=excluded.consecutive_failure_count,
                        next_eligible_refresh_at=excluded.next_eligible_refresh_at,
                        content_fingerprint=excluded.content_fingerprint,
                        source_state_fingerprint=excluded.source_state_fingerprint,
                        audit_version=excluded.audit_version,
                        registry_plan_hash=excluded.registry_plan_hash,
                        extraction_profile_hash=excluded.extraction_profile_hash,
                        conditional_validators_json=excluded.conditional_validators_json,
                        browser_required=excluded.browser_required,
                        source_health=excluded.source_health,
                        incomplete_static=excluded.incomplete_static,
                        updated_at=excluded.updated_at
                    """,
                    (
                        validated.source_id,
                        _optional_datetime(validated.last_attempted_at),
                        _optional_datetime(validated.last_successful_at),
                        _optional_datetime(validated.last_complete_at),
                        validated.last_outcome.value,
                        _dump_json_list(validated.diagnostic_codes),
                        validated.consecutive_failure_count,
                        _optional_datetime(validated.next_eligible_refresh_at),
                        validated.content_fingerprint,
                        validated.source_state_fingerprint,
                        validated.audit_version,
                        validated.registry_plan_hash,
                        validated.extraction_profile_hash,
                        json.dumps(validated.conditional_validators, sort_keys=True),
                        1 if validated.browser_required else 0,
                        validated.source_health.value,
                        1 if validated.incomplete_static else 0,
                        _optional_datetime(validated.updated_at) or "",
                    ),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise


def read_existing_source_runtime_states(
    database_path: str | Path, source_ids: Sequence[str]
) -> dict[str, SourceRuntimeState]:
    """Read runtime state for preview selection without initializing or mutating storage."""

    path = Path(database_path)
    if not path.is_file():
        return {}
    repository = SQLiteSourceRuntimeStateRepository(path, initialize=False)
    try:
        return {
            source_id: state
            for source_id in source_ids
            if (state := repository.get(source_id)) is not None
        }
    except sqlite3.OperationalError:
        return {}


class SQLiteSourceIdentityAliasRepository(
    _SQLiteJobDiscoveryRepository, SourceIdentityAliasRepository
):
    def upsert(self, alias: SourceIdentityAlias) -> None:
        validated = _validate_model(SourceIdentityAlias, alias)
        if (
            validated.identity_kind == "canonical_detail"
            and not validated.canonical_detail_identity
        ):
            raise ValueError("canonical detail identity is required for canonical aliases")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    INSERT INTO job_identity_aliases(
                        source_id, identity_kind, identity_value, external_identity,
                        requisition_identity, application_identity, canonical_detail_identity,
                        job_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_id, identity_kind, identity_value) DO UPDATE SET
                        external_identity=excluded.external_identity,
                        requisition_identity=excluded.requisition_identity,
                        application_identity=excluded.application_identity,
                        canonical_detail_identity=excluded.canonical_detail_identity,
                        job_id=excluded.job_id,
                        created_at=excluded.created_at
                    """,
                    (
                        validated.source_id,
                        validated.identity_kind,
                        validated.identity_value,
                        validated.external_identity,
                        validated.requisition_identity,
                        validated.application_identity,
                        validated.canonical_detail_identity,
                        validated.job_id,
                        _optional_datetime(validated.created_at) or "",
                    ),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def list_for_source(self, source_id: str) -> list[SourceIdentityAlias]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT source_id, identity_kind, identity_value, external_identity,
                       requisition_identity, application_identity, canonical_detail_identity,
                       job_id, created_at
                FROM job_identity_aliases WHERE source_id = ?
                ORDER BY identity_kind, identity_value
                """,
                (source_id,),
            ).fetchall()
        return [
            SourceIdentityAlias(
                source_id=row[0],
                identity_kind=row[1],
                identity_value=row[2],
                external_identity=row[3],
                requisition_identity=row[4],
                application_identity=row[5],
                canonical_detail_identity=row[6],
                job_id=row[7],
                created_at=row[8] or None,
            )
            for row in rows
        ]


def _run_row(run: DiscoveryRun, payload_json: str) -> tuple[Any, ...]:
    return (
        run.id,
        run.user_id,
        run.profile_id,
        run.preference_version,
        run.status.value,
        payload_json,
        run.started_at.isoformat(),
        _optional_datetime(run.completed_at),
        run.warning_count,
        _dump_json_list(run.error_messages),
        _dump_model_list(run.source_outcomes),
    )


def _raise_for_reused_recommendation_identity(
    connection: sqlite3.Connection,
    run_id: str,
    recommendations: list[JobRecommendation],
) -> None:
    existing_rows = connection.execute(
        """
        SELECT recommendation_id, job_id
        FROM job_recommendations
        WHERE run_id = ?
        """,
        (run_id,),
    ).fetchall()
    existing_job_ids_by_recommendation_id = {
        recommendation_id: job_id for recommendation_id, job_id in existing_rows
    }
    for recommendation in recommendations:
        existing_job_id = existing_job_ids_by_recommendation_id.get(recommendation.id)
        if existing_job_id is not None and existing_job_id != recommendation.job_id:
            raise sqlite3.IntegrityError(
                "Recommendation identity cannot be reused for a different job"
            )


def _validate_model(model_type: type[_ModelT], value: _ModelT) -> _ModelT:
    return model_type.model_validate(value.model_dump(mode="json"))


def _dump_model(model: BaseModel) -> str:
    return json.dumps(model.model_dump(mode="json"), separators=(",", ":"), sort_keys=True)


def _dump_json_list(values: list[str]) -> str:
    return json.dumps(values, separators=(",", ":"), sort_keys=True)


def _dump_model_list(values: Sequence[object]) -> str:
    return json.dumps(values, separators=(",", ":"), sort_keys=True)


def _load_json_list(payload_json: str, label: str) -> list[str]:
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError as error:
        raise CorruptStoredJobDiscoveryError(f"Stored {label} is invalid JSON") from error
    if not isinstance(payload, list) or not all(isinstance(item, str) for item in payload):
        raise CorruptStoredJobDiscoveryError(f"Stored {label} is not a string list")
    return payload


def _load_model_list(payload_json: str, label: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError as error:
        raise CorruptStoredJobDiscoveryError(f"Stored {label} is invalid JSON") from error
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise CorruptStoredJobDiscoveryError(f"Stored {label} is not an object list")
    return payload


def _load_versioned_model(
    model_type: type[_ModelT],
    payload_json: str,
    schema_version: int,
    label: str,
) -> _ModelT:
    if schema_version != SCHEMA_VERSION:
        raise CorruptStoredJobDiscoveryError(
            f"Stored {label} uses unsupported schema version {schema_version}"
        )
    return _load_model(model_type, payload_json, label)


def _load_model(model_type: type[_ModelT], payload_json: str, label: str) -> _ModelT:
    try:
        payload = json.loads(payload_json)
        if model_type is JobRecommendation and isinstance(payload, dict):
            score_payload = payload.get("score")
            legacy = (
                "feed_kind" not in payload
                or "visibility" not in payload
                or not isinstance(score_payload, dict)
                or score_payload.get("evaluation_policy_version") is None
            )
            if legacy:
                payload = {
                    **payload,
                    "earlier_policy": True,
                    "legacy_payload": json.loads(json.dumps(payload)),
                }
        return model_type.model_validate(payload)
    except (json.JSONDecodeError, TypeError, ValidationError, ValueError) as error:
        raise CorruptStoredJobDiscoveryError(
            f"Stored {label} is invalid or incompatible"
        ) from error


def _load_saved(row: tuple[Any, ...], label: str) -> SavedJob:
    (
        saved_id,
        user_id,
        job_id,
        availability,
        snapshot_json,
        snapshot_schema_version,
        saved_at,
        checked_at,
    ) = row
    if snapshot_schema_version != SAVED_SNAPSHOT_SCHEMA_VERSION:
        raise CorruptStoredJobDiscoveryError(
            f"Stored {label} uses unsupported snapshot schema version {snapshot_schema_version}"
        )
    snapshot = _load_model(DiscoveredJob, snapshot_json, f"{label} snapshot")
    try:
        return SavedJob.model_validate(
            {
                "id": saved_id,
                "user_id": user_id,
                "job_id": job_id,
                "availability": availability,
                "saved_at": saved_at,
                "checked_at": checked_at,
                "snapshot_schema_version": snapshot_schema_version,
                "posting_snapshot": snapshot.model_dump(mode="json"),
            }
        )
    except (TypeError, ValidationError, ValueError) as error:
        raise CorruptStoredJobDiscoveryError(
            f"Stored {label} is invalid or incompatible"
        ) from error


def _load_source(row: tuple[Any, ...]) -> SupportedJobSource:
    (
        source_id,
        connector_type,
        company_name,
        board_token,
        official_base_url,
        lever_api_region,
        enabled,
    ) = row
    try:
        return SupportedJobSource.model_validate(
            {
                "source_id": source_id,
                "connector_type": connector_type,
                "company_name": company_name,
                "board_token": board_token,
                "official_base_url": official_base_url,
                "lever_api_region": lever_api_region,
                "enabled": bool(enabled),
            }
        )
    except (TypeError, ValidationError, ValueError) as error:
        raise CorruptStoredJobDiscoveryError(
            f"Stored supported job source {source_id!r} is invalid or incompatible"
        ) from error


def _optional_datetime(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return value
    raise TypeError("timestamp values must be datetime, text, or None")


def _require_timezone_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
