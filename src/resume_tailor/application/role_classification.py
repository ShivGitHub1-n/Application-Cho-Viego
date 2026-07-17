from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel

from resume_tailor.application.llm_validation import (
    RoleClassificationStatus,
    RoleClassificationValidationResult,
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
from resume_tailor.domain.models import (
    JobPosting,
    RoleClassification,
    RoleClassificationDiagnostic,
    RoleClassificationValidationStatus,
)
from resume_tailor.domain.models import (
    RoleClassificationCacheBehavior as HybridRoleClassificationCacheBehavior,
)
from resume_tailor.domain.models import (
    RoleClassificationFallbackReason as HybridRoleClassificationFallbackReason,
)
from resume_tailor.domain.models import (
    RoleClassificationSource as HybridRoleClassificationSource,
)
from resume_tailor.ports.interfaces import (
    RoleClassificationCache,
    RoleClassificationCacheError,
)

ROLE_CLASSIFICATION_CACHE_CONTRACT_VERSION = "role_classification_v1"


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
    semantic_enabled: bool
    selected_source: HybridRoleClassificationSource
    semantic_output: RoleClassificationOutput | None
    deterministic_classification: RoleSignalClassification
    validation: RoleClassificationValidationResult | None
    fallback_reason: HybridRoleClassificationFallbackReason | None
    provider_metadata: ModelCallMetadata | None
    cache_behavior: HybridRoleClassificationCacheBehavior


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
        safe_cache_failures: bool = False,
    ) -> None:
        if cache is not None and cache_identity is None:
            raise ValueError(
                "cache_identity is required when a role classification cache is supplied"
            )
        self._role_model = role_model
        self._enabled = enabled
        self._cache = cache
        self._cache_identity = cache_identity
        self._safe_cache_failures = safe_cache_failures

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
                semantic_enabled=False,
            )
        if self._role_model is None:
            return self._fallback(
                deterministic,
                HybridRoleClassificationFallbackReason.MODEL_UNAVAILABLE,
                semantic_enabled=True,
            )

        cache_key: str | None = None
        cache_behavior = HybridRoleClassificationCacheBehavior.NOT_USED
        if self._cache is not None:
            try:
                cache_key = self._cache_key(request)
                cached_result = self._cache.get(cache_key, RoleClassificationResult)
            except RoleClassificationCacheError:
                if not self._safe_cache_failures:
                    raise
                return self._fallback(
                    deterministic,
                    HybridRoleClassificationFallbackReason.CACHE_READ_ERROR,
                    semantic_enabled=True,
                    cache_behavior=HybridRoleClassificationCacheBehavior.READ_ERROR,
                )
            if cached_result is not None:
                return self._select_result(
                    deterministic,
                    request,
                    cached_result,
                    minimum_confidence,
                    cache_behavior=HybridRoleClassificationCacheBehavior.HIT,
                )
            cache_behavior = HybridRoleClassificationCacheBehavior.MISS

        try:
            model_result = self._role_model.classify_role(request)
        except LanguageModelError:
            return self._fallback(
                deterministic,
                HybridRoleClassificationFallbackReason.PROVIDER_ERROR,
                semantic_enabled=True,
                cache_behavior=cache_behavior,
            )

        if cache_key is not None:
            try:
                if self._cache is None:
                    raise RuntimeError("Role classification cache is unavailable")
                self._cache.set(cache_key, model_result.model_copy(deep=True))
            except RoleClassificationCacheError:
                if not self._safe_cache_failures:
                    raise
                cache_behavior = HybridRoleClassificationCacheBehavior.WRITE_ERROR
            else:
                cache_behavior = HybridRoleClassificationCacheBehavior.STORED

        return self._select_result(
            deterministic,
            request,
            model_result,
            minimum_confidence,
            cache_behavior=cache_behavior,
        )

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
        *,
        cache_behavior: HybridRoleClassificationCacheBehavior,
    ) -> HybridRoleClassificationResult:
        validation = validate_role_classification(
            request,
            model_result.output,
            minimum_confidence=minimum_confidence,
        )
        if validation.status is RoleClassificationStatus.VALID:
            return HybridRoleClassificationResult(
                semantic_enabled=True,
                selected_source=HybridRoleClassificationSource.GEMINI,
                semantic_output=model_result.output,
                deterministic_classification=deterministic,
                validation=validation,
                fallback_reason=None,
                provider_metadata=model_result.metadata,
                cache_behavior=cache_behavior,
            )
        fallback_reason = (
            HybridRoleClassificationFallbackReason.INVALID_OUTPUT
            if validation.status is RoleClassificationStatus.INVALID
            else HybridRoleClassificationFallbackReason.LOW_CONFIDENCE
        )
        return HybridRoleClassificationResult(
            semantic_enabled=True,
            selected_source=HybridRoleClassificationSource.DETERMINISTIC,
            semantic_output=None,
            deterministic_classification=deterministic,
            validation=validation,
            fallback_reason=fallback_reason,
            provider_metadata=model_result.metadata,
            cache_behavior=cache_behavior,
        )

    @staticmethod
    def _fallback(
        deterministic: RoleSignalClassification,
        reason: HybridRoleClassificationFallbackReason,
        *,
        semantic_enabled: bool,
        cache_behavior: HybridRoleClassificationCacheBehavior = (
            HybridRoleClassificationCacheBehavior.NOT_USED
        ),
    ) -> HybridRoleClassificationResult:
        return HybridRoleClassificationResult(
            semantic_enabled=semantic_enabled,
            selected_source=HybridRoleClassificationSource.DETERMINISTIC,
            semantic_output=None,
            deterministic_classification=deterministic,
            validation=None,
            fallback_reason=reason,
            provider_metadata=None,
            cache_behavior=cache_behavior,
        )


class HybridRoleOpportunityAnalyzer:
    """Resolve a validated semantic primary family over deterministic role signals."""

    def __init__(
        self,
        classifier: HybridRoleClassifier,
        *,
        minimum_confidence: float,
    ) -> None:
        validate_minimum_confidence(minimum_confidence)
        self._classifier = classifier
        self._minimum_confidence = minimum_confidence

    def analyze(self, posting: JobPosting) -> RoleClassification:
        hybrid = self._classifier.classify(
            RoleClassificationRequest(
                title=posting.title,
                description=posting.description,
            ),
            minimum_confidence=self._minimum_confidence,
        )
        deterministic = hybrid.deterministic_classification
        validation_output = hybrid.validation.output if hybrid.validation is not None else None
        semantic_primary = (
            validation_output.primary_family if validation_output is not None else None
        )
        resolved_primary = deterministic.primary_family
        selected_source = hybrid.selected_source
        fallback_reason = hybrid.fallback_reason

        if selected_source is HybridRoleClassificationSource.GEMINI:
            if (
                semantic_primary is None
                or not deterministic.supported
                or semantic_primary not in deterministic.family_scores
            ):
                selected_source = HybridRoleClassificationSource.DETERMINISTIC
                fallback_reason = (
                    HybridRoleClassificationFallbackReason.SEMANTIC_FAMILY_UNSUPPORTED
                )
            else:
                resolved_primary = semantic_primary

        diagnostic = RoleClassificationDiagnostic(
            semantic_enabled=hybrid.semantic_enabled,
            selected_source=selected_source,
            resolved_primary_family=resolved_primary,
            deterministic_primary_family=deterministic.primary_family,
            semantic_primary_family=semantic_primary,
            validation_status=(
                RoleClassificationValidationStatus(hybrid.validation.status.value)
                if hybrid.validation is not None
                else None
            ),
            fallback_reason=fallback_reason,
            confidence=(
                validation_output.confidence if validation_output is not None else None
            ),
            cache_behavior=hybrid.cache_behavior,
        )

        if (
            not deterministic.supported
            or resolved_primary is None
        ):
            return RoleClassification(
                role_family="unsupported",
                confidence=deterministic.confidence,
                supported=False,
                reason=deterministic.reason,
                diagnostic=diagnostic,
            )

        deterministic_family_order = [
            family
            for family in [
                deterministic.primary_family,
                *deterministic.secondary_role_families,
            ]
            if family is not None and family != resolved_primary
        ]
        return RoleClassification(
            role_family=resolved_primary.value,
            confidence=deterministic.confidence,
            supported=True,
            signals=deterministic.signals,
            secondary_role_families=list(dict.fromkeys(deterministic_family_order)),
            diagnostic=diagnostic,
        )


def _normalize_cache_text(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()
