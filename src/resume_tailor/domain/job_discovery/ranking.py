"""Provider-independent deterministic evaluation ordering."""

from __future__ import annotations

from datetime import datetime

from resume_tailor.domain.job_discovery.grading import FitGrade, grade_rank
from resume_tailor.domain.job_discovery.models import EligibilityStatus


def evaluation_sort_key(
    *,
    fit_grade: FitGrade,
    diagnostic_total: float,
    eligibility: EligibilityStatus,
    posted_at: datetime | None,
    stable_id: str,
) -> tuple[int, float, int, float, str]:
    freshness = posted_at.timestamp() if posted_at is not None else -1.0e18
    return (
        grade_rank(fit_grade),
        -diagnostic_total,
        0 if eligibility is EligibilityStatus.ELIGIBLE else 1,
        -freshness,
        stable_id,
    )


__all__ = ["evaluation_sort_key"]
