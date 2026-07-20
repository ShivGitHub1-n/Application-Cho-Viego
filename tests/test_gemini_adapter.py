import pytest

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
from resume_tailor.infrastructure.gemini_adapter import GeminiResumeLanguageModel
from resume_tailor.infrastructure.gemini_schema import gemini_response_schema
from resume_tailor.infrastructure.llm_cache import InMemoryLlmCache


def test_gemini_error_mapping_is_provider_specific() -> None:
    error = GeminiResumeLanguageModel._map_error(RuntimeError("429 resource exhausted"))

    assert error.kind == LanguageModelErrorKind.RATE_LIMITED
    assert error.retryable is True


def test_provider_schemas_exclude_unsupported_additional_properties() -> None:
    for model_type in (
        OpportunityAnalysisOutput,
        CompositionRecommendationOutput,
        BulletRewriteOutput,
        BulletShorteningOutput,
        SkillCompositionOutput,
    ):
        schema = gemini_response_schema(model_type)

        assert "additionalProperties" not in str(schema)
        assert "$ref" not in str(schema)


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
    assert "additionalProperties" not in str(config["response_schema"])


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
    schema = config["response_schema"]
    assert (
        "description"
        not in schema["properties"]["profile"]["properties"]["experiences"]["items"]["properties"]
    )
    assert (
        "bullets"
        not in schema["properties"]["profile"]["properties"]["experiences"]["items"]["properties"]
    )
    assert (
        "bullet_points"
        not in schema["properties"]["profile"]["properties"]["experiences"]["items"]["properties"]
    )


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
