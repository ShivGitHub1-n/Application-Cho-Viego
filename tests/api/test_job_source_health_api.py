# ruff: noqa: E501

from fastapi.testclient import TestClient

from resume_tailor.api.dependencies import JobDiscoveryServiceBundle, get_job_discovery_services
from resume_tailor.api.main import app
from resume_tailor.application.job_discovery.source_health import SourceHealthSummary


class _Health:
    def list(self):
        return [
            SourceHealthSummary(
                source_id="rocket-lab",
                company_name="Rocket Lab",
                mechanism="first_party",
                enabled=True,
                runnable=True,
                audit_version="2026-07-24.1",
            )
        ]

    def get(self, source_id):
        if source_id != "rocket-lab":
            raise KeyError(source_id)
        return self.list()[0]


def test_source_health_is_read_only_and_safe() -> None:
    bundle = JobDiscoveryServiceBundle(
        suggest_preferences=object(), refresh=object(), source_health=_Health()
    )
    app.dependency_overrides[get_job_discovery_services] = lambda: bundle
    try:
        client = TestClient(app)
        listed = client.get("/job-discovery/sources")
        detail = client.get("/job-discovery/sources/rocket-lab/health")
        missing = client.get("/job-discovery/sources/missing/health")
    finally:
        app.dependency_overrides.pop(get_job_discovery_services, None)

    assert listed.status_code == 200
    assert detail.status_code == 200
    assert detail.json()["source_id"] == "rocket-lab"
    assert missing.status_code == 404
    assert "description" not in detail.text
