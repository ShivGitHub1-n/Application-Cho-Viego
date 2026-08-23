from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from resume_tailor.domain.company_research import CompanyResearchBundle
from resume_tailor.domain.generated_artifact import StageTiming
from resume_tailor.domain.models import ContactInfo


class CoverLetterParagraphPurpose(StrEnum):
    OPENING = "opening"
    INTRODUCTION = "opening"
    EXPERIENCE_CONNECTION = "experience_connection"
    EVIDENCE = "experience_connection"
    CONTRIBUTION = "contribution"
    ROLE_FIT = "role_fit"
    CLOSING = "closing"


def normalize_paragraph_purpose(value: object) -> CoverLetterParagraphPurpose:
    if isinstance(value, CoverLetterParagraphPurpose):
        return value
    normalized = str(value).strip().casefold().replace("-", "_").replace(" ", "_")
    legacy = {
        "introduction": CoverLetterParagraphPurpose.OPENING.value,
        "evidence": CoverLetterParagraphPurpose.EXPERIENCE_CONNECTION.value,
    }
    try:
        return CoverLetterParagraphPurpose(legacy.get(normalized, normalized))
    except ValueError as error:
        raise ValueError(f"Unsupported paragraph purpose: {value}") from error


class CoverLetterReviewState(StrEnum):
    NOT_GENERATED = "not_generated"
    GENERATING = "generating"
    GENERATED_AWAITING_REVIEW = "generated_awaiting_review"
    WORDING_CHANGED_REBUILD_REQUIRED = "wording_changed_rebuild_required"
    REBUILD_IN_PROGRESS = "rebuild_in_progress"
    REBUILT_AWAITING_REVIEW = "rebuilt_awaiting_review"
    APPROVED = "approved"
    DOWNLOADED = "downloaded"
    GENERATION_FAILED = "generation_failed"
    RESEARCH_LIMITED = "research_limited"


class CoverLetterValidationStatus(StrEnum):
    SUPPORTED = "supported"
    REVIEW_REQUIRED = "review_required"
    REJECTED = "rejected"


class CoverLetterQualityGateStatus(StrEnum):
    PASSED = "passed"
    REVIEW_REQUIRED = "review_required"
    FAILED = "failed"


class CoverLetterEvidenceKind(StrEnum):
    EXPERIENCE = "experience"
    PROJECT = "project"
    EDUCATION = "education"
    SKILL = "skill"
    USER_MOTIVATION = "user_motivation"


class CoverLetterLengthClass(StrEnum):
    CONCISE = "concise"
    STANDARD = "standard"
    DEVELOPED = "developed"


class CoverLetterCanonicalMetadata(StrEnum):
    COMPANY_NAME = "company_name"
    ROLE_TITLE = "role_title"


class CoverLetterSentenceAuthority(BaseModel):
    """Exact authority attached to one deterministic cover-letter sentence."""

    text: str = Field(min_length=1, max_length=900)
    posting_fact_ids: list[str] = Field(default_factory=list, max_length=3)
    candidate_evidence_ids: list[str] = Field(default_factory=list, max_length=3)
    verified_company_fact_ids: list[str] = Field(default_factory=list, max_length=3)
    canonical_metadata: list[CoverLetterCanonicalMetadata] = Field(
        default_factory=list,
        max_length=2,
    )


class CoverLetterProviderStatus(StrEnum):
    SUCCEEDED = "succeeded"
    CACHE_HIT = "cache_hit"
    DISABLED = "disabled"
    CONFIGURATION_UNAVAILABLE = "configuration_unavailable"
    MALFORMED_OUTPUT = "malformed_output"
    REQUEST_FAILED = "request_failed"
    VALIDATION_FALLBACK = "validation_fallback"


class CoverLetterFallbackReason(StrEnum):
    PROVIDER_DISABLED = "provider_disabled"
    CREDENTIALS_ABSENT = "credentials_absent"
    PROVIDER_MALFORMED_AFTER_REPAIR = "provider_malformed_after_repair"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_RATE_LIMIT = "provider_rate_limit"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    ALL_PARAGRAPHS_REJECTED = "all_generated_paragraphs_rejected"
    RESEARCH_UNAVAILABLE = "research_unavailable"
    COMPANY_FACT_NOT_VERIFIED = "company_fact_not_verified"
    PROVIDER_PAGE_FIT_REJECTED = "provider_page_fit_rejected"


class CoverLetterProviderFailureStage(StrEnum):
    REQUEST = "request"
    RESPONSE_PARSING = "response_parsing"
    CLAIM_VALIDATION = "claim_validation"
    PAGE_FIT = "page_fit"


class CoverLetterPageFitStatus(StrEnum):
    PREFERRED_DENSITY = "preferred_density"
    ACCEPTABLE_DENSITY = "acceptable_density"
    SEVERE_UNDERFILL = "severe_underfill"
    OVERFLOW = "overflow"
    PAGINATION_UNVERIFIED = "pagination_unverified"
    BLANK_TRAILING_PAGE = "blank_trailing_page"


class CoverLetterRecipient(BaseModel):
    name: str | None = None
    title: str | None = None
    company: str | None = None
    address_lines: list[str] = Field(default_factory=list, max_length=4)


class CoverLetterEvidenceRecord(BaseModel):
    id: str
    kind: CoverLetterEvidenceKind
    entity_id: str | None = None
    entry_title: str | None = None
    source_text: str
    writer_text: str | None = None
    excluded_title_claims: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    outcomes: list[str] = Field(default_factory=list)
    provenance: list[str] = Field(default_factory=list)
    matched_requirements: list[str] = Field(default_factory=list)
    retrieval_rank: int | None = Field(default=None, ge=1)
    selected_in_final_resume: bool = False
    selected_for_letter: bool = True
    selection_reason: str


class CoverLetterNarrativeStory(BaseModel):
    """One ordered, evidence-authorized story in the internal writing plan."""

    thread_id: str
    entry_id: str | None = None
    authoritative_title: str | None = None
    evidence_ids: list[str] = Field(min_length=1, max_length=3)
    focus: str = Field(min_length=1, max_length=240)
    role_connection: str = Field(min_length=1, max_length=360)


class CoverLetterNarrativePlan(BaseModel):
    """Typed narrative intent prepared before prose generation."""

    thesis: str = Field(min_length=1, max_length=500)
    company_role_hook: str = Field(min_length=1, max_length=500)
    role_themes: list[str] = Field(min_length=1, max_length=4)
    stories: list[CoverLetterNarrativeStory] = Field(min_length=1, max_length=3)
    authoritative_entry_titles: dict[str, str] = Field(default_factory=dict)
    prohibited_title_claims: list[str] = Field(default_factory=list)
    tone: str = Field(min_length=1, max_length=240)


class CoverLetterClaimDiagnostic(BaseModel):
    id: str
    text: str
    candidate_evidence_ids: list[str] = Field(default_factory=list)
    company_research_ids: list[str] = Field(default_factory=list)
    status: CoverLetterValidationStatus
    codes: list[str] = Field(default_factory=list)
    detail: str
    paragraph_index: int | None = Field(default=None, ge=0)
    sentence_index: int | None = Field(default=None, ge=0)


class CoverLetterParagraph(BaseModel):
    id: str
    purpose: CoverLetterParagraphPurpose
    text: str = Field(min_length=1, max_length=2400)
    candidate_evidence_ids: list[str] = Field(default_factory=list)
    company_research_ids: list[str] = Field(default_factory=list)
    narrative_thread_id: str | None = None
    length_class: CoverLetterLengthClass = CoverLetterLengthClass.STANDARD
    sentence_authorities: list[CoverLetterSentenceAuthority] = Field(default_factory=list)
    claims: list[CoverLetterClaimDiagnostic] = Field(default_factory=list)
    validation_status: CoverLetterValidationStatus = CoverLetterValidationStatus.SUPPORTED
    deterministic_fallback: bool = False


class CoverLetterLayoutProfile(BaseModel):
    """Standard-business-brief tokens with a restrained correspondence header override."""

    profile_id: str = "cover-letter-correspondence-v6"
    preset_name: str = "standard_business_brief"
    header_pattern: str = "proposal_centerpiece_minimal_correspondence_override"
    page_width_inches: float = 8.5
    page_height_inches: float = 11.0
    top_margin_inches: float = 1.0
    bottom_margin_inches: float = 1.0
    left_margin_inches: float = 1.0
    right_margin_inches: float = 1.0
    header_distance_inches: float = 0.492
    footer_distance_inches: float = 0.492
    body_font: str = "Calibri"
    body_size_pt: float = 11.0
    body_alignment: str = "left"
    line_spacing: float = 1.10
    paragraph_spacing_pt: float = 8.0
    candidate_name_size_pt: float = 16.0
    contact_size_pt: float = 10.0
    contact_spacing_pt: float = 2.0
    signoff_spacing_pt: float = 2.0
    contact_separator: str = " | "
    preferred_utilization_floor: float = 0.82
    preferred_utilization_ceiling: float = 0.90
    acceptable_utilization_floor: float = 0.76
    acceptable_utilization_ceiling: float = 0.94
    target_utilization: float = 0.86

    @property
    def usable_width_inches(self) -> float:
        return self.page_width_inches - self.left_margin_inches - self.right_margin_inches

    @property
    def usable_height_inches(self) -> float:
        return self.page_height_inches - self.top_margin_inches - self.bottom_margin_inches


class CoverLetter(BaseModel):
    profile_id: str
    profile_version: int
    posting_id: str
    plan_fingerprint: str | None = None
    candidate_name: str
    contact: ContactInfo
    date_text: str
    job_title: str
    company_name: str | None = None
    recipient: CoverLetterRecipient = Field(default_factory=CoverLetterRecipient)
    salutation: str
    paragraphs: list[CoverLetterParagraph] = Field(min_length=3)
    signoff: str = "Sincerely,"
    signoff_name: str
    layout_profile: CoverLetterLayoutProfile = Field(default_factory=CoverLetterLayoutProfile)

    @model_validator(mode="after")
    def validate_structure(self) -> CoverLetter:
        if self.paragraphs[0].purpose is not CoverLetterParagraphPurpose.OPENING:
            raise ValueError("The first cover-letter paragraph must be an opening")
        if self.paragraphs[-1].purpose is not CoverLetterParagraphPurpose.CLOSING:
            raise ValueError("The final cover-letter paragraph must be a closing")
        paragraph_ids = [paragraph.id for paragraph in self.paragraphs]
        if len(paragraph_ids) != len(set(paragraph_ids)):
            raise ValueError("Cover-letter paragraph IDs must be unique")
        return self


class CoverLetterQualityGateResult(BaseModel):
    gate: str
    status: CoverLetterQualityGateStatus
    code: str
    detail: str


class CoverLetterEvidenceSelectionDiagnostic(BaseModel):
    selected_evidence_ids: list[str]
    omitted_resume_evidence_ids: list[str] = Field(default_factory=list)
    used_evidence_omitted_from_resume_ids: list[str] = Field(default_factory=list)
    considered_evidence_count: int = Field(ge=0)
    narrative_thread_count: int = Field(ge=0, le=3)
    reasons: list[str] = Field(default_factory=list)


class CoverLetterResumeConsistencyFinding(BaseModel):
    status: CoverLetterValidationStatus
    code: str
    detail: str
    evidence_ids: list[str] = Field(default_factory=list)


class CoverLetterCandidateValidationDiagnostic(BaseModel):
    """Safe, validator-separated outcome for one generated prose candidate."""

    candidate_id: str
    candidate_index: int = Field(ge=0)
    generation_source: str
    paragraph_count: int = Field(ge=0)
    sentence_count: int = Field(ge=0)
    source_bound_sentence_count: int = Field(default=0, ge=0)
    unbound_sentence_count: int = Field(default=0, ge=0)
    character_count: int = Field(ge=0)
    posting_fingerprint: str
    company_name: str | None = None
    recipient_company: str | None = None
    posting_authority_fact_count: int = Field(ge=0)
    verified_company_fact_count: int = Field(ge=0)
    selected_evidence_ids: list[str] = Field(default_factory=list)
    accepted_resume_narrative_fingerprint: str | None = None
    structural_validation: CoverLetterQualityGateStatus
    company_validation: CoverLetterQualityGateStatus
    narrative_validation: CoverLetterQualityGateStatus
    claim_validation: CoverLetterQualityGateStatus
    rejection_codes: list[str] = Field(default_factory=list)
    rejection_summaries: list[str] = Field(default_factory=list)
    rejected_paragraph_indexes: list[int] = Field(default_factory=list)
    rejected_sentence_indexes: list[int] = Field(default_factory=list)
    rendering_attempted: bool = False


class CoverLetterProviderDiagnostic(BaseModel):
    provider: str
    model: str
    status: CoverLetterProviderStatus
    request_count: int = Field(ge=0, le=2)
    repair_count: int = Field(ge=0, le=1)
    cache_hit_count: int = Field(ge=0)
    elapsed_seconds: float = Field(ge=0)
    finish_reason: str | None = None
    fallback_reason: CoverLetterFallbackReason | None = None
    failure_stage: CoverLetterProviderFailureStage | None = None
    failure_code: str | None = Field(default=None, max_length=120)
    structured_parsing_succeeded: bool = False
    semantic_validation_succeeded: bool | None = None
    provider_candidate_selected: bool = False
    safe_detail: str


class CoverLetterPageFitCandidateDiagnostic(BaseModel):
    candidate_id: str
    evidence_ids: list[str] = Field(default_factory=list)
    company_research_ids: list[str] = Field(default_factory=list)
    estimated_utilization: float = Field(ge=0)
    estimated_remaining_lines: int = Field(ge=0)
    page_count: int = Field(ge=1)
    exact_pagination: bool
    status: CoverLetterPageFitStatus
    selected: bool = False
    rejection_code: str | None = None
    rejection_reason: str | None = None


class CoverLetterPageFitDiagnostic(BaseModel):
    status: CoverLetterPageFitStatus
    selected_candidate_id: str
    page_count: int = Field(ge=1)
    exact_pagination: bool
    pagination_provider: str
    pagination_failure: str | None = None
    estimated_utilization: float = Field(ge=0)
    estimated_remaining_lines: int = Field(ge=0)
    preferred_density_reachable: bool
    underfill_or_overflow: str
    manual_word_inspection_required: bool
    blank_trailing_page: bool = False
    evidence_added_during_page_fit: list[str] = Field(default_factory=list)
    evidence_removed_during_page_fit: list[str] = Field(default_factory=list)
    candidates: list[CoverLetterPageFitCandidateDiagnostic] = Field(default_factory=list)


class CoverLetterCallCounts(BaseModel):
    research_calls: int = Field(default=0, ge=0)
    research_network_requests: int = Field(default=0, ge=0, le=3)
    provider_calls: int = Field(default=0, ge=0, le=2)
    provider_repairs: int = Field(default=0, ge=0, le=1)
    claim_validations: int = Field(default=0, ge=0)
    composition_searches: int = Field(default=0, ge=0)
    docx_renders: int = Field(default=0, ge=0)
    pagination_attempts: int = Field(default=0, ge=0, le=1)
    download_preparations: int = Field(default=0, ge=0)


class CoverLetterArtifactFingerprintInputs(BaseModel):
    reviewed_profile_fingerprint: str
    posting_fingerprint: str
    plan_fingerprint: str | None = None
    final_resume_fingerprint: str | None = None
    research_request_fingerprint: str
    research_fingerprint: str
    evidence_fingerprint: str
    recipient_fingerprint: str
    date_text: str
    motivation_fingerprint: str | None = None
    writing_policy_version: str
    provider_contract_version: str
    validation_policy_version: str
    template_identity: str
    provider: str
    model: str


class GeneratedCoverLetterArtifact(BaseModel):
    model_config = ConfigDict(frozen=True)

    artifact_fingerprint: str
    artifact_version: int = Field(ge=1)
    fingerprint_inputs: CoverLetterArtifactFingerprintInputs
    generation_timestamp: datetime
    review_state: CoverLetterReviewState
    ready_for_review: bool
    current: bool = True
    letter: CoverLetter
    evidence_records: list[CoverLetterEvidenceRecord]
    company_research: CompanyResearchBundle
    evidence_selection: CoverLetterEvidenceSelectionDiagnostic
    quality_gates: list[CoverLetterQualityGateResult]
    candidate_validations: list[CoverLetterCandidateValidationDiagnostic] = Field(
        default_factory=list
    )
    rejected_claims: list[CoverLetterClaimDiagnostic] = Field(default_factory=list)
    review_required_claims: list[CoverLetterClaimDiagnostic] = Field(default_factory=list)
    resume_consistency: list[CoverLetterResumeConsistencyFinding] = Field(default_factory=list)
    provider_diagnostic: CoverLetterProviderDiagnostic
    page_fit: CoverLetterPageFitDiagnostic
    call_counts: CoverLetterCallCounts
    stage_timings: list[StageTiming] = Field(default_factory=list)
    total_build_seconds: float = Field(ge=0)
    docx_bytes: bytes
    approved_at: datetime | None = None


class CoverLetterDownload(BaseModel):
    model_config = ConfigDict(frozen=True)

    artifact_fingerprint: str
    artifact_version: int
    docx_bytes: bytes
    elapsed_seconds: float = Field(ge=0)
    generation_call_counts: CoverLetterCallCounts = Field(default_factory=CoverLetterCallCounts)


__all__ = [
    "CoverLetter",
    "CoverLetterArtifactFingerprintInputs",
    "CoverLetterCallCounts",
    "CoverLetterClaimDiagnostic",
    "CoverLetterDownload",
    "CoverLetterEvidenceKind",
    "CoverLetterEvidenceRecord",
    "CoverLetterEvidenceSelectionDiagnostic",
    "CoverLetterFallbackReason",
    "CoverLetterLayoutProfile",
    "CoverLetterLengthClass",
    "CoverLetterNarrativePlan",
    "CoverLetterNarrativeStory",
    "CoverLetterPageFitCandidateDiagnostic",
    "CoverLetterPageFitDiagnostic",
    "CoverLetterPageFitStatus",
    "CoverLetterParagraph",
    "CoverLetterParagraphPurpose",
    "CoverLetterProviderDiagnostic",
    "CoverLetterProviderStatus",
    "CoverLetterQualityGateResult",
    "CoverLetterQualityGateStatus",
    "CoverLetterRecipient",
    "CoverLetterResumeConsistencyFinding",
    "CoverLetterReviewState",
    "CoverLetterValidationStatus",
    "GeneratedCoverLetterArtifact",
    "normalize_paragraph_purpose",
]
