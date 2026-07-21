# Jobs Query, Feeds, and Providers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Use superpowers:verification-before-completion before reporting completion.

**Goal:** Add sanitized Tailored and Explore queries, provider capability contracts, deterministic feed assembly, official-source auditing, and one atomic recommendation/feed persistence and API migration.

**Architecture:** Application retrieval builds provider-safe queries and records provider-side versus local filtering. Connectors return paged provider-neutral records with provenance and structured warnings. Feed services evaluate every candidate using Plan 2's frozen evaluator and persist normal/excluded visibility together with the new feed contract.

**Tech Stack:** Python 3.11+, Pydantic 2, Protocol ports, httpx, Greenhouse/Lever fixtures, SQLite migrations, FastAPI, pytest, and opt-in official-source smoke tests.

## Global Constraints

- Providers receive only sectors, controlled role families/titles, locations, arrangements, levels, posting age, and approved source restrictions.
- Providers never receive resume text, profile evidence, skills, coursework, or scoring instructions.
- Official-source audit may approve providers, reject all candidates, or defer expansion with documented reasons.
- No generic arbitrary web scraper is allowed.
- `Tailored` sorts primarily by fit; `Explore` sorts newest-to-oldest with fit only as a tie-breaker.
- Both feeds share Plan 2 eligibility and fit grading.
- `Don't Match` is persisted but excluded from ordinary feed payloads until explicit expansion.
- Permanent recommendation/feed persistence migration occurs once, atomically, in this plan.
- The known unrelated DOCX HTTP 503 constraint remains unchanged.

## Prerequisites

- Branch: `feature/jobs-query-feeds-providers`, created from newest `main` after `feature/jobs-scoring-redesign` merges.
- Plan 2 evaluation policy, policy version, validation report, and user-authorized locked gate are complete.
- Read the approved Jobs design, current provider adapters, source registry, SQLite repositories, API router, and fixture conventions.

## Files

Create:

- `src/resume_tailor/domain/job_discovery/queries.py` — Tailored, Explore, and provider-safe query models.
- `src/resume_tailor/domain/job_discovery/providers.py` — capability and page/provenance models.
- `src/resume_tailor/domain/job_discovery/feeds.py` — feed-specific visibility and ordering.
- `src/resume_tailor/application/job_discovery/retrieval.py` — query planning, paging, local filtering, and partial success.
- `src/resume_tailor/application/job_discovery/feed_services.py` — Tailored/Explore orchestration.
- `src/resume_tailor/infrastructure/job_discovery_migrations.py` — one transactional schema migration.
- `tests/domain/job_discovery/test_queries.py`
- `tests/domain/job_discovery/test_feed_ranking.py`
- `tests/application/job_discovery/test_retrieval.py`
- `tests/application/job_discovery/test_feed_services.py`
- `tests/infrastructure/job_sources/test_provider_capabilities.py`
- `docs/job-discovery/PROVIDER_AUDIT.md`

Modify:

- `src/resume_tailor/ports/job_discovery.py`
- `src/resume_tailor/domain/job_discovery/models.py`
- `src/resume_tailor/domain/job_discovery/normalization.py`
- `src/resume_tailor/domain/job_discovery/deduplication.py`
- `src/resume_tailor/infrastructure/job_sources/registry.py`
- `src/resume_tailor/infrastructure/job_sources/_common.py`
- `src/resume_tailor/infrastructure/job_sources/greenhouse.py`
- `src/resume_tailor/infrastructure/job_sources/lever.py`
- `src/resume_tailor/infrastructure/job_discovery_sqlite.py`
- `src/resume_tailor/infrastructure/dependencies.py`
- `src/resume_tailor/api/dependencies.py`
- `src/resume_tailor/api/job_discovery.py`
- `src/resume_tailor/infrastructure/config.py`
- Existing provider, registry, persistence, API, normalization, deduplication, and refresh tests.
- `README.md`, `ROADMAP.md`, `docs/ARCHITECTURE.md`, and `docs/PRODUCT_SPEC.md`.

No new provider adapter is authorized until the audit task has selected an exact official provider and the reviewed plan records its exact adapter and fixture paths.

## Interfaces

```python
class FeedKind(StrEnum):
    TAILORED = "tailored"
    EXPLORE = "explore"

class TailoredJobQuery(BaseModel): ...
class ExploreJobQuery(BaseModel): ...
class ProviderJobQuery(BaseModel): ...

class JobSourceConnector(Protocol):
    def capabilities(self, source: SupportedJobSource) -> ProviderCapabilities: ...
    def fetch_page(
        self,
        source: SupportedJobSource,
        query: ProviderJobQuery,
        cursor: str | None,
        *,
        fetched_at: datetime,
    ) -> JobSourcePage: ...

class FeedService(Protocol):
    def refresh_tailored(...): ...
    def refresh_explore(...): ...
    def get_feed(...): ...
    def get_excluded(...): ...
```

## Task 1: Official-source audit

**Files:** `docs/job-discovery/PROVIDER_AUDIT.md` and provider research notes.

Audit Greenhouse, Lever, and candidate official mechanisms against access approval, stability, description quality, stable IDs, locations, application URLs, timestamps, pagination, terms, rate limits, availability checks, and offline testability.

- [ ] Write a failing documentation-review checklist that rejects a candidate without evidence for every mandatory field.
- [ ] Run the checklist manually; expected initial result is an incomplete audit.
- [ ] Record one of three outcomes for each candidate: approved, rejected, or deferred with concrete reasons.
- [ ] If no candidate meets every mandatory requirement, document that provider expansion is deferred; do not require or implement a new provider.
- [ ] Commit: `docs(jobs): audit official provider coverage`.

## Task 2: Query and capability contracts

- [ ] Write a spy-connector test asserting that provider calls contain only sanitized retrieval fields and never profile evidence or resume text.
- [ ] Run:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q `
  tests/domain/job_discovery/test_queries.py `
  tests/infrastructure/job_sources/test_provider_capabilities.py
```

Expected failure: current connector signature has no query or capability contract.

- [ ] Implement query models, provider capabilities, page cursor, filter-plan, and provenance models.
- [ ] Re-run; expected pass proves provider-boundary sanitization.
- [ ] Commit: `feat(jobs): define provider-neutral retrieval queries`.

## Task 3: Retrieval planning and partial success

**Interfaces:** `RetrievalService` consumes Tailored/Explore queries and produces normalized source pages, pushdown/local filter diagnostics, warnings, and partial-success status.

- [ ] Write failing tests for bounded pagination, repeated-cursor protection, provider-side filter declaration, local fallback filtering, one-page failure, one-provider failure, and deterministic page ordering.
- [ ] Run:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q tests/application/job_discovery/test_retrieval.py
```

Expected failure: missing query orchestration and page contracts.

- [ ] Implement bounded retrieval and structured source outcomes. A successful provider remains successful even if another provider fails; a repeated cursor terminates with a warning.
- [ ] Re-run; expected pass with no raw secret or profile logging.
- [ ] Commit: `feat(jobs): orchestrate bounded multi-source retrieval`.

## Task 4: Adapt official connectors and fixtures

- [ ] Write failing Greenhouse and Lever fixture tests for query invocation, capability metadata, pagination, timestamp authority, malformed records, bad envelopes, retries, and availability checks.
- [ ] Run:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q `
  tests/infrastructure/job_sources/test_greenhouse.py `
  tests/infrastructure/job_sources/test_lever.py `
  tests/infrastructure/job_sources/test_registry.py `
  tests/infrastructure/job_sources/test_provider_capabilities.py
```

Expected failure: adapters do not implement `fetch_page()` or truthful capabilities.

- [ ] Adapt only audited official connectors. Never invent `posted_at`; unknown freshness is explicit. Keep recorded fixtures offline.
- [ ] Re-run; expected pass with no ordinary live network calls.
- [ ] Commit: `refactor(jobs): adapt official sources to query contract`.

If Task 1 approves an additional provider, create a separate reviewed task naming its exact adapter and fixture files, then run the same failing/pass/commit cycle. If all candidates are rejected or deferred, record that no additional adapter is required.

## Task 5: Normalize, deduplicate, and retain provenance

- [ ] Write failing tests for source-qualified identities, cross-provider duplicates, alias provenance, canonical winner selection, and source-order independence.
- [ ] Run:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q `
  tests/domain/job_discovery/test_normalization.py `
  tests/domain/job_discovery/test_deduplication.py
```

Expected failure: alias provenance and source identity are incomplete.

- [ ] Implement full provenance retention and deterministic duplicate resolution.
- [ ] Re-run; expected pass with identical results under provider permutations.
- [ ] Commit: `fix(jobs): preserve cross-provider provenance and identity`.

## Task 6: Feed services and ordering

- [ ] Write failing tests for Tailored fit-first ordering, Explore freshness-first ordering, unknown-date placement, equal-timestamp fit tie-breaks, unknown eligibility ordering, and excluded-count behavior.
- [ ] Run:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q `
  tests/domain/job_discovery/test_feed_ranking.py `
  tests/application/job_discovery/test_feed_services.py
```

Expected failure: only one current recommendation ordering exists.

- [ ] Implement two feed services using the frozen Plan 2 evaluator. Persist all evaluations conceptually, but return only visible items plus excluded count by default.
- [ ] Re-run; expected pass with shared grade/eligibility and feed-specific ordering.
- [ ] Commit: `feat(jobs): add tailored and sector exploration feeds`.

## Task 7: Atomic persistence and API migration

Plan 2 may have added policy-version fields and compatibility adapters, but this task performs the single permanent recommendation/feed migration. Do not migrate the same recommendation data in another plan.

- [ ] Write failing SQLite/API tests for feed kind, visibility, evaluation policy version, historical-result labels, excluded retrieval, new Tailored/Explore refresh endpoints, and the existing refresh compatibility alias.
- [ ] Run:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q `
  tests/infrastructure/test_job_discovery_sqlite.py `
  tests/api/test_job_discovery_api.py
```

Expected failure: existing schema and API cannot represent two feeds and excluded evaluations.

- [ ] Implement one transactional schema migration, legacy-read conversion, repositories, application wiring, and typed API responses.
- [ ] Re-run; expected pass with immutable saved snapshots and readable earlier-policy recommendations.
- [ ] Commit atomically: `feat(jobs): persist and deliver two feeds`.

## Task 8: Opt-in live smoke

Run only after offline tests pass and only with explicit approved source configuration:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q `
  -m job_source_integration tests/integration/job_sources/test_live_smoke.py
```

Without configuration, expected result is a clear skip. With configuration, the smoke is bounded, official-source-only, and profile-free.

## Acceptance criteria

- Tailored and Explore have separate typed query models.
- Provider calls contain no profile evidence.
- Pushdown and local filters are observable.
- Pagination, freshness, partial failure, availability, and provenance are explicit.
- Provider expansion is conditional and evidence-backed.
- Both feeds share eligibility and grading but sort differently.
- Excluded evaluations are retained and separately requested.
- Persistence and API migration occur once and atomically.

## Recommended branch and commit boundaries

Recommended branch: `feature/jobs-query-feeds-providers`, created from newest `main` after Plan 2 merges. Tasks 1–6 are independently reviewable. Task 7 is one atomic migration/API commit. Any approved additional provider is a separate commit.

## Known unrelated DOCX constraint

Do not modify the DOCX health test or rendering behavior if the known environment-specific 503 appears.

