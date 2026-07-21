from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class RequirementAuthority(StrEnum):
    CORE = "core"
    IMPORTANT = "important"
    BONUS = "bonus"
    INCIDENTAL = "incidental"


class EvidenceRelationship(StrEnum):
    DIRECT = "direct"
    ADJACENT = "adjacent"
    COMPLEMENTARY = "complementary"
    INCIDENTAL = "incidental"
    REJECTED = "rejected"


class PostingRequirement(BaseModel):
    id: str
    text: str
    normalized_text: str
    authority: RequirementAuthority
    importance: float = Field(ge=0, le=2)
    source_context: str
    repetition_count: int = Field(default=1, ge=1)
    technical_specificity: float = Field(ge=0, le=1)
    responsibility_signals: list[str] = Field(default_factory=list)
    specific_phrases: list[str] = Field(default_factory=list)
    # Material parts of a compound requirement (for example, firmware *and*
    # GUI).  Coverage is complete only when every listed component is supported.
    material_components: list[str] = Field(default_factory=list)


class PostingRequirementModel(BaseModel):
    role_context: str = ""
    requirements: list[PostingRequirement] = Field(default_factory=list)


class ShortTokenContribution(BaseModel):
    token: str
    requirement_ids: list[str] = Field(default_factory=list)
    contribution: float = Field(ge=0)
    corroborated: bool
    specificity_reason: str
    corroborating_context: list[str] = Field(default_factory=list)


class EvidenceRelationshipAssessment(BaseModel):
    relationship: EvidenceRelationship
    direct_requirement_ids: list[str] = Field(default_factory=list)
    adjacent_requirement_ids: list[str] = Field(default_factory=list)
    complementary_requirement_ids: list[str] = Field(default_factory=list)
    incidental_requirement_ids: list[str] = Field(default_factory=list)
    contextual_relevance: float = Field(ge=0)
    matched_requirement_labels: list[str] = Field(default_factory=list)
    meaningful_overlap: list[str] = Field(default_factory=list)
    short_token_contributions: list[ShortTokenContribution] = Field(
        default_factory=list
    )
    reason: str


class RequirementComponentMatch(BaseModel):
    component: str
    normalized_component: str
    supported: bool
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    supporting_entry_ids: list[str] = Field(default_factory=list)
    relationships: list[EvidenceRelationship] = Field(default_factory=list)
    satisfied_by_profile_sections: list[str] = Field(default_factory=list)


class RequirementCoverageDiagnostic(BaseModel):
    requirement_id: str
    text: str
    authority: RequirementAuthority
    importance: float = Field(ge=0, le=2)
    selected_entry_ids: list[str] = Field(default_factory=list)
    selected_bullet_ids: list[str] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    relationships: list[EvidenceRelationship] = Field(default_factory=list)
    satisfied_by_profile_sections: list[str] = Field(default_factory=list)
    component_matches: list[RequirementComponentMatch] = Field(default_factory=list)
    fully_covered: bool = False


class DirectCandidateTradeoffDiagnostic(BaseModel):
    omitted_candidate_id: str
    selected_complementary_candidate_ids: list[str] = Field(default_factory=list)
    reason: str


__all__ = [
    "DirectCandidateTradeoffDiagnostic",
    "EvidenceRelationship",
    "EvidenceRelationshipAssessment",
    "PostingRequirement",
    "PostingRequirementModel",
    "RequirementAuthority",
    "RequirementComponentMatch",
    "RequirementCoverageDiagnostic",
    "ShortTokenContribution",
]
