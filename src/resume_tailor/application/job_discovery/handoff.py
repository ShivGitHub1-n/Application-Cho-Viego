from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from resume_tailor.domain.job_discovery.models import DiscoveredJob, SavedJob


class DiscoveredJobLookup(Protocol):
    def get(self, job_id: str) -> DiscoveredJob | None: ...


class SavedJobLookup(Protocol):
    def get(self, user_id: str, saved_id: str) -> SavedJob | None: ...


class TailoringHandoff(BaseModel):
    posting_id: str
    title: str
    company: str
    description: str
    official_url: str
    source_id: str
    profile_id: str


class PrepareTailoringHandoffService:
    """Prepare existing tailoring inputs without generating derived output."""

    def __init__(
        self,
        jobs: DiscoveredJobLookup,
        saved_jobs: SavedJobLookup,
    ) -> None:
        self._jobs = jobs
        self._saved_jobs = saved_jobs

    def from_discovered(self, job_id: str, *, profile_id: str) -> TailoringHandoff:
        job = self._jobs.get(job_id)
        if job is None:
            raise LookupError(f"Discovered job {job_id!r} was not found.")
        return _from_job(job, profile_id=profile_id)

    def from_saved(
        self,
        saved_id: str,
        *,
        profile_id: str,
        user_id: str,
    ) -> TailoringHandoff:
        saved = self._saved_jobs.get(user_id, saved_id)
        if saved is None:
            raise LookupError(f"Saved job {saved_id!r} was not found.")
        return _from_job(saved.posting_snapshot, profile_id=profile_id)


def _from_job(job: DiscoveredJob, *, profile_id: str) -> TailoringHandoff:
    return TailoringHandoff(
        posting_id=job.id,
        title=job.title,
        company=job.company_name,
        description=job.description,
        official_url=job.official_url,
        source_id=job.source.source_id,
        profile_id=profile_id,
    )


__all__ = ["PrepareTailoringHandoffService", "TailoringHandoff"]
