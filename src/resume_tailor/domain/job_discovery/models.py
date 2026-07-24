from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator, model_validator

from resume_tailor.domain.models import RoleFamily


class WorkArrangement(StrEnum):
    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"
    UNKNOWN = "unknown"


class ConnectorType(StrEnum):
    GREENHOUSE = "greenhouse"
    LEVER = "lever"


class LeverApiRegion(StrEnum):
    GLOBAL = "global"
    EU = "eu"


class VerificationStatus(StrEnum):
    VERIFIED_ACTIVE = "verified_active"
    VERIFIED_STATUS_UNKNOWN = "verified_status_unknown"
    UNVERIFIED = "unverified"
    UNAVAILABLE = "unavailable"
    EXPIRED = "expired"


class VerificationConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class MatchLabel(StrEnum):
    STRONG = "strong"
    GOOD = "good"
    STRETCH = "stretch"
    PROVISIONAL = "provisional"
    DONT_MATCH = "dont_match"


class FitGrade(StrEnum):
    EXCELLENT = "excellent"
    GOOD = "good"
    WEAK = "weak"
    DONT_MATCH = "dont_match"


class RequirementCriticality(StrEnum):
    CRITICAL = "critical"
    IMPORTANT = "important"
    SUPPORTING = "supporting"


class EvidenceQuality(StrEnum):
    DEMONSTRATED = "demonstrated"
    TRANSFERABLE = "transferable"
    REVIEWED_SKILL = "reviewed_skill"
    COURSEWORK_CONTEXT = "coursework_context"
    ABSENT = "absent"


class RequirementMatchStatus(StrEnum):
    MATCHED = "matched"
    INSUFFICIENT = "insufficient"
    UNRESOLVED = "unresolved"
    ABSENT = "absent"


class EligibilityStatus(StrEnum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    UNKNOWN = "unknown"


class EligibilityReasonCode(StrEnum):
    ROLE_FAMILY_MISMATCH = "role_family_mismatch"
    LOCATION_MISMATCH = "location_mismatch"
    WORK_ARRANGEMENT_CONFLICT = "work_arrangement_conflict"
    AUTHORIZATION_CONFLICT = "authorization_conflict"
    POSTING_TOO_OLD = "posting_too_old"
    VERIFICATION_UNAVAILABLE = "verification_unavailable"
    MISSING_REQUIRED_DATA = "missing_required_data"
    COMPANY_EXCLUDED = "company_excluded"
    JOB_LEVEL_MISMATCH = "job_level_mismatch"
    DEGREE_CONFLICT = "degree_conflict"
    GRADUATION_CONFLICT = "graduation_conflict"
    EXPERIENCE_REQUIREMENT_TOO_HIGH = "experience_requirement_too_high"


class RecommendationGroup(StrEnum):
    PRIMARY = "primary"
    FALLBACK = "fallback"


class DiscoveryRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED_ALL_SOURCES = "failed_all_sources"
    NO_SOURCES_CONFIGURED = "no_sources_configured"


class SavedJobAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class JobLevel(StrEnum):
    INTERN = "intern"
    ENTRY = "entry"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    STAFF = "staff"
    PRINCIPAL = "principal"
    DIRECTOR = "director"
    UNKNOWN = "unknown"


class WorkArrangementPreferenceMode(StrEnum):
    REQUIRED = "required"
    PREFERRED = "preferred"
    ACCEPTABLE = "acceptable"
    EXCLUDED = "excluded"


class NormalizedLocation(BaseModel):
    city: str | None = None
    region: str | None = None
    country_code: str | None = None
    country_name: str | None = None
    raw: str = ""
    parseable: bool = False


class WorkArrangementPreference(BaseModel):
    arrangement: WorkArrangement
    mode: WorkArrangementPreferenceMode


class JobDiscoverySettings(BaseModel):
    enabled: bool = True
    source_registry_path: str
    greenhouse_api_base_url: AnyHttpUrl
    lever_global_api_base_url: AnyHttpUrl
    lever_eu_api_base_url: AnyHttpUrl
    source_timeout_seconds: float = 15.0
    source_page_size: int = 100
    source_max_pages: int = 20


class JobSearchPreferences(BaseModel):
    user_id: str
    profile_id: str
    version: int
    role_family_priority: list[RoleFamily]
    target_titles: list[str]
    related_title_variants: list[str]
    technical_themes: list[str]
    career_interests: list[str]
    job_levels: list[JobLevel]
    locations: list[NormalizedLocation]
    work_arrangement: WorkArrangement
    work_arrangement_mode: WorkArrangementPreferenceMode = WorkArrangementPreferenceMode.PREFERRED
    preferred_companies: list[str]
    excluded_companies: list[str] = Field(default_factory=list)
    work_authorization_constraints: list[str] = Field(default_factory=list)
    max_posting_age_days: int | None = 30
    created_at: datetime
    confirmed_at: datetime | None = None


class JobSearchPreferenceSuggestion(BaseModel):
    profile_id: str
    generated_at: datetime
    role_family_priority: list[RoleFamily]
    target_titles: list[str]
    related_title_variants: list[str]
    technical_themes: list[str]
    career_interests: list[str]
    job_levels: list[JobLevel]
    locations: list[NormalizedLocation]
    work_arrangement: WorkArrangement
    work_arrangement_mode: WorkArrangementPreferenceMode = WorkArrangementPreferenceMode.PREFERRED
    preferred_companies: list[str]
    rationale: list[str]


class ProfileCapabilityEvidence(BaseModel):
    source_type: Literal[
        "confirmed_evidence",
        "resume_item",
        "reviewed_skill",
        "coursework",
        "education",
        "title",
    ]
    source_id: str
    source_text: str
    demonstrated: bool
    evidence_quality: EvidenceQuality | None = None


class ProfileCapabilityIndex(BaseModel):
    terms: dict[str, list[ProfileCapabilityEvidence]]


class RequirementCategory(StrEnum):
    TECHNOLOGY = "technology"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    CERTIFICATION = "certification"
    AUTHORIZATION = "authorization"
    LOCATION = "location"
    WORK_ARRANGEMENT = "work_arrangement"
    RESPONSIBILITY = "responsibility"
    ROLE = "role"


class RequirementImportance(StrEnum):
    REQUIRED = "required"
    PREFERRED = "preferred"
    UNKNOWN = "unknown"


class JobRequirement(BaseModel):
    term: str
    category: RequirementCategory
    importance: RequirementImportance
    source_text: str
    source_start: int
    source_end: int
    requirement_id: str | None = None
    criticality: RequirementCriticality | None = None
    aliases: list[str] = Field(default_factory=list)
    evidence_references: list[str] = Field(default_factory=list)


class JobRequirementSignals(BaseModel):
    required_terms: list[str] = Field(default_factory=list)
    preferred_terms: list[str] = Field(default_factory=list)
    unknown_terms: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    experience_years: int | None = None
    degree_requirements: list[str] = Field(default_factory=list)
    degree_equivalent_experience: bool = False
    graduation_requirements: list[str] = Field(default_factory=list)
    certification_requirements: list[str] = Field(default_factory=list)
    work_arrangement: WorkArrangement = WorkArrangement.UNKNOWN
    authorization_language: list[str] = Field(default_factory=list)
    role_signals: list[str] = Field(default_factory=list)
    job_level: JobLevel = JobLevel.UNKNOWN
    location: NormalizedLocation | None = None
    requirements: list[JobRequirement] = Field(default_factory=list)
    material_gaps: list[str] = Field(default_factory=list)


class SupportedJobSource(BaseModel):
    source_id: str
    connector_type: ConnectorType
    company_name: str
    board_token: str
    enabled: bool
    official_base_url: AnyHttpUrl
    lever_api_region: LeverApiRegion | None = None


class SourceJobRecord(BaseModel):
    external_job_id: str
    title: str
    company_name: str
    description: str
    official_url: AnyHttpUrl
    location_raw: str | None = None
    work_arrangement: WorkArrangement = WorkArrangement.UNKNOWN
    posted_at: datetime | None = None
    source_updated_at: datetime | None = None
    application_deadline: datetime | None = None
    source_payload: dict[str, Any] = Field(default_factory=dict)


class SourceRecordWarningCode(StrEnum):
    MISSING_EXTERNAL_JOB_ID = "missing_external_job_id"
    MISSING_TITLE = "missing_title"
    INVALID_OFFICIAL_URL = "invalid_official_url"
    INVALID_LOCATION = "invalid_location"
    INVALID_TIMESTAMP = "invalid_timestamp"
    INVALID_RECORD_SHAPE = "invalid_record_shape"
    DUPLICATE_RECORD = "duplicate_record"


class SourceRecordWarning(BaseModel):
    external_job_id: str | None
    code: SourceRecordWarningCode
    message: str


class JobSourceFetchResult(BaseModel):
    records: list[SourceJobRecord]
    warnings: list[SourceRecordWarning]


class VerificationResult(BaseModel):
    status: VerificationStatus
    confidence: VerificationConfidence
    checked_at: datetime
    message: str


class DiscoveredJob(BaseModel):
    id: str
    source: SupportedJobSource
    external_job_id: str
    title: str
    company_name: str
    description: str
    official_url: str
    location: NormalizedLocation
    work_arrangement: WorkArrangement
    role_family: RoleFamily | None = None
    role_family_scores: dict[RoleFamily, float] = Field(default_factory=dict)
    requirements: JobRequirementSignals = Field(default_factory=JobRequirementSignals)
    posted_at: datetime | None = None
    source_updated_at: datetime | None = None
    application_deadline: datetime | None = None
    verification_status: VerificationStatus = VerificationStatus.VERIFIED_STATUS_UNKNOWN
    verification_confidence: VerificationConfidence = VerificationConfidence.MEDIUM
    completeness: list[str] = Field(default_factory=list)
    fetched_at: datetime
    requisition_id: str | None = None
    normalized_title: str = ""
    normalized_company_name: str = ""
    canonical_description_hash: str = ""
    source_alias_ids: list[str] = Field(default_factory=list)


class EligibilityAssessment(BaseModel):
    status: EligibilityStatus
    reasons: list[EligibilityReasonCode] = Field(default_factory=list)
    explanations: list[str] = Field(default_factory=list)
    location_match: bool | None = None
    verification_confidence: VerificationConfidence
    posting_age_days: int | None = None
    posting_references: list[str] = Field(default_factory=list)
    profile_references: list[str] = Field(default_factory=list)
    conflict_references: list[str] = Field(default_factory=list)
    unresolved_facts: list[str] = Field(default_factory=list)


class JobScoreBreakdown(BaseModel):
    demonstrated_technical_evidence: float
    required_coverage: float
    role_alignment: float
    level_alignment: float
    education_coursework: float
    preferred_skill_alignment: float
    recency_completeness: float
    total: float
    label: MatchLabel
    provisional: bool
    fit_grade: FitGrade | None = None
    evaluation_policy_version: str | None = None
    historical_label: MatchLabel | None = None
    historical_policy: bool = False

    @model_validator(mode="after")
    def mark_legacy_records(self) -> JobScoreBreakdown:
        if self.evaluation_policy_version is None:
            self.evaluation_policy_version = "jobs-score-legacy-v1"
            self.historical_label = self.label
            self.historical_policy = True
            if self.label is MatchLabel.PROVISIONAL:
                self.fit_grade = None
        return self


class DuplicateGroup(BaseModel):
    canonical: DiscoveredJob
    aliases: list[DiscoveredJob] = Field(default_factory=list)


class DeduplicationResult(BaseModel):
    jobs: list[DiscoveredJob]
    groups: list[DuplicateGroup] = Field(default_factory=list)
    duplicate_count: int = 0


class JobRecommendation(BaseModel):
    id: str
    run_id: str
    user_id: str
    profile_id: str
    profile_version: int | None
    preference_version: int
    job_id: str
    group: RecommendationGroup
    primary_role_family: RoleFamily | None
    eligibility: EligibilityAssessment
    score: JobScoreBreakdown
    reasons: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    rank: int
    created_at: datetime
    evaluation_policy_version: str | None = None

    @field_validator("created_at")
    @classmethod
    def _created_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        _require_timezone_aware(value, "created_at")
        return value


class SavedJob(BaseModel):
    id: str
    user_id: str
    job_id: str
    availability: SavedJobAvailability
    saved_at: datetime
    checked_at: datetime | None = None
    snapshot_schema_version: int = 1
    posting_snapshot: DiscoveredJob

    @field_validator("saved_at", "checked_at")
    @classmethod
    def _saved_timestamps_must_be_timezone_aware(
        cls, value: datetime | None
    ) -> datetime | None:
        if value is not None:
            _require_timezone_aware(value, "saved job timestamp")
        return value


class DiscoveryRun(BaseModel):
    id: str
    user_id: str
    profile_id: str
    profile_version: int | None = None
    preference_version: int
    status: DiscoveryRunStatus
    started_at: datetime
    completed_at: datetime | None = None
    sources_attempted: list[str] = Field(default_factory=list)
    source_warnings: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    failed_sources: list[str] = Field(default_factory=list)
    source_count: int = 0
    retrieved_count: int = 0
    normalized_count: int = 0
    duplicate_count: int = 0
    eligibility_filtered_count: int = 0
    scored_count: int = 0
    returned_count: int = 0
    record_count: int = 0
    warning_count: int = 0
    model_assisted: bool = False
    model_call_count: int = 0
    error_messages: list[str] = Field(default_factory=list)

    @field_validator("started_at", "completed_at")
    @classmethod
    def _run_timestamps_must_be_timezone_aware(
        cls, value: datetime | None
    ) -> datetime | None:
        if value is not None:
            _require_timezone_aware(value, "discovery run timestamp")
        return value


def _require_timezone_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
