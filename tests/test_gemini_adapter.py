from resume_tailor.domain.llm_models import (
    BulletRewriteOutput,
    BulletShorteningOutput,
    CompositionRecommendationOutput,
    LanguageModelErrorKind,
    OpportunityAnalysisOutput,
    OpportunityAnalysisRequest,
)
from resume_tailor.domain.models import RoleFamily
from resume_tailor.infrastructure.gemini_adapter import GeminiResumeLanguageModel
from resume_tailor.infrastructure.llm_cache import InMemoryLlmCache
from resume_tailor.infrastructure.gemini_schema import gemini_response_schema


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
