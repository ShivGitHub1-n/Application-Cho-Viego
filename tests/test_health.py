from fastapi.testclient import TestClient

import resume_tailor.api.main as api_main
from resume_tailor.application.llm_services import HybridLlmServices
from resume_tailor.application.services import TailorResumeService
from resume_tailor.domain.llm_models import (
    CompositionRecommendationOutput,
    CompositionRecommendationResult,
    LlmOperation,
)
from resume_tailor.api.main import app
from resume_tailor.infrastructure.optimization import (
    DeterministicResumeOptimizer,
    EvidenceBoundResumeWriter,
)
from tests.fakes import FakeResumeLanguageModel, metadata


def test_health_check_returns_service_status() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "resume-tailor"}


def test_optimization_endpoint_returns_supported_plan() -> None:
    payload = {
        "profile": {
            "id": "profile-api",
            "user_id": "user-api",
            "display_name": "Avery Engineer",
            "experiences": [{"id": "experience-api", "title": "Firmware Intern", "kind": "experience"}],
            "projects": [],
            "evidence": [
                {
                    "id": "evidence-api",
                    "entity_id": "experience-api",
                    "source_text": "Developed embedded STM32 firmware and tested hardware interfaces.",
                }
            ],
        },
        "posting": {
            "id": "posting-api",
            "title": "Embedded Firmware Intern",
            "description": "Develop and test firmware for STM32 microcontrollers.",
        },
    }

    response = TestClient(app).post("/optimization-plans", json=payload)

    assert response.status_code == 200
    assert response.json()["strategy"]["role_family"] == "embedded_firmware"


def test_resume_document_endpoint_rejects_invalid_client_plan() -> None:
    payload = {
        "profile": {
            "id": "profile-api-invalid",
            "user_id": "user-api",
            "display_name": "Avery Engineer",
            "experiences": [{"id": "experience-api", "title": "Firmware Intern", "kind": "experience"}],
            "projects": [],
            "evidence": [
                {
                    "id": "evidence-api",
                    "entity_id": "experience-api",
                    "source_text": "Developed embedded STM32 firmware and tested hardware interfaces.",
                }
            ],
        },
        "posting": {
            "id": "posting-api-invalid",
            "title": "Embedded Firmware Intern",
            "description": "Develop and test firmware for STM32 microcontrollers.",
        },
    }
    client = TestClient(app)
    plan_response = client.post("/optimization-plans", json=payload)
    assert plan_response.status_code == 200
    plan = plan_response.json()
    plan["claim_candidates"][0]["evidence_ids"] = ["fabricated-evidence"]

    response = client.post(
        "/resume-documents",
        json={"profile": payload["profile"], "plan": plan},
    )

    assert response.status_code == 422
    assert "unknown candidate evidence ID" in response.json()["detail"]


def test_api_plan_and_document_use_reconciled_composition(monkeypatch) -> None:
    result = CompositionRecommendationResult(
        metadata=metadata(LlmOperation.RECOMMEND_COMPOSITION),
        output=CompositionRecommendationOutput(
            selected_entry_ids=["experience-api"],
            selected_evidence_ids=["evidence-api-2"],
            rationale="Use the focused hardware validation evidence.",
        ),
    )
    fake = FakeResumeLanguageModel(recommend_composition=result)
    hybrid = HybridLlmServices(fake, 0, 4, False, True, False)
    monkeypatch.setattr(
        api_main,
        "_service",
        TailorResumeService(
            DeterministicResumeOptimizer(),
            EvidenceBoundResumeWriter(),
            hybrid_services=hybrid,
        ),
    )
    profile = {
        "id": "profile-api-composition",
        "user_id": "user-api",
        "display_name": "Avery Engineer",
        "experiences": [
            {"id": "experience-api", "title": "Firmware Intern", "kind": "experience"}
        ],
        "evidence": [
            {
                "id": "evidence-api-1",
                "entity_id": "experience-api",
                "source_text": "Developed STM32 embedded firmware.",
            },
            {
                "id": "evidence-api-2",
                "entity_id": "experience-api",
                "source_text": "Validated SPI hardware sensor interfaces.",
            },
        ],
    }
    client = TestClient(app)
    plan_response = client.post(
        "/optimization-plans",
        json={
            "profile": profile,
            "posting": {
                "id": "posting-api-composition",
                "title": "Embedded Firmware Intern",
                "description": "Develop STM32 firmware and validate SPI hardware interfaces.",
            },
        },
    )

    assert plan_response.status_code == 200
    assert plan_response.json()["selected_claim_ids"] == ["evidence-api-2"]
    document_response = client.post(
        "/resume-documents",
        json={"profile": profile, "plan": plan_response.json()},
    )
    assert document_response.status_code == 200
    bullets = document_response.json()["experience_bullets"]["experience-api"]
    assert [bullet["id"] for bullet in bullets] == ["evidence-api-2"]
