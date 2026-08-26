import json
from copy import deepcopy
from pathlib import Path

from streamlit.testing.v1 import AppTest

from resume_tailor.frontend.profile_editor_view import (
    candidate_name_widget_key,
    editor_ui_identity,
    next_link_ui_id,
)

HARNESS = Path(__file__).parent / "streamlit_apps" / "profile_test_app.py"
APP = Path(__file__).parents[1] / "src" / "resume_tailor" / "frontend" / "app.py"


def test_career_profile_defaults_to_reviewed_document_without_persisting_edits() -> None:
    app = AppTest.from_file(str(HARNESS)).run()

    assert app.exception == []
    assert any(item.value == "Career Profile" for item in app.title)
    assert app.pills(key="profile-active-section").value == "Reviewed profile"
    assert app.session_state["profile-test-save-count"] == 0
    assert any("reviewed source of truth" in item.value.lower() for item in app.caption)
    assert app.session_state["profile_load_status"] != "Profile not loaded."
    page = "\n".join(item.value for item in app.markdown)
    assert "Example Institute" in page
    assert "Embedded Systems Intern" in page
    assert "Software Engineering Intern" in page
    assert "Research Assistant" in page
    assert "Engineering Assistant" in page
    assert "Sensor Platform" in page
    assert "Automation Challenge" in page
    assert "Digital Monitor" in page
    assert "Python, C++" in page
    assert "evidence-one" not in page
    assert app.text_area == []


def test_source_resume_surface_is_truthful_when_original_bytes_are_not_retained() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    saved_before = app.session_state["profile-test-save-count"]

    app.pills(key="profile-active-section").set_value("Source résumé").run()

    assert app.exception == []
    assert any(item.value == "Import or replace résumé" for item in app.subheader)
    assert any("current Career Profile stays unchanged" in item.value for item in app.caption)
    assert not any(
        "original uploaded résumé file was not retained" in item.value for item in app.info
    )
    assert any(
        item.label == "Upload résumé for extracted-profile review (.docx or text-based .pdf)"
        for item in app.file_uploader
    )
    assert not any("original résumé preview" in item.value.lower() for item in app.markdown)
    assert app.session_state["profile-test-save-count"] == saved_before


def test_reviewed_profile_uses_import_action_when_no_source_preview_exists() -> None:
    app = AppTest.from_file(str(HARNESS)).run()

    action = app.button(key="profile-source-action")
    assert action.label == "Import or replace résumé"
    action.click().run()

    assert app.pills(key="profile-active-section").value == "Source résumé"
    assert any(item.value == "Import or replace résumé" for item in app.subheader)


def test_switching_profile_surfaces_does_not_mutate_the_reviewed_profile() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    before = app.session_state["profile"].model_dump(mode="json")

    app.pills(key="profile-active-section").set_value("Source résumé").run()
    app.pills(key="profile-active-section").set_value("Edit profile").run()
    app.pills(key="profile-active-section").set_value("Reviewed profile").run()

    assert app.exception == []
    assert app.session_state["profile"].model_dump(mode="json") == before
    assert app.session_state["profile-test-save-count"] == 0


def test_career_profile_uses_reviewed_profile_selector_and_structured_subsections() -> None:
    app = AppTest.from_file(str(HARNESS)).run()

    assert app.pills(key="profile-active-section").value == "Reviewed profile"
    assert app.selectbox(key="profile-reviewed-selector").value == "profile-completeness-fixture"
    app.pills(key="profile-active-section").set_value("Edit profile").run()

    assert app.pills(key="profile-data-section").value == "Personal"
    assert app.pills(key="profile-active-section").value == "Edit profile"


def test_career_profile_edits_are_saved_only_after_explicit_confirmation() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    app.pills(key="profile-active-section").set_value("Edit profile").run()
    app.pills(key="profile-data-section").set_value("Personal").run()
    name_key = candidate_name_widget_key(app.session_state["profile_editor_source_key"])
    app.text_input(key=name_key).set_value("Avery Updated").run()

    assert app.session_state["profile-test-save-count"] == 0
    app.button(key="profile-save-edits").click().run()

    assert app.exception == []
    assert app.session_state["profile-test-save-count"] == 1
    assert app.session_state["profile"].display_name == "Avery Updated"


def test_career_profile_discard_restores_the_last_saved_profile() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    app.pills(key="profile-active-section").set_value("Edit profile").run()
    app.pills(key="profile-data-section").set_value("Personal").run()
    name_key = candidate_name_widget_key(app.session_state["profile_editor_source_key"])
    app.text_input(key=name_key).set_value("Temporary edit").run()
    app.button(key="profile-discard-edits").click().run()

    assert app.exception == []
    name_key = candidate_name_widget_key(app.session_state["profile_editor_source_key"])
    assert app.text_input(key=name_key).value == "Example Candidate"
    assert app.session_state["profile-test-save-count"] == 0


def test_career_profile_normalizes_a_stale_section_before_rendering_widgets() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    app.session_state["profile-active-section"] = "Master profile"
    app.run()

    assert app.exception == []
    assert app.pills(key="profile-active-section").value == "Reviewed profile"
    assert app.session_state["profile-active-section"] == "Reviewed profile"


def test_production_router_defaults_to_career_profile() -> None:
    app = AppTest.from_file(str(APP)).run(timeout=30)

    assert app.exception == []
    assert app.session_state["app_active_page"] == "Career Profile"
    assert any(item.value == "Career Profile" for item in app.title)


def test_no_profile_surface_loads_an_existing_profile_by_id() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    app.selectbox(key="profile-test-scenario").set_value("No profile").run()
    app.selectbox(key="profile-reviewed-selector").set_value("profile-existing").run()
    app.button(key="profile-reviewed-load").click().run()

    assert app.exception == []
    assert app.session_state["profile"].id == "profile-existing"
    assert "Loaded profile profile-existing" in app.session_state["profile_load_status"]


def test_no_profile_surface_reports_missing_profile_without_persisting() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    app.selectbox(key="profile-test-scenario").set_value("No profile").run()
    app.pills(key="profile-active-section").set_value("Advanced").run()
    app.text_input(key="profile-advanced-id").set_value("missing-profile").run()
    app.button(key="profile-advanced-load").click().run()

    assert app.exception == []
    assert "was not found" in app.session_state["profile_load_status"]
    assert app.session_state["profile-test-save-count"] == 0


def test_no_profile_advanced_tools_validate_raw_json_before_explicit_save() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    app.selectbox(key="profile-test-scenario").set_value("No profile").run()
    app.pills(key="profile-active-section").set_value("Advanced").run()
    app.text_area(key="profile-bootstrap-raw-json").set_value("not-json").run()
    app.button(key="profile-bootstrap-save").click().run()

    assert app.exception == []
    assert app.session_state["profile-test-save-count"] == 0
    assert any("Raw profile was not saved" in item.value for item in app.error)


def test_no_profile_advanced_tools_create_valid_raw_profile_only_on_save() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    app.selectbox(key="profile-test-scenario").set_value("No profile").run()
    app.pills(key="profile-active-section").set_value("Advanced").run()
    fixture_path = Path(__file__).parent / "fixtures" / "profile_completeness.json"
    raw_profile = json.loads(fixture_path.read_text(encoding="utf-8"))
    raw_profile["id"] = "profile-created"
    app.text_area(key="profile-bootstrap-raw-json").set_value(json.dumps(raw_profile)).run()

    assert app.session_state["profile-test-save-count"] == 0
    app.button(key="profile-bootstrap-save").click().run()

    assert app.exception == []
    assert app.session_state["profile-test-save-count"] == 1
    assert app.session_state["profile"].id == "profile-created"


def test_loaded_career_profile_can_switch_to_another_reviewed_profile() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    app.selectbox(key="profile-reviewed-selector").set_value("profile-existing").run()
    app.button(key="profile-reviewed-load").click().run()

    assert app.exception == []
    assert app.session_state["profile"].id == "profile-existing"
    assert app.session_state["profile"].display_name == "Second Candidate"
    assert "Loaded profile profile-existing" in app.session_state["profile_load_status"]


def test_career_profile_honors_jobs_selected_profile_identity() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    app.session_state["jobs_profile_id"] = "profile-existing"
    app.session_state["profile_id"] = "profile-existing"
    app.run()

    assert app.exception == []
    assert app.session_state["profile"].id == "profile-existing"
    assert app.session_state["jobs_profile_id"] == "profile-existing"


def test_candidate_name_widget_is_scoped_to_the_loaded_profile_source() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    first_key = candidate_name_widget_key(app.session_state["profile_editor_source_key"])
    app.pills(key="profile-active-section").set_value("Edit profile").run()
    app.pills(key="profile-data-section").set_value("Personal").run()
    app.text_input(key=first_key).set_value("Unsaved Profile A").run()

    app.pills(key="profile-active-section").set_value("Reviewed profile").run()
    app.selectbox(key="profile-reviewed-selector").set_value("profile-existing").run()
    app.button(key="profile-reviewed-load").click().run()
    app.pills(key="profile-active-section").set_value("Edit profile").run()
    app.pills(key="profile-data-section").set_value("Personal").run()
    second_key = candidate_name_widget_key(app.session_state["profile_editor_source_key"])

    assert second_key != first_key
    assert app.text_input(key=second_key).value == "Second Candidate"


def test_seeded_extracted_profile_draft_stays_local_until_explicit_save() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    app.selectbox(key="profile-test-scenario").set_value("Seed extracted draft").run()
    app.pills(key="profile-active-section").set_value("Source résumé").run()

    assert app.exception == []
    assert app.session_state["profile"].id == "profile-completeness-fixture"
    assert app.session_state["profile_extraction_draft"].profile.id == "draft-profile"
    assert app.session_state["profile-test-save-count"] == 0
    assert any("original uploaded file is not persisted" in item.value for item in app.warning)
    assert any("review-source.docx" in item.value for item in app.caption)

    app.pills(key="profile-active-section").set_value("Edit profile").run()
    app.pills(key="profile-data-section").set_value("Personal").run()
    draft_name_key = candidate_name_widget_key(app.session_state["profile_editor_source_key"])
    app.text_input(key=draft_name_key).set_value("Reviewed Draft Candidate").run()
    app.button(key="profile-save-edits").click().run()

    assert app.session_state["profile-test-save-count"] == 1
    assert app.session_state["profile"].id == "draft-profile"
    assert app.session_state["profile"].display_name == "Reviewed Draft Candidate"
    assert "profile_extraction_draft" not in app.session_state


def _first_labeled_widget(app: AppTest, label: str):
    for collection in (app.text_input, app.text_area):
        for widget in collection:
            if widget.label == label:
                return widget
    raise AssertionError(f"No widget found for {label!r}")


def test_structured_profile_editor_round_trips_supported_optional_fields() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    app.pills(key="profile-active-section").set_value("Edit profile").run()
    app.pills(key="profile-data-section").set_value("Education").run()
    _first_labeled_widget(app, "Minor or specialization").set_value("Computer engineering").run()
    _first_labeled_widget(app, "Relevant coursework").set_value("Controls, Signals").run()

    app.pills(key="profile-active-section").set_value("Edit profile").run()
    app.pills(key="profile-data-section").set_value("Experiences").run()
    _first_labeled_widget(app, "Subtitle").set_value("Platform team").run()
    _first_labeled_widget(app, "Technology label").set_value("Embedded platform").run()
    _first_labeled_widget(app, "Award or placement").set_value("Dean's list").run()

    app.pills(key="profile-active-section").set_value("Edit profile").run()
    app.pills(key="profile-data-section").set_value("Skills").run()
    _first_labeled_widget(app, "Top-level coursework").set_value("Controls, Signals").run()
    _first_labeled_widget(app, "Category source reference").set_value("profile://skills").run()
    _first_labeled_widget(app, "Skill source reference").set_value("profile://skills/c").run()
    app.session_state["profile_editor_state"]["skill_normalization_decisions"] = [
        {
            "action": "retain",
            "skill_value": "C",
            "source_category_id": "category-source",
            "retained_category_id": "category-retained",
            "reason": "Reviewed source category.",
        }
    ]
    app.button(key="profile-save-edits").click().run()

    profile = app.session_state["profile"]
    assert profile.education[0].minor_or_specialization == "Computer engineering"
    assert profile.education[0].relevant_coursework == ["Controls", "Signals"]
    assert profile.experiences[0].subtitle == "Platform team"
    assert profile.experiences[0].technology_label == "Embedded platform"
    assert profile.experiences[0].award_or_placement == "Dean's list"
    assert profile.coursework == ["Controls", "Signals"]
    assert profile.technical_skills[0].source_reference == "profile://skills"
    assert profile.technical_skills[0].skills[0].source_reference == "profile://skills/c"
    assert profile.skill_normalization_decisions[0].reason == "Reviewed source category."


def test_editor_ui_identities_survive_reorder_remove_and_add_after_remove() -> None:
    registry: dict[str, str] = {}
    first = {"school": "First"}
    second = {"school": "Second"}
    first_identity = editor_ui_identity(registry, "education", first)
    second_identity = editor_ui_identity(registry, "education", second)

    reordered = list(reversed(deepcopy([first, second])))
    assert [editor_ui_identity(registry, "education", record) for record in reordered] == [
        second_identity,
        first_identity,
    ]
    remaining = [second]
    replacement = {"school": "Replacement"}
    assert editor_ui_identity(registry, "education", remaining[0]) == second_identity
    assert editor_ui_identity(registry, "education", replacement) not in {
        first_identity,
        second_identity,
    }
    assert next_link_ui_id([{"id": "link-0"}, {"id": "link-2"}]) == "link-1"
