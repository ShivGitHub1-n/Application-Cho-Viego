# Jobs Scoring Redesign and Calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Use superpowers:verification-before-completion before reporting completion.

**Goal:** Replace the current additive scorer with an evidence-authoritative evaluator that is calibrated on the approved benchmark and gated on validation before the user-authorized locked test.

**Architecture:** Eligibility and role relevance are explicit gates; requirement extraction produces critical/required/preferred facts; a contribution ledger prevents evidence reuse; grading and provisional status are independent; explanations contain typed evidence references. Plan 2 may add compatibility adapters and policy-version metadata, but permanent recommendation/feed persistence migration is owned atomically by Plan 3.

**Tech Stack:** Python 3.11+, Pydantic 2, deterministic domain services, pytest, standard-library hashing, and the benchmark tooling from Plan 1.

## Global Constraints

- Use only the reviewed profile after retrieval; providers receive sanitized retrieval fields only.
- Numeric component and total scores remain internal to diagnostics.
- Fit grades are Excellent, Good, Weak, and Don't Match; Provisional is independent.
- Unknown eligibility is visible and cannot silently become confirmed eligibility.
- Interests and preferred companies never provide substantive qualification points or raise a grade.
- Every positive reason and material gap must be traceable to typed evidence references.
- The known unrelated DOCX HTTP 503 constraint remains unchanged.
- No permanent recommendation/feed schema migration occurs in this plan.

## Prerequisites

- Branch: `feature/jobs-scoring-redesign`, created from the newest `main` after `feature/jobs-scoring-benchmark` is reviewed and merged.
- Plan 1 Stage B must have approved calibration and validation ground truth.
- Read `docs/job-discovery/BENCHMARK.md`, current `domain/job_discovery/scoring.py`, `requirements.py`, `eligibility.py`, and focused tests.

## Files

Create:

- `src/resume_tailor/domain/job_discovery/evidence.py` — evidence quality, requirement matching, and single-use contribution ledger.
- `src/resume_tailor/domain/job_discovery/grading.py` — grade thresholds, caps, penalties, and policy version.
- `src/resume_tailor/domain/job_discovery/evaluation.py` — ordered pure evaluation pipeline.
- `src/resume_tailor/domain/job_discovery/explanations.py` — typed reasons, gaps, and unresolved facts.
- `src/resume_tailor/domain/job_discovery/ranking.py` — deterministic fit ordering independent of providers.
- `tests/domain/job_discovery/test_evidence_matching.py`
- `tests/domain/job_discovery/test_grading.py`
- `tests/domain/job_discovery/test_evaluation.py`
- `tests/domain/job_discovery/test_explanations.py`
- `tests/domain/job_discovery/test_ranking.py`
- `tests/job_discovery/benchmark/test_calibration_acceptance.py`
- `tests/job_discovery/benchmark/test_validation_acceptance.py`
- `tests/job_discovery/benchmark/test_locked_gate.py`
- `docs/job-discovery/SCORING.md`

Modify:

- `src/resume_tailor/domain/job_discovery/models.py`
- `src/resume_tailor/domain/job_discovery/capabilities.py`
- `src/resume_tailor/domain/job_discovery/requirements.py`
- `src/resume_tailor/domain/job_discovery/role_signals.py`
- `src/resume_tailor/domain/job_discovery/eligibility.py`
- `src/resume_tailor/domain/job_discovery/scoring.py` — compatibility façade during transition.
- `src/resume_tailor/application/job_discovery/refresh.py`
- Focused Jobs domain/application tests.
- `docs/ARCHITECTURE.md`, `docs/AI_GUIDELINES.md`, and `docs/PRODUCT_SPEC.md`.

## Interfaces

```python
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

class JobEvaluator(Protocol):
    def evaluate(
        self,
        job: DiscoveredJob,
        preferences: JobSearchPreferences,
        profile_index: ProfileCapabilityIndex,
        *,
        as_of: datetime,
    ) -> JobEvaluation: ...
```

`JobEvaluation` contains eligibility, role relevance, requirement matches, fit grade, internal diagnostics, independent provisional status, typed reasons, typed gaps, unresolved facts, and `evaluation_policy_version`.

## Task 1: Evaluation contracts and compatibility metadata

**Interfaces:** Produces `FitGrade`, criticality, evidence quality, typed references, `JobEvaluation`, and policy-version fields consumed by all later tasks.

- [ ] Write failing Pydantic/domain tests for grade values, independent provisional status, typed references, and policy version.
- [ ] Run:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q tests/domain/job_discovery/test_grading.py
```

Expected failure: missing models and imports.

- [ ] Implement the minimal typed models and a compatibility mapping for legacy Strong/Good/Stretch/Provisional labels. The adapter must mark historical results as earlier-policy results rather than current-policy evaluations.
- [ ] Re-run; expected pass with round-trip validation.
- [ ] Commit: `feat(jobs): define fit evaluation authority`.

## Task 2: Eligibility facts and role relevance

**Interfaces:** Produces explicit `EligibilityAssessment`, `RoleRelevanceAssessment`, and unresolved-fact records consumed by `JobEvaluator`.

- [ ] Write failing tests for authorization token boundaries, degree hierarchy, equivalent experience, graduation wording, level distance, title/responsibility conflict, incidental product prose, and employer-sector traps.
- [ ] Run:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q `
  tests/domain/job_discovery/test_eligibility.py `
  tests/domain/job_discovery/test_role_signals.py `
  tests/domain/job_discovery/test_requirement_extraction.py
```

Expected failure: current substring, all-or-nothing level, and role-mismatch behavior violates the assertions.

- [ ] Implement structural eligibility fact extraction, responsibility-weighted role relevance, and explicit unknown facts. A known hard conflict produces `Don't Match`; an unresolved fact remains unknown.
- [ ] Re-run; expected pass with no silent eligibility coercion.
- [ ] Commit: `fix(jobs): establish eligibility and relevance authority`.

## Task 3: Requirement criticality and evidence ledger

**Interfaces:** Produces one canonical requirement cluster per substantive requirement and a ledger that allocates each evidence ID at most once at full strength.

- [ ] Write failing tests proving that one demonstrated Python fact cannot earn both technical and required-coverage credit, an incidental keyword earns no evidence credit, a reviewed skill is not demonstrated experience, and preferred evidence cannot outweigh a missing critical requirement.
- [ ] Run:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q tests/domain/job_discovery/test_evidence_matching.py
```

Expected failure: current scorer returns overlapping positive components.

- [ ] Implement alias clustering, requirement source spans, criticality, evidence hierarchy, and single-use allocation.
- [ ] Re-run; expected pass with traceable allocations.
- [ ] Commit: `feat(jobs): prevent evidence double counting`.

## Task 4: Grades, caps, penalties, and explanations

**Interfaces:** Produces a substantive `FitGrade`, independent `ProvisionalAssessment`, grade-cap records, and explanation objects.

- [ ] Write failing tests for missing critical requirements, severe level mismatch, role irrelevance, insufficient description, unknown eligibility, interest-only matches, preferred-company-only matches, and accurate reason/gap references.
- [ ] Run:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q `
  tests/domain/job_discovery/test_grading.py `
  tests/domain/job_discovery/test_evaluation.py `
  tests/domain/job_discovery/test_explanations.py
```

Expected failure: current labels are score-only and Provisional replaces substantive fit.

- [ ] Implement monotone grade rules. Candidate parameter values may change only through calibration evidence; invariant caps remain mandatory.
- [ ] Re-run; expected pass with every reason linked to posting/profile/preference authority and every material gap linked to a requirement.
- [ ] Commit: `feat(jobs): add evidence-grounded grades and explanations`.

## Task 5: Deterministic ranking and refresh integration

**Interfaces:** Produces provider-independent deterministic ranking and makes refresh retain all evaluations for Plan 3 to persist atomically.

- [ ] Write failing tests for shuffled jobs, shuffled requirements, source-order permutations, and `PYTHONHASHSEED` values.
- [ ] Run:

```powershell
foreach ($seed in 1, 2, 777) {
  $env:PYTHONHASHSEED = "$seed"
  & ".\.venv\Scripts\python.exe" -m pytest -q `
    tests/domain/job_discovery/test_ranking.py `
    tests/application/job_discovery/test_refresh.py
}
Remove-Item Env:PYTHONHASHSEED
```

Expected failure: unstable or incomplete evaluation output.

- [ ] Integrate `JobEvaluator` into refresh after structural eligibility/relevance and before feed persistence. Keep `scoring.py` import-compatible until Plan 3 replaces recommendation persistence.
- [ ] Re-run; expected pass with source-order-independent evaluations.
- [ ] Commit: `refactor(jobs): route refresh through graded evaluation`.

## Task 6: Calibration and validation gate

**Interfaces:** Consumes approved benchmark splits and produces a frozen scoring-policy version plus acceptance report.

- [ ] Write failing acceptance assertions for every target metric.
- [ ] Run:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q tests/job_discovery/benchmark/test_calibration_acceptance.py
```

Expected failure: the initial policy misses one or more calibrated cases.

- [ ] Iterate only on calibration cases. Each policy change must cite a calibration case and add a focused regression test.
- [ ] Run validation only after calibration closes:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q tests/job_discovery/benchmark/test_validation_acceptance.py
```

Expected pass: at least 85% exact, at least 95% exact-or-adjacent, at least 85% pairwise ranking, at least 80% Tailored top-five precision, zero hard-ineligible normal-feed leakage, zero critical-gap Excellent grades, full traceability, and determinism.

- [ ] Record policy version, counts, confusion matrices, and limitations in `docs/job-discovery/SCORING.md`.
- [ ] Commit: `feat(jobs): calibrate and validate fit grading`.

## Task 7: User-authorized locked gate

The first locked execution requires explicit user authorization. The worker must stop before running it and request that authorization. Do not infer authorization from branch state, prior review, or the existence of the command.

After authorization:

```powershell
$env:JOB_DISCOVERY_LOCKED_GATE = "1"
& ".\.venv\Scripts\python.exe" -m pytest -q `
  -m job_discovery_locked `
  tests/job_discovery/benchmark/test_locked_gate.py
Remove-Item Env:JOB_DISCOVERY_LOCKED_GATE
```

If it fails, freeze the aggregate report, diagnose only failure classes, create independent calibration regressions, re-run calibration and validation, and obtain authorization for the next locked execution. A second failure blocks release unless the user approves blind locked-set replenishment.

## Acceptance criteria

- Criticality, evidence quality, role relevance, eligibility, grade, and provisional status are separate typed authorities.
- No double counting, interest-only grade increase, preferred-company grade increase, or substring-only positive match.
- Validation targets pass before locked execution.
- Locked execution occurs only after user authorization.
- Historical policy versions remain readable and labeled.
- No permanent recommendation/feed persistence migration occurs in Plan 2.

## Recommended branch and commit boundaries

Recommended branch: `feature/jobs-scoring-redesign`, created from newest `main` after Plan 1 merges. Tasks 1–6 are independently reviewable commits. Task 7 is a separately reviewed gate commit and must not be run without authorization.

## Known unrelated DOCX constraint

The unrelated health test may return HTTP 503 without an exact page-count provider. Report it without changing health, rendering, DOCX generation, or the test.

