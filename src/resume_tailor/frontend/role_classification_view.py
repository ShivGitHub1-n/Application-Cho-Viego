from typing import Literal

from pydantic import BaseModel, Field

from resume_tailor.domain.models import (
    RoleClassification,
    RoleClassificationCacheBehavior,
    RoleClassificationFallbackReason,
    RoleClassificationSource,
    RoleClassificationValidationStatus,
)


class RoleClassificationDiagnosticView(BaseModel):
    semantic_enabled: bool
    resolved_role_family: str
    selected_source: Literal["Gemini", "Deterministic"]
    fallback_reason: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    cached_reuse: bool | None = None


_FALLBACK_MESSAGES = {
    RoleClassificationFallbackReason.DISABLED: (
        "Gemini role classification is disabled."
    ),
    RoleClassificationFallbackReason.MODEL_UNAVAILABLE: (
        "Gemini is not configured or the selected model is unavailable."
    ),
    RoleClassificationFallbackReason.PROVIDER_ERROR: (
        "Gemini role classification was unavailable for this request."
    ),
    RoleClassificationFallbackReason.INVALID_OUTPUT: (
        "Gemini returned a role classification that did not pass validation."
    ),
    RoleClassificationFallbackReason.LOW_CONFIDENCE: (
        "Gemini confidence was below the configured minimum."
    ),
    RoleClassificationFallbackReason.CACHE_READ_ERROR: (
        "The role-classification cache was unavailable, so Gemini was not called."
    ),
    RoleClassificationFallbackReason.SEMANTIC_FAMILY_UNSUPPORTED: (
        "Gemini's family was not supported by deterministic posting signals."
    ),
}


def build_role_classification_diagnostic_view(
    role: RoleClassification,
) -> RoleClassificationDiagnosticView:
    diagnostic = role.diagnostic
    if diagnostic is None:
        return RoleClassificationDiagnosticView(
            semantic_enabled=False,
            resolved_role_family=_family_label(role.role_family),
            selected_source="Deterministic",
        )

    confidence = (
        diagnostic.confidence
        if diagnostic.validation_status
        in {
            RoleClassificationValidationStatus.VALID,
            RoleClassificationValidationStatus.LOW_CONFIDENCE,
        }
        else None
    )
    cached_reuse: bool | None = None
    if diagnostic.cache_behavior is RoleClassificationCacheBehavior.HIT:
        cached_reuse = True
    elif diagnostic.cache_behavior is not RoleClassificationCacheBehavior.NOT_USED:
        cached_reuse = False

    resolved_family = (
        diagnostic.resolved_primary_family.value
        if diagnostic.resolved_primary_family is not None
        else role.role_family
    )
    return RoleClassificationDiagnosticView(
        semantic_enabled=diagnostic.semantic_enabled,
        resolved_role_family=_family_label(resolved_family),
        selected_source=(
            "Gemini"
            if diagnostic.selected_source is RoleClassificationSource.GEMINI
            else "Deterministic"
        ),
        fallback_reason=(
            _FALLBACK_MESSAGES.get(diagnostic.fallback_reason)
            if diagnostic.fallback_reason is not None
            else None
        ),
        confidence=confidence,
        cached_reuse=cached_reuse,
    )


def _family_label(value: str) -> str:
    return value.replace("_", " ").title()
