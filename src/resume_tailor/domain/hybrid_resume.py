from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from resume_tailor.domain.requirement_ranking import (
    EvidenceRelationship,
    PostingRequirement,
    ShortTokenContribution,
)
from resume_tailor.domain.resume_composition import BulletLineFitDiagnostic

EVIDENCE_RETRIEVAL_CONTRACT_VERSION = "resume-evidence-retrieval-v1"
RESUME_WRITING_CONTRACT_VERSION = "evidence-grounded-bullet-v3"
RESUME_WRITING_POLICY_VERSION = "technical-recruiter-writing-v5"
RESUME_WRITING_PROMPT_VERSION = "gemini-batched-writer-v2"


class RetrievalAdmissionStatus(StrEnum):
    ADMITTED_DIRECT = "admitted_direct"
    ADMITTED_ADJACENT = "admitted_adjacent"
    ADMITTED_COMPLEMENTARY = "admitted_complementary"
    REJECTED_INCIDENTAL = "rejected_incidental"
    REJECTED_GENERIC_ONLY = "rejected_generic_only"
    REJECTED_LOW_RELEVANCE = "rejected_low_relevance"
    REJECTED_MISSING_METADATA = "rejected_missing_metadata"
    REJECTED_UNREVIEWED = "rejected_unreviewed"


class HybridPlanningStatus(StrEnum):
    DISABLED = "disabled"
    DETERMINISTIC_ONLY = "deterministic_only"
    ADVISORY_APPLIED = "advisory_applied"
    ADVISORY_REJECTED = "advisory_rejected"


class WriterExecutionStatus(StrEnum):
    REWRITING_DISABLED = "rewriting_disabled"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_REQUEST_FAILED = "provider_request_failed"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_SAFETY_BLOCKED = "provider_safety_blocked"
    PROVIDER_EMPTY_RESPONSE = "provider_empty_response"
    RESPONSE_EXTRACTION_FAILED = "response_extraction_failed"
    CACHE_HIT = "cache_hit"
    WRITER_SUCCEEDED = "writer_succeeded"
    WRITER_PARTIALLY_SUCCEEDED = "writer_partially_succeeded"
    MALFORMED_WRITER_OUTPUT = "malformed_writer_output"
    ALL_GENERATED_VARIANTS_REJECTED = "all_generated_variants_rejected"
    NO_MATERIAL_IMPROVEMENT = "no_material_improvement"
    SOURCE_VARIANTS_SCORED_BETTER = "source_variants_scored_better"
    SOURCE_FALLBACK_USED = "source_fallback_used"


class BulletLengthClass(StrEnum):
    CONCISE_ONE_LINE = "concise_one_line"
    STANDARD_ONE_TO_TWO_LINES = "standard_one_to_two_lines"
    FULL_TWO_LINES = "full_two_lines"
    EXCEPTIONAL_THREE_LINES = "exceptional_three_lines"


class BulletValidationStatus(StrEnum):
    VALIDATED = "validated"
    REVIEW_REQUIRED = "review_required"
    REJECTED = "rejected"
    SOURCE_FALLBACK = "source_fallback"


class ClaimValidationStatus(StrEnum):
    SUPPORTED = "supported"
    REJECTED = "rejected"
    REVIEW_REQUIRED = "review_required"


class ProviderRewriteMappingStatus(StrEnum):
    MAPPED = "mapped"
    REJECTED_EMPTY_EVIDENCE = "rejected_empty_evidence"
    REJECTED_DUPLICATE_EVIDENCE = "rejected_duplicate_evidence"
    REJECTED_UNKNOWN_EVIDENCE = "rejected_unknown_evidence"
    REJECTED_CROSS_ENTRY_EVIDENCE = "rejected_cross_entry_evidence"
    REJECTED_DUPLICATE_VARIANT = "rejected_duplicate_variant"
    REJECTED_INTERNAL_CONTRACT = "rejected_internal_contract"


class GroundingFailureCode(StrEnum):
    DUPLICATE_EVIDENCE = "duplicate_evidence"
    UNKNOWN_EVIDENCE = "unknown_evidence"
    CROSS_ENTRY_EVIDENCE = "cross_entry_evidence"
    INCORRECT_COMBINATION_STATUS = "incorrect_combination_status"
    UNSUPPORTED_CLAIM = "unsupported_claim"
    CLAIM_PROVENANCE = "claim_provenance"
    CHANGED_NUMBER_OR_METRIC = "changed_number_or_metric"
    UNSUPPORTED_TECHNOLOGY_OR_ENTITY = "unsupported_technology_or_entity"
    OWNERSHIP_EXPANSION = "ownership_expansion"
    UNSUPPORTED_CAUSAL_OUTCOME = "unsupported_causal_outcome"
    UNSUPPORTED_OUTCOME = "unsupported_outcome"
    UNSUPPORTED_NARROWING_OR_SCOPE = "unsupported_narrowing_or_scope"
    WRITING_POLICY_REJECTION = "writing_policy_rejection"
    SEMANTIC_EQUIVALENCE_REVIEW = "semantic_equivalence_review"
    NO_MATERIAL_IMPROVEMENT = "no_material_improvement"
    INTERNAL_CONTRACT = "internal_contract"
    OTHER_VALIDATION_RULE = "other_validation_rule"


class ProviderRewriteMappingOutcome(BaseModel):
    rewrite_index: int = Field(ge=0)
    evidence_ids: list[str] = Field(default_factory=list)
    rewritten_text: str
    mapping_status: ProviderRewriteMappingStatus
    entry_id: str | None = None
    mapped_bullet_index: int | None = Field(default=None, ge=0)
    failure_codes: list[GroundingFailureCode] = Field(default_factory=list)
    failure_details: list[str] = Field(default_factory=list)


class WriterRewriteDiagnostic(BaseModel):
    rewrite_index: int = Field(ge=0)
    evidence_ids: list[str] = Field(default_factory=list)
    source_evidence_text: list[str] = Field(default_factory=list)
    rewritten_text: str
    reconstructed_claim: str | None = None
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    entry_id: str | None = None
    entry_type: str | None = None
    provider_contract_mapping_result: ProviderRewriteMappingStatus
    validator_rejection_codes: list[GroundingFailureCode] = Field(default_factory=list)
    validator_rejection_details: list[str] = Field(default_factory=list)
    normalized_unsupported_terms: list[str] = Field(default_factory=list)
    ownership_comparison: str
    metric_comparison: str
    causal_outcome_comparison: str
    singular_plural_scope_comparison: str
    validation_status: BulletValidationStatus
    batch_effect: str


class WriterPipelineStage(StrEnum):
    PROVIDER_REQUEST = "provider_request"
    RESPONSE_EXTRACTION = "response_extraction"
    JSON_PARSING = "json_parsing"
    TYPED_SCHEMA_VALIDATION = "typed_schema_validation"
    CLAIM_VALIDATION = "claim_validation"
    VARIANT_SELECTION = "variant_selection"


class WriterPipelineFailureCode(StrEnum):
    PROVIDER_TRANSPORT_OR_SDK_ERROR = "provider_transport_or_sdk_error"
    INVALID_MODEL_OR_CONFIG = "invalid_model_or_config"
    UNSUPPORTED_SCHEMA_KEYWORD = "unsupported_schema_keyword"
    SCHEMA_TOO_LARGE_OR_DEEP = "schema_too_large_or_deep"
    INCOMPATIBLE_SDK_API_VERSION = "incompatible_sdk_api_version"
    UNKNOWN_INVALID_ARGUMENT = "unknown_invalid_argument"
    PROVIDER_TIMEOUT = "provider_timeout"
    SAFETY_BLOCKED_RESPONSE = "safety_blocked_response"
    EMPTY_PROVIDER_RESPONSE = "empty_provider_response"
    RESPONSE_EXTRACTION_FAILED = "response_extraction_failed"
    MALFORMED_JSON = "malformed_json"
    TYPED_SCHEMA_MISMATCH = "typed_schema_mismatch"
    CLAIM_GROUNDING_REJECTION = "claim_grounding_rejection"
    ALL_REWRITES_REQUIRE_REVIEW = "all_rewrites_require_review"
    NO_MATERIAL_IMPROVEMENT = "no_material_improvement"
    SOURCE_VARIANT_SELECTED = "source_variant_selected"


class ProviderFieldViolation(BaseModel):
    field_path: str = Field(min_length=1, max_length=240)
    description: str = Field(min_length=1, max_length=300)


class ProviderRequestShapeDiagnostic(BaseModel):
    sdk_package: str
    sdk_version: str
    api_version: str | None = None
    endpoint: str | None = None
    model: str
    config_field_names: list[str] = Field(default_factory=list)
    request_field_types: dict[str, str] = Field(default_factory=dict)
    schema_byte_length: int = Field(ge=0)
    schema_nesting_depth: int = Field(ge=0)
    schema_property_count: int = Field(ge=0)
    schema_enum_count: int = Field(ge=0)
    schema_ref_count: int = Field(ge=0)
    schema_defs_count: int = Field(ge=0)
    schema_pre_inline_ref_count: int = Field(default=0, ge=0)
    schema_pre_inline_defs_count: int = Field(default=0, ge=0)
    schema_inlined_ref_count: int = Field(default=0, ge=0)
    source_schema_ref_sibling_violation_paths: list[str] = Field(default_factory=list)
    schema_ref_sibling_violation_paths: list[str] = Field(default_factory=list)
    schema_keywords: list[str] = Field(default_factory=list)
    removed_schema_keywords: list[str] = Field(default_factory=list)
    compatibility_findings: list[str] = Field(default_factory=list)


class WriterPipelineIssue(BaseModel):
    code: WriterPipelineFailureCode
    stage: WriterPipelineStage
    provider_error_kind: str | None = None
    exception_type: str | None = None
    provider_error_code: str | None = None
    finish_reason: str | None = None
    candidate_count: int | None = Field(default=None, ge=0)
    text_present: bool | None = None
    top_level_json_keys: list[str] = Field(default_factory=list)
    schema_error_field_paths: list[str] = Field(default_factory=list)
    field_violations: list[ProviderFieldViolation] = Field(default_factory=list)
    request_shape: ProviderRequestShapeDiagnostic | None = None
    sanitized_detail: str | None = Field(default=None, max_length=300)


class RetrievedEvidence(BaseModel):
    evidence_id: str
    entry_id: str
    entry_kind: str
    source_text: str
    rank: int = Field(ge=1)
    contextual_relevance: float = Field(ge=0)
    intrinsic_evidence_strength: float = Field(ge=0)
    complementary_value: float = Field(ge=0)
    total_score: float
    normalized_features: list[str] = Field(default_factory=list)
    meaningful_overlap: list[str] = Field(default_factory=list)
    matched_requirements: list[str] = Field(default_factory=list)
    relationship: EvidenceRelationship = EvidenceRelationship.REJECTED
    direct_requirement_ids: list[str] = Field(default_factory=list)
    adjacent_requirement_ids: list[str] = Field(default_factory=list)
    complementary_requirement_ids: list[str] = Field(default_factory=list)
    incidental_requirement_ids: list[str] = Field(default_factory=list)
    short_token_contributions: list[ShortTokenContribution] = Field(default_factory=list)
    admission_status: RetrievalAdmissionStatus
    admission_reason: str
    provenance: list[str] = Field(default_factory=list)


class EvidenceRetrievalResult(BaseModel):
    contract_version: str = EVIDENCE_RETRIEVAL_CONTRACT_VERSION
    strategy: str = "in_process_normalized_lexical_and_structured_evidence"
    profile_fingerprint: str
    posting_fingerprint: str
    complete_profile_evidence_count: int = Field(ge=0)
    reviewed_evidence_count: int = Field(ge=0)
    posting_requirements: list[PostingRequirement] = Field(default_factory=list)
    admitted: list[RetrievedEvidence] = Field(default_factory=list)
    rejected: list[RetrievedEvidence] = Field(default_factory=list)


class GroundedClaim(BaseModel):
    text: str
    supporting_evidence_ids: list[str] = Field(min_length=1)
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)
    validation_status: ClaimValidationStatus
    reason: str


class WriterShortlistCandidate(BaseModel):
    evidence_id: str
    entry_id: str
    entry_kind: str
    relationship: EvidenceRelationship
    contextual_relevance: float = Field(ge=0)
    intrinsic_evidence_strength: float = Field(ge=0)
    selected: bool
    selection_reason: str


class BulletVariantRecord(BaseModel):
    variant_id: str
    entry_id: str
    source_evidence_ids: list[str] = Field(min_length=1)
    original_reviewed_text: list[str] = Field(min_length=1)
    rewritten_text: str
    factual_claims: list[GroundedClaim] = Field(min_length=1)
    target_job_requirements: list[str] = Field(default_factory=list)
    relationship_tier: EvidenceRelationship = EvidenceRelationship.REJECTED
    intended_length_class: BulletLengthClass
    writing_policy_version: str = RESUME_WRITING_POLICY_VERSION
    contract_version: str = RESUME_WRITING_CONTRACT_VERSION
    prompt_version: str = RESUME_WRITING_PROMPT_VERSION
    provider: str
    model: str
    validation_status: BulletValidationStatus
    validation_reasons: list[str] = Field(default_factory=list)
    line_fit: BulletLineFitDiagnostic
    material_improvement: bool = False
    improvement_reasons: list[str] = Field(default_factory=list)
    selected: bool = False
    selection_reason: str | None = None
    future_user_review: bool = False


class HybridResumeDiagnostic(BaseModel):
    retrieval: EvidenceRetrievalResult | None = None
    planning_status: HybridPlanningStatus = HybridPlanningStatus.DETERMINISTIC_ONLY
    planning_reason: str = "Deterministic planning remained authoritative."
    writing_status: HybridPlanningStatus = HybridPlanningStatus.DETERMINISTIC_ONLY
    writer_execution_status: WriterExecutionStatus = WriterExecutionStatus.REWRITING_DISABLED
    writing_reason: str = "Reviewed source bullets remained authoritative."
    source_writer_path: str = "reviewed_profile_evidence"
    layout_input: str = "reviewed_source_bullets"
    writer_shortlist: list[WriterShortlistCandidate] = Field(default_factory=list)
    shortlisted_entry_ids: list[str] = Field(default_factory=list)
    shortlisted_evidence_ids: list[str] = Field(default_factory=list)
    bullet_variants: list[BulletVariantRecord] = Field(default_factory=list)
    rejected_variants: list[BulletVariantRecord] = Field(default_factory=list)
    rewrite_diagnostics: list[WriterRewriteDiagnostic] = Field(default_factory=list)
    validation_failures: list[str] = Field(default_factory=list)
    writer_pipeline_issue: WriterPipelineIssue | None = None
    provider_request_shape: ProviderRequestShapeDiagnostic | None = None
    provider_finish_reason: str | None = None
    provider_call_count: int = Field(default=0, ge=0)
    provider_retry_reason: str | None = None
    provider_cache_hits: int = Field(default=0, ge=0)
    rewrite_enabled: bool = False
    deterministic_fallback_used: bool = True
    source_bullet_count: int = Field(default=0, ge=0)
    rewritten_bullet_count: int = Field(default=0, ge=0)
    fallback_bullet_count: int = Field(default=0, ge=0)
    source_alternatives_available: int = Field(default=0, ge=0)
    rewrites_returned: int = Field(default=0, ge=0)
    rewrites_validated: int = Field(default=0, ge=0)
    rewrites_selected: int = Field(default=0, ge=0)
    source_bullets_selected: int = Field(default=0, ge=0)
    source_fallbacks_rendered: int = Field(default=0, ge=0)
    rejected_variant_count: int = Field(default=0, ge=0)
    review_required_variant_count: int = Field(default=0, ge=0)
    estimated_remaining_lines: int | None = Field(default=None, ge=0)
    exact_pagination: bool = False
    page_verification_provider: str | None = None
    underfill_reason: str | None = None


__all__ = [
    "BulletLengthClass",
    "BulletValidationStatus",
    "BulletVariantRecord",
    "ClaimValidationStatus",
    "EVIDENCE_RETRIEVAL_CONTRACT_VERSION",
    "EvidenceRetrievalResult",
    "GroundedClaim",
    "GroundingFailureCode",
    "HybridPlanningStatus",
    "HybridResumeDiagnostic",
    "RESUME_WRITING_CONTRACT_VERSION",
    "RESUME_WRITING_POLICY_VERSION",
    "RESUME_WRITING_PROMPT_VERSION",
    "RetrievalAdmissionStatus",
    "RetrievedEvidence",
    "WriterExecutionStatus",
    "ProviderFieldViolation",
    "ProviderRewriteMappingOutcome",
    "ProviderRewriteMappingStatus",
    "ProviderRequestShapeDiagnostic",
    "WriterPipelineFailureCode",
    "WriterPipelineIssue",
    "WriterPipelineStage",
    "WriterShortlistCandidate",
    "WriterRewriteDiagnostic",
]
