from __future__ import annotations

from datetime import UTC, datetime

from resume_tailor.domain.job_discovery.models import (
    JobLevel,
    JobSearchPreferences,
    NormalizedLocation,
    WorkArrangement,
    WorkArrangementPreferenceMode,
)
from resume_tailor.domain.job_discovery.queries import (
    APPROVED_EXPLORE_SECTORS,
    ExploreJobQuery,
    FeedKind,
    TailoredJobQuery,
    serialize_provider_job_query,
)


def _preferences() -> JobSearchPreferences:
    return JobSearchPreferences(
        user_id="user-1",
        profile_id="profile-1",
        version=4,
        role_family_priority=[],
        target_titles=["Robotics Software Engineer"],
        related_title_variants=["Autonomy Engineer"],
        technical_themes=["resume secret skill inventory"],
        career_interests=["resume secret interest prose"],
        job_levels=[JobLevel.MID],
        locations=[NormalizedLocation(city="Toronto", country_code="CA", raw="Toronto")],
        work_arrangement=WorkArrangement.REMOTE,
        work_arrangement_mode=WorkArrangementPreferenceMode.PREFERRED,
        preferred_companies=["Secret Company Preference"],
        excluded_companies=[],
        max_posting_age_days=30,
        created_at=datetime(2026, 7, 24, tzinfo=UTC),
        confirmed_at=datetime(2026, 7, 24, tzinfo=UTC),
    )


def test_tailored_query_serializes_only_allow_listed_provider_fields() -> None:
    query = TailoredJobQuery(
        preferences=_preferences(),
        profile_id="profile-1",
        local_profile_text="RESUME SECRET PROFILE TEXT",
        resume_text="RESUME SECRET FULL RESUME",
        source_restrictions=["greenhouse-acme"],
        page_size=25,
    )

    provider_query = query.to_provider_query()
    payload = serialize_provider_job_query(provider_query)

    assert provider_query.feed_kind is FeedKind.TAILORED
    assert set(payload) <= {
        "sectors",
        "role_families",
        "titles",
        "locations",
        "work_arrangements",
        "levels",
        "employment_types",
        "max_posting_age_days",
        "posted_after",
        "source_restrictions",
        "page_size",
        "cursor",
    }
    assert "RESUME SECRET PROFILE TEXT" not in repr(provider_query)
    assert "RESUME SECRET FULL RESUME" not in repr(payload)
    assert "resume secret" not in repr(payload).casefold()
    assert payload["titles"] == ["Robotics Software Engineer", "Autonomy Engineer"]


def test_explore_query_requires_approved_sector_and_does_not_require_profile() -> None:
    query = ExploreJobQuery(
        sectors=[APPROVED_EXPLORE_SECTORS[0]],
        locations=["Toronto"],
        page_size=10,
    )

    provider_query = query.to_provider_query()

    assert provider_query.feed_kind is FeedKind.EXPLORE
    assert provider_query.sectors == [APPROVED_EXPLORE_SECTORS[0]]
    assert provider_query.titles == []

