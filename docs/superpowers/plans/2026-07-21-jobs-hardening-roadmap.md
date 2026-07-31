# Jobs Hardening Roadmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Use superpowers:verification-before-completion before reporting completion.

**Goal:** Harden the Jobs feature into an evidence-backed, two-feed discovery experience whose retrieval, eligibility, grading, explanations, persistence, and UI behavior are measurable and deterministic.

**Architecture:** Keep domain policy deterministic and evidence-authoritative, application services responsible for orchestration, provider ports sanitized to retrieval fields, infrastructure responsible for connectors and persistence, and FastAPI/Streamlit responsible only for delivery. Retain excluded evaluations internally while exposing them only through an explicit user action.

**Tech Stack:** Python 3.11+, Pydantic 2, FastAPI, Streamlit, SQLite, httpx, pytest, Ruff, strict mypy, recorded provider fixtures, and opt-in official-source smoke tests.

## Global Constraints

- Do not send a complete resume, profile evidence, or profile capability index to a provider.
- Numeric component and total scores remain internal; normal UI shows grade, eligibility, matches, evidence, gaps, and provisional status.
- The grade is profile fit, never interview, hiring, offer, or probability language.
- `Don't Match` is retained internally and hidden until the user expands `Show excluded jobs (N)`.
- Unknown eligibility is allowed when there is no known hard conflict, is visibly labeled, ranks after known-eligible jobs within an otherwise equal Tailored grade, and identifies every unresolved fact.
- Interest and preferred-company signals affect retrieval, filtering, and equal-fit tie-breaking only; they never provide substantive qualification points or raise a fit grade.
- Provider expansion is conditional on an official-source audit; arbitrary scraping is prohibited.
- The known unrelated DOCX health test may return HTTP 503 when no exact page-count provider exists. Do not alter resume rendering, DOCX generation, health behavior, or that test to hide the condition.
- Existing resume, cover-letter, Gemini, DOCX, profile, and health behavior remains unchanged except for the explicit Tailor-for-this-job handoff.
- Production implementation branches are sequential branches from the newest `main`, never one branch for all five batches.

## Approved product decisions

### Exploration sectors

The initial user-facing sectors are:

- Software Engineering
- Data Engineering
- AI / Machine Learning
- Computer Vision
- Robotics / Autonomous Systems
- Embedded Systems / Firmware
- Hardware / Systems Integration
- Controls / Mechatronics
- Testing / Verification

These are exploration sectors and do not replace internal role families.

### Feeds and grades

- `Tailored for you` retrieves from reviewed profile direction, confirmed preferences, eligibility constraints, level, location, arrangement, and posting age; it ranks primarily by fit.
- `Explore sectors` retrieves from explicitly selected sectors; it ranks newest to oldest, with fit only as a secondary tie-breaker.
- Both feeds use the same eligibility and fit-grade evaluator.
- Substantive grades are Excellent, Good, Weak, and Don't Match.
- Provisional is independent of substantive grade.

### Numeric score visibility

Numeric component and total scores remain internal. Benchmark and developer diagnostics may expose them; normal Jobs UI does not.

### Unknown eligibility

Unknown is not silently treated as eligible. It may appear in a normal feed when no hard conflict is known, is visibly labeled, is ranked after known-eligible jobs within an equal Tailored grade, and lists each unresolved fact.

### Other approved decisions

- The user authorizes the first locked-test execution; Codex must stop and request that authorization before running it.
- Tailor for this job prepares the existing tailoring input and switches to the existing resume workflow. It does not generate documents or alter Gemini, composition, or DOCX behavior.
- Historical results remain readable, are labeled as evaluated using an earlier matching policy, and are not silently represented as current-policy evaluations.

## Dependency sequence

```text
1. Benchmark and human review
        |
2. Scoring redesign, calibration, validation, and locked gate
        |
3. Queries, two feeds, provider audit, and approved providers
        |
4. Dedicated Jobs UI, preferences, and manual testing
        |
5. Final hardening
```

## Branch strategy

This branch, `feature/job-discovery-hardening`, contains only the roadmap and execution-plan documents. After this branch is reviewed and merged, implementation uses these sequential branches, each created from the newest `main`:

1. `feature/jobs-scoring-benchmark`
2. `feature/jobs-scoring-redesign`
3. `feature/jobs-query-feeds-providers`
4. `feature/jobs-ui`
5. `fix/jobs-final-hardening`

Each branch must finish its own tests and documentation before the next branch is created. Workers must not complete all five batches on one branch.

## Plan documents

1. `2026-07-21-jobs-benchmark-human-review.md` — dataset, rubric, human pause, and baseline.
2. `2026-07-21-jobs-scoring-redesign-calibration.md` — evaluator authority, calibration, validation, and user-authorized locked gate.
3. `2026-07-21-jobs-query-feeds-providers.md` — sanitized queries, feed services, provider audit, persistence, and API.
4. `2026-07-21-jobs-ui-manual-testing.md` — dedicated Jobs navigation, preferences, split-panel UI, actions, and browser testing.
5. `2026-07-21-jobs-final-hardening.md` — cross-system verification and final audit.

## Cross-plan contracts

The following names are stable across all plans:

```python
class FitGrade(StrEnum):
    EXCELLENT = "excellent"
    GOOD = "good"
    WEAK = "weak"
    DONT_MATCH = "dont_match"

class FeedKind(StrEnum):
    TAILORED = "tailored"
    EXPLORE = "explore"

class TailoredJobQuery(BaseModel): ...
class ExploreJobQuery(BaseModel): ...
class ProviderJobQuery(BaseModel): ...
class ProviderCapabilities(BaseModel): ...

class JobsExperienceService(Protocol):
    def refresh_tailored(...): ...
    def refresh_explore(...): ...
    def get_feed(...): ...
    def get_excluded(...): ...
    def get_job_detail(...): ...
    def save_job(...): ...
    def prepare_tailoring(...): ...
```

Plan 2 owns evaluation-policy versioning and compatibility adapters. Plan 3 owns permanent recommendation/feed persistence migration and changes query, feed, persistence, and API contracts atomically; there must not be two separate migrations for the same recommendation data.

## Global acceptance gates

- Exactly 60 calibration, 20 validation, and 20 locked-test cases.
- Permanent split membership and no cross-split duplicate or near-duplicate scenario leakage.
- No hard-ineligible posting in a normal feed.
- No Excellent grade without every critical must-have satisfied.
- At least 85% exact validation grade agreement.
- At least 95% exact-or-adjacent validation grade agreement.
- At least 85% pairwise ranking accuracy on annotated comparable validation pairs.
- At least 80% top-five precision in grouped Tailored validation scenarios.
- 100% traceable positive reasons and material gaps.
- No interest-only or preferred-company result outranks a clear evidence match.
- Deterministic output across source order, input order, and `PYTHONHASHSEED` values.
- Offline Jobs suite, Ruff, strict mypy comparison, `git diff --check`, and manual browser checklist complete.

## Scope and migration guardrails

- Do not add background scheduling, application tracking, automatic application submission, authentication, arbitrary web scraping, paid search providers, geocoding, radius calculations, Gemini job-fit analysis, or resume/cover-letter generation changes.
- Preserve stable job IDs and immutable saved snapshots.
- Migrate legacy results for readability and label them with their earlier matching policy.
- Do not silently rescore historical results with the current policy.

