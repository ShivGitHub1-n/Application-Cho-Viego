from __future__ import annotations

import json
import os
import re
import time
from typing import Any, TypeVar, cast

from pydantic import BaseModel, ValidationError

from resume_tailor.application.generation_diagnostics import GenerationTelemetry
from resume_tailor.application.llm_prompts import system_prompt, task_prompt
from resume_tailor.domain.generated_artifact import GenerationStage
from resume_tailor.domain.hybrid_resume import (
    ProviderFieldViolation,
    ProviderRequestShapeDiagnostic,
    WriterPipelineFailureCode,
    WriterPipelineIssue,
    WriterPipelineStage,
)
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
from resume_tailor.infrastructure.gemini_request_diagnostics import (
    build_request_shape_diagnostic,
)
from resume_tailor.infrastructure.gemini_schema import (
    gemini_schema_transform,
    transform_gemini_schema,
)
from resume_tailor.infrastructure.gemini_writer_contract import (
    GEMINI_WRITER_RESPONSE_SCHEMA,
    GeminiProviderWriterOutput,
    GeminiWriterMappingError,
    map_provider_writer_output,
)
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
        request_shape: ProviderRequestShapeDiagnostic | None = None
        writer_mapping_outcomes: list[object] = []
        try:
            if operation is LlmOperation.REWRITE_BULLETS:
                provider_output_type: type[BaseModel] = GeminiProviderWriterOutput
                schema_transform = transform_gemini_schema(
                    GEMINI_WRITER_RESPONSE_SCHEMA
                )
            else:
                provider_output_type = output_type
                schema_transform = gemini_schema_transform(
                    output_type,
                    excluded_properties=(
                        {"description", "bullets", "bullet_points"}
                        if operation == LlmOperation.PROFILE_EXTRACTION
                        else None
                    ),
                )
            provider_config = self._types.GenerateContentConfig(
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
                response_json_schema=schema_transform.schema,
            )
            request_shape = build_request_shape_diagnostic(
                client=self._client,
                model=self._model,
                config=provider_config,
                schema_transform=schema_transform,
            )
            def generate() -> Any:
                return self._client.models.generate_content(
                    model=self._model,
                    contents=task_prompt(operation, request),
                    config=provider_config,
                )

            if telemetry is not None and operation is LlmOperation.REWRITE_BULLETS:
                with telemetry.measure(GenerationStage.PROVIDER_REQUEST):
                    response = generate()
            else:
                response = generate()

            def parse() -> BaseModel:
                return self._parse_response(response, provider_output_type)

            if telemetry is not None:
                with telemetry.measure(GenerationStage.PROVIDER_RESPONSE_PARSING):
                    provider_output = parse()
            else:
                provider_output = parse()
            if operation is LlmOperation.REWRITE_BULLETS:
                try:
                    mapped = map_provider_writer_output(
                        cast(GeminiProviderWriterOutput, provider_output),
                        cast(BulletRewriteRequest, request),
                    )
                    output = cast(OutputType, mapped.output)
                    writer_mapping_outcomes = list(mapped.mapping_outcomes)
                except GeminiWriterMappingError as error:
                    raise LanguageModelError(
                        LanguageModelErrorKind.VALIDATION,
                        "Gemini writer output referenced an unauthorized evidence bundle.",
                        diagnostic=WriterPipelineIssue(
                            code=WriterPipelineFailureCode.CLAIM_GROUNDING_REJECTION,
                            stage=WriterPipelineStage.CLAIM_VALIDATION,
                            provider_error_kind=LanguageModelErrorKind.VALIDATION.value,
                            sanitized_detail=(
                                "Provider writer response failed authorized evidence "
                                "mapping."
                            ),
                        ),
                    ) from error
            else:
                output = cast(OutputType, provider_output)
        except LanguageModelError as error:
            if error.diagnostic is not None and error.diagnostic.request_shape is None:
                error.diagnostic = error.diagnostic.model_copy(
                    update={"request_shape": request_shape}
                )
            raise
        except Exception as error:
            raise self._map_error(error, request_shape=request_shape) from error
        metadata = self._metadata(operation, response, started, request_shape)
        result_payload: dict[str, object] = {"metadata": metadata, "output": output}
        if operation is LlmOperation.REWRITE_BULLETS:
            result_payload["mapping_outcomes"] = writer_mapping_outcomes
        result = result_type.model_validate(result_payload)
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

    def _parse_response(
        self,
        response: Any,
        output_type: type[OutputType],
    ) -> OutputType:
        try:
            candidates = list(getattr(response, "candidates", None) or [])
            finish_reason, finish_message = self._finish_diagnostics(response)
            prompt_feedback = getattr(response, "prompt_feedback", None)
            block_reason = getattr(prompt_feedback, "block_reason", None)
        except Exception as error:
            raise LanguageModelError(
                LanguageModelErrorKind.RESPONSE_EXTRACTION,
                "Gemini returned a response that could not be inspected safely.",
                diagnostic=WriterPipelineIssue(
                    code=WriterPipelineFailureCode.RESPONSE_EXTRACTION_FAILED,
                    stage=WriterPipelineStage.RESPONSE_EXTRACTION,
                    provider_error_kind=LanguageModelErrorKind.RESPONSE_EXTRACTION.value,
                    exception_type=type(error).__name__,
                ),
            ) from error
        candidate_count = len(candidates)
        if self._is_safety_block(finish_reason, block_reason):
            raise LanguageModelError(
                LanguageModelErrorKind.SAFETY_BLOCKED,
                "Gemini blocked the response under its safety policy.",
                diagnostic=WriterPipelineIssue(
                    code=WriterPipelineFailureCode.SAFETY_BLOCKED_RESPONSE,
                    stage=WriterPipelineStage.RESPONSE_EXTRACTION,
                    provider_error_kind=LanguageModelErrorKind.SAFETY_BLOCKED.value,
                    finish_reason=finish_reason or self._safe_string(block_reason),
                    candidate_count=candidate_count,
                    text_present=False,
                ),
            )
        usage = getattr(response, "usage_metadata", None)
        if self._is_truncated(finish_reason, finish_message):
            output_tokens = getattr(usage, "candidates_token_count", None)
            raise LanguageModelError(
                LanguageModelErrorKind.TRUNCATED_RESPONSE,
                "Gemini response was truncated before typed JSON completed "
                f"(output_tokens={output_tokens!r}); it was not retried automatically.",
                diagnostic=WriterPipelineIssue(
                    code=WriterPipelineFailureCode.RESPONSE_EXTRACTION_FAILED,
                    stage=WriterPipelineStage.RESPONSE_EXTRACTION,
                    provider_error_kind=LanguageModelErrorKind.TRUNCATED_RESPONSE.value,
                    finish_reason=finish_reason,
                    candidate_count=candidate_count,
                ),
            )
        try:
            parsed = getattr(response, "parsed", None)
            response_text = None if parsed is not None else getattr(response, "text", None)
        except Exception as error:
            raise LanguageModelError(
                LanguageModelErrorKind.RESPONSE_EXTRACTION,
                "Gemini response text extraction failed.",
                diagnostic=WriterPipelineIssue(
                    code=WriterPipelineFailureCode.RESPONSE_EXTRACTION_FAILED,
                    stage=WriterPipelineStage.RESPONSE_EXTRACTION,
                    provider_error_kind=LanguageModelErrorKind.RESPONSE_EXTRACTION.value,
                    exception_type=type(error).__name__,
                    finish_reason=finish_reason,
                    candidate_count=candidate_count,
                ),
            ) from error
        text_present = bool(response_text and response_text.strip())
        if parsed is None and not text_present:
            raise LanguageModelError(
                LanguageModelErrorKind.EMPTY_RESPONSE,
                "Gemini returned no candidate text.",
                diagnostic=WriterPipelineIssue(
                    code=WriterPipelineFailureCode.EMPTY_PROVIDER_RESPONSE,
                    stage=WriterPipelineStage.RESPONSE_EXTRACTION,
                    provider_error_kind=LanguageModelErrorKind.EMPTY_RESPONSE.value,
                    finish_reason=finish_reason,
                    candidate_count=candidate_count,
                    text_present=False,
                ),
            )
        if parsed is None:
            try:
                parsed = json.loads(self._clean_json_text(response_text or ""))
            except json.JSONDecodeError as error:
                raise LanguageModelError(
                    LanguageModelErrorKind.MALFORMED_RESPONSE,
                    "Gemini returned malformed JSON.",
                    diagnostic=WriterPipelineIssue(
                        code=WriterPipelineFailureCode.MALFORMED_JSON,
                        stage=WriterPipelineStage.JSON_PARSING,
                        provider_error_kind=LanguageModelErrorKind.MALFORMED_RESPONSE.value,
                        exception_type=type(error).__name__,
                        finish_reason=finish_reason,
                        candidate_count=candidate_count,
                        text_present=True,
                    ),
                ) from error
        top_level_keys = (
            sorted(str(key) for key in parsed)[:40] if isinstance(parsed, dict) else []
        )
        try:
            if isinstance(parsed, output_type):
                return parsed
            return output_type.model_validate(parsed)
        except ValidationError as error:
            raise LanguageModelError(
                LanguageModelErrorKind.MALFORMED_RESPONSE,
                "Gemini JSON did not match the typed response schema.",
                diagnostic=WriterPipelineIssue(
                    code=WriterPipelineFailureCode.TYPED_SCHEMA_MISMATCH,
                    stage=WriterPipelineStage.TYPED_SCHEMA_VALIDATION,
                    provider_error_kind=LanguageModelErrorKind.MALFORMED_RESPONSE.value,
                    exception_type=type(error).__name__,
                    finish_reason=finish_reason,
                    candidate_count=candidate_count,
                    text_present=text_present or parsed is not None,
                    top_level_json_keys=top_level_keys,
                    schema_error_field_paths=self._schema_error_paths(error),
                ),
            ) from error

    @staticmethod
    def _clean_json_text(text: str) -> str:
        cleaned = text.lstrip("\ufeff").strip()
        if cleaned.startswith("```") and cleaned.endswith("```"):
            first_newline = cleaned.find("\n")
            if first_newline != -1:
                cleaned = cleaned[first_newline + 1 : -3].strip()
        return cleaned

    @staticmethod
    def _schema_error_paths(error: ValidationError) -> list[str]:
        paths: list[str] = []
        for item in error.errors(include_url=False):
            location = item.get("loc", ())
            path = ".".join(str(part) for part in location) or "$"
            if path not in paths:
                paths.append(path)
        return paths[:20]

    @staticmethod
    def _safe_string(value: object) -> str | None:
        return str(value)[:120] if value is not None else None

    @classmethod
    def _is_safety_block(cls, finish_reason: str | None, block_reason: object) -> bool:
        value = f"{finish_reason or ''} {cls._safe_string(block_reason) or ''}".casefold()
        return any(
            token in value
            for token in (
                "safety",
                "blocklist",
                "prohibited_content",
                "prohibited content",
                "spii",
            )
        )

    def _metadata(
        self,
        operation: LlmOperation,
        response: Any,
        started: float,
        request_shape: ProviderRequestShapeDiagnostic | None,
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
            request_shape=request_shape,
        )

    @staticmethod
    def _map_error(
        error: Exception,
        *,
        request_shape: ProviderRequestShapeDiagnostic | None = None,
    ) -> LanguageModelError:
        message = str(error).casefold()
        exception_name = type(error).__name__.casefold()
        provider_code = GeminiResumeLanguageModel._provider_error_code(error)
        provider_status = str(getattr(error, "status", "") or "").casefold()
        field_violations = GeminiResumeLanguageModel._field_violations(error)
        if provider_code == "400" or "invalid_argument" in provider_status:
            kind = LanguageModelErrorKind.CONFIGURATION
            public_message = "Gemini rejected the request as an invalid argument."
            failure_code = GeminiResumeLanguageModel._invalid_argument_failure_code(
                request_shape,
                field_violations,
            )
        elif "429" in message or "rate" in message or "resource exhausted" in message:
            kind = LanguageModelErrorKind.RATE_LIMITED
            public_message = "Gemini rate limit reached."
            failure_code = WriterPipelineFailureCode.PROVIDER_TRANSPORT_OR_SDK_ERROR
        elif (
            "timeout" in message
            or "timed out" in message
            or "timeout" in exception_name
        ):
            kind = LanguageModelErrorKind.TIMEOUT
            public_message = "Gemini request timed out."
            failure_code = WriterPipelineFailureCode.PROVIDER_TIMEOUT
        elif "404" in message or "model" in message and "not found" in message:
            kind = LanguageModelErrorKind.UNAVAILABLE
            public_message = "Configured Gemini model is unavailable."
            failure_code = WriterPipelineFailureCode.INVALID_MODEL_OR_CONFIG
        elif (
            "connection" in message
            or "network" in message
            or "dns" in message
            or "socket" in message
            or "connect" in exception_name
            or "network" in exception_name
        ):
            kind = LanguageModelErrorKind.NETWORK
            public_message = "Gemini network request failed."
            failure_code = WriterPipelineFailureCode.PROVIDER_TRANSPORT_OR_SDK_ERROR
        else:
            kind = LanguageModelErrorKind.UNAVAILABLE
            public_message = "Gemini SDK request failed."
            failure_code = WriterPipelineFailureCode.PROVIDER_TRANSPORT_OR_SDK_ERROR
        return LanguageModelError(
            kind,
            public_message,
            kind
            in {
                LanguageModelErrorKind.RATE_LIMITED,
                LanguageModelErrorKind.TIMEOUT,
                LanguageModelErrorKind.NETWORK,
            },
            diagnostic=WriterPipelineIssue(
                code=failure_code,
                stage=WriterPipelineStage.PROVIDER_REQUEST,
                provider_error_kind=kind.value,
                exception_type=type(error).__name__,
                provider_error_code=provider_code,
                field_violations=field_violations,
                request_shape=request_shape,
                sanitized_detail=GeminiResumeLanguageModel._sanitized_provider_detail(error),
            ),
        )

    @staticmethod
    def _invalid_argument_failure_code(
        request_shape: ProviderRequestShapeDiagnostic | None,
        field_violations: list[ProviderFieldViolation],
    ) -> WriterPipelineFailureCode:
        findings = request_shape.compatibility_findings if request_shape is not None else []
        combined = " ".join(
            f"{item.field_path} {item.description}" for item in field_violations
        ).casefold()
        if "schema" in combined and any(
            token in combined
            for token in ("unsupported", "unknown name", "unknown field", "keyword")
        ):
            return WriterPipelineFailureCode.UNSUPPORTED_SCHEMA_KEYWORD
        if "schema" in combined and any(
            token in combined for token in ("too large", "too deep", "complex", "nesting")
        ):
            return WriterPipelineFailureCode.SCHEMA_TOO_LARGE_OR_DEEP
        if request_shape is not None and any(
            finding.startswith("schema_") for finding in findings
        ):
            return WriterPipelineFailureCode.SCHEMA_TOO_LARGE_OR_DEEP
        if field_violations:
            return WriterPipelineFailureCode.INVALID_MODEL_OR_CONFIG
        if any(item.startswith("incompatible_sdk_api_version:") for item in findings):
            return WriterPipelineFailureCode.INCOMPATIBLE_SDK_API_VERSION
        return WriterPipelineFailureCode.UNKNOWN_INVALID_ARGUMENT

    @staticmethod
    def _field_violations(error: Exception) -> list[ProviderFieldViolation]:
        violations: list[ProviderFieldViolation] = []

        def visit(value: object) -> None:
            if len(violations) >= 12:
                return
            if isinstance(value, list):
                for item in value:
                    visit(item)
                return
            if not isinstance(value, dict):
                return
            field_path = value.get("field") or value.get("fieldPath")
            description = value.get("description") or value.get("reason")
            safe_path = GeminiResumeLanguageModel._safe_field_path(field_path)
            safe_description = GeminiResumeLanguageModel._safe_violation_description(
                description
            )
            if safe_path and safe_description:
                candidate = ProviderFieldViolation(
                    field_path=safe_path,
                    description=safe_description,
                )
                if candidate not in violations:
                    violations.append(candidate)
            for nested in value.values():
                if isinstance(nested, (dict, list)):
                    visit(nested)

        visit(getattr(error, "details", None))
        return violations

    @staticmethod
    def _safe_field_path(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        cleaned = value.strip()[:240]
        return cleaned if re.fullmatch(r"[A-Za-z0-9_.$\[\]/:-]+", cleaned) else None

    @staticmethod
    def _safe_violation_description(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        lowered = value.casefold()
        if any(
            token in lowered
            for token in ("authorization", "bearer ", "api_key", "api-key", "prompt")
        ):
            return None
        cleaned = " ".join(value.split())[:300]
        return cleaned or None

    @staticmethod
    def _provider_error_code(error: Exception) -> str | None:
        value = getattr(error, "code", None) or getattr(error, "status_code", None)
        return str(value)[:40] if value is not None else None

    @staticmethod
    def _sanitized_provider_detail(error: Exception) -> str | None:
        detail = getattr(error, "message", None)
        if not isinstance(detail, str):
            return None
        lowered = detail.casefold()
        if any(
            token in lowered
            for token in (
                "authorization",
                "bearer ",
                "api_key",
                "api-key",
                "contents=",
                "prompt",
                "profile",
                "source_text",
            )
        ):
            return None
        detail = re.sub(
            r"(?i)(key|token|secret)\s*[:=]\s*['\"]?[^,\s'\"]+",
            r"\1=<redacted>",
            detail,
        )
        detail = " ".join(detail.split())
        return detail[:280] or None
