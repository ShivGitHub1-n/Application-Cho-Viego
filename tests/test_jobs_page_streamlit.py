from __future__ import annotations

import inspect

from resume_tailor.domain.job_discovery.models import EligibilityStatus, FitGrade
from resume_tailor.frontend.job_feed_view import (
    eligibility_indicator_markup,
    fit_grade_meter_markup,
    recommendation_selection_key,
)
from resume_tailor.frontend.jobs_page import (
    JobsPageExperience,
    apply_tailoring_handoff,
    jobs_css,
)


def test_fit_grade_meter_maps_each_grade_without_numeric_score() -> None:
    expected = {
        FitGrade.EXCELLENT: 3,
        FitGrade.GOOD: 2,
        FitGrade.WEAK: 1,
        FitGrade.DONT_MATCH: 0,
    }
    labels = {
        FitGrade.EXCELLENT: "Excellent",
        FitGrade.GOOD: "Good",
        FitGrade.WEAK: "Weak",
        FitGrade.DONT_MATCH: "Don’t Match",
    }

    for grade, active_count in expected.items():
        markup = fit_grade_meter_markup(grade)
        assert markup.count("jobs-fit-bar--active") == active_count
        assert markup.count("jobs-fit-bar--inactive") == 3 - active_count
        assert f"Fit grade: {labels[grade]}" in markup
        assert "score" not in markup.lower()


def test_fit_meter_keeps_grade_independent_from_eligibility_and_provisional() -> None:
    markup = fit_grade_meter_markup(
        FitGrade.GOOD,
        eligibility=EligibilityStatus.UNKNOWN,
        provisional=True,
    )

    assert markup.count("jobs-fit-bar--active") == 2
    assert "Good" in markup
    assert "Unknown" not in markup
    assert "Provisional" not in markup


def test_tailoring_handoff_sets_existing_inputs_and_only_invalidates_derived_state() -> None:
    state: dict[str, object] = {
        "profile_id": "profile-old",
        "profile": type("Profile", (), {"id": "profile-old"})(),
        "job_description_input": "old description",
        "_resume_studio_job_title_widget": "old title widget",
        "_resume_studio_job_description_widget": "old description widget",
        "resume_studio_stage": "Export",
        "cover_recipient_name": "Keep this",
        "plan": "stale plan",
        "resume": "stale resume",
    }
    handoff = type(
        "Handoff",
        (),
        {
            "profile_id": "profile-new",
            "title": "Embedded Firmware Engineer",
            "description": "Build reliable firmware.",
        },
    )()

    apply_tailoring_handoff(state, handoff)

    assert state["profile_id"] == "profile-new"
    assert state["job_title_input"] == "Embedded Firmware Engineer"
    assert state["job_description_input"] == "Build reliable firmware."
    assert "plan" not in state
    assert "resume" not in state
    assert "profile" not in state
    assert state["cover_recipient_name"] == "Keep this"
    assert state["app_pending_page"] == "Resume Studio"
    assert "_resume_studio_job_title_widget" not in state
    assert "_resume_studio_job_description_widget" not in state
    assert state["resume_studio_pending_stage"] == "Job context"


def test_jobs_css_is_limited_to_scoped_jobs_enhancements() -> None:
    css = jobs_css()

    assert ".st-key-jobs-page" in css
    assert ".jobs-filter-chip" in css
    assert "22px" in css or "1.375rem" in css
    assert "--jobs-accent" in css
    assert "body {" not in css
    assert "<script" not in css.lower()
    assert "javascript" not in css.lower()
    assert "light-dark" not in css
    assert "color-scheme" not in css


def test_jobs_css_keeps_fit_meter_and_overflow_helpers_scoped() -> None:
    css = jobs_css()

    assert "jobs-fit-bar--active" in css
    assert "jobs-fit-bar--inactive" in css
    assert "overflow-wrap: anywhere" in css
    assert "height: 0;" not in css


def test_jobs_css_keeps_figma_palette_scoped_to_jobs_without_replacing_shell() -> None:
    css = jobs_css().lower()

    assert "_dark_jobs_palette" not in css
    assert "--jobs-surface" in css
    assert ".st-key-app-shell" not in css
    assert ".st-key-jobs-page" in css
    assert "st-emotion-cache" not in css


def test_recommendation_selection_keys_are_context_safe() -> None:
    keys = {
        recommendation_selection_key("tailored-profile-1", "same-job"),
        recommendation_selection_key("explore-profile-1-sector-a", "same-job"),
        recommendation_selection_key("explore-profile-1-sector-b", "same-job"),
        recommendation_selection_key("tailored-profile-2", "same-job"),
        recommendation_selection_key("tailored-profile-1", "excluded-same-job"),
    }

    assert len(keys) == 5
    assert all(key.startswith("jobs-card-action-") for key in keys)


def test_jobs_css_targets_the_visible_selected_card_container() -> None:
    css = jobs_css()

    selected_card = (
        '[data-testid="stVerticalBlock"][class*="st-key-jobs-card-"]'
        ":has(.jobs-card-selected-marker)"
    )
    assert selected_card in css
    assert "background: var(--jobs-card-selected) !important;" in css
    assert "border-color: var(--jobs-accent) !important;" in css
    assert "box-shadow:" in css
    assert "var(--jobs-selected-glow)" in css


def test_jobs_css_keeps_the_native_card_action_as_a_full_card_focusable_target() -> None:
    css = jobs_css()

    card = '[data-testid="stVerticalBlock"][class*="st-key-jobs-card-"]'
    action_container = '[data-testid="stElementContainer"][class*="st-key-jobs-card-action-"]'

    assert f"{card} {{" in css
    assert "position: relative;" in css
    assert f"{card} > {action_container} {{" in css
    assert "inset: 0;" in css
    assert "position: absolute;" in css
    assert "width: 100%;" in css
    assert f'{card} > {action_container} [data-testid="stButton"] {{' in css
    assert f'{card} > {action_container} [data-testid="stButton"] > button {{' in css
    assert "height: 100%;" in css
    assert "opacity: 0;" in css
    assert f"{card}:has(button:focus-visible)" in css
    assert "pointer-events: none" not in css
    assert "<script" not in css.lower()
    assert "javascript" not in css.lower()


def test_jobs_css_covers_the_keyed_visual_surfaces_and_responsive_layout() -> None:
    css = jobs_css()

    assert '.st-key-jobs-detail-panel[data-testid="stVerticalBlock"]' in css
    assert '.st-key-jobs-saved-detail-panel[data-testid="stVerticalBlock"]' in css
    assert '.st-key-jobs-section-nav [data-testid="stButtonGroup"]' in css
    assert '.st-key-jobs-preference-editor > [data-testid="stElementContainer"]' in css
    assert "@media (max-width: 900px)" in css
    assert '[data-testid="stColumn"]' in css
    assert "height: 7px;" in css
    assert "width: 22px;" in css
    assert "var(--jobs-surface-secondary)" in css
    assert "body" not in css


def test_jobs_css_matches_page_eleven_browse_surface_geometry() -> None:
    css = jobs_css()

    assert '[data-testid="stTextInput"] input' in css
    assert "min-height: 2.625rem;" in css
    assert '[class*="st-key-jobs-filter-panel-"]' in css
    assert "border-radius: 12px;" in css
    assert '[class*="st-key-jobs-chip-"] button' in css
    assert "border-radius: 999px;" in css


def test_jobs_css_uses_shared_semantic_tokens_and_selected_state_precedence() -> None:
    css = jobs_css()

    assert ".st-key-jobs-page {" in css
    assert "--jobs-surface: var(--pw-surface);" in css
    assert "--jobs-card-selected: color-mix(in srgb, var(--pw-state-info)" in css
    assert "--jobs-accent: var(--pw-state-info);" in css
    assert "--jobs-fit-inactive: var(--pw-border-strong);" in css
    assert ".jobs-fit-bars { display: inline-flex; gap: .375rem; }" in css
    assert "#FF2B2B" not in css
    assert "#FF4B4B" not in css

    card = '[data-testid="stVerticalBlock"][class*="st-key-jobs-card-"]'
    selected = f"{card}:has(.jobs-card-selected-marker)"
    selected_hover = f"{selected}:has(button:hover)"
    assert selected in css
    assert selected_hover in css
    assert css.index(selected_hover) > css.index(selected)
    assert "background: var(--jobs-card-selected) !important;" in css
    assert "border-color: var(--jobs-accent) !important;" in css
    assert "body {" not in css


def test_eligibility_indicator_uses_shared_semantic_markup() -> None:
    expected = {
        EligibilityStatus.ELIGIBLE: "eligible",
        EligibilityStatus.UNKNOWN: "unknown",
        EligibilityStatus.INELIGIBLE: "ineligible",
    }

    for status, css_state in expected.items():
        markup = eligibility_indicator_markup(status)
        assert f'jobs-eligibility--{css_state}' in markup
        assert 'class="jobs-eligibility-dot"' in markup
        assert status.value.title() in markup
        assert "FitGrade" not in markup
        assert "Provisional" not in markup


def test_jobs_css_defines_navigation_precedence_and_eligibility_tokens() -> None:
    css = jobs_css()

    assert "--jobs-eligibility-eligible: var(--pw-state-positive);" in css
    assert "--jobs-eligibility-unknown: var(--pw-state-review);" in css
    assert "--jobs-eligibility-ineligible: var(--pw-state-critical);" in css
    assert ".jobs-eligibility-dot" in css
    assert "width: 7px;" in css
    assert "height: 7px;" in css

    inactive_hover = '.st-key-jobs-section-nav [data-variant="pills"]:hover'
    active = '.st-key-jobs-section-nav [data-variant="pills"][data-selected]'
    active_hover = active + ":hover"
    assert inactive_hover in css
    assert active in css
    assert active_hover in css
    assert "display: flex;" in css
    assert "flex: 0 0 auto;" in css
    assert "gap: 1.25rem;" in css
    assert css.index(active) < css.index(active_hover)
    assert "background: transparent !important;" in css[css.index(active_hover) :]


def test_explore_detail_contract_accepts_sector_scope() -> None:
    parameters = inspect.signature(JobsPageExperience.get_job_detail).parameters

    assert "sector" in parameters
    assert parameters["sector"].kind is inspect.Parameter.KEYWORD_ONLY
