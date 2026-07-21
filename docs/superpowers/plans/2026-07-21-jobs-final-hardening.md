# Jobs Final Hardening and Merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Use superpowers:verification-before-completion before reporting completion.

**Goal:** Verify the complete Jobs redesign across benchmark, evaluator, providers, persistence, API, Streamlit, determinism, and manual browser behavior without adding new features.

**Architecture:** This is a verification and defect-fix batch. It exercises the full offline path from provider fixture through query planning, normalization, eligibility, grading, persistence, API, and UI, then performs authorized locked reporting and documentation reconciliation. Any fix must be narrow, tested, and documented.

**Tech Stack:** Python 3.11+, pytest, Streamlit `AppTest`, Ruff, strict mypy, SQLite, recorded provider fixtures, opt-in live smoke, and manual browser testing.

## Global Constraints

- No new product features during final hardening.
- Do not alter resume rendering, DOCX generation, Gemini, cover-letter behavior, health behavior, or unrelated tests.
- Locked execution requires explicit user authorization; stop before running it if authorization is absent.
- Numeric scores remain diagnostics-only in normal UI.
- Historical results remain readable and earlier-policy labeled.
- The known unrelated DOCX HTTP 503 constraint is reported, never concealed.

## Prerequisites

- Branch: `fix/jobs-final-hardening`, created from newest `main` after `feature/jobs-ui` merges.
- Plans 1–4 merged and their focused acceptance criteria complete.
- Manual browser checklist has been executed for the UI branch.
- Record pre-change Ruff and strict-mypy output before any fix.

## Files

Create:

- `tests/integration/job_discovery/test_jobs_end_to_end.py` — offline full-path scenarios.
- `tests/job_discovery/test_determinism_matrix.py` — input/source/hash-seed permutations.
- `tests/job_discovery/test_saved_snapshot_compatibility.py` — old/new snapshot reads.
- `docs/job-discovery/VALIDATION_REPORT.md` — benchmark, locked, and gate results.
- `docs/job-discovery/MANUAL_TEST_REPORT.md` — browser evidence summary.

Modify only when a verified defect requires it:

- Jobs domain/application/infrastructure/API/frontend files from Plans 1–4.
- `README.md`, `ROADMAP.md`, `docs/ARCHITECTURE.md`, `docs/PRODUCT_SPEC.md`, `docs/AI_GUIDELINES.md`, `docs/job-discovery/BENCHMARK.md`, `docs/job-discovery/SCORING.md`, and `docs/job-discovery/PROVIDER_AUDIT.md`.

## Interfaces

Final verification consumes the stable interfaces:

```python
class JobsExperienceService(Protocol): ...
class JobSourceConnector(Protocol): ...
class JobEvaluator(Protocol): ...
class FeedService(Protocol): ...
```

No interface may be renamed during this plan unless a focused failing test demonstrates a real contract defect and all dependent plans are reconciled in the same change.

## Task 1: Cross-system offline matrix

- [ ] Write failing end-to-end tests for Tailored, Explore, exclusion, partial failure, duplicate providers, unknown eligibility, provisional status, saved snapshot, API ownership, and Streamlit selection.
- [ ] Run:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q tests/integration/job_discovery/test_jobs_end_to_end.py
```

Expected failure: any incomplete contract between provider fixture, application service, persistence, API, or UI is exposed.

- [ ] Fix only the narrow failing contract.
- [ ] Re-run; expected pass through the complete offline path.
- [ ] Commit: `test(jobs): verify cross-system discovery contracts`.

## Task 2: Determinism and duplicate prevention

- [ ] Write failing permutation tests for provider order, page order, posting order, evidence order, requirement order, preference order, duplicate alias order, and hash seeds.
- [ ] Run:

```powershell
foreach ($seed in 1, 2, 777, 99991) {
  $env:PYTHONHASHSEED = "$seed"
  & ".\.venv\Scripts\python.exe" -m pytest -q `
    tests/job_discovery/test_determinism_matrix.py `
    tests/domain/job_discovery/test_deduplication.py
}
Remove-Item Env:PYTHONHASHSEED
```

Expected failure: any noncanonical result differs in evaluation JSON, visibility, provenance, explanation order, or rank.

- [ ] Fix canonical sorting or identity only where the failing assertion identifies it.
- [ ] Re-run; expected byte-identical canonical output.
- [ ] Commit: `test(jobs): enforce order-independent recommendations`.

## Task 3: Saved snapshot and migration compatibility

- [ ] Write failing tests for legacy recommendation labels, earlier-policy display, v1 saved snapshots, v2 snapshots, availability changes, and preservation of immutable descriptions/URLs.
- [ ] Run:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q tests/job_discovery/test_saved_snapshot_compatibility.py tests/infrastructure/test_job_discovery_sqlite.py
```

Expected failure: a legacy payload cannot be loaded or is incorrectly presented as current-policy output.

- [ ] Fix the legacy-read adapter or migration transaction without rewriting historical snapshots.
- [ ] Re-run; expected pass with explicit earlier-policy labels.
- [ ] Commit: `fix(jobs): preserve historical result compatibility`.

## Task 4: Benchmark validation and locked reporting

- [ ] Run calibration and validation acceptance commands from Plans 1–2.
- [ ] Confirm the approved policy version, split checksums, metric definitions, confusion matrices, traceability, ranking, and leakage counts.
- [ ] Stop and request user authorization before running the first locked command.
- [ ] After authorization, run exactly:

```powershell
$env:JOB_DISCOVERY_LOCKED_GATE = "1"
& ".\.venv\Scripts\python.exe" -m pytest -q `
  -m job_discovery_locked tests/job_discovery/benchmark/test_locked_gate.py
Remove-Item Env:JOB_DISCOVERY_LOCKED_GATE
```

- [ ] Record aggregate results and locked exposure count in `docs/job-discovery/VALIDATION_REPORT.md`.
- [ ] If locked fails, follow Plan 2's aggregate failure-class and independent-calibration regression process; do not tune against individual locked cases.
- [ ] Commit: `docs(jobs): publish validation and locked-test report`.

## Task 5: Manual web audit

- [ ] Review the completed `manual-test/JOBS_BROWSER_CHECKLIST.md`.
- [ ] Re-run production entry-point checks for profile loading, four sections, both feed orders, selection, exclusions, saved jobs, availability, URL, Tailor handoff, responsive layout, and source failure states.
- [ ] Record browser, viewport, date, commit, result, and screenshot references in `docs/job-discovery/MANUAL_TEST_REPORT.md`.
- [ ] Commit: `docs(jobs): record final manual browser audit`.

## Task 6: Full verification and tool comparison

Capture pre-change comparisons and run:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q `
  tests/domain/job_discovery `
  tests/application/job_discovery `
  tests/infrastructure/job_sources `
  tests/infrastructure/test_job_discovery_sqlite.py `
  tests/api/test_job_discovery_api.py `
  tests/test_job_discovery_streamlit.py `
  tests/test_jobs_page_streamlit.py `
  tests/test_jobs_app_streamlit.py `
  tests/integration/job_discovery/test_jobs_end_to_end.py

& ".\.venv\Scripts\python.exe" -m pytest -q `
  -m "not gemini_integration and not job_source_integration and not job_discovery_locked"

& ".\.venv\Scripts\python.exe" -m ruff check src tests
& ".\.venv\Scripts\python.exe" -m mypy src
git diff --check
git status --short
```

Expected passing behavior: focused Jobs and offline suites pass; Ruff reports zero violations; mypy has no new errors versus the captured baseline and should be zero total; diff check is clean; status contains only intended Jobs hardening changes.

If the known unrelated DOCX health test alone returns HTTP 503 because no exact page-count provider exists, record it as an environmental exception. Any additional failure is investigated normally and blocks completion.

- [ ] Commit: `test(jobs): complete final hardening verification`.

## Task 7: Final reviewer audit and documentation reconciliation

- [ ] Review all six plan/feature documents for interface names, branch names, approved sectors, score visibility, unknown eligibility, provider decision, migration ownership, locked custodian, Tailor action, and historical-result policy.
- [ ] Confirm no unsupported candidate claim, arbitrary scraping, or full-profile provider call is documented or implemented.
- [ ] Confirm no new feature entered during hardening.
- [ ] Re-run `git diff --check` and `git status --short`.
- [ ] Commit documentation-only reconciliation if needed: `docs(jobs): reconcile final hardening contracts`.

## Acceptance criteria

- Cross-system offline matrix passes.
- Deterministic outputs and duplicate prevention pass across all permutations.
- Historical results and snapshots remain readable and correctly labeled.
- User-authorized locked gate is reported with exposure policy.
- Manual browser report is complete.
- Focused suite, offline suite, Ruff, strict mypy comparison, and diff checks meet gates.
- No new feature, unrelated code, or concealed DOCX/health failure exists.

## Recommended branch and commit boundaries

Recommended branch: `fix/jobs-final-hardening`, created from newest `main` after Plan 4 merges. Each task is an independently reviewable commit; fixes must remain narrow and no feature work may be introduced.

## Known unrelated DOCX constraint

The HTTP 503 condition from the exact DOCX page-count provider test remains an explicitly documented environmental constraint. Do not alter health, DOCX, rendering, or its test.

