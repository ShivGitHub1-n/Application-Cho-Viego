from __future__ import annotations

from datetime import datetime
from typing import Protocol

from resume_tailor.domain.job_discovery.models import (
    JobSourceFetchResult,
    SupportedJobSource,
    VerificationResult,
)


class JobSourceConnector(Protocol):
    def fetch(
        self, source: SupportedJobSource, *, fetched_at: datetime
    ) -> JobSourceFetchResult: ...


class JobSourceAvailabilityChecker(Protocol):
    def check(
        self,
        source: SupportedJobSource,
        external_job_id: str,
    ) -> VerificationResult: ...


__all__ = [
    "JobSourceAvailabilityChecker",
    "JobSourceConnector",
]
