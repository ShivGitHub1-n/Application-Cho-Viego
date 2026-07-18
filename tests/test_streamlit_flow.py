import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

import resume_tailor.infrastructure.dependencies as dependencies
from resume_tailor.application.llm_services import HybridLlmServices
from resume_tailor.application.services import TailorResumeService
from resume_tailor.application.workflow_state import (
    get_active_posting,
    has_cover_letter_prerequisites,
    invalidate_posting_derived_workflow,
    invalidate_profile_derived_workflow,
)
from resume_tailor.domain.llm_models import (
    CompositionRecommendationOutput,
    CompositionRecommendationResult,
    LlmOperation,
)
from resume_tailor.domain.models import MasterProfile
from resume_tailor.infrastructure.optimization import (
    DeterministicResumeOptimizer,
    EvidenceBoundResumeWriter,
)
from resume_tailor.infrastructure.profile_repository import SQLiteMasterProfileRepository
from tests.fakes import FakeResumeLanguageModel, metadata


class _Strategy:
    pass


class _Plan:
    strategy = _Strategy()


def _workflow_state() -> dict[str, object]:
    return {
        "profile": object(),
        "posting": type(
            "Posting", (), {"title": "Robotics Engineer", "company_name": "Example Robotics"}
        )(),
        "plan": _Plan(),
        "resume": "resume-artifact",
        "generated_content_reviewed": True,
        "cover_letter": "cover-letter-draft",
        "cover_letter_reviewed": True,
        "cover_letter_download": "download-state",
        "workflow_profile_fingerprint": "profile-v1",
        "workflow_posting_fingerprint": "posting-v1",
        "cover_letter_profile_fingerprint": "profile-v1",
        "cover_letter_posting_fingerprint": "posting-v1",
        "cover_letter_plan_fingerprint": "plan-v1",
        "cover_letter_evidence_fingerprint": "evidence-v1",
        "cover_letter_recipient_fingerprint": "recipient-v1",
    }


def test_initial_workflow_has_no_active_posting_and_cover_letter_is_guarded() -> None:
    state: dict[str, object] = {}

    assert get_active_posting(state) is None
    assert not has_cover_letter_prerequisites(state)


def test_active_posting_survives_rerun_without_original_local_variable() -> None:
    state = _workflow_state()

    assert get_active_posting(state).title == "Robotics Engineer"
    assert get_active_posting(state).company_name == "Example Robotics"


def test_authoritative_posting_supplies_company_and_role_defaults() -> None:
    state = _workflow_state()
    posting = get_active_posting(state)

    assert posting.company_name == "Example Robotics"
    assert posting.title == "Robotics Engineer"


def test_job_description_invalidation_removes_all_posting_derived_state() -> None:
    state = _workflow_state()

    invalidate_posting_derived_workflow(state)

    assert get_active_posting(state) is None
    assert not has_cover_letter_prerequisites(state)
    assert "plan" not in state
    assert "resume" not in state
    assert "generated_content_reviewed" not in state
    assert "cover_letter" not in state
    assert "cover_letter_reviewed" not in state
    assert "workflow_posting_fingerprint" not in state


def test_invalid_posting_cannot_leave_the_prior_posting_active() -> None:
    state = _workflow_state()

    invalidate_posting_derived_workflow(state)

    assert get_active_posting(state) is None
    assert not has_cover_letter_prerequisites(state)


def test_loading_same_profile_preserves_active_posting() -> None:
    state = _workflow_state()
    posting = state["posting"]

    invalidate_profile_derived_workflow(state)

    assert state["posting"] is posting
    assert get_active_posting(state) is posting


def test_changed_canonical_profile_invalidates_dependents_but_preserves_posting() -> None:
    state = _workflow_state()
    posting = state["posting"]

    invalidate_profile_derived_workflow(state)

    assert state["posting"] is posting
    assert "plan" not in state
    assert "resume" not in state
    assert "cover_letter" not in state
    assert "generated_content_reviewed" not in state
    assert "cover_letter_reviewed" not in state


def test_missing_posting_is_a_cover_letter_guard_not_a_name_error() -> None:
    state = {"profile": object(), "plan": _Plan()}

    assert not has_cover_letter_prerequisites(state)


def test_resume_and_cover_letter_approval_states_are_separate() -> None:
    state = {"generated_content_reviewed": True, "cover_letter_reviewed": False}

    state["generated_content_reviewed"] = False

    assert state["generated_content_reviewed"] is False
    assert state["cover_letter_reviewed"] is False


def test_repeated_invalidation_is_safe_and_deterministic() -> None:
    state = _workflow_state()

    invalidate_posting_derived_workflow(state)
    first_result = dict(state)
    invalidate_posting_derived_workflow(state)

    assert state == first_result


def test_streamlit_strategy_uses_reconciled_composition(monkeypatch, tmp_path) -> None:
    result = CompositionRecommendationResult(
        metadata=metadata(LlmOperation.RECOMMEND_COMPOSITION),
        output=CompositionRecommendationOutput(
            selected_entry_ids=["streamlit-entry"],
            selected_evidence_ids=["streamlit-evidence-2"],
            rationale="Use focused interface validation evidence.",
        ),
    )
    hybrid = HybridLlmServices(
        FakeResumeLanguageModel(recommend_composition=result),
        0,
        4,
        False,
        True,
        False,
    )
    service = TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
        hybrid_services=hybrid,
    )
    monkeypatch.setattr(dependencies, "create_tailor_service", lambda: service)
    monkeypatch.setattr(
        dependencies,
        "create_profile_repository",
        lambda: SQLiteMasterProfileRepository(tmp_path / "streamlit-profile.sqlite3"),
    )
    profile = {
        "id": "streamlit-profile",
        "user_id": "streamlit-user",
        "display_name": "Candidate",
        "experiences": [
            {"id": "streamlit-entry", "title": "Firmware Intern", "kind": "experience"}
        ],
        "evidence": [
            {
                "id": "streamlit-evidence-1",
                "entity_id": "streamlit-entry",
                "source_text": "Developed STM32 embedded firmware.",
            },
            {
                "id": "streamlit-evidence-2",
                "entity_id": "streamlit-entry",
                "source_text": "Validated SPI hardware sensor interfaces.",
            },
        ],
    }
    app_path = Path(__file__).parents[1] / "src" / "resume_tailor" / "frontend" / "app.py"
    app = AppTest.from_file(str(app_path)).run()
    app.radio(key="navigation_selection").set_value("Profile").run()
    app.text_input(key="profile_id_input").input("streamlit-profile").run()
    app.text_area(key="profile_editor_raw_json").input(json.dumps(profile))
    next(
        button for button in app.button if button.label == "Validate and save raw JSON"
    ).click().run()
    app.radio(key="navigation_selection").set_value("Tailor Resume").run()
    app.text_area(key="job_description_input").input(
        "Develop STM32 firmware and validate SPI hardware interfaces."
    )
    app.text_input(key="job_title_input").input("Embedded Firmware Intern")
    app.session_state["resume"] = "stale-generated-resume"
    app.session_state["generated_content_reviewed"] = True
    next(
        button for button in app.button if button.label == "Recommend resume strategy"
    ).click().run()

    assert app.session_state["plan"].selected_claim_ids == ["streamlit-evidence-2"]
    assert "resume" not in app.session_state
    assert app.session_state["generated_content_reviewed"] is False

    next(button for button in app.button if button.label == "Build reviewed resume").click().run()

    assert app.session_state["resume"].experience_bullets["streamlit-entry"][0].text == (
        "Validated SPI hardware sensor interfaces."
    )
    assert app.session_state["generated_content_reviewed"] is False
    assert any("Generated resume review" in element.value for element in app.subheader)
    assert (
        next(button for button in app.button if button.label == "Export reviewed resume").disabled
        is True
    )


def test_streamlit_uses_persisted_profile_with_pasted_job_description(
    monkeypatch, tmp_path
) -> None:
    database = tmp_path / "profiles.sqlite3"
    repository = SQLiteMasterProfileRepository(database)
    profile = MasterProfile(
        id="local-profile",
        user_id="local-user",
        display_name="Persisted Candidate",
        experiences=[{"id": "entry-1", "title": "Engineer", "kind": "experience"}],
        evidence=[{"id": "evidence-1", "entity_id": "entry-1", "source_text": "Built firmware."}],
    )
    repository.save(profile)
    monkeypatch.setattr(
        dependencies, "create_profile_repository", lambda: SQLiteMasterProfileRepository(database)
    )
    monkeypatch.setattr(
        dependencies,
        "create_tailor_service",
        lambda: TailorResumeService(DeterministicResumeOptimizer(), EvidenceBoundResumeWriter()),
    )

    app_path = Path(__file__).parents[1] / "src" / "resume_tailor" / "frontend" / "app.py"
    app = AppTest.from_file(str(app_path)).run()
    app.radio(key="navigation_selection").set_value("Tailor Resume").run()
    app.text_area(key="job_description_input").input("Build firmware.\r\n\r\n- Test systems  ")
    app.text_input(key="job_title_input").input("Firmware Engineer")
    next(
        button for button in app.button if button.label == "Recommend resume strategy"
    ).click().run()

    assert app.session_state["profile"].id == "local-profile"
    assert app.session_state["posting"].description == "Build firmware.\n\n- Test systems"
    assert app.session_state["profile_load_status"] == "Loaded from persistent storage."
