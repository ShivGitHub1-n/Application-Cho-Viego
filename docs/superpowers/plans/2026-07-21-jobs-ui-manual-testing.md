# Jobs UI and Manual Testing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Use superpowers:verification-before-completion before reporting completion.

**Goal:** Build a dedicated Jobs experience with four sections, split-panel selection, simplified preferences, explicit excluded-result expansion, application-boundary actions, and repeatable browser checkpoints.

**Architecture:** The existing Streamlit entry point gains minimal navigation and stops before the unrelated resume page when Jobs is selected. A typed application façade supplies profile, feed, detail, save, availability, and tailoring-handoff operations; frontend modules contain only layout and session state.

**Tech Stack:** Streamlit, Streamlit `AppTest`, Pydantic DTOs, existing FastAPI/application services, and a deterministic manual browser harness using approved offline scenarios.

## Global Constraints

- Normal UI shows grade, eligibility, matches, exact supporting evidence, material gaps, unknowns, and provisional status; numeric scores remain diagnostics-only.
- Sections are Tailored for you, Explore sectors, Saved, and Preferences.
- Tailored ranks by fit; Explore ranks newest to oldest with fit as a tie-breaker only.
- Don't Match results are not rendered until the user deliberately expands `Show excluded jobs (N)`.
- Initial sectors are Software Engineering, Data Engineering, AI / Machine Learning, Computer Vision, Robotics / Autonomous Systems, Embedded Systems / Firmware, Hardware / Systems Integration, Controls / Mechatronics, and Testing / Verification.
- Unknown eligibility may appear without a hard conflict, is visibly labeled, ranks after known-eligible jobs within an equal Tailored grade, and lists every unresolved fact.
- Tailor for this job prepares existing tailoring input and switches workflows; it does not generate documents or alter Gemini, composition, or DOCX behavior.
- Do not redesign unrelated resume UI.
- The known unrelated DOCX HTTP 503 constraint remains unchanged.

## Prerequisites

- Branch: `feature/jobs-ui`, created from newest `main` after `feature/jobs-query-feeds-providers` merges.
- Plans 1–3 have approved ground truth, frozen evaluator, feed/API contracts, and the atomic persistence migration.
- Read current `frontend/app.py`, `frontend/job_discovery_view.py`, Streamlit tests, API contracts, and application/profile repository ports.

## Files

Create:

- `src/resume_tailor/application/job_discovery/experience.py` — page-facing application façade.
- `src/resume_tailor/application/job_discovery/profile_queries.py` — reviewed-profile loading use case.
- `src/resume_tailor/application/job_discovery/handoff.py` — existing tailoring input preparation.
- `src/resume_tailor/frontend/jobs_page.py` — Jobs navigation and session-state orchestration.
- `src/resume_tailor/frontend/job_feed_view.py` — split-panel Tailored/Explore rendering.
- `src/resume_tailor/frontend/job_preferences_view.py` — simple role/sector/eligibility/location preferences.
- `src/resume_tailor/frontend/saved_jobs_view.py` — saved snapshot and availability rendering.
- `tests/application/job_discovery/test_experience.py`
- `tests/application/job_discovery/test_profile_queries.py`
- `tests/application/job_discovery/test_handoff.py`
- `tests/test_jobs_page_streamlit.py`
- `tests/test_jobs_app_streamlit.py`
- `tests/streamlit_apps/jobs_test_app.py`
- `manual-test/jobs_browser_scenarios.py`
- `manual-test/JOBS_BROWSER_CHECKLIST.md`

Modify:

- `src/resume_tailor/ports/interfaces.py` — narrow reviewed-profile query capability.
- `src/resume_tailor/infrastructure/profile_repository.py`
- `src/resume_tailor/infrastructure/dependencies.py`
- `src/resume_tailor/api/dependencies.py`
- `src/resume_tailor/frontend/app.py`
- `src/resume_tailor/frontend/job_discovery_view.py` — compatibility export or removal after migration.
- Focused Streamlit tests.
- `README.md`, `docs/ARCHITECTURE.md`, and `docs/PRODUCT_SPEC.md`.

## Interfaces

```python
class JobsExperienceService(Protocol):
    def list_reviewed_profiles(self, user_id: str) -> Sequence[ReviewedProfile]: ...
    def get_preferences(self, user_id: str, profile_id: str) -> JobSearchPreferences | None: ...
    def confirm_preferences(self, preferences: JobSearchPreferences) -> JobSearchPreferences: ...
    def refresh_tailored(self, user_id: str, profile_id: str) -> FeedRefreshResult: ...
    def refresh_explore(self, user_id: str, profile_id: str) -> FeedRefreshResult: ...
    def get_feed(self, run_id: str, feed: FeedKind) -> FeedView: ...
    def get_excluded(self, run_id: str, feed: FeedKind) -> FeedView: ...
    def get_job_detail(self, job_id: str) -> JobDetailView: ...
    def save_job(self, user_id: str, job_id: str) -> SavedJob: ...
    def check_saved_job(self, user_id: str, saved_id: str) -> SavedJob: ...
    def prepare_tailoring(self, user_id: str, job_id: str) -> TailoringHandoff: ...
```

No frontend module may import SQLite repositories, provider connectors, or `Settings`.

## Task 1: Application façade and profile loading

- [ ] Write failing tests proving a saved reviewed profile loads without resume-editor session state, a missing profile produces a clear create/review action, and job details go through `JobsExperienceService`.
- [ ] Run:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q `
  tests/application/job_discovery/test_profile_queries.py `
  tests/application/job_discovery/test_experience.py
```

Expected failure: no page façade or reviewed-profile query contract.

- [ ] Implement the narrow application façade and infrastructure composition.
- [ ] Re-run; expected pass with no frontend repository imports.
- [ ] Commit: `refactor(jobs): expose page use cases through application services`.

Manual checkpoint: start Jobs with a persisted profile and with an empty profile store; both states must be explicit.

## Task 2: Navigation and Preferences

- [ ] Write failing Streamlit tests for Jobs/Resume navigation, four section labels, empty-profile action, restored preferences, and absence of internal technical-theme editing.
- [ ] Run:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q tests/test_jobs_page_streamlit.py -k "navigation or preferences or empty_profile"
```

Expected failure: Jobs remains appended to the resume page and exposes internal fields.

- [ ] Add minimal sidebar navigation. When Jobs is selected, render Jobs and stop before the unrelated resume editor body.
- [ ] Render only role families, initial sectors, levels, locations, arrangement, posting age, authorization/eligibility facts, and secondary preferred/excluded companies.
- [ ] Re-run; expected pass with confirmed preferences restored through the façade.
- [ ] Commit: `feat(jobs): add dedicated Jobs navigation and preferences`.

Manual checkpoint: change sections, refresh the page, and confirm preferences remain attached to the selected reviewed profile.

## Task 3: Split-panel feeds and selection state

- [ ] Write failing tests for Tailored selection, Explore selection, first-job default, selection preservation after refresh, responsive narrow layout, grade/eligibility/provisional display, exact evidence, gaps, unknowns, source, and posting date.
- [ ] Run:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q `
  tests/test_jobs_page_streamlit.py -k "selection or tailored or explore or details"
& ".\.venv\Scripts\python.exe" -m pytest -q `
  tests/test_jobs_app_streamlit.py -k "selection"
```

Expected failure: current view renders a vertical list and does not update a right-hand detail panel.

- [ ] Implement left list/right details using session-state selected job ID. Selecting a row updates only the selected detail state and does not navigate away.
- [ ] Re-run; expected pass with shared grade/eligibility components and feed-specific order.
- [ ] Commit: `feat(jobs): render selectable split-panel feeds`.

Manual checkpoints: select first, middle, and last jobs; test both feeds; resize to desktop and narrow viewport.

## Task 4: Excluded results and explicit expansion

- [ ] Write failing tests proving excluded payloads are not requested or rendered on initial feed load, the control displays `Show excluded jobs (N)`, and one deliberate expansion requests and renders the excluded feed.
- [ ] Run:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q `
  tests/test_jobs_page_streamlit.py -k "excluded"
& ".\.venv\Scripts\python.exe" -m pytest -q `
  tests/test_jobs_app_streamlit.py -k "excluded"
```

Expected failure: current application discards ineligible jobs and has no explicit excluded control.

- [ ] Implement count-only normal response, deliberate expansion, and collapse behavior.
- [ ] Re-run; expected pass with no excluded details before expansion.
- [ ] Commit: `feat(jobs): hide excluded evaluations until requested`.

Manual checkpoint: use hard-ineligible and keyword-overlap Don't Match scenarios and verify they are absent until expansion.

## Task 5: Saved, posting, and tailoring actions

- [ ] Write failing tests for idempotent save, immutable snapshot, availability update, official URL action, and Tailor handoff.
- [ ] Run:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q `
  tests/application/job_discovery/test_handoff.py `
  tests/application/job_discovery/test_saved_jobs.py `
  tests/test_jobs_page_streamlit.py -k "save or posting or tailor"
```

Expected failure: no application-boundary handoff or split-panel action state.

- [ ] Implement `prepare_tailoring()` as an existing `JobPosting` handoff, set the existing session input, switch to Resume Tailor, and do not call document generation.
- [ ] Re-run; expected pass with unchanged resume/Gemini/DOCX behavior.
- [ ] Commit: `feat(jobs): connect saved and tailoring actions`.

Manual checkpoint: save, reload, check availability, open the official posting, and hand off one selected job.

## Task 6: Loading, empty, partial-failure, and refresh states

- [ ] Write failing tests for no source configuration, no results, loading, successful refresh, partial source failure, all-source failure, stale results after refresh failure, unknown freshness, and unknown eligibility.
- [ ] Run:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q `
  tests/test_jobs_page_streamlit.py `
  tests/test_jobs_app_streamlit.py
```

Expected failure: current view has only basic warnings and no dedicated state model.

- [ ] Implement explicit state messages and preserve stale visible results when a new refresh fails.
- [ ] Re-run; expected pass with behavior assertions rather than text-presence-only assertions.
- [ ] Commit: `test(jobs): cover Jobs page interaction states`.

## Task 7: Browser harness and checklist

- [ ] Write `manual-test/JOBS_BROWSER_CHECKLIST.md` with scenario, viewport, expected behavior, actual result, date, commit, and screenshot fields.
- [ ] Add the deterministic harness:

```powershell
& ".\.venv\Scripts\python.exe" -m streamlit run `
  manual-test/jobs_browser_scenarios.py `
  --server.headless true `
  --server.port 8501
```

- [ ] Manually verify profile loading, all four sections, both feeds, selection, excluded expansion, save, availability, URL, Tailor handoff, responsive layout, and failure states.
- [ ] Record results in the checklist and commit: `docs(jobs): record Jobs browser checkpoints`.

## Acceptance criteria

- Dedicated Jobs navigation exists without moving unrelated resume UI.
- Four sections are visible and functional.
- Left selection updates right details without navigation.
- Normal UI never displays numeric scores or probability language.
- Unknown eligibility and provisional status are independent and visible.
- Excluded jobs remain hidden until deliberate expansion.
- Saved snapshots remain immutable.
- Tailor handoff does not generate documents or change existing tailoring behavior.
- Automated behavior tests and manual browser checkpoints pass.

## Recommended branch and commit boundaries

Recommended branch: `feature/jobs-ui`, created from newest `main` after Plan 3 merges. Tasks 1–7 are independently reviewable commits. Do not combine UI work with final hardening.

## Known unrelated DOCX constraint

The known health HTTP 503 remains a separate environment condition and must not be changed by this plan.

