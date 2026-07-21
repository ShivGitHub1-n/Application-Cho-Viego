import pytest
from pydantic import ValidationError

from resume_tailor.application.llm_prompts import task_prompt
from resume_tailor.domain.llm_models import (
    LlmOperation,
    RoleClassificationOutput,
    RoleClassificationRequest,
    RoleClassificationResult,
    RoleEvidenceQuote,
)
from resume_tailor.domain.models import RoleFamily
from resume_tailor.infrastructure.gemini_adapter import GeminiResumeLanguageModel
from resume_tailor.infrastructure.gemini_schema import gemini_response_schema
from resume_tailor.infrastructure.llm_cache import InMemoryLlmCache


def _request() -> RoleClassificationRequest:
    return RoleClassificationRequest(
        title="Embedded Systems Engineer",
        description="Own firmware development for sensor interfaces using STM32 and C++.",
    )


def test_role_classification_models_are_typed_and_bounded() -> None:
    output = RoleClassificationOutput(
        is_engineering_role=True,
        primary_family=RoleFamily.EMBEDDED_FIRMWARE,
        secondary_families=[RoleFamily.SOFTWARE_DATA_ENGINEERING],
        owned_responsibilities=["firmware development"],
        contextual_mentions=["sensor interfaces"],
        managed_subjects=["firmware"],
        tools_and_skills=["STM32", "C++"],
        evidence_quotes=[
            RoleEvidenceQuote(quote="Own firmware development", category="responsibility")
        ],
        confidence=0.9,
    )

    assert output.primary_family is RoleFamily.EMBEDDED_FIRMWARE
    assert output.evidence_quotes[0].category == "responsibility"

    with pytest.raises(ValidationError):
        RoleClassificationRequest(title="", description="Posting")
    with pytest.raises(ValidationError):
        RoleEvidenceQuote(quote="x" * 501, category="tool_or_skill")
    with pytest.raises(ValidationError):
        RoleClassificationOutput(is_engineering_role=False, confidence=1.1)


def test_role_classification_prompt_restricts_families_and_quotes() -> None:
    prompt = task_prompt(LlmOperation.CLASSIFY_ROLE, _request())

    assert "existing RoleFamily enum values" in prompt
    assert "Do not invent" in prompt
    assert "Copy every evidence quote exactly" in prompt
    assert "exactly from the supplied title or description" in prompt
    assert '"title":"Embedded Systems Engineer"' in prompt


def test_role_classification_schema_is_provider_safe() -> None:
    schema = gemini_response_schema(RoleClassificationOutput)

    rendered = str(schema)
    assert "$ref" not in rendered
    assert schema["additionalProperties"] is False
    assert schema["properties"]["primary_family"]["anyOf"]
    assert "responsibility" in str(schema["properties"]["evidence_quotes"])
    for family in RoleFamily:
        assert family.value in str(schema)


def test_gemini_adapter_classifies_role_through_mocked_boundary() -> None:
    captured: dict[str, object] = {}

    class Response:
        parsed = RoleClassificationOutput(
            is_engineering_role=True,
            primary_family=RoleFamily.EMBEDDED_FIRMWARE,
            confidence=0.9,
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
    adapter._max_output_tokens = 2048
    adapter._profile_extraction_max_output_tokens = 8192
    adapter._cache = InMemoryLlmCache(60)

    result = adapter.classify_role(_request())

    assert isinstance(result, RoleClassificationResult)
    assert result.metadata.operation is LlmOperation.CLASSIFY_ROLE
    assert isinstance(result.output, RoleClassificationOutput)
    assert result.output.primary_family is RoleFamily.EMBEDDED_FIRMWARE
    config = captured["config"]
    assert isinstance(config, dict)
    assert config["response_mime_type"] == "application/json"
    assert config["response_json_schema"]["additionalProperties"] is False
