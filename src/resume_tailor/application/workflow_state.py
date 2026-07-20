from __future__ import annotations

from collections.abc import MutableMapping

DERIVED_WORKFLOW_KEYS = (
    "plan",
    "resume",
    "generated_resume_artifact",
    "generated_content_reviewed",
    "workflow_profile_fingerprint",
    "workflow_posting_fingerprint",
    "cover_letter",
    "cover_letter_reviewed",
    "cover_letter_profile_fingerprint",
    "cover_letter_posting_fingerprint",
    "cover_letter_plan_fingerprint",
    "cover_letter_evidence_fingerprint",
    "cover_letter_recipient_fingerprint",
)

ACTIVE_POSTING_KEY = "posting"
POSTING_FINGERPRINT_KEY = "workflow_posting_fingerprint"
PROFILE_FINGERPRINT_KEY = "workflow_profile_fingerprint"

POSTING_DERIVED_WORKFLOW_KEYS = (
    "plan",
    "resume",
    "generated_resume_artifact",
    "generated_content_reviewed",
    POSTING_FINGERPRINT_KEY,
    "cover_letter",
    "cover_letter_reviewed",
    "cover_letter_profile_fingerprint",
    "cover_letter_posting_fingerprint",
    "cover_letter_plan_fingerprint",
    "cover_letter_evidence_fingerprint",
    "cover_letter_recipient_fingerprint",
)

PROFILE_DERIVED_WORKFLOW_KEYS = (
    "plan",
    "resume",
    "generated_resume_artifact",
    "generated_content_reviewed",
    PROFILE_FINGERPRINT_KEY,
    "cover_letter",
    "cover_letter_reviewed",
    "cover_letter_profile_fingerprint",
    "cover_letter_posting_fingerprint",
    "cover_letter_plan_fingerprint",
    "cover_letter_evidence_fingerprint",
    "cover_letter_recipient_fingerprint",
)


def invalidate_derived_workflow(state: MutableMapping[str, object]) -> None:
    for key in DERIVED_WORKFLOW_KEYS:
        state.pop(key, None)


def invalidate_posting_derived_workflow(state: MutableMapping[str, object]) -> None:
    """Remove the active posting and every artifact derived from that posting."""

    state.pop(ACTIVE_POSTING_KEY, None)
    for key in POSTING_DERIVED_WORKFLOW_KEYS:
        state.pop(key, None)


def get_active_posting(state: MutableMapping[str, object]) -> object | None:
    """Return the validated posting shared by all downstream workflow consumers."""

    return state.get(ACTIVE_POSTING_KEY)


def has_cover_letter_prerequisites(state: MutableMapping[str, object]) -> bool:
    """Report whether the active profile, posting, and strategy can draft a letter."""

    plan = state.get("plan")
    return (
        state.get("profile") is not None
        and get_active_posting(state) is not None
        and plan is not None
        and getattr(plan, "strategy", None) is not None
    )


def invalidate_profile_derived_workflow(state: MutableMapping[str, object]) -> None:
    """Remove profile-dependent artifacts while preserving the active posting."""

    for key in PROFILE_DERIVED_WORKFLOW_KEYS:
        state.pop(key, None)
