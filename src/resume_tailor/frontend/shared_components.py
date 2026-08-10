"""Small, intentionally shared Precision Workbench presentation helpers."""

from __future__ import annotations

from html import escape
from typing import Any

from resume_tailor.frontend.routes import AppRoute

_WORKSPACE_ICON_PATHS: dict[AppRoute, str] = {
    AppRoute.CAREER_PROFILE: (
        '<circle cx="12" cy="8" r="3.25"/><path d="M5.5 20c.55-3.25 3.1-5 6.5-5s5.95 1.75 6.5 5"/>'
    ),
    AppRoute.JOBS: (
        '<path d="M4.5 8.5h15v10.25h-15z"/><path d="M9 8.5v-2h6v2M4.5 12.5h15M10 12.5h4v2h-4z"/>'
    ),
    AppRoute.RESUME_STUDIO: (
        '<path d="M6 3.75h8.5l3.5 3.5v13H6z"/><path d="M14.5 3.75v3.5H18M9 12h6M9 15h6M9 9h2.75"/>'
    ),
    AppRoute.COVER_LETTERS: (
        '<rect x="3.75" y="6" width="16.5" height="12" rx="1"/>'
        '<path d="m4.25 7 7.75 5.75L19.75 7"/>'
    ),
}


def workspace_icon_markup(route: AppRoute) -> str:
    """Return a decorative centralized inline SVG beside a native control."""

    path = _WORKSPACE_ICON_PATHS[route]
    label = escape(route.value)
    return (
        f'<span class="pw-workspace-icon" aria-hidden="true" data-workspace-icon="{label}">'
        '<svg viewBox="0 0 24 24" fill="none" stroke-width="1.7" '
        'stroke-linecap="round" stroke-linejoin="round" focusable="false">'
        f"{path}</svg></span>"
    )


def render_page_header(streamlit_module: Any, title: str, description: str | None = None) -> None:
    """Render a restrained page header without substituting for page controls."""

    streamlit_module.title(title)
    if description:
        streamlit_module.caption(description)


__all__ = ["render_page_header", "workspace_icon_markup"]
