from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from resume_tailor.application.profile_editor import empty_profile_editor_state
from resume_tailor.application.services import TailorResumeService
from resume_tailor.domain.models import MasterProfile
from resume_tailor.frontend.state import (
    NAVIGATION_ITEMS,
    initialize_frontend_state,
    navigate_to,
    populate_profile_editor_state,
)
from resume_tailor.infrastructure import dependencies
from resume_tailor.infrastructure.job_sources.greenhouse import GreenhouseConnector
from resume_tailor.infrastructure.job_sources.lever import LeverConnector
from resume_tailor.infrastructure.optimization import (
    DeterministicResumeOptimizer,
    EvidenceBoundResumeWriter,
)
from resume_tailor.infrastructure.profile_repository import (
    SQLiteMasterProfileRepository,
)


def _app_path() -> Path:
    return Path(__file__).parents[1] / "src" / "resume_tailor" / "frontend" / "app.py"


def _configure_app_dependencies(monkeypatch, tmp_path: Path) -> None:
    repository = SQLiteMasterProfileRepository(tmp_path / "frontend.sqlite3")
    service = TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
    )
    monkeypatch.setattr(dependencies, "create_profile_repository", lambda: repository)
    monkeypatch.setattr(dependencies, "create_tailor_service", lambda: service)


def test_navigation_preserves_unrelated_session_state() -> None:
    state: dict[str, object] = {"draft_job_description": "Keep this draft."}

    initialize_frontend_state(state)
    navigate_to(state, "Profile")
    navigate_to(state, "Tailor Resume")

    assert state["active_page"] == "Tailor Resume"
    assert state["navigation_selection"] == "Tailor Resume"
    assert state["draft_job_description"] == "Keep this draft."


def test_successful_import_populates_visible_editor_state() -> None:
    state: dict[str, object] = {}
    profile = MasterProfile(
        id="imported-profile",
        user_id="imported-user",
        display_name="Reviewed Candidate",
        experiences=[
            {
                "id": "experience-1",
                "title": "Engineer",
                "kind": "experience",
                "location": "Toronto, Ontario, Canada",
            }
        ],
    )

    changed = populate_profile_editor_state(state, profile, "upload:resume.docx")

    assert changed is True
    assert state["profile_editor_state"]["display_name"] == "Reviewed Candidate"
    assert state["profile_editor_state"]["experiences"][0]["location"] == (
        "Toronto, Ontario, Canada"
    )
    assert "Reviewed Candidate" in state["profile_editor_raw_json"]


def test_blank_editor_contains_no_placeholder_facts() -> None:
    state = empty_profile_editor_state("blank-profile")

    assert state["display_name"] == ""
    assert state["contact"]["location"] == ""
    assert state["experiences"] == []
    assert state["projects"] == []


def test_every_major_workflow_is_reachable_and_state_survives(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure_app_dependencies(monkeypatch, tmp_path)
    app = AppTest.from_file(str(_app_path())).run()
    app.session_state["navigation-survival-sentinel"] = "preserved"

    for page in NAVIGATION_ITEMS:
        app.radio(key="navigation_selection").set_value(page).run()
        assert app.session_state["active_page"] == page
        assert app.session_state["navigation-survival-sentinel"] == "preserved"
        assert not app.exception


def test_job_search_sources_are_not_initialized_during_startup_or_other_pages(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure_app_dependencies(monkeypatch, tmp_path)
    calls = 0

    def unexpected_job_discovery_initialization():
        nonlocal calls
        calls += 1
        raise AssertionError("Job Search initialized outside its selected workflow.")

    monkeypatch.setattr(
        dependencies,
        "create_job_discovery_services",
        unexpected_job_discovery_initialization,
    )
    app = AppTest.from_file(str(_app_path())).run()

    for page in (
        "Home / Workspace",
        "Profile",
        "Tailor Resume",
        "Cover Letter",
        "Settings / Diagnostics",
        "Job Search",
    ):
        app.radio(key="navigation_selection").set_value(page).run()
        assert not app.exception

    assert calls == 0


def test_default_startup_needs_no_gemini_credentials(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure_app_dependencies(monkeypatch, tmp_path)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    app = AppTest.from_file(str(_app_path())).run()
    app.radio(key="navigation_selection").set_value("Settings / Diagnostics").run()

    assert not app.exception
    assert any("Gemini role classification: Disabled" in element.value for element in app.markdown)


def test_job_search_initialization_with_profile_does_not_call_sources(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("APPLICATION_VIEGO_DATA_DIR", str(tmp_path))
    repository = SQLiteMasterProfileRepository(tmp_path / "job-search.sqlite3")
    repository.save(
        MasterProfile(
            id="local-profile",
            user_id="local-user",
            display_name="Reviewed Candidate",
        )
    )
    service = TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
    )
    monkeypatch.setattr(dependencies, "create_profile_repository", lambda: repository)
    monkeypatch.setattr(dependencies, "create_tailor_service", lambda: service)

    def unexpected_source_call(*args, **kwargs):
        raise AssertionError("A job source was called during page initialization.")

    monkeypatch.setattr(GreenhouseConnector, "fetch", unexpected_source_call)
    monkeypatch.setattr(GreenhouseConnector, "check", unexpected_source_call)
    monkeypatch.setattr(LeverConnector, "fetch", unexpected_source_call)
    monkeypatch.setattr(LeverConnector, "check", unexpected_source_call)

    app = AppTest.from_file(str(_app_path())).run()
    app.radio(key="navigation_selection").set_value("Job Search").run()

    assert not app.exception
    assert any("No approved job sources are configured" in warning.value for warning in app.warning)
