from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from time import perf_counter

from resume_tailor.application.job_discovery.feed_services import FeedAssemblyService
from resume_tailor.application.job_discovery.preferences import ProfileNotFoundError
from resume_tailor.application.job_discovery.retrieval import RetrievalService
from resume_tailor.domain.job_discovery.capabilities import ProfileCapabilityIndexBuilder
from resume_tailor.domain.job_discovery.deduplication import JobDeduplicator
from resume_tailor.domain.job_discovery.eligibility import EligibilityEvaluator
from resume_tailor.domain.job_discovery.evaluation import JobEvaluation, JobEvaluator
from resume_tailor.domain.job_discovery.ids import run_id
from resume_tailor.domain.job_discovery.models import (
    ConnectorType,
    DiscoveredJob,
    DiscoveryRun,
    DiscoveryRunStatus,
    EligibilityStatus,
    JobRecommendation,
    JobSearchPreferences,
    NormalizedLocation,
    ProfileCapabilityIndex,
    SourceDefinition,
    SourceJobRecord,
    SourceRecordWarning,
    SupportedJobSource,
    WorkArrangement,
)
from resume_tailor.domain.job_discovery.normalization import JobNormalizer
from resume_tailor.domain.job_discovery.providers import RetrievalOutcome, SourceOutcome
from resume_tailor.domain.job_discovery.queries import (
    ExploreJobQuery,
    FeedKind,
    TailoredJobQuery,
)
from resume_tailor.domain.job_discovery.requirements import RequirementExtractor
from resume_tailor.domain.job_discovery.scoring import (
    DeterministicExplanationBuilder,
    ScoringPolicy,
)
from resume_tailor.domain.job_discovery.source_lifecycle import SourceIdentityAlias
from resume_tailor.domain.models import MasterProfile
from resume_tailor.ports.interfaces import MasterProfileRepository
from resume_tailor.ports.job_discovery import (
    AtomicJobDiscoveryPersistence,
    DiscoveredJobRepository,
    DiscoveryRunRepository,
    JobRecommendationRepository,
    JobSearchPreferencesRepository,
    JobSourceConnector,
    JobSourceEnvelopeError,
    JobSourceTransportError,
    SourceIdentityAliasRepository,
    SupportedJobSourceRepository,
)

ConnectorCollection = Mapping[
    ConnectorType,
    JobSourceConnector | Mapping[str, JobSourceConnector],
]


class RefreshJobDiscoveryService:
    """Orchestrate one deterministic, persisted discovery refresh."""

    def __init__(
        self,
        *,
        profiles: MasterProfileRepository,
        preferences: JobSearchPreferencesRepository,
        sources: SupportedJobSourceRepository,
        connectors: ConnectorCollection,
        discovered_jobs: DiscoveredJobRepository,
        recommendations: JobRecommendationRepository,
        runs: DiscoveryRunRepository,
        normalizer: JobNormalizer | None = None,
        deduplicator: JobDeduplicator | None = None,
        requirement_extractor: RequirementExtractor | None = None,
        capability_index_builder: ProfileCapabilityIndexBuilder | None = None,
        eligibility_evaluator: EligibilityEvaluator | None = None,
        scoring_policy: ScoringPolicy | None = None,
        explanation_builder: DeterministicExplanationBuilder | None = None,
        job_evaluator: JobEvaluator | None = None,
        atomic_persistence: AtomicJobDiscoveryPersistence | None = None,
        aliases: SourceIdentityAliasRepository | None = None,
    ) -> None:
        self._profiles = profiles
        self._preferences = preferences
        self._sources = sources
        self._connectors = connectors
        self._discovered_jobs = discovered_jobs
        self._recommendations = recommendations
        self._runs = runs
        self._requirement_extractor = requirement_extractor or RequirementExtractor()
        self._normalizer = normalizer or JobNormalizer(self._requirement_extractor)
        self._reconcile_normalized_requirements = normalizer is not None
        self._deduplicator = deduplicator or JobDeduplicator()
        self._capability_index_builder = capability_index_builder or ProfileCapabilityIndexBuilder()
        self._eligibility_evaluator = eligibility_evaluator or EligibilityEvaluator()
        self._scoring_policy = scoring_policy or ScoringPolicy()
        self._explanation_builder = explanation_builder or DeterministicExplanationBuilder()
        self._job_evaluator = job_evaluator or JobEvaluator(
            eligibility_evaluator=self._eligibility_evaluator,
            requirement_extractor=self._requirement_extractor,
        )
        self._feed_assembly = FeedAssemblyService()
        self._atomic_persistence = atomic_persistence
        self._aliases = aliases
        self._last_evaluations: list[JobEvaluation] = []
        self._last_phase_timings_seconds: dict[str, float] = {}

    @property
    def last_phase_timings_seconds(self) -> dict[str, float]:
        """Return non-persisted runtime timings for the most recent refresh."""

        return dict(self._last_phase_timings_seconds)

    def refresh(
        self,
        user_id: str,
        profile_id: str,
        preferences: JobSearchPreferences,
        *,
        started_at: datetime,
    ) -> DiscoveryRun:
        profile = self._load_owned_profile(user_id, profile_id)
        if preferences.user_id != user_id or preferences.profile_id != profile_id:
            raise ValueError("Job-search preferences do not belong to the requested user/profile.")
        identifier = run_id(
            user_id,
            profile_id,
            profile.version,
            preferences.version,
            started_at,
            FeedKind.TAILORED.value,
        )
        try:
            return self._refresh_impl(
                user_id,
                profile_id,
                preferences,
                query=TailoredJobQuery(preferences=preferences),
                feed_kind=FeedKind.TAILORED,
                started_at=started_at,
            )
        except Exception:
            persisted = self._runs.get(identifier)
            if persisted is None or persisted.status is not DiscoveryRunStatus.RUNNING:
                raise
            failed = persisted.model_copy(
                update={
                    "status": DiscoveryRunStatus.FAILED_ALL_SOURCES,
                    "completed_at": started_at,
                    "error_messages": ["refresh processing failed"],
                    "warning_count": persisted.warning_count,
                }
            )
            self._recommendations.replace_for_run(identifier, [])
            self._runs.complete(failed)
            return failed

    def refresh_explore(
        self,
        user_id: str,
        *,
        sectors: list[str],
        profile_id: str,
        started_at: datetime,
        title_keywords: list[str] | None = None,
        locations: list[str] | None = None,
        page_size: int = 100,
        max_posting_age_days: int | None = None,
        source_restrictions: list[str] | None = None,
    ) -> DiscoveryRun:
        self._load_owned_profile(user_id, profile_id)
        preferences = self._preferences.get_current(user_id, profile_id)
        if preferences is None:
            preferences = JobSearchPreferences(
                user_id=user_id,
                profile_id=profile_id,
                version=0,
                role_family_priority=[],
                target_titles=list(title_keywords or []),
                related_title_variants=[],
                technical_themes=[],
                career_interests=[],
                job_levels=[],
                locations=[NormalizedLocation(raw=value) for value in locations or []],
                work_arrangement=WorkArrangement.UNKNOWN,
                preferred_companies=[],
                excluded_companies=[],
                max_posting_age_days=max_posting_age_days,
                created_at=started_at,
            )
        query = ExploreJobQuery(
            sectors=sectors,
            title_keywords=list(title_keywords or []),
            locations=list(locations or []),
            max_posting_age_days=max_posting_age_days,
            source_restrictions=list(source_restrictions or []),
            page_size=page_size,
            profile_id=profile_id,
            evaluate_fit=True,
        )
        return self._refresh_impl(
            user_id,
            profile_id,
            preferences,
            query=query,
            feed_kind=FeedKind.EXPLORE,
            started_at=started_at,
        )

    def persist_retrieval_for_profile(
        self,
        user_id: str,
        profile_id: str,
        *,
        query: ExploreJobQuery,
        retrieval: RetrievalOutcome,
        started_at: datetime,
    ) -> DiscoveryRun:
        """Persist already-retrieved records through the normal refresh pipeline."""

        self._load_owned_profile(user_id, profile_id)
        preferences = self._preferences.get_current(user_id, profile_id)
        if preferences is None:
            preferences = JobSearchPreferences(
                user_id=user_id,
                profile_id=profile_id,
                version=0,
                role_family_priority=[],
                target_titles=list(query.title_keywords),
                related_title_variants=[],
                technical_themes=[],
                career_interests=[],
                job_levels=[],
                locations=[NormalizedLocation(raw=value) for value in query.locations],
                work_arrangement=WorkArrangement.UNKNOWN,
                preferred_companies=[],
                excluded_companies=[],
                max_posting_age_days=query.max_posting_age_days,
                created_at=started_at,
            )
        if not query.source_restrictions:
            retrieved_source_ids = sorted(
                {
                    item.source_id
                    for item in retrieval.source_outcomes
                    if item.source_id
                }
            )
            if retrieved_source_ids:
                query = query.model_copy(update={"source_restrictions": retrieved_source_ids})
        return self._refresh_impl(
            user_id,
            profile_id,
            preferences,
            query=query,
            feed_kind=FeedKind.EXPLORE,
            started_at=started_at,
            retrieval_override=retrieval,
        )

    def _refresh_impl(
        self,
        user_id: str,
        profile_id: str,
        preferences: JobSearchPreferences,
        *,
        query: TailoredJobQuery | ExploreJobQuery,
        feed_kind: FeedKind,
        started_at: datetime,
        retrieval_override: RetrievalOutcome | None = None,
    ) -> DiscoveryRun:
        phase_timings: dict[str, float] = {}
        phase_started = perf_counter()
        profile = self._load_owned_profile(user_id, profile_id)
        if preferences.user_id != user_id or preferences.profile_id != profile_id:
            raise ValueError("Job-search preferences do not belong to the requested user/profile.")
        phase_timings["profile_and_query"] = perf_counter() - phase_started

        identifier = run_id(
            user_id,
            profile_id,
            profile.version,
            preferences.version,
            started_at,
            feed_kind.value,
        )
        running = DiscoveryRun(
            id=identifier,
            user_id=user_id,
            profile_id=profile_id,
            profile_version=profile.version,
            preference_version=preferences.version,
            status=DiscoveryRunStatus.RUNNING,
            started_at=started_at,
            completed_at=None,
            source_count=0,
            record_count=0,
            warning_count=0,
            error_messages=[],
        )
        if self._atomic_persistence is None:
            self._runs.create(running)

        sources = sorted(
            [
                source
                for source in self._sources.list_enabled()
                if not query.source_restrictions
                or source.source_id in query.source_restrictions
            ],
            key=lambda source: (source.source_id, source.connector_type.value),
        )
        if not sources:
            return self._finish(
                running,
                status=DiscoveryRunStatus.NO_SOURCES_CONFIGURED,
                completed_at=started_at,
            )

        phase_started = perf_counter()
        retrieval = retrieval_override or RetrievalService(
            sources=sources, connectors=self._connectors
        ).retrieve(query, fetched_at=started_at)
        phase_timings["source_retrieval_and_parsing"] = perf_counter() - phase_started
        raw_records = [(item.source, item.record) for item in retrieval.records]
        warnings = self._retrieval_warnings(retrieval.source_outcomes)
        errors = self._retrieval_errors(retrieval.source_outcomes)
        failed_sources = sorted(
            item.source_id for item in retrieval.source_outcomes if item.status.value == "failed"
        )
        successful_sources = sum(
            item.status.value != "failed" for item in retrieval.source_outcomes
        )

        warnings.sort()
        errors.sort()
        if successful_sources == 0:
            return self._finish(
                running,
                status=DiscoveryRunStatus.FAILED_ALL_SOURCES,
                source_count=len(sources),
                sources_attempted=[source.source_id for source in sources],
                failed_sources=sorted(failed_sources),
                record_count=0,
                warning_count=len(warnings),
                source_warnings=warnings,
                warnings=warnings,
                error_messages=errors,
                completed_at=started_at,
            )

        phase_started = perf_counter()
        normalized = self._normalize_records(raw_records, fetched_at=started_at)
        phase_timings["normalization"] = perf_counter() - phase_started
        phase_started = perf_counter()
        retained_jobs = self._retained_jobs_for_failed_sources(
            user_id,
            profile_id,
            feed_kind,
            failed_sources=set(failed_sources),
            explore_sector=(
                query.sectors[0]
                if isinstance(query, ExploreJobQuery) and len(query.sectors) == 1
                else None
            ),
        )
        normalized.extend(retained_jobs)
        if retained_jobs:
            company_by_source = {source.source_id: source.company_name for source in sources}
            retained_sources = sorted({job.source.source_id for job in retained_jobs})
            warnings.extend(
                f"{company_by_source.get(source_id, source_id)} could not refresh — "
                "showing previous results."
                for source_id in retained_sources
            )
            warnings.sort()
        phase_timings["cached_source_recovery"] = perf_counter() - phase_started
        phase_started = perf_counter()
        deduplicated = self._deduplicator.resolve(normalized)
        phase_timings["deduplication"] = perf_counter() - phase_started
        phase_started = perf_counter()
        profile_index = self._capability_index_builder.build(profile)
        phase_timings["profile_capability_index"] = perf_counter() - phase_started

        phase_started = perf_counter()
        assessed: list[tuple[DiscoveredJob, JobEvaluation]] = []
        for job in deduplicated.jobs:
            evaluation = self._job_evaluator.evaluate(
                job,
                preferences,
                profile_index,
                as_of=started_at,
                profile=profile,
            )
            assessed.append((job, evaluation))
        self._last_evaluations = [evaluation for _job, evaluation in assessed]
        phase_timings["evaluation_and_scoring"] = perf_counter() - phase_started

        if self._atomic_persistence is None:
            for job in deduplicated.jobs:
                self._discovered_jobs.upsert(job)

        phase_started = perf_counter()
        assembly = self._feed_assembly.build_recommendations(
            identifier,
            profile=profile,
            preferences=preferences,
            assessed=assessed,
            feed_kind=feed_kind,
            created_at=started_at,
            explore_sector=(
                query.sectors[0]
                if isinstance(query, ExploreJobQuery) and len(query.sectors) == 1
                else None
            ),
        )
        phase_timings["feed_assembly"] = perf_counter() - phase_started
        recommendations = assembly.recommendations
        aliases = [_identity_alias(job, started_at) for job in deduplicated.jobs]
        status = (
            DiscoveryRunStatus.COMPLETED_WITH_WARNINGS
            if warnings or errors
            else DiscoveryRunStatus.COMPLETED
        )
        complete = running.model_copy(
            update={
                "status": status,
                "source_count": len(sources),
                "sources_attempted": [source.source_id for source in sources],
                "failed_sources": sorted(failed_sources),
                "record_count": len(raw_records),
                "retrieved_count": retrieval.retrieved_count,
                "normalized_count": len(normalized),
                "duplicate_count": deduplicated.duplicate_count,
                "eligibility_filtered_count": sum(
                    evaluation.eligibility.status is EligibilityStatus.INELIGIBLE
                    for _job, evaluation in assessed
                ),
                "scored_count": len(assessed),
                "returned_count": sum(
                    item.visibility.value == "visible" for item in recommendations
                ),
                "warning_count": len(warnings),
                "source_warnings": warnings,
                "warnings": warnings,
                "error_messages": errors,
                "source_outcomes": [
                    item.model_dump(mode="json") for item in retrieval.source_outcomes
                ],
                "completed_at": started_at,
            }
        )
        if self._atomic_persistence is not None:
            phase_started = perf_counter()
            self._atomic_persistence.persist_refresh(
                complete, deduplicated.jobs, recommendations, aliases
            )
            phase_timings["persistence"] = perf_counter() - phase_started
            self._last_phase_timings_seconds = dict(phase_timings)
            return complete
        phase_started = perf_counter()
        self._recommendations.replace_for_run(identifier, recommendations)
        self._persist_aliases(aliases)
        result = self._finish(
            running,
            **complete.model_dump(
                exclude={
                    "id",
                    "user_id",
                    "profile_id",
                    "profile_version",
                    "preference_version",
                    "started_at",
                }
            ),
        )
        phase_timings["persistence"] = perf_counter() - phase_started
        self._last_phase_timings_seconds = dict(phase_timings)
        return result

    def _retained_jobs_for_failed_sources(
        self,
        user_id: str,
        profile_id: str,
        feed_kind: FeedKind,
        *,
        failed_sources: set[str],
        explore_sector: str | None,
    ) -> list[DiscoveredJob]:
        if not failed_sources:
            return []
        prior = [
            item
            for item in self._recommendations.list_for_feed(
                user_id, feed_kind.value, include_excluded=True
            )
            if item.profile_id == profile_id
            and (feed_kind is not FeedKind.EXPLORE or item.explore_sector == explore_sector)
        ]
        if not prior:
            return []
        latest_created_at = max(item.created_at for item in prior)
        latest_run_id = max(
            item.run_id for item in prior if item.created_at == latest_created_at
        )
        recommendations = [
            item for item in prior if item.run_id == latest_run_id
        ]
        get_many = getattr(self._discovered_jobs, "get_many", None)
        if callable(get_many):
            jobs = get_many(
                [item.job_id for item in recommendations],
                source_ids=failed_sources,
            )
            jobs_by_id = {job.id: job for job in jobs}
        else:
            jobs_by_id = {
                item.job_id: job
                for item in recommendations
                if (job := self._discovered_jobs.get(item.job_id)) is not None
            }
        retained: list[DiscoveredJob] = []
        for recommendation in recommendations:
            job = jobs_by_id.get(recommendation.job_id)
            if job is not None and job.source.source_id in failed_sources:
                retained.append(job)
        return retained

    def _load_owned_profile(self, user_id: str, profile_id: str) -> MasterProfile:
        profile = self._profiles.get(profile_id)
        if profile is None or profile.user_id != user_id:
            raise ProfileNotFoundError(
                f"Profile {profile_id!r} was not found for user {user_id!r}."
            )
        return profile

    def _connector_for(self, source: SupportedJobSource) -> JobSourceConnector:
        configured = self._connectors.get(source.connector_type)
        if configured is None:
            raise JobSourceTransportError("job source connector is not configured")
        if isinstance(configured, Mapping):
            connector = configured.get(source.source_id)
            if connector is None:
                raise JobSourceTransportError("job source connector is not configured")
            return connector
        return configured

    @staticmethod
    def _retrieval_warnings(outcomes: list[SourceOutcome]) -> list[str]:
        values = []
        for outcome in outcomes:
            for warning in outcome.warnings:
                values.append(
                    "|".join(
                        (
                            warning.source_id,
                            warning.code,
                            warning.external_job_id or "",
                            warning.message,
                        )
                    )
                )
        return sorted(values)

    @staticmethod
    def _retrieval_errors(outcomes: list[SourceOutcome]) -> list[str]:
        return sorted(
            f"{error.source_id}: {error.message}"
            for outcome in outcomes
            for error in outcome.errors
        )

    def _normalize(
        self,
        source: SourceDefinition,
        record: SourceJobRecord,
        *,
        fetched_at: datetime,
    ) -> DiscoveredJob:
        job = self._normalizer.normalize(record, source, fetched_at=fetched_at)
        if not self._reconcile_normalized_requirements:
            return job
        requirements = self._requirement_extractor.extract(
            job.title,
            job.description,
            job.location.raw,
            job.work_arrangement,
        )
        return job.model_copy(update={"requirements": requirements})

    def _normalize_records(
        self,
        raw_records: list[tuple[SourceDefinition, SourceJobRecord]],
        *,
        fetched_at: datetime,
    ) -> list[DiscoveredJob]:
        return [
            self._normalize(source, record, fetched_at=fetched_at)
            for source, record in raw_records
        ]

    @staticmethod
    def _source_error(source: SupportedJobSource, error: Exception) -> str:
        if isinstance(error, JobSourceEnvelopeError):
            reason = "malformed provider response"
        elif error.__class__.__name__ == "JobSourceAuthenticationError":
            reason = "provider authentication failed"
        elif error.__class__.__name__ == "JobSourceRateLimitedError":
            reason = "provider rate limit reached"
        elif error.__class__.__name__ == "JobSourceNotFoundError":
            reason = "provider resource was not found"
        else:
            reason = "provider transport failed"
        return f"{source.source_id}: {reason}"

    @staticmethod
    def _format_warnings(
        source: SupportedJobSource, warnings: list[SourceRecordWarning]
    ) -> list[str]:
        return [
            "|".join(
                (
                    source.source_id,
                    warning.code.value,
                    warning.external_job_id or "",
                    warning.message,
                )
            )
            for warning in warnings
        ]

    def _build_recommendations(
        self,
        run_identifier: str,
        profile: MasterProfile,
        preferences: JobSearchPreferences,
        profile_index: ProfileCapabilityIndex,
        assessed: list[tuple[DiscoveredJob, JobEvaluation]],
        *,
        created_at: datetime,
    ) -> list[JobRecommendation]:
        return self._feed_assembly.build_recommendations(
            run_identifier,
            profile=profile,
            preferences=preferences,
            assessed=assessed,
            feed_kind=FeedKind.TAILORED,
            created_at=created_at,
        ).recommendations

    def _finish(self, running: DiscoveryRun, **updates: object) -> DiscoveryRun:
        complete = running.model_copy(update=updates)
        if complete.status in {
            DiscoveryRunStatus.NO_SOURCES_CONFIGURED,
            DiscoveryRunStatus.FAILED_ALL_SOURCES,
        }:
            if self._atomic_persistence is None:
                self._recommendations.replace_for_run(complete.id, [])
        if self._atomic_persistence is None:
            self._runs.complete(complete)
        else:
            self._atomic_persistence.persist_refresh(complete, [], [], [])
        return complete

    def _persist_aliases(self, aliases: list[SourceIdentityAlias]) -> None:
        repository = getattr(self, "_aliases", None)
        if repository is not None:
            for alias in aliases:
                repository.upsert(alias)


def _identity_alias(job: DiscoveredJob, created_at: datetime) -> SourceIdentityAlias:
    first_party = job.source.connector_type.value == "first_party"
    kind = "canonical_detail" if first_party else "external"
    canonical = job.official_url if first_party else None
    return SourceIdentityAlias(
        source_id=job.source.source_id,
        identity_kind=kind,
        identity_value=job.official_url if first_party else job.external_job_id,
        external_identity=job.external_job_id,
        requisition_identity=job.requisition_id,
        application_identity=job.application_url,
        canonical_detail_identity=canonical,
        job_id=job.id,
        created_at=created_at,
    )


__all__ = ["RefreshJobDiscoveryService"]
