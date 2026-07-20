from __future__ import annotations

import os
import time
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from resume_tailor.application.generation_diagnostics import GenerationTelemetry
from resume_tailor.application.llm_prompts import system_prompt, task_prompt
from resume_tailor.domain.generated_artifact import GenerationStage
from resume_tailor.domain.llm_models import (
    BulletRewriteOutput,
    BulletRewriteRequest,
    BulletRewriteResult,
    BulletShorteningOutput,
    BulletShorteningRequest,
    BulletShorteningResult,
    CompositionRecommendationOutput,
    CompositionRecommendationRequest,
    CompositionRecommendationResult,
    CoverLetterDraftOutput,
    CoverLetterDraftRequest,
    CoverLetterDraftResult,
    LanguageModelError,
    LanguageModelErrorKind,
    LlmOperation,
    ModelCallMetadata,
    ModelResult,
    OpportunityAnalysisOutput,
    OpportunityAnalysisRequest,
    OpportunityAnalysisResult,
    ProfileExtractionOutput,
    ProfileExtractionRequest,
    ProfileExtractionResult,
    RoleClassificationOutput,
    RoleClassificationRequest,
    RoleClassificationResult,
    SkillCompositionOutput,
    SkillCompositionRequest,
    SkillCompositionResult,
)
from resume_tailor.infrastructure.config import Settings
from resume_tailor.infrastructure.gemini_schema import gemini_response_schema
from resume_tailor.infrastructure.llm_cache import InMemoryLlmCache

OutputType = TypeVar("OutputType", bound=BaseModel)
ResultType = TypeVar("ResultType", bound=ModelResult)


class _ProviderCachePayload(BaseModel):
    payload: dict[str, Any]


class GeminiResumeLanguageModel:
    def __init__(
        self,
        settings: Settings,
        cache: InMemoryLlmCache | None = None,
        telemetry: GenerationTelemetry | None = None,
    ) -> None:
        api_key = settings.gemini_api_key or os.getenv(settings.llm_api_key_env_var)
        if not api_key:
            raise LanguageModelError(
                LanguageModelErrorKind.CONFIGURATION,
                "GEMINI_API_KEY is required when Gemini features are enabled.",
            )
        if not settings.gemini_model:
            raise LanguageModelError(
                LanguageModelErrorKind.CONFIGURATION,
                "GEMINI_MODEL is required when Gemini features are enabled.",
            )
        try:
            from google import genai
            from google.genai import types
        except ImportError as error:
            raise LanguageModelError(
                LanguageModelErrorKind.CONFIGURATION,
                "The google-genai package is not installed.",
            ) from error
        self._types = types
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=settings.llm_timeout_seconds * 1000,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
        self._model = settings.gemini_model
        self._temperature = settings.llm_temperature
        self._max_output_tokens = settings.llm_max_output_tokens
        self._bullet_rewrite_max_output_tokens = settings.llm_bullet_rewrite_max_output_tokens
        self._profile_extraction_max_output_tokens = (
            settings.llm_profile_extraction_max_output_tokens
        )
        self._cache = cache or InMemoryLlmCache(settings.llm_cache_ttl_seconds)
        self._telemetry = telemetry or GenerationTelemetry()

    def set_telemetry(self, telemetry: GenerationTelemetry) -> None:
        self._telemetry = telemetry

    def analyze_opportunity(self, request: OpportunityAnalysisRequest) -> OpportunityAnalysisResult:
        return self._generate(
            LlmOperation.ANALYZE_OPPORTUNITY,
            request,
            OpportunityAnalysisOutput,
            OpportunityAnalysisResult,
        )

    def classify_role(self, request: RoleClassificationRequest) -> RoleClassificationResult:
        return self._generate(
            LlmOperation.CLASSIFY_ROLE,
            request,
            RoleClassificationOutput,
            RoleClassificationResult,
        )

    def extract_profile(self, request: ProfileExtractionRequest) -> ProfileExtractionResult:
        return self._generate(
            LlmOperation.PROFILE_EXTRACTION,
            request,
            ProfileExtractionOutput,
            ProfileExtractionResult,
        )

    def recommend_composition(
        self, request: CompositionRecommendationRequest
    ) -> CompositionRecommendationResult:
        return self._generate(
            LlmOperation.RECOMMEND_COMPOSITION,
            request,
            CompositionRecommendationOutput,
            CompositionRecommendationResult,
        )

    def recommend_skill_composition(
        self, request: SkillCompositionRequest
    ) -> SkillCompositionResult:
        return self._generate(
            LlmOperation.RECOMMEND_SKILL_COMPOSITION,
            request,
            SkillCompositionOutput,
            SkillCompositionResult,
        )

    def rewrite_bullets(self, request: BulletRewriteRequest) -> BulletRewriteResult:
        return self._generate(
            LlmOperation.REWRITE_BULLETS,
            request,
            BulletRewriteOutput,
            BulletRewriteResult,
        )

    def shorten_bullets(self, request: BulletShorteningRequest) -> BulletShorteningResult:
        return self._generate(
            LlmOperation.SHORTEN_BULLETS,
            request,
            BulletShorteningOutput,
            BulletShorteningResult,
        )

    def draft_cover_letter(self, request: CoverLetterDraftRequest) -> CoverLetterDraftResult:
        return self._generate(
            LlmOperation.COVER_LETTER_DRAFT,
            request,
            CoverLetterDraftOutput,
            CoverLetterDraftResult,
        )

    def close(self) -> None:
        self._client.close()

    def _generate(
        self,
        operation: LlmOperation,
        request: BaseModel,
        output_type: type[OutputType],
        result_type: type[ResultType],
    ) -> ResultType:
        cache_key = self._cache.key_for(
            operation.value,
            self._model,
            self._cache_payload(operation, request),
        )
        telemetry = getattr(self, "_telemetry", None)
        cache_started = telemetry.clock() if telemetry is not None else 0.0
        cached = self._cache.get(cache_key, result_type)
        if telemetry is not None:
            telemetry.record(
                GenerationStage.WRITER_CACHE_LOOKUP,
                telemetry.clock() - cache_started,
            )
        if cached is not None:
            metadata = cached.metadata.model_copy(update={"cache_hit": True, "latency_ms": 0})
            return cached.model_copy(update={"metadata": metadata})
        started = time.monotonic()
        try:

            def generate() -> Any:
                return self._client.models.generate_content(
                    model=self._model,
                    contents=task_prompt(operation, request),
                    config=self._types.GenerateContentConfig(
                        system_instruction=system_prompt(),
                        temperature=self._temperature,
                        max_output_tokens=(
                            self._profile_extraction_max_output_tokens
                            if operation == LlmOperation.PROFILE_EXTRACTION
                            else self._bullet_rewrite_max_output_tokens
                            if operation == LlmOperation.REWRITE_BULLETS
                            else self._max_output_tokens
                        ),
                        response_mime_type="application/json",
                        response_schema=gemini_response_schema(
                            output_type,
                            excluded_properties=(
                                {"description", "bullets", "bullet_points"}
                                if operation == LlmOperation.PROFILE_EXTRACTION
                                else None
                            ),
                        ),
                    ),
                )

            if telemetry is not None and operation is LlmOperation.REWRITE_BULLETS:
                with telemetry.measure(GenerationStage.PROVIDER_REQUEST):
                    response = generate()
            else:
                response = generate()
            parsing_started = telemetry.clock() if telemetry is not None else 0.0
            finish_reason, finish_message = self._finish_diagnostics(response)
            usage = getattr(response, "usage_metadata", None)
            if self._is_truncated(finish_reason, finish_message):
                output_tokens = getattr(usage, "candidates_token_count", None)
                raise LanguageModelError(
                    LanguageModelErrorKind.TRUNCATED_RESPONSE,
                    "Gemini profile extraction response was truncated before JSON completed "
                    f"(finish_reason={finish_reason!r}, finish_message={finish_message!r}, "
                    f"output_tokens={output_tokens!r}, "
                    f"max_output_tokens={self._profile_extraction_max_output_tokens}). "
                    "Increase the configured extraction token budget or reduce source size; "
                    "the extraction was not retried automatically.",
                )
            parsed = getattr(response, "parsed", None)
            if parsed is None:
                response_text = getattr(response, "text", None)
                if not response_text:
                    raise LanguageModelError(
                        LanguageModelErrorKind.SAFETY_BLOCKED,
                        "Gemini did not return structured text.",
                    )
                output = output_type.model_validate_json(response_text)
            elif isinstance(parsed, output_type):
                output = parsed
            else:
                output = output_type.model_validate(parsed)
            if telemetry is not None:
                telemetry.record(
                    GenerationStage.PROVIDER_RESPONSE_PARSING,
                    telemetry.clock() - parsing_started,
                )
        except LanguageModelError:
            raise
        except ValidationError as error:
            raise LanguageModelError(
                LanguageModelErrorKind.MALFORMED_RESPONSE,
                "Gemini returned output that does not match the requested schema.",
            ) from error
        except Exception as error:
            raise self._map_error(error) from error
        metadata = self._metadata(operation, response, started)
        result = result_type.model_validate({"metadata": metadata, "output": output})
        self._cache.set(cache_key, result)
        return result

    @staticmethod
    def _cache_payload(
        operation: LlmOperation,
        request: BaseModel,
    ) -> BaseModel:
        if operation is not LlmOperation.REWRITE_BULLETS:
            return request
        payload = request.model_dump(
            mode="json",
            exclude={"max_total_lines", "max_bullets_per_entry"},
        )
        for group in payload.get("groups", []):
            if isinstance(group, dict):
                group.pop("max_rendered_lines", None)
        return _ProviderCachePayload(payload=payload)

    @staticmethod
    def _finish_diagnostics(response: Any) -> tuple[str | None, str | None]:
        candidates = getattr(response, "candidates", None) or []
        candidate = candidates[0] if candidates else None
        if candidate is None:
            return None, None
        reason = getattr(candidate, "finish_reason", None)
        message = getattr(candidate, "finish_message", None)
        return (str(reason) if reason is not None else None, str(message) if message else None)

    @staticmethod
    def _is_truncated(finish_reason: str | None, finish_message: str | None) -> bool:
        value = f"{finish_reason or ''} {finish_message or ''}".casefold()
        return any(
            token in value for token in ("max_tokens", "max tokens", "length", "token limit")
        )

    def _metadata(
        self, operation: LlmOperation, response: Any, started: float
    ) -> ModelCallMetadata:
        usage = getattr(response, "usage_metadata", None)
        return ModelCallMetadata(
            provider="gemini",
            model=self._model,
            operation=operation,
            latency_ms=round((time.monotonic() - started) * 1000),
            prompt_tokens=getattr(usage, "prompt_token_count", None),
            output_tokens=getattr(usage, "candidates_token_count", None),
            total_tokens=getattr(usage, "total_token_count", None),
            finish_reason=self._finish_diagnostics(response)[0],
            finish_message=self._finish_diagnostics(response)[1],
        )

    @staticmethod
    def _map_error(error: Exception) -> LanguageModelError:
        message = str(error).casefold()
        if "429" in message or "rate" in message or "resource exhausted" in message:
            return LanguageModelError(
                LanguageModelErrorKind.RATE_LIMITED, "Gemini rate limit reached.", True
            )
        if "timeout" in message or "timed out" in message:
            return LanguageModelError(
                LanguageModelErrorKind.TIMEOUT, "Gemini request timed out.", True
            )
        if "404" in message or "model" in message and "not found" in message:
            return LanguageModelError(
                LanguageModelErrorKind.UNAVAILABLE, "Configured Gemini model is unavailable."
            )
        if "connection" in message or "network" in message or "dns" in message:
            return LanguageModelError(
                LanguageModelErrorKind.NETWORK, "Gemini network request failed.", True
            )
        return LanguageModelError(
            LanguageModelErrorKind.UNAVAILABLE, "Gemini request failed.", True
        )
