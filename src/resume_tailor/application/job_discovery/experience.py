from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from threading import RLock
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from resume_tailor.application.job_discovery.background_refresh import (
    BackgroundJobsRefreshCoordinator,
    BackgroundRefreshSnapshot,
    refresh_context_key,
)
from resume_tailor.application.job_discovery.confirmation import (
    ConfirmJobSearchPreferencesService,
)
from resume_tailor.application.job_discovery.filtering import (
    BrowseSeniority,
    classify_browse_seniority,
)
from resume_tailor.application.job_discovery.handoff import TailoringHandoff
from resume_tailor.application.job_discovery.preferences import (
    ProfileNotFoundError,
    SuggestJobSearchPreferencesService,
)
from resume_tailor.application.job_discovery.profile_queries import (
    ReviewedProfileQueryResult,
    ReviewedProfileQueryService,
)
from resume_tailor.application.job_discovery.queries import (
    GetCurrentJobSearchPreferencesService,
    GetJobFeedService,
    JobFeedDetails,
    PreferencesNotFoundError,
)
from resume_tailor.application.job_discovery.refresh import RefreshJobDiscoveryService
from resume_tailor.application.job_discovery.saved import (
    CheckSavedJobAvailabilityService,
    SaveJobService,
)
from resume_tailor.domain.job_discovery.models import (
    DiscoveredJob,
    DiscoveryRun,
    EligibilityStatus,
    FitGrade,
    JobRecommendation,
    JobSearchPreferences,
    JobSearchPreferenceSuggestion,
    RecommendationVisibility,
    SavedJob,
    VerificationConfidence,
    VerificationStatus,
    WorkArrangement,
)
from resume_tailor.domain.job_discovery.queries import FeedKind
from resume_tailor.ports.interfaces import MasterProfileRepository


class JobsApplicationServices(Protocol):
    suggest_preferences: SuggestJobSearchPreferencesService
    refresh: RefreshJobDiscoveryService
    confirm_preferences: ConfirmJobSearchPreferencesService | None
    current_preferences: GetCurrentJobSearchPreferencesService | None
    feed_queries: GetJobFeedService | None
    save: SaveJobService | None
    check_saved_availability: CheckSavedJobAvailabilityService | None


class DiscoveredJobPort(Protocol):
    def get(self, job_id: str) -> DiscoveredJob | None: ...


class HandoffPort(Protocol):
    def from_discovered(self, job_id: str, *, profile_id: str) -> TailoringHandoff: ...

    def from_saved(self, saved_id: str, *, profile_id: str, user_id: str) -> TailoringHandoff: ...


class RecommendationView(BaseModel):
    model_config = ConfigDict(frozen=True)

    recommendation_id: str
    job_id: str
    feed_kind: FeedKind
    title: str
    company: str
    source_company: str
    source_id: str
    location_label: str
    work_arrangement: WorkArrangement
    posted_at: datetime | None
    posting_age_label: str
    first_seen_at: datetime | None = None
    first_seen_label: str = "First seen unknown"
    checked_at: datetime | None = None
    checked_label: str = "Not checked recently"
    grade: FitGrade
    eligibility: EligibilityStatus
    provisional: bool
    verification_status: VerificationStatus
    verification_confidence: VerificationConfidence
    freshness_label: str
    reasons: list[str] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    unresolved_facts: list[str] = Field(default_factory=list)
    official_url: str | None
    saved: bool = False
    primary_role_family: str | None = None
    visibility: RecommendationVisibility
    browse_seniority: BrowseSeniority = BrowseSeniority.UNKNOWN


class JobDetailView(RecommendationView):
    description: str


class FeedView(BaseModel):
    model_config = ConfigDict(frozen=True)

    feed_kind: FeedKind
    visible: list[RecommendationView]
    excluded_count: int
    source_warnings: list[str] = Field(default_factory=list)
    status: str | None = None
    last_refresh_at: datetime | None = None
    source_count: int = 0
    retrieved_count: int = 0
    normalized_count: int = 0
    scored_count: int = 0
    returned_count: int = 0


class FeedRefreshView(BaseModel):
    feed: FeedView
    run: DiscoveryRun


class SavedJobView(BaseModel):
    model_config = ConfigDict(frozen=True)

    saved_id: str
    job_id: str
    title: str
    company: str
    saved_at: datetime
    location_label: str
    work_arrangement: WorkArrangement
    description: str
    official_url: str | None
    availability: str
    checked_at: datetime | None
    source_id: str
    snapshot: SavedJob
    posted_at: datetime | None = None
    browse_seniority: BrowseSeniority = BrowseSeniority.UNKNOWN


class JobsExperienceService:
    """Typed page-facing boundary for the dedicated Jobs workspace."""

    def __init__(
        self,
        *,
        profiles: MasterProfileRepository,
        services: JobsApplicationServices,
        jobs: DiscoveredJobPort,
        handoff: HandoffPort,
        now: Callable[[], datetime] | None = None,
        refresh_coordinator: BackgroundJobsRefreshCoordinator | None = None,
    ) -> None:
        self._profiles = ReviewedProfileQueryService(profiles)
        self._services = services
        self._jobs = jobs
        self._handoff = handoff
        self._now = now or (lambda: datetime.now(UTC))
        self._refresh_coordinator = refresh_coordinator or BackgroundJobsRefreshCoordinator()
        self._view_cache_lock = RLock()
        self._feed_cache: dict[tuple[str, FeedKind, str | None], FeedView] = {}
        self._excluded_cache: dict[
            tuple[str, FeedKind, str | None], list[RecommendationView]
        ] = {}
        self._saved_cache: dict[str, list[SavedJobView]] = {}

    def list_reviewed_profiles(self) -> ReviewedProfileQueryResult:
        return self._profiles.list_reviewed_profiles()

    def now(self) -> datetime:
        """Return the application clock used for deterministic browse projections."""

        return self._now()

    def suggest_preferences(self, profile_id: str) -> JobSearchPreferenceSuggestion:
        return self._services.suggest_preferences.suggest(
            self._profile_user_id(profile_id), profile_id, generated_at=self._now()
        )

    def get_preferences(self, profile_id: str) -> JobSearchPreferences | None:
        service = self._services.current_preferences
        if service is None:
            return None
        try:
            return service.get(self._profile_user_id(profile_id), profile_id)
        except PreferencesNotFoundError:
            return None

    def confirm_preferences(self, preferences: JobSearchPreferences) -> JobSearchPreferences:
        if self._services.confirm_preferences is None:
            raise RuntimeError("Preference confirmation is unavailable.")
        return self._services.confirm_preferences.confirm(preferences)

    def load_feed(
        self, profile_id: str, feed_kind: FeedKind, *, sector: str | None = None
    ) -> FeedView:
        cache_key = (profile_id, feed_kind, sector)
        with self._view_cache_lock:
            cached = self._feed_cache.get(cache_key)
            if cached is not None:
                return cached.model_copy(deep=True)
        if self._services.feed_queries is None:
            raise RuntimeError("Feed retrieval is unavailable.")
        user_id = self._profile_user_id(profile_id)
        details = (
            self._services.feed_queries.get(
                user_id,
                feed_kind,
                profile_id=profile_id,
                excluded_only=False,
            )
            if sector is None
            else self._services.feed_queries.get(
                user_id,
                feed_kind,
                profile_id=profile_id,
                sector=sector,
                excluded_only=False,
            )
        )
        view = self._feed_view(details, user_id=user_id)
        with self._view_cache_lock:
            self._feed_cache[cache_key] = view.model_copy(deep=True)
        return view

    def load_excluded(
        self, profile_id: str, feed_kind: FeedKind, *, sector: str | None = None
    ) -> list[RecommendationView]:
        cache_key = (profile_id, feed_kind, sector)
        with self._view_cache_lock:
            cached = self._excluded_cache.get(cache_key)
            if cached is not None:
                return [item.model_copy(deep=True) for item in cached]
        if self._services.feed_queries is None:
            raise RuntimeError("Feed retrieval is unavailable.")
        user_id = self._profile_user_id(profile_id)
        details = (
            self._services.feed_queries.get(
                user_id,
                feed_kind,
                profile_id=profile_id,
                excluded_only=True,
            )
            if sector is None
            else self._services.feed_queries.get(
                user_id,
                feed_kind,
                profile_id=profile_id,
                sector=sector,
                excluded_only=True,
            )
        )
        view = [self._recommendation_view(item) for item in details.items]
        with self._view_cache_lock:
            self._excluded_cache[cache_key] = [item.model_copy(deep=True) for item in view]
        return view

    def refresh_tailored(self, profile_id: str) -> FeedRefreshView:
        preferences = self.get_preferences(profile_id)
        if preferences is None:
            raise PreferencesNotFoundError(
                f"Preferences for profile {profile_id!r} were not found."
            )
        run = self._services.refresh.refresh(
            self._profile_user_id(profile_id), profile_id, preferences, started_at=self._now()
        )
        self._invalidate_profile_views(profile_id)
        return FeedRefreshView(feed=self.load_feed(profile_id, FeedKind.TAILORED), run=run)

    def refresh_explore(self, profile_id: str, sector: str) -> FeedRefreshView:
        run = self._services.refresh.refresh_explore(
            self._profile_user_id(profile_id),
            sectors=[sector],
            profile_id=profile_id,
            started_at=self._now(),
        )
        self._invalidate_profile_views(profile_id)
        return FeedRefreshView(
            feed=self.load_feed(profile_id, FeedKind.EXPLORE, sector=sector), run=run
        )

    def start_tailored_refresh(self, profile_id: str) -> BackgroundRefreshSnapshot:
        key = refresh_context_key(profile_id, FeedKind.TAILORED.value)
        return self._refresh_coordinator.start(key, lambda: self.refresh_tailored(profile_id))

    def start_explore_refresh(
        self, profile_id: str, sector: str
    ) -> BackgroundRefreshSnapshot:
        key = refresh_context_key(profile_id, FeedKind.EXPLORE.value, sector=sector)
        return self._refresh_coordinator.start(
            key, lambda: self.refresh_explore(profile_id, sector)
        )

    def refresh_state(
        self,
        profile_id: str,
        feed_kind: FeedKind,
        *,
        sector: str | None = None,
    ) -> BackgroundRefreshSnapshot | None:
        return self._refresh_coordinator.get(
            refresh_context_key(profile_id, feed_kind.value, sector=sector)
        )

    def get_job_detail(
        self, profile_id: str, feed_kind: FeedKind, job_id: str, *, sector: str | None = None
    ) -> JobDetailView | None:
        feed = self.load_feed(profile_id, feed_kind, sector=sector)
        recommendation = next((item for item in feed.visible if item.job_id == job_id), None)
        if recommendation is None:
            return None
        job = self._jobs.get(job_id)
        if job is None:
            return None
        return JobDetailView(
            **recommendation.model_dump(),
            description=job.description,
        )

    def save_job(self, job_id: str, profile_id: str) -> SavedJob:
        if self._services.save is None:
            raise RuntimeError("Saved-job persistence is unavailable.")
        saved = self._services.save.save(
            self._profile_user_id(profile_id), job_id, saved_at=self._now()
        )
        self._invalidate_profile_views(profile_id)
        return saved

    def remove_saved_job(self, saved_id: str, profile_id: str) -> SavedJob:
        if self._services.save is None:
            raise RuntimeError("Saved-job persistence is unavailable.")
        removed = self._services.save.remove(self._profile_user_id(profile_id), saved_id)
        self._invalidate_profile_views(profile_id)
        return removed

    def list_saved_jobs(self, profile_id: str) -> list[SavedJobView]:
        if self._services.save is None:
            return []
        with self._view_cache_lock:
            cached = self._saved_cache.get(profile_id)
            if cached is not None:
                return [item.model_copy(deep=True) for item in cached]
        view = [
            _saved_view(saved)
            for saved in self._services.save.list(self._profile_user_id(profile_id))
        ]
        with self._view_cache_lock:
            self._saved_cache[profile_id] = [item.model_copy(deep=True) for item in view]
        return view

    def check_saved_job_availability(self, saved_id: str, profile_id: str) -> SavedJobView:
        if self._services.check_saved_availability is None:
            raise RuntimeError("Saved-job availability is unavailable.")
        saved = self._services.check_saved_availability.check(
            self._profile_user_id(profile_id), saved_id, checked_at=self._now()
        )
        with self._view_cache_lock:
            self._saved_cache.pop(profile_id, None)
        return _saved_view(saved)

    def _invalidate_profile_views(self, profile_id: str) -> None:
        """Invalidate only delivery projections; ranking and stored results are untouched."""

        with self._view_cache_lock:
            self._feed_cache = {
                key: value for key, value in self._feed_cache.items() if key[0] != profile_id
            }
            self._excluded_cache = {
                key: value for key, value in self._excluded_cache.items() if key[0] != profile_id
            }
            self._saved_cache.pop(profile_id, None)

    def prepare_tailoring(self, job_id: str, profile_id: str) -> TailoringHandoff:
        return self._handoff.from_discovered(job_id, profile_id=profile_id)

    def prepare_saved_tailoring(self, saved_id: str, profile_id: str) -> TailoringHandoff:
        return self._handoff.from_saved(
            saved_id,
            profile_id=profile_id,
            user_id=self._profile_user_id(profile_id),
        )

    def _feed_view(self, details: JobFeedDetails, *, user_id: str) -> FeedView:
        run = details.run
        warnings = [] if run is None else [*run.warnings, *run.source_warnings, *run.error_messages]
        saved_ids = self._saved_ids(user_id)
        return FeedView(
            feed_kind=details.feed_kind,
            visible=[
                self._recommendation_view(item).model_copy(
                    update={"saved": item.job_id in saved_ids}
                )
                for item in details.items
            ],
            excluded_count=details.excluded_count,
            source_warnings=list(dict.fromkeys(warnings)),
            status=run.status.value if run else None,
            last_refresh_at=run.completed_at if run else None,
            source_count=run.source_count if run else 0,
            retrieved_count=run.retrieved_count if run else 0,
            normalized_count=run.normalized_count if run else 0,
            scored_count=run.scored_count if run else 0,
            returned_count=run.returned_count if run else 0,
        )

    def _recommendation_view(self, recommendation: JobRecommendation) -> RecommendationView:
        job = self._jobs.get(recommendation.job_id)
        return _recommendation_view(recommendation, job, now=self._now())

    def _saved_ids(self, user_id: str) -> set[str]:
        if self._services.save is None:
            return set()
        return {saved.job_id for saved in self._services.save.list(user_id)}

    def _profile_user_id(self, profile_id: str) -> str:
        profile = self._profiles.get_reviewed_profile(profile_id)
        if profile is None:
            raise ProfileNotFoundError(
                f"Reviewed profile {profile_id!r} is unavailable from the canonical "
                "profile repository."
            )
        return profile.user_id


def _recommendation_view(
    recommendation: JobRecommendation,
    job: DiscoveredJob | None,
    *,
    now: datetime,
) -> RecommendationView:
    posted_at = job.posted_at if job else None
    provenance = job.source_provenance if job else []
    first_seen_at = getattr(job, "first_seen_at", None) if job else None
    if first_seen_at is None:
        first_seen_at = min((item.fetched_at for item in provenance), default=None)
    checked_at = job.fetched_at if job else None
    location = job.location.raw if job else "Location unavailable"
    company = job.company_name if job else "Company unavailable"
    source_company = job.source.company_name if job else company
    source_id = job.source.source_id if job else "unknown"
    work_arrangement = job.work_arrangement if job else WorkArrangement.UNKNOWN
    verification_status = job.verification_status if job else VerificationStatus.UNVERIFIED
    verification_confidence = job.verification_confidence if job else VerificationConfidence.LOW
    grade = recommendation.score.fit_grade or FitGrade.WEAK
    return RecommendationView(
        recommendation_id=recommendation.id,
        job_id=recommendation.job_id,
        feed_kind=recommendation.feed_kind,
        title=job.title if job else recommendation.job_id,
        company=company,
        source_company=source_company,
        source_id=source_id,
        location_label=location or "Location unknown",
        work_arrangement=work_arrangement,
        posted_at=posted_at,
        posting_age_label=_posting_age(posted_at, now),
        first_seen_at=first_seen_at,
        first_seen_label=_timestamp_label("First seen", first_seen_at, now, "First seen unknown"),
        checked_at=checked_at,
        checked_label=_timestamp_label("Checked", checked_at, now, "Not checked recently"),
        grade=grade,
        eligibility=recommendation.eligibility.status,
        provisional=recommendation.provisional,
        verification_status=verification_status,
        verification_confidence=verification_confidence,
        freshness_label=_freshness(posted_at, verification_status),
        reasons=list(recommendation.reasons),
        supporting_evidence=list(recommendation.reasons),
        gaps=list(recommendation.gaps),
        unresolved_facts=list(recommendation.unresolved_facts),
        official_url=job.official_url if job else None,
        primary_role_family=(
            recommendation.primary_role_family.value if recommendation.primary_role_family else None
        ),
        visibility=recommendation.visibility,
        browse_seniority=classify_browse_seniority(
            job.title if job else recommendation.job_id,
            job.requirements.job_level if job else None,
        ),
    )


def _saved_view(saved: SavedJob) -> SavedJobView:
    snapshot = saved.posting_snapshot
    return SavedJobView(
        saved_id=saved.id,
        job_id=saved.job_id,
        title=snapshot.title,
        company=snapshot.company_name,
        saved_at=saved.saved_at,
        location_label=snapshot.location.raw or "Location unknown",
        work_arrangement=snapshot.work_arrangement,
        description=snapshot.description,
        official_url=snapshot.official_url or None,
        availability=saved.availability.value,
        checked_at=saved.checked_at,
        source_id=snapshot.source.source_id,
        snapshot=saved,
        posted_at=snapshot.posted_at,
        browse_seniority=classify_browse_seniority(
            snapshot.title, snapshot.requirements.job_level
        ),
    )


def _posting_age(posted_at: datetime | None, now: datetime) -> str:
    if posted_at is None:
        return "Posted date unknown"
    days = max(0, (now.date() - posted_at.date()).days)
    return "Posted today" if days == 0 else f"Posted {days} days ago"


def _freshness(posted_at: datetime | None, verification: VerificationStatus) -> str:
    if verification is VerificationStatus.VERIFIED_ACTIVE:
        return "Verified active"
    if posted_at is None:
        return "Freshness unknown"
    return "Posting date available"


def _timestamp_label(prefix: str, timestamp: datetime | None, now: datetime, fallback: str) -> str:
    if timestamp is None:
        return fallback
    days = max(0, (now.date() - timestamp.date()).days)
    if days == 0:
        return f"{prefix} today"
    if days == 1:
        return f"{prefix} 1 day ago"
    return f"{prefix} {days} days ago"


__all__ = [
    "FeedRefreshView",
    "FeedView",
    "JobDetailView",
    "JobsExperienceService",
    "RecommendationView",
    "SavedJobView",
]
