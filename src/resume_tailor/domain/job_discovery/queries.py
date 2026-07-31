"""Typed local and provider-bound job discovery queries."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

from resume_tailor.domain.job_discovery.models import (
    FeedKind,
    JobLevel,
    JobSearchPreferences,
    WorkArrangement,
)

APPROVED_EXPLORE_SECTORS = (
    "Software Engineering",
    "Data Engineering",
    "AI / Machine Learning",
    "Computer Vision",
    "Robotics / Autonomous Systems",
    "Embedded Systems / Firmware",
    "Hardware / Systems Integration",
    "Controls / Mechatronics",
    "Testing / Verification",
)


class ProviderFilterDisposition(StrEnum):
    PUSHED_DOWN = "pushed_down"
    LOCAL = "local"
    UNSUPPORTED = "unsupported"
    NOT_REQUESTED = "not_requested"


class ProviderJobQuery(BaseModel):
    """The complete allow-list of fields that may cross a provider boundary."""

    feed_kind: FeedKind
    sectors: list[str] = Field(default_factory=list)
    role_families: list[str] = Field(default_factory=list)
    titles: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    work_arrangements: list[WorkArrangement] = Field(default_factory=list)
    levels: list[JobLevel] = Field(default_factory=list)
    employment_types: list[str] = Field(default_factory=list)
    max_posting_age_days: int | None = Field(default=None, ge=0)
    posted_after: datetime | None = None
    source_restrictions: list[str] = Field(default_factory=list)
    page_size: int = Field(default=100, ge=1, le=1000)
    cursor: str | None = None


class TailoredJobQuery(BaseModel):
    """Local Tailored inputs; profile text is deliberately local-only."""

    preferences: JobSearchPreferences
    profile_id: str | None = None
    local_profile_text: str | None = None
    resume_text: str | None = None
    source_restrictions: list[str] = Field(default_factory=list)
    page_size: int = Field(default=100, ge=1, le=1000)

    def to_provider_query(self, *, cursor: str | None = None) -> ProviderJobQuery:
        preferences = self.preferences
        return ProviderJobQuery(
            feed_kind=FeedKind.TAILORED,
            role_families=[],
            titles=[*preferences.target_titles, *preferences.related_title_variants],
            locations=[location.raw for location in preferences.locations if location.raw],
            work_arrangements=(
                []
                if preferences.work_arrangement is WorkArrangement.UNKNOWN
                else [preferences.work_arrangement]
            ),
            levels=[level for level in preferences.job_levels if level is not JobLevel.UNKNOWN],
            max_posting_age_days=preferences.max_posting_age_days,
            source_restrictions=list(self.source_restrictions),
            page_size=self.page_size,
            cursor=cursor,
        )


class ExploreJobQuery(BaseModel):
    """Explore inputs contain selected sectors and sanitized retrieval controls."""

    sectors: list[str] = Field(min_length=1)
    title_keywords: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    work_arrangements: list[WorkArrangement] = Field(default_factory=list)
    levels: list[JobLevel] = Field(default_factory=list)
    employment_types: list[str] = Field(default_factory=list)
    max_posting_age_days: int | None = Field(default=None, ge=0)
    source_restrictions: list[str] = Field(default_factory=list)
    page_size: int = Field(default=100, ge=1, le=1000)
    profile_id: str | None = None
    evaluate_fit: bool = False

    @field_validator("sectors")
    @classmethod
    def validate_sectors(cls, values: list[str]) -> list[str]:
        invalid = sorted(set(values).difference(APPROVED_EXPLORE_SECTORS))
        if invalid:
            raise ValueError(f"unsupported explore sector: {invalid[0]}")
        return list(dict.fromkeys(values))

    def to_provider_query(self, *, cursor: str | None = None) -> ProviderJobQuery:
        return ProviderJobQuery(
            feed_kind=FeedKind.EXPLORE,
            sectors=list(self.sectors),
            titles=list(self.title_keywords),
            locations=list(self.locations),
            work_arrangements=list(self.work_arrangements),
            levels=[level for level in self.levels if level is not JobLevel.UNKNOWN],
            employment_types=list(self.employment_types),
            max_posting_age_days=self.max_posting_age_days,
            source_restrictions=list(self.source_restrictions),
            page_size=self.page_size,
            cursor=cursor,
        )


def serialize_provider_job_query(query: ProviderJobQuery) -> dict[str, object]:
    """Serialize by explicit allow-list; never use a broad model dump here."""

    payload: dict[str, object] = {
        "sectors": list(query.sectors),
        "role_families": list(query.role_families),
        "titles": list(query.titles),
        "locations": list(query.locations),
        "work_arrangements": [item.value for item in query.work_arrangements],
        "levels": [item.value for item in query.levels],
        "employment_types": list(query.employment_types),
        "max_posting_age_days": query.max_posting_age_days,
        "posted_after": query.posted_after.isoformat() if query.posted_after else None,
        "source_restrictions": list(query.source_restrictions),
        "page_size": query.page_size,
        "cursor": query.cursor,
    }
    return {key: value for key, value in payload.items() if value not in (None, [], "")}


__all__ = [
    "APPROVED_EXPLORE_SECTORS",
    "ExploreJobQuery",
    "FeedKind",
    "ProviderFilterDisposition",
    "ProviderJobQuery",
    "TailoredJobQuery",
    "serialize_provider_job_query",
]
