from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from streamlit.testing.v1 import AppTest

from resume_tailor.frontend.jobs_page import _windowed_recommendations

HARNESS = Path(__file__).parent / "streamlit_apps" / "jobs_test_app.py"
APP = Path(__file__).parents[1] / "src" / "resume_tailor" / "frontend" / "app.py"


def test_large_job_feed_renders_a_bounded_window_and_keeps_selected_result() -> None:
    items = [SimpleNamespace(job_id=f"job-{index}") for index in range(60)]

    first_window = _windowed_recommendations(items, 24, None)
    selected_window = _windowed_recommendations(items, 24, "job-45")

    assert [item.job_id for item in first_window] == [f"job-{index}" for index in range(24)]
    assert len(selected_window) == 25
    assert selected_window[-1].job_id == "job-45"


def test_offline_jobs_harness_renders_only_the_jobs_workspace() -> None:
    app = AppTest.from_file(str(HARNESS)).run()

    assert app.exception == []
    assert any(item.value == "Jobs" for item in app.title)
    assert app.pills(key="jobs-active-section").options == [
        "Tailored for you",
        "Explore sectors",
        "Saved",
        "Preferences",
    ]
    assert not any("profile-fit score" in item.value.lower() for item in app.markdown)
    assert any(expander.label == "Evidence behind this fit" for expander in app.expander)
    assert any("Material gaps" in item.value for item in app.warning)
    assert any("jobs-eligibility--unknown" in item.value for item in app.markdown)
    assert any("Provisional" in item.value for item in app.caption)


def test_jobs_header_uses_the_page_eleven_workspace_composition() -> None:
    app = AppTest.from_file(str(HARNESS)).run()

    assert not any(item.value == "Job discovery" for item in app.subheader)
    assert not any(item.label == "Reviewed profile" for item in app.selectbox)
    assert any(item.label == "Active profile" for item in app.selectbox)


def test_visual_acceptance_fixture_keeps_a_senior_result_populated() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    app.button(key="jobs-filter-toggle-tailored").click().run()
    app.multiselect(key="jobs-filter-seniority-tailored").set_value(["Senior"]).run()

    assert any("1 of 3 jobs" in item.value for item in app.caption)


def test_offline_jobs_harness_selection_uses_contextual_keys_and_persists() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    assert app.session_state["jobs_tailored_selected_job_id"] == "excellent-1"
    assert any("jobs-card-selected-marker" in item.value for item in app.markdown)
    good = app.button(key="jobs-card-action-tailored-profile-1-good-1")
    assert good.label == "View Good Role details"
    good.click().run()

    assert app.exception == []
    assert app.session_state["jobs_tailored_selected_job_id"] == "good-1"
    assert any(item.value == "Good Role" for item in app.subheader)
    assert any("jobs-eligibility--unknown" in item.value for item in app.markdown)
    assert any("Provisional" in item.value for item in app.caption)
    app.button(key="jobs-card-action-tailored-profile-1-weak-1").click().run().run()
    assert app.session_state["jobs_tailored_selected_job_id"] == "weak-1"
    assert any(item.value == "Weak Role" for item in app.subheader)
    app.button(key="jobs-card-action-tailored-profile-1-excellent-1").click().run()
    assert app.session_state["jobs_tailored_selected_job_id"] == "excellent-1"
    assert not any(item.label.startswith("Select ") for item in app.button)


def test_jobs_database_unavailable_is_presented_without_a_traceback() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    app.selectbox(key="offline-scenario-selector").set_value("database-unavailable").run()

    assert app.exception == []
    assert any(item.value == "Jobs is temporarily unavailable" for item in app.subheader)
    assert any(item.label == "Retry Jobs" for item in app.button)


def test_jobs_profile_selection_updates_the_canonical_profile_id() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    app.selectbox(key="jobs-profile-selector").set_value("profile-2").run()

    assert app.session_state["jobs_profile_id"] == "profile-2"
    assert app.session_state["profile_id"] == "profile-2"


def test_offline_discovered_handoff_defers_navigation_until_the_next_run() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    app.button(key="jobs-tailor-tailored-profile-1-excellent-1").click().run()

    assert app.exception == []
    assert app.session_state["app_active_page"] == "Resume Studio"
    assert "jobs_pending_page" not in app.session_state
    assert app.session_state["job_title_input"] == "Tailored Role"
    assert app.session_state["job_description_input"] == "Tailoring description."
    assert app.session_state["profile_id"] == "profile-1"


def test_offline_refresh_uses_human_status_and_keeps_shell_subordinate_scenario() -> None:
    app = AppTest.from_file(str(HARNESS)).run()

    assert any(item.label == "Offline scenario" for item in app.selectbox)
    app.button(key="jobs-refresh-tailored").click().run()

    rendered = [item.value for item in app.markdown] + [item.value for item in app.caption]
    assert not any("OfflineRun(" in value or "status='completed'" in value for value in rendered)
    assert any("Last refreshed" in value for value in rendered)
    assert app.session_state["app_active_page"] == "Jobs"


def test_offline_jobs_harness_expands_excluded_results_only_after_click() -> None:
    app = AppTest.from_file(str(HARNESS)).run()

    assert not any("Don’t Match Role" in item.value for item in app.markdown)
    disclosure = next(item for item in app.button if "Show excluded jobs" in item.label)
    disclosure.click().run()

    assert any("Don’t Match Role" in item.value for item in app.markdown)


def test_offline_jobs_harness_switches_to_explore_without_copying_tailored_selection() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    app.pills(key="jobs-active-section").set_value("Explore sectors").run()

    assert app.pills(key="jobs-active-section").value == "Explore sectors"
    assert app.selectbox(key="jobs-explore-sector").label == "Explore sector"
    assert not any("Tailored selected detail" in item.value for item in app.markdown)


def test_production_router_selects_jobs_without_rendering_resume_body() -> None:
    app = AppTest.from_file(str(APP)).run(timeout=30)
    app.button(key="pw-route-sidebar-jobs").click().run(timeout=30)

    assert app.exception == []
    assert any(item.value == "Jobs" for item in app.title)
    assert not any("Structured master-profile editor" in item.value for item in app.header)


def test_offline_harness_exercises_preference_suggestion_and_saved_availability() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    scenario = next(item for item in app.selectbox if item.label == "Offline scenario")
    scenario.set_value("preference-suggestion").run()
    app.pills(key="jobs-active-section").set_value("Preferences").run()
    next(item for item in app.button if item.label == "Suggest preferences").click().run()

    assert any("Suggestion" in item.value for item in app.info)

    scenario = next(item for item in app.selectbox if item.label == "Offline scenario")
    scenario.set_value("saved-unavailable").run()
    app.pills(key="jobs-active-section").set_value("Saved").run()

    assert any("Unavailable posting retained" in item.value for item in app.warning)
    assert any(item.label == "Check availability" for item in app.button)


def test_offline_harness_all_documented_scenarios_start_without_exception() -> None:
    scenarios = [
        "visible-grades",
        "excluded-results",
        "partial-source-warning",
        "all-sources-failure",
        "no-reviewed-profile",
        "no-confirmed-preferences",
        "no-visible-results",
        "saved-available",
        "saved-unavailable",
        "preference-suggestion",
        "tailoring-handoff",
        "long-content",
    ]
    for scenario_name in scenarios:
        app = AppTest.from_file(str(HARNESS)).run()
        scenario = next(item for item in app.selectbox if item.label == "Offline scenario")
        scenario.set_value(scenario_name).run()
        assert app.exception == [], scenario_name


def test_jobs_surfaces_sanitized_source_and_sector_no_match_diagnostics() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    scenario = next(item for item in app.selectbox if item.label == "Offline scenario")
    scenario.set_value("partial-source-warning").run()

    assert any(
        item.value == "One approved source returned a partial response."
        for item in app.warning
    )

    scenario = next(item for item in app.selectbox if item.label == "Offline scenario")
    scenario.set_value("no-visible-results").run()
    app.pills(key="jobs-active-section").set_value("Explore sectors").run()

    assert any(item.value == "Explore returned no roles" for item in app.subheader)
    assert any(
        item.value == "No sector roles matched the approved retrieval boundary."
        for item in app.markdown
    )


def test_jobs_empty_actions_use_safe_pending_navigation_intents() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    scenario = next(item for item in app.selectbox if item.label == "Offline scenario")
    scenario.set_value("no-reviewed-profile").run()

    assert app.button(key="jobs-open-master-profile").label == "Open Career Profile"
    app.button(key="jobs-open-master-profile").click().run()
    assert app.session_state["app_active_page"] == "Career Profile"

    app = AppTest.from_file(str(HARNESS)).run()
    scenario = next(item for item in app.selectbox if item.label == "Offline scenario")
    scenario.set_value("no-confirmed-preferences").run()
    app.button(key="jobs-open-preferences").click().run()

    assert app.pills(key="jobs-active-section").value == "Preferences"


def test_jobs_structure_uses_integrated_cards_and_one_detail_panel() -> None:
    app = AppTest.from_file(str(HARNESS)).run()

    assert not any(item.key == "jobs-select-excellent-1" for item in app.button)
    assert (
        app.button(key="jobs-card-action-tailored-profile-1-good-1").label
        == "View Good Role details"
    )
    assert not any(item.label.startswith("Select ") for item in app.button)
    assert any(item.value == "Excellent Role" for item in app.subheader)
    assert any(item.label == "Tailor resume" for item in app.button)
    assert not any("OfflineRun(" in item.value for item in app.markdown)


def test_application_shell_uses_native_navigation_without_radio_widgets() -> None:
    app = AppTest.from_file(str(APP)).run(timeout=30)

    labels = [item.label for item in app.button]
    assert "Career Profile" in labels
    assert "Jobs" in labels
    assert "Resume Studio" in labels
    assert "Cover Letters" in labels
    assert not any(item.key == "app_active_page" for item in app.pills)
    assert app.radio == []


def test_saved_uses_same_card_detail_and_grouped_action_structure() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    scenario = next(item for item in app.selectbox if item.label == "Offline scenario")
    scenario.set_value("saved-available").run()
    app.pills(key="jobs-active-section").set_value("Saved").run()

    assert any("Saved immutable snapshot" in item.value for item in app.caption)
    assert not any(item.key == "jobs-select-saved-saved-1" for item in app.button)
    assert any(item.label == "Check availability" for item in app.button)
    assert any(item.label == "Tailor resume from snapshot" for item in app.button)


def test_offline_saved_handoff_defers_navigation_until_the_next_run() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    scenario = next(item for item in app.selectbox if item.label == "Offline scenario")
    scenario.set_value("saved-available").run()
    app.pills(key="jobs-active-section").set_value("Saved").run()
    app.button(key="jobs-tailor-saved-saved-1").click().run()

    assert app.exception == []
    assert app.session_state["app_active_page"] == "Resume Studio"
    assert "jobs_pending_page" not in app.session_state


def test_preferences_use_grouped_desktop_panels() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    app.pills(key="jobs-active-section").set_value("Preferences").run()
    app.button(key="jobs-suggest-preferences").click().run()

    markdown = [item.value for item in app.markdown]
    assert any("Role direction" in value for value in markdown)
    assert any("Skills and interests" in value for value in markdown)
    assert any("Work constraints" in value for value in markdown)
    assert any("Companies and authorization" in value for value in markdown)
    assert app.radio == []


def test_jobs_search_state_is_independent_between_tailored_and_explore() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    app.text_input(key="jobs-search-tailored").set_value("Good").run()

    app.pills(key="jobs-active-section").set_value("Explore sectors").run()

    assert app.text_input(key="jobs-search-explore").value == ""
    assert app.session_state["jobs-browse-state-tailored"].query == "Good"
    app.text_input(key="jobs-search-explore").set_value("does-not-exist").run()
    assert any(
        "No jobs match your search and filters." in item.value for item in app.subheader
    )

    app.pills(key="jobs-active-section").set_value("Tailored for you").run()
    assert app.text_input(key="jobs-search-tailored").value == "Good"
    assert any(item.value == "Good Role" for item in app.subheader)


def test_jobs_expanded_filter_panel_exposes_grouped_controls_and_reset() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    app.button(key="jobs-filter-toggle-tailored").click().run()

    assert app.multiselect(key="jobs-filter-seniority-tailored").options
    assert app.multiselect(key="jobs-filter-location-tailored").options == ["Toronto, ON"]
    assert app.multiselect(key="jobs-filter-arrangement-tailored").options
    assert app.selectbox(key="jobs-filter-date-tailored").options[-1] == "Any time"

    app.multiselect(key="jobs-filter-seniority-tailored").set_value(["Senior"]).run()
    assert any("Senior" in item.label for item in app.button if "jobs-chip-tailored" in item.key)
    app.button(key="jobs-clear-all-tailored").click().run()
    assert app.multiselect(key="jobs-filter-seniority-tailored").value == []


def test_saved_search_filters_snapshot_list_and_reports_filtered_count() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    app.selectbox(key="offline-scenario-selector").set_value("saved-available").run()
    app.pills(key="jobs-active-section").set_value("Saved").run()

    app.text_input(key="jobs-search-saved").set_value("immutable").run()

    assert any("1 of 1 saved snapshots" in item.value for item in app.caption)
    app.text_input(key="jobs-search-saved").set_value("missing").run()
    assert any(
        "No jobs match your search and filters." in item.value for item in app.subheader
    )


def test_explore_detail_stays_in_the_active_sector_after_switching() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    app.pills(key="jobs-active-section").set_value("Explore sectors").run()
    assert any(item.value == "Good Role" for item in app.subheader)

    sectors = app.selectbox(key="jobs-explore-sector").options
    alternate_sector = next(sector for sector in sectors if sector != "Software Engineering")
    app.selectbox(key="jobs-explore-sector").set_value(alternate_sector).run()

    assert app.session_state["jobs_selected_explore_sector"] == alternate_sector
    assert app.session_state["jobs_explore_selected_job_id"] == "weak-1"
    assert any(item.value == "Weak Role" for item in app.subheader)
    assert not any(item.value == "Good Role" for item in app.subheader)


def test_explore_filters_survive_sector_switch_without_selection_leak() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    app.pills(key="jobs-active-section").set_value("Explore sectors").run()
    app.button(key="jobs-filter-toggle-explore").click().run()
    app.multiselect(key="jobs-filter-seniority-explore").set_value(["Senior"]).run()
    app.text_input(key="jobs-search-explore").set_value("Good").run()

    sectors = app.selectbox(key="jobs-explore-sector").options
    alternate_sector = next(sector for sector in sectors if sector != "Software Engineering")
    app.selectbox(key="jobs-explore-sector").set_value(alternate_sector).run()

    assert app.text_input(key="jobs-search-explore").value == "Good"
    assert app.multiselect(key="jobs-filter-seniority-explore").value == ["Senior"]
    assert "jobs_explore_selected_job_id" not in app.session_state
    assert any(
        "No jobs match your search and filters." in item.value for item in app.subheader
    )


def test_profile_change_clears_profile_specific_browse_state() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    app.text_input(key="jobs-search-tailored").set_value("Good").run()
    app.selectbox(key="jobs-profile-selector").set_value("profile-2").run()

    assert app.text_input(key="jobs-search-tailored").value == ""
    assert app.session_state["jobs-browse-state-tailored"].query == ""
