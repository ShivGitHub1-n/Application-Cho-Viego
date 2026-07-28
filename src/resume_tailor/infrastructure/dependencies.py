from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import httpx

from resume_tailor.api.dependencies import JobDiscoveryServiceBundle
from resume_tailor.application.cover_letter import CoverLetterService
from resume_tailor.application.job_discovery.confirmation import ConfirmJobSearchPreferencesService
from resume_tailor.application.job_discovery.preferences import SuggestJobSearchPreferencesService
from resume_tailor.application.job_discovery.queries import (
    GetCurrentJobSearchPreferencesService,
    GetDiscoveryRunService,
    GetJobFeedService,
)
from resume_tailor.application.job_discovery.refresh import RefreshJobDiscoveryService
from resume_tailor.application.job_discovery.retrieval import RetrievalService
from resume_tailor.application.job_discovery.saved import (
    CheckSavedJobAvailabilityService,
    SaveJobService,
)
from resume_tailor.application.job_discovery.source_health import SourceHealthQueryService
from resume_tailor.application.job_discovery.source_refresh import SourceRefreshOrchestrator
from resume_tailor.application.llm_services import HybridLlmServices
from resume_tailor.application.services import TailorResumeService
from resume_tailor.domain.job_discovery.models import (
    ConnectorType,
    FirstPartySource,
    SourceDefinition,
    SupportedJobSource,
)
from resume_tailor.domain.job_discovery.preferences import DeterministicJobSearchPreferenceSuggester
from resume_tailor.domain.job_discovery.providers import RetrievalOutcome
from resume_tailor.domain.job_discovery.queries import ExploreJobQuery
from resume_tailor.domain.llm_models import LanguageModelError
from resume_tailor.infrastructure.config import Settings
from resume_tailor.infrastructure.cover_letter_rendering import CoverLetterRenderer
from resume_tailor.infrastructure.gemini_adapter import GeminiResumeLanguageModel
from resume_tailor.infrastructure.job_discovery_sqlite import (
    SQLiteAtomicJobDiscoveryPersistence,
    SQLiteDiscoveredJobRepository,
    SQLiteDiscoveryRunRepository,
    SQLiteJobRecommendationRepository,
    SQLiteJobSearchPreferencesRepository,
    SQLiteSavedJobRepository,
    SQLiteSourceIdentityAliasRepository,
    SQLiteSourceRuntimeStateRepository,
    SQLiteSupportedJobSourceRepository,
)
from resume_tailor.infrastructure.job_sources.browser_fallback import BoundedBrowserFallback
from resume_tailor.infrastructure.job_sources.first_party import FirstPartyCareerConnector
from resume_tailor.infrastructure.job_sources.greenhouse import GreenhouseConnector
from resume_tailor.infrastructure.job_sources.lever import LeverConnector
from resume_tailor.infrastructure.job_sources.registry import (
    SourceConfigurationError,
    compile_runtime_sources,
    load_company_source_registry,
    load_source_registry,
)
from resume_tailor.infrastructure.job_sources.robots import RobotsChecker
from resume_tailor.infrastructure.job_sources.safe_http import SafeHttpClient, UrlAccessPolicy
from resume_tailor.infrastructure.optimization import (
    DeterministicResumeOptimizer,
    EvidenceBoundResumeWriter,
)
from resume_tailor.infrastructure.profile_repository import SQLiteMasterProfileRepository
from resume_tailor.ports.interfaces import ResumeLanguageModel


class _ConfiguredSourceRepository:
    """Expose only the source registry supplied for this service bundle."""

    def __init__(self, sources: list[SourceDefinition]) -> None:
        self._sources = tuple(
            sorted(sources, key=lambda source: (source.source_id, source.connector_type.value))
        )

    def list_enabled(self) -> list[SourceDefinition]:
        return [source.model_copy(deep=True) for source in self._sources]


def create_tailor_service(settings: Settings | None = None) -> TailorResumeService:
    resolved_settings = settings or Settings()
    language_model = _create_language_model(resolved_settings)
    hybrid_services = HybridLlmServices(
        language_model=language_model,
        retry_count=resolved_settings.llm_retry_count,
        max_calls=resolved_settings.llm_max_calls_per_generation,
        enable_opportunity_analysis=resolved_settings.llm_enable_opportunity_analysis,
        enable_composition=resolved_settings.llm_enable_composition,
        enable_bullet_rewrite=resolved_settings.llm_enable_bullet_rewrite,
    )
    cover_letter_service = CoverLetterService(
        language_model=language_model if resolved_settings.llm_enable_cover_letter else None,
        renderer=cast(Any, CoverLetterRenderer()),
    )
    return TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
        hybrid_services=hybrid_services,
        cover_letter_service=cover_letter_service,
    )


def create_profile_repository(settings: Settings | None = None) -> SQLiteMasterProfileRepository:
    resolved_settings = settings or Settings()
    return SQLiteMasterProfileRepository(
        resolved_settings.app_data_directory / resolved_settings.profile_store_filename
    )


def create_job_discovery_services(
    settings: Settings | None = None,
) -> JobDiscoveryServiceBundle:
    resolved_settings = settings or Settings()
    database = resolved_settings.app_data_directory / resolved_settings.profile_store_filename
    profiles = SQLiteMasterProfileRepository(database)
    preference_repository = SQLiteJobSearchPreferencesRepository(database)
    job_repository = SQLiteDiscoveredJobRepository(database)
    recommendation_repository = SQLiteJobRecommendationRepository(database)
    run_repository = SQLiteDiscoveryRunRepository(database)
    saved_job_repository = SQLiteSavedJobRepository(database)
    source_repository = SQLiteSupportedJobSourceRepository(database)
    atomic_persistence = SQLiteAtomicJobDiscoveryPersistence(database)
    alias_repository = SQLiteSourceIdentityAliasRepository(database)

    registry_configuration = resolved_settings.job_discovery_source_registry_path
    configured_sources: list[SourceDefinition] = []
    if registry_configuration:
        try:
            company_registry = load_company_source_registry(registry_configuration)
        except SourceConfigurationError:
            # Preserve the legacy explicit-provider configuration during the
            # transition; the approved company registry remains preferred.
            configured_sources = [*load_source_registry(registry_configuration)]
        else:
            configured_sources = compile_runtime_sources(company_registry)
    for source in configured_sources:
        if isinstance(source, SupportedJobSource):
            source_repository.save(source)
    configured_source_repository = _ConfiguredSourceRepository(
        configured_sources if resolved_settings.job_discovery_enabled else []
    )

    client = httpx.Client()
    greenhouse = GreenhouseConnector(
        client,
        timeout=resolved_settings.job_discovery_source_timeout_seconds,
        api_base_url=str(resolved_settings.job_discovery_greenhouse_api_base_url),
    )
    lever = LeverConnector(
        client,
        timeout=resolved_settings.job_discovery_source_timeout_seconds,
        page_size=resolved_settings.job_discovery_source_page_size,
        max_pages=resolved_settings.job_discovery_source_max_pages,
        global_api_base_url=resolved_settings.job_discovery_lever_global_api_base_url,
        eu_api_base_url=resolved_settings.job_discovery_lever_eu_api_base_url,
    )
    first_party_connectors: dict[str, FirstPartyCareerConnector] = {}
    safe_clients: list[SafeHttpClient] = []
    for source in configured_sources:
        if not isinstance(source, FirstPartySource):
            continue
        policy = UrlAccessPolicy(
            allowed_hosts=set(source.source_plan.navigation_hosts),
            redirect_hosts=set(source.source_plan.redirect_hosts),
            allowed_path_patterns=[
                *source.source_plan.allowed_job_path_patterns,
                r"^/robots\.txt$",
            ],
        )
        safe_client = SafeHttpClient(policy)
        safe_clients.append(safe_client)
        robots_checker = RobotsChecker(safe_client)
        first_party_connectors[source.source_id] = FirstPartyCareerConnector(
            safe_client,
            robots_checker=robots_checker,
            browser_fallback=BoundedBrowserFallback(robots_checker=robots_checker),
        )

    def close_resources() -> None:
        client.close()
        for safe_client in safe_clients:
            safe_client.close()

    connector_collection = {
        ConnectorType.GREENHOUSE: greenhouse,
        ConnectorType.LEVER: lever,
        ConnectorType.FIRST_PARTY: cast(Any, first_party_connectors),
    }
    runtime_states = SQLiteSourceRuntimeStateRepository(database)
    refresh_service = RefreshJobDiscoveryService(
        profiles=profiles,
        preferences=preference_repository,
        sources=cast(Any, configured_source_repository),
        connectors=connector_collection,
        discovered_jobs=job_repository,
        recommendations=recommendation_repository,
        runs=run_repository,
        atomic_persistence=atomic_persistence,
        aliases=alias_repository,
    )

    def persist_for_profiles(
        query: ExploreJobQuery, retrieval: RetrievalOutcome, started_at: datetime
    ) -> None:
        for profile in profiles.list_all():
            refresh_service.persist_retrieval_for_profile(
                profile.user_id,
                profile.id,
                query=query,
                retrieval=retrieval,
                started_at=started_at,
            )

    source_refresh = SourceRefreshOrchestrator(
        sources=configured_sources if resolved_settings.job_discovery_enabled else [],
        retrieval_factory=cast(
            Any,
            lambda selected: RetrievalService(
                sources=selected,
                connectors=cast(Any, connector_collection),
                max_pages=resolved_settings.job_discovery_source_max_pages,
                max_records_per_source=(
                    resolved_settings.job_discovery_source_page_size
                    * resolved_settings.job_discovery_source_max_pages
                ),
            ),
        ),
        runtime_states=runtime_states,
        now=lambda: datetime.now(UTC),
        max_sources=resolved_settings.job_discovery_source_max_pages,
        persist_retrieval=persist_for_profiles,
    )

    return JobDiscoveryServiceBundle(
        suggest_preferences=SuggestJobSearchPreferencesService(
            profiles,
            DeterministicJobSearchPreferenceSuggester(),
        ),
        refresh=refresh_service,
        confirm_preferences=ConfirmJobSearchPreferencesService(
            profiles,
            preference_repository,
        ),
        current_preferences=GetCurrentJobSearchPreferencesService(preference_repository),
        runs=GetDiscoveryRunService(run_repository, recommendation_repository),
        feed_queries=GetJobFeedService(recommendation_repository, run_repository),
        save=SaveJobService(job_repository, saved_job_repository),
        check_saved_availability=CheckSavedJobAvailabilityService(
            saved_job_repository,
            cast(Any, configured_source_repository),
            {ConnectorType.GREENHOUSE: greenhouse, ConnectorType.LEVER: lever},
        ),
        source_health=SourceHealthQueryService(configured_sources, runtime_states),
        source_refresh=source_refresh,
        close_resources=close_resources,
    )


def _create_language_model(settings: Settings) -> ResumeLanguageModel | None:
    enabled = any(
        [
            settings.llm_enable_opportunity_analysis,
            settings.llm_enable_composition,
            settings.llm_enable_bullet_rewrite,
            settings.llm_enable_shortening,
            settings.llm_enable_cover_letter,
        ]
    )
    if not enabled:
        return None
    try:
        return GeminiResumeLanguageModel(settings)
    except LanguageModelError:
        if settings.llm_deterministic_fallback:
            return None
        raise
