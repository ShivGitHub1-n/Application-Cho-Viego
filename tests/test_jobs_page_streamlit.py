from __future__ import annotations

from resume_tailor.domain.job_discovery.models import EligibilityStatus, FitGrade
from resume_tailor.frontend.job_feed_view import (
    eligibility_indicator_markup,
    fit_grade_meter_markup,
    recommendation_selection_key,
)
from resume_tailor.frontend.jobs_page import apply_tailoring_handoff, jobs_css


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
        "job_description_input": "old description",
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
    assert state["cover_recipient_name"] == "Keep this"


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


def test_jobs_css_sizes_the_native_card_action_dom_chain() -> None:
    css = jobs_css()

    card = '[data-testid="stVerticalBlock"][class*="st-key-jobs-card-"]'
    action_container = '[data-testid="stElementContainer"][class*="st-key-jobs-card-action-"]'

    assert f"{card} {{" in css
    assert "position: relative;" in css
    assert f"{card} > {action_container} {{" in css
    assert "inset: 0;" in css
    assert "position: absolute;" in css
    assert "width: 100%;" in css
    assert "height: 100%;" in css
    assert f'{card} > {action_container} [data-testid="stButton"] {{' in css
    assert f'{card} > {action_container} [data-testid="stButton"] > button {{' in css
    assert "cursor: pointer;" in css
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


def test_jobs_css_uses_scoped_figma_tokens_and_selected_state_precedence() -> None:
    dark = jobs_css("dark")
    light = jobs_css("light")

    assert ".st-key-jobs-page {" in dark
    assert "--jobs-surface: #171B23;" in dark
    assert "--jobs-card-selected: #2B171B;" in dark
    assert "--jobs-accent: #FF2B2B;" in dark
    assert "--jobs-fit-inactive: #555A65;" in dark
    assert ".jobs-fit-bars { display: inline-flex; gap: .375rem; }" in dark
    assert "--jobs-surface: #FFFFFF;" in light
    assert "--jobs-card-selected: #FFF8F8;" in light
    assert "--jobs-accent: #FF4B4B;" in light
    assert "--jobs-fit-inactive: #D9DCE3;" in light

    card = '[data-testid="stVerticalBlock"][class*="st-key-jobs-card-"]'
    selected = f"{card}:has(.jobs-card-selected-marker)"
    selected_hover = f"{selected}:has(button:hover)"
    assert selected in dark
    assert selected_hover in dark
    assert dark.index(selected_hover) > dark.index(selected)
    assert "background: var(--jobs-card-selected) !important;" in dark
    assert "border-color: var(--jobs-accent) !important;" in dark
    assert "box-shadow:" in dark
    assert "body {" not in dark


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
    dark = jobs_css("dark")
    light = jobs_css("light")

    assert "--jobs-eligibility-eligible: #5CE488;" in dark
    assert "--jobs-eligibility-unknown: #FFBD45;" in dark
    assert "--jobs-eligibility-ineligible: #FF2B2B;" in dark
    assert "--jobs-eligibility-eligible: #2E7D32;" in light
    assert "--jobs-eligibility-unknown: #A06000;" in light
    assert "--jobs-eligibility-ineligible: #FF4B4B;" in light
    assert ".jobs-eligibility-dot" in dark
    assert "width: 7px;" in dark
    assert "height: 7px;" in dark

    inactive_hover = '.st-key-jobs-section-nav [data-variant="pills"]:hover'
    active = '.st-key-jobs-section-nav [data-variant="pills"][data-selected]'
    active_hover = active + ":hover"
    assert inactive_hover in dark
    assert active in dark
    assert active_hover in dark
    assert "display: flex;" in dark
    assert "flex: 0 0 auto;" in dark
    assert "gap: 1.25rem;" in dark
    assert dark.index(active) < dark.index(active_hover)
    assert "background: transparent !important;" in dark[dark.index(active_hover) :]
