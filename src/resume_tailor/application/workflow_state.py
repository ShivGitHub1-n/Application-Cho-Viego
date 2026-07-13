from __future__ import annotations

from collections.abc import MutableMapping


DERIVED_WORKFLOW_KEYS = (
    "plan",
    "resume",
    "generated_content_reviewed",
    "workflow_profile_fingerprint",
    "workflow_posting_fingerprint",
)


def invalidate_derived_workflow(state: MutableMapping[str, object]) -> None:
    for key in DERIVED_WORKFLOW_KEYS:
        state.pop(key, None)
