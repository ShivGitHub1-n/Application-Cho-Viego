# Jobs Batch 5 Validation Report

Date: 2026-08-01
Branch: `fix/jobs-final-hardening`
Starting HEAD: `740aefa1c83ae8f9c47be4ceac8accc29644a6c0`

## Scope and status

Batch 5 is a verification and narrow-defect-remediation pass. No new Jobs
product feature or production defect fix was required. The Batch 5 changes
add offline integration, determinism, and snapshot/migration coverage only.
Tailored and Explore ordering, fit grades, eligibility, provisional state,
excluded visibility, saved snapshots, API ownership, and tailoring handoff
remain backend/application contracts.

This report records verification performed during Batch 5. It does not claim
locked-release certification.

## Tests run during Batch 5

| Command/scope | Result |
| --- | --- |
| `tests/integration/job_discovery/test_jobs_end_to_end.py` | 4 passed |
| `tests/job_discovery/test_determinism_matrix.py` | 4 passed |
| Domain/application suites plus determinism matrix, `PYTHONHASHSEED=1` | 209 passed |
| Domain/application suites plus determinism matrix, `PYTHONHASHSEED=2` | 209 passed |
| Domain/application suites plus determinism matrix, `PYTHONHASHSEED=777` | 209 passed |
| Domain/application suites plus determinism matrix, `PYTHONHASHSEED=99991` | 209 passed |
| `tests/job_discovery/test_saved_snapshot_compatibility.py` | 4 passed |
| Explicit source/API/migration/security allowlist excluding Playwright runtime test | 180 passed, 1 warning |
| Streamlit Jobs tests | 38 passed |

The complete affected Jobs command and final verification results are recorded
after the final test run below.

## Final explicit verification

- Complete affected Jobs allowlist, including the real Playwright integration:
  437 passed, 1 known sandbox-only `WinError 5` failure, and 1 expected
  HTTPX deprecation warning.
- Broader explicit offline allowlist with the Playwright runtime test omitted:
  435 passed and 1 expected HTTPX deprecation warning.
- Migration compatibility command covering snapshot compatibility, v1/v2/v3
  migrations, and SQLite persistence: 25 passed.
- `compileall -q src`: passed.
- Explicit Batch 5 test-file compilation: passed.
- Imports for application composition, API, production Jobs Streamlit modules,
  and the offline harness: passed, with expected bare-Streamlit warnings.
- Ruff on the three Batch 5 test files: passed.
- Ruff on the affected production scope: one pre-existing untouched import
  ordering finding in `application/job_discovery/presentation.py`; no Batch 5
  production file was modified.
- Strict mypy on the explicit Jobs production scope: 28 pre-existing errors in
  `domain/job_discovery/evidence.py`, `domain/job_discovery/scoring.py`, and
  the Greenhouse/Lever adapters; no Batch 5 production file was modified.

## Remediation verification

The independent-review remediation added deterministic permutation coverage,
real schema-v1/v2 repository reads, and a composed refresh/API/presentation
flow. The remediation verification produced:

- The three remediation files together: 16 passed and 1 expected HTTPX
  deprecation warning.
- Domain/application suites plus the determinism matrix: 212 passed for each
  of `PYTHONHASHSEED=1`, `2`, `777`, and `99991`.
- Snapshot compatibility plus SQLite persistence: 21 passed.
- API plus Streamlit Jobs tests: 50 passed and 1 expected HTTPX deprecation
  warning.
- The complete affected Jobs allowlist: 430 passed, 1 known sandbox-only
  Playwright `WinError 5` failure, and 1 expected HTTPX deprecation warning.
- Changed-test and changed-query Ruff checks passed. Strict mypy remains at
  the documented 28 pre-existing errors.

## Historical approved results

The Batch 4 retrospective records the user-accepted populated harness and real
application checks, including card selection, keyboard interaction, dark/light
styles, responsive behavior, all Jobs sections, saved jobs, official links,
and safe Tailor resume routing. Those are historical user evidence, not new
Batch 5 browser evidence.

## Environment-only conditions

The real Playwright browser integration test remains unavailable in this
environment because the sandbox raises `WinError 5` before Chromium starts.
The expected Streamlit/HTTPX deprecation warning is non-functional. No
unexplained Jobs test failure was observed.

Exact DOCX health may return HTTP 503 when exact page-count tooling is
unavailable. This is a known environment-only condition outside Jobs final
hardening scope. Batch 5 did not modify DOCX rendering, health behavior,
resume generation, or the related test; the condition was not concealed or
converted into a passing result, and no DOCX test is included in the affected
Jobs allowlist above.

## Benchmark disclosure

No locked benchmark command was run during Batch 5, and no benchmark contents
were intentionally inspected, searched, opened, summarized, modified, or used.
The following three incidents remain disclosed accurately:

1. A historical broad test command accidentally collected the locked benchmark
   gate once.
2. A later broad `rg` diagnostic surfaced benchmark fixture lines.
3. During the first Batch 5 attempt, an inventory command listed paths beneath
   `tests/job_discovery/benchmark`. Only path names were listed; no benchmark
   file contents were opened; no cases, labels, metrics, expected outputs, or
   artifacts were read; no benchmark test was run; no benchmark information was
   used; the run stopped immediately; no files were modified; and no commits
   were created.

After that safe stop, the benchmark directory was not accessed again. Batch 5
does not claim a new locked-release result or certification.

## Remaining risks

- Visual browser behavior remains covered by the previously accepted Batch 4
  manual evidence and should be rechecked by the user if frontend code changes
  later.
- The sandbox cannot provide new Playwright evidence.
- Exact DOCX health/page-count behavior remains outside Batch 5 scope.
- The frozen Jobs policy remains development-gate-approved and not
  locked-release-certified.
