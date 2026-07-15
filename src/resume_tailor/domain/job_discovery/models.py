from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from resume_tailor.domain.models import RoleFamily


class WorkArrangement(StrEnum):
    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"
    UNKNOWN = "unknown"


class JobLevel(StrEnum):
    INTERN = "intern"
    ENTRY = "entry"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    UNKNOWN = "unknown"


class WorkArrangementPreferenceMode(StrEnum):
    REQUIRED = "required"
    PREFERRED = "preferred"
    ACCEPTABLE = "acceptable"
    EXCLUDED = "excluded"


class NormalizedLocation(BaseModel):
    city: str | None = None
    region: str | None = None
    country_code: str | None = None
    country_name: str | None = None
    raw: str = ""
    parseable: bool = False


class WorkArrangementPreference(BaseModel):
    arrangement: WorkArrangement
    mode: WorkArrangementPreferenceMode


class JobSearchPreferences(BaseModel):
    user_id: str
    profile_id: str
    version: int
    role_family_priority: list[RoleFamily]
    target_titles: list[str]
    related_title_variants: list[str]
    technical_themes: list[str]
    career_interests: list[str]
    job_levels: list[JobLevel]
    locations: list[NormalizedLocation]
    work_arrangement: WorkArrangement
    work_arrangement_mode: WorkArrangementPreferenceMode = WorkArrangementPreferenceMode.PREFERRED
    preferred_companies: list[str]
    max_posting_age_days: int | None = 30
    created_at: datetime
    confirmed_at: datetime | None = None


class JobSearchPreferenceSuggestion(BaseModel):
    profile_id: str
    generated_at: datetime
    role_family_priority: list[RoleFamily]
    target_titles: list[str]
    related_title_variants: list[str]
    technical_themes: list[str]
    career_interests: list[str]
    job_levels: list[JobLevel]
    locations: list[NormalizedLocation]
    work_arrangement: WorkArrangement
    work_arrangement_mode: WorkArrangementPreferenceMode = WorkArrangementPreferenceMode.PREFERRED
    preferred_companies: list[str]
    rationale: list[str]
