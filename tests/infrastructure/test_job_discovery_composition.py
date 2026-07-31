from pathlib import Path

from resume_tailor.infrastructure import dependencies
from resume_tailor.infrastructure.config import Settings


def test_production_first_party_composition_injects_one_robots_authority(
    monkeypatch, tmp_path: Path
) -> None:
    captured: list[object] = []

    class Connector:
        def __init__(self, client, *, robots_checker=None, browser_fallback=None):
            captured.append((robots_checker, browser_fallback))

    monkeypatch.setattr(dependencies, "FirstPartyCareerConnector", Connector)
    bundle = dependencies.create_job_discovery_services(
        Settings(
            app_data_directory=tmp_path,
            job_discovery_source_registry_path=Path("config/approved-job-sources.json"),
        )
    )
    try:
        assert len(captured) == 1
        robots_checker, browser_fallback = captured[0]
        assert callable(robots_checker)
        assert browser_fallback._robots_checker is robots_checker
    finally:
        bundle.close()
