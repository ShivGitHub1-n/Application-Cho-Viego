from __future__ import annotations

from datetime import UTC, datetime

from resume_tailor.domain.job_discovery.evaluation import (
    InternalDiagnostics,
    JobEvaluation,
    ProvisionalAssessment,
    RoleRelevanceAssessment,
)
from resume_tailor.domain.job_discovery.feeds import (
    FeedVisibility,
    rank_feed_candidates,
)
from resume_tailor.domain.job_discovery.grading import FitGrade
from resume_tailor.domain.job_discovery.models import (
    ConnectorType,
    EligibilityAssessment,
    EligibilityStatus,
    SourceJobRecord,
    SupportedJobSource,
    VerificationConfidence,
    WorkArrangement,
)
from resume_tailor.domain.job_discovery.normalization import normalize_job_record
from resume_tailor.domain.job_discovery.queries import FeedKind

WHEN = datetime(2026, 7, 24, 12, tzinfo=UTC)


def _job(job_id: str, posted_at: datetime | None):
    source = SupportedJobSource(
        source_id="source",
        connector_type=ConnectorType.GREENHOUSE,
        company_name="Acme",
        board_token="acme",
        enabled=True,
        official_base_url="https://boards.greenhouse.io",
    )
    return normalize_job_record(
        SourceJobRecord(
            external_job_id=job_id,
            title="Engineer",
            company_name="Acme",
            description="Build systems.",
            official_url=f"https://boards.greenhouse.io/acme/jobs/{job_id}",
            location_raw="Toronto",
            work_arrangement=WorkArrangement.REMOTE,
            posted_at=posted_at,
        ),
        source,
        fetched_at=WHEN,
    )


def _evaluation(job, grade: FitGrade, total: float, status=EligibilityStatus.ELIGIBLE):
    return JobEvaluation(
        job_id=job.id,
        eligibility=EligibilityAssessment(
            status=status,
            verification_confidence=VerificationConfidence.HIGH,
        ),
        role_relevance=RoleRelevanceAssessment(relevant=True),
        fit_grade=grade,
        diagnostics=InternalDiagnostics(total=total),
        provisional=ProvisionalAssessment(),
    )


def test_tailored_fit_order_hides_excluded_but_retains_excluded_count() -> None:
    candidates = [
        (_job("weak", WHEN), _evaluation(_job("weak", WHEN), FitGrade.WEAK, 10)),
        (_job("excellent", None), _evaluation(_job("excellent", None), FitGrade.EXCELLENT, 1)),
        (_job("good", WHEN), _evaluation(_job("good", WHEN), FitGrade.GOOD, 50)),
        (
            _job("excluded", WHEN),
            _evaluation(_job("excluded", WHEN), FitGrade.DONT_MATCH, 100),
        ),
    ]

    result = rank_feed_candidates(candidates, feed_kind=FeedKind.TAILORED)

    assert [item.job.external_job_id for item in result.items] == [
        "excellent",
        "good",
        "weak",
    ]
    assert result.excluded_count == 1
    assert result.visibility_by_job[candidates[-1][0].id] is FeedVisibility.EXCLUDED


def test_explore_known_posted_dates_precede_unknown_and_fit_breaks_date_ties() -> None:
    older = _job("older", datetime(2026, 7, 1, tzinfo=UTC))
    newer = _job("newer", datetime(2026, 7, 23, tzinfo=UTC))
    unknown = _job("unknown", None)
    result = rank_feed_candidates(
        [
            (older, _evaluation(older, FitGrade.EXCELLENT, 90)),
            (newer, _evaluation(newer, FitGrade.WEAK, 10)),
            (unknown, _evaluation(unknown, FitGrade.EXCELLENT, 100)),
        ],
        feed_kind=FeedKind.EXPLORE,
    )

    assert [item.job.external_job_id for item in result.items] == [
        "newer",
        "older",
        "unknown",
    ]
