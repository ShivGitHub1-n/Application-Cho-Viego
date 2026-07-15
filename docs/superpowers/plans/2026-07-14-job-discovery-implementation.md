# Job-discovery implementation plan

## Goal

Deliver the deterministic ATS-first job-discovery and recommendation MVP on feature/job-discovery after a reproducible clean baseline. This plan is standalone: every new contract, field, status, marker, table, and test path is defined here or points to an exact existing import.

## Architecture summary

The domain owns immutable job, preference, capability, requirement, eligibility, normalization, deduplication, role-family, and scoring policy. Application services load repositories and orchestrate suggestion, refresh, saving, and availability checks. Ports expose repositories and ATS connectors. Infrastructure contains SQLite adapters, the curated source registry, Greenhouse/Lever adapters, and the shared deterministic role-signal refactor from infrastructure/optimization.py. FastAPI and Streamlit are delivery layers only. Services receive generated_at or started_at explicitly and use the hash functions below.

## Technology stack

Python 3.11, Pydantic v2, FastAPI, Streamlit, SQLite, httpx, pytest, existing Ruff and strict mypy settings in pyproject.toml. No dependency additions.

## Global constraints and non-goals

- Work only after Gate 0 succeeds. Never skip, xfail, delete, or weaken unrelated tests.
- Offline fixtures are default; live ATS tests are opt-in.
- Production source registry is empty until approved board configuration is supplied.
- Official URLs may be HTTP or HTTPS; upgrade HTTP only for explicit safe ATS hosts.
- No arbitrary web scraping, LinkedIn, Indeed, paid providers, geocoding, radius calculations, authentication, scheduling, application tracking, resume generation, cover letters, or Gemini job-fit analysis. Existing Gemini behavior elsewhere remains unchanged.
- Keep modules small; do not put this feature in domain/models.py, api/main.py, frontend/app.py, or one service file.
- Every implementation task has failing test, failing command, minimal implementation, passing command, and focused commit.

Existing imports: MasterProfile, EvidenceItem, ResumeItem, EducationRecord, RoleFamily from src/resume_tailor/domain/models.py; MasterProfileRepository and existing repository protocols from src/resume_tailor/ports/interfaces.py; MultiRoleOpportunityAnalyzer and RoleSignal from src/resume_tailor/infrastructure/optimization.py; dependency wiring from src/resume_tailor/infrastructure/dependencies.py; FastAPI entry point src/resume_tailor/api/main.py; Streamlit entry point src/resume_tailor/frontend/app.py.

## Standalone domain contracts

Create focused modules under src/resume_tailor/domain/job_discovery/: models.py, preferences.py, role_signals.py, normalization.py, location.py, requirements.py, capabilities.py, eligibility.py, scoring.py, deduplication.py, ids.py.

~~~python
class ConnectorType(str, Enum):
    GREENHOUSE = "greenhouse"
    LEVER = "lever"

class LeverApiRegion(str, Enum):
    GLOBAL = "global"
    EU = "eu"

class VerificationStatus(str, Enum):
    VERIFIED_ACTIVE = "verified_active"
    VERIFIED_STATUS_UNKNOWN = "verified_status_unknown"
    UNVERIFIED = "unverified"
    UNAVAILABLE = "unavailable"
    EXPIRED = "expired"

class VerificationConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class SourceRecordWarningCode(str, Enum):
    MISSING_EXTERNAL_JOB_ID = "missing_external_job_id"
    MISSING_TITLE = "missing_title"
    INVALID_OFFICIAL_URL = "invalid_official_url"
    INVALID_LOCATION = "invalid_location"
    INVALID_TIMESTAMP = "invalid_timestamp"
    INVALID_RECORD_SHAPE = "invalid_record_shape"
    DUPLICATE_RECORD = "duplicate_record"

class DiscoveryRunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED_ALL_SOURCES = "failed_all_sources"
    NO_SOURCES_CONFIGURED = "no_sources_configured"

class WorkArrangement(str, Enum):
    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"
    UNKNOWN = "unknown"

class JobLevel(str, Enum):
    INTERN = "intern"
    ENTRY = "entry"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    UNKNOWN = "unknown"

class MatchLabel(str, Enum):
    STRONG = "strong"
    GOOD = "good"
    STRETCH = "stretch"
    PROVISIONAL = "provisional"

class EligibilityStatus(str, Enum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    UNKNOWN = "unknown"

class EligibilityReasonCode(str, Enum):
    ROLE_FAMILY_MISMATCH = "role_family_mismatch"
    LOCATION_MISMATCH = "location_mismatch"
    WORK_ARRANGEMENT_CONFLICT = "work_arrangement_conflict"
    AUTHORIZATION_CONFLICT = "authorization_conflict"
    POSTING_TOO_OLD = "posting_too_old"
    VERIFICATION_UNAVAILABLE = "verification_unavailable"
    MISSING_REQUIRED_DATA = "missing_required_data"

class RecommendationGroup(str, Enum):
    PRIMARY = "primary"
    FALLBACK = "fallback"

class SavedJobAvailability(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"
~~~

~~~python
class NormalizedLocation(BaseModel):
    city: str | None
    region: str | None
    country_code: str | None
    country_name: str | None
    raw: str
    parseable: bool

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
    preferred_companies: list[str]
    max_posting_age_days: int | None
    created_at: datetime
    confirmed_at: datetime | None

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
    preferred_companies: list[str]
    rationale: list[str]

class ProfileCapabilityEvidence(BaseModel):
    source_type: Literal["confirmed_evidence", "resume_item", "reviewed_skill", "coursework", "education", "title"]
    source_id: str
    source_text: str
    demonstrated: bool

class ProfileCapabilityIndex(BaseModel):
    terms: dict[str, list[ProfileCapabilityEvidence]]

class JobRequirementSignals(BaseModel):
    required_terms: list[str]
    preferred_terms: list[str]
    responsibilities: list[str]
    experience_years: int | None
    degree_requirements: list[str]
    graduation_requirements: list[str]
    work_arrangement: WorkArrangement
    authorization_language: list[str]
    role_signals: list[str]
    job_level: JobLevel

class EligibilityAssessment(BaseModel):
    status: EligibilityStatus
    reasons: list[EligibilityReasonCode]
    location_match: bool | None
    verification_confidence: VerificationConfidence
    posting_age_days: int | None

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
    role_family: RoleFamily | None
    role_family_scores: dict[RoleFamily, float]
    requirements: JobRequirementSignals
    posted_at: datetime | None
    source_updated_at: datetime | None
    application_deadline: datetime | None
    verification_status: VerificationStatus
    verification_confidence: VerificationConfidence
    completeness: list[str]
    fetched_at: datetime

class JobRecommendation(BaseModel):
    id: str
    run_id: str
    job_id: str
    group: RecommendationGroup
    primary_role_family: RoleFamily | None
    eligibility: EligibilityAssessment
    score: JobScoreBreakdown
    reasons: list[str]
    gaps: list[str]
    rank: int
    created_at: datetime

class SavedJob(BaseModel):
    id: str
    user_id: str
    job_id: str
    availability: SavedJobAvailability
    saved_at: datetime
    snapshot_schema_version: int
    posting_snapshot: DiscoveredJob

class DiscoveryRun(BaseModel):
    id: str
    user_id: str
    profile_id: str
    preference_version: int
    status: DiscoveryRunStatus
    started_at: datetime
    completed_at: datetime | None
    source_count: int
    record_count: int
    warning_count: int
    error_messages: list[str]
~~~

~~~python
class SupportedJobSource(BaseModel):
    source_id: str
    connector_type: ConnectorType
    company_name: str
    board_token: str
    enabled: bool
    official_base_url: AnyHttpUrl
    lever_api_region: LeverApiRegion | None

class SourceJobRecord(BaseModel):
    external_job_id: str
    title: str
    company_name: str
    description: str
    official_url: AnyHttpUrl
    location_raw: str | None
    work_arrangement: WorkArrangement
    posted_at: datetime | None
    source_updated_at: datetime | None
    application_deadline: datetime | None
    source_payload: dict[str, Any]

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
~~~

~~~python
class JobSourceConnector(Protocol):
    def fetch(self, source: SupportedJobSource, *, fetched_at: datetime) -> JobSourceFetchResult: ...

class JobSourceAvailabilityChecker(Protocol):
    def check(self, source: SupportedJobSource, external_job_id: str) -> VerificationResult: ...

class JobSourceEnvelopeError(Exception): ...
class JobSourceTransportError(Exception): ...
class JobSourceRateLimitedError(JobSourceTransportError): ...
class JobSourceAuthenticationError(JobSourceTransportError): ...
class JobSourceNotFoundError(JobSourceTransportError): ...
~~~

## Deterministic role, requirements, location, evidence, and scoring

role_signals.py owns one ROLE_SIGNAL_CATALOG containing the 14 existing signals from infrastructure/optimization.py, with family, canonical term, aliases, title_weight, and content_weight. classify_role_signals casefolds, uses phrase boundaries, weights title 2.0/content 1.0, sorts score descending then RoleFamily.value, and keeps the existing confidence formula. MultiRoleOpportunityAnalyzer becomes an adapter importing this catalogue and classifier; optimizer imports and regression tests are updated. No second role vocabulary.

requirements.py owns JOB_REQUIREMENT_TERM_CATALOG with every shared role term plus: python, java, javascript, typescript, c++, c#, go, rust, sql, postgresql, mysql, git, linux, docker, kubernetes, aws, azure, gcp, tensorflow, pytorch, scikit-learn, opencv, ros, ros2, ci/cd, embedded c, microcontrollers, firmware, apis, distributed systems, data structures, algorithms, testing, and system design. Each catalog entry has canonical, aliases, category, and required/preferred phrase rules. Catalog candidates are always scanned; ProfileCapabilityIndex only expands aliases.

normalization.py uses Unicode NFKC, casefold, punctuation-to-space, whitespace collapse, explicit aliases js/javascript, ts/typescript, cpp/c++, csharp/c#, postgres/postgresql, k8s/kubernetes, ros2/ros 2, ml/machine learning, ai/artificial intelligence, and phrase boundaries. Every match links evidence.

location.py parses conservative comma-delimited city, region, country; region/country; country-only. It supports ISO two-letter CA/US and country names, every Canadian province/territory name and abbreviation, and every US state name and abbreviation. Unparseable strings have parseable=False and no components. Eligibility uses exact city/region/country equality only.

ProfileCapabilityIndexBuilder consumes exactly confirmed EvidenceItem source_text/capabilities/technologies, ResumeItem capabilities/technologies, reviewed technical_skills, coursework, EducationRecord.program, and project/experience titles. Declared_skills are not demonstrated. Confirmed evidence, resume items, and reviewed skills are demonstrated; coursework, education, and titles are contextual. Each term links source_type, source_id, source_text, demonstrated.

RequirementExtractor.extract(title, description, location_raw, work_arrangement) scans the catalog. Required phrases are must, required, minimum, strong proficiency; preferred phrases are preferred, nice to have, bonus. Responsibilities use design, build, develop, implement, maintain, test, analyze, deploy, integrate, research, evaluate. Years use N+ years and minimum N years regexes. Fixed degree, graduation, authorization, arrangement, role-signal, and title/phrase level tables are used. A required term absent from the profile index remains required and is surfaced as a gap.

EligibilityEvaluator.assess applies: excluded arrangement conflicts are ineligible; required arrangement must equal explicit job arrangement; preferred/acceptable arrangements never reject and add no points; exact city/region/country; known posted_at older than max_posting_age_days is ineligible and unknown age is retained; explicit contradictory authorization is ineligible; unavailable/expired verification is ineligible. Unknown data yields UNKNOWN where policy cannot prove eligibility.

ScoringPolicy.score is exactly 100 points: 30 demonstrated technical evidence; 20 required coverage weighted demonstrated=1.0, declared/reviewed skill=0.7, contextual coursework/title=0.4; 15 role/career (8 first family, 6 other family, title overlap up to 4, themes/interests up to 3 capped at 15); 15 level; 10 education/coursework; 5 preferred skill; 5 recency/completeness. Labels are 85+ strong, 70-84.99 good, 55-69.99 stretch, below 55 stretch. Missing description or required fields sets provisional=True and caps total at 54.

Reasons are ordered demonstrated required, demonstrated responsibility, demonstrated preferred, declared required, role, level, education, preferred company. Exact templates: Demonstrated {term} in {entry_title} ({count} confirmed evidence item[s]).; Confirmed experience demonstrates {term} for this role.; Reviewed technical skill matches required {term}.; Selected role family {family_label} matches the posting's primary role family.; Selected job level {level_label} matches the posting.; Reviewed education or coursework matches {term}.; Company is on your preferred-company list. Gaps are ordered by weighted contribution, required before preferred, normalized term, maximum five. Exact gap templates: No reviewed profile evidence or skill was found for required {term}.; Reviewed profile mentions {term}, but no confirmed evidence item demonstrates it.; Preferred {term} is not present in reviewed profile evidence or skills.; Reviewed education or coursework does not show {term}.

Primary role family is highest score. Fallback order is user role_family_priority then autonomous_systems, robotics_mechatronics, computer_vision_perception, ai_ml_multimodal, embedded_firmware, software_data_engineering without duplicates. target_titles and related_title_variants affect title overlap/reasons; technical_themes and career_interests affect theme alignment/reasons; job_levels are a hard filter only when non-empty and otherwise affect level score; preferred_companies affect tie-breaking and exact reason but not points/eligibility; max_posting_age_days filters known dates only. IDs: job sha256(connector_type + NUL + source_id + NUL + external_job_id), first 24 hex prefixed job-; run sha256(user_id + NUL + profile_id + NUL + profile_version + NUL + preference_version + NUL + started_at.isoformat()), first 24 prefixed run-; recommendation sha256(run_id + NUL + job_id + NUL + profile_version + NUL + preference_version), first 24 prefixed rec-; saved sha256(user_id + NUL + job_id), first 24 prefixed saved-.

## Application and port contracts

Create src/resume_tailor/ports/job_discovery.py:

~~~python
class JobSearchPreferencesRepository(Protocol):
    def get_current(self, user_id: str, profile_id: str) -> JobSearchPreferences | None: ...
    def save_confirmed(self, preferences: JobSearchPreferences) -> None: ...

class DiscoveredJobRepository(Protocol):
    def upsert(self, job: DiscoveredJob) -> None: ...
    def get(self, job_id: str) -> DiscoveredJob | None: ...

class JobRecommendationRepository(Protocol):
    def replace_for_run(self, run_id: str, recommendations: list[JobRecommendation]) -> None: ...
    def list_for_run(self, run_id: str) -> list[JobRecommendation]: ...

class SavedJobRepository(Protocol):
    def save(self, saved: SavedJob) -> None: ...
    def get(self, user_id: str, saved_id: str) -> SavedJob | None: ...
    def list(self, user_id: str) -> list[SavedJob]: ...
    def update_availability(self, saved_id: str, availability: SavedJobAvailability, checked_at: datetime) -> None: ...

class DiscoveryRunRepository(Protocol):
    def create(self, run: DiscoveryRun) -> None: ...
    def complete(self, run: DiscoveryRun) -> None: ...
    def get(self, run_id: str) -> DiscoveryRun | None: ...

class SupportedJobSourceRepository(Protocol):
    def list_enabled(self) -> list[SupportedJobSource]: ...

from resume_tailor.ports.interfaces import MasterProfileRepository
~~~

~~~python
class DeterministicJobSearchPreferenceSuggester:
    def suggest(self, profile: MasterProfile, *, generated_at: datetime) -> JobSearchPreferenceSuggestion: ...

class SuggestJobSearchPreferencesService:
    def __init__(self, profiles: MasterProfileRepository, suggester: DeterministicJobSearchPreferenceSuggester): ...
    def suggest(self, user_id: str, profile_id: str, *, generated_at: datetime) -> JobSearchPreferenceSuggestion: ...

class RefreshJobDiscoveryService:
    def refresh(self, user_id: str, profile_id: str, preferences: JobSearchPreferences, *, started_at: datetime) -> DiscoveryRun: ...

class SaveJobService:
    def save(self, user_id: str, job_id: str, *, saved_at: datetime) -> SavedJob: ...

class CheckSavedJobAvailabilityService:
    def check(self, user_id: str, saved_id: str, *, checked_at: datetime) -> SavedJob: ...
~~~

SuggestJobSearchPreferencesService loads MasterProfileRepository.get_by_id, raises ProfileNotFoundError for absent profile or owner mismatch, and calls only the pure suggester. Suggestions are never persisted automatically. Refresh performs fetch, normalize, deduplicate, verify, extract, assess, score, persist, and aggregates warnings by source_id then code then external_job_id/message. Empty registry produces NO_SOURCES_CONFIGURED; envelope errors fail a source; malformed records are skipped with warnings; all-source failure produces FAILED_ALL_SOURCES.

## Connectors and persistence

Greenhouse list updated_at maps only to source_updated_at. No detail request per search result for recency. A configured detail call may supply first_published as posted_at and application_deadline. Unknown dates remain None. Lever list uses skip/limit and never undocumented createdAt. Availability uses GET /v0/postings/{site}/{posting-id} with explicit global or EU region. Valid HTTP/HTTPS URLs pass; only boards.greenhouse.io, job-boards.greenhouse.io, jobs.lever.co, jobs.eu.lever.co are safe upgrades. HTTP status classes map to the exceptions above. SourceRecordWarning codes are exactly those defined; malformed envelopes raise JobSourceEnvelopeError, malformed records are omitted and warnings deterministically aggregated.

Create infrastructure/job_discovery_sqlite.py with schema_version=1:

- job_search_preferences(user_id, profile_id, version, payload_json, schema_version, created_at, confirmed_at, primary key user_id/profile_id/version) plus current index.
- discovered_jobs(job_id primary key, external_job_id, source_id, payload_json, schema_version, fetched_at, unique source_id/external_job_id).
- discovery_runs(run_id primary key, user_id, profile_id, preference_version, status, payload_json, started_at, completed_at, warning_count, error_json).
- job_recommendations(recommendation_id primary key, run_id, job_id, group_name, rank, payload_json, created_at, unique run_id/job_id).
- saved_jobs(saved_id primary key, user_id, job_id, availability, snapshot_json, snapshot_schema_version, saved_at, checked_at).
- supported_job_sources(source_id primary key, connector_type, company_name, board_token, official_base_url, lever_api_region, enabled).

Use model_dump_json, transactions, indexes, and immutable saved snapshots.

## API and delivery contracts

Create src/resume_tailor/api/job_discovery.py and include it from existing src/resume_tailor/api/main.py. Create src/resume_tailor/api/dependencies.py:

~~~python
class SuggestPreferencesRequest(BaseModel):
    profile_id: str

class ConfirmPreferencesRequest(JobSearchPreferences):
    pass

class RefreshDiscoveryRequest(BaseModel):
    profile_id: str

class RefreshDiscoveryResponse(BaseModel):
    run: DiscoveryRun
    recommendations: list[JobRecommendation]

class SaveJobRequest(BaseModel):
    job_id: str

@dataclass
class JobDiscoveryServiceBundle:
    suggest_preferences: SuggestJobSearchPreferencesService
    refresh: RefreshJobDiscoveryService
    save: SaveJobService
    check_saved_availability: CheckSavedJobAvailabilityService
~~~

The exact dependency function is get_job_discovery_services() -> JobDiscoveryServiceBundle and returns create_job_discovery_services(). Endpoints are POST /job-discovery/preferences/suggest, POST /job-discovery/preferences/confirm, POST /job-discovery/refresh, GET /job-discovery/runs/{run_id}, POST /job-discovery/saved, GET /job-discovery/saved, and POST /job-discovery/saved/{saved_id}/availability. Handlers use Depends(get_job_discovery_services); they never load repositories and no module-global discovery service exists. Tests override app.dependency_overrides[get_job_discovery_services].

Create frontend/job_discovery_view.py and keep frontend/app.py as composition. The flow selects a profile, proposes suggestions, edits every field, confirms, refreshes, displays official URL/reasons/gaps, saves immutable snapshots, lists saved jobs, and checks availability. It never shows radius/distance. Empty registry displays No approved job sources are configured and status NO_SOURCES_CONFIGURED. After implementation update docs/ARCHITECTURE.md, docs/PRODUCT_SPEC.md, docs/AI_GUIDELINES.md, README.md, and ROADMAP.md with source registry, contracts, offline tests, and non-goals.

## Milestone tasks

### Gate 0 — latest-main synchronization and clean baseline

- [ ] Files: branch state only plus existing assets; tests read-only. Consume origin/main and feature/job-discovery; produce actual clean baseline count.
- [ ] Failing command: git fetch origin main; git merge --no-commit origin/main; python -m pytest -q -m "not gemini_integration and not job_source_integration". Expected current failures/errors if assets or fixtures are stale.
- [ ] Inspect whether teammate’s deterministic profile-completeness fixture fix is present. Do not edit manual-test/profile.json without authoritative reviewed source and teammate ownership. Restore manual-test/reference-resume.docx only from validated source. Do not exclude the DOCX assertion or weaken unrelated tests.
- [ ] Minimal baseline repair is performed only by the owning change; if zero failures and zero errors cannot be reproduced, stop before Milestone A.
- [ ] Passing command: the same exact pytest command; expected zero failures/errors with actual count recorded from latest main, not assumed 139. Also run git diff --check and git status --short.
- [ ] Focused commit: chore: synchronize latest main and restore validated baseline assets.

### Milestone A — deterministic core

#### A1 shared role signals

- [ ] Files: domain/job_discovery/role_signals.py; infrastructure/optimization.py; tests/domain/job_discovery/test_role_signals.py; tests/test_multi_role_opportunity_analyzer.py. Consumed existing RoleFamily, RoleSignal, MultiRoleOpportunityAnalyzer; produced ROLE_SIGNAL_CATALOG, classifier, compatibility adapter.
- [ ] Failing test code asserts existing autonomous-driving and robotics classifications and optimizer regression. Command: python -m pytest -q tests/domain/job_discovery/test_role_signals.py tests/test_multi_role_opportunity_analyzer.py. Expected import failure.
- [ ] Move existing 14 signals and algorithm unchanged; update only imports and adapter wiring.
- [ ] Passing command: same; expected all focused tests pass.
- [ ] Focused commit: refactor: centralize deterministic role signal authority.

#### A2 preference suggestions

- [ ] Files: domain/job_discovery/preferences.py; application/job_discovery/preferences.py; tests/domain/job_discovery/test_preference_suggester.py; tests/application/job_discovery/test_suggest_preferences.py. Consumed exact MasterProfile fields; produced pure suggester and application service signatures above.
- [ ] Failing tests assert role families, target titles, variants, themes, levels, locations, deterministic rationale, owner mismatch ProfileNotFoundError, and zero saves. Command: python -m pytest -q tests/domain/job_discovery/test_preference_suggester.py tests/application/job_discovery/test_suggest_preferences.py. Expected missing symbols.
- [ ] Implement deterministic ordering, owner check, and delegation; no persistence.
- [ ] Passing command: same; expected all pass.
- [ ] Focused commit: feat: add reviewable deterministic preference suggestions.

#### A3 capability index and requirements

- [ ] Files: domain/job_discovery/capabilities.py; requirements.py; location.py; tests/domain/job_discovery/test_capability_index.py; tests/domain/job_discovery/test_requirement_extraction.py. Consumed exact profile fields and catalog; produced index, catalog, signals, extractor, parser.
- [ ] Failing tests include a required technology absent from profile and assert it is extracted and has exact material-gap text; locations cover Ontario/ON/Canada, a US state, country-only, unparseable. Command: python -m pytest -q tests/domain/job_discovery/test_capability_index.py tests/domain/job_discovery/test_requirement_extraction.py. Expected missing behavior.
- [ ] Implement fixed catalogs, aliases, phrase rules, evidence linkage, and conservative maps.
- [ ] Passing command: same; expected all pass.
- [ ] Focused commit: feat: add profile-independent requirements and capability index.

#### A4 normalization, deduplication, eligibility, scoring

- [ ] Files: normalization.py; deduplication.py; eligibility.py; scoring.py; ids.py; tests/domain/job_discovery/test_normalization.py; tests/domain/job_discovery/test_deduplication.py; tests/domain/job_discovery/test_eligibility.py; tests/domain/job_discovery/test_scoring.py. Consumed records, preferences, index, requirements; produced canonical terms, duplicate winner, assessments, score breakdown, IDs.
- [ ] Failing tests cover aliases, URL policy, duplicate keys, arrangement rules, age known/unknown, preferred-company tie-break, exact 100 points, provisional cap, exact reasons/gaps. Command: python -m pytest -q tests/domain/job_discovery/test_normalization.py tests/domain/job_discovery/test_deduplication.py tests/domain/job_discovery/test_eligibility.py tests/domain/job_discovery/test_scoring.py. Expected failures before implementation.
- [ ] Implement policies exactly; no radius/geocoding.
- [ ] Passing command: same; expected all pass.
- [ ] Focused commit: feat: add deterministic eligibility scoring and deduplication.

### Milestone B — connectors, persistence, orchestration, API

#### B1 source ports, registry, Greenhouse, Lever

- [ ] Files: domain/job_discovery/models.py; ports/job_discovery.py; infrastructure/job_sources/registry.py; infrastructure/job_sources/greenhouse.py; infrastructure/job_sources/lever.py; infrastructure/job_sources/errors.py; tests/infrastructure/job_sources/test_greenhouse.py; tests/infrastructure/job_sources/test_lever.py; tests/infrastructure/job_sources/test_registry.py; tests/fixtures/job_sources/*.json; pyproject.toml marker registration. Consumed source contracts; produced records/warnings, empty registry, connectors.
- [ ] Failing tests cover record-warning versus envelope-failure, Greenhouse timestamps/detail/no per-result detail, Lever skip/limit/direct availability GET with region, URL acceptance. Command: python -m pytest -q tests/infrastructure/job_sources. Expected missing modules.
- [ ] Implement injected httpx clients, pagination, warning aggregation, explicit region, safe-host upgrade, and status exceptions.
- [ ] Passing command: same; expected all fixture tests pass offline.
- [ ] Focused commit: feat: add Greenhouse and Lever source connectors.

#### B2 SQLite repositories

- [ ] Files: infrastructure/job_discovery_sqlite.py; tests/infrastructure/test_job_discovery_sqlite.py. Consumed repository protocols and six-table schema; produced migrations, adapters, indexes, transactions.
- [ ] Failing tests assert JSON round trips, current preference, immutable saved snapshot, recommendation replacement, statuses, empty registry. Command: python -m pytest -q tests/infrastructure/test_job_discovery_sqlite.py. Expected missing tables.
- [ ] Implement schema_version=1 storage.
- [ ] Passing command: same; expected all pass.
- [ ] Focused commit: feat: persist discovery runs recommendations and saved snapshots.

#### B3 refresh orchestration

- [ ] Files: application/job_discovery/refresh.py; tests/application/job_discovery/test_refresh.py. Consumed ports/connectors/policies; produced DiscoveryRun and persisted jobs/recommendations.
- [ ] Failing tests cover NO_SOURCES_CONFIGURED, partial warnings, all-source failure, warning ordering, IDs, ranks. Command: python -m pytest -q tests/application/job_discovery/test_refresh.py. Expected missing service.
- [ ] Implement exact refresh pipeline/status aggregation.
- [ ] Passing command: same; expected all pass.
- [ ] Focused commit: feat: orchestrate deterministic discovery refreshes.

#### B4 FastAPI

- [ ] Files: api/dependencies.py; api/job_discovery.py; api/main.py; tests/api/test_job_discovery_api.py. Consumed bundle/models; produced routes and dependency override point.
- [ ] Failing tests override app.dependency_overrides[get_job_discovery_services] and assert every endpoint, owner errors, and NO_SOURCES_CONFIGURED. Command: python -m pytest -q tests/api/test_job_discovery_api.py. Expected routes/dependency missing.
- [ ] Implement focused router and include it from existing main.
- [ ] Passing command: same; expected API contract tests pass.
- [ ] Focused commit: feat: expose job discovery FastAPI contracts.

### Milestone C — immutable saved jobs, Streamlit, documentation, opt-in smoke

#### C1 immutable saved jobs

- [ ] Files: application/job_discovery/saved.py; tests/application/job_discovery/test_saved_jobs.py. Consumed repositories/checker; produced immutable snapshot and retained unavailable rows.
- [ ] Failing tests assert repeated save keeps first snapshot and availability never deletes. Command: python -m pytest -q tests/application/job_discovery/test_saved_jobs.py. Expected missing service.
- [ ] Implement saved ID and status transitions.
- [ ] Passing command: same; expected all pass.
- [ ] Focused commit: feat: preserve immutable saved job snapshots.

#### C2 thin Streamlit

- [ ] Files: frontend/job_discovery_view.py; frontend/app.py; tests/test_job_discovery_streamlit.py. Consumed API/application contracts; produced propose/edit/confirm/refresh/results/save/check flow.
- [ ] Failing tests stub Streamlit and assert no radius/distance, exact empty-registry text, URL, reasons, gaps. Command: python -m pytest -q tests/test_job_discovery_streamlit.py. Expected missing view.
- [ ] Implement delivery composition only.
- [ ] Passing command: same; expected all pass.
- [ ] Focused commit: feat: add thin Streamlit job discovery delivery.

#### C3 documentation and opt-in smoke

- [ ] Files: docs/ARCHITECTURE.md; docs/PRODUCT_SPEC.md; docs/AI_GUIDELINES.md; README.md; ROADMAP.md; tests/integration/job_sources/test_live_smoke.py. Consumed implemented contracts; produced documentation and marker job_source_integration.
- [ ] Failing command: python -m pytest -q -m job_source_integration tests/integration/job_sources/test_live_smoke.py. Expected no-config report or missing test.
- [ ] Require explicitly supplied approved Greenhouse/Lever board configuration; without it report no sources configured, never a misleading successful empty search. With it, run only the live smoke.
- [ ] Passing command without env: same; expected clear opt-in skip/report. Ordinary suite never runs it.
- [ ] Focused commit: docs: document source registry and offline discovery guarantees.

### Final validation

- [ ] Run ruff check src tests; expected zero violations.
- [ ] Run mypy src; expected strict success without new ignores.
- [ ] Run all focused commands above; expected pass.
- [ ] Run python -m pytest -q -m "not gemini_integration and not job_source_integration"; expected zero failures/errors and actual clean count recorded.
- [ ] Run API contract tests and deterministic connector-fixture tests separately; expected pass.
- [ ] List, but do not automatically run, python -m pytest -q -m job_source_integration; run only with approved board configuration.
- [ ] Run git diff --check and git status --short; expected only intended files.
- [ ] Focused commit: test: validate deterministic job discovery MVP.

## Risks and mitigations

Free-source coverage is limited, so the curated registry is empty by default and unsupported sources are never shown. Registry maintenance and provider schema changes are handled with versioned adapters, envelope/record warnings, fixtures, and explicit failure statuses. Stale or removed postings use separate posted_at/source_updated_at/deadline, verification checks, and unavailable saved rows. Incomplete descriptions set completeness flags and the provisional cap. Duplicate postings use source/external keys then normalized fallback. Location ambiguity remains unknown under the conservative exact parser. Authorization ambiguity rejects only explicit contradiction. Score breakdown, labels, reasons, gaps, and provisional flag avoid false probability precision. Gemini job-fit work is deferred. Two-person synchronization is enforced by Gate 0.

## Deferred follow-up work

Gemini finalist explanations and any job_fit_models.py, job_fit_analysis.py, gemini_job_fit_analyzer.py, or Gemini job-fit tests; additional ATS providers; manual URL intake; scheduling; application tracking; authentication; geocoding; radius search.

## Self-review

- [ ] Every referenced type is defined above or imported from an exact existing path.
- [ ] DiscoveryRunStatus.NO_SOURCES_CONFIGURED and all warning codes are defined.
- [ ] No optional Gemini modules appear.
- [ ] Every preference field has filtering, scoring, reason, or tie-break behavior.
- [ ] Required terms come from a profile-independent catalog and absent required technology gaps are tested.
- [ ] Location behavior is exact and excludes radius/geocoding.
- [ ] Provider corrections and URL policy are explicit.
- [ ] Every task uses checkbox syntax with files, interfaces, failing/passing commands, and focused commit.
- [ ] Existing tests remain authoritative; baseline repair is separate from feature implementation.


## API response completion

The router also defines these exact response models: PreferencesSuggestionResponse with suggestion: JobSearchPreferenceSuggestion; ConfirmPreferencesResponse with preferences: JobSearchPreferences; SavedJobResponse with saved_job: SavedJob; SavedJobsResponse with saved_jobs: list[SavedJob]; AvailabilityResponse with saved_job: SavedJob. JobDiscoveryServiceBundle is a dataclass containing service instances, not a Pydantic payload, and its dependencies are constructed by create_job_discovery_services() in infrastructure/dependencies.py.


## Exact configuration and preference policy contracts

Add these types to domain/job_discovery/models.py:

~~~python
class WorkArrangementPreferenceMode(str, Enum):
    REQUIRED = "required"
    PREFERRED = "preferred"
    ACCEPTABLE = "acceptable"
    EXCLUDED = "excluded"

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
~~~

Add work_arrangement_mode: WorkArrangementPreferenceMode to JobSearchPreferences and JobSearchPreferenceSuggestion while retaining work_arrangement: WorkArrangement. Required means explicit equality is needed; preferred and acceptable do not reject and add no score; excluded means explicit equality is ineligible. The API and UI expose only city, region, country and these arrangement controls, never radius_km or distance. The production registry default is an empty list. A manual smoke requires an operator to provide approved Greenhouse board token or Lever site plus region; with no configuration the run is NO_SOURCES_CONFIGURED, not successful empty results.

Verification confidence is HIGH only for a successful official availability/status response with a valid URL and required identity fields, MEDIUM for a successful response with unknown status or nonfatal warnings, LOW for unverified records or malformed optional fields. Aggregate source confidence is the minimum confidence across the record's checks; unavailable/expired is ineligible.

## Exact file map

Create: src/resume_tailor/domain/job_discovery/__init__.py, models.py, preferences.py, role_signals.py, normalization.py, location.py, requirements.py, capabilities.py, eligibility.py, scoring.py, deduplication.py, ids.py; src/resume_tailor/application/job_discovery/__init__.py, preferences.py, refresh.py, saved.py; src/resume_tailor/ports/job_discovery.py; src/resume_tailor/infrastructure/job_sources/__init__.py, registry.py, greenhouse.py, lever.py, errors.py; src/resume_tailor/infrastructure/job_discovery_sqlite.py; src/resume_tailor/api/dependencies.py, job_discovery.py; src/resume_tailor/frontend/job_discovery_view.py; tests/domain/job_discovery/test_role_signals.py, test_preference_suggester.py, test_capability_index.py, test_requirement_extraction.py, test_normalization.py, test_deduplication.py, test_eligibility.py, test_scoring.py; tests/application/job_discovery/test_suggest_preferences.py, test_refresh.py, test_saved_jobs.py; tests/infrastructure/job_sources/test_greenhouse.py, test_lever.py, test_registry.py, test_job_discovery_sqlite.py; tests/fixtures/job_sources/*.json; tests/api/test_job_discovery_api.py; tests/test_job_discovery_streamlit.py; tests/integration/job_sources/test_live_smoke.py.

Modify only for this feature: src/resume_tailor/infrastructure/optimization.py, src/resume_tailor/api/main.py, src/resume_tailor/frontend/app.py, src/resume_tailor/config.py, src/resume_tailor/infrastructure/dependencies.py, pyproject.toml, and after implementation docs/ARCHITECTURE.md, docs/PRODUCT_SPEC.md, docs/AI_GUIDELINES.md, README.md, ROADMAP.md. Do not propose unrelated refactors.

## Exact failing-test bodies required by the checkbox tasks

Each implementation checkbox must create its named test before production code. These are the minimum failing bodies; assertions are exact and may only be expanded for the same behavior.

~~~python
def test_role_catalog_preserves_existing_classification():
    result = classify_role_signals("autonomous driving perception engineer", "Perception Engineer")
    assert result.primary_family is RoleFamily.AUTONOMOUS_SYSTEMS
    assert result.family_scores[RoleFamily.AUTONOMOUS_SYSTEMS] > 0
~~~

~~~python
def test_suggestion_is_reviewable_and_not_persisted():
    suggestion = DeterministicJobSearchPreferenceSuggester().suggest(profile, generated_at=when)
    assert suggestion.target_titles
    assert suggestion.related_title_variants
    assert suggestion.technical_themes
    assert suggestion.role_family_priority
    repository = SpyPreferencesRepository()
    SuggestJobSearchPreferencesService(profile_repo, suggester).suggest("user-1", profile.id, generated_at=when)
    assert repository.save_calls == 0
~~~

~~~python
def test_required_term_absent_from_profile_is_extracted_and_gap_is_material():
    signals = RequirementExtractor().extract("Software Engineer", "Required CUDA and Python.", None, WorkArrangement.UNKNOWN)
    assert "cuda" in signals.required_terms
    _, gaps = DeterministicExplanationBuilder().reasons_and_gaps(job_fixture, signals, ProfileCapabilityIndex(terms={}))
    assert "No reviewed profile evidence or skill was found for required cuda." in gaps
~~~

~~~python
@pytest.mark.parametrize(("raw", "city", "region", "country"), [
    ("Toronto, ON, Canada", "toronto", "on", "CA"),
    ("Toronto, Ontario, Canada", "toronto", "on", "CA"),
    ("Austin, TX, United States", "austin", "tx", "US"),
    ("Canada", None, None, "CA"),
])
def test_location_parser_supported_forms(raw, city, region, country):
    parsed = parse_location(raw)
    assert (parsed.city, parsed.region, parsed.country_code) == (city, region, country)

def test_location_parser_leaves_unparseable_unknown():
    parsed = parse_location("Near a major metropolitan area")
    assert parsed.parseable is False
    assert parsed.country_code is None
~~~

~~~python
def test_source_connector_skips_bad_record_with_warning_and_fails_bad_envelope():
    result = connector.fetch(source, fetched_at=when)
    assert result.records[0].external_job_id == "ok-1"
    assert result.warnings[0].code is SourceRecordWarningCode.MISSING_TITLE
    with pytest.raises(JobSourceEnvelopeError):
        connector.fetch(envelope_fixture_source, fetched_at=when)
~~~

~~~python
def test_api_uses_overridable_service_dependency():
    app.dependency_overrides[get_job_discovery_services] = lambda: fake_bundle
    response = client.post("/job-discovery/preferences/suggest", json={"profile_id": "p1"})
    assert response.status_code == 200
    app.dependency_overrides.clear()
~~~

~~~python
def test_refresh_empty_registry_has_explicit_status():
    run = service.refresh("u1", "p1", preferences, started_at=when)
    assert run.status is DiscoveryRunStatus.NO_SOURCES_CONFIGURED
    assert run.error_messages == []
~~~

~~~python
def test_saved_snapshot_is_immutable_when_job_changes():
    first = save_service.save("u1", "job-1", saved_at=when)
    repository.replace_job(job_with_new_description)
    second = save_service.save("u1", "job-1", saved_at=later)
    assert second.posting_snapshot.description == first.posting_snapshot.description
~~~

~~~python
def test_streamlit_does_not_render_radius_or_distance():
    render_job_discovery_view(fake_api)
    assert "radius" not in rendered_text.lower()
    assert "distance" not in rendered_text.lower()
~~~

Gate 0 intentionally adds no new test body: its failing command is the unmodified repository suite, and its repair is blocked until the established baseline is reproduced.

## Baseline evidence and stop rule

The prior local result was 102 passed, 27 failed, 10 errors, 1 deselected; repository documentation records 139 passed, 1 deselected, 1 warning. The known missing asset is manual-test/reference-resume.docx, referenced by existing DOCX/rendering tests. The known stale manual-test/profile.json lacks technical_skills, required education fields (start_date, expected_graduation_date, location, awards, relevant_coursework), experience dates/locations, project technology_label, and the expected MPC Hacks award_or_placement. Gate 0 must first fetch and integrate origin/main, then check whether the teammate's deterministic profile-completeness fixture fix is present. Do not edit manual-test/profile.json without authoritative reviewed source plus teammate ownership. Restore reference-resume.docx only from its validated source. If the exact offline command has any failure or error after synchronization and approved baseline repair, stop implementation; never solve this by exclusions or weakened assertions.

## API response completion

The router also defines these exact response models: PreferencesSuggestionResponse with suggestion: JobSearchPreferenceSuggestion; ConfirmPreferencesResponse with preferences: JobSearchPreferences; SavedJobResponse with saved_job: SavedJob; SavedJobsResponse with saved_jobs: list[SavedJob]; AvailabilityResponse with saved_job: SavedJob. JobDiscoveryServiceBundle is a dataclass containing service instances, not a Pydantic payload, and its dependencies are constructed by create_job_discovery_services() in infrastructure/dependencies.py.


## Exact import and exception requirements

Every new module begins with from __future__ import annotations. models.py imports datetime from datetime, Enum from enum, Any and Literal from typing, BaseModel and AnyHttpUrl from pydantic, and RoleFamily from resume_tailor.domain.models. Ports import Protocol and the domain models from resume_tailor.domain.job_discovery.models. application/job_discovery/preferences.py imports the existing MasterProfileRepository from resume_tailor.ports.interfaces; it does not redeclare that protocol. Define ProfileNotFoundError(ValueError) in application/job_discovery/preferences.py and map it to HTTP 404 in the focused router. Define SourceConfigurationError(ValueError) in infrastructure/job_sources/registry.py for invalid operator configuration. All type references in the snippets are therefore either standard-library/Pydantic imports, same-module definitions, or the exact existing paths listed above.


## Explanation and marker contracts

Create DeterministicExplanationBuilder in domain/job_discovery/scoring.py with exact signature:

~~~python
class DeterministicExplanationBuilder:
    def reasons_and_gaps(self, job: DiscoveredJob, requirements: JobRequirementSignals, profile_index: ProfileCapabilityIndex) -> tuple[list[str], list[str]]: ...
~~~

The required-technology failing test calls this signature with ProfileCapabilityIndex(terms={}), so no undefined helper is part of the plan. Add the exact pytest marker in pyproject.toml: job_source_integration = "opt-in tests that require explicitly approved live Greenhouse or Lever configuration". Existing gemini_integration remains unchanged and no Gemini job-fit marker is added.
