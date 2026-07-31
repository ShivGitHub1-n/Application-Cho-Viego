"""Feed-specific application assembly over the frozen evaluator output."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from resume_tailor.domain.job_discovery.evaluation import JobEvaluation
from resume_tailor.domain.job_discovery.feeds import (
    FeedVisibility,
    rank_feed_candidates,
)
from resume_tailor.domain.job_discovery.ids import recommendation_id
from resume_tailor.domain.job_discovery.models import (
    DiscoveredJob,
    JobRecommendation,
    JobSearchPreferences,
    RecommendationGroup,
    RecommendationVisibility,
)
from resume_tailor.domain.job_discovery.queries import FeedKind
from resume_tailor.domain.job_discovery.scoring import breakdown_from_evaluation
from resume_tailor.domain.models import MasterProfile


@dataclass(frozen=True)
class FeedAssemblyResult:
    recommendations: list[JobRecommendation]
    excluded_count: int


class FeedAssemblyService:
    """Turn all frozen evaluations into persistable feed records."""

    def build_recommendations(
        self,
        run_id: str,
        *,
        profile: MasterProfile,
        preferences: JobSearchPreferences,
        assessed: Sequence[tuple[DiscoveredJob, JobEvaluation]],
        feed_kind: FeedKind,
        created_at: datetime,
    ) -> FeedAssemblyResult:
        ranked = rank_feed_candidates(
            assessed,
            feed_kind=feed_kind,
            include_excluded=True,
            preferred_companies=set(preferences.preferred_companies),
        )
        recommendations: list[JobRecommendation] = []
        for item in ranked.items:
            job = item.job
            evaluation = item.evaluation
            score = breakdown_from_evaluation(evaluation)
            visibility = (
                RecommendationVisibility.VISIBLE
                if item.visibility is FeedVisibility.VISIBLE
                else RecommendationVisibility.EXCLUDED
            )
            group = (
                RecommendationGroup.PRIMARY
                if job.role_family in preferences.role_family_priority
                else RecommendationGroup.FALLBACK
            )
            recommendations.append(
                JobRecommendation(
                    id=recommendation_id(
                        run_id,
                        job.id,
                        profile.version,
                        preferences.version,
                    ),
                    run_id=run_id,
                    user_id=profile.user_id,
                    profile_id=profile.id,
                    profile_version=profile.version,
                    preference_version=preferences.version,
                    job_id=job.id,
                    group=group,
                    primary_role_family=job.role_family,
                    eligibility=evaluation.eligibility,
                    score=score,
                    reasons=[reason.statement for reason in evaluation.positive_reasons],
                    gaps=[gap.statement for gap in evaluation.material_gaps],
                    rank=item.rank,
                    created_at=created_at,
                    evaluation_policy_version=evaluation.evaluation_policy_version,
                    feed_kind=feed_kind,
                    visibility=visibility,
                    unresolved_facts=[
                        *[fact.statement for fact in evaluation.unresolved_facts],
                        *evaluation.eligibility.unresolved_facts,
                    ],
                    provisional=evaluation.provisional.is_provisional,
                    earlier_policy=False,
                )
            )
        return FeedAssemblyResult(
            recommendations=recommendations,
            excluded_count=ranked.excluded_count,
        )


FeedService = FeedAssemblyService


__all__ = ["FeedAssemblyResult", "FeedAssemblyService", "FeedService"]

