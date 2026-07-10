from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field


class ClaimSupport(StrEnum):
    DIRECT = "direct"
    INFERRED = "inferred"
    UNSUPPORTED = "unsupported"


class EvidenceItem(BaseModel):
    id: str
    entity_id: str
    source_text: str
    support: ClaimSupport = ClaimSupport.DIRECT
    source_reference: str | None = None


class ResumeItem(BaseModel):
    id: str
    title: str
    organization: str | None = None
    bullets: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)


class MasterProfile(BaseModel):
    id: str
    user_id: str
    version: int = 1
    display_name: str
    experiences: list[ResumeItem] = Field(default_factory=list)
    projects: list[ResumeItem] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    coursework: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)


class JobPosting(BaseModel):
    id: str
    title: str
    description: str
    company_name: str | None = None
    source_url: str | None = None


class RoleClassification(BaseModel):
    role_family: str
    confidence: Annotated[float, Field(ge=0, le=1)]
    signals: list[str] = Field(default_factory=list)


class Decision(BaseModel):
    action: str
    entity_id: str
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)


class DecisionReport(BaseModel):
    role: RoleClassification
    decisions: list[Decision] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TailoringPlan(BaseModel):
    profile_id: str
    posting_id: str
    report: DecisionReport
    selected_entity_ids: list[str] = Field(default_factory=list)


class StructuredBullet(BaseModel):
    text: str
    evidence_ids: list[str] = Field(min_length=1)
    support: ClaimSupport


class StructuredResume(BaseModel):
    profile_id: str
    posting_id: str
    experience_bullets: dict[str, list[StructuredBullet]] = Field(default_factory=dict)
    selected_skills: list[str] = Field(default_factory=list)
    selected_coursework: list[str] = Field(default_factory=list)

