from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import is_dataclass, replace
from datetime import UTC, datetime
from html import escape
from typing import Any, Protocol

import streamlit as st

from resume_tailor.application.job_discovery.background_refresh import (
    BackgroundRefreshSnapshot,
    BackgroundRefreshStatus,
)
from resume_tailor.application.job_discovery.experience import (
    FeedView,
    JobsExperienceService,
)
from resume_tailor.application.job_discovery.filtering import filter_recommendations
from resume_tailor.application.job_discovery.handoff import TailoringHandoff
from resume_tailor.application.job_discovery.presentation import (
    normalize_job_description_for_display,
)
from resume_tailor.application.job_intake import normalize_job_description
from resume_tailor.application.workflow_state import (
    invalidate_derived_workflow,
    set_active_application_context,
)
from resume_tailor.domain.job_discovery.queries import APPROVED_EXPLORE_SECTORS, FeedKind
from resume_tailor.domain.models import JobPosting
from resume_tailor.frontend.job_feed_view import render_feed
from resume_tailor.frontend.job_preferences_view import render_preferences
from resume_tailor.frontend.jobs_filter_view import clear_browse_state, render_browse_controls
from resume_tailor.frontend.jobs_styles import jobs_css as shared_jobs_css
from resume_tailor.frontend.saved_jobs_view import render_saved_jobs


class JobsPageExperience(Protocol):
    def list_reviewed_profiles(self) -> Any: ...
    def get_preferences(self, profile_id: str) -> Any: ...
    def suggest_preferences(self, profile_id: str) -> Any: ...
    def confirm_preferences(self, preferences: Any) -> Any: ...
    def load_feed(
        self, profile_id: str, feed_kind: FeedKind, *, sector: str | None = None
    ) -> FeedView: ...
    def load_excluded(
        self, profile_id: str, feed_kind: FeedKind, *, sector: str | None = None
    ) -> Any: ...
    def refresh_tailored(self, profile_id: str) -> Any: ...
    def refresh_explore(self, profile_id: str, sector: str) -> Any: ...
    def start_tailored_refresh(self, profile_id: str) -> BackgroundRefreshSnapshot: ...
    def start_explore_refresh(
        self, profile_id: str, sector: str
    ) -> BackgroundRefreshSnapshot: ...
    def refresh_state(
        self,
        profile_id: str,
        feed_kind: FeedKind,
        *,
        sector: str | None = None,
    ) -> BackgroundRefreshSnapshot | None: ...
    def get_job_detail(
        self,
        profile_id: str,
        feed_kind: FeedKind,
        job_id: str,
        *,
        sector: str | None = None,
    ) -> Any: ...
    def save_job(self, job_id: str, profile_id: str) -> Any: ...
    def list_saved_jobs(self, profile_id: str) -> Any: ...
    def check_saved_job_availability(self, saved_id: str, profile_id: str) -> Any: ...
    def prepare_tailoring(self, job_id: str, profile_id: str) -> Any: ...
    def prepare_saved_tailoring(self, saved_id: str, profile_id: str) -> Any: ...


# Compatibility export for callers that historically imported jobs_css from
# this module. The implementation lives in the centralized token module.
jobs_css = shared_jobs_css
_JOB_CARD_WINDOW_SIZE = 24


def _windowed_recommendations(
    items: list[Any], visible_limit: int, selected_job_id: str | None
) -> list[Any]:
    """Bound card rendering while retaining an explicitly selected result."""

    windowed = list(items[:visible_limit])
    if selected_job_id and selected_job_id not in {item.job_id for item in windowed}:
        selected_item = next(
            (item for item in items if item.job_id == selected_job_id),
            None,
        )
        if selected_item is not None:
            windowed.append(selected_item)
    return windowed


def apply_tailoring_handoff(
    state: MutableMapping[str, object],
    handoff: TailoringHandoff | Any,
    *,
    destination: str = "Resume Studio",
) -> None:
    """Bind one application context, then open either sibling document workspace."""

    invalidate_derived_workflow(state)
    current_profile = state.get("profile")
    if getattr(current_profile, "id", None) != handoff.profile_id:
        state.pop("profile", None)
    state["profile_id"] = handoff.profile_id
    state["profile_id_input"] = handoff.profile_id
    state["job_title_input"] = handoff.title
    company = str(getattr(handoff, "company", "")).strip()
    state["job_company_input"] = company
    display_description = normalize_job_description_for_display(handoff.description)
    state["job_description_input"] = display_description
    state.pop("_resume_studio_job_title_widget", None)
    state.pop("_resume_studio_job_company_widget", None)
    state.pop("_resume_studio_job_description_widget", None)
    state.pop("cover_direct_company", None)
    state.pop("cover_direct_role", None)
    state.pop("cover_direct_posting", None)
    state["resume_studio_pending_stage"] = "Job context"
    posting = JobPosting(
        id=str(getattr(handoff, "posting_id", "jobs-handoff-posting")),
        title=handoff.title.strip(),
        company_name=company or None,
        description=normalize_job_description(display_description),
        source_url=str(getattr(handoff, "official_url", "")).strip() or None,
    )
    set_active_application_context(state, posting)
    state["app_pending_page"] = destination
    state["pending_tailoring_handoff"] = handoff


def render_jobs_page(
    experience: JobsPageExperience | JobsExperienceService,
    *,
    streamlit_module: Any = st,
) -> None:
    streamlit_module.markdown(jobs_css(), unsafe_allow_html=True)
    with streamlit_module.container(key="jobs-page"):
        with streamlit_module.container(key="jobs-header"):
            header_col, action_col = streamlit_module.columns(
                [4.6, 1], gap="large", vertical_alignment="top"
            )
            profiles_result = experience.list_reviewed_profiles()
            if getattr(profiles_result, "warning", None):
                streamlit_module.warning(profiles_result.warning)
            profiles = list(getattr(profiles_result, "profiles", []))
            if not profiles:
                _render_empty_state(
                    streamlit_module,
                    "A reviewed profile is required",
                    "Review and save a profile in Career Profile before discovering jobs.",
                    action_label="Open Career Profile",
                    action_key="jobs-open-master-profile",
                )
                return
            profile_ids = [profile.profile_id for profile in profiles]
            owners = {profile.profile_id: profile.user_id for profile in profiles}
            previous_profile = streamlit_module.session_state.get("jobs_profile_id")
            selected_profile = previous_profile
            if selected_profile not in profile_ids:
                selected_profile = profile_ids[0]
            if previous_profile != selected_profile:
                _clear_profile_state(streamlit_module.session_state)
                streamlit_module.session_state["jobs_profile_id"] = selected_profile
                streamlit_module.session_state["profile_id"] = selected_profile
            preferences = experience.get_preferences(selected_profile)
            with header_col:
                streamlit_module.title("Jobs")
                streamlit_module.caption(
                    "Evidence-backed job discovery from approved sources, with fit, "
                    "eligibility, evidence, and freshness kept distinct."
                )
            with action_col:
                if streamlit_module is st and _refresh_is_running(
                    experience, selected_profile, FeedKind.TAILORED
                ):
                    _tailored_refresh_fragment(
                        experience,
                        selected_profile,
                        disabled=preferences is None,
                    )
                else:
                    _render_tailored_refresh_control(
                        experience,
                        selected_profile,
                        streamlit_module,
                        disabled=preferences is None,
                    )

        with streamlit_module.container(key="jobs-section-nav"):
            section_options = [
                "Tailored for you",
                "Explore sectors",
                "Saved",
                "Preferences",
            ]
            pending_section = streamlit_module.session_state.pop("jobs_pending_section", None)
            current_section = pending_section or streamlit_module.session_state.get(
                "jobs-active-section", section_options[0]
            )
            if current_section not in section_options:
                current_section = section_options[0]
            if pending_section in section_options:
                streamlit_module.session_state.pop("jobs-active-section", None)
            section = streamlit_module.pills(
                "Jobs section",
                section_options,
                default=current_section,
                key="jobs-active-section",
                label_visibility="collapsed",
            )
            if section not in section_options:
                section = current_section
        if section == "Tailored for you":
            _render_tailored(experience, selected_profile, streamlit_module, preferences)
        elif section == "Explore sectors":
            _render_explore(experience, selected_profile, streamlit_module)
        elif section == "Saved":
            render_saved_jobs(experience, selected_profile, streamlit_module=streamlit_module)
        else:
            with streamlit_module.container(key="jobs-preferences"):
                render_preferences(
                    experience,
                    selected_profile,
                    owners[selected_profile],
                    streamlit_module=streamlit_module,
                )


def _render_tailored(
    experience: JobsPageExperience,
    profile_id: str,
    streamlit_module: Any,
    preferences: Any,
) -> None:
    if preferences is None:
        _render_empty_state(
            streamlit_module,
            "Confirm Preferences before refreshing Tailored",
            "Set your role direction, constraints, and recency in Preferences, then return "
            "here to load evidence-backed recommendations.",
            action_label="Open Preferences",
            action_key="jobs-open-preferences",
        )
        return
    try:
        feed = experience.load_feed(profile_id, FeedKind.TAILORED)
    except Exception:
        _render_empty_state(
            streamlit_module,
            "Tailored recommendations are temporarily unavailable",
            "Previously stored results were preserved. Try refreshing again when approved "
            "sources are available.",
            action_label="Refresh recommendations",
            action_key="jobs-refresh-tailored-failure",
        )
        return
    controls = render_browse_controls(
        streamlit_module,
        section="tailored",
        items=feed.visible,
        filter_items=filter_recommendations,
        now=_browse_now(experience),
    )
    projected_feed = _project_feed(feed, controls.filtered)
    _render_sort_note(streamlit_module, "Sorted by fit, eligibility, then freshness")
    _render_feed(
        experience,
        profile_id,
        FeedKind.TAILORED,
        projected_feed,
        streamlit_module,
        base_visible_count=controls.base_count,
    )


def _render_explore(experience: JobsPageExperience, profile_id: str, streamlit_module: Any) -> None:
    with streamlit_module.container(key="jobs-explore-controls"):
        control_col, spacer_col, action_col = streamlit_module.columns(
            [1.25, 0.65, 1], gap="medium", vertical_alignment="bottom"
        )
        with control_col:
            sector = streamlit_module.selectbox(
                "Explore sector",
                list(APPROVED_EXPLORE_SECTORS),
                key="jobs-explore-sector",
            )
        with spacer_col:
            streamlit_module.empty()
        with action_col:
            with streamlit_module.container(key="jobs-explore-action"):
                if streamlit_module is st and _refresh_is_running(
                    experience, profile_id, FeedKind.EXPLORE, sector=sector
                ):
                    _explore_refresh_fragment(experience, profile_id, sector)
                else:
                    _render_explore_refresh_control(
                        experience, profile_id, sector, streamlit_module
                    )
    previous_sector = streamlit_module.session_state.get("jobs_selected_explore_sector")
    if previous_sector != sector:
        streamlit_module.session_state.pop("jobs_explore_selected_job_id", None)
        streamlit_module.session_state.pop("jobs_explore_excluded_expanded", None)
    streamlit_module.session_state["jobs_selected_explore_sector"] = sector
    try:
        feed = experience.load_feed(profile_id, FeedKind.EXPLORE, sector=sector)
    except Exception as error:
        _render_empty_state(
            streamlit_module,
            "Explore feed could not be read",
            f"The persisted feed for {sector} could not be read: {error}",
            action_label=None,
            action_key="jobs-refresh-explore-empty",
        )

    if not feed.visible and feed.status == "no_sources_configured":
        _render_empty_state(
            streamlit_module,
            "No approved sources configured",
            "Configure or restore an approved source before refreshing this sector.",
            action_label=None,
            action_key="jobs-refresh-explore-empty",
        )
        return
    if not feed.visible and feed.status == "failed_all_sources":
        _render_empty_state(
            streamlit_module,
            "All approved sources failed",
            "No new sector roles were retrieved. Previously persisted results remain unchanged.",
            action_label=None,
            action_key="jobs-refresh-explore-empty",
        )
        return
    if not feed.visible and feed.status in {"completed", "completed_with_warnings"}:
        message = (
            "Approved sources returned no records for this sector."
            if getattr(feed, "retrieved_count", 0) == 0
            else "No sector roles matched the approved retrieval boundary."
        )
        _render_empty_state(
            streamlit_module,
            "Explore returned no roles",
            message,
            action_label=None,
            action_key="jobs-refresh-explore-empty",
        )
        return
    controls = render_browse_controls(
        streamlit_module,
        section="explore",
        items=feed.visible,
        filter_items=filter_recommendations,
        now=_browse_now(experience),
    )
    projected_feed = _project_feed(feed, controls.filtered)
    _render_sort_note(streamlit_module, "Newest postings first; fit breaks ties")
    _render_feed(
        experience,
        profile_id,
        FeedKind.EXPLORE,
        projected_feed,
        streamlit_module,
        base_visible_count=controls.base_count,
    )


def render_jobs_unavailable(streamlit_module: Any = st) -> None:
    """Render a controlled storage-unavailable boundary for Jobs."""

    with streamlit_module.container(border=True, key="jobs-database-unavailable"):
        streamlit_module.subheader("Jobs is temporarily unavailable")
        streamlit_module.write(
            "The local Jobs database is busy or unavailable. Retry after the current "
            "workspace run has finished."
        )
        if streamlit_module.button("Retry Jobs", key="jobs-retry-database"):
            streamlit_module.rerun()


def _render_feed(
    experience: JobsPageExperience,
    profile_id: str,
    feed_kind: FeedKind,
    feed: FeedView,
    streamlit_module: Any,
    *,
    base_visible_count: int | None = None,
) -> None:
    selected_key = (
        "jobs_tailored_selected_job_id"
        if feed_kind is FeedKind.TAILORED
        else "jobs_explore_selected_job_id"
    )
    expanded_key = (
        "jobs_tailored_excluded_expanded"
        if feed_kind is FeedKind.TAILORED
        else "jobs_explore_excluded_expanded"
    )
    selected = streamlit_module.session_state.get(selected_key)
    expanded = bool(streamlit_module.session_state.get(expanded_key, False))
    selection_scope = f"{feed_kind.value}-{_safe_key(profile_id)}"
    if feed_kind is FeedKind.EXPLORE:
        sector = streamlit_module.session_state.get("jobs_selected_explore_sector", "")
        selection_scope = f"{selection_scope}-{_safe_key(str(sector))}"
    else:
        sector = None
    window_key = f"jobs-visible-window-{selection_scope}"
    visible_limit = max(
        _JOB_CARD_WINDOW_SIZE,
        int(streamlit_module.session_state.get(window_key, _JOB_CARD_WINDOW_SIZE)),
    )
    full_visible = list(feed.visible)
    windowed_visible = _windowed_recommendations(full_visible, visible_limit, selected)
    display_feed = _project_feed(feed, windowed_visible)
    excluded = experience.load_excluded(profile_id, feed_kind, sector=sector) if expanded else []
    if not feed.visible:
        streamlit_module.session_state.pop(selected_key, None)
    if feed.status:
        streamlit_module.caption(
            f"{_human_status(feed.status)} · Last refreshed {_format_refresh(feed.last_refresh_at)}"
        )
        if feed.status == "no_sources_configured":
            streamlit_module.warning("No approved job sources are configured")
        elif feed.status == "failed_all_sources":
            streamlit_module.error(
                "All approved job sources failed. Previously stored recommendations were preserved."
            )
    for warning in feed.source_warnings:
        streamlit_module.warning(_human_source_warning(warning))

    def toggle_excluded() -> list[Any] | None:
        expanded_now = not expanded
        streamlit_module.session_state[expanded_key] = expanded_now
        if expanded_now:
            return experience.load_excluded(profile_id, feed_kind, sector=sector)
        return []

    with streamlit_module.container(key="jobs-feed-layout"):
        render_feed(
            display_feed,
            selected_job_id=selected,
            selected_key=selected_key,
            selection_scope=selection_scope,
            streamlit_module=streamlit_module,
            on_select=lambda job_id: streamlit_module.session_state.__setitem__(
                selected_key, job_id
            ),
            on_save=lambda job_id: experience.save_job(job_id, profile_id),
            on_tailor=lambda job_id: _tailor(experience, profile_id, job_id, streamlit_module),
            on_cover_letter=lambda job_id: _create_cover_letter(
                experience, profile_id, job_id, streamlit_module
            ),
            get_detail=lambda job_id: experience.get_job_detail(
                profile_id, feed_kind, job_id, sector=sector
            ),
            expanded_excluded=expanded,
            excluded=excluded,
            on_toggle_excluded=toggle_excluded,
            base_visible_count=base_visible_count,
        )
        if len(full_visible) > len(windowed_visible):
            streamlit_module.caption(
                f"Showing {len(windowed_visible)} of {len(full_visible)} matching jobs"
            )
            if streamlit_module.button(
                "Load more jobs",
                key=f"jobs-load-more-{selection_scope}",
                width="stretch",
            ):
                streamlit_module.session_state[window_key] = min(
                    len(full_visible), visible_limit + _JOB_CARD_WINDOW_SIZE
                )
                streamlit_module.rerun()


def _tailor(
    experience: JobsPageExperience, profile_id: str, job_id: str, streamlit_module: Any
) -> None:
    handoff = experience.prepare_tailoring(job_id, profile_id)
    apply_tailoring_handoff(streamlit_module.session_state, handoff)
    streamlit_module.success("Tailoring inputs prepared. Resume Studio is ready for review.")
    if hasattr(streamlit_module, "rerun"):
        streamlit_module.rerun()


def _create_cover_letter(
    experience: JobsPageExperience, profile_id: str, job_id: str, streamlit_module: Any
) -> None:
    handoff = experience.prepare_tailoring(job_id, profile_id)
    apply_tailoring_handoff(
        streamlit_module.session_state,
        handoff,
        destination="Cover Letters",
    )
    streamlit_module.success("Application context prepared. Cover Letters is ready.")
    if hasattr(streamlit_module, "rerun"):
        streamlit_module.rerun()


@st.fragment(run_every=1.0)
def _tailored_refresh_fragment(
    experience: JobsPageExperience,
    profile_id: str,
    *,
    disabled: bool,
) -> None:
    _render_tailored_refresh_control(
        experience,
        profile_id,
        st,
        disabled=disabled,
    )


@st.fragment(run_every=1.0)
def _explore_refresh_fragment(
    experience: JobsPageExperience,
    profile_id: str,
    sector: str,
) -> None:
    _render_explore_refresh_control(experience, profile_id, sector, st)


def _render_tailored_refresh_control(
    experience: JobsPageExperience,
    profile_id: str,
    streamlit_module: Any,
    *,
    disabled: bool,
) -> None:
    snapshot = _background_refresh_state(
        experience, profile_id, FeedKind.TAILORED
    )
    running = snapshot is not None and snapshot.status is BackgroundRefreshStatus.RUNNING
    if streamlit_module.button(
        "Refresh recommendations",
        key="jobs-refresh-tailored",
        type="primary",
        width="stretch",
        disabled=disabled or running,
    ):
        starter = getattr(experience, "start_tailored_refresh", None)
        if callable(starter):
            snapshot = starter(profile_id)
            streamlit_module.rerun()
        else:
            _refresh_tailored(experience, profile_id, streamlit_module)
    _render_refresh_snapshot(
        streamlit_module,
        snapshot,
        timestamp_key="jobs_last_tailored_refresh",
        status_key="jobs_last_tailored_status",
        excluded_key="jobs_tailored_excluded_expanded",
    )


def _render_explore_refresh_control(
    experience: JobsPageExperience,
    profile_id: str,
    sector: str,
    streamlit_module: Any,
) -> None:
    snapshot = _background_refresh_state(
        experience, profile_id, FeedKind.EXPLORE, sector=sector
    )
    running = snapshot is not None and snapshot.status is BackgroundRefreshStatus.RUNNING
    if streamlit_module.button(
        "Refresh Explore roles",
        key="jobs-refresh-explore",
        type="primary",
        width="content",
        disabled=running,
    ):
        starter = getattr(experience, "start_explore_refresh", None)
        if callable(starter):
            snapshot = starter(profile_id, sector)
            streamlit_module.rerun()
        else:
            try:
                result = experience.refresh_explore(profile_id, sector)
                streamlit_module.session_state["jobs_last_explore_refresh"] = (
                    _refresh_timestamp(result)
                )
                streamlit_module.session_state["jobs_last_explore_status"] = (
                    _refresh_status(result)
                )
                streamlit_module.session_state["jobs_explore_excluded_expanded"] = False
            except Exception:
                streamlit_module.error(
                    "Explore roles could not be refreshed. Previously stored results "
                    "were preserved."
                )
    _render_refresh_snapshot(
        streamlit_module,
        snapshot,
        timestamp_key="jobs_last_explore_refresh",
        status_key="jobs_last_explore_status",
        excluded_key="jobs_explore_excluded_expanded",
    )


def _background_refresh_state(
    experience: JobsPageExperience,
    profile_id: str,
    feed_kind: FeedKind,
    *,
    sector: str | None = None,
) -> BackgroundRefreshSnapshot | None:
    getter = getattr(experience, "refresh_state", None)
    if not callable(getter):
        return None
    return getter(profile_id, feed_kind, sector=sector)


def _refresh_is_running(
    experience: JobsPageExperience,
    profile_id: str,
    feed_kind: FeedKind,
    *,
    sector: str | None = None,
) -> bool:
    snapshot = _background_refresh_state(
        experience, profile_id, feed_kind, sector=sector
    )
    return snapshot is not None and snapshot.status is BackgroundRefreshStatus.RUNNING


def _render_refresh_snapshot(
    streamlit_module: Any,
    snapshot: BackgroundRefreshSnapshot | None,
    *,
    timestamp_key: str,
    status_key: str,
    excluded_key: str,
) -> None:
    if snapshot is None:
        last_refresh = streamlit_module.session_state.get(timestamp_key)
        if last_refresh is not None:
            streamlit_module.caption(_refresh_copy(last_refresh))
        return
    if snapshot.status is BackgroundRefreshStatus.RUNNING:
        streamlit_module.caption("Refreshing jobs... Existing recommendations remain available.")
        return
    handled = streamlit_module.session_state.setdefault("jobs_refresh_handled_tokens", {})
    if handled.get(snapshot.key) != snapshot.token:
        handled[snapshot.key] = snapshot.token
        if snapshot.status is BackgroundRefreshStatus.SUCCEEDED:
            streamlit_module.session_state[timestamp_key] = _refresh_timestamp(snapshot.result)
            streamlit_module.session_state[status_key] = _refresh_status(snapshot.result)
            streamlit_module.session_state[excluded_key] = False
            run = getattr(snapshot.result, "run", None)
            run_status = getattr(getattr(run, "status", None), "value", "")
            if run_status == "failed_all_sources":
                streamlit_module.session_state[status_key] = "Refresh failed"
            else:
                streamlit_module.toast(
                    "Job recommendations refreshed.", icon=":material/check:"
                )
        else:
            streamlit_module.session_state[status_key] = "Refresh failed"
        streamlit_module.rerun()
    if snapshot.status is BackgroundRefreshStatus.FAILED:
        streamlit_module.warning(snapshot.error_message or "Job refresh failed.")
        return
    if streamlit_module.session_state.get(status_key) == "Refresh failed":
        streamlit_module.warning(
            "Job sources could not be refreshed. Previously stored recommendations "
            "remain available."
        )
        return
    streamlit_module.caption(_refresh_copy(streamlit_module.session_state.get(timestamp_key)))


def _refresh_tailored(
    experience: JobsPageExperience, profile_id: str, streamlit_module: Any
) -> None:
    try:
        with streamlit_module.spinner("Refreshing approved job sources..."):
            result = experience.refresh_tailored(profile_id)
        streamlit_module.session_state["jobs_last_tailored_refresh"] = _refresh_timestamp(result)
        streamlit_module.session_state["jobs_last_tailored_status"] = _refresh_status(result)
        streamlit_module.session_state["jobs_tailored_excluded_expanded"] = False
    except Exception:
        streamlit_module.error(
            "Recommendations could not be refreshed. Previously stored results were preserved."
        )


def _render_section_heading(streamlit_module: Any, title: str, helper: str) -> None:
    streamlit_module.subheader(title)
    streamlit_module.caption(helper)


def _render_filter_row(
    streamlit_module: Any,
    chips: list[tuple[str, str]],
    summary: str,
) -> None:
    rendered = "".join(
        f'<span class="jobs-filter-chip" title="{escape(label)}">{escape(value)}</span>'
        for label, value in chips
    )
    summary_markup = f'<span class="jobs-filter-summary">{escape(summary)}</span>'
    streamlit_module.markdown(
        f'<div class="jobs-filter-row">{rendered}{summary_markup}</div>',
        unsafe_allow_html=True,
    )


def _render_sort_note(streamlit_module: Any, copy: str) -> None:
    streamlit_module.markdown(
        f'<div class="jobs-sort-note">{escape(copy)}</div>', unsafe_allow_html=True
    )


def _render_empty_state(
    streamlit_module: Any,
    title: str,
    message: str,
    *,
    action_label: str | None,
    action_key: str,
) -> None:
    with streamlit_module.container(border=True, key="jobs-empty-state"):
        streamlit_module.subheader(title)
        streamlit_module.write(message)
        if action_label:
            if streamlit_module.button(action_label, key=action_key, type="primary"):
                if action_key == "jobs-open-master-profile":
                    streamlit_module.session_state["app_pending_page"] = "Career Profile"
                    streamlit_module.rerun()
                if action_key == "jobs-open-preferences":
                    streamlit_module.session_state["jobs_pending_section"] = "Preferences"
                    streamlit_module.rerun()


def _render_list_section(
    streamlit_module: Any,
    title: str,
    values: Any,
    css_class: str,
) -> None:
    items = [str(value) for value in values] or ["Unavailable."]
    rendered = "".join(f"<li>{escape(value)}</li>" for value in items)
    streamlit_module.markdown(
        f'<div class="jobs-detail-section"><h4>{escape(title)}</h4>'
        f'<ul class="{css_class}">{rendered}</ul></div>',
        unsafe_allow_html=True,
    )


def _format_refresh(value: Any) -> str:
    if value is None:
        return "Never refreshed"
    if isinstance(value, datetime):
        return value.astimezone().strftime("%b %d at %I:%M %p").replace(" 0", " ")
    if isinstance(value, str):
        return escape(value.replace("_", " ").capitalize())
    return "Completed"


def _refresh_copy(value: Any) -> str:
    formatted = _format_refresh(value)
    return formatted if formatted == "Never refreshed" else f"Last refreshed {formatted}"


def _refresh_timestamp(result: Any) -> Any:
    feed = getattr(result, "feed", None)
    timestamp = getattr(feed, "last_refresh_at", None)
    return timestamp if isinstance(timestamp, datetime) else datetime.now().astimezone()


def _refresh_status(result: Any) -> str:
    run = getattr(result, "run", None)
    return _human_status(getattr(run, "status", None))


def _human_status(value: Any) -> str:
    if value is None:
        return "Ready"
    if isinstance(value, str):
        return value.replace("_", " ").capitalize()
    return "Completed"


def _human_source_warning(value: Any) -> str:
    text = str(value).strip()
    if " could not refresh — showing previous results." in text:
        return text
    if "|" in text:
        parts = text.split("|", 3)
        source = parts[0].replace("-", " ").strip().title() or "One source"
        message = parts[-1].strip().rstrip(".")
        return f"{source} reported an issue — {message}."
    if ": Provider" in text or ": Source" in text:
        source = text.split(":", 1)[0].replace("-", " ").strip().title()
        return f"{source} could not refresh — showing previous results where available."
    return text


def _clear_profile_state(state: MutableMapping[str, object]) -> None:
    for key in (
        "jobs_tailored_selected_job_id",
        "jobs_explore_selected_job_id",
        "jobs_preference_suggestion",
        "jobs_preference_draft",
        "jobs_confirmed_preferences",
        "jobs_tailored_excluded_expanded",
        "jobs_explore_excluded_expanded",
        "jobs_last_tailored_refresh",
        "jobs_last_explore_refresh",
        "jobs-pref-role-families",
        "jobs-pref-target-titles",
        "jobs-pref-related-titles",
        "jobs-pref-themes",
        "jobs-pref-interests",
        "jobs-pref-levels",
        "jobs-pref-locations",
        "jobs-pref-arrangement",
        "jobs-pref-arrangement-mode",
        "jobs-pref-authorization",
        "jobs-pref-max-age",
        "jobs-pref-preferred-companies",
        "jobs-pref-excluded-companies",
    ):
        state.pop(key, None)
    for key in tuple(state):
        if key.startswith("jobs-visible-window-"):
            state.pop(key, None)
    clear_browse_state(state)


def _browse_now(experience: JobsPageExperience) -> datetime:
    now = getattr(experience, "now", None)
    return now() if callable(now) else datetime.now(UTC)


def _project_feed(feed: FeedView, visible: list[Any]) -> FeedView:
    if hasattr(feed, "model_copy"):
        return feed.model_copy(update={"visible": visible})
    if is_dataclass(feed):
        return replace(feed, visible=visible)
    raise TypeError("Feed view must support model_copy or dataclass replacement")


def _safe_key(value: str) -> str:
    return "".join(
        character if character.isalnum() or character in "-_" else "-" for character in value
    )


def _locations(preferences: Any) -> str:
    values = [getattr(location, "raw", "") for location in getattr(preferences, "locations", [])]
    return ", ".join(value for value in values if value) or "not set"


def _levels(preferences: Any) -> str:
    values = [
        getattr(level, "value", str(level)) for level in getattr(preferences, "job_levels", [])
    ]
    return ", ".join(values) or "not set"


__all__ = ["apply_tailoring_handoff", "jobs_css", "render_jobs_page"]
