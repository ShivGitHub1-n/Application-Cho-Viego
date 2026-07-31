# Resume Tailor

Resume Tailor is an evidence-backed AI platform for tailoring resumes to specific roles. It treats a resume as a constrained, one-page strategy problem: select the strongest supported evidence, allocate document space deliberately, and explain every meaningful decision.

## Status

Canonical convergence stage. The accepted resume pipeline, autonomous
first-party job discovery, responsive Streamlit UI, and bounded
evidence-grounded cover-letter workflow are integrated. Cover-letter prose and
cross-role ranking remain under product review. The repository also includes
managed DOCX/PDF rendering, optional Gemini structured-output assistance,
FastAPI endpoints, and focused regression tests.

## Current project status

- [Project status and accepted-versus-experimental boundaries](docs/PROJECT_STATUS.md)
- [Ordered roadmap and acceptance gates](docs/ROADMAP.md)
- [Evidence-grounded cover-letter workflow](docs/COVER_LETTER_WORKFLOW.md)
- [Codex operating guide](docs/CODEX_OPERATING_GUIDE.md)

## Quick start

1. Install Python 3.11 or newer.
2. Create and activate a virtual environment.
3. Install dependencies and this checkout: `pip install -r requirements-dev.txt`, then
   `python -m pip install -e .`. This prevents another editable checkout from
   supplying the `resume_tailor` package at runtime.
4. Copy `.env.example` to `.env`, set `GEMINI_API_KEY` and `GEMINI_MODEL` to enable the production Gemini writer, or keep deterministic fallback enabled. The default resume route disables semantic opportunity/composition calls, uses one batched writer request with at most one malformed-output repair, and never calls Gemini during page fit or download. Validated Gemini role classification is separately opt-in with `LLM_ENABLE_ROLE_CLASSIFICATION=true`; it is disabled by default.
5. Run the API: `python -m uvicorn resume_tailor.api.main:app --reload --app-dir src`
6. Run the UI in another terminal: `python -m streamlit run src/resume_tailor/frontend/app.py`

The API health check is available at `http://localhost:8000/health`. Use `POST /optimization-plans` with a reviewed profile and a job posting to obtain a strategy and decision report.

`gemini-3.1-*` models require `google-genai>=2.1`; the dependency constraint
enforces that boundary. To isolate model/SDK/API compatibility from the resume
schema, run the manual-only, one-request structured-output canary after loading
the local `.env`:

```powershell
$env:PYTHONPATH=(Resolve-Path .\src).Path
python manual-test\run_gemini_structured_output_canary.py
```

The default canary sends no profile or resume evidence. It uses the configured
model, 30-second client timeout, one SDK attempt, and `application/json`.
Normal resume generation never invokes it. The production writer now uses a
separate shallow provider contract and reconstructs the rich internal response
locally. Run its one-request neutral-evidence canary with:

```powershell
python manual-test\run_gemini_structured_output_canary.py --mode minimal-production-writer
```

Only run the full Streamlit route after this mode reports a candidate, response
text, parsed JSON, a valid provider contract, successful evidence-ID mapping,
an internal variant, and completed grounding validation. The historical
`production-schema-only` and `production-config-only` modes remain available
for manual request-axis isolation; none of the canaries run automatically.
The writer canary uses synthetic evidence only, so its report intentionally
includes the exact synthetic source, generated rewrite, reconstructed claims,
supporting IDs, and typed grounding rejections. Production profile and prompt
contents remain excluded from diagnostics.

User profiles and Job Search state default to
`%LOCALAPPDATA%\Application Viego` on Windows, independently of the current
clone or worktree. Set `APPLICATION_VIEGO_DATA_DIR` for a portable location or
tests. See [Application data](docs/APPLICATION_DATA.md).

## Job discovery

The job-discovery MVP uses only explicitly approved Greenhouse or Lever
sources. Production defaults to an empty registry, so the UI displays
`No approved job sources are configured` until a registry is configured.
Unsupported sources are not scraped.

Configure the registry with the `JOB_DISCOVERY_SOURCE_REGISTRY_PATH` setting,
for example in `.env`:

```text
JOB_DISCOVERY_SOURCE_REGISTRY_PATH=config/approved-job-sources.json
```

The file is a JSON list (or an object containing a `sources` list). Each
enabled entry must provide a unique `source_id`, `connector_type`
(`greenhouse` or `lever`), `company_name`, approved `board_token`,
`official_base_url`, and `enabled: true`. Lever entries must also provide
`lever_api_region` (`global` or `eu`); Greenhouse entries must set it to
`null`. The registry accepts only the supported provider configuration and
the application uses bounded source timeouts and pagination from settings. Do
not place secrets in the registry.

Offline tests use recorded source fixtures and never make live source
requests. Run them with:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q `
  -m "not gemini_integration and not job_source_integration"
```

The live smoke test is separate, marker-gated, and requires explicit approved
registry configuration. Invoke it manually with:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q `
  -m job_source_integration `
  tests/integration/job_sources/test_live_smoke.py
```

With no configured sources it reports a clear skip; it never treats an
unconfigured empty result as successful discovery. The smoke test performs
only a bounded fetch against the explicitly configured source and does not log
raw payloads or secrets.

Batch 3 adds separate Tailored and Explore feed contracts. Tailored uses the
reviewed profile and confirmed preferences locally; Explore uses approved
sectors and sanitized retrieval controls. Provider requests are explicit
allow-lists and never include profile/resume text, evidence, scores, or
explanations. Retrieval is paged and bounded, records partial source success,
retains provenance and excluded evaluations, and persists one feed refresh
atomically. Legacy recommendations remain readable as earlier-policy results;
saved posting snapshots remain immutable. The development-gate-approved
policy is not locked-release-certified, and the dedicated Jobs UI is owned by
Batch 4.

## Documentation

The canonical resume pipeline and closeout contract is
[docs/RESUME_ENGINE_CLOSEOUT.md](docs/RESUME_ENGINE_CLOSEOUT.md). See
[docs/RESUME_DECISION_ENGINE.md](docs/RESUME_DECISION_ENGINE.md) for the
decision policy, [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for boundaries,
and [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md) for deferred work.

- [Project status](docs/PROJECT_STATUS.md)
- [Roadmap](docs/ROADMAP.md)
- [Codex operating guide](docs/CODEX_OPERATING_GUIDE.md)
- [Product specification](docs/PRODUCT_SPEC.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Decision engine](docs/RESUME_DECISION_ENGINE.md)
- [Optimization-engine design](docs/RESUME_OPTIMIZATION_ENGINE.md)
- [Master profile](docs/MASTER_PROFILE.md)
- [Template engine](docs/TEMPLATE_ENGINE.md)
- [Template V1 contract](docs/TEMPLATE_V1.md)
- [Application data](docs/APPLICATION_DATA.md)
- [Known issues and frozen layout scope](docs/KNOWN_ISSUES.md)
- [AI guidelines](docs/AI_GUIDELINES.md)
- [Validated role classification](docs/ROLE_CLASSIFICATION.md)
- [Contributing](docs/CONTRIBUTING.md)

Batch 3.5 adds the approved static-first Rocket Lab first-party path with
bounded employer index/detail retrieval, JSON-LD plus constrained HTML
extraction, and terminal-only Greenhouse application provenance. Runtime
observations use schema version 3; the registry remains the sole source-plan
authority. Source operations are CLI-only and safe read-only visibility is
available at `GET /job-discovery/sources` and
`GET /job-discovery/sources/{source_id}/health`.

```powershell
python -m resume_tailor.cli.job_sources --format json refresh --dry-run
python -m resume_tailor.cli.job_sources --format json health
```

Browser fallback is an explicit optional capability. It is never installed,
downloaded, or launched during import, startup, CLI parsing, or ordinary
tests. Playwright is a direct dependency, while browser binaries remain a
separate machine setup step:

```powershell
& ".\.venv\Scripts\python.exe" -m playwright install chromium
```

The adapter prefers Playwright-managed Chromium and otherwise locates only a
trusted system Chrome/Edge executable; registry configuration cannot provide
an executable path or launch arguments. Browser requests remain allowlisted
and bounded, with isolated contexts, no credentials or persistence, and a
documented browser DNS TOCTOU residual risk. The verified local browser path
uses Playwright 1.55.0 with managed Chromium 140.0.7339.16 (build v1187); the
controlled local integration test passed three tests, including JavaScript-
rendered listing and detail extraction. Browser binaries remain a separate
explicit setup step and startup never installs or launches a browser.

Source refresh uses the existing normalization, frozen evaluation, feed, alias,
and transactional SQLite persistence pipeline. Robots policy is composed once
per first-party source and enforced before static content fetches or browser
launch. Lifecycle state records compiled audit, registry-plan, and extraction-
profile hashes plus next eligibility. A global run deadline prevents new source
starts after expiry. Browser action limits count actual attempts, and `--force`
only bypasses cadence; it never bypasses source or security policy.
