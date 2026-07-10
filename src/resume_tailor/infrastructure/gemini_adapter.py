from __future__ import annotations

import os
import time
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from resume_tailor.application.llm_prompts import system_prompt, task_prompt
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
    LanguageModelError,
    LanguageModelErrorKind,
    LlmOperation,
    ModelCallMetadata,
    ModelResult,
    OpportunityAnalysisOutput,
    OpportunityAnalysisRequest,
    OpportunityAnalysisResult,
)
from resume_tailor.infrastructure.config import Settings
from resume_tailor.infrastructure.llm_cache import InMemoryLlmCache
from resume_tailor.infrastructure.gemini_schema import gemini_response_schema

OutputType = TypeVar("OutputType", bound=BaseModel)
ResultType = TypeVar("ResultType", bound=ModelResult)


class GeminiResumeLanguageModel:
    def __init__(self, settings: Settings, cache: InMemoryLlmCache | None = None) -> None:
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
            http_options=types.HttpOptions(timeout=settings.llm_timeout_seconds * 1000),
        )
        self._model = settings.gemini_model
        self._temperature = settings.llm_temperature
        self._max_output_tokens = settings.llm_max_output_tokens
        self._cache = cache or InMemoryLlmCache(settings.llm_cache_ttl_seconds)

    def analyze_opportunity(self, request: OpportunityAnalysisRequest) -> OpportunityAnalysisResult:
        return self._generate(
            LlmOperation.ANALYZE_OPPORTUNITY,
            request,
            OpportunityAnalysisOutput,
            OpportunityAnalysisResult,
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

    def close(self) -> None:
        self._client.close()

    def _generate(
        self,
        operation: LlmOperation,
        request: BaseModel,
        output_type: type[OutputType],
        result_type: type[ResultType],
    ) -> ResultType:
        cache_key = self._cache.key_for(operation.value, self._model, request)
        cached = self._cache.get(cache_key, result_type)
        if cached is not None:
            metadata = cached.metadata.model_copy(update={"cache_hit": True, "latency_ms": 0})
            return cached.model_copy(update={"metadata": metadata})
        started = time.monotonic()
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=task_prompt(operation, request),
                config=self._types.GenerateContentConfig(
                    system_instruction=system_prompt(),
                    temperature=self._temperature,
                    max_output_tokens=self._max_output_tokens,
                    response_mime_type="application/json",
                    response_schema=gemini_response_schema(output_type),
                ),
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

    def _metadata(self, operation: LlmOperation, response: Any, started: float) -> ModelCallMetadata:
        usage = getattr(response, "usage_metadata", None)
        return ModelCallMetadata(
            provider="gemini",
            model=self._model,
            operation=operation,
            latency_ms=round((time.monotonic() - started) * 1000),
            prompt_tokens=getattr(usage, "prompt_token_count", None),
            output_tokens=getattr(usage, "candidates_token_count", None),
            total_tokens=getattr(usage, "total_token_count", None),
        )

    @staticmethod
    def _map_error(error: Exception) -> LanguageModelError:
        message = str(error).casefold()
        if "429" in message or "rate" in message or "resource exhausted" in message:
            return LanguageModelError(LanguageModelErrorKind.RATE_LIMITED, "Gemini rate limit reached.", True)
        if "timeout" in message or "timed out" in message:
            return LanguageModelError(LanguageModelErrorKind.TIMEOUT, "Gemini request timed out.", True)
        if "404" in message or "model" in message and "not found" in message:
            return LanguageModelError(LanguageModelErrorKind.UNAVAILABLE, "Configured Gemini model is unavailable.")
        if "connection" in message or "network" in message or "dns" in message:
            return LanguageModelError(LanguageModelErrorKind.NETWORK, "Gemini network request failed.", True)
        return LanguageModelError(LanguageModelErrorKind.UNAVAILABLE, "Gemini request failed.", True)
