from __future__ import annotations

import json
from collections.abc import MutableMapping
from typing import Any

from resume_tailor.application.profile_editor import profile_to_editor_state
from resume_tailor.domain.models import MasterProfile

NAVIGATION_ITEMS: tuple[str, ...] = (
    "Home / Workspace",
    "Profile",
    "Tailor Resume",
    "Cover Letter",
    "Job Search",
    "Settings / Diagnostics",
)
DEFAULT_NAVIGATION_ITEM = NAVIGATION_ITEMS[0]


def initialize_frontend_state(state: MutableMapping[str, Any]) -> None:
    state.setdefault("active_page", DEFAULT_NAVIGATION_ITEM)
    state.setdefault("navigation_selection", state["active_page"])
    state.setdefault("profile_id", "local-profile")
    state.setdefault("profile_id_input", state["profile_id"])
    state.setdefault("profile_load_status", "No reviewed profile is loaded.")
    state.setdefault("generated_content_reviewed", False)
    state.setdefault("cover_letter_reviewed", False)


def populate_profile_editor_state(
    state: MutableMapping[str, Any],
    profile: MasterProfile,
    source_key: str,
    *,
    defer_raw_json: bool = False,
) -> bool:
    """Populate visible structured controls once for a saved or imported source."""

    if state.get("profile_editor_source_key") == source_key:
        return False
    state["profile_editor_state"] = profile_to_editor_state(profile)
    state["profile_editor_source_key"] = source_key
    raw_json = json.dumps(
        profile.model_dump(mode="json"),
        indent=2,
    )
    if defer_raw_json:
        state["profile_editor_pending_raw_json"] = raw_json
    else:
        state["profile_editor_raw_json"] = raw_json
    state.pop("profile_editor_errors", None)
    return True


def navigate_to(
    state: MutableMapping[str, Any],
    page: str,
) -> None:
    if page not in NAVIGATION_ITEMS:
        raise ValueError(f"Unknown frontend page: {page}")
    state["active_page"] = page
    state["navigation_selection"] = page


__all__ = [
    "DEFAULT_NAVIGATION_ITEM",
    "NAVIGATION_ITEMS",
    "initialize_frontend_state",
    "navigate_to",
    "populate_profile_editor_state",
]
