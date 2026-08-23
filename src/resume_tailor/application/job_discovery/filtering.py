from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from resume_tailor.domain.job_discovery.models import JobLevel, WorkArrangement


class BrowseSeniority(StrEnum):
    INTERNSHIP = "internship"
    COOP = "coop"
    NEW_GRAD = "new_grad"
    JUNIOR = "junior"
    MID_LEVEL = "mid_level"
    SENIOR = "senior"
    LEAD = "lead"
    STAFF = "staff"
    PRINCIPAL = "principal"
    MANAGER = "manager"
    UNKNOWN = "unknown"


class DatePostedWindow(StrEnum):
    PAST_24_HOURS = "past_24_hours"
    PAST_3_DAYS = "past_3_days"
    PAST_WEEK = "past_week"
    PAST_2_WEEKS = "past_2_weeks"
    PAST_MONTH = "past_month"
    ANY_TIME = "any_time"


class BrowseFilterState(BaseModel):
    model_config = ConfigDict(frozen=True)

    query: str = ""
    seniorities: frozenset[BrowseSeniority] = Field(default_factory=frozenset)
    locations: frozenset[str] = Field(default_factory=frozenset)
    arrangements: frozenset[WorkArrangement] = Field(default_factory=frozenset)
    date_posted: DatePostedWindow = DatePostedWindow.ANY_TIME


@dataclass(frozen=True)
class BrowseFilterChip:
    group: str
    value: str
    label: str


_SENIORITY_LABELS = {
    BrowseSeniority.INTERNSHIP: "Internship",
    BrowseSeniority.COOP: "Co-op",
    BrowseSeniority.NEW_GRAD: "New Grad",
    BrowseSeniority.JUNIOR: "Junior",
    BrowseSeniority.MID_LEVEL: "Mid-level",
    BrowseSeniority.SENIOR: "Senior",
    BrowseSeniority.LEAD: "Lead",
    BrowseSeniority.STAFF: "Staff",
    BrowseSeniority.PRINCIPAL: "Principal",
    BrowseSeniority.MANAGER: "Manager",
    BrowseSeniority.UNKNOWN: "Unknown",
}
_SENIORITY_ORDER = tuple(_SENIORITY_LABELS)
_ARRANGEMENT_LABELS = {
    WorkArrangement.REMOTE: "Remote",
    WorkArrangement.HYBRID: "Hybrid",
    WorkArrangement.ONSITE: "On-site",
    WorkArrangement.UNKNOWN: "Unknown",
}
_ARRANGEMENT_ORDER = (
    WorkArrangement.REMOTE,
    WorkArrangement.HYBRID,
    WorkArrangement.ONSITE,
    WorkArrangement.UNKNOWN,
)
_DATE_LABELS = {
    DatePostedWindow.PAST_24_HOURS: "Past 24 hours",
    DatePostedWindow.PAST_3_DAYS: "Past 3 days",
    DatePostedWindow.PAST_WEEK: "Past week",
    DatePostedWindow.PAST_2_WEEKS: "Past 2 weeks",
    DatePostedWindow.PAST_MONTH: "Past month",
    DatePostedWindow.ANY_TIME: "Any time",
}
_TITLE_TOKEN = re.compile(r"\b[\w]+(?:[-'][\w]+)*\b", re.IGNORECASE)
T = TypeVar("T")


def classify_browse_seniority(
    title: str, job_level: JobLevel | str | None
) -> BrowseSeniority:
    """Classify browse seniority using conservative title signals then JobLevel."""

    tokens = set(_TITLE_TOKEN.findall(_normalized_text(title)))
    title_text = _normalized_text(title)
    if "co-op" in title_text or "coop" in tokens or "co op" in title_text:
        return BrowseSeniority.COOP
    if "intern" in tokens or "internship" in tokens:
        return BrowseSeniority.INTERNSHIP
    if re.search(r"\bnew[- ]?grad(?:uate)?s?\b", title_text):
        return BrowseSeniority.NEW_GRAD
    if "manager" in tokens:
        return BrowseSeniority.MANAGER
    if "principal" in tokens:
        return BrowseSeniority.PRINCIPAL
    if "staff" in tokens:
        return BrowseSeniority.STAFF
    if "lead" in tokens:
        return BrowseSeniority.LEAD
    if "senior" in tokens or "sr" in tokens:
        return BrowseSeniority.SENIOR
    if "mid-level" in title_text or "mid level" in title_text:
        return BrowseSeniority.MID_LEVEL
    if "junior" in tokens or "jr" in tokens:
        return BrowseSeniority.JUNIOR

    try:
        normalized_level = JobLevel(job_level) if job_level is not None else JobLevel.UNKNOWN
    except ValueError:
        normalized_level = JobLevel.UNKNOWN
    return {
        JobLevel.INTERN: BrowseSeniority.INTERNSHIP,
        JobLevel.ENTRY: BrowseSeniority.JUNIOR,
        JobLevel.JUNIOR: BrowseSeniority.JUNIOR,
        JobLevel.MID: BrowseSeniority.MID_LEVEL,
        JobLevel.SENIOR: BrowseSeniority.SENIOR,
        JobLevel.LEAD: BrowseSeniority.LEAD,
        JobLevel.STAFF: BrowseSeniority.STAFF,
        JobLevel.PRINCIPAL: BrowseSeniority.PRINCIPAL,
        JobLevel.DIRECTOR: BrowseSeniority.MANAGER,
        JobLevel.UNKNOWN: BrowseSeniority.UNKNOWN,
    }[normalized_level]


def filter_recommendations(
    items: Sequence[T], state: BrowseFilterState, *, now: datetime
) -> list[T]:
    return _filter_items(items, state, now=now)


def filter_saved_jobs(items: Sequence[T], state: BrowseFilterState, *, now: datetime) -> list[T]:
    return _filter_items(items, state, now=now)


def available_locations(items: Sequence[Any]) -> list[str]:
    seen: set[str] = set()
    values: list[str] = []
    for item in items:
        label = str(getattr(item, "location_label", "")).strip()
        key = _normalized_text(label)
        if label and key not in seen:
            seen.add(key)
            values.append(label)
    return values


def active_filter_chips(state: BrowseFilterState) -> list[BrowseFilterChip]:
    chips = [
        BrowseFilterChip("seniority", seniority.value, _SENIORITY_LABELS[seniority])
        for seniority in _SENIORITY_ORDER
        if seniority in state.seniorities
    ]
    chips.extend(
        BrowseFilterChip("location", location, location)
        for location in sorted(state.locations, key=_normalized_text)
    )
    chips.extend(
        BrowseFilterChip("arrangement", arrangement.value, _ARRANGEMENT_LABELS[arrangement])
        for arrangement in _ARRANGEMENT_ORDER
        if arrangement in state.arrangements
    )
    if state.date_posted is not DatePostedWindow.ANY_TIME:
        chips.append(
            BrowseFilterChip(
                "date_posted", state.date_posted.value, _DATE_LABELS[state.date_posted]
            )
        )
    return chips


def remove_filter(
    state: BrowseFilterState, group: str, value: str | None
) -> BrowseFilterState:
    if group == "all":
        return BrowseFilterState(query=state.query)
    if group == "seniority" and value is not None:
        seniority = BrowseSeniority(value)
        return state.model_copy(update={"seniorities": state.seniorities - {seniority}})
    if group == "location" and value is not None:
        return state.model_copy(update={"locations": state.locations - {value}})
    if group == "arrangement" and value is not None:
        arrangement = WorkArrangement(value)
        return state.model_copy(update={"arrangements": state.arrangements - {arrangement}})
    if group == "date_posted":
        return state.model_copy(update={"date_posted": DatePostedWindow.ANY_TIME})
    return state


def _filter_items(items: Sequence[T], state: BrowseFilterState, *, now: datetime) -> list[T]:
    return [item for item in items if _matches(item, state, now=now)]


def _matches(item: Any, state: BrowseFilterState, *, now: datetime) -> bool:
    if not _matches_search(item, state.query):
        return False
    if state.seniorities and getattr(
        item, "browse_seniority", BrowseSeniority.UNKNOWN
    ) not in state.seniorities:
        return False
    if state.locations and _location_key(getattr(item, "location_label", "")) not in {
        _location_key(location) for location in state.locations
    }:
        return False
    if state.arrangements and getattr(
        item, "work_arrangement", WorkArrangement.UNKNOWN
    ) not in state.arrangements:
        return False
    return _matches_date(getattr(item, "posted_at", None), state.date_posted, now=now)


def _matches_search(item: Any, query: str) -> bool:
    normalized_query = _normalized_text(query)
    if not normalized_query:
        return True
    return normalized_query in _normalized_text(getattr(item, "title", "")) or (
        normalized_query in _normalized_text(getattr(item, "company", ""))
    )


def _matches_date(
    posted_at: datetime | None, window: DatePostedWindow, *, now: datetime
) -> bool:
    if window is DatePostedWindow.ANY_TIME or posted_at is None:
        return window is DatePostedWindow.ANY_TIME
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if posted_at.tzinfo is None or posted_at.utcoffset() is None:
        raise ValueError("posted_at must be timezone-aware")
    durations = {
        DatePostedWindow.PAST_24_HOURS: timedelta(hours=24),
        DatePostedWindow.PAST_3_DAYS: timedelta(days=3),
        DatePostedWindow.PAST_WEEK: timedelta(days=7),
        DatePostedWindow.PAST_2_WEEKS: timedelta(days=14),
        DatePostedWindow.PAST_MONTH: timedelta(days=30),
    }
    threshold = now - durations[window]
    return threshold <= posted_at.astimezone(UTC) <= now.astimezone(UTC)


def _normalized_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _location_key(value: str) -> str:
    return _normalized_text(value)


__all__ = [
    "BrowseFilterChip",
    "BrowseFilterState",
    "BrowseSeniority",
    "DatePostedWindow",
    "active_filter_chips",
    "available_locations",
    "classify_browse_seniority",
    "filter_recommendations",
    "filter_saved_jobs",
    "remove_filter",
]
