from fastapi.testclient import TestClient

from resume_tailor.api.main import app


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
