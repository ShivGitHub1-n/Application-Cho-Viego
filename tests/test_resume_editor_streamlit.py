from pathlib import Path

from streamlit.testing.v1 import AppTest

HARNESS = Path(__file__).parent / "streamlit_apps" / "resume_editor_test_app.py"


def _app(*, preview_pages: int = 1) -> AppTest:
    app = AppTest.from_file(str(HARNESS))
    app.session_state["editor-preview-pages"] = preview_pages
    app.run()
    assert not app.exception
    return app


def _open_section(app: AppTest, section: str) -> None:
    app.segmented_control[0].set_value(section).run()
    assert not app.exception


def test_editor_stages_typing_and_reordering_before_one_render() -> None:
    app = _app()
    assert app.session_state["editor-render-calls"] == 1
    _open_section(app, "experience")
    app.button(key="resume-editor-bullet-edit-experience-controls-bullet-firmware").click().run()
    assert app.session_state["editor-render-calls"] == 1
    app.text_area(
        key="resume-editor-bullet-text-experience-controls-bullet-firmware"
    ).input("Developed C++ STM32 control firmware for actuator feedback.")
    next(button for button in app.button if button.label == "Stage edit").click().run()
    assert app.session_state["editor-render-calls"] == 1
    assert any("Changes pending" in item.value for item in app.info)
    edited_id = app.session_state["resume_editor_workspaces"][
        app.session_state["resume_editor_active_context"]
    ]["staged_resume"].experience_bullets["experience-controls"][0].id
    app.button(
        key=f"resume-editor-bullet-down-experience-controls-{edited_id}"
    ).click().run()
    assert app.session_state["editor-render-calls"] == 1
    app.button(key="resume-editor-apply").click().run()
    assert app.session_state["editor-render-calls"] == 2
    assert not any("Changes pending" in item.value for item in app.info)


def test_editor_reuses_unchanged_preview_on_navigation_rerun() -> None:
    app = _app()
    assert app.session_state["editor-render-calls"] == 1
    app.run()
    assert app.session_state["editor-render-calls"] == 1


def test_editor_is_collapsed_by_default_and_uses_browser_safe_preview() -> None:
    app = _app()
    assert app.segmented_control[0].value is None
    assert not any(
        button.key and button.key.startswith("resume-editor-bullet-edit-")
        for button in app.button
    )
    assert len(app.image) == 1
    assert any(button.label == "Download PDF preview" for button in app.download_button)
    app.run()
    assert app.session_state["editor-render-calls"] == 1


def test_overflow_preview_shows_every_exact_pdf_page() -> None:
    app = _app(preview_pages=2)
    assert len(app.image) == 2
    assert any("Exceeds one page" in markdown.value for markdown in app.markdown)
    assert any(button.label == "Download PDF preview" for button in app.download_button)


def test_staging_an_edit_invalidates_revision_approval_without_rendering() -> None:
    app = _app()
    context = app.session_state["resume_editor_active_context"]
    workspace = app.session_state["resume_editor_workspaces"][context]
    workspace["approved_revision_fingerprint"] = workspace[
        "applied_revision"
    ].revision_fingerprint
    app.session_state["resume_studio_review_confirmed"] = True
    _open_section(app, "experience")
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
    _open_section(app, "experience")
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


def test_explicit_experience_and_project_additions_stage_then_render_once() -> None:
    app = _app()
    _open_section(app, "experience")
    next(
        button
        for button in app.button
        if button.key and button.key.startswith("resume-editor-add-experience-")
    ).click().run()
    experience_evidence = next(
        widget
        for widget in app.multiselect
        if widget.key and widget.key.startswith("resume-editor-omitted-evidence-experience-")
    )
    experience_evidence.set_value(["evidence-lab"]).run()
    app.button(key="resume-editor-stage-entry-experience-experience-lab").click().run()
    context = app.session_state["resume_editor_active_context"]
    staged = app.session_state["resume_editor_workspaces"][context]["staged_resume"]
    assert staged.experiences[-1].id == "experience-lab"
    assert staged.experience_bullets["experience-lab"][0].evidence_ids == [
        "evidence-lab"
    ]
    assert app.session_state["editor-render-calls"] == 1
    # AppTest retains the prior conditional widget node for one event after the
    # production UI removes it; bridge that testing-only handoff explicitly.
    app.session_state[experience_evidence.key] = []

    _open_section(app, "projects")
    next(
        button
        for button in app.button
        if button.key and button.key.startswith("resume-editor-add-project-")
    ).click().run()
    project_evidence = next(
        widget
        for widget in app.multiselect
        if widget.key and widget.key.startswith("resume-editor-omitted-evidence-project-")
    )
    project_evidence.set_value(["evidence-arm"]).run()
    app.button(key="resume-editor-stage-entry-project-project-arm").click().run()
    staged = app.session_state["resume_editor_workspaces"][context]["staged_resume"]
    assert staged.projects[-1].id == "project-arm"
    assert staged.project_bullets["project-arm"][0].evidence_ids == ["evidence-arm"]
    assert app.session_state["editor-render-calls"] == 1

    app.button(key="resume-editor-apply").click().run()
    assert app.session_state["editor-render-calls"] == 2
