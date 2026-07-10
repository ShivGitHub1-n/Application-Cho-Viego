from resume_tailor.application.llm_services import HybridLlmServices
from resume_tailor.application.services import TailorResumeService
from resume_tailor.domain.llm_models import LanguageModelError
from resume_tailor.infrastructure.config import Settings
from resume_tailor.infrastructure.gemini_adapter import GeminiResumeLanguageModel
from resume_tailor.infrastructure.optimization import DeterministicResumeOptimizer, EvidenceBoundResumeWriter
from resume_tailor.ports.interfaces import ResumeLanguageModel


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
    return TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
        hybrid_services=hybrid_services,
    )


def _create_language_model(settings: Settings) -> ResumeLanguageModel | None:
    enabled = any(
        [
            settings.llm_enable_opportunity_analysis,
            settings.llm_enable_composition,
            settings.llm_enable_bullet_rewrite,
            settings.llm_enable_shortening,
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
