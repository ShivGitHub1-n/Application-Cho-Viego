from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from resume_tailor.domain.layout import PageUtilizationStatus
from resume_tailor.domain.requirement_ranking import (
    DirectCandidateTradeoffDiagnostic,
    EvidenceRelationship,
    PostingRequirement,
    RequirementCoverageDiagnostic,
    ShortTokenContribution,
)

TEMPLATE_V1_UTILIZATION_TARGET_FLOOR = 0.72
TEMPLATE_V1_UTILIZATION_TARGET_CEILING = 0.97
TEMPLATE_V1_PREFERRED_DENSITY_FLOOR = 0.90
TEMPLATE_V1_PREFERRED_DENSITY_CEILING = 0.93
TEMPLATE_V1_ACCEPTABLE_DENSITY_CEILING = 0.95
TEMPLATE_V1_IDEAL_DENSITY = 0.92
TEMPLATE_V1_DENSITY_INVESTIGATION_FLOOR = 0.85
RESUME_COMPOSITION_CONTRACT_VERSION = "deterministic-resume-composition-v6"


class CompositionOutcome(StrEnum):
    OVERFLOW = "overflow"
    ACCEPTABLE_ONE_PAGE = "acceptable_one_page"
    SEVERE_UNDERFILL = "severe_underfill"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    UNVERIFIED = "unverified"


class CompositionCandidateKind(StrEnum):
    EXPERIENCE_ENTRY = "experience_entry"
    PROJECT_ENTRY = "project_entry"
    EXPERIENCE_BULLET = "experience_bullet"
    PROJECT_BULLET = "project_bullet"
    SKILL_CATEGORY = "skill_category"
    EDUCATION_DETAIL = "education_detail"


class PageVerificationStatus(StrEnum):
    EXACT = "exact"
    ESTIMATED = "estimated"


class LineFitVerificationStatus(StrEnum):
    EXACT = "exact"
    ESTIMATED = "estimated"


class CompositionUnderfillReason(StrEnum):
    NONE = "none"
    PROFILE_INCOMPLETE = "profile_incomplete"
    EVIDENCE_LIMITED = "evidence_limited"
    QUALITY_LIMITED = "quality_limited"
    JOB_MATCH_LIMITED = "job_match_limited"
    CANDIDATE_CONSTRUCTION_FAILURE = "candidate_construction_failure"
    RETRIEVAL_FAILURE = "retrieval_failure"
    VALIDATION_LIMITED = "validation_limited"
    SEARCH_BOUNDS_LIMITED = "search_bounds_limited"
    PAGINATION_UNVERIFIED = "pagination_unverified"


class CompositionTerminationReason(StrEnum):
    TARGET_FINALISTS_FOUND = "target_finalists_found"
    NO_RELEVANT_EVIDENCE = "no_relevant_evidence"
    FRONTIER_EXHAUSTED = "frontier_exhausted"
    ESTIMATED_EVALUATION_LIMIT = "estimated_evaluation_limit"
    EXPANSION_OPERATION_LIMIT = "expansion_operation_limit"
    EXACT_VERIFICATION_UNAVAILABLE = "exact_verification_unavailable"
    EXACT_FINALISTS_EXHAUSTED = "exact_finalists_exhausted"
    ALL_ADMISSIBLE_CANDIDATES_OVERFLOWED = "all_admissible_candidates_overflowed"


class CandidateExclusionCategory(StrEnum):
    RELEVANCE_THRESHOLD = "relevance_threshold"
    REDUNDANCY_THRESHOLD = "redundancy_threshold"
    SEARCH_BOUND = "search_bound"
    OVERFLOW = "overflow"
    FINAL_PLAN_OBJECTIVE = "final_plan_objective"
    COHERENT_BLOCK_MINIMUM = "coherent_block_minimum"


class PreferredDensityStatus(StrEnum):
    BELOW_PREFERRED = "below_preferred"
    PREFERRED = "preferred"
    ABOVE_PREFERRED = "above_preferred"
    OVERFLOW_RISK = "overflow_risk"


class ProjectRepresentationStatus(StrEnum):
    SUBSTANTIVE_PROJECT = "substantive_project"
    SHALLOW_PROJECT_EXCEPTION = "shallow_project_exception"
    ZERO_PROJECT_EXCEPTION = "zero_project_exception"
    NO_CREDIBLE_PROJECT_EVIDENCE = "no_credible_project_evidence"


class ExperienceSingleBulletExceptionReason(StrEnum):
    USER_PINNED = "user_pinned"
    UNIQUE_DIRECT_REQUIREMENT_COVERAGE = "unique_direct_requirement_coverage"
    REVIEWED_CENTRAL_ROLE_EXCEPTIONAL_VALUE = (
        "reviewed_central_role_exceptional_value"
    )


class PageFitEvaluation(BaseModel):
    status: PageUtilizationStatus
    page_count: int | None = Field(default=None, ge=0)
    exact: bool
    provider: str
    utilization_ratio: float = Field(ge=0)
    fits_one_page: bool
    verification_failure: str | None = None


class BulletLineFitDiagnostic(BaseModel):
    verification_status: LineFitVerificationStatus
    expected_line_count: int = Field(ge=1)
    expected_final_line_word_count: int = Field(ge=0)
    expected_final_line_width_ratio: float = Field(ge=0, le=1)
    total_vertical_line_cost: float = Field(ge=1)
    awkward_wrap_risk: bool
    three_line_risk: bool
    future_rewrite_recommended: bool


class CompositionCandidateDiagnostic(BaseModel):
    candidate_id: str
    kind: CompositionCandidateKind
    entry_id: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    provenance: list[str] = Field(default_factory=list)
    relevance_score: float
    estimated_lines: int = Field(ge=0)
    matched_requirements: list[str] = Field(default_factory=list)
    selected: bool
    selection_reason: str | None = None
    exclusion_reason: str | None = None
    exclusion_category: CandidateExclusionCategory | None = None
    redundancy_penalty: float = Field(default=0, ge=0)
    normalized_features: list[str] = Field(default_factory=list)
    meaningful_overlap: list[str] = Field(default_factory=list)
    generic_only_rejected: bool = False
    admission_reason: str | None = None
    expansion_type: str | None = None
    skill_support_status: str | None = None
    line_fit: BulletLineFitDiagnostic | None = None
    contextual_relevance: float = Field(default=0, ge=0)
    intrinsic_evidence_strength: float = Field(default=0, ge=0)
    portfolio_contribution: float = 0
    dominance_relationship: str | None = None
    unique_capability_retained: bool = False
    evidence_relationship: EvidenceRelationship = EvidenceRelationship.REJECTED
    direct_requirement_ids: list[str] = Field(default_factory=list)
    adjacent_requirement_ids: list[str] = Field(default_factory=list)
    complementary_requirement_ids: list[str] = Field(default_factory=list)
    incidental_requirement_ids: list[str] = Field(default_factory=list)
    short_token_contributions: list[ShortTokenContribution] = Field(default_factory=list)
    marginal_contribution: float = 0
    writing_variant_id: str | None = None
    package_id: str | None = None
    package_bullet_count: int | None = Field(default=None, ge=1)
    page_cost: float | None = Field(default=None, gt=0)
    pruning_bound: str | None = None
    would_improve_density: bool | None = None


class PageFillIterationDiagnostic(BaseModel):
    iteration: int = Field(ge=1)
    candidate_id: str
    accepted: bool
    overflow: bool
    utilization_ratio: float = Field(ge=0)
    exact_page_verification: bool
    reason: str


class EntryBulletSelectionDiagnostic(BaseModel):
    entry_id: str
    entry_kind: str
    available_bullet_ids: list[str] = Field(default_factory=list)
    selected_bullet_ids: list[str] = Field(default_factory=list)
    omitted_bullet_reasons: dict[str, str] = Field(default_factory=dict)
    retained_all_available_bullets: bool = False
    distinct_contributions: dict[str, str] = Field(default_factory=dict)
    evidence_relationships: dict[str, EvidenceRelationship] = Field(default_factory=dict)
    marginal_contributions: dict[str, float] = Field(default_factory=dict)


class ExperiencePackageAlternativeDiagnostic(BaseModel):
    package_id: str
    bullet_ids: list[str] = Field(min_length=1, max_length=4)
    source_evidence_ids: list[str] = Field(min_length=1)
    bullet_count: int = Field(ge=1, le=4)
    source_bullet_count: int = Field(ge=0)
    rewritten_bullet_count: int = Field(ge=0)
    package_relevance: float = Field(ge=0)
    intrinsic_strength: float = Field(ge=0)
    writing_quality: float = Field(ge=0)
    duration_recency_contribution: float = Field(ge=0)
    enterprise_production_contribution: float = Field(ge=0)
    enterprise_production_evidence: list[str] = Field(default_factory=list)
    distinct_coverage: list[str] = Field(default_factory=list)
    page_cost: float = Field(gt=0)
    redundancy_penalty: float = Field(ge=0)
    total_score: float
    single_bullet_exception_reason: ExperienceSingleBulletExceptionReason | None = None


class ExperiencePackageSelectionDiagnostic(BaseModel):
    entry_id: str
    source_bullets_available: int = Field(ge=0)
    validated_rewrites_available: int = Field(ge=0)
    best_package_alternatives: list[ExperiencePackageAlternativeDiagnostic] = Field(
        default_factory=list
    )
    selected_bullet_count: int = Field(ge=0)
    selected_package_id: str | None = None
    selected: bool
    coherent_block_minimum_failed: bool = False
    single_bullet_exception_reason: ExperienceSingleBulletExceptionReason | None = None
    enterprise_production_tiebreaker_affected_result: bool = False
    user_priority_signal: float | None = None
    final_reason: str


class ProjectRepresentationDiagnostic(BaseModel):
    status: ProjectRepresentationStatus
    selected_project_ids: list[str] = Field(default_factory=list)
    substantive_project_ids: list[str] = Field(default_factory=list)
    credible_project_ids: list[str] = Field(default_factory=list)
    reason: str


class PortfolioMarginalComparisonDiagnostic(BaseModel):
    selected_entry_id: str
    selected_entry_kind: str
    selected_package_score: float
    selected_page_cost: float = Field(gt=0)
    strongest_omitted_entry_id: str | None = None
    strongest_omitted_entry_kind: str | None = None
    strongest_omitted_package_score: float | None = None
    strongest_omitted_professional_entry_id: str | None = None
    strongest_omitted_professional_package_score: float | None = None
    strongest_omitted_project_entry_id: str | None = None
    strongest_omitted_project_package_score: float | None = None
    marginal_gain: float | None = None
    page_cost_difference: float | None = None
    unique_requirements_contributed: list[str] = Field(default_factory=list)
    redundancy_difference: float | None = None
    choice_changed_after_validated_writing: bool = False
    selected_reason: str
    omitted_reason: str | None = None


class SkillRowSelectionDiagnostic(BaseModel):
    row_id: str
    label: str
    source_category_ids: list[str] = Field(min_length=1)
    skill_ids: list[str] = Field(default_factory=list)
    skill_values: list[str] = Field(default_factory=list)
    provenance: list[str] = Field(default_factory=list)
    relationship: EvidenceRelationship = EvidenceRelationship.REJECTED
    estimated_available_width_points: float = Field(default=0, ge=0)
    estimated_used_width_points: float = Field(default=0, ge=0)
    estimated_remaining_width_points: float = Field(default=0, ge=0)
    estimated_used_width_ratio: float = Field(default=0, ge=0, le=1)
    compatible_omitted_skill_values: list[str] = Field(default_factory=list)
    underfill_exception_reason: str | None = None
    one_skill_exception_reason: str | None = None
    grouping_reason: str | None = None


class ResumeCompositionDiagnostic(BaseModel):
    outcome: CompositionOutcome
    termination_reason: CompositionTerminationReason
    selected_experience_ids: list[str] = Field(default_factory=list)
    selected_project_ids: list[str] = Field(default_factory=list)
    selected_bullet_ids: list[str] = Field(default_factory=list)
    bullet_counts: dict[str, int] = Field(default_factory=dict)
    selected_skill_category_ids: list[str] = Field(default_factory=list)
    selected_skill_category_labels: list[str] = Field(default_factory=list)
    credible_skill_category_count: int = Field(default=0, ge=0)
    desired_skill_category_count: int = Field(default=0, ge=0)
    skill_category_shortfall_reason: str | None = None
    entry_bullet_selections: list[EntryBulletSelectionDiagnostic] = Field(default_factory=list)
    experience_package_selections: list[ExperiencePackageSelectionDiagnostic] = Field(
        default_factory=list
    )
    project_representation: ProjectRepresentationDiagnostic | None = None
    portfolio_marginal_comparisons: list[PortfolioMarginalComparisonDiagnostic] = Field(
        default_factory=list
    )
    selected_skill_rows: list[SkillRowSelectionDiagnostic] = Field(default_factory=list)
    posting_requirements: list[PostingRequirement] = Field(default_factory=list)
    requirement_coverage: list[RequirementCoverageDiagnostic] = Field(default_factory=list)
    portfolio_coverage_gaps: list[str] = Field(default_factory=list)
    direct_candidate_tradeoffs: list[DirectCandidateTradeoffDiagnostic] = Field(
        default_factory=list
    )
    omitted_direct_skill_values: list[str] = Field(default_factory=list)
    omitted_direct_skill_reasons: dict[str, str] = Field(default_factory=dict)
    selected_candidates: list[CompositionCandidateDiagnostic] = Field(default_factory=list)
    excluded_high_ranking_candidates: list[CompositionCandidateDiagnostic] = Field(
        default_factory=list
    )
    unused_admissible_candidates: list[CompositionCandidateDiagnostic] = Field(default_factory=list)
    candidates_excluded_by_search_bounds: list[CompositionCandidateDiagnostic] = Field(
        default_factory=list
    )
    candidates_excluded_by_thresholds: list[CompositionCandidateDiagnostic] = Field(
        default_factory=list
    )
    unused_experience_ids: list[str] = Field(default_factory=list)
    unused_project_ids: list[str] = Field(default_factory=list)
    unused_reviewed_bullet_ids: list[str] = Field(default_factory=list)
    unused_relevant_skill_category_ids: list[str] = Field(default_factory=list)
    page_fill_iterations: list[PageFillIterationDiagnostic] = Field(default_factory=list)
    overflow_rollbacks: int = Field(default=0, ge=0)
    final_utilization_ratio: float = Field(ge=0)
    best_estimated_utilization_ratio: float = Field(ge=0)
    best_exact_verified_utilization_ratio: float | None = Field(default=None, ge=0)
    utilization_target_floor: float = Field(gt=0, lt=1)
    utilization_target_ceiling: float = Field(gt=0, le=1)
    utilization_target_reached: bool
    preferred_density_floor: float = Field(
        default=TEMPLATE_V1_PREFERRED_DENSITY_FLOOR,
        gt=0,
        lt=1,
    )
    preferred_density_ceiling: float = Field(
        default=TEMPLATE_V1_PREFERRED_DENSITY_CEILING,
        gt=0,
        le=1,
    )
    acceptable_density_ceiling: float = Field(
        default=TEMPLATE_V1_ACCEPTABLE_DENSITY_CEILING,
        gt=0,
        le=1,
    )
    ideal_density: float = Field(default=TEMPLATE_V1_IDEAL_DENSITY, gt=0, le=1)
    preferred_density_reached: bool = False
    preferred_density_status: PreferredDensityStatus = PreferredDensityStatus.BELOW_PREFERRED
    underfill_reasons: list[CompositionUnderfillReason] = Field(default_factory=list)
    profile_appears_incomplete: bool = False
    normalized_posting_features: list[str] = Field(default_factory=list)
    page_count: int | None = Field(default=None, ge=0)
    verification_status: PageVerificationStatus
    verification_provider: str
    verification_failure: str | None = None
    additional_evidence_unavailable: bool
    reason: str
    beam_width: int = Field(gt=0)
    maximum_page_evaluations: int = Field(gt=0)
    maximum_estimated_page_evaluations: int = Field(gt=0)
    maximum_exact_finalist_evaluations: int = Field(gt=0)
    maximum_expansion_operations: int = Field(gt=0)
    maximum_selected_bullets: int = Field(gt=0)
    maximum_selected_entries: int = Field(gt=0)
    estimated_page_evaluations: int = Field(ge=0)
    exact_page_evaluations: int = Field(ge=0)
    expansion_operations: int = Field(ge=0)
    maximum_search_depth: int | None = None


__all__ = [
    "BulletLineFitDiagnostic",
    "CandidateExclusionCategory",
    "CompositionCandidateDiagnostic",
    "CompositionCandidateKind",
    "CompositionOutcome",
    "CompositionTerminationReason",
    "CompositionUnderfillReason",
    "EntryBulletSelectionDiagnostic",
    "ExperiencePackageAlternativeDiagnostic",
    "ExperiencePackageSelectionDiagnostic",
    "ExperienceSingleBulletExceptionReason",
    "LineFitVerificationStatus",
    "PageFillIterationDiagnostic",
    "PageFitEvaluation",
    "PageVerificationStatus",
    "PortfolioMarginalComparisonDiagnostic",
    "PreferredDensityStatus",
    "ProjectRepresentationDiagnostic",
    "ProjectRepresentationStatus",
    "RESUME_COMPOSITION_CONTRACT_VERSION",
    "ResumeCompositionDiagnostic",
    "SkillRowSelectionDiagnostic",
    "TEMPLATE_V1_DENSITY_INVESTIGATION_FLOOR",
    "TEMPLATE_V1_ACCEPTABLE_DENSITY_CEILING",
    "TEMPLATE_V1_IDEAL_DENSITY",
    "TEMPLATE_V1_PREFERRED_DENSITY_CEILING",
    "TEMPLATE_V1_PREFERRED_DENSITY_FLOOR",
    "TEMPLATE_V1_UTILIZATION_TARGET_CEILING",
    "TEMPLATE_V1_UTILIZATION_TARGET_FLOOR",
]
