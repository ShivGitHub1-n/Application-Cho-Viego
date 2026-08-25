"""Small, intentionally shared Precision Workbench presentation helpers."""

from __future__ import annotations

from collections.abc import Mapping
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

_EMPTY_ICON_PATHS = {
    "check": '<path d="m5.5 12.5 4 4 9-9"/>',
    "document": (
        '<path d="M6 3.75h8.5l3.5 3.5v13H6z"/>'
        '<path d="M14.5 3.75v3.5H18M9 12h6M9 15h6"/>'
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


def render_page_header(
    streamlit_module: Any,
    title: str,
    description: str | None = None,
    *,
    eyebrow: str | None = None,
) -> None:
    """Render the shared product header while retaining native accessible headings."""

    with streamlit_module.container(key="pw-page-header"):
        if eyebrow:
            streamlit_module.markdown(
                f'<div class="pw-eyebrow">{escape(eyebrow)}</div>',
                unsafe_allow_html=True,
            )
        streamlit_module.title(title)
        if description:
            streamlit_module.caption(description)


def render_status_strip(streamlit_module: Any, items: Mapping[str, str]) -> None:
    """Render concise product status without exposing diagnostic implementation terms."""

    cards = "".join(
        '<div class="pw-status-item">'
        f"<span>{escape(label)}</span><strong>{escape(value)}</strong>"
        "</div>"
        for label, value in items.items()
    )
    streamlit_module.markdown(f'<div class="pw-status-strip">{cards}</div>', unsafe_allow_html=True)


def render_empty_state(
    streamlit_module: Any,
    title: str,
    message: str,
    *,
    icon: str = "document",
) -> None:
    """Render a consistent, action-oriented empty state."""

    icon_path = _EMPTY_ICON_PATHS.get(icon, _EMPTY_ICON_PATHS["document"])
    streamlit_module.markdown(
        '<div class="pw-empty-state">'
        '<span class="pw-empty-icon" aria-hidden="true">'
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
        'stroke-linecap="round" stroke-linejoin="round" focusable="false">'
        f"{icon_path}</svg></span>"
        f"<div><strong>{escape(title)}</strong><p>{escape(message)}</p></div>"
        "</div>",
        unsafe_allow_html=True,
    )


__all__ = [
    "render_empty_state",
    "render_page_header",
    "render_status_strip",
    "workspace_icon_markup",
]
