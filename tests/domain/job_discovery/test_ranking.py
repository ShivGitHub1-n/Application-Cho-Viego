from __future__ import annotations

from datetime import UTC, datetime

from resume_tailor.domain.job_discovery.grading import FitGrade
from resume_tailor.domain.job_discovery.models import EligibilityStatus
from resume_tailor.domain.job_discovery.ranking import evaluation_sort_key


def test_known_eligible_precedes_unknown_with_equal_fit() -> None:
    eligible = evaluation_sort_key(
        fit_grade=FitGrade.GOOD,
        diagnostic_total=70,
        eligibility=EligibilityStatus.ELIGIBLE,
        posted_at=datetime(2026, 7, 1, tzinfo=UTC),
        stable_id="z",
    )
    unknown = evaluation_sort_key(
        fit_grade=FitGrade.GOOD,
        diagnostic_total=70,
        eligibility=EligibilityStatus.UNKNOWN,
        posted_at=datetime(2026, 7, 23, tzinfo=UTC),
        stable_id="a",
    )

    assert eligible < unknown


def test_interests_and_preferred_companies_are_absent_from_ranking_key() -> None:
    first = evaluation_sort_key(
        fit_grade=FitGrade.WEAK,
        diagnostic_total=55,
        eligibility=EligibilityStatus.ELIGIBLE,
        posted_at=None,
        stable_id="a",
    )
    second = evaluation_sort_key(
        fit_grade=FitGrade.WEAK,
        diagnostic_total=55,
        eligibility=EligibilityStatus.ELIGIBLE,
        posted_at=None,
        stable_id="b",
    )

    assert first < second
