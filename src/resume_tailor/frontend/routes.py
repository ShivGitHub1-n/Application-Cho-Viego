"""Canonical workspace routes and compatibility normalization."""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class AppRoute(StrEnum):
    """Product-facing workspace routes used by the Streamlit shell."""

    CAREER_PROFILE = "Career Profile"
    JOBS = "Jobs"
    RESUME_STUDIO = "Resume Studio"
    COVER_LETTERS = "Cover Letters"


ROUTE_OPTIONS: tuple[AppRoute, ...] = tuple(AppRoute)

_ROUTE_ALIASES: dict[str, AppRoute] = {
    AppRoute.CAREER_PROFILE.value.casefold(): AppRoute.CAREER_PROFILE,
    "master profile": AppRoute.CAREER_PROFILE,
    AppRoute.JOBS.value.casefold(): AppRoute.JOBS,
    AppRoute.RESUME_STUDIO.value.casefold(): AppRoute.RESUME_STUDIO,
    "resume tailor": AppRoute.RESUME_STUDIO,
    AppRoute.COVER_LETTERS.value.casefold(): AppRoute.COVER_LETTERS,
    "cover letters": AppRoute.COVER_LETTERS,
}


def normalize_route(value: Any) -> AppRoute:
    """Return a canonical route while safely migrating persisted legacy labels."""

    if isinstance(value, AppRoute):
        return value
    if isinstance(value, str):
        return _ROUTE_ALIASES.get(value.strip().casefold(), AppRoute.CAREER_PROFILE)
    return AppRoute.CAREER_PROFILE


__all__ = ["AppRoute", "ROUTE_OPTIONS", "normalize_route"]
