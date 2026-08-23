from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypeVar

from resume_tailor.application.job_discovery.filtering import (
    BrowseFilterChip,
    BrowseFilterState,
    BrowseSeniority,
    DatePostedWindow,
    active_filter_chips,
    available_locations,
)
from resume_tailor.domain.job_discovery.models import WorkArrangement

T = TypeVar("T")


@dataclass(frozen=True)
class BrowseControlsResult:
    state: BrowseFilterState
    filtered: list[Any]
    base_count: int


_SENIORITY_LABELS = {
    BrowseSeniority.INTERNSHIP: "Internship",
    BrowseSeniority.COOP: "Co-op",
    BrowseSeniority.NEW_GRAD: "New Grad",
    BrowseSeniority.JUNIOR: "Junior",
    BrowseSeniority.MID_LEVEL: "Mid-level",
    BrowseSeniority.SENIOR: "Senior",
    BrowseSeniority.LEAD: "Lead",
    BrowseSeniority.STAFF: "Staff",
    BrowseSeniority.PRINCIPAL: "Principal",
    BrowseSeniority.MANAGER: "Manager",
    BrowseSeniority.UNKNOWN: "Unknown",
}
_SENIORITY_BY_LABEL = {label: value for value, label in _SENIORITY_LABELS.items()}
_ARRANGEMENT_LABELS = {
    WorkArrangement.REMOTE: "Remote",
    WorkArrangement.HYBRID: "Hybrid",
    WorkArrangement.ONSITE: "On-site",
    WorkArrangement.UNKNOWN: "Unknown",
}
_ARRANGEMENT_BY_LABEL = {label: value for value, label in _ARRANGEMENT_LABELS.items()}
_DATE_LABELS = {
    DatePostedWindow.PAST_24_HOURS: "Past 24 hours",
    DatePostedWindow.PAST_3_DAYS: "Past 3 days",
    DatePostedWindow.PAST_WEEK: "Past week",
    DatePostedWindow.PAST_2_WEEKS: "Past 2 weeks",
    DatePostedWindow.PAST_MONTH: "Past month",
    DatePostedWindow.ANY_TIME: "Any time",
}
_DATE_BY_LABEL = {label: value for value, label in _DATE_LABELS.items()}


def render_browse_controls(
    streamlit_module: Any,
    *,
    section: str,
    items: Sequence[T],
    filter_items: Callable[..., list[T]],
    now: datetime,
    result_noun: str = "jobs",
) -> BrowseControlsResult:
    """Render one section-local search/filter surface and return its projection."""

    _initialize_widget_state(streamlit_module, section)
    search_col, filter_col, count_col = streamlit_module.columns(
        [5.8, 1, 1], gap="small", vertical_alignment="center"
    )
    with search_col:
        streamlit_module.text_input(
            "Search jobs or companies",
            key=f"jobs-search-{section}",
            placeholder="Search jobs or companies...",
            label_visibility="collapsed",
        )
    with filter_col:
        active_count = _active_filter_count(streamlit_module, section)
        if streamlit_module.button(
            "Filters" + (f" · {active_count}" if active_count else ""),
            key=f"jobs-filter-toggle-{section}",
            width="stretch",
        ):
            toggle_key = f"jobs-filter-open-{section}"
            streamlit_module.session_state[toggle_key] = not bool(
                streamlit_module.session_state.get(toggle_key, False)
            )
    with count_col:
        with streamlit_module.container(key=f"jobs-result-count-{section}"):
            count_slot = streamlit_module.empty()

    if streamlit_module.session_state.get(f"jobs-filter-open-{section}", False):
        with streamlit_module.container(border=True, key=f"jobs-filter-panel-{section}"):
            streamlit_module.caption("FILTERS")
            seniority_col, location_col, arrangement_col, date_col = streamlit_module.columns(
                4, gap="medium"
            )
            with seniority_col:
                streamlit_module.multiselect(
                    "Seniority",
                    list(_SENIORITY_BY_LABEL),
                    key=f"jobs-filter-seniority-{section}",
                )
            with location_col:
                streamlit_module.multiselect(
                    "Location",
                    available_locations(items),
                    key=f"jobs-filter-location-{section}",
                    placeholder="Search loaded locations...",
                )
            with arrangement_col:
                streamlit_module.multiselect(
                    "Work arrangement",
                    list(_ARRANGEMENT_BY_LABEL),
                    key=f"jobs-filter-arrangement-{section}",
                )
            with date_col:
                streamlit_module.selectbox(
                    "Date posted",
                    list(_DATE_BY_LABEL),
                    key=f"jobs-filter-date-{section}",
                )

    state = _read_filter_state(streamlit_module, section)
    filtered = filter_items(items, state, now=now)
    count_slot.caption(f"{len(filtered)} of {len(items)} {result_noun}")
    _render_active_chips(streamlit_module, section, state)
    return BrowseControlsResult(state=state, filtered=filtered, base_count=len(items))


def clear_browse_state(
    state: Any, *, sections: Sequence[str] = ("tailored", "explore", "saved")
) -> None:
    """Clear profile-specific widget state before the next section widgets render."""

    for section in sections:
        for suffix in (
            "search",
            "filter-seniority",
            "filter-location",
            "filter-arrangement",
            "filter-date",
        ):
            state.pop(f"jobs-{suffix}-{section}", None)
        state.pop(f"jobs-filter-open-{section}", None)
        state.pop(f"jobs-browse-state-{section}", None)


def _initialize_widget_state(streamlit_module: Any, section: str) -> None:
    state = streamlit_module.session_state
    saved = state.get(f"jobs-browse-state-{section}", BrowseFilterState())
    state.setdefault(f"jobs-search-{section}", saved.query)
    state.setdefault(
        f"jobs-filter-seniority-{section}",
        [_SENIORITY_LABELS[value] for value in saved.seniorities],
    )
    state.setdefault(f"jobs-filter-location-{section}", list(saved.locations))
    state.setdefault(
        f"jobs-filter-arrangement-{section}",
        [_ARRANGEMENT_LABELS[value] for value in saved.arrangements],
    )
    state.setdefault(f"jobs-filter-date-{section}", _DATE_LABELS[saved.date_posted])
    state.setdefault(f"jobs-filter-open-{section}", False)


def _read_filter_state(streamlit_module: Any, section: str) -> BrowseFilterState:
    state = streamlit_module.session_state
    seniorities = frozenset(
        _SENIORITY_BY_LABEL[label]
        for label in state.get(f"jobs-filter-seniority-{section}", [])
        if label in _SENIORITY_BY_LABEL
    )
    arrangements = frozenset(
        _ARRANGEMENT_BY_LABEL[label]
        for label in state.get(f"jobs-filter-arrangement-{section}", [])
        if label in _ARRANGEMENT_BY_LABEL
    )
    date_label = state.get(f"jobs-filter-date-{section}", "Any time")
    browse_state = BrowseFilterState(
        query=str(state.get(f"jobs-search-{section}", "")),
        seniorities=seniorities,
        locations=frozenset(state.get(f"jobs-filter-location-{section}", [])),
        arrangements=arrangements,
        date_posted=_DATE_BY_LABEL.get(date_label, DatePostedWindow.ANY_TIME),
    )
    state[f"jobs-browse-state-{section}"] = browse_state
    return browse_state


def _active_filter_count(streamlit_module: Any, section: str) -> int:
    return len(active_filter_chips(_read_filter_state(streamlit_module, section)))


def _render_active_chips(streamlit_module: Any, section: str, state: BrowseFilterState) -> None:
    chips = active_filter_chips(state)
    if not chips:
        return
    with streamlit_module.container(key=f"jobs-active-filters-{section}"):
        for chip in chips:
            streamlit_module.button(
                f"{chip.label} ×",
                key=f"jobs-chip-{section}-{chip.group}-{_safe_key(chip.value)}",
                on_click=_remove_filter_widget_value,
                args=(streamlit_module.session_state, section, chip),
                width="content",
            )
        streamlit_module.button(
            "Clear all",
            key=f"jobs-clear-all-{section}",
            on_click=_clear_filter_widget_values,
            args=(streamlit_module.session_state, section),
            width="content",
        )


def _remove_filter_widget_value(state: Any, section: str, chip: BrowseFilterChip) -> None:
    if chip.group == "seniority":
        key = f"jobs-filter-seniority-{section}"
        state[key] = [value for value in state.get(key, []) if value != chip.label]
    elif chip.group == "location":
        key = f"jobs-filter-location-{section}"
        state[key] = [value for value in state.get(key, []) if value != chip.value]
    elif chip.group == "arrangement":
        key = f"jobs-filter-arrangement-{section}"
        state[key] = [value for value in state.get(key, []) if value != chip.label]
    elif chip.group == "date_posted":
        state[f"jobs-filter-date-{section}"] = "Any time"


def _clear_filter_widget_values(state: Any, section: str) -> None:
    state[f"jobs-filter-seniority-{section}"] = []
    state[f"jobs-filter-location-{section}"] = []
    state[f"jobs-filter-arrangement-{section}"] = []
    state[f"jobs-filter-date-{section}"] = "Any time"


def _safe_key(value: str) -> str:
    return "".join(
        character if character.isalnum() or character in "-_" else "-"
        for character in value
    )


__all__ = ["BrowseControlsResult", "clear_browse_state", "render_browse_controls"]
