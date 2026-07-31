from __future__ import annotations

from collections.abc import Callable
from typing import Any

APPLICATION_OPTIONS = ("Jobs", "Resume Tailor", "Cover letters", "Master profile")


def render_application_shell(
    streamlit_module: Any,
    *,
    active_profile_label: str | None = None,
    active_profile_id: str | None = None,
    development_ui: Callable[[], None] | None = None,
) -> str:
    """Render the shared application sidebar using native Streamlit controls."""

    state = streamlit_module.session_state
    pending_page = state.pop("jobs_pending_page", None)
    if pending_page in APPLICATION_OPTIONS:
        state["app_active_page"] = pending_page
    stored = state.get("app_active_page", "Resume Tailor")
    if stored not in APPLICATION_OPTIONS:
        stored = "Resume Tailor"

    with streamlit_module.sidebar:
        streamlit_module.title("Resume Tailor")
        streamlit_module.caption("Evidence-backed application tools")
        streamlit_module.caption("Navigation")
        selected = streamlit_module.pills(
            "Application navigation",
            APPLICATION_OPTIONS,
            default=stored,
            key="app_active_page",
            label_visibility="collapsed",
        )
        if selected in APPLICATION_OPTIONS:
            stored = selected
        streamlit_module.divider()
        streamlit_module.caption("Active profile")
        label = active_profile_label or state.get("profile_display_name")
        profile_id = active_profile_id or state.get("jobs_profile_id") or state.get("profile_id")
        streamlit_module.write(label or "Choose a reviewed profile in Jobs")
        streamlit_module.caption(f"Reviewed profile · {profile_id or 'not selected'}")
        if development_ui is not None:
            with streamlit_module.expander("Offline scenario", expanded=False):
                development_ui()
    return str(stored)


__all__ = ["APPLICATION_OPTIONS", "render_application_shell"]
