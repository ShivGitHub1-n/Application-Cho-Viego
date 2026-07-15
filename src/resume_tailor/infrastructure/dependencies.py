from __future__ import annotations

import httpx

from resume_tailor.api.dependencies import JobDiscoveryServiceBundle
from resume_tailor.application.cover_letter import CoverLetterService
from resume_tailor.application.job_discovery.confirmation import ConfirmJobSearchPreferencesService
from resume_tailor.application.job_discovery.preferences import SuggestJobSearchPreferencesService
from resume_tailor.application.job_discovery.queries import (
    GetCurrentJobSearchPreferencesService,
    GetDiscoveryRunService,
)
from resume_tailor.application.job_discovery.refresh import RefreshJobDiscoveryService
from resume_tailor.application.llm_services import HybridLlmServices
from resume_tailor.application.services import TailorResumeService
from resume_tailor.domain.job_discovery.models import ConnectorType, SupportedJobSource
from resume_tailor.domain.job_discovery.preferences import DeterministicJobSearchPreferenceSuggester
from resume_tailor.domain.llm_models import LanguageModelError
from resume_tailor.infrastructure.config import Settings
from resume_tailor.infrastructure.cover_letter_rendering import CoverLetterRenderer
from resume_tailor.infrastructure.gemini_adapter import GeminiResumeLanguageModel
from resume_tailor.infrastructure.job_discovery_sqlite import (
    SQLiteDiscoveredJobRepository,
    SQLiteDiscoveryRunRepository,
    SQLiteJobRecommendationRepository,
    SQLiteJobSearchPreferencesRepository,
    SQLiteSupportedJobSourceRepository,
)
from resume_tailor.infrastructure.job_sources.greenhouse import GreenhouseConnector
from resume_tailor.infrastructure.job_sources.lever import LeverConnector
from resume_tailor.infrastructure.job_sources.registry import load_source_registry
from resume_tailor.infrastructure.optimization import (
    DeterministicResumeOptimizer,
    EvidenceBoundResumeWriter,
)
from resume_tailor.infrastructure.profile_repository import SQLiteMasterProfileRepository
from resume_tailor.ports.interfaces import ResumeLanguageModel


class _ConfiguredSourceRepository:
    """Expose only the source registry supplied for this service bundle."""

    def __init__(self, sources: list[SupportedJobSource]) -> None:
        self._sources = tuple(
            sorted(sources, key=lambda source: (source.source_id, source.connector_type.value))
        )

    def list_enabled(self) -> list[SupportedJobSource]:
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
        renderer=CoverLetterRenderer(),
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
    source_repository = SQLiteSupportedJobSourceRepository(database)

    registry_configuration = resolved_settings.job_discovery_source_registry_path
    configured_sources = (
        load_source_registry(registry_configuration) if registry_configuration else []
    )
    for source in configured_sources:
        source_repository.save(source)

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
    return JobDiscoveryServiceBundle(
        suggest_preferences=SuggestJobSearchPreferencesService(
            profiles,
            DeterministicJobSearchPreferenceSuggester(),
        ),
        refresh=RefreshJobDiscoveryService(
            profiles=profiles,
            preferences=preference_repository,
            sources=(
                _ConfiguredSourceRepository(configured_sources)
                if resolved_settings.job_discovery_enabled
                else _ConfiguredSourceRepository([])
            ),
            connectors={
                ConnectorType.GREENHOUSE: greenhouse,
                ConnectorType.LEVER: lever,
            },
            discovered_jobs=job_repository,
            recommendations=recommendation_repository,
            runs=run_repository,
        ),
        confirm_preferences=ConfirmJobSearchPreferencesService(
            profiles,
            preference_repository,
        ),
        current_preferences=GetCurrentJobSearchPreferencesService(preference_repository),
        runs=GetDiscoveryRunService(run_repository, recommendation_repository),
        close_resources=client.close,
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
