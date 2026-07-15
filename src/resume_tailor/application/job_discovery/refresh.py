from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from resume_tailor.application.job_discovery.preferences import ProfileNotFoundError
from resume_tailor.domain.job_discovery.capabilities import ProfileCapabilityIndexBuilder
from resume_tailor.domain.job_discovery.deduplication import JobDeduplicator
from resume_tailor.domain.job_discovery.eligibility import EligibilityEvaluator
from resume_tailor.domain.job_discovery.ids import recommendation_id, run_id
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
    ProfileCapabilityIndex,
    RecommendationGroup,
    SourceJobRecord,
    SourceRecordWarning,
    SupportedJobSource,
)
from resume_tailor.domain.job_discovery.normalization import JobNormalizer
from resume_tailor.domain.job_discovery.requirements import RequirementExtractor
from resume_tailor.domain.job_discovery.scoring import (
    DeterministicExplanationBuilder,
    ScoringPolicy,
)
from resume_tailor.domain.models import MasterProfile
from resume_tailor.ports.interfaces import MasterProfileRepository
from resume_tailor.ports.job_discovery import (
    DiscoveredJobRepository,
    DiscoveryRunRepository,
    JobRecommendationRepository,
    JobSearchPreferencesRepository,
    JobSourceConnector,
    JobSourceEnvelopeError,
    JobSourceTransportError,
    SupportedJobSourceRepository,
)

ConnectorCollection = Mapping[
    ConnectorType,
    JobSourceConnector | Mapping[str, JobSourceConnector],
]
MAX_INITIAL_RECOMMENDATIONS = 10


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
    ) -> None:
        self._profiles = profiles
        self._preferences = preferences
        self._sources = sources
        self._connectors = connectors
        self._discovered_jobs = discovered_jobs
        self._recommendations = recommendations
        self._runs = runs
        self._normalizer = normalizer or JobNormalizer()
        self._deduplicator = deduplicator or JobDeduplicator()
        self._requirement_extractor = requirement_extractor or RequirementExtractor()
        self._capability_index_builder = capability_index_builder or ProfileCapabilityIndexBuilder()
        self._eligibility_evaluator = eligibility_evaluator or EligibilityEvaluator()
        self._scoring_policy = scoring_policy or ScoringPolicy()
        self._explanation_builder = explanation_builder or DeterministicExplanationBuilder()

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
        )
        try:
            return self._refresh_impl(
                user_id,
                profile_id,
                preferences,
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

    def _refresh_impl(
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
        self._runs.create(running)

        sources = sorted(
            self._sources.list_enabled(),
            key=lambda source: (source.source_id, source.connector_type.value),
        )
        if not sources:
            return self._finish(
                running,
                status=DiscoveryRunStatus.NO_SOURCES_CONFIGURED,
                completed_at=started_at,
            )

        raw_records: list[tuple[SupportedJobSource, SourceJobRecord]] = []
        warnings: list[str] = []
        errors: list[str] = []
        failed_sources: list[str] = []
        successful_sources = 0
        for source in sources:
            try:
                result = self._connector_for(source).fetch(source, fetched_at=started_at)
            except (JobSourceEnvelopeError, JobSourceTransportError) as error:
                errors.append(self._source_error(source, error))
                failed_sources.append(source.source_id)
                continue
            successful_sources += 1
            raw_records.extend((source, record) for record in result.records)
            warnings.extend(self._format_warnings(source, result.warnings))

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

        normalized = [
            self._normalize(source, record, fetched_at=started_at)
            for source, record in raw_records
        ]
        deduplicated = self._deduplicator.resolve(normalized)
        profile_index = self._capability_index_builder.build(profile)

        assessed: list[tuple[DiscoveredJob, EligibilityAssessment, JobScoreBreakdown]] = []
        for job in deduplicated.jobs:
            assessment = self._eligibility_evaluator.assess(
                job,
                preferences,
                as_of=started_at,
                profile=profile,
            )
            if assessment.status is EligibilityStatus.INELIGIBLE:
                continue
            score = self._scoring_policy.score(
                job,
                preferences,
                profile_index,
                as_of=started_at,
            )
            assessed.append((job, assessment, score))

        for job in deduplicated.jobs:
            self._discovered_jobs.upsert(job)

        recommendations = self._build_recommendations(
            identifier,
            profile,
            preferences,
            profile_index,
            assessed,
            created_at=started_at,
        )
        self._recommendations.replace_for_run(identifier, recommendations)
        status = (
            DiscoveryRunStatus.COMPLETED_WITH_WARNINGS
            if warnings or errors
            else DiscoveryRunStatus.COMPLETED
        )
        return self._finish(
            running,
            status=status,
            source_count=len(sources),
            sources_attempted=[source.source_id for source in sources],
            failed_sources=sorted(failed_sources),
            record_count=len(raw_records),
            retrieved_count=len(raw_records),
            normalized_count=len(normalized),
            duplicate_count=deduplicated.duplicate_count,
            eligibility_filtered_count=len(deduplicated.jobs) - len(assessed),
            scored_count=len(assessed),
            returned_count=len(recommendations),
            warning_count=len(warnings),
            source_warnings=warnings,
            warnings=warnings,
            error_messages=errors,
            completed_at=started_at,
        )

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

    def _normalize(
        self,
        source: SupportedJobSource,
        record: SourceJobRecord,
        *,
        fetched_at: datetime,
    ) -> DiscoveredJob:
        job = self._normalizer.normalize(record, source, fetched_at=fetched_at)
        requirements = self._requirement_extractor.extract(
            job.title,
            job.description,
            job.location.raw,
            job.work_arrangement,
        )
        return job.model_copy(update={"requirements": requirements})

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
        assessed: list[tuple[DiscoveredJob, EligibilityAssessment, JobScoreBreakdown]],
        *,
        created_at: datetime,
    ) -> list[JobRecommendation]:
        explanation_builder = self._explanation_builder
        if isinstance(explanation_builder, DeterministicExplanationBuilder):
            explanation_builder = DeterministicExplanationBuilder(preferences)
        ranked = sorted(
            assessed,
            key=lambda item: self._recommendation_sort_key(item[0], item[1], item[2], preferences),
        )[:MAX_INITIAL_RECOMMENDATIONS]
        recommendations: list[JobRecommendation] = []
        for rank, (job, eligibility, score) in enumerate(ranked, start=1):
            reasons, gaps = explanation_builder.reasons_and_gaps(
                job, job.requirements, profile_index
            )
            group = (
                RecommendationGroup.PRIMARY
                if job.role_family in preferences.role_family_priority
                else RecommendationGroup.FALLBACK
            )
            recommendations.append(
                JobRecommendation(
                    id=recommendation_id(
                        run_identifier,
                        job.id,
                        profile.version,
                        preferences.version,
                    ),
                    run_id=run_identifier,
                    user_id=profile.user_id,
                    profile_id=profile.id,
                    profile_version=profile.version,
                    preference_version=preferences.version,
                    job_id=job.id,
                    group=group,
                    primary_role_family=job.role_family,
                    eligibility=eligibility,
                    score=score,
                    reasons=reasons,
                    gaps=gaps,
                    rank=rank,
                    created_at=created_at,
                )
            )
        return recommendations

    @staticmethod
    def _recommendation_sort_key(
        job: DiscoveredJob,
        eligibility: EligibilityAssessment,
        score: JobScoreBreakdown,
        preferences: JobSearchPreferences,
    ) -> tuple[float, int, int, int, int, str, str, str]:
        preferred = {
            company.casefold().strip() for company in preferences.preferred_companies
        }
        role_order = {
            family: index for index, family in enumerate(preferences.role_family_priority)
        }
        role_index = (
            role_order.get(job.role_family)
            if job.role_family is not None
            else None
        )
        return (
            -score.total,
            0 if job.company_name.casefold().strip() in preferred else 1,
            0 if job.role_family in role_order else 1,
            role_index if role_index is not None else len(role_order),
            0 if eligibility.status is EligibilityStatus.ELIGIBLE else 1,
            job.normalized_company_name,
            job.normalized_title,
            job.id,
        )

    def _finish(self, running: DiscoveryRun, **updates: object) -> DiscoveryRun:
        complete = running.model_copy(update=updates)
        if complete.status in {
            DiscoveryRunStatus.NO_SOURCES_CONFIGURED,
            DiscoveryRunStatus.FAILED_ALL_SOURCES,
        }:
            self._recommendations.replace_for_run(complete.id, [])
        self._runs.complete(complete)
        return complete


__all__ = ["RefreshJobDiscoveryService"]
