"""Shared Precision Workbench navigation shell."""

from __future__ import annotations

from collections.abc import Callable, MutableMapping, Sequence
from typing import Any

from resume_tailor.frontend.app_shell_styles import application_shell_css
from resume_tailor.frontend.design_tokens import design_token_css, resolve_theme_type
from resume_tailor.frontend.routes import ROUTE_OPTIONS, AppRoute, normalize_route
from resume_tailor.frontend.shared_components import workspace_icon_markup

APPLICATION_OPTIONS = tuple(route.value for route in ROUTE_OPTIONS)


def _consume_pending_route(state: MutableMapping[str, Any]) -> AppRoute | None:
    """Consume the current and legacy pending-route keys before controls render."""

    current = state.pop("app_pending_page", None)
    legacy = state.pop("jobs_pending_page", None)
    if current is not None:
        return normalize_route(current)
    if legacy is not None:
        return normalize_route(legacy)
    return None


def _select_route(streamlit_module: Any, route: AppRoute) -> None:
    streamlit_module.session_state["app_pending_page"] = route.value
    streamlit_module.rerun()


def _select_profile(
    state: MutableMapping[str, Any], on_profile_change: Callable[[str], None] | None
) -> None:
    selected = str(state.get("jobs-profile-selector", "")).strip()
    if not selected:
        return
    state["jobs_profile_id"] = selected
    state["profile_id"] = selected
    state.pop("profile", None)
    if on_profile_change is not None:
        on_profile_change(selected)


def _render_route_control(
    streamlit_module: Any,
    route: AppRoute,
    active_route: AppRoute,
    key: str,
) -> None:
    row_key = "pw-route-row-active" if route is active_route else "pw-route-row"
    with streamlit_module.container(key=f"{row_key}-{key}-{route.name.lower()}"):
        icon_column, action_column = streamlit_module.columns((.18, 1))
        with icon_column:
            streamlit_module.markdown(
                workspace_icon_markup(route),
                unsafe_allow_html=True,
            )
        with action_column:
            if streamlit_module.button(route.value, key=f"pw-route-{key}-{route.name.lower()}"):
                _select_route(streamlit_module, route)


def _render_mobile_navigation(
    streamlit_module: Any,
    active_route: AppRoute,
) -> None:
    with streamlit_module.container(key="pw-mobile-navigation"):
        columns = streamlit_module.columns(len(ROUTE_OPTIONS))
        for column, route in zip(columns, ROUTE_OPTIONS, strict=True):
            container_key = (
                "pw-mobile-navigation-active" if route is active_route else "pw-mobile-navigation"
            )
            with column:
                with streamlit_module.container(key=f"{container_key}-{route.name.lower()}"):
                    streamlit_module.markdown(workspace_icon_markup(route), unsafe_allow_html=True)
                    if streamlit_module.button(
                        route.value,
                        key=f"pw-mobile-route-{route.name.lower()}",
                    ):
                        _select_route(streamlit_module, route)


def render_application_shell(
    streamlit_module: Any,
    *,
    active_profile_label: str | None = None,
    active_profile_id: str | None = None,
    development_ui: Callable[[], None] | None = None,
    profile_options: Sequence[tuple[str, str]] | None = None,
    on_profile_change: Callable[[str], None] | None = None,
) -> str:
    """Render canonical navigation and return the selected product route.

    The shell owns route migration only. Page-specific input and derived state
    remain owned by the appropriate workflow modules.
    """

    state = streamlit_module.session_state
    pending_route = _consume_pending_route(state)
    active_route = pending_route or normalize_route(state.get("app_active_page"))
    state["app_active_page"] = active_route.value

    streamlit_module.markdown(
        design_token_css(resolve_theme_type(streamlit_module)), unsafe_allow_html=True
    )
    streamlit_module.markdown(application_shell_css(), unsafe_allow_html=True)
    with streamlit_module.container(key="pw-shell-root"):
        with streamlit_module.sidebar:
            with streamlit_module.container(key="pw-sidebar-brand"):
                streamlit_module.markdown("### Viego")
                streamlit_module.caption("Your application workspace")
            streamlit_module.caption("Workspace")
            for route in ROUTE_OPTIONS:
                _render_route_control(streamlit_module, route, active_route, "sidebar")
            with streamlit_module.container(key="pw-profile-context"):
                streamlit_module.caption("Active profile")
                profile_id = active_profile_id or state.get("jobs_profile_id") or state.get(
                    "profile_id"
                )
                if profile_options:
                    profile_ids = [profile_id for profile_id, _ in profile_options]
                    labels = dict(profile_options)
                    selected = profile_id if profile_id in profile_ids else profile_ids[0]
                    streamlit_module.selectbox(
                        "Active profile",
                        profile_ids,
                        index=profile_ids.index(selected),
                        format_func=lambda value: labels[value],
                        key="jobs-profile-selector",
                        label_visibility="collapsed",
                        on_change=_select_profile,
                        args=(state, on_profile_change),
                    )
                    streamlit_module.caption("Reviewed profile")
                else:
                    label = active_profile_label or state.get("profile_display_name")
                    streamlit_module.markdown(label or "Choose a reviewed profile")
                    streamlit_module.caption(
                        "Reviewed profile" if profile_id else "No profile selected"
                    )
            if development_ui is not None:
                with streamlit_module.expander("Developer preview", expanded=False):
                    development_ui()
        _render_mobile_navigation(streamlit_module, active_route)
    return active_route.value


__all__ = ["APPLICATION_OPTIONS", "render_application_shell"]
