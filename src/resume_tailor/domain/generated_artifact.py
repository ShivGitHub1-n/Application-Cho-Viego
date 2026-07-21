from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from resume_tailor.domain.hybrid_resume import (
    BulletVariantRecord,
    HybridResumeDiagnostic,
    ProviderRequestShapeDiagnostic,
    WriterPipelineIssue,
)
from resume_tailor.domain.models import StructuredResume, TailoringPlan
from resume_tailor.domain.resume_composition import ResumeCompositionDiagnostic


class GenerationStage(StrEnum):
    PROFILE_LOADING = "profile_loading"
    POSTING_NORMALIZATION = "posting_normalization"
    EVIDENCE_RETRIEVAL = "evidence_retrieval"
    DETERMINISTIC_PLANNING = "deterministic_planning"
    SEMANTIC_PLANNING = "semantic_planning"
    PLAN_VALIDATION = "plan_validation"
    WRITER_SHORTLIST = "writer_shortlist"
    WRITER_CACHE_LOOKUP = "writer_cache_lookup"
    PROVIDER_REQUEST = "provider_request"
    PROVIDER_RESPONSE_PARSING = "provider_response_parsing"
    CLAIM_VALIDATION = "claim_validation"
    WRITER_VARIANT_SELECTION = "writer_variant_selection"
    COMPOSITION_CANDIDATE_CONSTRUCTION = "composition_candidate_construction"
    PORTFOLIO_PAGE_FIT_SEARCH = "portfolio_page_fit_search"
    DOCX_RENDERING = "docx_rendering"
    EXACT_WORD_PAGINATION = "exact_word_pagination"
    ESTIMATED_PAGINATION_FALLBACK = "estimated_pagination_fallback"
    GENERATED_ARTIFACT_STORAGE = "generated_artifact_storage"
    STREAMLIT_RERUN_OVERHEAD = "streamlit_rerun_overhead"
    DOWNLOAD_PREPARATION = "download_preparation"


class StageStatus(StrEnum):
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


class StageTiming(BaseModel):
    stage: GenerationStage
    elapsed_seconds: float = Field(ge=0)
    invocation_count: int = Field(default=1, ge=0)
    status: StageStatus = StageStatus.COMPLETED
    detail: str | None = None


class GenerationCallCounts(BaseModel):
    profile_loads: int = Field(default=0, ge=0)
    posting_normalizations: int = Field(default=0, ge=0)
    evidence_retrievals: int = Field(default=0, ge=0)
    deterministic_plans: int = Field(default=0, ge=0)
    semantic_plans: int = Field(default=0, ge=0)
    provider_calls: int = Field(default=0, ge=0)
    provider_retries: int = Field(default=0, ge=0)
    claim_validations: int = Field(default=0, ge=0)
    composition_searches: int = Field(default=0, ge=0)
    docx_renders: int = Field(default=0, ge=0)
    pagination_attempts: int = Field(default=0, ge=0)


class ProviderExecutionDiagnostic(BaseModel):
    writing_enabled: bool
    provider: str
    model: str
    status: str
    call_count: int = Field(ge=0)
    retry_count: int = Field(ge=0)
    cache_hit_count: int = Field(ge=0)
    request_timeout_seconds: float = Field(gt=0)
    configured_retry_count: int = Field(ge=0)
    retry_reason: str | None = None
    finish_reason: str | None = None
    pipeline_issue: WriterPipelineIssue | None = None
    request_shape: ProviderRequestShapeDiagnostic | None = None
    provider_elapsed_seconds: float = Field(default=0, ge=0)
    parsing_elapsed_seconds: float = Field(default=0, ge=0)
    validation_elapsed_seconds: float = Field(default=0, ge=0)
    deterministic_fallback_used: bool
    reason: str


class PaginationExecutionDiagnostic(BaseModel):
    status: str
    attempt_count: int = Field(ge=0, le=1)
    provider: str
    elapsed_seconds: float = Field(ge=0)
    failure_reason: str | None = None


class ArtifactFingerprintInputs(BaseModel):
    reviewed_profile_fingerprint: str
    normalized_posting_fingerprint: str
    validated_plan_fingerprint: str
    approved_claim_ids: list[str] = Field(default_factory=list)
    template_identity: str
    composition_contract_version: str
    writing_policy_version: str
    writing_contract_version: str
    feature_flags: dict[str, bool] = Field(default_factory=dict)
    provider: str
    model: str


class GeneratedResumeArtifact(BaseModel):
    model_config = ConfigDict(frozen=True)

    artifact_fingerprint: str
    fingerprint_inputs: ArtifactFingerprintInputs
    generation_timestamp: datetime
    template_identity: str
    composition_contract_version: str
    writing_policy_version: str
    writing_contract_version: str
    final_validated_plan: TailoringPlan
    final_resume: StructuredResume
    selected_bullet_variants: list[BulletVariantRecord] = Field(default_factory=list)
    composition_diagnostic: ResumeCompositionDiagnostic | None = None
    writing_diagnostic: HybridResumeDiagnostic | None = None
    stage_timings: list[StageTiming] = Field(default_factory=list)
    call_counts: GenerationCallCounts
    provider_diagnostic: ProviderExecutionDiagnostic
    pagination_diagnostic: PaginationExecutionDiagnostic
    total_build_seconds: float = Field(ge=0)
    docx_bytes: bytes


class ArtifactDownload(BaseModel):
    model_config = ConfigDict(frozen=True)

    artifact_fingerprint: str
    docx_bytes: bytes
    preparation_timing: StageTiming
    generation_call_counts: GenerationCallCounts = Field(default_factory=GenerationCallCounts)


__all__ = [
    "ArtifactDownload",
    "ArtifactFingerprintInputs",
    "GeneratedResumeArtifact",
    "GenerationCallCounts",
    "GenerationStage",
    "PaginationExecutionDiagnostic",
    "ProviderExecutionDiagnostic",
    "StageStatus",
    "StageTiming",
]
