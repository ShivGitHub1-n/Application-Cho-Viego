from __future__ import annotations

from dataclasses import dataclass
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
from resume_tailor.ports.interfaces import RoleClassificationCache


ROLE_CLASSIFICATION_CACHE_CONTRACT_VERSION = "role_classification_v1"


class HybridRoleClassificationSource(StrEnum):
    GEMINI = "gemini"
    DETERMINISTIC = "deterministic"


class HybridRoleClassificationFallbackReason(StrEnum):
    DISABLED = "disabled"
    MODEL_UNAVAILABLE = "model_unavailable"
    PROVIDER_ERROR = "provider_error"
    INVALID_OUTPUT = "invalid_output"
    LOW_CONFIDENCE = "low_confidence"


@dataclass(frozen=True)
class RoleClassificationCacheIdentity:
    provider: str
    model: str

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("Role classification cache provider identity must be non-empty")
        if not self.model.strip():
            raise ValueError("Role classification cache model identity must be non-empty")


class RoleClassificationModel(Protocol):
    def classify_role(self, request: RoleClassificationRequest) -> RoleClassificationResult: ...


class HybridRoleClassificationResult(BaseModel):
    selected_source: HybridRoleClassificationSource
    semantic_output: RoleClassificationOutput | None
    deterministic_classification: RoleSignalClassification
    validation: RoleClassificationValidationResult | None
    fallback_reason: HybridRoleClassificationFallbackReason | None
    provider_metadata: ModelCallMetadata | None


class _RoleClassificationCachePayload(BaseModel):
    contract_version: str
    provider_identity: str
    model_identity: str
    title: str
    description: str


class HybridRoleClassifier:
    def __init__(
        self,
        role_model: RoleClassificationModel | None,
        *,
        enabled: bool = True,
        cache: RoleClassificationCache | None = None,
        cache_identity: RoleClassificationCacheIdentity | None = None,
    ) -> None:
        if cache is not None and cache_identity is None:
            raise ValueError("cache_identity is required when a role classification cache is supplied")
        self._role_model = role_model
        self._enabled = enabled
        self._cache = cache
        self._cache_identity = cache_identity

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

        cache_key = self._cache_key(request) if self._cache is not None else None
        if cache_key is not None:
            # Stage 4 is pre-production: cache failures propagate. Stage 5 wiring
            # must decide whether cache failures degrade to provider execution.
            cached_result = self._cache.get(cache_key, RoleClassificationResult)
            if cached_result is not None:
                return self._select_result(deterministic, request, cached_result, minimum_confidence)

        try:
            model_result = self._role_model.classify_role(request)
        except LanguageModelError:
            return self._fallback(
                deterministic,
                HybridRoleClassificationFallbackReason.PROVIDER_ERROR,
            )

        if cache_key is not None:
            # Stage 4 is pre-production: cache failures propagate. Stage 5 wiring
            # must decide whether cache failures remain fatal or degrade safely.
            self._cache.set(cache_key, model_result.model_copy(deep=True))

        return self._select_result(deterministic, request, model_result, minimum_confidence)

    def _cache_key(self, request: RoleClassificationRequest) -> str:
        if self._cache is None or self._cache_identity is None:
            raise RuntimeError("Role classification cache identity is unavailable")
        payload = _RoleClassificationCachePayload(
            contract_version=ROLE_CLASSIFICATION_CACHE_CONTRACT_VERSION,
            provider_identity=self._cache_identity.provider,
            model_identity=self._cache_identity.model,
            title=_normalize_cache_text(request.title),
            description=_normalize_cache_text(request.description),
        )
        return self._cache.key_for(
            "classify_role",
            f"{self._cache_identity.provider}:{self._cache_identity.model}",
            payload,
        )

    @staticmethod
    def _select_result(
        deterministic: RoleSignalClassification,
        request: RoleClassificationRequest,
        model_result: RoleClassificationResult,
        minimum_confidence: float,
    ) -> HybridRoleClassificationResult:
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


def _normalize_cache_text(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()
