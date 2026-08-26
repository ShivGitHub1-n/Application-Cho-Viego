from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from resume_tailor.application.job_discovery.experience import (
    FeedView,
    JobDetailView,
    RecommendationView,
)
from resume_tailor.application.job_discovery.presentation import (
    normalize_job_description_for_display,
)
from resume_tailor.domain.job_discovery.models import EligibilityStatus, FitGrade

_GRADE_LABELS = {
    FitGrade.EXCELLENT: "Excellent",
    FitGrade.GOOD: "Good",
    FitGrade.WEAK: "Weak",
    FitGrade.DONT_MATCH: "Don’t Match",
}

_GRADE_DESCRIPTIONS = {
    FitGrade.EXCELLENT: "Strong alignment",
    FitGrade.GOOD: "Solid alignment",
    FitGrade.WEAK: "Limited alignment",
    FitGrade.DONT_MATCH: "Material conflict or insufficient fit",
}


def eligibility_indicator_markup(eligibility: EligibilityStatus) -> str:
    """Render the shared, non-interactive eligibility indicator."""

    label = eligibility.value.title()
    state = eligibility.value
    return (
        f'<span class="jobs-eligibility-indicator jobs-eligibility--{state}" '
        f'role="status" aria-label="Eligibility: {label}">'
        '<span class="jobs-eligibility-dot" aria-hidden="true"></span>'
        f'<span class="jobs-eligibility-label">{label}</span></span>'
    )


def fit_grade_meter_markup(
    grade: FitGrade,
    *,
    eligibility: EligibilityStatus | None = None,
    provisional: bool = False,
) -> str:
    """Render the one display-only custom component used by Jobs."""

    del eligibility, provisional
    active = {
        FitGrade.EXCELLENT: 3,
        FitGrade.GOOD: 2,
        FitGrade.WEAK: 1,
        FitGrade.DONT_MATCH: 0,
    }[grade]
    label = _GRADE_LABELS[grade]
    bars = "".join(
        '<span class="jobs-fit-bar '
        f"{'jobs-fit-bar--active' if index < active else 'jobs-fit-bar--inactive'}"
        '" aria-hidden="true"></span>'
        for index in range(3)
    )
    return (
        f'<div class="jobs-fit-meter" role="img" aria-label="Fit grade: {label}, '
        f'{active} of 3 bars"><span class="jobs-fit-bars">{bars}</span>'
        f'<span class="jobs-fit-label">{label}</span>'
        f'<span class="jobs-fit-description">{_GRADE_DESCRIPTIONS[grade]}</span></div>'
    )


def render_feed(
    feed: FeedView,
    *,
    selected_job_id: str | None,
    selected_key: str,
    selection_scope: str,
    streamlit_module: Any,
    on_select: Callable[[str], None],
    on_save: Callable[[str], None],
    on_tailor: Callable[[str], None],
    on_cover_letter: Callable[[str], None],
    get_detail: Callable[[str], JobDetailView | None],
    expanded_excluded: bool,
    excluded: Sequence[RecommendationView],
    on_toggle_excluded: Callable[[], Sequence[RecommendationView] | None],
    base_visible_count: int | None = None,
) -> str | None:
    """Render Tailored and Explore with native containers and controls."""

    visible = list(feed.visible)
    if visible and selected_job_id not in {item.job_id for item in visible}:
        selected_job_id = visible[0].job_id
        on_select(selected_job_id)
    if not visible:
        _render_empty_feed(
            streamlit_module,
            feed,
            no_match=base_visible_count is not None and base_visible_count > 0,
        )
        _render_excluded_results(
            feed.excluded_count,
            expanded_excluded,
            excluded,
            selected_key,
            streamlit_module,
            on_toggle_excluded,
        )
        return None

    left, right = streamlit_module.columns([0.38, 0.62], gap="large")
    with left:
        streamlit_module.subheader("Recommendations")
        streamlit_module.caption("Choose a role; its details stay visible beside the list.")
        with streamlit_module.container(
            height=680,
            border=False,
            key=f"jobs-results-scroll-{_safe_key(selection_scope)}",
        ):
            for item in visible:
                if _render_card(
                    item,
                    selected=item.job_id == selected_job_id,
                    selection_scope=selection_scope,
                    streamlit_module=streamlit_module,
                    on_select=on_select,
                ):
                    selected_job_id = item.job_id
            _render_excluded_results(
                feed.excluded_count,
                expanded_excluded,
                excluded,
                selected_key,
                streamlit_module,
                on_toggle_excluded,
            )

    with right:
        selected = next((item for item in visible if item.job_id == selected_job_id), None)
        if selected is not None:
            _render_detail(
                selected,
                get_detail(selected.job_id),
                streamlit_module=streamlit_module,
                on_save=on_save,
                on_tailor=on_tailor,
                on_cover_letter=on_cover_letter,
                selection_scope=selection_scope,
            )
    return selected_job_id


def _render_card(
    item: RecommendationView,
    *,
    selected: bool,
    selection_scope: str,
    streamlit_module: Any,
    on_select: Callable[[str], None],
) -> bool:
    with streamlit_module.container(
        border=True,
        key=f"jobs-card-{selection_scope}-{_safe_key(item.job_id)}",
    ):
        content, grade = streamlit_module.columns([3, 1], gap="small")
        with content:
            streamlit_module.markdown(f"**{item.title}**")
            streamlit_module.caption(item.company)
            streamlit_module.caption(
                f"{item.location_label} · {item.work_arrangement.value.title()} · "
                f"{item.posting_age_label}"
            )
            streamlit_module.caption(f"{item.first_seen_label} · {item.checked_label}")
        with grade:
            streamlit_module.markdown(fit_grade_meter_markup(item.grade), unsafe_allow_html=True)
        status, action = streamlit_module.columns([2, 1], vertical_alignment="bottom")
        with status:
            streamlit_module.markdown(
                eligibility_indicator_markup(item.eligibility), unsafe_allow_html=True
            )
            if item.provisional:
                streamlit_module.caption("Provisional · needs review")
        with action:
            if selected:
                streamlit_module.markdown(
                    '<span class="jobs-card-selected-marker" aria-hidden="true"></span>'
                    '<span class="jobs-selected-label">Selected</span>',
                    unsafe_allow_html=True,
                )
        streamlit_module.button(
            f"View {item.title} details",
            key=recommendation_selection_key(selection_scope, item.job_id),
            type="tertiary",
            width="stretch",
            on_click=on_select,
            args=(item.job_id,),
        )
    return False


def _render_excluded_results(
    excluded_count: int,
    expanded: bool,
    excluded: Sequence[RecommendationView],
    selected_key: str,
    streamlit_module: Any,
    on_toggle_excluded: Callable[[], Sequence[RecommendationView] | None],
) -> None:
    if not excluded_count:
        return
    label = (
        f"Hide excluded jobs ({excluded_count})"
        if expanded
        else f"Show excluded jobs ({excluded_count})"
    )
    if streamlit_module.button(label, key=f"{selected_key}-excluded-toggle"):
        updated = on_toggle_excluded()
        expanded = not expanded
        if updated is not None:
            excluded = updated
    if expanded:
        streamlit_module.caption("Excluded from the normal feed")
        for item in excluded:
            with streamlit_module.container(
                border=True, key=f"jobs-excluded-card-{_safe_key(item.job_id)}"
            ):
                streamlit_module.markdown(f"**{item.title}**")
                streamlit_module.caption(item.company)
                streamlit_module.markdown(
                    fit_grade_meter_markup(item.grade), unsafe_allow_html=True
                )
                streamlit_module.markdown(
                    eligibility_indicator_markup(item.eligibility), unsafe_allow_html=True
                )
                _render_list(
                    streamlit_module,
                    "Why excluded",
                    [*item.reasons, *item.gaps, *item.unresolved_facts],
                )
                if item.official_url:
                    streamlit_module.link_button("Open official posting", item.official_url)


def _render_detail(
    item: RecommendationView,
    detail: JobDetailView | None,
    *,
    streamlit_module: Any,
    on_save: Callable[[str], None],
    on_tailor: Callable[[str], None],
    on_cover_letter: Callable[[str], None],
    selection_scope: str,
) -> None:
    with streamlit_module.container(border=True, key="jobs-detail-panel"):
        streamlit_module.subheader(item.title)
        if _meaningful_detail_value(item.company):
            streamlit_module.caption(item.company)
        job_metadata = _join_meaningful(
            item.location_label,
            item.work_arrangement.value.title(),
            item.posting_age_label,
        )
        if job_metadata:
            streamlit_module.caption(job_metadata)
        timing = _join_meaningful(item.first_seen_label, item.checked_label)
        if timing:
            streamlit_module.caption(timing)
        fit, status = streamlit_module.columns([1, 1], gap="medium")
        with fit:
            streamlit_module.markdown(fit_grade_meter_markup(item.grade), unsafe_allow_html=True)
        with status:
            streamlit_module.markdown(
                eligibility_indicator_markup(item.eligibility), unsafe_allow_html=True
            )
        with streamlit_module.container(key="jobs-action-row"):
            actions = streamlit_module.columns(4, gap="small")
            with actions[0]:
                if item.official_url:
                    streamlit_module.link_button("Open posting", item.official_url, width="content")
            with actions[1]:
                if (
                    streamlit_module.button(
                        "Saved" if item.saved else "Save job",
                        key=f"jobs-save-{selection_scope}-{_safe_key(item.job_id)}",
                        disabled=item.saved,
                        width="content",
                    )
                    and not item.saved
                ):
                    on_save(item.job_id)
                    streamlit_module.toast("Saved to your jobs.", icon=":material/bookmark_added:")
                    streamlit_module.rerun()
            with actions[2]:
                if streamlit_module.button(
                    "Tailor resume",
                    key=f"jobs-tailor-{selection_scope}-{_safe_key(item.job_id)}",
                    type="primary",
                    width="content",
                ):
                    on_tailor(item.job_id)
            with actions[3]:
                if streamlit_module.button(
                    "Create cover letter",
                    key=f"jobs-cover-{selection_scope}-{_safe_key(item.job_id)}",
                    width="content",
                ):
                    on_cover_letter(item.job_id)
        streamlit_module.divider()
        _render_list(streamlit_module, "Why it fits", item.reasons)
        _render_list(streamlit_module, "Skills to strengthen", item.gaps)
        if detail is not None:
            with streamlit_module.expander("Full job description", expanded=False):
                streamlit_module.write(
                    normalize_job_description_for_display(detail.description)
                )
        with streamlit_module.expander("Evidence behind this fit", expanded=False):
            _render_list(streamlit_module, "Supporting profile evidence", item.supporting_evidence)
        with streamlit_module.expander("Advanced fit details", expanded=False):
            streamlit_module.caption(
                f"Verification: {item.verification_status.value.replace('_', ' ').title()} · "
                f"Freshness: {item.freshness_label}"
            )
            if item.provisional:
                streamlit_module.caption(
                    "Provisional result; important posting details need review."
                )
            source = _join_meaningful(
                f"Source: {item.source_company}",
                f"Confidence: {item.verification_confidence.value.title()}",
            )
            if source:
                streamlit_module.caption(source)
            _render_list(streamlit_module, "Unresolved facts", item.unresolved_facts)


def _render_list(streamlit_module: Any, title: str, values: Sequence[str]) -> None:
    cleaned = _unique_meaningful(values)
    if not cleaned:
        return
    streamlit_module.markdown(f"#### {title}")
    streamlit_module.markdown("\n".join(f"- {value}" for value in cleaned))


def _join_meaningful(*values: str) -> str:
    return " · ".join(value.strip() for value in values if _meaningful_detail_value(value))


def _unique_meaningful(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        normalized = " ".join(text.casefold().split())
        if not _meaningful_detail_value(text) or normalized in seen:
            continue
        seen.add(normalized)
        result.append(text)
    return result


def _meaningful_detail_value(value: str) -> bool:
    normalized = " ".join(str(value).strip().casefold().split())
    return normalized not in {
        "",
        "-",
        "unknown",
        "unknown company",
        "unknown location",
        "unknown arrangement",
        "unknown posting age",
        "posting age unknown",
        "first seen unknown",
        "not checked recently",
        "freshness unknown",
        "unavailable",
        "unavailable.",
    }


def _render_empty_feed(
    streamlit_module: Any, feed: FeedView, *, no_match: bool = False
) -> None:
    excluded_count = feed.excluded_count
    never_loaded = feed.status is None and feed.last_refresh_at is None
    refresh_failed = feed.status in {"failed", "failed_all_sources"}
    with streamlit_module.container(border=True, key="jobs-feed-empty-state"):
        streamlit_module.subheader(
            "No jobs match your search and filters."
            if no_match
            else "All retrieved jobs were excluded"
            if excluded_count
            else "Recommendations have not been loaded"
            if never_loaded
            else "Recommendations could not be refreshed"
            if refresh_failed
            else "No recommendations found"
        )
        streamlit_module.write(
            "Use Clear all or adjust the search and filters."
            if no_match
            else "Expand excluded results when you want to review them."
            if excluded_count
            else "Refresh this feed to retrieve recommendations from approved sources."
            if never_loaded
            else "Previously stored recommendations remain safe. Try refreshing again later."
            if refresh_failed
            else "The latest successful refresh returned no matching roles."
        )


def _safe_key(value: str) -> str:
    return "".join(
        character if character.isalnum() or character in "-_" else "-" for character in value
    )


def recommendation_selection_key(selection_scope: str, job_id: str) -> str:
    """Return the native full-card action key for one recommendation context."""

    return f"jobs-card-action-{_safe_key(selection_scope)}-{_safe_key(job_id)}"


__all__ = [
    "eligibility_indicator_markup",
    "fit_grade_meter_markup",
    "recommendation_selection_key",
    "render_feed",
]
