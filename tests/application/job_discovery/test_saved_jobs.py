from __future__ import annotations

from datetime import UTC, datetime

import pytest

import resume_tailor.application.job_discovery.saved as saved_module
from resume_tailor.application.job_discovery.saved import (
    CheckSavedJobAvailabilityService,
    DiscoveredJobNotFoundError,
    SavedJobNotFoundError,
    SaveJobService,
)
from resume_tailor.domain.job_discovery.ids import saved_job_id
from resume_tailor.domain.job_discovery.models import (
    ConnectorType,
    DiscoveredJob,
    NormalizedLocation,
    SavedJobAvailability,
    SupportedJobSource,
    VerificationConfidence,
    VerificationResult,
    VerificationStatus,
    WorkArrangement,
)

WHEN = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)


def _job(description: str) -> DiscoveredJob:
    source = SupportedJobSource(
        source_id="greenhouse-example",
        connector_type=ConnectorType.GREENHOUSE,
        company_name="Example",
        board_token="example",
        enabled=True,
        official_base_url="https://boards.greenhouse.io",
    )
    return DiscoveredJob(
        id="job-1",
        source=source,
        external_job_id="123",
        title="Software Engineer",
        company_name="Example",
        description=description,
        official_url="https://boards.greenhouse.io/example/jobs/123",
        location=NormalizedLocation(raw="Toronto, ON, Canada", parseable=True),
        work_arrangement=WorkArrangement.UNKNOWN,
        fetched_at=WHEN,
    )


class FakeJobRepository:
    def __init__(self, job: DiscoveredJob) -> None:
        self.job = job

    def get(self, job_id: str) -> DiscoveredJob | None:
        return self.job if job_id == self.job.id else None


class FakeSavedJobRepository:
    def __init__(self) -> None:
        self.saved = {}

    def save(self, saved) -> None:
        self.saved[saved.id] = saved

    def get(self, user_id: str, saved_id: str):
        saved = self.saved.get(saved_id)
        return saved if saved is not None and saved.user_id == user_id else None

    def list(self, user_id: str):
        return [saved for saved in self.saved.values() if saved.user_id == user_id]

    def update_availability(self, saved_id, availability, checked_at) -> None:
        saved = self.saved[saved_id]
        self.saved[saved_id] = saved.model_copy(
            update={"availability": availability, "checked_at": checked_at}, deep=True
        )


class FakeSourceRepository:
    def __init__(self, source: SupportedJobSource | None) -> None:
        self.source = source

    def list_enabled(self):
        return [] if self.source is None else [self.source.model_copy(deep=True)]


class FakeAvailabilityChecker:
    def __init__(self, result: VerificationResult | None = None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.calls = []

    def check(self, source, external_job_id):
        self.calls.append((source, external_job_id))
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def _saved_services():
    job_repository = FakeJobRepository(_job("Original description."))
    saved_repository = FakeSavedJobRepository()
    save_service = SaveJobService(job_repository, saved_repository)
    source = job_repository.job.source
    return job_repository, saved_repository, save_service, FakeSourceRepository(source)


def test_saved_snapshot_is_immutable_when_job_changes():
    repository = FakeJobRepository(_job("Original description."))
    saved_repository = FakeSavedJobRepository()
    save_service = SaveJobService(repository, saved_repository)

    first = save_service.save("u1", "job-1", saved_at=WHEN)
    repository.job = _job("Changed description.")
    second = save_service.save("u1", "job-1", saved_at=LATER)

    assert second.posting_snapshot.description == first.posting_snapshot.description
    assert second.saved_at == first.saved_at


def test_save_uses_deterministic_id_and_rejects_unknown_job_without_writing():
    job_repository, saved_repository, save_service, _ = _saved_services()

    saved = save_service.save("u1", "job-1", saved_at=WHEN)

    assert saved.id == saved_job_id("u1", "job-1")
    with pytest.raises(DiscoveredJobNotFoundError):
        save_service.save("u1", "missing", saved_at=WHEN)
    assert list(saved_repository.saved) == [saved.id]
    assert job_repository.job.description == "Original description."


def test_repeated_save_preserves_original_snapshot_and_saved_at():
    _, _, save_service, _ = _saved_services()

    first = save_service.save("u1", "job-1", saved_at=WHEN)
    second = save_service.save("u1", "job-1", saved_at=LATER)

    assert second == first


def test_availability_check_updates_only_status_metadata_and_uses_external_id():
    _, saved_repository, save_service, sources = _saved_services()
    saved = save_service.save("u1", "job-1", saved_at=WHEN)
    checker = FakeAvailabilityChecker(
        VerificationResult(
            status=VerificationStatus.VERIFIED_ACTIVE,
            confidence=VerificationConfidence.HIGH,
            checked_at=LATER,
            message="available",
        )
    )
    service = CheckSavedJobAvailabilityService(
        saved_repository,
        sources,
        {ConnectorType.GREENHOUSE: checker},
    )

    checked = service.check("u1", saved.id, checked_at=LATER)

    assert checked.availability is SavedJobAvailability.AVAILABLE
    assert checked.checked_at == LATER
    assert checked.saved_at == WHEN
    assert checked.posting_snapshot == saved.posting_snapshot
    assert checker.calls[0][1] == "123"


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (VerificationStatus.UNAVAILABLE, SavedJobAvailability.UNAVAILABLE),
        (VerificationStatus.EXPIRED, SavedJobAvailability.UNAVAILABLE),
        (VerificationStatus.VERIFIED_STATUS_UNKNOWN, SavedJobAvailability.UNKNOWN),
        (VerificationStatus.UNVERIFIED, SavedJobAvailability.UNKNOWN),
    ],
)
def test_availability_states_remain_explicit_and_saved_row_is_retained(status, expected):
    _, saved_repository, save_service, sources = _saved_services()
    saved = save_service.save("u1", "job-1", saved_at=WHEN)
    checker = FakeAvailabilityChecker(
        VerificationResult(
            status=status,
            confidence=VerificationConfidence.MEDIUM,
            checked_at=LATER,
            message="provider result",
        )
    )
    service = CheckSavedJobAvailabilityService(
        saved_repository,
        sources,
        {ConnectorType.GREENHOUSE: checker},
    )

    checked = service.check("u1", saved.id, checked_at=LATER)

    assert checked.availability is expected
    assert saved_repository.get("u1", saved.id) is not None
    assert checked.posting_snapshot.description == "Original description."


def test_transport_failure_retains_saved_job_as_unknown():
    _, saved_repository, save_service, sources = _saved_services()
    saved = save_service.save("u1", "job-1", saved_at=WHEN)
    checker = FakeAvailabilityChecker(error=TimeoutError("network timeout"))
    service = CheckSavedJobAvailabilityService(
        saved_repository,
        sources,
        {ConnectorType.GREENHOUSE: checker},
    )

    checked = service.check("u1", saved.id, checked_at=LATER)

    assert checked.availability is SavedJobAvailability.UNKNOWN
    assert saved_repository.get("u1", saved.id) is not None


def test_unexpected_programming_error_is_not_silently_reclassified():
    _, saved_repository, save_service, sources = _saved_services()
    saved = save_service.save("u1", "job-1", saved_at=WHEN)
    checker = FakeAvailabilityChecker(error=AssertionError("programming defect"))
    service = CheckSavedJobAvailabilityService(
        saved_repository,
        sources,
        {ConnectorType.GREENHOUSE: checker},
    )

    with pytest.raises(AssertionError, match="programming defect"):
        service.check("u1", saved.id, checked_at=LATER)


def test_missing_source_or_checker_is_unknown_without_provider_call():
    _, saved_repository, save_service, _ = _saved_services()
    saved = save_service.save("u1", "job-1", saved_at=WHEN)
    checker = FakeAvailabilityChecker()
    service = CheckSavedJobAvailabilityService(
        saved_repository,
        FakeSourceRepository(None),
        {ConnectorType.GREENHOUSE: checker},
    )

    checked = service.check("u1", saved.id, checked_at=LATER)

    assert checked.availability is SavedJobAvailability.UNKNOWN
    assert checker.calls == []


def test_availability_enforces_ownership():
    _, saved_repository, save_service, sources = _saved_services()
    saved = save_service.save("u1", "job-1", saved_at=WHEN)
    service = CheckSavedJobAvailabilityService(saved_repository, sources, {})

    with pytest.raises(SavedJobNotFoundError):
        service.check("u2", saved.id, checked_at=LATER)


def test_saved_job_listing_is_user_isolated():
    _, saved_repository, save_service, _ = _saved_services()
    save_service.save("u1", "job-1", saved_at=WHEN)
    job_repository = FakeJobRepository(_job("Second job."))
    other_save_service = SaveJobService(job_repository, saved_repository)
    job_repository.job = job_repository.job.model_copy(update={"id": "job-2"}, deep=True)
    other_save_service.save("u2", "job-2", saved_at=LATER)

    assert [saved.user_id for saved in save_service.list("u1")] == ["u1"]
    assert [saved.user_id for saved in save_service.list("u2")] == ["u2"]


def test_saved_services_use_only_explicit_timestamps(monkeypatch):
    class ExplodingDatetime:
        @classmethod
        def now(cls, *args, **kwargs):
            raise AssertionError("saved services must not read current time")

    monkeypatch.setattr(saved_module, "datetime", ExplodingDatetime)
    _, saved_repository, save_service, sources = _saved_services()
    saved = save_service.save("u1", "job-1", saved_at=WHEN)
    checker = FakeAvailabilityChecker(
        VerificationResult(
            status=VerificationStatus.VERIFIED_STATUS_UNKNOWN,
            confidence=VerificationConfidence.MEDIUM,
            checked_at=LATER,
            message="unknown",
        )
    )
    check_service = CheckSavedJobAvailabilityService(
        saved_repository,
        sources,
        {ConnectorType.GREENHOUSE: checker},
    )

    checked = check_service.check("u1", saved.id, checked_at=LATER)

    assert checked.saved_at == WHEN
    assert checked.checked_at == LATER
