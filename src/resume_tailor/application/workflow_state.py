from __future__ import annotations

from collections.abc import MutableMapping
from enum import StrEnum


class GeneratedResumeReviewState(StrEnum):
    """Explicit lifecycle states for a generated resume artifact."""

    GENERATED_AWAITING_REVIEW = "generated_awaiting_review"
    WORDING_CHANGED_REBUILD_REQUIRED = "wording_changed_rebuild_required"
    REBUILD_IN_PROGRESS = "rebuild_in_progress"
    REBUILT_AWAITING_REVIEW = "rebuilt_awaiting_review"
    REBUILT_APPROVED = "rebuilt_approved"
    DOWNLOADED = "downloaded"


GENERATED_RESUME_REVIEW_STATE_KEY = "generated_resume_review_state"
GENERATED_RESUME_APPROVED_CLAIMS_KEY = "generated_resume_approved_claim_ids"
GENERATED_RESUME_GENERATED_APPROVALS_KEY = "generated_resume_generated_approval_ids"
GENERATED_RESUME_ARTIFACT_VERSION_KEY = "generated_resume_artifact_version"
GENERATED_RESUME_REBUILD_REQUIRED_KEY = "generated_resume_rebuild_required"
GENERATED_RESUME_WORDING_DIRTY_KEY = "generated_resume_wording_dirty"
GENERATED_RESUME_REBUILD_IN_PROGRESS_KEY = "generated_resume_rebuild_in_progress"
GENERATED_RESUME_REBUILD_ERROR_KEY = "generated_resume_rebuild_error"

DERIVED_WORKFLOW_KEYS = (
    "plan",
    "resume",
    "generated_resume_artifact",
    "generated_content_reviewed",
    GENERATED_RESUME_REVIEW_STATE_KEY,
    GENERATED_RESUME_APPROVED_CLAIMS_KEY,
    GENERATED_RESUME_GENERATED_APPROVALS_KEY,
    GENERATED_RESUME_ARTIFACT_VERSION_KEY,
    GENERATED_RESUME_REBUILD_REQUIRED_KEY,
    GENERATED_RESUME_WORDING_DIRTY_KEY,
    GENERATED_RESUME_REBUILD_IN_PROGRESS_KEY,
    GENERATED_RESUME_REBUILD_ERROR_KEY,
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
    GENERATED_RESUME_REVIEW_STATE_KEY,
    GENERATED_RESUME_APPROVED_CLAIMS_KEY,
    GENERATED_RESUME_GENERATED_APPROVALS_KEY,
    GENERATED_RESUME_ARTIFACT_VERSION_KEY,
    GENERATED_RESUME_REBUILD_REQUIRED_KEY,
    GENERATED_RESUME_WORDING_DIRTY_KEY,
    GENERATED_RESUME_REBUILD_IN_PROGRESS_KEY,
    GENERATED_RESUME_REBUILD_ERROR_KEY,
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
    GENERATED_RESUME_REVIEW_STATE_KEY,
    GENERATED_RESUME_APPROVED_CLAIMS_KEY,
    GENERATED_RESUME_GENERATED_APPROVALS_KEY,
    GENERATED_RESUME_ARTIFACT_VERSION_KEY,
    GENERATED_RESUME_REBUILD_REQUIRED_KEY,
    GENERATED_RESUME_WORDING_DIRTY_KEY,
    GENERATED_RESUME_REBUILD_IN_PROGRESS_KEY,
    GENERATED_RESUME_REBUILD_ERROR_KEY,
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
