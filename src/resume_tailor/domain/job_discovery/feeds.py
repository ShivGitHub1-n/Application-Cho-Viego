"""Visibility and deterministic ordering for the two Jobs feeds."""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, Field

from resume_tailor.domain.job_discovery.evaluation import JobEvaluation
from resume_tailor.domain.job_discovery.grading import grade_rank
from resume_tailor.domain.job_discovery.models import (
    DiscoveredJob,
    EligibilityStatus,
    FitGrade,
)
from resume_tailor.domain.job_discovery.queries import FeedKind


class FeedVisibility(StrEnum):
    VISIBLE = "visible"
    EXCLUDED = "excluded"


class RankedFeedItem(BaseModel):
    job: DiscoveredJob
    evaluation: JobEvaluation
    visibility: FeedVisibility
    rank: int


class FeedRankingResult(BaseModel):
    items: list[RankedFeedItem] = Field(default_factory=list)
    excluded_count: int = 0
    visibility_by_job: dict[str, FeedVisibility] = Field(default_factory=dict)


def rank_feed_candidates(
    candidates: Sequence[tuple[DiscoveredJob, JobEvaluation]],
    *,
    feed_kind: FeedKind,
    include_excluded: bool = False,
    preferred_companies: set[str] | None = None,
) -> FeedRankingResult:
    """Rank every evaluation, retaining excluded visibility for persistence."""

    preferred = {value.casefold().strip() for value in (preferred_companies or set())}
    ranked = sorted(
        candidates,
        key=lambda item: _sort_key(
            item[0], item[1], feed_kind=feed_kind, preferred_companies=preferred
        ),
    )
    visibility_by_job = {
        job.id: _visibility(evaluation, feed_kind=feed_kind) for job, evaluation in candidates
    }
    excluded_count = sum(value is FeedVisibility.EXCLUDED for value in visibility_by_job.values())
    items: list[RankedFeedItem] = []
    for rank, (job, evaluation) in enumerate(ranked, start=1):
        visibility = visibility_by_job[job.id]
        if visibility is FeedVisibility.EXCLUDED and not include_excluded:
            continue
        items.append(
            RankedFeedItem(
                job=job,
                evaluation=evaluation,
                visibility=visibility,
                rank=rank,
            )
        )
    return FeedRankingResult(
        items=items,
        excluded_count=excluded_count,
        visibility_by_job=visibility_by_job,
    )


def _visibility(evaluation: JobEvaluation, *, feed_kind: FeedKind) -> FeedVisibility:
    if feed_kind is FeedKind.EXPLORE:
        # Explore is a sector browse surface. Fit and eligibility remain visible
        # annotations; they do not remove a retrieved sector role.
        return FeedVisibility.VISIBLE
    if (
        evaluation.fit_grade is FitGrade.DONT_MATCH
        or evaluation.eligibility.status is EligibilityStatus.INELIGIBLE
    ):
        return FeedVisibility.EXCLUDED
    return FeedVisibility.VISIBLE


def _sort_key(
    job: DiscoveredJob,
    evaluation: JobEvaluation,
    *,
    feed_kind: FeedKind,
    preferred_companies: set[str],
) -> tuple[object, ...]:
    grade = grade_rank(evaluation.fit_grade)
    diagnostic = -evaluation.diagnostics.total
    eligibility = 0 if evaluation.eligibility.status is EligibilityStatus.ELIGIBLE else 1
    preferred = 0 if job.company_name.casefold().strip() in preferred_companies else 1
    stable = job.id
    if feed_kind is FeedKind.EXPLORE:
        freshness = -(job.posted_at.timestamp()) if job.posted_at else float("inf")
        return (
            0 if job.posted_at is not None else 1,
            freshness,
            grade,
            diagnostic,
            stable,
        )
    freshness = -(job.posted_at.timestamp()) if job.posted_at else float("inf")
    return (grade, diagnostic, eligibility, freshness, preferred, stable)


__all__ = [
    "FeedRankingResult",
    "FeedVisibility",
    "RankedFeedItem",
    "rank_feed_candidates",
]

