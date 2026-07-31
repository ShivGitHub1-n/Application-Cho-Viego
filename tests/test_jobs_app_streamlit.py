from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

HARNESS = Path(__file__).parent / "streamlit_apps" / "jobs_test_app.py"
APP = Path(__file__).parents[1] / "src" / "resume_tailor" / "frontend" / "app.py"


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
    assert any("Exact supporting evidence" in item.value for item in app.markdown)
    assert any("Material gaps" in item.value for item in app.warning)
    assert any("jobs-eligibility--unknown" in item.value for item in app.markdown)
    assert any("Provisional" in item.value for item in app.caption)


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
    assert any(item.value == "Excellent Role" for item in app.subheader)
    assert not any(item.label.startswith("Select ") for item in app.button)


def test_offline_discovered_handoff_defers_navigation_until_the_next_run() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    app.button(key="jobs-tailor-tailored-profile-1-excellent-1").click().run()

    assert app.exception == []
    assert app.session_state["app_active_page"] == "Resume Tailor"
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
    assert app.pills(key="app_active_page").value == "Resume Tailor"


def test_offline_jobs_harness_expands_excluded_results_only_after_click() -> None:
    app = AppTest.from_file(str(HARNESS)).run()

    assert not any("Don’t Match Role" in item.value for item in app.markdown)
    disclosure = next(item for item in app.button if "Show excluded jobs" in item.label)
    disclosure.click().run()

    assert any("Don’t Match Role" in item.value for item in app.markdown)


def test_offline_jobs_harness_switches_to_explore_without_copying_tailored_selection() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    app.pills(key="jobs-active-section").set_value("Explore sectors").run()

    rendered = (
        [item.value for item in app.header]
        + [item.value for item in app.subheader]
        + [item.value for item in app.markdown]
    )
    assert any("Explore sectors" in item for item in rendered)
    assert not any("Tailored selected detail" in item.value for item in app.markdown)


def test_application_router_has_dedicated_jobs_stop_and_preserves_tailoring_keys() -> None:
    source = (
        Path(__file__).parents[1] / "src" / "resume_tailor" / "frontend" / "app.py"
    ).read_text(encoding="utf-8")

    assert "render_jobs_page" in source
    assert "st.stop()" in source
    assert '"Jobs"' in source
    assert 'key="job_title_input"' in source


def test_production_router_selects_jobs_without_rendering_resume_body() -> None:
    app = AppTest.from_file(str(APP)).run(timeout=30)
    app.pills(key="app_active_page").set_value("Jobs").run(timeout=30)

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

    assert app.pills(key="app_active_page").options == [
        "Jobs",
        "Resume Tailor",
        "Cover letters",
        "Master profile",
    ]
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
    assert app.session_state["app_active_page"] == "Resume Tailor"
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
