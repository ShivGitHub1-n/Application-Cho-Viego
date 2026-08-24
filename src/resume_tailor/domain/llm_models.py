from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from resume_tailor.domain.application_strategy import (
    APPLICATION_STRATEGY_RESERVE_MAXIMUM_ACTIONS,
    APPLICATION_STRATEGY_RESERVE_MINIMUM_ACTIONS,
    APPLICATION_STRATEGY_RESERVE_TARGET_ACTIONS,
    EvidencePriorityTier,
    SourceWordingAssessment,
)
from resume_tailor.domain.cover_letter import (
    CoverLetterLengthClass,
    CoverLetterNarrativePlan,
    CoverLetterParagraphPurpose,
    CoverLetterSentenceAuthority,
    normalize_paragraph_purpose,
)
from resume_tailor.domain.hybrid_resume import (
    RESUME_WRITING_CONTRACT_VERSION,
    RESUME_WRITING_POLICY_VERSION,
    RESUME_WRITING_PROMPT_VERSION,
    BulletLengthClass,
    ProviderRequestShapeDiagnostic,
    ProviderRewriteMappingOutcome,
    WriterPipelineIssue,
)
from resume_tailor.domain.models import ClaimConfidence, MasterProfile, RoleFamily
from resume_tailor.domain.requirement_ranking import EvidenceRelationship


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LlmOperation(StrEnum):
    PROFILE_EXTRACTION = "profile_extraction"
    CLASSIFY_ROLE = "classify_role"
    ANALYZE_OPPORTUNITY = "analyze_opportunity"
    APPLICATION_STRATEGY = "application_strategy"
    RECOMMEND_COMPOSITION = "recommend_composition"
    RECOMMEND_SKILL_COMPOSITION = "recommend_skill_composition"
    REWRITE_BULLETS = "rewrite_bullets"
    SHORTEN_BULLETS = "shorten_bullets"
    COVER_LETTER_DRAFT = "cover_letter_draft"


class LanguageModelErrorKind(StrEnum):
    CONFIGURATION = "configuration"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    NETWORK = "network"
    SAFETY_BLOCKED = "safety_blocked"
    MALFORMED_RESPONSE = "malformed_response"
    VALIDATION = "validation"
    TRUNCATED_RESPONSE = "truncated_response"
    EMPTY_RESPONSE = "empty_response"
    RESPONSE_EXTRACTION = "response_extraction"


class LanguageModelError(RuntimeError):
    def __init__(
        self,
        kind: LanguageModelErrorKind,
        message: str,
        retryable: bool = False,
        *,
        diagnostic: WriterPipelineIssue | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable
        self.diagnostic = diagnostic


class ModelCallMetadata(StrictModel):
    provider: str
    model: str
    operation: LlmOperation
    latency_ms: int = Field(ge=0)
    prompt_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    attempts: int = Field(default=1, ge=1)
    cache_hit: bool = False
    finish_reason: str | None = None
    finish_message: str | None = None
    request_shape: ProviderRequestShapeDiagnostic | None = None


class ModelResult(StrictModel):
    metadata: ModelCallMetadata


class EvidenceCoverageSummary(StrictModel):
    signal_id: str
    direct_evidence_ids: list[str] = Field(default_factory=list)
    declared_skill_names: list[str] = Field(default_factory=list)


class OpportunityAnalysisRequest(StrictModel):
    posting_id: str
    title: str
    description: str
    supported_role_families: list[RoleFamily]
    evidence_coverage: list[EvidenceCoverageSummary] = Field(default_factory=list)
    correction_notes: list[str] = Field(default_factory=list)


class RoleClassificationRequest(StrictModel):
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)


class RoleEvidenceQuote(StrictModel):
    quote: str = Field(min_length=1, max_length=500)
    category: Literal[
        "responsibility",
        "contextual_mention",
        "managed_subject",
        "tool_or_skill",
    ]


class RoleClassificationOutput(StrictModel):
    is_engineering_role: bool
    primary_family: RoleFamily | None = None
    secondary_families: list[RoleFamily] = Field(default_factory=list)
    owned_responsibilities: list[str] = Field(default_factory=list)
    contextual_mentions: list[str] = Field(default_factory=list)
    managed_subjects: list[str] = Field(default_factory=list)
    tools_and_skills: list[str] = Field(default_factory=list)
    evidence_quotes: list[RoleEvidenceQuote] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class RoleClassificationResult(ModelResult):
    output: RoleClassificationOutput


class ProfileExtractionRequest(StrictModel):
    profile_id: str = Field(min_length=1)
    source_format: str
    extracted_text: str = Field(min_length=1, max_length=100_000)
    correction_notes: list[str] = Field(default_factory=list)


class ProfileExtractionOutput(StrictModel):
    profile: MasterProfile
    missing_fields: list[str] = Field(default_factory=list)
    uncertain_fields: list[str] = Field(default_factory=list)
    extraction_notes: list[str] = Field(default_factory=list)
    fidelity_flags: list[str] = Field(default_factory=list)


class ProfileExtractionResult(ModelResult):
    output: ProfileExtractionOutput


class OpportunityRequirement(StrictModel):
    label: str
    priority: str
    supporting_terms: list[str] = Field(default_factory=list)


class OpportunityAnalysisOutput(StrictModel):
    role_families: list[RoleFamily] = Field(min_length=1)
    primary_focus: str
    responsibilities: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    domain_signals: list[str] = Field(default_factory=list)
    evidence_requirements: list[OpportunityRequirement] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    reasoning: str = Field(max_length=600)


class OpportunityAnalysisResult(ModelResult):
    output: OpportunityAnalysisOutput


class EligibleEvidence(StrictModel):
    evidence_id: str
    entity_id: str
    source_text: str
    technologies: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    outcomes: list[str] = Field(default_factory=list)
    estimated_lines: int = Field(gt=0)


class EligibleEntry(StrictModel):
    entry_id: str
    title: str
    entry_cost_lines: int = Field(ge=0)
    evidence: list[EligibleEvidence] = Field(default_factory=list)


class StrategyRequirementInput(StrictModel):
    requirement_id: str
    text: str
    authority: str
    importance: float = Field(ge=0)


class StrategyEvidenceInput(StrictModel):
    evidence_id: str
    source_text: str
    technologies: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    outcomes: list[str] = Field(default_factory=list)
    estimated_lines: int = Field(gt=0)
    deterministic_relationship: str
    supported_requirement_ids: list[str] = Field(default_factory=list)


class StrategyEntryInput(StrictModel):
    entry_id: str
    entry_kind: str
    authoritative_title: str
    organization: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    entry_cost_lines: int = Field(ge=0)
    evidence: list[StrategyEvidenceInput] = Field(default_factory=list)


class StrategySkillInput(StrictModel):
    category: str
    values: list[str] = Field(default_factory=list)


class ApplicationStrategyConstraintsInput(StrictModel):
    maximum_selected_entries: int = Field(gt=0)
    maximum_selected_evidence: int = Field(gt=0)
    minimum_expansion_reserve_actions: int = Field(default=0, ge=0)
    target_expansion_reserve_actions: int = Field(
        default=APPLICATION_STRATEGY_RESERVE_TARGET_ACTIONS,
        gt=0,
    )
    maximum_expansion_reserve_actions: int = Field(
        default=APPLICATION_STRATEGY_RESERVE_MAXIMUM_ACTIONS,
        gt=0,
    )
    maximum_total_lines: int = Field(gt=0)
    maximum_experience_lines: int = Field(gt=0)
    maximum_project_lines: int = Field(gt=0)
    maximum_skill_lines: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_expansion_reserve_bounds(self) -> ApplicationStrategyConstraintsInput:
        if not (
            self.minimum_expansion_reserve_actions
            <= self.target_expansion_reserve_actions
            <= self.maximum_expansion_reserve_actions
        ):
            raise ValueError("Expansion reserve bounds must satisfy minimum <= target <= maximum")
        if (
            self.minimum_expansion_reserve_actions
            > APPLICATION_STRATEGY_RESERVE_MINIMUM_ACTIONS
        ):
            raise ValueError("Expansion reserve minimum exceeds the supported deep-bank floor")
        return self


class ApplicationStrategyRequest(StrictModel):
    posting_id: str
    title: str
    normalized_full_posting: str
    requirements: list[StrategyRequirementInput] = Field(default_factory=list)
    entries: list[StrategyEntryInput] = Field(min_length=1)
    reviewed_skills: list[StrategySkillInput] = Field(default_factory=list)
    constraints: ApplicationStrategyConstraintsInput
    correction_notes: list[str] = Field(default_factory=list)


class ProposedStrategyRolePriority(StrictModel):
    theme: str = Field(min_length=1, max_length=180)
    requirement_ids: list[str] = Field(default_factory=list)


class ProposedStrategyEvidence(StrictModel):
    evidence_id: str
    priority: EvidencePriorityTier
    requirement_ids: list[str] = Field(default_factory=list)
    source_wording: SourceWordingAssessment = SourceWordingAssessment.STRONG


class ProposedStrategyEntry(StrictModel):
    entry_id: str
    reason: str = Field(min_length=1, max_length=400)
    desired_depth: int = Field(ge=1, le=8)
    selected_evidence: list[ProposedStrategyEvidence] = Field(min_length=1, max_length=8)
    alternative_evidence: list[ProposedStrategyEvidence] = Field(
        default_factory=list,
        max_length=8,
    )


class ProposedLowPriorityEntry(StrictModel):
    entry_id: str
    reason: str = Field(min_length=1, max_length=300)


class ProposedStrategyExpansionAction(StrictModel):
    entry_id: str
    evidence_ids: list[str] = Field(min_length=1, max_length=4)
    priority: EvidencePriorityTier
    marginal_value_reason: str = Field(min_length=1, max_length=300)
    minimum_coherent_depth: int = Field(default=1, ge=1, le=4)


class ApplicationStrategyOutput(StrictModel):
    application_thesis: str = Field(min_length=1, max_length=500)
    role_priorities: list[ProposedStrategyRolePriority] = Field(default_factory=list)
    selected_entries: list[ProposedStrategyEntry] = Field(min_length=1)
    expansion_reserve: list[ProposedStrategyExpansionAction] = Field(
        default_factory=list,
        max_length=APPLICATION_STRATEGY_RESERVE_MAXIMUM_ACTIONS,
        description=(
            "A deep ranked bench, broader than the selective core and not automatically rendered. "
            "Rank independent actions by marginal value to the current core. When the evidence "
            "bank contains enough materially useful unused choices, aim for the supplied target "
            "and keep returning actions up to the supplied maximum so page fitting can try deeper "
            "same-entry evidence and complementary entries after earlier actions are redundant or "
            "overflow. Return fewer only when fewer choices add real application value."
        ),
    )
    low_priority_entries: list[ProposedLowPriorityEntry] = Field(default_factory=list)
    global_evidence_priority: list[str] = Field(min_length=1)


class ApplicationStrategyResult(ModelResult):
    output: ApplicationStrategyOutput


class CompositionRecommendationRequest(StrictModel):
    posting_id: str
    primary_focus: str
    entries: list[EligibleEntry]
    max_total_lines: int = Field(gt=0)
    correction_notes: list[str] = Field(default_factory=list)


class EvidenceGrouping(StrictModel):
    entry_id: str
    evidence_ids: list[str] = Field(min_length=1, max_length=4)


class CompositionRecommendationOutput(StrictModel):
    selected_entry_ids: list[str] = Field(default_factory=list)
    excluded_entry_ids: list[str] = Field(default_factory=list)
    selected_evidence_ids: list[str] = Field(default_factory=list)
    proposed_evidence_groupings: list[EvidenceGrouping] = Field(default_factory=list)
    rationale: str = Field(max_length=800)
    unsupported_requirements: list[str] = Field(default_factory=list)


class CompositionRecommendationResult(ModelResult):
    output: CompositionRecommendationOutput


class EligibleSkill(StrictModel):
    skill_id: str
    value: str
    relevance_score: float = Field(ge=0)
    supporting_job_signals: list[str] = Field(default_factory=list)


class EligibleSkillCategory(StrictModel):
    category_id: str
    label: str
    relevance_score: float = Field(ge=0)
    skills: list[EligibleSkill] = Field(min_length=1)


class SkillCompositionRequest(StrictModel):
    posting_id: str
    job_signals: list[str] = Field(default_factory=list)
    categories: list[EligibleSkillCategory] = Field(min_length=1)
    evidence: list[EligibleEvidence] = Field(default_factory=list)
    correction_notes: list[str] = Field(default_factory=list)


class ProposedSkill(StrictModel):
    skill_id: str
    value: str


class ProposedDemonstratedSkill(StrictModel):
    category_id: str
    value: str = Field(min_length=1, max_length=120)
    source_evidence_ids: list[str] = Field(min_length=1, max_length=4)
    confidence: ClaimConfidence
    rationale: str = Field(min_length=1, max_length=400)


class ProposedSkillCategory(StrictModel):
    category_id: str
    label: str
    skills: list[ProposedSkill] = Field(min_length=1)


class SkillCompositionOutput(StrictModel):
    categories: list[ProposedSkillCategory] = Field(min_length=1)
    demonstrated_skills: list[ProposedDemonstratedSkill] = Field(default_factory=list)
    rationale: str = Field(max_length=800)


class SkillCompositionResult(ModelResult):
    output: SkillCompositionOutput


class ApprovedEvidenceGroup(StrictModel):
    entry_id: str
    authoritative_entry_title: str = ""
    evidence_ids: list[str] = Field(min_length=1, max_length=4)
    source_texts: list[str] = Field(min_length=1, max_length=4)
    technologies: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    relationship_tier: EvidenceRelationship = EvidenceRelationship.REJECTED
    posting_requirement_ids: list[str] = Field(default_factory=list)
    posting_requirements: list[str] = Field(default_factory=list)
    intrinsic_evidence_strength: float = Field(default=0, ge=0)
    shortlist_reason: str = ""
    max_rendered_lines: int = Field(gt=0)


class BulletRewriteRequest(StrictModel):
    profile_fingerprint: str = ""
    posting_fingerprint: str = ""
    primary_focus: str
    target_terms: list[str] = Field(default_factory=list)
    target_requirements: list[str] = Field(default_factory=list)
    groups: list[ApprovedEvidenceGroup] = Field(min_length=1)
    max_bullets_per_entry: int = Field(gt=0)
    max_total_lines: int = Field(gt=0)
    writing_policy_version: str = RESUME_WRITING_POLICY_VERSION
    contract_version: str = RESUME_WRITING_CONTRACT_VERSION
    prompt_version: str = RESUME_WRITING_PROMPT_VERSION
    relevant_feature_flags: dict[str, bool] = Field(
        default_factory=lambda: {"bullet_rewrite": True}
    )
    writing_instructions: list[str] = Field(default_factory=list)
    prohibited_phrases: list[str] = Field(default_factory=list)
    discouraged_phrases: list[str] = Field(default_factory=list)
    correction_notes: list[str] = Field(default_factory=list)


class BulletRewriteClaim(StrictModel):
    text: str = Field(min_length=1, max_length=500)
    supporting_evidence_ids: list[str] = Field(min_length=1, max_length=4)


class BulletRewrite(StrictModel):
    entry_id: str
    final_bullet_text: str = Field(min_length=1, max_length=500)
    source_evidence_ids: list[str] = Field(min_length=1, max_length=4)
    preserved_technologies: list[str] = Field(default_factory=list)
    preserved_metrics: list[str] = Field(default_factory=list)
    emphasized_terms: list[str] = Field(default_factory=list)
    evidence_combined: bool
    concise_alternative: str | None = Field(default=None, min_length=1, max_length=500)
    confidence: float = Field(ge=0, le=1)
    support: ClaimConfidence = ClaimConfidence.EXPLICITLY_SUPPORTED
    support_rationale: str = Field(default="", max_length=400)
    claims: list[BulletRewriteClaim] = Field(default_factory=list)
    target_requirements_addressed: list[str] = Field(default_factory=list)
    intended_length_class: BulletLengthClass = BulletLengthClass.STANDARD_ONE_TO_TWO_LINES


class BulletRewriteOutput(StrictModel):
    bullets: list[BulletRewrite] = Field(default_factory=list, max_length=48)


class BulletRewriteResult(ModelResult):
    output: BulletRewriteOutput
    mapping_outcomes: list[ProviderRewriteMappingOutcome] = Field(default_factory=list)


class BulletShorteningRequest(StrictModel):
    bullet_id: str
    entry_id: str
    original_text: str
    source_evidence_ids: list[str] = Field(min_length=1, max_length=2)
    source_texts: list[str] = Field(min_length=1, max_length=2)
    protected_facts: list[str] = Field(default_factory=list)
    max_rendered_lines: int = Field(gt=0)
    correction_notes: list[str] = Field(default_factory=list)


class BulletShorteningOutput(StrictModel):
    original_bullet_id: str
    shortened_text: str = Field(min_length=1, max_length=500)
    source_evidence_ids: list[str] = Field(min_length=1, max_length=2)
    preserved_facts: list[str] = Field(default_factory=list)
    removed_wording: list[str] = Field(default_factory=list)
    no_new_claim_introduced: bool


class BulletShorteningResult(ModelResult):
    output: BulletShorteningOutput


class CoverLetterEvidence(StrictModel):
    evidence_id: str
    evidence_kind: str
    source_text: str
    entity_id: str | None = None
    entry_title: str | None = None
    technologies: list[str] = Field(default_factory=list)
    outcomes: list[str] = Field(default_factory=list)
    matched_requirements: list[str] = Field(default_factory=list)
    selected_in_final_resume: bool = False


class CoverLetterCompanyFact(StrictModel):
    research_id: str
    fact: str
    supported_claim: str
    source_title: str
    source_type: str


class CoverLetterDraftRequest(StrictModel):
    job_title: str
    company_name: str | None = None
    job_description: str
    strategy: str
    narrative_plan: CoverLetterNarrativePlan
    selected_entry_ids: list[str] = Field(default_factory=list)
    selected_evidence: list[CoverLetterEvidence] = Field(min_length=1)
    company_research: list[CoverLetterCompanyFact] = Field(default_factory=list)
    final_resume_evidence_ids: list[str] = Field(default_factory=list)
    approximate_body_lines: int = Field(gt=0)
    writing_constraints: list[str] = Field(default_factory=list)
    repair_instruction: str | None = None


class CoverLetterDraftParagraph(StrictModel):
    purpose: CoverLetterParagraphPurpose
    text: str = Field(min_length=1, max_length=2400)
    candidate_evidence_ids: list[str] = Field(default_factory=list, max_length=3)
    company_research_ids: list[str] = Field(default_factory=list, max_length=3)
    narrative_thread_id: str | None = None
    length_class: CoverLetterLengthClass = CoverLetterLengthClass.STANDARD
    source_bound_sentences: list[CoverLetterSentenceAuthority] = Field(default_factory=list)

    @field_validator("purpose", mode="before")
    @classmethod
    def normalize_legacy_purpose(cls, value: object) -> CoverLetterParagraphPurpose:
        return normalize_paragraph_purpose(value)

    @model_validator(mode="after")
    def validate_source_bound_text(self) -> CoverLetterDraftParagraph:
        if not self.source_bound_sentences:
            return self
        assembled = " ".join(
            " ".join(sentence.text.split()) for sentence in self.source_bound_sentences
        )
        if assembled != " ".join(self.text.split()):
            raise ValueError(
                "Source-bound paragraph text must be assembled from its sentence objects"
            )
        return self


class CoverLetterDraftOutput(StrictModel):
    paragraphs: list[CoverLetterDraftParagraph] = Field(min_length=3, max_length=5)


class CoverLetterDraftResult(ModelResult):
    output: CoverLetterDraftOutput
