from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from resume_tailor.domain.resume_composition import BulletLineFitDiagnostic

EVIDENCE_RETRIEVAL_CONTRACT_VERSION = "resume-evidence-retrieval-v1"
RESUME_WRITING_CONTRACT_VERSION = "evidence-grounded-bullet-v2"
RESUME_WRITING_POLICY_VERSION = "technical-resume-writing-v1"


class RetrievalAdmissionStatus(StrEnum):
    ADMITTED_DIRECT = "admitted_direct"
    ADMITTED_ADJACENT = "admitted_adjacent"
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
    PROVIDER_TIMEOUT = "provider_timeout"
    CACHE_HIT = "cache_hit"
    WRITER_SUCCEEDED = "writer_succeeded"
    MALFORMED_WRITER_OUTPUT = "malformed_writer_output"
    ALL_GENERATED_VARIANTS_REJECTED = "all_generated_variants_rejected"
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
    admitted: list[RetrievedEvidence] = Field(default_factory=list)
    rejected: list[RetrievedEvidence] = Field(default_factory=list)


class GroundedClaim(BaseModel):
    text: str
    supporting_evidence_ids: list[str] = Field(min_length=1)
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)
    validation_status: ClaimValidationStatus
    reason: str


class BulletVariantRecord(BaseModel):
    variant_id: str
    entry_id: str
    source_evidence_ids: list[str] = Field(min_length=1)
    original_reviewed_text: list[str] = Field(min_length=1)
    rewritten_text: str
    factual_claims: list[GroundedClaim] = Field(min_length=1)
    target_job_requirements: list[str] = Field(default_factory=list)
    intended_length_class: BulletLengthClass
    writing_policy_version: str = RESUME_WRITING_POLICY_VERSION
    contract_version: str = RESUME_WRITING_CONTRACT_VERSION
    provider: str
    model: str
    validation_status: BulletValidationStatus
    validation_reasons: list[str] = Field(default_factory=list)
    line_fit: BulletLineFitDiagnostic
    material_improvement: bool = False
    improvement_reasons: list[str] = Field(default_factory=list)
    selected: bool = False
    future_user_review: bool = False


class HybridResumeDiagnostic(BaseModel):
    retrieval: EvidenceRetrievalResult | None = None
    planning_status: HybridPlanningStatus = HybridPlanningStatus.DETERMINISTIC_ONLY
    planning_reason: str = "Deterministic planning remained authoritative."
    writing_status: HybridPlanningStatus = HybridPlanningStatus.DETERMINISTIC_ONLY
    writer_execution_status: WriterExecutionStatus = (
        WriterExecutionStatus.REWRITING_DISABLED
    )
    writing_reason: str = "Reviewed source bullets remained authoritative."
    source_writer_path: str = "reviewed_profile_evidence"
    layout_input: str = "reviewed_source_bullets"
    bullet_variants: list[BulletVariantRecord] = Field(default_factory=list)
    rejected_variants: list[BulletVariantRecord] = Field(default_factory=list)
    validation_failures: list[str] = Field(default_factory=list)
    provider_call_count: int = Field(default=0, ge=0)
    provider_cache_hits: int = Field(default=0, ge=0)
    rewrite_enabled: bool = False
    deterministic_fallback_used: bool = True
    source_bullet_count: int = Field(default=0, ge=0)
    rewritten_bullet_count: int = Field(default=0, ge=0)
    fallback_bullet_count: int = Field(default=0, ge=0)
    rejected_variant_count: int = Field(default=0, ge=0)
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
    "HybridPlanningStatus",
    "HybridResumeDiagnostic",
    "RESUME_WRITING_CONTRACT_VERSION",
    "RESUME_WRITING_POLICY_VERSION",
    "RetrievalAdmissionStatus",
    "RetrievedEvidence",
    "WriterExecutionStatus",
]
