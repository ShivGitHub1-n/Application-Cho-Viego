from copy import deepcopy

import pytest
from pydantic import ValidationError

from resume_tailor.application.generation_diagnostics import GenerationTelemetry
from resume_tailor.domain.generated_artifact import GenerationStage, StageStatus
from resume_tailor.domain.hybrid_resume import (
    ProviderFieldViolation,
    WriterPipelineFailureCode,
    WriterPipelineStage,
)
from resume_tailor.domain.llm_models import (
    ApprovedEvidenceGroup,
    BulletRewriteOutput,
    BulletRewriteRequest,
    BulletShorteningOutput,
    CompositionRecommendationOutput,
    LanguageModelError,
    LanguageModelErrorKind,
    LlmOperation,
    OpportunityAnalysisOutput,
    OpportunityAnalysisRequest,
    ProfileExtractionOutput,
    ProfileExtractionRequest,
    SkillCompositionOutput,
)
from resume_tailor.domain.models import RoleFamily
from resume_tailor.infrastructure.config import Settings
from resume_tailor.infrastructure.gemini_adapter import GeminiResumeLanguageModel
from resume_tailor.infrastructure.gemini_canary import (
    MINIMAL_STRUCTURED_OUTPUT_CANARY_SCHEMA,
    MINIMAL_WRITER_CANARY_EVIDENCE_ID,
    MINIMAL_WRITER_CANARY_SAFE_PARAPHRASES,
    MINIMAL_WRITER_CANARY_SOURCE,
    GeminiCanaryRejectionCode,
    GeminiIsolationMode,
    GeminiStructuredOutputCanaryResult,
    minimal_production_writer_canary_config,
    minimal_structured_output_canary_config,
    production_config_only_canary_config,
    production_schema_only_canary_config,
    run_structured_output_canary,
)
from resume_tailor.infrastructure.gemini_request_diagnostics import (
    build_request_shape_diagnostic,
)
from resume_tailor.infrastructure.gemini_schema import (
    GeminiSchemaCompatibilityError,
    audit_gemini_schema,
    gemini_schema_transform,
    inline_local_schema_refs,
    transform_gemini_schema,
)
from resume_tailor.infrastructure.gemini_writer_contract import (
    GEMINI_WRITER_RESPONSE_SCHEMA,
)
from resume_tailor.infrastructure.llm_cache import InMemoryLlmCache


def test_gemini_client_uses_interactive_timeout_and_disables_sdk_retries(
    monkeypatch,
) -> None:
    from google import genai

    captured: dict[str, object] = {}

    class Client:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(genai, "Client", Client)
    GeminiResumeLanguageModel(
        Settings(
            _env_file=None,
            gemini_api_key="configured-secret",
            gemini_model="configured-model",
            llm_timeout_seconds=27,
        )
    )

    http_options = captured["http_options"]
    assert http_options.timeout == 27_000
    assert http_options.retry_options.attempts == 1


def test_gemini_error_mapping_is_provider_specific() -> None:
    error = GeminiResumeLanguageModel._map_error(RuntimeError("429 resource exhausted"))

    assert error.kind == LanguageModelErrorKind.RATE_LIMITED
    assert error.retryable is True
    assert error.diagnostic is not None
    assert (
        error.diagnostic.code
        is WriterPipelineFailureCode.PROVIDER_TRANSPORT_OR_SDK_ERROR
    )
    assert error.diagnostic.stage is WriterPipelineStage.PROVIDER_REQUEST
    assert error.diagnostic.exception_type == "RuntimeError"


def test_provider_schemas_use_only_audited_gemini_keywords() -> None:
    for model_type in (
        OpportunityAnalysisOutput,
        CompositionRecommendationOutput,
        BulletRewriteOutput,
        BulletShorteningOutput,
        SkillCompositionOutput,
    ):
        transform = gemini_schema_transform(model_type)

        assert transform.provider_audit.unsupported_keyword_paths == ()
        assert transform.provider_audit.complexity_findings == ()
        assert "additionalProperties" in str(transform.schema)
        assert transform.provider_audit.ref_count == 0
        assert transform.provider_audit.defs_count == 0
        assert transform.inlined_ref_count == transform.pre_inline_audit.ref_count
        assert transform.pre_inline_audit.ref_sibling_violation_paths == ()


def test_schema_compatibility_audit_is_deterministic_and_non_mutating() -> None:
    source = BulletRewriteOutput.model_json_schema()
    original = deepcopy(source)

    first = transform_gemini_schema(source)
    second = transform_gemini_schema(source)

    assert source == original
    assert first == second
    assert first.provider_audit == audit_gemini_schema(first.schema)
    assert first.removed_keyword_paths


def test_ref_sibling_audit_reports_exact_json_path() -> None:
    schema = {
        "$defs": {"Value": {"type": "string"}},
        "type": "object",
        "properties": {
            "safe": {"$ref": "#/$defs/Value"},
            "unsafe": {
                "$ref": "#/$defs/Value",
                "description": "Non-$ sibling",
            },
        },
    }

    audit = audit_gemini_schema(schema)

    assert audit.ref_sibling_violation_paths == ("$.properties.unsafe",)
    with pytest.raises(GeminiSchemaCompatibilityError, match="non-\\$ siblings"):
        inline_local_schema_refs(schema)


def test_local_refs_are_inlined_without_mutating_schema() -> None:
    schema = {
        "$defs": {
            "Choice": {"type": "string", "enum": ["one", "two"]},
            "Record": {
                "type": "object",
                "properties": {"choice": {"$ref": "#/$defs/Choice"}},
                "required": ["choice"],
            },
        },
        "type": "array",
        "items": {"$ref": "#/$defs/Record"},
    }
    original = deepcopy(schema)

    inlined, count = inline_local_schema_refs(schema)

    assert schema == original
    assert count == 2
    assert "$defs" not in str(inlined)
    assert "$ref" not in str(inlined)
    assert inlined["items"]["type"] == "object"
    assert inlined["items"]["required"] == ["choice"]
    assert inlined["items"]["properties"]["choice"] == {
        "type": "string",
        "enum": ["one", "two"],
    }


def test_provider_schema_omits_local_constraints_but_keeps_contract_shape() -> None:
    transform = gemini_schema_transform(BulletRewriteOutput)
    schema_text = str(transform.schema)

    assert "minLength" not in schema_text
    assert "maxLength" not in schema_text
    assert "default" not in schema_text
    assert "$defs" not in schema_text
    assert "$ref" not in schema_text
    assert transform.schema["type"] == "object"
    assert transform.schema["properties"]["bullets"]["type"] == "array"
    rewrite_schema = transform.schema["properties"]["bullets"]["items"]
    assert rewrite_schema["properties"]["entry_id"]["type"] == "string"
    assert set(rewrite_schema["required"]) == {
        "entry_id",
        "final_bullet_text",
        "source_evidence_ids",
        "evidence_combined",
        "confidence",
    }
    with pytest.raises(ValidationError):
        BulletRewriteOutput.model_validate(
            {
                "bullets": [
                    {
                        "entry_id": "entry",
                        "final_bullet_text": "",
                        "source_evidence_ids": ["evidence"],
                        "evidence_combined": False,
                        "confidence": 0.9,
                    }
                ]
            }
        )


def test_minimal_canary_config_matches_documented_contract() -> None:
    class Types:
        @staticmethod
        def GenerateContentConfig(**kwargs: object) -> dict[str, object]:
            return kwargs

    config = minimal_structured_output_canary_config(Types())

    assert config == {
        "response_mime_type": "application/json",
        "response_json_schema": MINIMAL_STRUCTURED_OUTPUT_CANARY_SCHEMA,
    }


def test_production_isolation_configs_separate_schema_and_extra_fields() -> None:
    class Types:
        @staticmethod
        def GenerateContentConfig(**kwargs: object) -> dict[str, object]:
            return kwargs

    settings = Settings(
        _env_file=None,
        gemini_model="gemini-3.1-flash-lite",
        llm_temperature=0.1,
        llm_bullet_rewrite_max_output_tokens=8192,
    )

    schema_only = production_schema_only_canary_config(Types())
    config_only = production_config_only_canary_config(Types(), settings)

    assert set(schema_only) == {"response_mime_type", "response_json_schema"}
    assert schema_only["response_json_schema"] == GEMINI_WRITER_RESPONSE_SCHEMA
    assert "$ref" not in str(schema_only["response_json_schema"])
    assert "$defs" not in str(schema_only["response_json_schema"])
    assert set(config_only) == {
        "system_instruction",
        "temperature",
        "max_output_tokens",
        "response_mime_type",
        "response_json_schema",
    }
    assert isinstance(config_only["system_instruction"], str)
    assert config_only["temperature"] == 0.1
    assert config_only["max_output_tokens"] == 8192
    assert config_only["response_json_schema"] == MINIMAL_STRUCTURED_OUTPUT_CANARY_SCHEMA

    writer_config = minimal_production_writer_canary_config(Types(), settings)
    assert set(writer_config) == {
        "system_instruction",
        "temperature",
        "max_output_tokens",
        "response_mime_type",
        "response_json_schema",
    }
    assert writer_config["response_json_schema"] == GEMINI_WRITER_RESPONSE_SCHEMA


def test_manual_canary_uses_one_minimal_structured_output_request() -> None:
    captured: list[dict[str, object]] = []

    class Candidate:
        finish_reason = "STOP"
        finish_message = "Completed"

    class Response:
        parsed = {"status": "ready"}
        candidates = [Candidate()]

    class Models:
        def generate_content(self, **kwargs: object) -> Response:
            captured.append(kwargs)
            return Response()

    class HttpOptions:
        api_version = "v1beta"
        base_url = "https://generativelanguage.googleapis.com/"

    class ApiClient:
        _http_options = HttpOptions()

    class Client:
        models = Models()
        _api_client = ApiClient()

    class Types:
        @staticmethod
        def GenerateContentConfig(**kwargs: object) -> dict[str, object]:
            return kwargs

    result = run_structured_output_canary(
        Settings(_env_file=None, gemini_model="gemini-3.1-flash-lite"),
        client=Client(),
        types_module=Types(),
        sdk_version="2.1.0",
    )

    assert result.request_count == 1
    assert result.schema_valid is True
    assert result.finish_reason == "STOP"
    assert len(captured) == 1
    assert captured[0]["model"] == "gemini-3.1-flash-lite"
    assert captured[0]["config"] == {
        "response_mime_type": "application/json",
        "response_json_schema": MINIMAL_STRUCTURED_OUTPUT_CANARY_SCHEMA,
    }


@pytest.mark.parametrize(
    ("mode", "parsed", "expected_config_fields"),
    [
        (
            GeminiIsolationMode.PRODUCTION_SCHEMA_ONLY,
            {"rewrites": []},
            {"response_mime_type", "response_json_schema"},
        ),
        (
            GeminiIsolationMode.PRODUCTION_CONFIG_ONLY,
            {"status": "ready"},
            {
                "system_instruction",
                "temperature",
                "max_output_tokens",
                "response_mime_type",
                "response_json_schema",
            },
        ),
    ],
)
def test_each_production_isolation_mode_makes_exactly_one_safe_request(
    mode: GeminiIsolationMode,
    parsed: dict[str, object],
    expected_config_fields: set[str],
) -> None:
    captured: list[dict[str, object]] = []

    class Candidate:
        finish_reason = "STOP"
        finish_message = "Completed"

    class Response:
        candidates = [Candidate()]

        def __init__(self, payload: dict[str, object]) -> None:
            self.parsed = payload

    class Models:
        def generate_content(self, **kwargs: object) -> Response:
            captured.append(kwargs)
            return Response(parsed)

    class Client:
        models = Models()

    class Types:
        @staticmethod
        def GenerateContentConfig(**kwargs: object) -> dict[str, object]:
            return kwargs

    result = run_structured_output_canary(
        Settings(
            _env_file=None,
            gemini_model="gemini-3.1-flash-lite",
            llm_temperature=0.1,
            llm_bullet_rewrite_max_output_tokens=8192,
        ),
        mode=mode,
        client=Client(),
        types_module=Types(),
        sdk_version="2.12.1",
    )

    assert result.mode is mode
    assert result.request_count == 1
    assert result.schema_valid is True
    assert result.issue is None
    assert len(captured) == 1
    config = captured[0]["config"]
    assert isinstance(config, dict)
    assert set(config) == expected_config_fields
    serialized = result.model_dump_json()
    assert "Return a JSON" not in serialized
    assert "structured JSON" not in serialized


def _run_minimal_production_writer_canary(
    rewrite: str,
) -> tuple[GeminiStructuredOutputCanaryResult, list[dict[str, object]]]:
    captured: list[dict[str, object]] = []

    class Candidate:
        finish_reason = "STOP"
        finish_message = "Completed"

    class Response:
        parsed = {
            "rewrites": [
                {
                    "source_evidence_ids": [MINIMAL_WRITER_CANARY_EVIDENCE_ID],
                    "rewritten_text": rewrite,
                    "length_class": "standard",
                }
            ]
        }
        text = "synthetic canary response text present"
        candidates = [Candidate()]

    class Models:
        def generate_content(self, **kwargs: object) -> Response:
            captured.append(kwargs)
            return Response()

    class Client:
        models = Models()

    class Types:
        @staticmethod
        def GenerateContentConfig(**kwargs: object) -> dict[str, object]:
            return kwargs

    result = run_structured_output_canary(
        Settings(
            _env_file=None,
            gemini_model="gemini-3.1-flash-lite",
            llm_temperature=0.1,
            llm_bullet_rewrite_max_output_tokens=8192,
        ),
        mode=GeminiIsolationMode.MINIMAL_PRODUCTION_WRITER,
        client=Client(),
        types_module=Types(),
        sdk_version="2.12.1",
    )
    return result, captured


def test_minimal_production_writer_canary_reaches_local_grounding_once() -> None:
    rewrite = MINIMAL_WRITER_CANARY_SAFE_PARAPHRASES[0]
    result, captured = _run_minimal_production_writer_canary(rewrite)

    assert len(captured) == 1
    assert result.request_count == 1
    assert result.finish_reason == "STOP"
    assert result.candidate_count == 1
    assert result.text_present is True
    assert result.json_parsed is True
    assert result.provider_contract_validated is True
    assert result.evidence_ids_mapped is True
    assert result.internal_variant_reconstructed is True
    assert result.grounding_validation_reached is True
    assert result.grounding_validation_passed is True
    assert result.issue is None
    assert result.grounding_diagnostic is not None
    assert result.grounding_diagnostic.synthetic_source_evidence[0].source_text == (
        MINIMAL_WRITER_CANARY_SOURCE
    )
    assert result.grounding_diagnostic.generated_rewrites == [rewrite]
    assert result.grounding_diagnostic.reconstructed_claims[0].text == rewrite
    assert result.grounding_diagnostic.reconstructed_claims[
        0
    ].supporting_evidence_ids == [MINIMAL_WRITER_CANARY_EVIDENCE_ID]
    assert result.grounding_diagnostic.validator_rejections == []
    config = captured[0]["config"]
    assert isinstance(config, dict)
    assert config["response_json_schema"] == GEMINI_WRITER_RESPONSE_SCHEMA
    serialized = result.model_dump_json()
    assert MINIMAL_WRITER_CANARY_SOURCE in serialized
    assert rewrite in serialized
    assert MINIMAL_WRITER_CANARY_EVIDENCE_ID in serialized


@pytest.mark.parametrize(
    ("rewrite", "expected_code", "expected_span"),
    [
        (
            "Built and tested a Python API on AWS that processed 500 requests per day.",
            GeminiCanaryRejectionCode.UNSUPPORTED_TECHNOLOGY,
            "aws",
        ),
        (
            "Built and tested a Python API that processed 600 requests per day.",
            GeminiCanaryRejectionCode.CHANGED_NUMBER_OR_METRIC,
            "600",
        ),
        (
            "Built and tested a Python API that improved reliability while processing "
            "500 requests per day.",
            GeminiCanaryRejectionCode.UNSUPPORTED_OUTCOME,
            "improved",
        ),
    ],
)
def test_minimal_writer_canary_reports_exact_safe_grounding_rejection(
    rewrite: str,
    expected_code: GeminiCanaryRejectionCode,
    expected_span: str,
) -> None:
    result, captured = _run_minimal_production_writer_canary(rewrite)

    assert len(captured) == 1
    assert result.request_count == 1
    assert result.provider_contract_validated is True
    assert result.evidence_ids_mapped is True
    assert result.internal_variant_reconstructed is True
    assert result.grounding_validation_reached is True
    assert result.grounding_validation_passed is False
    assert result.grounding_diagnostic is not None
    assert result.grounding_diagnostic.generated_rewrites == [rewrite]
    assert result.grounding_diagnostic.synthetic_source_evidence[0].source_text == (
        MINIMAL_WRITER_CANARY_SOURCE
    )
    assert result.grounding_diagnostic.reconstructed_claims[0].text == rewrite
    rejections = result.grounding_diagnostic.validator_rejections
    assert any(rejection.code is expected_code for rejection in rejections)
    assert any(
        expected_span in rejection.rejected_phrase_or_claim_span.casefold()
        for rejection in rejections
        if rejection.code is expected_code
    )


def test_adapter_passes_sanitized_schema_to_gemini_client() -> None:
    captured: dict[str, object] = {}

    class Response:
        parsed = OpportunityAnalysisOutput(
            role_families=[RoleFamily.EMBEDDED_FIRMWARE],
            primary_focus="embedded firmware",
            confidence=0.8,
            reasoning="Synthetic response.",
        )
        usage_metadata = None

    class Models:
        def generate_content(self, **kwargs: object) -> Response:
            captured.update(kwargs)
            return Response()

    class Client:
        models = Models()

    class Types:
        @staticmethod
        def GenerateContentConfig(**kwargs: object) -> dict[str, object]:
            return kwargs

    adapter = object.__new__(GeminiResumeLanguageModel)
    adapter._client = Client()
    adapter._types = Types()
    adapter._model = "test-model"
    adapter._temperature = 0.1
    adapter._max_output_tokens = 100
    adapter._cache = InMemoryLlmCache(60)

    adapter.analyze_opportunity(
        OpportunityAnalysisRequest(
            posting_id="posting-1",
            title="Embedded Engineer",
            description="Develop embedded firmware.",
            supported_role_families=[RoleFamily.EMBEDDED_FIRMWARE],
        )
    )

    config = captured["config"]
    assert isinstance(config, dict)
    assert config["response_mime_type"] == "application/json"
    assert "response_schema" not in config
    assert "additionalProperties" in str(config["response_json_schema"])
    assert "$ref" not in str(config["response_json_schema"])
    assert "$defs" not in str(config["response_json_schema"])
    assert "minLength" not in str(config["response_json_schema"])
    assert "maxLength" not in str(config["response_json_schema"])


def _profile_request() -> ProfileExtractionRequest:
    return ProfileExtractionRequest(
        profile_id="profile-1",
        source_format="docx",
        extracted_text="Candidate\nBuilt firmware.",
    )


def _profile_adapter(response: object, captured: dict[str, object]) -> GeminiResumeLanguageModel:
    class Models:
        def generate_content(self, **kwargs: object) -> object:
            captured.update(kwargs)
            return response

    class Client:
        models = Models()

    class Types:
        @staticmethod
        def GenerateContentConfig(**kwargs: object) -> dict[str, object]:
            return kwargs

    adapter = object.__new__(GeminiResumeLanguageModel)
    adapter._client = Client()
    adapter._types = Types()
    adapter._model = "test-model"
    adapter._temperature = 0.1
    adapter._max_output_tokens = 100
    adapter._profile_extraction_max_output_tokens = 8192
    adapter._cache = InMemoryLlmCache(60)
    return adapter


def test_profile_extraction_uses_compact_schema_and_explicit_budget() -> None:
    captured: dict[str, object] = {}

    class Response:
        parsed = ProfileExtractionOutput(
            profile={"id": "profile-1", "user_id": "local", "display_name": "Candidate"}
        )
        usage_metadata = None

    adapter = _profile_adapter(Response(), captured)
    adapter.extract_profile(_profile_request())
    config = captured["config"]
    assert isinstance(config, dict)
    assert config["max_output_tokens"] == 8192
    schema = config["response_json_schema"]
    experience_schema = schema["properties"]["profile"]["properties"][
        "experiences"
    ]["items"]
    assert (
        "description"
        not in experience_schema["properties"]
    )
    assert "bullets" not in experience_schema["properties"]
    assert "bullet_points" not in experience_schema["properties"]


def test_truncated_profile_response_is_actionable_and_not_retried() -> None:
    calls = 0

    class Candidate:
        finish_reason = "MAX_TOKENS"
        finish_message = "Output reached token limit."

    class Response:
        parsed = None
        text = '{"profile":{"id":"profile-1","display_name":"Candidate'
        candidates = [Candidate()]
        usage_metadata = type("Usage", (), {"candidates_token_count": 8192})()

    captured: dict[str, object] = {}
    adapter = _profile_adapter(Response(), captured)
    original = adapter._client.models.generate_content

    def counted(**kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return original(**kwargs)

    adapter._client.models.generate_content = counted
    with pytest.raises(LanguageModelError) as error:
        adapter.extract_profile(_profile_request())
    assert error.value.kind == LanguageModelErrorKind.TRUNCATED_RESPONSE
    assert "not retried automatically" in str(error.value)
    assert calls == 1


def test_non_truncated_malformed_profile_json_remains_schema_error() -> None:
    class Candidate:
        finish_reason = "STOP"
        finish_message = "Completed"

    class Response:
        parsed = None
        text = '{"profile":}'
        candidates = [Candidate()]
        usage_metadata = None

    adapter = _profile_adapter(Response(), {})
    with pytest.raises(LanguageModelError) as error:
        adapter.extract_profile(_profile_request())
    assert error.value.kind == LanguageModelErrorKind.MALFORMED_RESPONSE
    assert error.value.diagnostic is not None
    assert error.value.diagnostic.code is WriterPipelineFailureCode.MALFORMED_JSON
    assert error.value.diagnostic.stage is WriterPipelineStage.JSON_PARSING


def _rewrite_request() -> BulletRewriteRequest:
    return BulletRewriteRequest(
        primary_focus="Embedded firmware",
        groups=[
            ApprovedEvidenceGroup(
                entry_id="embedded-entry",
                evidence_ids=["embedded-evidence"],
                source_texts=["Developed STM32 firmware and validated SPI communication."],
                technologies=["STM32", "SPI"],
                capabilities=["firmware", "validation"],
                max_rendered_lines=2,
            )
        ],
        max_bullets_per_entry=2,
        max_total_lines=12,
    )


def _rewrite_adapter(response: object) -> GeminiResumeLanguageModel:
    class Models:
        def generate_content(self, **kwargs: object) -> object:
            return response

    class Client:
        models = Models()

    class Types:
        @staticmethod
        def GenerateContentConfig(**kwargs: object) -> dict[str, object]:
            return kwargs

    adapter = object.__new__(GeminiResumeLanguageModel)
    adapter._client = Client()
    adapter._types = Types()
    adapter._model = "test-model"
    adapter._temperature = 0.1
    adapter._max_output_tokens = 100
    adapter._bullet_rewrite_max_output_tokens = 1000
    adapter._profile_extraction_max_output_tokens = 1000
    adapter._cache = InMemoryLlmCache(60)
    adapter._telemetry = GenerationTelemetry()
    return adapter


class _StopCandidate:
    finish_reason = "STOP"
    finish_message = "Completed"


def test_valid_gemini_structured_output_reaches_typed_parsing() -> None:
    class Response:
        parsed = {
            "rewrites": [
                {
                    "rewritten_text": (
                        "Built STM32 firmware and validated SPI communication."
                    ),
                    "source_evidence_ids": ["embedded-evidence"],
                    "length_class": "standard",
                }
            ]
        }
        candidates = [_StopCandidate()]
        usage_metadata = None

    adapter = _rewrite_adapter(Response())
    result = adapter.rewrite_bullets(_rewrite_request())

    assert len(result.output.bullets) == 1
    assert len(result.mapping_outcomes) == 1
    assert result.mapping_outcomes[0].mapping_status.value == "mapped"
    assert result.metadata.finish_reason == "STOP"
    assert result.metadata.request_shape is not None
    assert result.metadata.request_shape.config_field_names == [
        "max_output_tokens",
        "response_json_schema",
        "response_mime_type",
        "system_instruction",
        "temperature",
    ]
    parsing = {
        timing.stage: timing for timing in adapter._telemetry.timings()
    }[GenerationStage.PROVIDER_RESPONSE_PARSING]
    assert parsing.status is StageStatus.COMPLETED


def test_request_shape_diagnostic_is_sanitized_and_flags_old_model_sdk() -> None:
    class HttpOptions:
        api_version = "v1beta"
        base_url = "https://generativelanguage.googleapis.com/?key=configured-secret"

    class ApiClient:
        _http_options = HttpOptions()

    class Client:
        _api_client = ApiClient()

    transform = gemini_schema_transform(BulletRewriteOutput)
    diagnostic = build_request_shape_diagnostic(
        client=Client(),
        model="gemini-3.1-flash-lite",
        config={
            "system_instruction": "complete prompt and profile must stay secret",
            "response_mime_type": "application/json",
            "response_json_schema": transform.schema,
        },
        schema_transform=transform,
        sdk_version="1.75.0",
    )

    serialized = diagnostic.model_dump_json()
    assert "configured-secret" not in serialized
    assert "complete prompt" not in serialized
    assert "profile must stay secret" not in serialized
    assert diagnostic.endpoint == "https://generativelanguage.googleapis.com/"
    assert diagnostic.api_version == "v1beta"
    assert diagnostic.schema_byte_length == 1926
    assert diagnostic.schema_nesting_depth == 7
    assert diagnostic.schema_property_count == 17
    assert diagnostic.schema_enum_count == 2
    assert diagnostic.schema_ref_count == 0
    assert diagnostic.schema_defs_count == 0
    assert diagnostic.schema_pre_inline_ref_count == 4
    assert diagnostic.schema_pre_inline_defs_count == 4
    assert diagnostic.schema_inlined_ref_count == 4
    assert diagnostic.schema_ref_sibling_violation_paths == []
    assert diagnostic.source_schema_ref_sibling_violation_paths == [
        "$.$defs.BulletRewrite.properties.intended_length_class",
        "$.$defs.BulletRewrite.properties.support",
    ]
    assert diagnostic.compatibility_findings == [
        "incompatible_sdk_api_version:gemini-3.1 requires google-genai>=2.1.0",
        "provider_schema_inlined_local_refs:4",
    ]


def test_structured_400_field_violation_has_precise_typed_diagnostic() -> None:
    class HttpOptions:
        api_version = "v1beta"
        base_url = "https://generativelanguage.googleapis.com/"

    class ApiClient:
        _http_options = HttpOptions()

    class Client:
        _api_client = ApiClient()

    transform = gemini_schema_transform(BulletRewriteOutput)
    request_shape = build_request_shape_diagnostic(
        client=Client(),
        model="gemini-3.1-flash-lite",
        config={
            "response_mime_type": "application/json",
            "response_json_schema": transform.schema,
        },
        schema_transform=transform,
        sdk_version="2.1.0",
    )

    class ClientError(RuntimeError):
        code = 400
        status = "INVALID_ARGUMENT"
        message = "Request contains an invalid argument"
        details = [
            {
                "fieldViolations": [
                    {
                        "field": "generationConfig.responseJsonSchema.pattern",
                        "description": "Unsupported JSON schema keyword pattern",
                    }
                ]
            }
        ]

    mapped = GeminiResumeLanguageModel._map_error(
        ClientError(ClientError.message),
        request_shape=request_shape,
    )

    assert mapped.retryable is False
    assert mapped.diagnostic is not None
    assert mapped.diagnostic.code is WriterPipelineFailureCode.UNSUPPORTED_SCHEMA_KEYWORD
    assert mapped.diagnostic.provider_error_code == "400"
    assert mapped.diagnostic.field_violations[0].field_path.endswith(".pattern")
    assert mapped.diagnostic.request_shape == request_shape


@pytest.mark.parametrize(
    ("sdk_version", "violations", "expected"),
    [
        (
            "2.1.0",
            [ProviderFieldViolation(field_path="model", description="Invalid value")],
            WriterPipelineFailureCode.INVALID_MODEL_OR_CONFIG,
        ),
        (
            "2.1.0",
            [
                ProviderFieldViolation(
                    field_path="generationConfig.responseJsonSchema",
                    description="Schema is too deeply nested",
                )
            ],
            WriterPipelineFailureCode.SCHEMA_TOO_LARGE_OR_DEEP,
        ),
        ("1.75.0", [], WriterPipelineFailureCode.INCOMPATIBLE_SDK_API_VERSION),
        ("2.1.0", [], WriterPipelineFailureCode.UNKNOWN_INVALID_ARGUMENT),
    ],
)
def test_invalid_argument_classification_is_specific(
    sdk_version: str,
    violations: list[ProviderFieldViolation],
    expected: WriterPipelineFailureCode,
) -> None:
    class Client:
        pass

    transform = gemini_schema_transform(BulletRewriteOutput)
    request_shape = build_request_shape_diagnostic(
        client=Client(),
        model="gemini-3.1-flash-lite",
        config={"response_json_schema": transform.schema},
        schema_transform=transform,
        sdk_version=sdk_version,
    )

    assert (
        GeminiResumeLanguageModel._invalid_argument_failure_code(
            request_shape,
            violations,
        )
        is expected
    )


def test_valid_json_with_schema_mismatch_is_typed_schema_error() -> None:
    class Response:
        parsed = None
        text = '{"rewrites":[{"source_evidence_ids":["safe"]}],"unexpected":"safe"}'
        candidates = [_StopCandidate()]
        usage_metadata = None

    adapter = _rewrite_adapter(Response())
    with pytest.raises(LanguageModelError) as raised:
        adapter.rewrite_bullets(_rewrite_request())

    assert raised.value.kind is LanguageModelErrorKind.MALFORMED_RESPONSE
    issue = raised.value.diagnostic
    assert issue is not None
    assert issue.code is WriterPipelineFailureCode.TYPED_SCHEMA_MISMATCH
    assert issue.stage is WriterPipelineStage.TYPED_SCHEMA_VALIDATION
    assert issue.top_level_json_keys == ["rewrites", "unexpected"]
    assert "rewrites.0.rewritten_text" in issue.schema_error_field_paths
    parsing = {
        timing.stage: timing for timing in adapter._telemetry.timings()
    }[GenerationStage.PROVIDER_RESPONSE_PARSING]
    assert parsing.status is StageStatus.FAILED


def test_safety_blocked_response_has_typed_reason() -> None:
    class Candidate:
        finish_reason = "SAFETY"
        finish_message = "Blocked"

    class Response:
        parsed = None
        text = None
        candidates = [Candidate()]
        usage_metadata = None

    adapter = _rewrite_adapter(Response())
    with pytest.raises(LanguageModelError) as raised:
        adapter.rewrite_bullets(_rewrite_request())

    assert raised.value.kind is LanguageModelErrorKind.SAFETY_BLOCKED
    issue = raised.value.diagnostic
    assert issue is not None
    assert issue.code is WriterPipelineFailureCode.SAFETY_BLOCKED_RESPONSE
    assert issue.candidate_count == 1
    assert issue.finish_reason == "SAFETY"


def test_empty_response_has_typed_reason() -> None:
    class Response:
        parsed = None
        text = None
        candidates: list[object] = []
        usage_metadata = None

    adapter = _rewrite_adapter(Response())
    with pytest.raises(LanguageModelError) as raised:
        adapter.rewrite_bullets(_rewrite_request())

    assert raised.value.kind is LanguageModelErrorKind.EMPTY_RESPONSE
    issue = raised.value.diagnostic
    assert issue is not None
    assert issue.code is WriterPipelineFailureCode.EMPTY_PROVIDER_RESPONSE
    assert issue.candidate_count == 0
    assert issue.text_present is False


def test_response_text_extraction_failure_has_typed_reason() -> None:
    class Response:
        parsed = None
        candidates = [_StopCandidate()]
        usage_metadata = None

        @property
        def text(self) -> str:
            raise TypeError("Controlled extraction failure.")

    adapter = _rewrite_adapter(Response())
    with pytest.raises(LanguageModelError) as raised:
        adapter.rewrite_bullets(_rewrite_request())

    assert raised.value.kind is LanguageModelErrorKind.RESPONSE_EXTRACTION
    issue = raised.value.diagnostic
    assert issue is not None
    assert issue.code is WriterPipelineFailureCode.RESPONSE_EXTRACTION_FAILED
    assert issue.exception_type == "TypeError"


def test_rewrite_provider_cache_identity_ignores_page_fit_thresholds() -> None:
    group = ApprovedEvidenceGroup(
        entry_id="entry",
        evidence_ids=["evidence"],
        source_texts=["Built a grounded service."],
        max_rendered_lines=2,
    )
    first = BulletRewriteRequest(
        primary_focus="Backend",
        groups=[group],
        max_bullets_per_entry=4,
        max_total_lines=42,
    )
    second = first.model_copy(
        update={
            "max_bullets_per_entry": 6,
            "max_total_lines": 50,
            "groups": [group.model_copy(update={"max_rendered_lines": 3})],
        }
    )

    first_payload = GeminiResumeLanguageModel._cache_payload(
        LlmOperation.REWRITE_BULLETS,
        first,
    )
    second_payload = GeminiResumeLanguageModel._cache_payload(
        LlmOperation.REWRITE_BULLETS,
        second,
    )

    assert first_payload == second_payload
