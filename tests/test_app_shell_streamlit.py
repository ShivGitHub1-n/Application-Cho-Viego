from pathlib import Path

from streamlit.testing.v1 import AppTest

from resume_tailor.frontend.routes import AppRoute

HARNESS = Path(__file__).parent / "streamlit_apps" / "shell_test_app.py"


def test_shell_defaults_to_career_profile_and_renders_all_workspace_routes() -> None:
    app = AppTest.from_file(str(HARNESS)).run()

    assert app.exception == []
    assert app.session_state["app_active_page"] == AppRoute.CAREER_PROFILE.value
    labels = [item.label for item in app.button]
    assert "Career Profile" in labels
    assert "Jobs" in labels
    assert "Resume Studio" in labels
    assert "Cover Letters" in labels


def test_shell_normalizes_pending_legacy_route_before_navigation_controls() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    app.session_state["jobs_pending_page"] = "Resume Tailor"
    app.run()

    assert app.exception == []
    assert app.session_state["app_active_page"] == AppRoute.RESUME_STUDIO.value
    assert "jobs_pending_page" not in app.session_state


def test_shell_consumes_both_pending_route_keys_with_current_key_precedence() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    app.session_state["app_pending_page"] = "Cover Letters"
    app.session_state["jobs_pending_page"] = "Resume Tailor"
    app.run()

    assert app.exception == []
    assert app.session_state["app_active_page"] == AppRoute.COVER_LETTERS.value
    assert "app_pending_page" not in app.session_state
    assert "jobs_pending_page" not in app.session_state


def test_shell_normalizes_invalid_pending_values_without_leaving_a_stale_intent() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    app.session_state["app_pending_page"] = "not a route"
    app.run()

    assert app.exception == []
    assert app.session_state["app_active_page"] == AppRoute.CAREER_PROFILE.value
    assert "app_pending_page" not in app.session_state


def test_shell_renders_active_profile_context_for_present_and_absent_profiles() -> None:
    app = AppTest.from_file(str(HARNESS)).run()
    assert any("Avery Engineer" in item.value for item in app.markdown)

    app.session_state["shell-test-active-profile"] = False
    app.run()

    assert any("Choose a reviewed profile" in item.value for item in app.markdown)
