from __future__ import annotations

from dataclasses import dataclass

from resume_tailor.domain.job_discovery.models import (
    DiscoveryRun,
    JobRecommendation,
    JobSearchPreferences,
    RecommendationVisibility,
)
from resume_tailor.domain.job_discovery.queries import FeedKind as _FeedKind
from resume_tailor.ports.job_discovery import (
    DiscoveryRunRepository,
    JobRecommendationRepository,
    JobSearchPreferencesRepository,
)


class PreferencesNotFoundError(ValueError):
    pass


class DiscoveryRunNotFoundError(ValueError):
    pass


class GetCurrentJobSearchPreferencesService:
    def __init__(self, preferences: JobSearchPreferencesRepository) -> None:
        self._preferences = preferences

    def get(self, user_id: str, profile_id: str) -> JobSearchPreferences:
        preferences = self._preferences.get_current(user_id, profile_id)
        if preferences is None:
            raise PreferencesNotFoundError(
                f"Preferences for profile {profile_id!r} were not found."
            )
        return preferences


@dataclass(frozen=True)
class DiscoveryRunDetails:
    run: DiscoveryRun
    recommendations: list[JobRecommendation]


class GetDiscoveryRunService:
    def __init__(
        self,
        runs: DiscoveryRunRepository,
        recommendations: JobRecommendationRepository,
    ) -> None:
        self._runs = runs
        self._recommendations = recommendations

    def get(self, user_id: str, run_id: str) -> DiscoveryRunDetails:
        run = self._runs.get(run_id)
        if run is None or run.user_id != user_id:
            raise DiscoveryRunNotFoundError(f"Discovery run {run_id!r} was not found.")
        return DiscoveryRunDetails(
            run=run,
            recommendations=self._recommendations.list_for_run(run_id),
        )


@dataclass(frozen=True)
class JobFeedDetails:
    feed_kind: _FeedKind
    items: list[JobRecommendation]
    excluded_count: int
    run: DiscoveryRun | None = None


class GetJobFeedService:
    def __init__(
        self,
        recommendations: JobRecommendationRepository,
        runs: DiscoveryRunRepository | None = None,
    ) -> None:
        self._recommendations = recommendations
        self._runs = runs

    def get(
        self,
        user_id: str,
        feed_kind: _FeedKind,
        *,
        profile_id: str | None = None,
        sector: str | None = None,
        excluded_only: bool = False,
    ) -> JobFeedDetails:
        all_items = self._recommendations.list_for_feed(
            user_id, feed_kind.value, include_excluded=True
        )
        if profile_id is not None:
            all_items = [item for item in all_items if item.profile_id == profile_id]
        if sector is not None and feed_kind is _FeedKind.EXPLORE:
            all_items = [item for item in all_items if item.explore_sector == sector]
        excluded = [
            item for item in all_items if item.visibility is RecommendationVisibility.EXCLUDED
        ]
        latest_run_id = None
        if all_items:
            latest_created_at = max(item.created_at for item in all_items)
            latest_run_id = max(
                item.run_id for item in all_items if item.created_at == latest_created_at
            )
            all_items = [item for item in all_items if item.run_id == latest_run_id]
            excluded = [
                item
                for item in all_items
                if item.visibility is RecommendationVisibility.EXCLUDED
            ]
        items = excluded if excluded_only else [
            item for item in all_items if item.visibility is RecommendationVisibility.VISIBLE
        ]
        return JobFeedDetails(
            feed_kind=feed_kind,
            items=items,
            excluded_count=len(excluded),
            run=self._runs.get(latest_run_id) if self._runs and latest_run_id else None,
        )


__all__ = [
    "DiscoveryRunDetails",
    "DiscoveryRunNotFoundError",
    "GetCurrentJobSearchPreferencesService",
    "GetJobFeedService",
    "JobFeedDetails",
    "GetDiscoveryRunService",
    "PreferencesNotFoundError",
]
