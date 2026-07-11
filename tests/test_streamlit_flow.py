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
from tests.fakes import FakeResumeLanguageModel, metadata


def test_streamlit_strategy_uses_reconciled_composition(monkeypatch) -> None:
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
    app.text_input[0].input("Embedded Firmware Intern")
    app.button[0].click().run()

    assert app.session_state["plan"].selected_claim_ids == ["streamlit-evidence-2"]
