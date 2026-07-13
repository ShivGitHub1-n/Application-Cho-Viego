import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

import resume_tailor.infrastructure.dependencies as dependencies
from resume_tailor.application.llm_services import HybridLlmServices
from resume_tailor.application.services import TailorResumeService
from resume_tailor.domain.llm_models import (
    CompositionRecommendationOutput,
    CompositionRecommendationResult,
    LlmOperation,
)
from resume_tailor.infrastructure.optimization import (
    DeterministicResumeOptimizer,
    EvidenceBoundResumeWriter,
)
from resume_tailor.infrastructure.profile_repository import SQLiteMasterProfileRepository
from resume_tailor.domain.models import MasterProfile
from tests.fakes import FakeResumeLanguageModel, metadata


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
    app.text_area[0].input(json.dumps(profile))
    app.text_area[1].input("Develop STM32 firmware and validate SPI hardware interfaces.")
    app.text_input[0].input("streamlit-profile")
    app.text_input[1].input("Embedded Firmware Intern")
    app.session_state["resume"] = "stale-generated-resume"
    app.session_state["generated_content_reviewed"] = True
    app.button[3].click().run()

    assert app.session_state["plan"].selected_claim_ids == ["streamlit-evidence-2"]
    assert "resume" not in app.session_state
    assert app.session_state["generated_content_reviewed"] is False

    app.button[4].click().run()

    assert app.session_state["resume"].experience_bullets["streamlit-entry"][0].text == (
        "Validated SPI hardware sensor interfaces."
    )
    assert app.session_state["generated_content_reviewed"] is False
    assert any(
        "Generated resume review" in element.value
        for element in app.subheader
    )
    assert app.button[5].disabled is True


def test_streamlit_uses_persisted_profile_with_pasted_job_description(monkeypatch, tmp_path) -> None:
    database = tmp_path / "profiles.sqlite3"
    repository = SQLiteMasterProfileRepository(database)
    profile = MasterProfile(
        id="local-profile",
        user_id="local-user",
        display_name="Persisted Candidate",
        experiences=[{"id": "entry-1", "title": "Engineer", "kind": "experience"}],
        evidence=[
            {"id": "evidence-1", "entity_id": "entry-1", "source_text": "Built firmware."}
        ],
    )
    repository.save(profile)
    monkeypatch.setattr(dependencies, "create_profile_repository", lambda: SQLiteMasterProfileRepository(database))
    monkeypatch.setattr(
        dependencies,
        "create_tailor_service",
        lambda: TailorResumeService(DeterministicResumeOptimizer(), EvidenceBoundResumeWriter()),
    )

    app_path = Path(__file__).parents[1] / "src" / "resume_tailor" / "frontend" / "app.py"
    app = AppTest.from_file(str(app_path)).run()
    app.text_area[1].input("Build firmware.\r\n\r\n- Test systems  ")
    app.text_input[1].input("Firmware Engineer")
    app.button[3].click().run()

    assert app.session_state["profile"].id == "local-profile"
    assert app.session_state["posting"].description == "Build firmware.\n\n- Test systems"
    assert app.session_state["profile_load_status"] == "Loaded from persistent storage."
