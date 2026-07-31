# Jobs Benchmark and Human Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Use superpowers:verification-before-completion before reporting completion.

**Goal:** Create an exactly 100-case benchmark and obtain approved human-reviewed ground truth before production scoring changes.

**Architecture:** Benchmark schemas, split loading, metrics, and review reporting live under test/development tooling and never enter production services. The process has an explicit Stage A proposal/pause and Stage B approval/freeze; no proposed label becomes approved ground truth before the pause.

**Tech Stack:** Python 3.11+, Pydantic 2, pytest, standard-library JSON/HTML generation, and ignored generated review artifacts.

## Global Constraints

- Do not change production scoring in this plan.
- Do not create provider fixtures in this plan.
- Use synthetic or deidentified profile evidence only.
- The locked split is never evaluated by ordinary benchmark commands.
- The user must review required cases and supply corrections/approvals before Stage B.
- Exact grade balance is not a permanent invariant; human review may change it.
- The known unrelated DOCX HTTP 503 constraint remains unchanged.

## Prerequisites

- Branch: `feature/jobs-scoring-benchmark`, created from the newest `main` after `feature/job-discovery-hardening` is merged.
- Read `docs/ARCHITECTURE.md`, `docs/RESUME_DECISION_ENGINE.md`, the approved Jobs design, and the repository's current job-discovery tests.
- Preserve the supplied focused baseline of 206 passed and one unrelated warning as the pre-change comparison.

## Files

Create:

- `tests/job_discovery/benchmark/__init__.py` — package marker.
- `tests/job_discovery/benchmark/models.py` — Pydantic benchmark input/output models.
- `tests/job_discovery/benchmark/loader.py` — split checksums and locked-access guard.
- `tests/job_discovery/benchmark/metrics.py` — grade, eligibility, ranking, precision, and traceability metrics.
- `tests/job_discovery/benchmark/report.py` — review HTML and baseline-report CLI.
- `tests/job_discovery/benchmark/test_dataset_contract.py` — counts, identities, quotas, and leakage checks.
- `tests/job_discovery/benchmark/test_metrics.py` — metric behavior on miniature cases.
- `tests/job_discovery/benchmark/test_current_production_baseline.py` — current-policy comparison only.
- `tests/fixtures/job_discovery/benchmark/manifest.json` — version, split IDs, checksums, approval status.
- `tests/fixtures/job_discovery/benchmark/calibration.json` — exactly 60 cases.
- `tests/fixtures/job_discovery/benchmark/validation.json` — exactly 20 cases.
- `tests/fixtures/job_discovery/benchmark/locked.json` — exactly 20 cases; loaded only under explicit gate authorization.
- `docs/job-discovery/BENCHMARK.md` — rubric, review protocol, and baseline results.

Modify:

- `pyproject.toml` — only to register `job_discovery_locked` if the existing marker list lacks it.

Generated and ignored:

- `generated/job-discovery/benchmark-review.html`
- `generated/job-discovery/current-baseline.html`
- `generated/job-discovery/current-baseline.json`

No production source, test outside benchmark tooling, configuration, dependency, or fixture file may be modified.

## Interfaces

```python
class BenchmarkCase(BaseModel):
    case_id: str
    scenario_id: str
    split: Literal["calibration", "validation", "locked"]
    profile: dict[str, object]
    preferences: dict[str, object]
    posting: dict[str, object]
    expected_eligibility: str
    proposed_grade: str
    proposed_provisional: bool
    critical_requirements: list[str]
    important_evidence: list[str]
    important_gaps: list[str]
    proposed_reasons: list[str]
    rationale: str
    proposal_confidence: Literal["high", "medium", "low"]
    review_tags: list[str]

def load_development_cases() -> list[BenchmarkCase]: ...
def load_locked_cases(*, authorized: bool) -> list[BenchmarkCase]: ...
def render_review_artifact(cases: list[BenchmarkCase], output: Path) -> None: ...
```

## Task 1: Define schemas and split isolation

**Files:** `models.py`, `loader.py`, `test_dataset_contract.py`, `manifest.json`.

**Interfaces:** Produces `BenchmarkCase`, `load_development_cases()`, and guarded `load_locked_cases()` for later plans.

- [ ] Write a failing test requiring split names, unique case IDs, scenario IDs, review fields, and refusal to load locked expectations without an explicit authorization value.
- [ ] Run:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q tests/job_discovery/benchmark/test_dataset_contract.py
```

Expected failure: missing benchmark modules or missing split guard.

- [ ] Implement the Pydantic boundary models and checksum-aware loader.
- [ ] Run the same command.

Expected passing behavior: development loading returns only calibration and validation; unauthorized locked loading raises a typed error.

- [ ] Commit independently on `feature/jobs-scoring-benchmark`: `test(jobs): define isolated benchmark contracts`.

## Task 2: Curate the 100 proposed cases

**Files:** `calibration.json`, `validation.json`, `locked.json`, `manifest.json`, `test_dataset_contract.py`.

**Interfaces:** Produces exactly 60/20/20 split membership and immutable case/scenario IDs.

The initial proposal should be approximately grade-balanced, but the permanent invariants are only:

- exactly 60 calibration cases;
- exactly 20 validation cases;
- exactly 20 locked-test cases;
- permanent split membership;
- meaningful representation of Excellent, Good, Weak, and Don't Match;
- hard-negative, false-positive, and boundary coverage;
- no cross-split duplicate or near-duplicate scenario leakage.

Required coverage includes hard eligibility conflicts, uncertain eligibility, keyword overlap, misleading titles, company-sector traps, critical gaps, preferred-only evidence, transferable evidence, level distance, degree alternatives, posting-age boundaries, incomplete descriptions, duplicate identities, and provider-order cases.

- [ ] Write failing count, split, scenario, and leakage assertions.
- [ ] Run the focused contract command; expected failure identifies absent cases.
- [ ] Create only benchmark JSON cases with synthetic/deidentified content.
- [ ] Re-run; expected pass is exactly 100 cases with the required distribution and no leakage.
- [ ] Commit: `test(jobs): curate discovery benchmark proposal`.

## Task 3: Implement metrics

**Files:** `metrics.py`, `test_metrics.py`.

**Interfaces:** Produces exact grade agreement, exact-or-adjacent agreement, eligibility agreement, pairwise ranking accuracy, top-five precision, traceability, hard-ineligible leakage, critical-gap leakage, and determinism metrics.

Define grade adjacency as Excellent → Good → Weak → Don't Match. Define top-five precision using human `apply_worthy` labels in ten-job grouped Tailored scenarios. Define pairwise accuracy only over annotated non-tied pairs and report both scenario macro-average and pair micro-average.

- [ ] Write miniature metric tests with hand-calculated expected values.
- [ ] Run:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q tests/job_discovery/benchmark/test_metrics.py
```

Expected failure: metric functions do not exist.

- [ ] Implement deterministic metric functions with canonical JSON ordering.
- [ ] Re-run; expected pass is exact hand-calculated agreement.
- [ ] Commit: `test(jobs): define benchmark quality metrics`.

## Task 4: Stage A — proposed review artifact and preliminary comparison

**Files:** `report.py`, `test_current_production_baseline.py`, `docs/job-discovery/BENCHMARK.md`.

**Interfaces:** Produces a readable artifact and preliminary comparisons without approving or freezing labels.

- [ ] Write a failing report test requiring posting summary, profile evidence references, proposed labels, rationales, confidence, review tags, and correction fields.
- [ ] Run the report test; expected failure is a missing renderer or incomplete artifact fields.
- [ ] Implement:

```powershell
& ".\.venv\Scripts\python.exe" -m tests.job_discovery.benchmark.report `
  --mode review `
  --output generated/job-discovery/benchmark-review.html
```

- [ ] Generate a preliminary current-production comparison for calibration and validation only:

```powershell
& ".\.venv\Scripts\python.exe" -m tests.job_discovery.benchmark.report `
  --mode current-baseline `
  --splits calibration validation `
  --output generated/job-discovery/current-baseline.html
```

Expected passing behavior: artifacts show proposed labels and current-policy comparisons, explicitly marked preliminary. No checksum is frozen, no approval status is set, and the locked split is not evaluated.

- [ ] Stop and deliver the review artifact to the user. Do not continue to Stage B in the same execution turn.

## Human review pause

The user reviews every proposed Excellent case, uncertain case, hard-eligibility case, keyword-overlap Don't Match case, and the stratified representative sample. The user supplies corrections and approvals. No proposed label becomes approved ground truth without this pause.

## Task 5: Stage B — apply corrections and freeze approved ground truth

**Files:** `calibration.json`, `validation.json`, `locked.json`, `manifest.json`, `BENCHMARK.md`, `test_dataset_contract.py`.

**Interfaces:** Produces the approved benchmark version, frozen split membership, and authoritative calibration/validation baseline. It deliberately does not evaluate the locked split.

- [ ] Write a failing test requiring approved status, nonempty reviewer record, checksums, and unchanged split membership.
- [ ] Apply the user's reviewed corrections and approval metadata.
- [ ] Run:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q tests/job_discovery/benchmark/test_dataset_contract.py
& ".\.venv\Scripts\python.exe" -m tests.job_discovery.benchmark.report `
  --mode authoritative-baseline `
  --splits calibration validation `
  --output generated/job-discovery/current-baseline.html
```

Expected passing behavior: approved version and checksums are recorded; authoritative baseline covers only calibration and validation; locked expectations remain unopened.

- [ ] Commit: `docs(jobs): freeze reviewed benchmark baseline`.

## Acceptance criteria

- Exactly 60 calibration, 20 validation, and 20 locked cases.
- Permanent split membership and no cross-split near-duplicate leakage.
- Human corrections are represented in approved ground truth.
- Stage A visibly stops before labels freeze.
- Stage B is impossible without recorded human review approval.
- Locked split is not evaluated in either stage.
- No production scoring, configuration, dependency, or unrelated test changes.

## Recommended branch and independently reviewable boundaries

Recommended branch: `feature/jobs-scoring-benchmark`, created from newest `main` after roadmap merge. Safe commits are the five commits listed above. Do not begin Plan 2 until Stage B approval is complete.

## Known unrelated DOCX constraint

If the later full suite reports only `tests/test_health.py::test_api_plan_and_document_use_reconciled_composition` as HTTP 503 because no exact DOCX page-count provider exists, report it unchanged. Do not modify health, rendering, DOCX generation, or that test.

