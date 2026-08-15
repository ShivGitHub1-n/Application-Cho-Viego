from datetime import UTC, datetime
from pathlib import Path

from resume_tailor.domain.models import MasterProfile
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


def test_production_composition_exposes_tailoring_handoff_service(tmp_path: Path) -> None:
    bundle = dependencies.create_job_discovery_services(
        Settings(app_data_directory=tmp_path)
    )
    try:
        assert bundle.prepare_handoff is not None
    finally:
        bundle.close()


def test_production_composition_uses_injected_canonical_profile_authority(
    tmp_path: Path,
) -> None:
    profile = MasterProfile(
        id="profile-1",
        user_id="profile-owner",
        display_name="Reviewed Candidate",
    )

    class CanonicalProfiles:
        def get(self, profile_id: str) -> MasterProfile | None:
            return profile if profile_id == profile.id else None

        def list_all(self) -> list[MasterProfile]:
            return [profile]

        def save(self, value: MasterProfile) -> None:
            raise AssertionError(f"Unexpected profile write for {value.id}")

    profiles = CanonicalProfiles()
    bundle = dependencies.create_job_discovery_services(
        Settings(app_data_directory=tmp_path),
        profile_repository=profiles,
    )
    try:
        suggestion = bundle.suggest_preferences.suggest(
            profile.user_id,
            profile.id,
            generated_at=datetime(2026, 8, 15, tzinfo=UTC),
        )
    finally:
        bundle.close()

    assert suggestion.profile_id == profile.id
    assert bundle.suggest_preferences._profiles is profiles
