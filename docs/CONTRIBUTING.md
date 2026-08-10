# Contributing

## Standards

- Python 3.11+, type annotations, Pydantic models at boundaries, and small testable services.
- Format and lint with Ruff; run targeted pytest tests before broader validation.
- Keep domain logic vendor-neutral and inject dependencies through constructors or FastAPI dependencies.
- Add tests alongside behavior changes and update focused documentation for contract changes.

## Organization

- Add business concepts in `domain`.
- Add orchestration use cases in `application`.
- Add external interfaces in `ports` and their implementations in `infrastructure`.
- Keep request/response mapping in `api` and visual state in `frontend`.

## Git workflow

Use small, focused branches and pull requests. Keep commits cohesive and describe user-visible behavior. Do not mix refactors with feature changes unless required for the feature.

## Codex development workflow

Codex work in this repository is performed inline: no subagents, delegated
agents, parallel agents, or background agents. Codex must not write Git state
or change branches. The user performs staging, commits, pushes, merges, and
branch changes manually. A deliberately dirty worktree is valid during an
uncommitted batch and must not be cleaned by resetting or restoring files.

Every task begins with a read-only check of the branch, HEAD, status, diff
summary, changed-file list, and whitespace. Use the repository environment
`..\\.venv\\Scripts\\python.exe`, rather than an implicit Python installation.
Preserve unrelated changes and explicitly exclude `tests/job_discovery/benchmark`
from test and search commands.

Use strict red-green-refactor for bugs and new behavior: read the complete
error or browser evidence; reproduce it; trace state, data, DOM, or control
flow; identify the root cause; add a failing regression test; implement the
smallest fix; run focused and affected tests; and manually validate visual or
interactive changes in a browser. Broad prompts are appropriate for coherent
batches; narrow bugs require focused debugging prompts. Return exact commands
and exact results. Screenshots and real browser behavior override optimistic
reports and CSS-string tests.

## Acceptance and release gates

The normal sequence is focused tests, Streamlit AppTest interactions, the
affected Jobs suite, the broad offline suite, populated harness browser checks,
real-application browser checks, an independent review-only pass, and a manual
smoke test after any review remediation. Commit and PR work starts only after
the user receives an APPROVED review. Keep one canonical roadmap/status
document and one canonical handoff per major batch.

Known environment failures are documented rather than hidden: Playwright may
fail in the Codex sandbox with WinError 5 before Chromium launches, and exact
DOCX health may return HTTP 503 when exact page-count tooling is unavailable.

## Jobs validation commands

Use the explicit repository environment and exclude the locked benchmark from
affected-suite commands:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q tests/test_jobs_page_streamlit.py tests/test_jobs_app_streamlit.py
& ".\.venv\Scripts\python.exe" -m pytest -q tests --ignore=tests/job_discovery/benchmark
& ".\.venv\Scripts\python.exe" -m pytest -q -m "not gemini_integration and not job_source_integration" --ignore=tests/job_discovery/benchmark
```

Acceptance layers are: focused unit/structural tests; Streamlit AppTest
interactions; the affected Jobs suite; the broad offline suite; populated
offline-harness browser validation; real-application browser validation;
independent review-only pass; and manual smoke testing after review
remediation. Commit and PR work begins only after approval.

