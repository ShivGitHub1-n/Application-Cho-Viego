from __future__ import annotations

import os
from pathlib import Path

import httpx

from resume_tailor.api.dependencies import JobDiscoveryServiceBundle
from resume_tailor.application.cover_letter import CoverLetterService
from resume_tailor.application.generated_artifact import ResumeGenerationConfiguration
from resume_tailor.application.generation_diagnostics import GenerationTelemetry
from resume_tailor.application.job_discovery.confirmation import ConfirmJobSearchPreferencesService
from resume_tailor.application.job_discovery.preferences import SuggestJobSearchPreferencesService
from resume_tailor.application.job_discovery.queries import (
    GetCurrentJobSearchPreferencesService,
    GetDiscoveryRunService,
)
from resume_tailor.application.job_discovery.refresh import RefreshJobDiscoveryService
from resume_tailor.application.job_discovery.saved import (
    CheckSavedJobAvailabilityService,
    SaveJobService,
)
from resume_tailor.application.llm_services import HybridLlmServices
from resume_tailor.application.resume_composition import DeterministicResumeComposer
from resume_tailor.application.role_classification import (
    HybridRoleClassifier,
    HybridRoleOpportunityAnalyzer,
    RoleClassificationCacheIdentity,
)
from resume_tailor.application.services import TailorResumeService
from resume_tailor.domain.hybrid_resume import (
    RESUME_WRITING_CONTRACT_VERSION,
    RESUME_WRITING_POLICY_VERSION,
)
from resume_tailor.domain.job_discovery.models import ConnectorType, SupportedJobSource
from resume_tailor.domain.job_discovery.preferences import DeterministicJobSearchPreferenceSuggester
from resume_tailor.domain.llm_models import LanguageModelError
from resume_tailor.domain.resume_composition import RESUME_COMPOSITION_CONTRACT_VERSION
from resume_tailor.infrastructure.application_data import (
    application_database_path,
    migrate_legacy_application_database,
    repository_local_legacy_database,
)
from resume_tailor.infrastructure.artifact_rendering import TemplateV1ArtifactRenderer
from resume_tailor.infrastructure.composition_page_fit import TemplateV1PageFitEvaluator
from resume_tailor.infrastructure.config import Settings
from resume_tailor.infrastructure.cover_letter_rendering import CoverLetterRenderer
from resume_tailor.infrastructure.gemini_adapter import GeminiResumeLanguageModel
from resume_tailor.infrastructure.job_discovery_sqlite import (
    SQLiteDiscoveredJobRepository,
    SQLiteDiscoveryRunRepository,
    SQLiteJobRecommendationRepository,
    SQLiteJobSearchPreferencesRepository,
    SQLiteSavedJobRepository,
    SQLiteSupportedJobSourceRepository,
)
from resume_tailor.infrastructure.job_sources.greenhouse import GreenhouseConnector
from resume_tailor.infrastructure.job_sources.lever import LeverConnector
from resume_tailor.infrastructure.job_sources.registry import load_source_registry
from resume_tailor.infrastructure.llm_cache import InMemoryLlmCache
from resume_tailor.infrastructure.optimization import (
    DeterministicResumeOptimizer,
    EvidenceBoundResumeWriter,
)
from resume_tailor.infrastructure.profile_repository import SQLiteMasterProfileRepository
from resume_tailor.infrastructure.rendering import ExactDocxPageCountProvider
from resume_tailor.infrastructure.template_v1 import TEMPLATE_V1_DOCX_SHA256, TEMPLATE_V1_ID
from resume_tailor.ports.interfaces import ResumeLanguageModel, RoleClassificationCache


class _ConfiguredSourceRepository:
    """Expose only the source registry supplied for this service bundle."""

    def __init__(self, sources: list[SupportedJobSource]) -> None:
        self._sources = tuple(
            sorted(sources, key=lambda source: (source.source_id, source.connector_type.value))
        )

    def list_enabled(self) -> list[SupportedJobSource]:
        return [source.model_copy(deep=True) for source in self._sources]


def create_tailor_service(
    settings: Settings | None = None,
    *,
    role_classification_cache: RoleClassificationCache | None = None,
) -> TailorResumeService:
    resolved_settings = settings or Settings()
    telemetry = GenerationTelemetry()
    language_model = _create_language_model(resolved_settings)
    provider_unavailable_reason = (
        _provider_unavailable_reason(resolved_settings)
        if language_model is None and resolved_settings.llm_enable_bullet_rewrite
        else None
    )
    set_model_telemetry = getattr(language_model, "set_telemetry", None)
    if callable(set_model_telemetry):
        set_model_telemetry(telemetry)
    optimizer = DeterministicResumeOptimizer()
    if resolved_settings.llm_enable_role_classification:
        resolved_role_cache: RoleClassificationCache | None = None
        cache_identity: RoleClassificationCacheIdentity | None = None
        if resolved_settings.gemini_model:
            resolved_role_cache = (
                role_classification_cache
                if role_classification_cache is not None
                else InMemoryLlmCache(resolved_settings.llm_cache_ttl_seconds)
            )
            cache_identity = RoleClassificationCacheIdentity(
                provider=resolved_settings.llm_provider,
                model=resolved_settings.gemini_model,
            )
        role_classifier = HybridRoleClassifier(
            language_model,
            enabled=True,
            cache=resolved_role_cache,
            cache_identity=cache_identity,
            safe_cache_failures=True,
        )
        optimizer = DeterministicResumeOptimizer(
            opportunity_analyzer=HybridRoleOpportunityAnalyzer(
                role_classifier,
                minimum_confidence=(resolved_settings.llm_role_classification_minimum_confidence),
            )
        )
    hybrid_services = HybridLlmServices(
        language_model=language_model,
        retry_count=resolved_settings.llm_retry_count,
        max_calls=resolved_settings.llm_max_calls_per_generation,
        enable_opportunity_analysis=resolved_settings.llm_enable_opportunity_analysis,
        enable_composition=resolved_settings.llm_enable_composition,
        enable_bullet_rewrite=resolved_settings.llm_enable_bullet_rewrite,
        provider_name=resolved_settings.llm_provider,
        model_name=resolved_settings.gemini_model or "unconfigured",
        telemetry=telemetry,
        provider_unavailable_reason=provider_unavailable_reason,
    )
    cover_letter_service = CoverLetterService(
        language_model=language_model if resolved_settings.llm_enable_cover_letter else None,
        renderer=CoverLetterRenderer(),
    )
    return TailorResumeService(
        optimizer,
        EvidenceBoundResumeWriter(),
        hybrid_services=hybrid_services,
        cover_letter_service=cover_letter_service,
        resume_composer=DeterministicResumeComposer(
            TemplateV1PageFitEvaluator(
                ExactDocxPageCountProvider(
                    word_timeout_seconds=resolved_settings.word_pagination_timeout_seconds
                ),
                telemetry=telemetry,
            ),
            telemetry=telemetry,
        ),
        artifact_renderer=TemplateV1ArtifactRenderer(telemetry),
        generation_configuration=ResumeGenerationConfiguration(
            template_identity=f"{TEMPLATE_V1_ID}:{TEMPLATE_V1_DOCX_SHA256}",
            composition_contract_version=RESUME_COMPOSITION_CONTRACT_VERSION,
            writing_policy_version=RESUME_WRITING_POLICY_VERSION,
            writing_contract_version=RESUME_WRITING_CONTRACT_VERSION,
            feature_flags={
                "opportunity_analysis": resolved_settings.llm_enable_opportunity_analysis,
                "semantic_composition": resolved_settings.llm_enable_composition,
                "bullet_rewrite": resolved_settings.llm_enable_bullet_rewrite,
                "shortening": resolved_settings.llm_enable_shortening,
                "role_classification": resolved_settings.llm_enable_role_classification,
            },
            provider=resolved_settings.llm_provider,
            model=resolved_settings.gemini_model or "unconfigured",
            provider_timeout_seconds=resolved_settings.llm_timeout_seconds,
            provider_retry_count=min(resolved_settings.llm_retry_count, 1),
        ),
        telemetry=telemetry,
    )


def create_profile_repository(
    settings: Settings | None = None,
    *,
    legacy_repository_root: Path | None = None,
) -> SQLiteMasterProfileRepository:
    resolved_settings = settings or Settings()
    database = application_database_path(
        resolved_settings.app_data_directory,
        resolved_settings.profile_store_filename,
    )
    repository = SQLiteMasterProfileRepository(database)
    legacy_database = _legacy_database(
        resolved_settings,
        explicit_root=legacy_repository_root,
        use_current_repository=settings is None,
    )
    repository.set_migration_report(migrate_legacy_application_database(legacy_database, database))
    return repository


def create_job_discovery_services(
    settings: Settings | None = None,
    *,
    legacy_repository_root: Path | None = None,
) -> JobDiscoveryServiceBundle:
    resolved_settings = settings or Settings()
    database = application_database_path(
        resolved_settings.app_data_directory,
        resolved_settings.profile_store_filename,
    )
    profiles = SQLiteMasterProfileRepository(database)
    preference_repository = SQLiteJobSearchPreferencesRepository(database)
    job_repository = SQLiteDiscoveredJobRepository(database)
    recommendation_repository = SQLiteJobRecommendationRepository(database)
    run_repository = SQLiteDiscoveryRunRepository(database)
    saved_job_repository = SQLiteSavedJobRepository(database)
    source_repository = SQLiteSupportedJobSourceRepository(database)
    profiles.set_migration_report(
        migrate_legacy_application_database(
            _legacy_database(
                resolved_settings,
                explicit_root=legacy_repository_root,
                use_current_repository=settings is None,
            ),
            database,
        )
    )

    registry_configuration = resolved_settings.job_discovery_source_registry_path
    configured_sources = (
        load_source_registry(registry_configuration) if registry_configuration else []
    )
    for source in configured_sources:
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
    return JobDiscoveryServiceBundle(
        suggest_preferences=SuggestJobSearchPreferencesService(
            profiles,
            DeterministicJobSearchPreferenceSuggester(),
        ),
        refresh=RefreshJobDiscoveryService(
            profiles=profiles,
            preferences=preference_repository,
            sources=(configured_source_repository),
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
        save=SaveJobService(job_repository, saved_job_repository),
        check_saved_availability=CheckSavedJobAvailabilityService(
            saved_job_repository,
            configured_source_repository,
            {ConnectorType.GREENHOUSE: greenhouse, ConnectorType.LEVER: lever},
        ),
        close_resources=client.close,
    )


def _create_language_model(
    settings: Settings,
    *,
    telemetry: GenerationTelemetry | None = None,
) -> ResumeLanguageModel | None:
    enabled = any(
        [
            settings.llm_enable_opportunity_analysis,
            settings.llm_enable_composition,
            settings.llm_enable_bullet_rewrite,
            settings.llm_enable_shortening,
            settings.llm_enable_cover_letter,
            settings.llm_enable_role_classification,
        ]
    )
    if not enabled:
        return None
    try:
        return GeminiResumeLanguageModel(settings, telemetry=telemetry)
    except LanguageModelError:
        if settings.llm_deterministic_fallback:
            return None
        raise


def _provider_unavailable_reason(settings: Settings) -> str:
    api_key = settings.gemini_api_key or os.getenv(settings.llm_api_key_env_var)
    if not api_key:
        return (
            "Gemini bullet writing is enabled, but credentials are missing. Configure "
            f"{settings.llm_api_key_env_var}; reviewed source bullets were retained."
        )
    if not settings.gemini_model:
        return (
            "Gemini bullet writing is enabled and credentials are present, but "
            "GEMINI_MODEL is missing; reviewed source bullets were retained."
        )
    return (
        "Gemini bullet writing is enabled and configured, but the provider adapter "
        "could not initialize; reviewed source bullets were retained."
    )


def _legacy_database(
    settings: Settings,
    *,
    explicit_root: Path | None,
    use_current_repository: bool,
) -> Path | None:
    root = explicit_root
    if root is None and use_current_repository:
        current = Path.cwd()
        if (current / ".git").exists():
            root = current
    if root is None:
        return None
    return repository_local_legacy_database(root, settings.profile_store_filename)
