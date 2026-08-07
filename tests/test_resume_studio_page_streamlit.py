from pathlib import Path

from streamlit.testing.v1 import AppTest

HARNESS = Path(__file__).parent / "streamlit_apps" / "resume_studio_test_app.py"
APP = Path(__file__).parents[1] / "src" / "resume_tailor" / "frontend" / "app.py"


def _prepare_job_context(app: AppTest) -> AppTest:
    app.session_state["job_title_input"] = "Embedded Firmware Engineer"
    app.session_state["job_description_input"] = "Build reliable embedded systems."
    app.session_state["_resume_studio_job_title_widget"] = "Embedded Firmware Engineer"
    app.session_state["_resume_studio_job_description_widget"] = "Build reliable embedded systems."
    return app.run()


def test_manual_resume_studio_session_starts_with_a_blank_job_title() -> None:
    app = AppTest.from_file(str(HARNESS)).run()

    assert app.exception == []
    assert app.text_input(key="_resume_studio_job_title_widget").value == ""


def test_resume_studio_starts_with_job_context_and_all_five_stages() -> None:
    app = AppTest.from_file(str(HARNESS)).run()

    assert app.exception == []
    assert any(item.value == "Resume Studio" for item in app.title)
    assert app.pills(key="_resume_studio_stage_widget").options == [
        "Job context",
        "Strategy",
        "Evidence selection",
        "Resume review",
        "Export",
    ]
    assert app.pills(key="_resume_studio_stage_widget").value == "Job context"
    assert any("using reviewed profile" in item.value.lower() for item in app.caption)


def test_resume_studio_stage_actions_progress_without_mutating_the_pills_key() -> None:
    app = _prepare_job_context(AppTest.from_file(str(HARNESS)).run())

    app.button(key="resume-create-strategy").click().run()
    assert app.exception == []
    assert app.session_state["resume_studio_stage"] == "Strategy"
    assert app.pills(key="_resume_studio_stage_widget").value == "Strategy"

    app.button(key="resume-to-evidence").click().run()
    assert app.session_state["resume_studio_stage"] == "Evidence selection"
    app.checkbox(key="_resume_evidence_approval_widget_plan-claim-1").set_value(True).run()
    app.button(key="resume-build-document").click().run()
    assert app.session_state["resume_studio_stage"] == "Resume review"

    app.checkbox(key="_resume_studio_review_confirmed_widget").set_value(True).run()
    app.button(key="resume-to-export").click().run()
    assert app.exception == []
    assert app.session_state["resume_studio_stage"] == "Export"
    assert app.session_state["resume_studio_review_confirmed"] is True


def test_resume_studio_preserves_pasted_context_and_review_confirmation_across_stages() -> None:
    app = _prepare_job_context(AppTest.from_file(str(HARNESS)).run())
    app.button(key="resume-create-strategy").click().run()
    app.button(key="resume-to-evidence").click().run()
    app.button(key="resume-build-document").click().run()
    app.checkbox(key="_resume_studio_review_confirmed_widget").set_value(True).run()
    app.button(key="resume-to-export").click().run()

    assert app.session_state["job_title_input"] == "Embedded Firmware Engineer"
    assert app.session_state["job_description_input"] == "Build reliable embedded systems."
    assert app.session_state["resume_studio_review_confirmed"] is True

    app.pills(key="_resume_studio_stage_widget").set_value("Job context").run()
    assert (
        app.text_input(key="_resume_studio_job_title_widget").value
        == "Embedded Firmware Engineer"
    )
    assert app.text_area(key="_resume_studio_job_description_widget").value == (
        "Build reliable embedded systems."
    )


def test_resume_approvals_survive_stage_revisits_until_explicitly_changed() -> None:
    app = _prepare_job_context(AppTest.from_file(str(HARNESS)).run())
    app.button(key="resume-create-strategy").click().run()
    app.button(key="resume-to-evidence").click().run()
    app.checkbox(key="_resume_evidence_approval_widget_plan-claim-1").set_value(True).run()
    app.session_state["resume-test-generated-pending"] = True
    app.button(key="resume-build-document").click().run()

    app.checkbox(key="_resume_generated_bullet_approval_widget_generated-bullet-1").set_value(True).run()
    app.checkbox(key="_resume_generated_skill_approval_widget_generated-skill-1").set_value(True).run()
    app.checkbox(key="_resume_studio_review_confirmed_widget").set_value(True).run()
    app.button(key="resume-to-export").click().run()
    app.button(key="resume-verify-export").click().run()

    assert app.session_state["resume_evidence_selection_ids"] == {"plan-claim-1"}
    assert app.session_state["resume_generated_approval_ids"] == {
        "generated-bullet-1",
        "generated-skill-1",
    }
    assert app.session_state["resume_studio_review_confirmed"] is True
    assert "resume_export_status" in app.session_state

    app.pills(key="_resume_studio_stage_widget").set_value("Evidence selection").run()
    assert app.checkbox(key="_resume_evidence_approval_widget_plan-claim-1").value is True
    assert "resume" in app.session_state
    assert "resume_export_status" in app.session_state

    app.pills(key="_resume_studio_stage_widget").set_value("Resume review").run()
    assert (
        app.checkbox(key="_resume_generated_bullet_approval_widget_generated-bullet-1").value
        is True
    )
    assert (
        app.checkbox(key="_resume_generated_skill_approval_widget_generated-skill-1").value
        is True
    )
    assert app.session_state["resume_studio_review_confirmed"] is True
    assert "resume_export_status" in app.session_state

    app.checkbox(key="_resume_generated_bullet_approval_widget_generated-bullet-1").set_value(False).run()
    assert "resume_export_status" not in app.session_state
    assert "resume_studio_review_confirmed" not in app.session_state


def test_jobs_handoff_context_is_the_first_resume_studio_context_and_survives_stages() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    app.session_state["_resume_studio_job_title_widget"] = "stale title"
    app.session_state["_resume_studio_job_description_widget"] = "stale description"
    app.session_state["resume-test-apply-handoff"] = True
    app.run()

    assert app.pills(key="_resume_studio_stage_widget").value == "Job context"
    assert (
        app.text_input(key="_resume_studio_job_title_widget").value
        == "Handoff Firmware Engineer"
    )
    assert app.text_area(key="_resume_studio_job_description_widget").value == (
        "Build firmware from a selected reviewed Jobs posting."
    )
    app.button(key="resume-create-strategy").click().run()
    app.button(key="resume-to-evidence").click().run()
    assert app.session_state["job_title_input"] == "Handoff Firmware Engineer"
    assert app.session_state["job_description_input"] == (
        "Build firmware from a selected reviewed Jobs posting."
    )


def test_resume_studio_normalizes_a_stale_stage_before_rendering_widgets() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    app.session_state["resume_studio_stage"] = "Resume Tailor"
    app.run()

    assert app.exception == []
    assert app.pills(key="_resume_studio_stage_widget").value == "Job context"
    assert app.session_state["resume_studio_stage"] == "Job context"


def test_rebuilding_resume_with_changed_approvals_clears_stale_export_artifacts() -> None:
    app = _prepare_job_context(AppTest.from_file(str(HARNESS)).run())
    app.button(key="resume-create-strategy").click().run()
    app.button(key="resume-to-evidence").click().run()
    app.checkbox(key="_resume_evidence_approval_widget_plan-claim-1").set_value(True).run()
    app.button(key="resume-build-document").click().run()
    app.checkbox(key="_resume_studio_review_confirmed_widget").set_value(True).run()
    app.button(key="resume-to-export").click().run()
    app.button(key="resume-verify-export").click().run()

    assert "resume_export_status" in app.session_state
    assert app.download_button(key="resume-download-docx").label == "Download DOCX"

    app.pills(key="_resume_studio_stage_widget").set_value("Evidence selection").run()
    app.checkbox(key="_resume_evidence_approval_widget_plan-claim-1").set_value(False).run()
    app.button(key="resume-build-document").click().run()

    assert "resume_export_status" not in app.session_state
    assert "resume_export_docx" not in app.session_state
    assert app.download_button == []


def test_resume_studio_reports_unavailable_exact_verification_without_export_success() -> None:
    app = _prepare_job_context(AppTest.from_file(str(HARNESS)).run())
    app.button(key="resume-create-strategy").click().run()
    app.button(key="resume-to-evidence").click().run()
    app.button(key="resume-build-document").click().run()
    app.checkbox(key="_resume_studio_review_confirmed_widget").set_value(True).run()
    app.button(key="resume-to-export").click().run()
    app.session_state["resume-test-render-mode"] = "unavailable"
    app.button(key="resume-verify-export").click().run()

    assert "resume_export_status" not in app.session_state
    assert any("Exact page verification is unavailable" in item.value for item in app.error)


def test_resume_studio_invalidates_derived_state_when_posting_or_profile_changes() -> None:
    app = _prepare_job_context(AppTest.from_file(str(HARNESS)).run())
    app.button(key="resume-create-strategy").click().run()
    app.session_state["job_description_input"] = "A materially changed embedded posting."
    app.run()

    assert "plan" not in app.session_state
    assert app.session_state["resume_studio_stage"] == "Job context"

    app = _prepare_job_context(AppTest.from_file(str(HARNESS)).run())
    app.button(key="resume-create-strategy").click().run()
    app.session_state["profile"] = app.session_state["profile"].model_copy(
        update={"display_name": "Changed Candidate"}
    )
    app.run()

    assert "plan" not in app.session_state
    assert app.session_state["resume_studio_stage"] == "Job context"


def test_production_router_reaches_resume_studio_without_generating_a_plan() -> None:
    app = AppTest.from_file(str(APP)).run(timeout=30)
    app.button(key="pw-route-sidebar-resume_studio").click().run(timeout=30)

    assert app.exception == []
    assert app.session_state["app_active_page"] == "Resume Studio"
    assert "plan" not in app.session_state
    assert app.pills(key="_resume_studio_stage_widget").value == "Job context"
