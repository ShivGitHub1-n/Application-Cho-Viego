from __future__ import annotations

import re
from enum import StrEnum
from hashlib import sha256
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator

from resume_tailor.domain.hybrid_resume import (
    BulletVariantRecord,
    HybridResumeDiagnostic,
)
from resume_tailor.domain.resume_composition import ResumeCompositionDiagnostic


class ClaimSupport(StrEnum):
    DIRECT = "direct"
    DERIVED = "derived"
    STRONG_INFERENCE_PENDING_REVIEW = "strong_inference_pending_review"
    UNSUPPORTED = "unsupported"


class ClaimConfidence(StrEnum):
    EXPLICITLY_SUPPORTED = "explicitly_supported"
    STRONGLY_IMPLIED = "strongly_implied"
    UNSUPPORTED = "unsupported"


class EntityKind(StrEnum):
    EXPERIENCE = "experience"
    PROJECT = "project"


class GraduationStatus(StrEnum):
    EXPECTED = "expected"
    COMPLETED = "completed"
    UNKNOWN = "unknown"


class RoleFamily(StrEnum):
    AUTONOMOUS_SYSTEMS = "autonomous_systems"
    ROBOTICS_MECHATRONICS = "robotics_mechatronics"
    COMPUTER_VISION_PERCEPTION = "computer_vision_perception"
    AI_ML_MULTIMODAL = "ai_ml_multimodal"
    EMBEDDED_FIRMWARE = "embedded_firmware"
    SOFTWARE_DATA_ENGINEERING = "software_data_engineering"


class RoleClassificationSource(StrEnum):
    GEMINI = "gemini"
    DETERMINISTIC = "deterministic"


class RoleClassificationValidationStatus(StrEnum):
    VALID = "valid"
    LOW_CONFIDENCE = "low_confidence"
    INVALID = "invalid"


class RoleClassificationFallbackReason(StrEnum):
    DISABLED = "disabled"
    MODEL_UNAVAILABLE = "model_unavailable"
    PROVIDER_ERROR = "provider_error"
    INVALID_OUTPUT = "invalid_output"
    LOW_CONFIDENCE = "low_confidence"
    CACHE_READ_ERROR = "cache_read_error"
    SEMANTIC_FAMILY_UNSUPPORTED = "semantic_family_unsupported"


class RoleClassificationCacheBehavior(StrEnum):
    NOT_USED = "not_used"
    MISS = "miss"
    HIT = "hit"
    STORED = "stored"
    READ_ERROR = "read_error"
    WRITE_ERROR = "write_error"


class RoleClassificationDiagnostic(BaseModel):
    semantic_enabled: bool
    selected_source: RoleClassificationSource
    resolved_primary_family: RoleFamily | None = None
    deterministic_primary_family: RoleFamily | None = None
    semantic_primary_family: RoleFamily | None = None
    validation_status: RoleClassificationValidationStatus | None = None
    fallback_reason: RoleClassificationFallbackReason | None = None
    confidence: Annotated[float | None, Field(ge=0, le=1)] = None
    cache_behavior: RoleClassificationCacheBehavior = RoleClassificationCacheBehavior.NOT_USED


class ProfileFitStatus(StrEnum):
    SUFFICIENT = "sufficient"
    LIMITED = "limited"
    INSUFFICIENT = "insufficient"


class ClaimComposition(StrEnum):
    SINGLE = "single"
    COMBINED = "combined"


class EvidenceItem(BaseModel):
    id: str = Field(description="Stable unique evidence ID")
    entity_id: str = Field(description="ID of the experience or project containing this bullet")
    source_text: str = Field(description="Exact factual bullet text from the source resume")
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
    start_date: str | None = None
    end_date: str | None = None
    location: str | None = None
    subtitle: str | None = None
    technology_label: str | None = None
    award_or_placement: str | None = None
    technologies: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    description: str | None = None
    bullets: list[str] = Field(default_factory=list)
    bullet_points: list[str] = Field(default_factory=list)


class ContactInfo(BaseModel):
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    links: list[str] = Field(default_factory=list)


class EducationRecord(BaseModel):
    school: str
    program: str
    minor_or_specialization: str | None = None
    co_op_designation: str | None = None
    start_date: str | None = None
    expected_graduation_date: str | None = None
    graduation_date: str | None = None
    graduation_status: GraduationStatus = GraduationStatus.UNKNOWN
    location: str | None = None
    gpa: str | None = None
    awards: list[str] = Field(default_factory=list)
    relevant_coursework: list[str] = Field(default_factory=list)

    @field_validator("gpa", mode="before")
    @classmethod
    def normalize_gpa(cls, value: object) -> object:
        if value is None or isinstance(value, str):
            return value
        if isinstance(value, bool):
            raise ValueError("GPA must be text or a number, not a boolean")
        if isinstance(value, (int, float)):
            return str(value)
        raise ValueError("GPA must be text or a number")


class ReviewedTechnicalSkill(BaseModel):
    id: str | None = None
    value: str
    source_reference: str | None = None


class TechnicalSkillCategory(BaseModel):
    id: str | None = None
    category: str
    values: list[str] = Field(default_factory=list)
    skills: list[ReviewedTechnicalSkill] = Field(default_factory=list)
    source_reference: str | None = None


class SkillNormalizationDecision(BaseModel):
    action: str
    skill_value: str
    source_category_id: str
    retained_category_id: str
    reason: str


class SkillSelectionStatus(StrEnum):
    SELECTED = "selected"
    ALTERNATE = "alternate"
    EXCLUDED_UNRELATED = "excluded_unrelated"
    EXCLUDED_REDUNDANT = "excluded_redundant"


class RankedSkill(BaseModel):
    id: str
    value: str
    relevance_score: float = Field(ge=0)
    status: SkillSelectionStatus
    original_order: int = Field(ge=0)
    selected_order: int | None = Field(default=None, ge=0)
    selection_reason: str
    supporting_job_signals: list[str] = Field(default_factory=list)
    provenance: str


class RankedSkillCategory(BaseModel):
    id: str
    label: str
    relevance_score: float = Field(ge=0)
    status: SkillSelectionStatus
    original_order: int = Field(ge=0)
    selected_order: int | None = Field(default=None, ge=0)
    selection_reason: str
    supporting_job_signals: list[str] = Field(default_factory=list)
    skills: list[RankedSkill] = Field(default_factory=list)
    provenance: str


class SkillCategorySelection(BaseModel):
    category_id: str
    skill_ids: list[str] = Field(min_length=1)


class GeneratedSkill(BaseModel):
    id: str
    category_id: str
    value: str
    evidence_ids: list[str] = Field(min_length=1)
    support: ClaimSupport


class SkillCompositionSelection(BaseModel):
    categories: list[SkillCategorySelection] = Field(min_length=1)
    rationale: str
    demonstrated_skills: list[GeneratedSkill] = Field(default_factory=list)


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
    technical_skills: list[TechnicalSkillCategory] = Field(default_factory=list)
    coursework: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(
        default_factory=list,
        description=(
            "Canonical bullet-level evidence. Include one item for every meaningful experience "
            "or project bullet and link it to the parent entity_id."
        ),
    )
    skill_normalization_decisions: list[SkillNormalizationDecision] = Field(default_factory=list)

    @field_validator("id", "user_id", "display_name")
    @classmethod
    def require_profile_identity(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Profile ID, user ID, and candidate name must not be empty")
        return cleaned

    @field_validator("technical_skills", mode="before")
    @classmethod
    def accept_category_mapping(cls, value: object) -> object:
        if isinstance(value, dict):
            return [{"category": label, "values": skills} for label, skills in value.items()]
        return value

    @model_validator(mode="after")
    def normalize_technical_skills(self) -> MasterProfile:
        seen_values: set[str] = set()
        normalized: list[TechnicalSkillCategory] = []
        duplicate_decisions: list[SkillNormalizationDecision] = []
        retained_category_by_value: dict[str, str] = {}
        seen_category_ids: set[str] = set()
        seen_skill_ids: set[str] = set()
        for category in self.technical_skills:
            label = category.category.strip()
            if not label:
                raise ValueError("Technical skill categories require a non-empty label")
            category_id = category.id or _stable_skill_id("category", label)
            if category_id in seen_category_ids:
                raise ValueError(f"Duplicate technical skill category ID: {category_id}")
            seen_category_ids.add(category_id)
            supplied = category.skills or [
                ReviewedTechnicalSkill(value=value) for value in category.values
            ]
            category_seen: set[str] = set()
            skills: list[ReviewedTechnicalSkill] = []
            for skill in supplied:
                value = skill.value.strip()
                if not value:
                    raise ValueError(f"Technical skill category {label!r} contains an empty skill")
                duplicate_key = value.casefold()
                if duplicate_key in category_seen or duplicate_key in seen_values:
                    duplicate_decisions.append(
                        SkillNormalizationDecision(
                            action="removed_duplicate",
                            skill_value=value,
                            source_category_id=category_id,
                            retained_category_id=retained_category_by_value.get(
                                duplicate_key, category_id
                            ),
                            reason=(
                                "Exact case-insensitive duplicate retained at its first "
                                "reviewed occurrence."
                            ),
                        )
                    )
                    continue
                category_seen.add(duplicate_key)
                seen_values.add(duplicate_key)
                retained_category_by_value[duplicate_key] = category_id
                skill_id = skill.id or _stable_skill_id(category_id, value)
                if skill_id in seen_skill_ids:
                    raise ValueError(f"Duplicate technical skill ID: {skill_id}")
                seen_skill_ids.add(skill_id)
                skills.append(skill.model_copy(update={"id": skill_id, "value": value}))
            if not skills:
                raise ValueError(f"Technical skill category {label!r} has no unique skills")
            normalized.append(
                category.model_copy(
                    update={
                        "id": category_id,
                        "category": label,
                        "values": [skill.value for skill in skills],
                        "skills": skills,
                    }
                )
            )
        self.technical_skills = normalized
        self.skill_normalization_decisions = [
            *self.skill_normalization_decisions,
            *duplicate_decisions,
        ]
        return self

    @model_validator(mode="after")
    def normalize_coursework_authority(self) -> MasterProfile:
        canonical = [
            course for education in self.education for course in education.relevant_coursework
        ]
        canonical = list(dict.fromkeys(canonical))
        if canonical:
            if self.coursework and self.coursework != canonical:
                raise ValueError("Top-level coursework must match education relevant_coursework")
            self.coursework = canonical
        elif self.coursework and len(self.education) == 1:
            self.education[0].relevant_coursework = list(self.coursework)
        return self

    @model_validator(mode="after")
    def derive_legacy_declared_skills(self) -> MasterProfile:
        if self.technical_skills:
            self.declared_skills = [
                skill.value for category in self.technical_skills for skill in category.skills
            ]
        return self

    @model_validator(mode="after")
    def validate_evidence_entities(self) -> MasterProfile:
        entries = self.experiences + self.projects
        entry_ids = [item.id for item in entries]
        evidence_ids = [item.id for item in self.evidence]
        if any(not value.strip() for value in entry_ids + evidence_ids):
            raise ValueError("Entry and evidence IDs must be non-empty")
        duplicate_entries = sorted({value for value in entry_ids if entry_ids.count(value) > 1})
        duplicate_evidence = sorted(
            {value for value in evidence_ids if evidence_ids.count(value) > 1}
        )
        if duplicate_entries:
            raise ValueError(f"Duplicate resume entry IDs: {duplicate_entries}")
        if duplicate_evidence:
            raise ValueError(f"Duplicate evidence IDs: {duplicate_evidence}")
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
    diagnostic: RoleClassificationDiagnostic | None = None


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
    max_skill_lines: Annotated[int, Field(gt=0)] = 4
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
    writing_variant: BulletVariantRecord | None = None


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


class CompositionEvidenceGroup(BaseModel):
    entry_id: str
    evidence_ids: list[str] = Field(min_length=1, max_length=2)


class CompositionSelection(BaseModel):
    selected_entry_ids: list[str] = Field(min_length=1)
    selected_evidence_ids: list[str] = Field(min_length=1)
    evidence_groups: list[CompositionEvidenceGroup] = Field(default_factory=list)
    rationale: str


class TailoringPlan(BaseModel):
    profile_id: str
    profile_version: int
    posting_id: str
    template_id: str
    posting: JobPosting
    constraints: TemplateConstraints
    strategy: ResumeStrategy | None = None
    report: DecisionReport
    selected_entity_ids: list[str] = Field(default_factory=list)
    selected_claim_ids: list[str] = Field(default_factory=list)
    claim_candidates: list[ClaimCandidate] = Field(default_factory=list)
    education: list[EducationRecord] = Field(default_factory=list)
    technical_skills: list[TechnicalSkillCategory] = Field(default_factory=list)
    selected_skill_categories: list[RankedSkillCategory] = Field(default_factory=list)
    ranked_skill_categories: list[RankedSkillCategory] = Field(default_factory=list)
    skill_composition_selection: SkillCompositionSelection | None = None
    selected_experiences: list[ResumeItem] = Field(default_factory=list)
    selected_projects: list[ResumeItem] = Field(default_factory=list)
    selected_skills: list[str] = Field(default_factory=list)
    selected_coursework: list[str] = Field(default_factory=list)
    estimated_lines: int = 0
    composition_selection: CompositionSelection | None = None
    demonstrated_skills: list[GeneratedSkill] = Field(default_factory=list)
    hybrid_diagnostic: HybridResumeDiagnostic | None = None

    @model_validator(mode="after")
    def derive_legacy_selected_skills(self) -> TailoringPlan:
        if self.selected_skill_categories:
            self.selected_skills = [
                skill.value
                for category in self.selected_skill_categories
                for skill in category.skills
            ]
        return self


class StructuredBullet(BaseModel):
    id: str
    text: str
    evidence_ids: list[str] = Field(min_length=1)
    support: ClaimSupport
    writing_variant: BulletVariantRecord | None = None


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
    technical_skills: list[TechnicalSkillCategory] = Field(default_factory=list)
    experiences: list[ResumeItem] = Field(default_factory=list)
    projects: list[ResumeItem] = Field(default_factory=list)
    experience_bullets: dict[str, list[StructuredBullet]] = Field(default_factory=dict)
    project_bullets: dict[str, list[StructuredBullet]] = Field(default_factory=dict)
    selected_skills: list[str] = Field(default_factory=list)
    selected_coursework: list[str] = Field(default_factory=list)
    review_required_claim_ids: list[str] = Field(default_factory=list)
    review_pending_bullets: list[StructuredBullet] = Field(default_factory=list)
    review_pending_skills: list[GeneratedSkill] = Field(default_factory=list)
    demonstrated_skills: list[GeneratedSkill] = Field(default_factory=list)
    composition_diagnostic: ResumeCompositionDiagnostic | None = None
    hybrid_diagnostic: HybridResumeDiagnostic | None = None

    @model_validator(mode="after")
    def derive_legacy_selected_skills(self) -> StructuredResume:
        if self.technical_skills:
            self.selected_skills = [
                skill.value for category in self.technical_skills for skill in category.skills
            ]
        return self


def _stable_skill_id(namespace: str, value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-") or "item"
    digest = sha256(f"{namespace}\0{value.casefold()}".encode()).hexdigest()[:10]
    return f"{slug}-{digest}"
