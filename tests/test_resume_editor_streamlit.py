from pathlib import Path

from streamlit.testing.v1 import AppTest

HARNESS = Path(__file__).parent / "streamlit_apps" / "resume_editor_test_app.py"


def _app() -> AppTest:
    app = AppTest.from_file(str(HARNESS))
    app.run()
    assert not app.exception
    return app


def test_editor_stages_typing_and_reordering_before_one_render() -> None:
    app = _app()
    assert app.session_state["editor-render-calls"] == 1
    app.button(key="resume-editor-bullet-edit-experience-controls-bullet-firmware").click().run()
    assert app.session_state["editor-render-calls"] == 1
    app.text_area(
        key="resume-editor-bullet-text-experience-controls-bullet-firmware"
    ).input("Developed C++ STM32 control firmware for actuator feedback.")
    next(button for button in app.button if button.label == "Stage edit").click().run()
    assert app.session_state["editor-render-calls"] == 1
    edited_id = app.session_state["resume_editor_workspaces"][
        app.session_state["resume_editor_active_context"]
    ]["staged_resume"].experience_bullets["experience-controls"][0].id
    app.button(
        key=f"resume-editor-bullet-down-experience-controls-{edited_id}"
    ).click().run()
    assert app.session_state["editor-render-calls"] == 1
    app.button(key="resume-editor-apply").click().run()
    assert app.session_state["editor-render-calls"] == 2


def test_editor_reuses_unchanged_preview_on_navigation_rerun() -> None:
    app = _app()
    assert app.session_state["editor-render-calls"] == 1
    app.run()
    assert app.session_state["editor-render-calls"] == 1


def test_staging_an_edit_invalidates_revision_approval_without_rendering() -> None:
    app = _app()
    context = app.session_state["resume_editor_active_context"]
    workspace = app.session_state["resume_editor_workspaces"][context]
    workspace["approved_revision_fingerprint"] = workspace[
        "applied_revision"
    ].revision_fingerprint
    app.session_state["resume_studio_review_confirmed"] = True
    app.button(key="resume-editor-bullet-remove-experience-controls-bullet-wiring").click().run()
    assert app.session_state["resume_editor_workspaces"][context][
        "approved_revision_fingerprint"
    ] is None
    assert app.session_state["resume_studio_review_confirmed"] is False
    assert app.session_state["editor-render-calls"] == 1
    app.run()
    assert app.session_state["editor-render-calls"] == 1


def test_editor_state_is_isolated_and_restored_per_application() -> None:
    app = _app()
    context_a = app.session_state["resume_editor_active_context"]
    app.button(key="resume-editor-bullet-edit-experience-controls-bullet-firmware").click().run()
    app.text_area(
        key="resume-editor-bullet-text-experience-controls-bullet-firmware"
    ).input("Developed C++ STM32 control firmware for actuator feedback.")
    next(button for button in app.button if button.label == "Stage edit").click().run()
    staged_a = app.session_state["resume_editor_workspaces"][context_a]["staged_resume"]
    assert staged_a.experience_bullets["experience-controls"][0].text.startswith(
        "Developed C++"
    )

    app.selectbox(key="editor-application").select("Job B").run()
    context_b = app.session_state["resume_editor_active_context"]
    assert context_b != context_a
    staged_b = app.session_state["resume_editor_workspaces"][context_b]["staged_resume"]
    assert staged_b.experience_bullets["experience-controls"][0].text.startswith(
        "Developed STM32"
    )

    app.selectbox(key="editor-application").select("Job A").run()
    assert app.session_state["resume_editor_active_context"] == context_a
    restored_a = app.session_state["resume_editor_workspaces"][context_a]["staged_resume"]
    assert restored_a.experience_bullets["experience-controls"][0].text.startswith(
        "Developed C++"
    )
    assert app.session_state["editor-render-calls"] == 2
