from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel

from resume_tailor.application.llm_validation import (
    RoleClassificationValidationResult,
    RoleClassificationStatus,
    validate_minimum_confidence,
    validate_role_classification,
)
from resume_tailor.domain.job_discovery.role_signals import (
    RoleSignalClassification,
    classify_role_signals,
)
from resume_tailor.domain.llm_models import (
    LanguageModelError,
    ModelCallMetadata,
    RoleClassificationOutput,
    RoleClassificationRequest,
    RoleClassificationResult,
)


class HybridRoleClassificationSource(StrEnum):
    GEMINI = "gemini"
    DETERMINISTIC = "deterministic"


class HybridRoleClassificationFallbackReason(StrEnum):
    DISABLED = "disabled"
    MODEL_UNAVAILABLE = "model_unavailable"
    PROVIDER_ERROR = "provider_error"
    INVALID_OUTPUT = "invalid_output"
    LOW_CONFIDENCE = "low_confidence"


class RoleClassificationModel(Protocol):
    def classify_role(self, request: RoleClassificationRequest) -> RoleClassificationResult: ...


class HybridRoleClassificationResult(BaseModel):
    selected_source: HybridRoleClassificationSource
    semantic_output: RoleClassificationOutput | None
    deterministic_classification: RoleSignalClassification
    validation: RoleClassificationValidationResult | None
    fallback_reason: HybridRoleClassificationFallbackReason | None
    provider_metadata: ModelCallMetadata | None


class HybridRoleClassifier:
    def __init__(
        self,
        role_model: RoleClassificationModel | None,
        *,
        enabled: bool = True,
    ) -> None:
        self._role_model = role_model
        self._enabled = enabled

    def classify(
        self,
        request: RoleClassificationRequest,
        *,
        minimum_confidence: float,
    ) -> HybridRoleClassificationResult:
        validate_minimum_confidence(minimum_confidence)
        deterministic = classify_role_signals(request.title, request.description)

        if not self._enabled:
            return self._fallback(
                deterministic,
                HybridRoleClassificationFallbackReason.DISABLED,
            )
        if self._role_model is None:
            return self._fallback(
                deterministic,
                HybridRoleClassificationFallbackReason.MODEL_UNAVAILABLE,
            )

        try:
            model_result = self._role_model.classify_role(request)
        except LanguageModelError:
            return self._fallback(
                deterministic,
                HybridRoleClassificationFallbackReason.PROVIDER_ERROR,
            )

        validation = validate_role_classification(
            request,
            model_result.output,
            minimum_confidence=minimum_confidence,
        )
        if validation.status is RoleClassificationStatus.VALID:
            return HybridRoleClassificationResult(
                selected_source=HybridRoleClassificationSource.GEMINI,
                semantic_output=model_result.output,
                deterministic_classification=deterministic,
                validation=validation,
                fallback_reason=None,
                provider_metadata=model_result.metadata,
            )
        fallback_reason = (
            HybridRoleClassificationFallbackReason.INVALID_OUTPUT
            if validation.status is RoleClassificationStatus.INVALID
            else HybridRoleClassificationFallbackReason.LOW_CONFIDENCE
        )
        return HybridRoleClassificationResult(
            selected_source=HybridRoleClassificationSource.DETERMINISTIC,
            semantic_output=None,
            deterministic_classification=deterministic,
            validation=validation,
            fallback_reason=fallback_reason,
            provider_metadata=model_result.metadata,
        )

    @staticmethod
    def _fallback(
        deterministic: RoleSignalClassification,
        reason: HybridRoleClassificationFallbackReason,
    ) -> HybridRoleClassificationResult:
        return HybridRoleClassificationResult(
            selected_source=HybridRoleClassificationSource.DETERMINISTIC,
            semantic_output=None,
            deterministic_classification=deterministic,
            validation=None,
            fallback_reason=reason,
            provider_metadata=None,
        )
