from __future__ import annotations

from copy import deepcopy

import pytest

from resume_tailor.application.role_classification import (
    HybridRoleClassificationFallbackReason,
    HybridRoleClassificationSource,
    HybridRoleClassifier,
)
from resume_tailor.domain.job_discovery.role_signals import classify_role_signals
from resume_tailor.domain.llm_models import (
    LanguageModelError,
    LanguageModelErrorKind,
    LlmOperation,
    ModelCallMetadata,
    RoleClassificationOutput,
    RoleClassificationRequest,
    RoleClassificationResult,
    RoleEvidenceQuote,
)
from resume_tailor.domain.models import RoleFamily


class FakeRoleClassificationModel:
    def __init__(self, response: RoleClassificationResult | Exception) -> None:
        self.response = response
        self.call_count = 0

    def classify_role(self, request: RoleClassificationRequest) -> RoleClassificationResult:
        self.call_count += 1
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _request() -> RoleClassificationRequest:
    return RoleClassificationRequest(
        title="Firmware Engineer",
        description="Design and implement firmware for STM32 motor-control boards.",
    )


def _output(**overrides: object) -> RoleClassificationOutput:
    values: dict[str, object] = {
        "is_engineering_role": True,
        "primary_family": RoleFamily.EMBEDDED_FIRMWARE,
        "confidence": 0.8,
    }
    values.update(overrides)
    return RoleClassificationOutput(**values)


def _model_result(output: RoleClassificationOutput) -> RoleClassificationResult:
    return RoleClassificationResult(
        metadata=ModelCallMetadata(
            provider="fake",
            model="fake-model",
            operation=LlmOperation.CLASSIFY_ROLE,
            latency_ms=1,
        ),
        output=output,
    )


def test_disabled_service_falls_back_without_calling_gemini() -> None:
    model = FakeRoleClassificationModel(_model_result(_output()))

    result = HybridRoleClassifier(model, enabled=False).classify(_request(), minimum_confidence=0.7)

    assert result.selected_source is HybridRoleClassificationSource.DETERMINISTIC
    assert result.fallback_reason is HybridRoleClassificationFallbackReason.DISABLED
    assert result.validation is None
    assert model.call_count == 0


def test_missing_model_falls_back_without_provider_metadata() -> None:
    result = HybridRoleClassifier(None).classify(_request(), minimum_confidence=0.7)

    assert result.selected_source is HybridRoleClassificationSource.DETERMINISTIC
    assert result.fallback_reason is HybridRoleClassificationFallbackReason.MODEL_UNAVAILABLE
    assert result.provider_metadata is None


def test_valid_gemini_result_preserves_both_classifications_and_metadata() -> None:
    output = _output(
        evidence_quotes=[RoleEvidenceQuote(quote="Firmware Engineer", category="responsibility")]
    )
    model = FakeRoleClassificationModel(_model_result(output))
    request = _request()

    result = HybridRoleClassifier(model).classify(request, minimum_confidence=0.8)

    assert result.selected_source is HybridRoleClassificationSource.GEMINI
    assert result.semantic_output == output
    assert result.deterministic_classification == classify_role_signals(request.title, request.description)
    assert result.validation is not None
    assert result.validation.status.value == "valid"
    assert result.fallback_reason is None
    assert result.provider_metadata == _model_result(output).metadata
    assert model.call_count == 1


def test_low_confidence_falls_back_and_preserves_validation() -> None:
    model = FakeRoleClassificationModel(_model_result(_output(confidence=0.7)))

    result = HybridRoleClassifier(model).classify(_request(), minimum_confidence=0.8)

    assert result.selected_source is HybridRoleClassificationSource.DETERMINISTIC
    assert result.semantic_output is None
    assert result.fallback_reason is HybridRoleClassificationFallbackReason.LOW_CONFIDENCE
    assert result.validation is not None
    assert result.validation.reason_codes[0].value == "low_confidence"
    assert model.call_count == 1


def test_structurally_invalid_gemini_result_falls_back_and_preserves_reasons() -> None:
    model = FakeRoleClassificationModel(_model_result(_output(primary_family=None)))

    result = HybridRoleClassifier(model).classify(_request(), minimum_confidence=0.7)

    assert result.selected_source is HybridRoleClassificationSource.DETERMINISTIC
    assert result.fallback_reason is HybridRoleClassificationFallbackReason.INVALID_OUTPUT
    assert result.validation is not None
    assert [code.value for code in result.validation.reason_codes] == ["missing_primary_family"]
    assert model.call_count == 1


def test_ungrounded_evidence_falls_back_with_grounding_reason() -> None:
    model = FakeRoleClassificationModel(
        _model_result(
            _output(
                evidence_quotes=[
                    RoleEvidenceQuote(quote="not supplied", category="responsibility")
                ]
            )
        )
    )

    result = HybridRoleClassifier(model).classify(_request(), minimum_confidence=0.7)

    assert result.fallback_reason is HybridRoleClassificationFallbackReason.INVALID_OUTPUT
    assert result.validation is not None
    assert [code.value for code in result.validation.reason_codes] == ["ungrounded_evidence_quote"]
    assert model.call_count == 1


def test_provider_error_falls_back_without_exposing_exception_text() -> None:
    secret_text = "provider failed with secret-token-value"
    model = FakeRoleClassificationModel(
        LanguageModelError(LanguageModelErrorKind.NETWORK, secret_text, retryable=True)
    )

    result = HybridRoleClassifier(model).classify(_request(), minimum_confidence=0.7)

    assert result.selected_source is HybridRoleClassificationSource.DETERMINISTIC
    assert result.fallback_reason is HybridRoleClassificationFallbackReason.PROVIDER_ERROR
    assert result.validation is None
    assert result.provider_metadata is None
    assert secret_text not in result.model_dump_json()
    assert model.call_count == 1


def test_confidence_equal_to_threshold_selects_gemini() -> None:
    model = FakeRoleClassificationModel(_model_result(_output(confidence=0.7)))

    result = HybridRoleClassifier(model).classify(_request(), minimum_confidence=0.7)

    assert result.selected_source is HybridRoleClassificationSource.GEMINI
    assert result.fallback_reason is None
    assert model.call_count == 1


@pytest.mark.parametrize("threshold", [-0.1, 1.1])
def test_invalid_minimum_confidence_propagates_without_calling_model(threshold: float) -> None:
    model = FakeRoleClassificationModel(_model_result(_output()))

    with pytest.raises(ValueError, match="between 0 and 1"):
        HybridRoleClassifier(model).classify(_request(), minimum_confidence=threshold)

    assert model.call_count == 0


@pytest.mark.parametrize("threshold", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_minimum_confidence_propagates_without_calling_model(threshold: float) -> None:
    request = _request()
    model = FakeRoleClassificationModel(_model_result(_output()))
    request_before = deepcopy(request.model_dump())

    with pytest.raises(ValueError, match="between 0 and 1"):
        HybridRoleClassifier(model).classify(request, minimum_confidence=threshold)

    assert model.call_count == 0
    assert request.model_dump() == request_before


def test_deterministic_output_matches_direct_classifier() -> None:
    request = _request()
    expected = classify_role_signals(request.title, request.description)

    result = HybridRoleClassifier(None).classify(request, minimum_confidence=0.7)

    assert result.deterministic_classification == expected


def test_call_limit_is_zero_or_one_for_all_paths() -> None:
    response = _model_result(_output())
    enabled_model = FakeRoleClassificationModel(response)
    disabled_model = FakeRoleClassificationModel(response)

    HybridRoleClassifier(enabled_model).classify(_request(), minimum_confidence=0.7)
    HybridRoleClassifier(disabled_model, enabled=False).classify(_request(), minimum_confidence=0.7)

    assert enabled_model.call_count == 1
    assert disabled_model.call_count == 0


def test_service_does_not_mutate_request_model_result_or_returned_classifications() -> None:
    request = _request()
    output = _output(
        evidence_quotes=[RoleEvidenceQuote(quote="Firmware Engineer", category="responsibility")]
    )
    model_result = _model_result(output)
    model = FakeRoleClassificationModel(model_result)
    request_before = deepcopy(request.model_dump())
    model_result_before = deepcopy(model_result.model_dump())
    deterministic_before = classify_role_signals(request.title, request.description)
    deterministic_before_dump = deterministic_before.model_dump()

    result = HybridRoleClassifier(model).classify(request, minimum_confidence=0.7)

    assert request.model_dump() == request_before
    assert model_result.model_dump() == model_result_before
    assert result.deterministic_classification.model_dump() == deterministic_before_dump
    assert result.validation is not None
    assert result.validation.output == output
