from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import streamlit as st

from resume_tailor.application.job_discovery.filtering import BrowseSeniority
from resume_tailor.domain.job_discovery.models import (
    EligibilityStatus,
    FitGrade,
    JobLevel,
    JobSearchPreferences,
    JobSearchPreferenceSuggestion,
    NormalizedLocation,
    RecommendationVisibility,
    VerificationConfidence,
    VerificationStatus,
    WorkArrangement,
    WorkArrangementPreferenceMode,
)
from resume_tailor.domain.job_discovery.queries import FeedKind
from resume_tailor.domain.models import RoleFamily
from resume_tailor.frontend.app_shell import render_application_shell
from resume_tailor.frontend.jobs_filter_view import clear_browse_state
from resume_tailor.frontend.jobs_page import render_jobs_page, render_jobs_unavailable

st.set_page_config(page_title="Jobs visual harness", layout="wide")

SCENARIOS = (
    "visible-grades",
    "visual-tailored-active",
    "visual-tailored-expanded",
    "visual-explore-detail",
    "visual-saved-filtering",
    "excluded-results",
    "partial-source-warning",
    "all-sources-failure",
    "no-reviewed-profile",
    "no-confirmed-preferences",
    "no-visible-results",
    "saved-available",
    "saved-unavailable",
    "preference-suggestion",
    "tailoring-handoff",
    "long-content",
    "database-unavailable",
)


@dataclass(frozen=True)
class OfflineProfile:
    profile_id: str
    label: str
    user_id: str


@dataclass(frozen=True)
class OfflineRecommendation:
    job_id: str
    recommendation_id: str
    title: str
    company: str
    source_company: str
    source_id: str
    location_label: str
    work_arrangement: WorkArrangement
    posted_at: datetime | None
    posting_age_label: str
    grade: FitGrade
    eligibility: EligibilityStatus
    provisional: bool
    verification_status: VerificationStatus
    verification_confidence: VerificationConfidence
    freshness_label: str
    reasons: list[str]
    supporting_evidence: list[str]
    gaps: list[str]
    unresolved_facts: list[str]
    official_url: str | None
    saved: bool
    primary_role_family: str
    visibility: RecommendationVisibility
    first_seen_label: str = "First seen unknown"
    checked_label: str = "Not checked recently"
    browse_seniority: BrowseSeniority = BrowseSeniority.UNKNOWN


@dataclass(frozen=True)
class OfflineDetail:
    recommendation: OfflineRecommendation
    description: str

    def __getattr__(self, name: str):
        return getattr(self.recommendation, name)


@dataclass(frozen=True)
class OfflineFeed:
    feed_kind: FeedKind
    visible: list[OfflineRecommendation]
    excluded_count: int
    source_warnings: list[str]
    status: str
    last_refresh_at: datetime
    retrieved_count: int = 0


@dataclass(frozen=True)
class OfflineRun:
    status: str


@dataclass(frozen=True)
class OfflineRefresh:
    feed: OfflineFeed
    run: OfflineRun


@dataclass(frozen=True)
class OfflineSaved:
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
    snapshot: object | None = None
    posted_at: datetime | None = None
    browse_seniority: BrowseSeniority = BrowseSeniority.UNKNOWN


@dataclass(frozen=True)
class OfflineHandoff:
    profile_id: str
    title: str
    description: str


class OfflineJobsExperience:
    """Deterministic typed façade used only by the offline browser harness."""

    def __init__(self, scenario: str = "visible-grades") -> None:
        self.scenario = scenario
        self.profile = OfflineProfile("profile-1", "Avery Engineer", "local-user")
        self.other_profile = OfflineProfile("profile-2", "Second Engineer", "local-user")
        self.visible = [
            self._recommendation(
                "excellent-1", FitGrade.EXCELLENT, EligibilityStatus.ELIGIBLE, False
            ),
            self._recommendation("good-1", FitGrade.GOOD, EligibilityStatus.UNKNOWN, True),
            self._recommendation("weak-1", FitGrade.WEAK, EligibilityStatus.ELIGIBLE, False),
        ]
        self.excluded = [
            self._recommendation(
                "excluded-1", FitGrade.DONT_MATCH, EligibilityStatus.INELIGIBLE, False
            )
        ]
        if scenario == "long-content":
            self.visible[0] = self.visible[0].__class__(
                **{
                    **self.visible[0].__dict__,
                    "title": (
                        "An exceptionally long embedded firmware and hardware "
                        "validation engineering role title that must wrap"
                    ),
                    "company": (
                        "A company with an intentionally long name for responsive "
                        "layout testing"
                    ),
                    "location_label": (
                        "Toronto, Ontario, Canada · Hybrid across a very large campus"
                    ),
                    "reasons": ["A long exact supporting evidence statement " * 4],
                    "supporting_evidence": ["A long exact supporting evidence statement " * 4],
                    "gaps": ["A long material gap statement " * 4],
                }
            )

    def now(self) -> datetime:
        return datetime(2026, 7, 28, tzinfo=UTC)

    def list_reviewed_profiles(self):
        if self.scenario == "no-reviewed-profile":
            return type("Profiles", (), {"profiles": [], "warning": None})()
        return type(
            "Profiles", (), {"profiles": [self.profile, self.other_profile], "warning": None}
        )()

    def get_preferences(self, profile_id: str):
        if self.scenario in {"no-confirmed-preferences", "preference-suggestion"}:
            return None
        return JobSearchPreferences(
            user_id="local-user",
            profile_id=profile_id,
            version=1,
            role_family_priority=[RoleFamily.EMBEDDED_FIRMWARE],
            target_titles=["Firmware Engineer"],
            related_title_variants=[],
            technical_themes=["firmware"],
            career_interests=[],
            job_levels=[JobLevel.ENTRY],
            locations=[NormalizedLocation(raw="Toronto, ON", city="Toronto", parseable=True)],
            work_arrangement=WorkArrangement.HYBRID,
            work_arrangement_mode=WorkArrangementPreferenceMode.PREFERRED,
            preferred_companies=[],
            excluded_companies=[],
            work_authorization_constraints=[],
            max_posting_age_days=30,
            created_at=datetime(2026, 7, 28, tzinfo=UTC),
        )

    def suggest_preferences(self, profile_id: str) -> JobSearchPreferenceSuggestion:
        return JobSearchPreferenceSuggestion(
            profile_id=profile_id,
            generated_at=datetime(2026, 7, 28, tzinfo=UTC),
            role_family_priority=[RoleFamily.EMBEDDED_FIRMWARE],
            target_titles=["Firmware Engineer"],
            related_title_variants=[],
            technical_themes=["firmware"],
            career_interests=[],
            job_levels=[JobLevel.ENTRY],
            locations=[NormalizedLocation(raw="Toronto, ON", city="Toronto", parseable=True)],
            work_arrangement=WorkArrangement.HYBRID,
            work_arrangement_mode=WorkArrangementPreferenceMode.PREFERRED,
            preferred_companies=[],
            rationale=["Suggested from reviewed evidence."],
        )

    def confirm_preferences(self, preferences: JobSearchPreferences) -> JobSearchPreferences:
        return preferences

    def load_feed(
        self, profile_id: str, feed_kind: FeedKind, *, sector: str | None = None
    ) -> OfflineFeed:
        warnings = (
            ["One approved source returned a partial response."]
            if self.scenario == "partial-source-warning"
            else []
        )
        if self.scenario == "all-sources-failure":
            return OfflineFeed(
                feed_kind,
                [],
                0,
                ["All approved sources failed."],
                "failed_all_sources",
                datetime(2026, 7, 28, tzinfo=UTC),
            )
        if self.scenario == "no-visible-results":
            return OfflineFeed(
                feed_kind,
                [],
                1,
                warnings,
                "completed",
                datetime(2026, 7, 28, tzinfo=UTC),
                retrieved_count=12,
            )
        if feed_kind is FeedKind.EXPLORE:
            visible = [self.visible[1 if sector == "Software Engineering" else 2]]
        else:
            visible = self.visible
        return OfflineFeed(
            feed_kind,
            visible,
            len(self.excluded),
            warnings,
            "completed",
            datetime(2026, 7, 28, tzinfo=UTC),
        )

    def load_excluded(
        self, profile_id: str, feed_kind: FeedKind, *, sector: str | None = None
    ) -> list[OfflineRecommendation]:
        del sector
        return self.excluded

    def refresh_tailored(self, profile_id: str) -> OfflineRefresh:
        feed = self.load_feed(profile_id, FeedKind.TAILORED)
        return OfflineRefresh(feed, OfflineRun(feed.status))

    def refresh_explore(self, profile_id: str, sector: str) -> OfflineRefresh:
        feed = self.load_feed(profile_id, FeedKind.EXPLORE)
        return OfflineRefresh(feed, OfflineRun(feed.status))

    def get_job_detail(
        self, profile_id: str, feed_kind: FeedKind, job_id: str, *, sector: str | None = None
    ) -> OfflineDetail | None:
        if feed_kind is FeedKind.EXPLORE:
            expected_job_id = "good-1" if sector == "Software Engineering" else "weak-1"
            if job_id != expected_job_id:
                return None
        for item in [*self.visible, *self.excluded]:
            if item.job_id == job_id:
                return OfflineDetail(
                    item,
            "Build and validate perception and embedded systems for reliable autonomy products.",
                )
        return None

    def save_job(self, job_id: str, profile_id: str) -> None:
        del job_id, profile_id
        return None

    def list_saved_jobs(self, profile_id: str) -> list[OfflineSaved]:
        del profile_id
        if self.scenario not in {
            "saved-available",
            "saved-unavailable",
            "visual-saved-filtering",
        }:
            return []
        availability = "unavailable" if self.scenario == "saved-unavailable" else "available"
        return [
            OfflineSaved(
                "saved-1",
                "saved-job-1",
                "Saved immutable role",
                "Example Robotics",
                datetime(2026, 7, 27, tzinfo=UTC),
                "Toronto, ON",
                WorkArrangement.HYBRID,
                "Original saved snapshot description.",
                "https://example.com/saved",
                availability,
                datetime(2026, 7, 28, tzinfo=UTC),
                "offline",
                None,
                datetime(2026, 7, 27, tzinfo=UTC),
                BrowseSeniority.MID_LEVEL,
            )
        ]

    def check_saved_job_availability(
        self, saved_id: str, profile_id: str
    ) -> OfflineSaved:
        del saved_id
        return self.list_saved_jobs(profile_id)[0]

    def prepare_tailoring(self, job_id: str, profile_id: str) -> OfflineHandoff:
        return OfflineHandoff(profile_id, "Tailored Role", "Tailoring description.")

    def prepare_saved_tailoring(self, saved_id: str, profile_id: str) -> OfflineHandoff:
        return self.prepare_tailoring(saved_id, profile_id)

    @staticmethod
    def _recommendation(
        job_id: str, grade: FitGrade, eligibility: EligibilityStatus, provisional: bool
    ) -> OfflineRecommendation:
        title = {
            FitGrade.EXCELLENT: "Excellent Role",
            FitGrade.GOOD: "Good Role",
            FitGrade.WEAK: "Weak Role",
            FitGrade.DONT_MATCH: "Don’t Match Role",
        }[grade]
        browse_seniority = {
            FitGrade.EXCELLENT: BrowseSeniority.SENIOR,
            FitGrade.GOOD: BrowseSeniority.MID_LEVEL,
            FitGrade.WEAK: BrowseSeniority.JUNIOR,
            FitGrade.DONT_MATCH: BrowseSeniority.UNKNOWN,
        }[grade]
        return OfflineRecommendation(
            job_id,
            f"rec-{job_id}",
            title,
            "Example Robotics",
            "Example Robotics",
            "offline",
            "Toronto, ON",
            WorkArrangement.HYBRID,
            datetime(2026, 7, 27, tzinfo=UTC),
            "Posted 1 day ago",
            grade,
            eligibility,
            provisional,
            VerificationStatus.VERIFIED_ACTIVE,
            VerificationConfidence.HIGH,
            "Verified active",
            [
                "Strong overlap with Python, C++, robotics, and autonomy work.",
                "Embedded and systems-integration projects support the core requirements.",
            ],
            [
                "Vision project — real-time object detection and tracking.",
                "Embedded project — sensors and low-level control systems.",
                "Skills — Python, C++, OpenCV, ROS, Linux.",
            ],
            ["No direct autonomous-vehicle production experience."],
            ["Authorization support is not stated in the posting."]
            if eligibility is EligibilityStatus.UNKNOWN
            else [],
            "https://example.com/jobs/offline",
            False,
            "embedded_firmware",
            RecommendationVisibility.EXCLUDED
            if grade is FitGrade.DONT_MATCH
            else RecommendationVisibility.VISIBLE,
            browse_seniority=browse_seniority,
        )


scenario_holder: dict[str, str] = {}


def render_offline_scenario() -> None:
    scenario_holder["value"] = st.selectbox(
        "Offline scenario", list(SCENARIOS), key="offline-scenario-selector"
    )
    _apply_visual_preset(scenario_holder["value"])


def _apply_visual_preset(scenario: str) -> None:
    state = st.session_state
    if state.get("jobs-visual-preset-applied") == scenario:
        return
    clear_browse_state(state)
    state.pop("jobs-active-section", None)
    state.pop("jobs_pending_section", None)
    if scenario == "visual-tailored-active":
        state["jobs_pending_section"] = "Tailored for you"
        state["jobs-search-tailored"] = "role"
        state["jobs-filter-seniority-tailored"] = ["Senior"]
        state["jobs-filter-location-tailored"] = ["Toronto, ON"]
        state["jobs-filter-arrangement-tailored"] = ["Hybrid"]
        state["jobs-filter-date-tailored"] = "Past week"
    elif scenario == "visual-tailored-expanded":
        state["jobs_pending_section"] = "Tailored for you"
        state["jobs-filter-open-tailored"] = True
        state["jobs-filter-seniority-tailored"] = ["Mid-level"]
        state["jobs-filter-location-tailored"] = ["Toronto, ON"]
        state["jobs-filter-arrangement-tailored"] = ["Hybrid"]
        state["jobs-filter-date-tailored"] = "Past week"
    elif scenario == "visual-explore-detail":
        state["jobs_pending_section"] = "Explore sectors"
        state["jobs-explore-sector"] = "Software Engineering"
        state["jobs-search-explore"] = "good"
        state["jobs-filter-arrangement-explore"] = ["Hybrid"]
        state["jobs-filter-date-explore"] = "Past month"
    elif scenario == "visual-saved-filtering":
        state["jobs_pending_section"] = "Saved"
        state["jobs-search-saved"] = "immutable"
        state["jobs-filter-location-saved"] = ["Toronto, ON"]
        state["jobs-filter-arrangement-saved"] = ["Hybrid"]
        state["jobs-filter-date-saved"] = "Past month"
    state["jobs-visual-preset-applied"] = scenario


st.session_state.setdefault("app_active_page", "Jobs")
render_application_shell(
    st,
    active_profile_label="Avery Engineer",
    active_profile_id="profile-1",
    profile_options=[("profile-1", "Avery Engineer"), ("profile-2", "Second Engineer")],
    on_profile_change=lambda _profile_id: clear_browse_state(st.session_state),
    development_ui=render_offline_scenario,
)
if scenario_holder["value"] == "database-unavailable":
    render_jobs_unavailable(st)
else:
    render_jobs_page(OfflineJobsExperience(scenario_holder["value"]))
