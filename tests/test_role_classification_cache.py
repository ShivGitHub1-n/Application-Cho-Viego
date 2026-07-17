from __future__ import annotations

from copy import deepcopy

import pytest

import resume_tailor.application.role_classification as role_classification_module
from resume_tailor.application.role_classification import (
    HybridRoleClassificationFallbackReason,
    HybridRoleClassificationResult,
    HybridRoleClassificationSource,
    RoleClassificationCacheIdentity,
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
from resume_tailor.infrastructure.llm_cache import InMemoryLlmCache
from resume_tailor.ports.interfaces import RoleClassificationCache


IDENTITY = RoleClassificationCacheIdentity(provider="fake-provider", model="fake-model")


class RecordingCache(InMemoryLlmCache):
    def __init__(self) -> None:
        super().__init__(ttl_seconds=900)
        self.get_calls = 0
        self.set_calls = 0
        self.stored_values: list[object] = []

    def get(self, key: str, result_type: type):  # type: ignore[no-untyped-def]
        self.get_calls += 1
        return super().get(key, result_type)

    def set(self, key: str, value: object) -> None:
        self.set_calls += 1
        self.stored_values.append(value)
        super().set(key, value)  # type: ignore[arg-type]


class SequencedRoleModel:
    def __init__(
        self,
        responses: list[RoleClassificationResult | Exception],
        model_name: str = "fake-model",
        provider_name: str = "fake-provider",
    ) -> None:
        self.responses = list(responses)
        self.model_name = model_name
        self.provider_name = provider_name
        self.call_count = 0

    def classify_role(self, request: RoleClassificationRequest) -> RoleClassificationResult:
        self.call_count += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _request(title: str = "Firmware Engineer", description: str | None = None) -> RoleClassificationRequest:
    return RoleClassificationRequest(
        title=title,
        description=description or "Design and implement firmware for STM32 motor-control boards.",
    )


def _output(**overrides: object) -> RoleClassificationOutput:
    values: dict[str, object] = {
        "is_engineering_role": True,
        "primary_family": RoleFamily.EMBEDDED_FIRMWARE,
        "confidence": 0.8,
    }
    values.update(overrides)
    return RoleClassificationOutput(**values)


def _result(output: RoleClassificationOutput) -> RoleClassificationResult:
    return RoleClassificationResult(
        metadata=ModelCallMetadata(
            provider="fake-provider",
            model="fake-model",
            operation=LlmOperation.CLASSIFY_ROLE,
            latency_ms=1,
        ),
        output=output,
    )


def _classifier(
    model: SequencedRoleModel | None,
    cache: RoleClassificationCache,
    identity: RoleClassificationCacheIdentity = IDENTITY,
) -> HybridRoleClassifier:
    return HybridRoleClassifier(model, cache=cache, cache_identity=identity)


def test_no_cache_preserves_stage3_behavior() -> None:
    model = SequencedRoleModel([_result(_output())])

    result = HybridRoleClassifier(model).classify(_request(), minimum_confidence=0.7)

    assert result.selected_source is HybridRoleClassificationSource.GEMINI
    assert model.call_count == 1


def test_in_memory_cache_conforms_to_role_classification_cache_protocol() -> None:
    cache = InMemoryLlmCache(ttl_seconds=900)

    assert isinstance(cache, RoleClassificationCache)


def test_cache_requires_identity_before_execution() -> None:
    cache = RecordingCache()
    model = SequencedRoleModel([_result(_output())])

    with pytest.raises(ValueError, match="cache_identity is required"):
        HybridRoleClassifier(model, cache=cache)

    assert cache.get_calls == 0
    assert model.call_count == 0


@pytest.mark.parametrize(
    ("provider", "model"),
    [
        ("", "model"),
        ("provider", ""),
    ],
)
def test_blank_cache_identity_is_rejected(provider: str, model: str) -> None:
    cache = RecordingCache()
    fake_model = SequencedRoleModel([_result(_output())])

    with pytest.raises(ValueError):
        HybridRoleClassifier(
            fake_model,
            cache=cache,
            cache_identity=RoleClassificationCacheIdentity(provider=provider, model=model),
        )


def test_first_request_misses_and_caches_typed_provider_result() -> None:
    cache = RecordingCache()
    model = SequencedRoleModel([_result(_output())])

    result = _classifier(model, cache).classify(_request(), minimum_confidence=0.7)

    assert result.selected_source is HybridRoleClassificationSource.GEMINI
    assert cache.get_calls == 1
    assert cache.set_calls == 1
    assert len(cache.stored_values) == 1
    assert isinstance(cache.stored_values[0], RoleClassificationResult)
    assert not isinstance(cache.stored_values[0], HybridRoleClassificationResult)
    assert model.call_count == 1


def test_second_identical_request_hits_without_another_gemini_call() -> None:
    cache = RecordingCache()
    model = SequencedRoleModel([_result(_output())])
    classifier = _classifier(model, cache)

    classifier.classify(_request(), minimum_confidence=0.7)
    second = classifier.classify(_request(), minimum_confidence=0.7)

    assert second.selected_source is HybridRoleClassificationSource.GEMINI
    assert cache.get_calls == 2
    assert cache.set_calls == 1
    assert model.call_count == 1


def test_cache_hit_revalidates_with_a_different_threshold() -> None:
    cache = RecordingCache()
    model = SequencedRoleModel([_result(_output(confidence=0.8))])
    classifier = _classifier(model, cache)

    first = classifier.classify(_request(), minimum_confidence=0.75)
    second = classifier.classify(_request(), minimum_confidence=0.9)

    assert first.selected_source is HybridRoleClassificationSource.GEMINI
    assert second.selected_source is HybridRoleClassificationSource.DETERMINISTIC
    assert second.fallback_reason is HybridRoleClassificationFallbackReason.LOW_CONFIDENCE
    assert second.validation is not None
    assert model.call_count == 1


@pytest.mark.parametrize(
    ("changed_request", "model_name"),
    [
        (_request(title="Embedded Firmware Engineer"), "fake-model"),
        (_request(description="Implement firmware for a different board."), "fake-model"),
        (_request(), "other-model"),
    ],
)
def test_changed_request_or_model_identity_misses_cache(
    changed_request: RoleClassificationRequest,
    model_name: str,
) -> None:
    cache = RecordingCache()
    model = SequencedRoleModel([_result(_output()), _result(_output())], model_name="fake-model")
    classifier = _classifier(model, cache)
    classifier.classify(_request(), minimum_confidence=0.7)
    if model_name != "fake-model":
        changed_model = SequencedRoleModel([_result(_output())], model_name=model_name)
        _classifier(changed_model, cache, RoleClassificationCacheIdentity("fake-provider", model_name)).classify(changed_request, minimum_confidence=0.7)
        assert changed_model.call_count == 1
    else:
        classifier.classify(changed_request, minimum_confidence=0.7)
        assert model.call_count == 2


def test_changed_contract_version_misses_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    cache = RecordingCache()
    model = SequencedRoleModel([_result(_output()), _result(_output())])
    classifier = _classifier(model, cache)
    classifier.classify(_request(), minimum_confidence=0.7)

    monkeypatch.setattr(
        role_classification_module,
        "ROLE_CLASSIFICATION_CACHE_CONTRACT_VERSION",
        "role_classification_v2",
    )
    classifier.classify(_request(), minimum_confidence=0.7)

    assert model.call_count == 2
    assert cache.set_calls == 2


def test_changed_provider_identity_misses_cache() -> None:
    cache = RecordingCache()
    first_model = SequencedRoleModel([_result(_output())], provider_name="provider-one")
    second_model = SequencedRoleModel([_result(_output())], provider_name="provider-two")

    _classifier(first_model, cache, RoleClassificationCacheIdentity("provider-one", "fake-model")).classify(_request(), minimum_confidence=0.7)
    result = _classifier(second_model, cache, RoleClassificationCacheIdentity("provider-two", "fake-model")).classify(
        _request(), minimum_confidence=0.7
    )

    assert result.selected_source is HybridRoleClassificationSource.GEMINI
    assert first_model.call_count == 1
    assert second_model.call_count == 1


def test_equivalent_models_share_cache_with_explicit_identity() -> None:
    cache = RecordingCache()
    first_model = SequencedRoleModel([_result(_output())], provider_name="misleading-one", model_name="misleading-one")
    second_model = SequencedRoleModel([_result(_output())], provider_name="misleading-two", model_name="misleading-two")
    identity = RoleClassificationCacheIdentity("stable-provider", "stable-model")

    _classifier(first_model, cache, identity).classify(_request(), minimum_confidence=0.7)
    result = _classifier(second_model, cache, identity).classify(_request(), minimum_confidence=0.7)

    assert result.selected_source is HybridRoleClassificationSource.GEMINI
    assert first_model.call_count == 1
    assert second_model.call_count == 0


def test_provider_exception_is_not_cached_and_next_call_retries_once() -> None:
    cache = RecordingCache()
    error = LanguageModelError(LanguageModelErrorKind.NETWORK, "transient failure", retryable=True)
    model = SequencedRoleModel([error, _result(_output())])
    classifier = _classifier(model, cache)

    first = classifier.classify(_request(), minimum_confidence=0.7)
    second = classifier.classify(_request(), minimum_confidence=0.7)

    assert first.fallback_reason is HybridRoleClassificationFallbackReason.PROVIDER_ERROR
    assert second.selected_source is HybridRoleClassificationSource.GEMINI
    assert cache.set_calls == 1
    assert model.call_count == 2


def test_disabled_and_missing_model_do_not_lookup_cache_or_call_gemini() -> None:
    cache = RecordingCache()
    model = SequencedRoleModel([_result(_output())])

    disabled = HybridRoleClassifier(model, enabled=False, cache=cache, cache_identity=IDENTITY).classify(
        _request(), minimum_confidence=0.7
    )
    unavailable = HybridRoleClassifier(None, cache=cache, cache_identity=IDENTITY).classify(
        _request(), minimum_confidence=0.7
    )

    assert disabled.fallback_reason is HybridRoleClassificationFallbackReason.DISABLED
    assert unavailable.fallback_reason is HybridRoleClassificationFallbackReason.MODEL_UNAVAILABLE
    assert cache.get_calls == 0
    assert model.call_count == 0


@pytest.mark.parametrize("threshold", [-0.1, 1.1, float("nan"), float("inf"), float("-inf")])
def test_invalid_threshold_does_not_lookup_cache_or_call_gemini(threshold: float) -> None:
    cache = RecordingCache()
    model = SequencedRoleModel([_result(_output())])

    with pytest.raises(ValueError):
        _classifier(model, cache).classify(_request(), minimum_confidence=threshold)

    assert cache.get_calls == 0
    assert cache.set_calls == 0
    assert model.call_count == 0


def test_cached_structurally_invalid_output_is_revalidated() -> None:
    cache = RecordingCache()
    model = SequencedRoleModel([_result(_output(primary_family=None))])
    classifier = _classifier(model, cache)

    first = classifier.classify(_request(), minimum_confidence=0.7)
    second = classifier.classify(_request(), minimum_confidence=0.7)

    assert first.fallback_reason is HybridRoleClassificationFallbackReason.INVALID_OUTPUT
    assert second.fallback_reason is HybridRoleClassificationFallbackReason.INVALID_OUTPUT
    assert second.validation is not None
    assert second.validation.reason_codes[0].value == "missing_primary_family"
    assert model.call_count == 1


def test_cached_low_confidence_output_is_revalidated() -> None:
    cache = RecordingCache()
    model = SequencedRoleModel([_result(_output(confidence=0.6))])
    classifier = _classifier(model, cache)

    first = classifier.classify(_request(), minimum_confidence=0.7)
    second = classifier.classify(_request(), minimum_confidence=0.5)

    assert first.fallback_reason is HybridRoleClassificationFallbackReason.LOW_CONFIDENCE
    assert second.selected_source is HybridRoleClassificationSource.GEMINI
    assert second.fallback_reason is None
    assert model.call_count == 1


def test_cached_evidence_is_revalidated_against_current_request() -> None:
    cache = RecordingCache()
    output = _output(
        evidence_quotes=[RoleEvidenceQuote(quote="Firmware Engineer", category="responsibility")]
    )
    model = SequencedRoleModel([_result(output)])
    classifier = _classifier(model, cache)

    first = classifier.classify(_request(), minimum_confidence=0.7)
    second_request = _request(title=" Firmware Engineer ")
    second = classifier.classify(second_request, minimum_confidence=0.7)

    assert first.selected_source is HybridRoleClassificationSource.GEMINI
    assert second.selected_source is HybridRoleClassificationSource.GEMINI
    assert second.validation is not None
    assert model.call_count == 1


def test_cached_values_are_isolated_between_calls() -> None:
    cache = RecordingCache()
    model = SequencedRoleModel([_result(_output())])
    classifier = _classifier(model, cache)

    first = classifier.classify(_request(), minimum_confidence=0.7)
    assert first.semantic_output is not None
    first.semantic_output.tools_and_skills.append("mutated")
    second = classifier.classify(_request(), minimum_confidence=0.7)

    assert second.semantic_output is not None
    assert "mutated" not in second.semantic_output.tools_and_skills
    assert model.call_count == 1


def test_deterministic_result_stays_equal_to_direct_classifier_on_cache_hit() -> None:
    cache = RecordingCache()
    model = SequencedRoleModel([_result(_output())])
    request = _request()
    classifier = _classifier(model, cache)

    classifier.classify(request, minimum_confidence=0.7)
    result = classifier.classify(request, minimum_confidence=0.7)

    assert result.deterministic_classification == classify_role_signals(
        request.title, request.description
    )
