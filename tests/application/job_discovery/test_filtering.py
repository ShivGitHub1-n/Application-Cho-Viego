from __future__ import annotations

from datetime import UTC, datetime, timedelta

from resume_tailor.application.job_discovery.experience import RecommendationView, SavedJobView
from resume_tailor.application.job_discovery.filtering import (
    BrowseFilterState,
    BrowseSeniority,
    DatePostedWindow,
    active_filter_chips,
    available_locations,
    classify_browse_seniority,
    filter_recommendations,
    filter_saved_jobs,
    remove_filter,
)
from resume_tailor.domain.job_discovery.models import (
    EligibilityStatus,
    FeedKind,
    FitGrade,
    JobLevel,
    RecommendationVisibility,
    VerificationConfidence,
    VerificationStatus,
    WorkArrangement,
)

NOW = datetime(2026, 8, 8, 12, tzinfo=UTC)


def _recommendation(
    job_id: str,
    *,
    title: str,
    company: str,
    description: str = "unsearchable description",
    location: str = "Toronto, ON",
    arrangement: WorkArrangement = WorkArrangement.HYBRID,
    posted_at: datetime | None = NOW - timedelta(days=2),
    browse_seniority: BrowseSeniority = BrowseSeniority.SENIOR,
    job_level: JobLevel = JobLevel.SENIOR,
) -> RecommendationView:
    return RecommendationView(
        recommendation_id=f"rec-{job_id}",
        job_id=job_id,
        feed_kind=FeedKind.TAILORED,
        title=title,
        company=company,
        source_company=company,
        source_id="source",
        location_label=location,
        work_arrangement=arrangement,
        posted_at=posted_at,
        posting_age_label="Posted recently",
        grade=FitGrade.GOOD,
        eligibility=EligibilityStatus.ELIGIBLE,
        provisional=False,
        verification_status=VerificationStatus.VERIFIED_ACTIVE,
        verification_confidence=VerificationConfidence.HIGH,
        freshness_label="Fresh",
        official_url="https://example.com/job",
        visibility=RecommendationVisibility.VISIBLE,
        browse_seniority=browse_seniority,
        browse_job_level=job_level,
        description=description,
    )


def _saved(
    job_id: str,
    *,
    title: str,
    company: str,
    location: str = "Toronto, ON",
    arrangement: WorkArrangement = WorkArrangement.HYBRID,
    posted_at: datetime | None = NOW - timedelta(days=2),
    browse_seniority: BrowseSeniority = BrowseSeniority.SENIOR,
) -> SavedJobView:
    return SavedJobView.model_construct(
        saved_id=f"saved-{job_id}",
        job_id=job_id,
        title=title,
        company=company,
        saved_at=NOW,
        location_label=location,
        work_arrangement=arrangement,
        description="snapshot description contains firmware",
        official_url="https://example.com/saved",
        availability="available",
        checked_at=NOW,
        source_id="source",
        snapshot=None,
        posted_at=posted_at,
        browse_seniority=browse_seniority,
    )


def test_search_matches_company_or_title_case_insensitively_and_preserves_order() -> None:
    jobs = [
        _recommendation("a", title="Backend Engineer", company="Apple"),
        _recommendation("b", title="Firmware Developer", company="Other"),
        _recommendation("c", title="Systems Engineer", company="AMD Labs"),
    ]

    result = filter_recommendations(jobs, BrowseFilterState(query="  aMd  "), now=NOW)

    assert [job.job_id for job in result] == ["c"]
    assert filter_recommendations(
        jobs, BrowseFilterState(query="firm"), now=NOW
    )[0].job_id == "b"
    assert filter_recommendations(
        [_recommendation("x", title="Other", company="Other", description="Firmware")],
        BrowseFilterState(query="firmware"),
        now=NOW,
    ) == []


def test_whitespace_only_search_is_unconstrained() -> None:
    jobs = [
        _recommendation("a", title="A", company="A"),
        _recommendation("b", title="B", company="B"),
    ]

    assert [
        job.job_id
        for job in filter_recommendations(jobs, BrowseFilterState(query="  "), now=NOW)
    ] == ["a", "b"]


def test_title_signals_classify_browse_seniority_without_changing_job_level() -> None:
    assert classify_browse_seniority(
        "Firmware Co-op", JobLevel.INTERN
    ) is BrowseSeniority.COOP
    assert classify_browse_seniority(
        "New Grad Software Engineer", JobLevel.ENTRY
    ) is BrowseSeniority.NEW_GRAD
    assert classify_browse_seniority(
        "Engineering Manager", JobLevel.SENIOR
    ) is BrowseSeniority.MANAGER
    assert classify_browse_seniority(
        "Firmware Engineer", JobLevel.ENTRY
    ) is BrowseSeniority.JUNIOR
    assert classify_browse_seniority(
        "Unclassified Role", JobLevel.UNKNOWN
    ) is BrowseSeniority.UNKNOWN


def test_filter_groups_use_or_within_group_and_and_across_groups() -> None:
    jobs = [
        _recommendation("senior-toronto", title="Senior A", company="A", location="Toronto, ON"),
        _recommendation(
            "staff-waterloo",
            title="Staff B",
            company="B",
            location="Waterloo, ON",
            arrangement=WorkArrangement.REMOTE,
            browse_seniority=BrowseSeniority.STAFF,
        ),
        _recommendation(
            "junior-toronto",
            title="Junior C",
            company="C",
            location="Toronto, ON",
            browse_seniority=BrowseSeniority.JUNIOR,
        ),
    ]
    state = BrowseFilterState(
        seniorities=frozenset({BrowseSeniority.SENIOR, BrowseSeniority.STAFF}),
        locations=frozenset({"Toronto, ON", "Waterloo, ON"}),
        arrangements=frozenset({WorkArrangement.HYBRID, WorkArrangement.REMOTE}),
    )

    assert [job.job_id for job in filter_recommendations(jobs, state, now=NOW)] == [
        "senior-toronto",
        "staff-waterloo",
    ]


def test_date_windows_include_exact_boundary_and_exclude_unknown_dates() -> None:
    jobs = [
        _recommendation(
            "boundary", title="Boundary", company="A", posted_at=NOW - timedelta(days=7)
        ),
        _recommendation(
            "older",
            title="Older",
            company="B",
            posted_at=NOW - timedelta(days=7, seconds=1),
        ),
        _recommendation("unknown", title="Unknown", company="C", posted_at=None),
    ]

    week = BrowseFilterState(date_posted=DatePostedWindow.PAST_WEEK)
    anytime = BrowseFilterState(date_posted=DatePostedWindow.ANY_TIME)

    assert [job.job_id for job in filter_recommendations(jobs, week, now=NOW)] == ["boundary"]
    assert [job.job_id for job in filter_recommendations(jobs, anytime, now=NOW)] == [
        "boundary",
        "older",
        "unknown",
    ]


def test_available_locations_deduplicate_case_insensitively_from_base_collection() -> None:
    jobs = [
        _recommendation("a", title="A", company="A", location="Toronto, ON"),
        _recommendation("b", title="B", company="B", location="toronto, on"),
        _recommendation("c", title="C", company="C", location="Remote"),
    ]

    assert available_locations(jobs) == ["Toronto, ON", "Remote"]


def test_saved_filters_use_snapshot_view_fields_and_not_description_or_availability() -> None:
    saved = [
        _saved(
            "a",
            title="Firmware Engineer",
            company="Apple",
            browse_seniority=BrowseSeniority.SENIOR,
        ),
        _saved(
            "b",
            title="Other Role",
            company="Other",
            location="Waterloo, ON",
            arrangement=WorkArrangement.REMOTE,
            browse_seniority=BrowseSeniority.JUNIOR,
        ),
    ]

    state = BrowseFilterState(
        query="apple",
        seniorities=frozenset({BrowseSeniority.SENIOR}),
        locations=frozenset({"Toronto, ON"}),
        arrangements=frozenset({WorkArrangement.HYBRID}),
    )
    assert [item.saved_id for item in filter_saved_jobs(saved, state, now=NOW)] == ["saved-a"]
    assert filter_saved_jobs(
        [_saved("c", title="Other", company="Other")],
        BrowseFilterState(query="firmware"),
        now=NOW,
    ) == []


def test_active_chips_remove_one_constraint_and_clear_all_preserves_search() -> None:
    state = BrowseFilterState(
        query="firmware",
        seniorities=frozenset({BrowseSeniority.SENIOR}),
        locations=frozenset({"Toronto, ON"}),
        arrangements=frozenset({WorkArrangement.HYBRID}),
        date_posted=DatePostedWindow.PAST_WEEK,
    )

    chips = active_filter_chips(state)
    without_location = remove_filter(state, "location", "Toronto, ON")
    cleared = remove_filter(state, "all", None)

    assert [chip.label for chip in chips] == ["Senior", "Toronto, ON", "Hybrid", "Past week"]
    assert without_location.locations == frozenset()
    assert without_location.query == "firmware"
    assert cleared.query == "firmware"
    assert cleared.seniorities == frozenset()
    assert cleared.date_posted is DatePostedWindow.ANY_TIME
