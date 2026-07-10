from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, model_validator


class ClaimSupport(StrEnum):
    DIRECT = "direct"
    DERIVED = "derived"
    STRONG_INFERENCE_PENDING_REVIEW = "strong_inference_pending_review"
    UNSUPPORTED = "unsupported"


class EntityKind(StrEnum):
    EXPERIENCE = "experience"
    PROJECT = "project"


class RoleFamily(StrEnum):
    AUTONOMOUS_SYSTEMS = "autonomous_systems"
    ROBOTICS_MECHATRONICS = "robotics_mechatronics"
    COMPUTER_VISION_PERCEPTION = "computer_vision_perception"
    AI_ML_MULTIMODAL = "ai_ml_multimodal"
    EMBEDDED_FIRMWARE = "embedded_firmware"
    SOFTWARE_DATA_ENGINEERING = "software_data_engineering"


class ProfileFitStatus(StrEnum):
    SUFFICIENT = "sufficient"
    LIMITED = "limited"
    INSUFFICIENT = "insufficient"


class ClaimComposition(StrEnum):
    SINGLE = "single"
    COMBINED = "combined"


class EvidenceItem(BaseModel):
    id: str
    entity_id: str
    source_text: str
    source_reference: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    outcomes: list[str] = Field(default_factory=list)
    confirmed: bool = True


class ResumeItem(BaseModel):
    id: str
    title: str
    kind: EntityKind
    organization: str | None = None
    technologies: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)


class ContactInfo(BaseModel):
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    links: list[str] = Field(default_factory=list)


class EducationRecord(BaseModel):
    school: str
    program: str
    graduation_date: str | None = None
    gpa: str | None = None


class MasterProfile(BaseModel):
    id: str
    user_id: str
    version: int = 1
    display_name: str
    contact: ContactInfo = Field(default_factory=ContactInfo)
    education: list[EducationRecord] = Field(default_factory=list)
    experiences: list[ResumeItem] = Field(default_factory=list)
    projects: list[ResumeItem] = Field(default_factory=list)
    declared_skills: list[str] = Field(default_factory=list)
    coursework: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_evidence_entities(self) -> MasterProfile:
        entity_ids = {item.id for item in self.experiences + self.projects}
        unknown_entities = {item.entity_id for item in self.evidence} - entity_ids
        if unknown_entities:
            raise ValueError(f"Evidence references unknown entities: {sorted(unknown_entities)}")
        return self


class JobPosting(BaseModel):
    id: str
    title: str
    description: str
    company_name: str | None = None
    source_url: str | None = None


class RoleSignal(BaseModel):
    id: str
    label: str
    keywords: list[str]
    weight: Annotated[float, Field(gt=0)]
    required: bool = False
    family: RoleFamily


class RoleClassification(BaseModel):
    role_family: str
    confidence: Annotated[float, Field(ge=0, le=1)]
    supported: bool
    signals: list[RoleSignal] = Field(default_factory=list)
    secondary_role_families: list[RoleFamily] = Field(default_factory=list)
    reason: str | None = None


class ProfileFitAssessment(BaseModel):
    status: ProfileFitStatus
    direct_signal_ids: list[str] = Field(default_factory=list)
    declared_skill_signal_ids: list[str] = Field(default_factory=list)
    material_gaps: list[str] = Field(default_factory=list)
    reason: str


class TemplateConstraints(BaseModel):
    template_id: str = "managed-engineering-v1"
    max_total_lines: Annotated[int, Field(gt=0)] = 42
    max_experience_lines: Annotated[int, Field(gt=0)] = 24
    max_project_lines: Annotated[int, Field(gt=0)] = 12
    max_skill_lines: Annotated[int, Field(gt=0)] = 3
    max_coursework_lines: Annotated[int, Field(gt=0)] = 2
    experience_entry_overhead_lines: Annotated[int, Field(ge=0)] = 2
    project_entry_overhead_lines: Annotated[int, Field(ge=0)] = 2
    max_bullets_per_entry: Annotated[int, Field(gt=0)] = 4
    max_combined_bullet_lines: Annotated[int, Field(gt=0)] = 2


class ResumeStrategy(BaseModel):
    role_family: str
    primary_focus: str
    secondary_focuses: list[str] = Field(default_factory=list)
    de_emphasized_themes: list[str] = Field(default_factory=list)
    rationale: str


class ClaimCandidate(BaseModel):
    id: str
    entity_id: str
    text: str
    evidence_ids: list[str] = Field(min_length=1)
    support: ClaimSupport
    estimated_lines: Annotated[int, Field(gt=0)]
    composition: ClaimComposition = ClaimComposition.SINGLE
    required_terms: list[str] = Field(default_factory=list)
    max_rendered_lines: Annotated[int, Field(gt=0)] = 2


class Decision(BaseModel):
    action: str
    entity_id: str
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)
    constraint: str | None = None


class DecisionReport(BaseModel):
    role: RoleClassification
    profile_fit: ProfileFitAssessment | None = None
    decisions: list[Decision] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    uncovered_signals: list[str] = Field(default_factory=list)


class TailoringPlan(BaseModel):
    profile_id: str
    profile_version: int
    posting_id: str
    template_id: str
    strategy: ResumeStrategy | None = None
    report: DecisionReport
    selected_entity_ids: list[str] = Field(default_factory=list)
    selected_claim_ids: list[str] = Field(default_factory=list)
    claim_candidates: list[ClaimCandidate] = Field(default_factory=list)
    selected_skills: list[str] = Field(default_factory=list)
    selected_coursework: list[str] = Field(default_factory=list)
    estimated_lines: int = 0


class StructuredBullet(BaseModel):
    id: str
    text: str
    evidence_ids: list[str] = Field(min_length=1)
    support: ClaimSupport


class StructuredResume(BaseModel):
    profile_id: str
    profile_version: int
    posting_id: str
    template_id: str
    display_name: str
    contact_line: str | None = None
    strategy: ResumeStrategy
    entity_titles: dict[str, str] = Field(default_factory=dict)
    education: list[EducationRecord] = Field(default_factory=list)
    experience_bullets: dict[str, list[StructuredBullet]] = Field(default_factory=dict)
    project_bullets: dict[str, list[StructuredBullet]] = Field(default_factory=dict)
    selected_skills: list[str] = Field(default_factory=list)
    selected_coursework: list[str] = Field(default_factory=list)
    review_required_claim_ids: list[str] = Field(default_factory=list)
