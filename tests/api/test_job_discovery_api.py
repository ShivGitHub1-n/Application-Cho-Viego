from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from resume_tailor.api.dependencies import JobDiscoveryServiceBundle, get_job_discovery_services
from resume_tailor.api.main import app
from resume_tailor.application.job_discovery.preferences import ProfileNotFoundError
from resume_tailor.application.job_discovery.saved import (
    DiscoveredJobNotFoundError,
    SavedJobNotFoundError,
)
from resume_tailor.domain.job_discovery.models import (
    DiscoveryRun,
    DiscoveryRunStatus,
    JobSearchPreferences,
    JobSearchPreferenceSuggestion,
    SavedJob,
    SavedJobAvailability,
    WorkArrangement,
)
from resume_tailor.domain.models import RoleFamily
from resume_tailor.ports.job_discovery import PreferenceVersionConflictError

WHEN = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


def _preferences() -> JobSearchPreferences:
    return JobSearchPreferences(
        user_id="u1",
        profile_id="p1",
        version=1,
        role_family_priority=[RoleFamily.SOFTWARE_DATA_ENGINEERING],
        target_titles=["Software Engineer"],
        related_title_variants=[],
        technical_themes=[],
        career_interests=[],
        job_levels=[],
        locations=[],
        work_arrangement=WorkArrangement.UNKNOWN,
        preferred_companies=[],
        created_at=WHEN,
        confirmed_at=WHEN,
    )


def _suggestion() -> JobSearchPreferenceSuggestion:
    return JobSearchPreferenceSuggestion(
        profile_id="p1",
        generated_at=WHEN,
        role_family_priority=[RoleFamily.SOFTWARE_DATA_ENGINEERING],
        target_titles=["Software Engineer"],
        related_title_variants=[],
        technical_themes=[],
        career_interests=[],
        job_levels=[],
        locations=[],
        work_arrangement=WorkArrangement.UNKNOWN,
        preferred_companies=[],
        rationale=["reviewable"],
    )


def _override(bundle: JobDiscoveryServiceBundle):
    return lambda: bundle


def _run(status: DiscoveryRunStatus = DiscoveryRunStatus.COMPLETED) -> DiscoveryRun:
    return DiscoveryRun(
        id="run-1",
        user_id="u1",
        profile_id="p1",
        preference_version=1,
        status=status,
        started_at=WHEN,
        completed_at=WHEN,
        source_count=0,
        record_count=0,
        warning_count=0,
        error_messages=[],
    )


def _saved_job() -> SavedJob:
    from tests.application.job_discovery.test_saved_jobs import _job

    return SavedJob(
        id="saved-1",
        user_id="local-user",
        job_id="job-1",
        availability=SavedJobAvailability.UNKNOWN,
        saved_at=WHEN,
        posting_snapshot=_job("Original description."),
    )


class FakeSuggest:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls = []
        self.error = error

    def suggest(self, user_id: str, profile_id: str, *, generated_at: datetime):
        self.calls.append((user_id, profile_id, generated_at))
        if self.error:
            raise self.error
        return _suggestion()


class FakeConfirm:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls = []
        self.error = error

    def confirm(self, preferences: JobSearchPreferences) -> JobSearchPreferences:
        self.calls.append(preferences)
        if self.error:
            raise self.error
        return preferences


class FakeCurrentPreferences:
    def get(self, user_id: str, profile_id: str) -> JobSearchPreferences:
        return _preferences()


class FakeRefresh:
    def __init__(self, run: DiscoveryRun) -> None:
        self.run = run
        self.calls = []

    def refresh(self, user_id: str, profile_id: str, preferences, *, started_at: datetime):
        self.calls.append((user_id, profile_id, preferences, started_at))
        return self.run


class FakeRuns:
    def __init__(self, run: DiscoveryRun | None) -> None:
        self.run = run
        self.calls = []

    def get(self, run_id: str):
        self.calls.append(run_id)
        return self.run


class FakeSave:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls = []
        self.error = error
        self.saved = _saved_job()

    def save(self, user_id: str, job_id: str, *, saved_at: datetime):
        self.calls.append((user_id, job_id, saved_at))
        if self.error:
            raise self.error
        return self.saved

    def list(self, user_id: str):
        self.calls.append(("list", user_id))
        return [self.saved] if user_id == self.saved.user_id else []


class FakeCheckAvailability:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls = []
        self.error = error
        self.saved = _saved_job().model_copy(
            update={"availability": SavedJobAvailability.AVAILABLE}
        )

    def check(self, user_id: str, saved_id: str, *, checked_at: datetime):
        self.calls.append((user_id, saved_id, checked_at))
        if self.error:
            raise self.error
        return self.saved


def _bundle(
    *,
    run: DiscoveryRun | None = None,
    status: DiscoveryRunStatus = DiscoveryRunStatus.COMPLETED,
) -> JobDiscoveryServiceBundle:
    return JobDiscoveryServiceBundle(
        suggest_preferences=FakeSuggest(),
        confirm_preferences=FakeConfirm(),
        current_preferences=FakeCurrentPreferences(),
        refresh=FakeRefresh(run or _run(status)),
        runs=FakeRuns(run or _run(status)),
        save=FakeSave(),
        check_saved_availability=FakeCheckAvailability(),
    )


def test_router_is_included_with_exact_supportable_paths() -> None:
    routes = {
        (path, method.upper())
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    }

    assert ("/job-discovery/preferences/suggest", "POST") in routes
    assert ("/job-discovery/preferences/confirm", "POST") in routes
    assert ("/job-discovery/refresh", "POST") in routes
    assert ("/job-discovery/runs/{run_id}", "GET") in routes
    assert ("/job-discovery/saved", "POST") in routes
    assert ("/job-discovery/saved", "GET") in routes
    assert ("/job-discovery/saved/{saved_id}/availability", "POST") in routes


def test_api_uses_overridable_service_dependency() -> None:
    fake_bundle = _bundle()
    app.dependency_overrides[get_job_discovery_services] = lambda: fake_bundle
    try:
        response = TestClient(app).post(
            "/job-discovery/preferences/suggest",
            json={"profile_id": "p1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["suggestion"]["profile_id"] == "p1"


def test_preference_confirmation_delegates_to_application_service() -> None:
    bundle = _bundle()
    app.dependency_overrides[get_job_discovery_services] = lambda: bundle
    try:
        response = TestClient(app).post(
            "/job-discovery/preferences/confirm",
            json=_preferences().model_dump(mode="json"),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["preferences"]["version"] == 1
    assert bundle.confirm_preferences.calls[0].user_id == "u1"


def test_profile_not_found_maps_to_http_404_for_suggestion_and_confirmation() -> None:
    bundle = _bundle()
    bundle.suggest_preferences = FakeSuggest(ProfileNotFoundError("missing"))
    bundle.confirm_preferences = FakeConfirm(ProfileNotFoundError("missing"))
    app.dependency_overrides[get_job_discovery_services] = lambda: bundle
    try:
        suggestion = TestClient(app).post(
            "/job-discovery/preferences/suggest",
            json={"profile_id": "missing"},
        )
        confirmation = TestClient(app).post(
            "/job-discovery/preferences/confirm",
            json=_preferences().model_dump(mode="json"),
        )
    finally:
        app.dependency_overrides.clear()

    assert suggestion.status_code == 404
    assert confirmation.status_code == 404


def test_preference_version_conflict_maps_to_http_409() -> None:
    bundle = _bundle()
    bundle.confirm_preferences = FakeConfirm(PreferenceVersionConflictError("conflict"))
    app.dependency_overrides[get_job_discovery_services] = lambda: bundle
    try:
        response = TestClient(app).post(
            "/job-discovery/preferences/confirm",
            json=_preferences().model_dump(mode="json"),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409


def test_refresh_success_and_no_sources_status_are_typed_responses() -> None:
    for status in (
        DiscoveryRunStatus.COMPLETED,
        DiscoveryRunStatus.NO_SOURCES_CONFIGURED,
        DiscoveryRunStatus.FAILED_ALL_SOURCES,
    ):
        bundle = _bundle(status=status)
        app.dependency_overrides[get_job_discovery_services] = _override(bundle)
        try:
            response = TestClient(app).post(
                "/job-discovery/refresh",
                json={"profile_id": "p1"},
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        assert response.json()["run"]["status"] == status.value
        assert bundle.refresh.calls[0][0:2] == ("local-user", "p1")


def test_run_retrieval_success_and_unknown_run() -> None:
    bundle = _bundle()
    app.dependency_overrides[get_job_discovery_services] = lambda: bundle
    try:
        response = TestClient(app).get("/job-discovery/runs/run-1")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["run"]["id"] == "run-1"

    unknown = _bundle(run=None)
    unknown.runs.run = None
    app.dependency_overrides[get_job_discovery_services] = lambda: unknown
    try:
        response = TestClient(app).get("/job-discovery/runs/missing")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 404


def test_refresh_request_validation_is_standard_fastapi_validation() -> None:
    bundle = _bundle()
    app.dependency_overrides[get_job_discovery_services] = lambda: bundle
    try:
        response = TestClient(app).post("/job-discovery/refresh", json={})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_save_list_and_availability_routes_delegate_to_services_with_typed_shapes() -> None:
    bundle = _bundle()
    app.dependency_overrides[get_job_discovery_services] = lambda: bundle
    try:
        client = TestClient(app)
        saved = client.post("/job-discovery/saved", json={"job_id": "job-1"})
        listed = client.get("/job-discovery/saved")
        checked = client.post("/job-discovery/saved/saved-1/availability")
    finally:
        app.dependency_overrides.clear()

    assert saved.status_code == 200
    assert saved.json().keys() == {"saved_job"}
    assert listed.status_code == 200
    assert listed.json().keys() == {"saved_jobs"}
    assert checked.status_code == 200
    assert checked.json().keys() == {"saved_job"}
    assert bundle.save.calls[0][0:2] == ("local-user", "job-1")
    assert bundle.save.calls[1] == ("list", "local-user")
    assert bundle.check_saved_availability.calls[0][0:2] == ("local-user", "saved-1")


def test_saved_routes_map_unknown_resources_and_ownership_failures_to_404() -> None:
    bundle = _bundle()
    bundle.save = FakeSave(DiscoveredJobNotFoundError("missing"))
    bundle.check_saved_availability = FakeCheckAvailability(SavedJobNotFoundError("other user"))
    app.dependency_overrides[get_job_discovery_services] = lambda: bundle
    try:
        client = TestClient(app)
        unknown_job = client.post("/job-discovery/saved", json={"job_id": "missing"})
        ownership = client.post("/job-discovery/saved/saved-1/availability")
    finally:
        app.dependency_overrides.clear()

    assert unknown_job.status_code == 404
    assert ownership.status_code == 404
