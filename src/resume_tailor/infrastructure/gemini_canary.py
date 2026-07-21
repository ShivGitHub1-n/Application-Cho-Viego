from __future__ import annotations

import json
import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from resume_tailor.application.llm_prompts import system_prompt
from resume_tailor.application.llm_validation import (
    GroundingValidationError,
    validate_rewrites,
)
from resume_tailor.domain.hybrid_resume import (
    ProviderRequestShapeDiagnostic,
    ProviderRewriteMappingStatus,
    WriterPipelineFailureCode,
    WriterPipelineIssue,
    WriterPipelineStage,
)
from resume_tailor.domain.llm_models import (
    ApprovedEvidenceGroup,
    BulletRewriteOutput,
    BulletRewriteRequest,
    LanguageModelErrorKind,
)
from resume_tailor.infrastructure.config import Settings
from resume_tailor.infrastructure.gemini_adapter import GeminiResumeLanguageModel
from resume_tailor.infrastructure.gemini_request_diagnostics import (
    build_request_shape_diagnostic,
    has_incompatible_sdk_or_api,
)
from resume_tailor.infrastructure.gemini_schema import (
    transform_gemini_schema,
)
from resume_tailor.infrastructure.gemini_writer_contract import (
    GEMINI_WRITER_RESPONSE_SCHEMA,
    GeminiProviderWriterOutput,
    GeminiWriterMappingError,
    map_provider_writer_output,
)

MINIMAL_STRUCTURED_OUTPUT_CANARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"status": {"type": "string"}},
    "required": ["status"],
}
_NEUTRAL_SYSTEM_INSTRUCTION = "Return only the requested structured JSON object."
MINIMAL_WRITER_CANARY_EVIDENCE_ID = "canary-evidence"
MINIMAL_WRITER_CANARY_SOURCE = (
    "Developed and tested a Python API that processed 500 requests per day."
)
MINIMAL_WRITER_CANARY_SAFE_PARAPHRASES = (
    "Built and tested a Python API that processed 500 requests per day.",
    "Tested and developed a Python API that processed 500 requests per day.",
)
_MINIMAL_WRITER_CONTENTS = (
    "Conservatively rewrite the synthetic evidence below with modest structural "
    "reordering only. Preserve the exact facts: Python API, development, testing, "
    "and 500 requests per day. Do not add technologies, mechanisms, outcomes, "
    "ownership, causality, or metrics. Use the authorized evidence ID exactly. If "
    "no conservative rewrite is possible, repeat the source. Evidence ID: "
    f"{MINIMAL_WRITER_CANARY_EVIDENCE_ID}. Source: {MINIMAL_WRITER_CANARY_SOURCE}"
)


class GeminiIsolationMode(StrEnum):
    MINIMAL = "minimal"
    PRODUCTION_SCHEMA_ONLY = "production-schema-only"
    PRODUCTION_CONFIG_ONLY = "production-config-only"
    MINIMAL_PRODUCTION_WRITER = "minimal-production-writer"


class GeminiCanaryRejectionCode(StrEnum):
    UNSUPPORTED_TECHNOLOGY = "unsupported_technology"
    CHANGED_NUMBER_OR_METRIC = "changed_number_or_metric"
    UNSUPPORTED_OUTCOME = "unsupported_outcome"
    OWNERSHIP_EXPANSION = "ownership_expansion"
    UNSUPPORTED_NARROWING = "unsupported_narrowing"
    CROSS_ENTRY_EVIDENCE = "cross_entry_evidence"
    SEMANTIC_EQUIVALENCE_FAILURE = "semantic_equivalence_failure"
    UNKNOWN_EVIDENCE = "unknown_evidence"
    DUPLICATE_EVIDENCE = "duplicate_evidence"
    CLAIM_PROVENANCE = "claim_provenance"
    ANOTHER_PRECISE_RULE = "another_precise_rule"


class GeminiCanaryEvidenceDiagnostic(BaseModel):
    evidence_id: str
    source_text: str


class GeminiCanaryClaimDiagnostic(BaseModel):
    text: str
    supporting_evidence_ids: list[str]


class GeminiCanaryValidatorRejection(BaseModel):
    code: GeminiCanaryRejectionCode
    rejected_phrase_or_claim_span: str
    rule_detail: str


class GeminiCanaryGroundingDiagnostic(BaseModel):
    synthetic_source_evidence: list[GeminiCanaryEvidenceDiagnostic]
    generated_rewrites: list[str]
    reconstructed_claims: list[GeminiCanaryClaimDiagnostic]
    supporting_evidence_ids: list[str]
    validator_rejections: list[GeminiCanaryValidatorRejection]


class GeminiStructuredOutputCanaryResult(BaseModel):
    provider: str = "gemini"
    model: str
    mode: GeminiIsolationMode = GeminiIsolationMode.MINIMAL
    request_count: int = Field(ge=0, le=1)
    finish_reason: str | None = None
    candidate_count: int = Field(default=0, ge=0)
    text_present: bool = False
    top_level_json_keys: list[str] = Field(default_factory=list)
    schema_valid: bool = False
    json_parsed: bool = False
    provider_contract_validated: bool = False
    evidence_ids_mapped: bool = False
    internal_variant_reconstructed: bool = False
    grounding_validation_reached: bool = False
    grounding_validation_passed: bool = False
    grounding_diagnostic: GeminiCanaryGroundingDiagnostic | None = None
    request_shape: ProviderRequestShapeDiagnostic
    issue: WriterPipelineIssue | None = None


def minimal_structured_output_canary_config(types_module: Any) -> Any:
    """Return the documented minimal Gemini structured-output config."""

    return types_module.GenerateContentConfig(
        response_mime_type="application/json",
        response_json_schema=MINIMAL_STRUCTURED_OUTPUT_CANARY_SCHEMA,
    )


def production_schema_only_canary_config(types_module: Any) -> Any:
    """Use the current minimal writer schema without production-only config."""

    return types_module.GenerateContentConfig(
        response_mime_type="application/json",
        response_json_schema=GEMINI_WRITER_RESPONSE_SCHEMA,
    )


def minimal_production_writer_canary_config(
    types_module: Any,
    settings: Settings,
) -> Any:
    """Use the real writer config with the minimal production transport schema."""

    return types_module.GenerateContentConfig(
        system_instruction=system_prompt(),
        temperature=settings.llm_temperature,
        max_output_tokens=settings.llm_bullet_rewrite_max_output_tokens,
        response_mime_type="application/json",
        response_json_schema=GEMINI_WRITER_RESPONSE_SCHEMA,
    )


def production_config_only_canary_config(
    types_module: Any,
    settings: Settings,
) -> Any:
    """Use production config field types and values with the minimal schema."""

    return types_module.GenerateContentConfig(
        system_instruction=_NEUTRAL_SYSTEM_INSTRUCTION,
        temperature=settings.llm_temperature,
        max_output_tokens=settings.llm_bullet_rewrite_max_output_tokens,
        response_mime_type="application/json",
        response_json_schema=MINIMAL_STRUCTURED_OUTPUT_CANARY_SCHEMA,
    )


def run_structured_output_canary(
    settings: Settings,
    *,
    mode: GeminiIsolationMode = GeminiIsolationMode.MINIMAL,
    client: Any | None = None,
    types_module: Any | None = None,
    sdk_version: str | None = None,
) -> GeminiStructuredOutputCanaryResult:
    """Make at most one manual-only canary request with no resume content."""

    if not settings.gemini_model:
        raise ValueError("GEMINI_MODEL is required for the Gemini canary.")
    owned_client = client is None
    if types_module is None:
        from google.genai import types

        types_module = types
    if client is None:
        from google import genai
        from google.genai import types as google_types

        api_key = settings.gemini_api_key
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required for the Gemini canary.")
        client = genai.Client(
            api_key=api_key,
            http_options=google_types.HttpOptions(
                timeout=settings.llm_timeout_seconds * 1000,
                retry_options=google_types.HttpRetryOptions(attempts=1),
            ),
        )
    writer_request: BulletRewriteRequest | None = None
    if mode is GeminiIsolationMode.PRODUCTION_SCHEMA_ONLY:
        schema_transform = transform_gemini_schema(GEMINI_WRITER_RESPONSE_SCHEMA)
        config = production_schema_only_canary_config(types_module)
        contents = "Return a JSON object with an empty rewrites array."
    elif mode is GeminiIsolationMode.PRODUCTION_CONFIG_ONLY:
        schema_transform = transform_gemini_schema(
            MINIMAL_STRUCTURED_OUTPUT_CANARY_SCHEMA
        )
        config = production_config_only_canary_config(types_module, settings)
        contents = "Return a JSON object whose status field is ready."
    elif mode is GeminiIsolationMode.MINIMAL_PRODUCTION_WRITER:
        writer_request = _minimal_writer_request()
        schema_transform = transform_gemini_schema(GEMINI_WRITER_RESPONSE_SCHEMA)
        config = minimal_production_writer_canary_config(types_module, settings)
        contents = _MINIMAL_WRITER_CONTENTS
    else:
        schema_transform = transform_gemini_schema(
            MINIMAL_STRUCTURED_OUTPUT_CANARY_SCHEMA
        )
        config = minimal_structured_output_canary_config(types_module)
        contents = "Return a JSON object whose status field is ready."
    request_shape = build_request_shape_diagnostic(
        client=client,
        model=settings.gemini_model,
        config=config,
        schema_transform=schema_transform,
        sdk_version=sdk_version,
    )
    if has_incompatible_sdk_or_api(request_shape):
        return GeminiStructuredOutputCanaryResult(
            model=settings.gemini_model,
            mode=mode,
            request_count=0,
            request_shape=request_shape,
            issue=WriterPipelineIssue(
                code=WriterPipelineFailureCode.INCOMPATIBLE_SDK_API_VERSION,
                stage=WriterPipelineStage.PROVIDER_REQUEST,
                provider_error_kind=LanguageModelErrorKind.CONFIGURATION.value,
                request_shape=request_shape,
            ),
        )
    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=contents,
            config=config,
        )
        candidates = list(getattr(response, "candidates", None) or [])
        finish_reason, _ = GeminiResumeLanguageModel._finish_diagnostics(response)
        parsed = getattr(response, "parsed", None)
        response_text = getattr(response, "text", None)
        text_present = bool(response_text and response_text.strip())
        if parsed is None and text_present:
            parsed = json.loads(
                GeminiResumeLanguageModel._clean_json_text(response_text or "")
            )
        top_level_keys = (
            sorted(str(key) for key in parsed)[:20] if isinstance(parsed, dict) else []
        )
        json_parsed = parsed is not None
        provider_contract_validated = False
        evidence_ids_mapped = False
        internal_variant_reconstructed = False
        grounding_validation_reached = False
        grounding_validation_passed = False
        grounding_diagnostic = None
        issue = None
        if mode is GeminiIsolationMode.MINIMAL_PRODUCTION_WRITER:
            (
                provider_contract_validated,
                evidence_ids_mapped,
                internal_variant_reconstructed,
                grounding_validation_reached,
                grounding_validation_passed,
                grounding_diagnostic,
                issue,
            ) = _validate_minimal_writer_canary_payload(
                parsed,
                writer_request,
                request_shape,
                finish_reason,
                len(candidates),
                text_present,
            )
            schema_valid = provider_contract_validated
            if not candidates or not text_present:
                issue = WriterPipelineIssue(
                    code=WriterPipelineFailureCode.EMPTY_PROVIDER_RESPONSE,
                    stage=WriterPipelineStage.RESPONSE_EXTRACTION,
                    finish_reason=finish_reason,
                    candidate_count=len(candidates),
                    text_present=text_present,
                    request_shape=request_shape,
                )
        else:
            schema_valid = _payload_matches_mode(parsed, mode)
        if not schema_valid:
            issue = issue or WriterPipelineIssue(
                code=(
                    WriterPipelineFailureCode.EMPTY_PROVIDER_RESPONSE
                    if parsed is None
                    else WriterPipelineFailureCode.TYPED_SCHEMA_MISMATCH
                ),
                stage=(
                    WriterPipelineStage.RESPONSE_EXTRACTION
                    if parsed is None
                    else WriterPipelineStage.TYPED_SCHEMA_VALIDATION
                ),
                finish_reason=finish_reason,
                candidate_count=len(candidates),
                text_present=text_present,
                top_level_json_keys=top_level_keys,
                request_shape=request_shape,
            )
        return GeminiStructuredOutputCanaryResult(
            model=settings.gemini_model,
            mode=mode,
            request_count=1,
            finish_reason=finish_reason,
            candidate_count=len(candidates),
            text_present=text_present,
            top_level_json_keys=top_level_keys,
            schema_valid=schema_valid,
            json_parsed=json_parsed,
            provider_contract_validated=provider_contract_validated,
            evidence_ids_mapped=evidence_ids_mapped,
            internal_variant_reconstructed=internal_variant_reconstructed,
            grounding_validation_reached=grounding_validation_reached,
            grounding_validation_passed=grounding_validation_passed,
            grounding_diagnostic=grounding_diagnostic,
            request_shape=request_shape,
            issue=issue,
        )
    except json.JSONDecodeError as error:
        return GeminiStructuredOutputCanaryResult(
            model=settings.gemini_model,
            mode=mode,
            request_count=1,
            request_shape=request_shape,
            issue=WriterPipelineIssue(
                code=WriterPipelineFailureCode.MALFORMED_JSON,
                stage=WriterPipelineStage.JSON_PARSING,
                exception_type=type(error).__name__,
                request_shape=request_shape,
            ),
        )
    except Exception as error:
        mapped = GeminiResumeLanguageModel._map_error(
            error,
            request_shape=request_shape,
        )
        return GeminiStructuredOutputCanaryResult(
            model=settings.gemini_model,
            mode=mode,
            request_count=1,
            request_shape=request_shape,
            issue=mapped.diagnostic,
        )
    finally:
        if owned_client:
            client.close()


def _payload_matches_mode(parsed: object, mode: GeminiIsolationMode) -> bool:
    if mode is GeminiIsolationMode.PRODUCTION_SCHEMA_ONLY:
        try:
            GeminiProviderWriterOutput.model_validate(parsed)
        except ValidationError:
            return False
        return True
    return isinstance(parsed, dict) and isinstance(parsed.get("status"), str)


def _validate_minimal_writer_canary_payload(
    parsed: object,
    request: BulletRewriteRequest | None,
    request_shape: ProviderRequestShapeDiagnostic,
    finish_reason: str | None,
    candidate_count: int,
    text_present: bool,
) -> tuple[
    bool,
    bool,
    bool,
    bool,
    bool,
    GeminiCanaryGroundingDiagnostic | None,
    WriterPipelineIssue | None,
]:
    if request is None:
        raise RuntimeError("Minimal writer canary request was not constructed.")
    try:
        provider_output = GeminiProviderWriterOutput.model_validate(parsed)
    except ValidationError as error:
        return (
            False,
            False,
            False,
            False,
            False,
            None,
            WriterPipelineIssue(
                code=WriterPipelineFailureCode.TYPED_SCHEMA_MISMATCH,
                stage=WriterPipelineStage.TYPED_SCHEMA_VALIDATION,
                exception_type=type(error).__name__,
                finish_reason=finish_reason,
                candidate_count=candidate_count,
                text_present=text_present,
                request_shape=request_shape,
            ),
        )
    try:
        mapping = map_provider_writer_output(provider_output, request)
    except GeminiWriterMappingError as error:
        diagnostic = _canary_grounding_diagnostic(
            request,
            provider_output,
            None,
            error.failures,
        )
        return (
            True,
            False,
            False,
            False,
            False,
            diagnostic,
            WriterPipelineIssue(
                code=WriterPipelineFailureCode.CLAIM_GROUNDING_REJECTION,
                stage=WriterPipelineStage.CLAIM_VALIDATION,
                provider_error_kind=LanguageModelErrorKind.VALIDATION.value,
                finish_reason=finish_reason,
                candidate_count=candidate_count,
                text_present=text_present,
                request_shape=request_shape,
                sanitized_detail=(
                    "Provider writer response failed authorized evidence mapping."
                ),
            ),
        )
    internal_output = mapping.output
    mapping_failures = [
        detail
        for outcome in mapping.mapping_outcomes
        if outcome.mapping_status is not ProviderRewriteMappingStatus.MAPPED
        for detail in outcome.failure_details
    ]
    if mapping_failures:
        diagnostic = _canary_grounding_diagnostic(
            request,
            provider_output,
            internal_output,
            mapping_failures,
        )
        return (
            True,
            False,
            bool(internal_output.bullets),
            False,
            False,
            diagnostic,
            WriterPipelineIssue(
                code=WriterPipelineFailureCode.CLAIM_GROUNDING_REJECTION,
                stage=WriterPipelineStage.CLAIM_VALIDATION,
                provider_error_kind=LanguageModelErrorKind.VALIDATION.value,
                finish_reason=finish_reason,
                candidate_count=candidate_count,
                text_present=text_present,
                request_shape=request_shape,
                sanitized_detail=(
                    "Provider writer response failed authorized evidence mapping."
                ),
            ),
        )
    try:
        validate_rewrites(
            internal_output,
            request.groups,
            max_bullets_per_entry=request.max_bullets_per_entry,
            max_total_lines=request.max_total_lines,
        )
    except GroundingValidationError as error:
        diagnostic = _canary_grounding_diagnostic(
            request,
            provider_output,
            internal_output,
            error.failures,
        )
        return (
            True,
            True,
            bool(internal_output.bullets),
            True,
            False,
            diagnostic,
            WriterPipelineIssue(
                code=WriterPipelineFailureCode.CLAIM_GROUNDING_REJECTION,
                stage=WriterPipelineStage.CLAIM_VALIDATION,
                provider_error_kind="grounding_validation",
                finish_reason=finish_reason,
                candidate_count=candidate_count,
                text_present=text_present,
                request_shape=request_shape,
                sanitized_detail=(
                    "Grounding validation rejected the reconstructed canary variant."
                ),
            ),
        )
    return (
        True,
        True,
        bool(internal_output.bullets),
        True,
        True,
        _canary_grounding_diagnostic(request, provider_output, internal_output, []),
        None,
    )


def _canary_grounding_diagnostic(
    request: BulletRewriteRequest,
    provider_output: GeminiProviderWriterOutput,
    internal_output: BulletRewriteOutput | None,
    failures: list[str],
) -> GeminiCanaryGroundingDiagnostic:
    generated_rewrites = [rewrite.rewritten_text for rewrite in provider_output.rewrites]
    claims = [
        GeminiCanaryClaimDiagnostic(
            text=claim.text,
            supporting_evidence_ids=claim.supporting_evidence_ids,
        )
        for bullet in (internal_output.bullets if internal_output is not None else [])
        for claim in bullet.claims
    ]
    supporting_ids = list(
        dict.fromkeys(
            evidence_id
            for rewrite in provider_output.rewrites
            for evidence_id in rewrite.source_evidence_ids
        )
    )
    source_evidence = [
        GeminiCanaryEvidenceDiagnostic(
            evidence_id=evidence_id,
            source_text=source_text,
        )
        for group in request.groups
        for evidence_id, source_text in zip(
            group.evidence_ids,
            group.source_texts,
            strict=False,
        )
    ]
    fallback_span = generated_rewrites[0] if generated_rewrites else "provider rewrite"
    return GeminiCanaryGroundingDiagnostic(
        synthetic_source_evidence=source_evidence,
        generated_rewrites=generated_rewrites,
        reconstructed_claims=claims,
        supporting_evidence_ids=supporting_ids,
        validator_rejections=[
            _classify_canary_rejection(failure, fallback_span)
            for failure in dict.fromkeys(failures)
        ],
    )


def _classify_canary_rejection(
    failure: str,
    fallback_span: str,
) -> GeminiCanaryValidatorRejection:
    normalized = failure.casefold()
    quoted_values = re.findall(r"'([^']+)'", failure)
    rejected_span = ", ".join(quoted_values) or fallback_span
    if "unsupported technical or named terms" in normalized:
        code = GeminiCanaryRejectionCode.UNSUPPORTED_TECHNOLOGY
    elif "unsupported numeric facts" in normalized or "required facts dropped" in normalized:
        code = GeminiCanaryRejectionCode.CHANGED_NUMBER_OR_METRIC
    elif "unsupported outcomes" in normalized:
        code = GeminiCanaryRejectionCode.UNSUPPORTED_OUTCOME
    elif "ownership or causality" in normalized:
        code = GeminiCanaryRejectionCode.OWNERSHIP_EXPANSION
    elif "narrow" in normalized:
        code = GeminiCanaryRejectionCode.UNSUPPORTED_NARROWING
    elif "cross-entry" in normalized or "across entries" in normalized:
        code = GeminiCanaryRejectionCode.CROSS_ENTRY_EVIDENCE
    elif "semantic" in normalized or "equival" in normalized:
        code = GeminiCanaryRejectionCode.SEMANTIC_EQUIVALENCE_FAILURE
    elif "unknown evidence" in normalized or "unknown evidence group" in normalized:
        code = GeminiCanaryRejectionCode.UNKNOWN_EVIDENCE
    elif "repeat" in normalized or "duplicate" in normalized:
        code = GeminiCanaryRejectionCode.DUPLICATE_EVIDENCE
    elif "claim" in normalized or "provenance" in normalized:
        code = GeminiCanaryRejectionCode.CLAIM_PROVENANCE
    else:
        code = GeminiCanaryRejectionCode.ANOTHER_PRECISE_RULE
    return GeminiCanaryValidatorRejection(
        code=code,
        rejected_phrase_or_claim_span=rejected_span,
        rule_detail=failure,
    )


def _minimal_writer_request() -> BulletRewriteRequest:
    return BulletRewriteRequest(
        primary_focus="Backend engineering",
        target_terms=["Python", "API", "testing"],
        groups=[
            ApprovedEvidenceGroup(
                entry_id="canary-entry",
                evidence_ids=[MINIMAL_WRITER_CANARY_EVIDENCE_ID],
                source_texts=[MINIMAL_WRITER_CANARY_SOURCE],
                technologies=["Python", "API"],
                capabilities=["development", "testing", "request processing"],
                metrics=["500 requests per day"],
                max_rendered_lines=2,
            )
        ],
        max_bullets_per_entry=1,
        max_total_lines=2,
    )


__all__ = [
    "GeminiStructuredOutputCanaryResult",
    "GeminiCanaryGroundingDiagnostic",
    "GeminiCanaryRejectionCode",
    "GeminiIsolationMode",
    "MINIMAL_STRUCTURED_OUTPUT_CANARY_SCHEMA",
    "MINIMAL_WRITER_CANARY_EVIDENCE_ID",
    "MINIMAL_WRITER_CANARY_SAFE_PARAPHRASES",
    "MINIMAL_WRITER_CANARY_SOURCE",
    "minimal_structured_output_canary_config",
    "minimal_production_writer_canary_config",
    "production_config_only_canary_config",
    "production_schema_only_canary_config",
    "run_structured_output_canary",
]
