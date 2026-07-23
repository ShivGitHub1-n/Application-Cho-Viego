from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FitGrade = Literal["excellent", "good", "weak", "dont_match"]
EligibilityStatus = Literal["eligible", "unknown", "ineligible"]
EvidenceQuality = Literal["verified", "self_reported", "incomplete", "stale", "absent"]
PostingFactKind = Literal[
    "responsibility",
    "critical_requirement",
    "required_qualification",
    "preferred_qualification",
    "location",
    "authorization",
    "level",
    "posting_date",
    "employment_type",
]


class StrictBenchmarkModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReviewedProfile(StrictBenchmarkModel):
    profile_ref: str
    synthetic_or_deidentified: bool
    reviewed: bool
    summary: str
    skills: list[str]
    evidence_items: list[ProfileEvidence]
    experience_years: float
    education_summary: str
    date_evidence_status: Literal["current", "incomplete", "stale", "unknown"]
    current_location: str = ""
    authorized_work_locations: list[str] = Field(default_factory=list)
    requires_sponsorship: bool = False
    professional_license_status: Literal[
        "active", "confirmed_none", "none_recorded", "unknown"
    ] = "unknown"
    clearance_status: Literal["active", "confirmed_none", "none_recorded", "unknown"] = "unknown"


class ProfileEvidence(StrictBenchmarkModel):
    evidence_id: str
    statement: str
    evidence_kind: Literal[
        "demonstrated",
        "transferable_demonstrated",
        "reviewed_skill",
        "coursework",
    ]
    evidence_quality: EvidenceQuality
    provenance: str
    demonstrated: bool
    capabilities: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)


class ConfirmedPreferences(StrictBenchmarkModel):
    confirmed: bool
    role_families: list[str]
    target_titles: list[str]
    target_levels: list[str]
    locations: list[str]
    work_arrangements: list[str]
    work_authorization_status: Literal["confirmed", "unknown", "conflict"]
    selected_exploration_sectors: list[str]
    preferred_companies: list[str]
    candidate_current_location: str = ""
    authorized_work_locations: list[str] = Field(default_factory=list)
    requires_sponsorship: bool = False


class NormalizedPosting(StrictBenchmarkModel):
    normalized_id: str
    title: str
    company: str
    description: str
    location: str
    work_arrangement: str
    employment_type: str
    posted_date: str | None
    responsibilities: list[str]
    requirements_text: list[str]
    posting_sponsorship_available: bool | None = None
    enrollment_requirement: str | None = None
    graduation_window: str | None = None
    posting_level: str = "unknown"
    posting_facts: list[PostingFact] = Field(default_factory=list)


class SourceProviderFacts(StrictBenchmarkModel):
    provider: str
    source_id: str
    external_job_id: str
    source_url: str
    retrieved_at: str
    provider_position: int
    verification_status: Literal["verified_active", "status_unknown", "unverified"]


class EvidenceReference(StrictBenchmarkModel):
    reference: str
    provenance: str
    statement: str
    evidence_quality: EvidenceQuality | None = None


class PostingFact(StrictBenchmarkModel):
    fact_id: str
    kind: PostingFactKind
    statement: str


class EligibilityReason(StrictBenchmarkModel):
    code: str
    statement: str
    evidence_references: list[str]
    posting_fact: str = ""
    profile_fact: str = ""


class Requirement(StrictBenchmarkModel):
    requirement_id: str
    text: str
    importance: Literal["critical", "required", "preferred"]
    evidence_references: list[str]
    fact_id: str | None = None


class Qualification(StrictBenchmarkModel):
    qualification_id: str
    text: str
    evidence_references: list[str]
    fact_id: str | None = None


class ProposedReason(StrictBenchmarkModel):
    code: str
    statement: str
    evidence_references: list[str]


class ComparablePair(StrictBenchmarkModel):
    other_case_id: str
    relationship: Literal["preferred_to_other", "less_preferred_than_other"]
    rationale: str


class EvidenceAssessment(StrictBenchmarkModel):
    quality: EvidenceQuality
    provenance: list[EvidenceReference]


class BenchmarkCase(StrictBenchmarkModel):
    case_id: str
    scenario_id: str
    split: Literal["calibration", "validation", "locked"]
    scenario_category: str
    ranking_group: str | None = None
    stage: Literal["A", "B"]
    proposal_status: Literal["proposed"]
    profile: ReviewedProfile
    preferences: ConfirmedPreferences
    posting: NormalizedPosting
    source: SourceProviderFacts
    expected_eligibility: EligibilityStatus
    proposed_eligibility_reasons: list[EligibilityReason]
    proposed_grade: FitGrade
    proposed_provisional: bool
    provisional_reason_codes: list[str]
    critical_requirements: list[Requirement]
    required_qualifications: list[Qualification]
    preferred_qualifications: list[Qualification]
    important_evidence: list[EvidenceReference]
    evidence_assessment: EvidenceAssessment
    important_gaps: list[ProposedReason]
    proposed_positive_reasons: list[ProposedReason]
    proposed_material_gap_reasons: list[ProposedReason]
    proposed_reasons: list[ProposedReason]
    rationale: str
    proposal_confidence: Literal["high", "medium", "low"]
    review_tags: list[str]
    review_required: bool
    apply_worthy: bool
    normal_feed_visible: bool = True
    human_ranking_tier: Literal["tier_1", "tier_2", "tier_3", "not_ranked"]
    comparable_pair_annotations: list[ComparablePair]
    reviewer_decision: Literal[""]
    reviewer_notes: Literal[""]
    approval_status: Literal["unapproved", "approved"]


BenchmarkSplitName = Literal["calibration", "validation", "locked"]


class ProposedBenchmarkSplit(StrictBenchmarkModel):
    path: str
    sha256: str | None
    case_count: int
    proposed_case_ids: list[str]


class ProposalIntegrity(StrictBenchmarkModel):
    type: Literal["proposal_only"]
    locked_checksum_scope: Literal["raw locked fixture bytes"]


class BenchmarkManifest(StrictBenchmarkModel):
    version: str
    stage: Literal["A", "B"]
    proposal_status: Literal["proposed", "partially_approved"]
    approval_status: Literal["unapproved", "partially_approved", "approved"]
    approved: bool
    proposal_integrity: ProposalIntegrity
    splits: dict[BenchmarkSplitName, ProposedBenchmarkSplit]
    benchmark_counts: dict[str, int] = Field(default_factory=dict)
    approval_record: str | None = None
    approval: dict[str, object] = Field(default_factory=dict)
