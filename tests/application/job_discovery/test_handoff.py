from __future__ import annotations

from datetime import UTC, datetime

from resume_tailor.application.job_discovery.handoff import (
    PrepareTailoringHandoffService,
)
from resume_tailor.domain.job_discovery.models import (
    ConnectorType,
    DiscoveredJob,
    NormalizedLocation,
    SavedJob,
    SavedJobAvailability,
    SupportedJobSource,
    VerificationConfidence,
    VerificationStatus,
    WorkArrangement,
)
from resume_tailor.domain.models import RoleFamily


def _job() -> DiscoveredJob:
    source = SupportedJobSource(
        source_id="source-1",
        connector_type=ConnectorType.GREENHOUSE,
        company_name="Example Robotics",
        board_token="example",
        enabled=True,
        official_base_url="https://example.com/careers",
    )
    return DiscoveredJob(
        id="job-1",
        source=source,
        external_job_id="ext-1",
        title="Senior Firmware Engineer",
        company_name="Example Robotics",
        description="Build embedded systems and validate hardware interfaces.",
        official_url="https://example.com/jobs/job-1",
        application_url="https://example.com/jobs/job-1/apply",
        location=NormalizedLocation(
            city="Toronto", country_code="CA", raw="Toronto, CA", parseable=True
        ),
        work_arrangement=WorkArrangement.HYBRID,
        role_family=RoleFamily.EMBEDDED_FIRMWARE,
        verification_status=VerificationStatus.VERIFIED_ACTIVE,
        verification_confidence=VerificationConfidence.HIGH,
        fetched_at=datetime(2026, 7, 1, tzinfo=UTC),
    )


class Jobs:
    def __init__(self, job: DiscoveredJob) -> None:
        self.job = job

    def get(self, job_id: str) -> DiscoveredJob | None:
        return self.job if job_id == self.job.id else None


class Saved:
    def __init__(self, saved: SavedJob) -> None:
        self.saved = saved

    def get(self, user_id: str, saved_id: str) -> SavedJob | None:
        return self.saved if user_id == self.saved.user_id and saved_id == self.saved.id else None


def test_discovered_job_prepares_existing_tailoring_inputs() -> None:
    job = _job()
    handoff = PrepareTailoringHandoffService(Jobs(job), Saved(None))

    result = handoff.from_discovered(job.id, profile_id="profile-1")

    assert result.posting_id == job.id
    assert result.profile_id == "profile-1"
    assert result.title == job.title
    assert result.company == job.company_name
    assert result.description == job.description
    assert result.official_url == job.official_url
    assert result.source_id == job.source.source_id


def test_saved_job_handoff_uses_immutable_snapshot() -> None:
    job = _job()
    saved = SavedJob(
        id="saved-1",
        user_id="local-user",
        job_id=job.id,
        availability=SavedJobAvailability.UNAVAILABLE,
        saved_at=datetime(2026, 7, 2, tzinfo=UTC),
        posting_snapshot=job,
    )
    newer = job.model_copy(update={"description": "A newer live description."})
    handoff = PrepareTailoringHandoffService(Jobs(newer), Saved(saved))

    result = handoff.from_saved(saved.id, profile_id="profile-1", user_id="local-user")

    assert result.description == job.description
    assert result.title == job.title
    assert result.official_url == job.official_url
