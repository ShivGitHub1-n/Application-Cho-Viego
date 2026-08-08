from pathlib import Path

from streamlit.testing.v1 import AppTest

HARNESS = Path(__file__).parent / "streamlit_apps" / "cover_letters_test_app.py"
APP = Path(__file__).parents[1] / "src" / "resume_tailor" / "frontend" / "app.py"


def _generate(app: AppTest) -> AppTest:
    app.button(key="cover-generate-draft").click().run()
    assert app.exception == []
    return app


def test_cover_letters_requires_an_explicit_decision_for_every_pending_claim() -> None:
    app = _generate(AppTest.from_file(str(HARNESS)).run())
    app.checkbox(key="cover_letter_reviewed").set_value(True).run()

    assert app.button(key="cover-confirm-review").disabled is True
    assert app.session_state["cover_letter_claim_decisions"] == {}


def test_cover_letters_all_approve_permits_confirmation_without_touching_resume_approvals() -> None:
    app = _generate(AppTest.from_file(str(HARNESS)).run())
    app.session_state["resume_approved_claim_ids"] = {"resume-claim"}
    app.selectbox(key="_cover_claim_decision_widget_claim-1").set_value("Approve").run()
    app.selectbox(key="_cover_claim_decision_widget_claim-2").set_value("Approve").run()
    app.checkbox(key="cover_letter_reviewed").set_value(True).run()

    assert app.button(key="cover-confirm-review").disabled is False
    app.button(key="cover-confirm-review").click().run()

    assert app.session_state["cover-letter-approved-ids"] == {"claim-1", "claim-2"}
    assert app.session_state["resume_approved_claim_ids"] == {"resume-claim"}


def test_cover_letters_mixed_approval_and_exclusion_permits_confirmation() -> None:
    app = _generate(AppTest.from_file(str(HARNESS)).run())
    app.selectbox(key="_cover_claim_decision_widget_claim-1").set_value("Approve").run()
    app.selectbox(key="_cover_claim_decision_widget_claim-2").set_value("Exclude").run()
    app.checkbox(key="cover_letter_reviewed").set_value(True).run()
    app.button(key="cover-confirm-review").click().run()

    assert app.exception == []
    assert app.session_state["cover-letter-approved-ids"] == {"claim-1"}


def test_regenerating_a_cover_letter_removes_old_export_and_requires_new_review() -> None:
    app = _generate(AppTest.from_file(str(HARNESS)).run())
    for claim_id in ("claim-1", "claim-2"):
        app.selectbox(key=f"_cover_claim_decision_widget_{claim_id}").set_value("Approve").run()
    app.checkbox(key="cover_letter_reviewed").set_value(True).run()
    app.button(key="cover-confirm-review").click().run()
    app.button(key="cover-verify-export").click().run()

    assert "cover_export_status" in app.session_state
    assert app.download_button(key="cover-download-docx").label == "Download cover-letter DOCX"

    app.button(key="cover-generate-draft").click().run()

    assert "cover_export_status" not in app.session_state
    assert "cover_export_docx" not in app.session_state
    assert app.download_button == []
    assert app.button(key="cover-verify-export").disabled is True


def test_recipient_context_change_invalidates_cover_letter_and_export_authority() -> None:
    app = _generate(AppTest.from_file(str(HARNESS)).run())
    for claim_id in ("claim-1", "claim-2"):
        app.selectbox(key=f"_cover_claim_decision_widget_{claim_id}").set_value("Approve").run()
    app.checkbox(key="cover_letter_reviewed").set_value(True).run()
    app.button(key="cover-confirm-review").click().run()
    app.button(key="cover-verify-export").click().run()

    app.text_input(key="cover_recipient_company").set_value("Changed Company").run()

    assert "cover_letter" not in app.session_state
    assert "cover_export_status" not in app.session_state
    assert "cover_letter_claim_decisions" not in app.session_state
    assert app.download_button == []


def test_cover_letters_report_unavailable_exact_verification_without_export_success() -> None:
    app = _generate(AppTest.from_file(str(HARNESS)).run())
    for claim_id in ("claim-1", "claim-2"):
        app.selectbox(key=f"_cover_claim_decision_widget_{claim_id}").set_value("Approve").run()
    app.checkbox(key="cover_letter_reviewed").set_value(True).run()
    app.button(key="cover-confirm-review").click().run()
    app.session_state["cover-test-export-mode"] = "unavailable"
    app.button(key="cover-verify-export").click().run()

    assert "cover_export_status" not in app.session_state
    assert any("Exact page verification is unavailable" in item.value for item in app.error)


def test_production_router_reaches_cover_letters_without_creating_a_draft() -> None:
    app = AppTest.from_file(str(APP)).run(timeout=30)
    app.button(key="pw-route-sidebar-cover_letters").click().run(timeout=30)

    assert app.exception == []
    assert app.session_state["app_active_page"] == "Cover Letters"
    assert "cover_letter" not in app.session_state
