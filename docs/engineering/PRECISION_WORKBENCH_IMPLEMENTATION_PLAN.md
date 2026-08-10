# Precision Workbench Implementation Plan

## Status and goal

**Implemented and converged with the accepted resume and cover-letter workflows.**

Goal: replace the page-long Streamlit MVP presentation with the approved
Precision Workbench workflow while preserving application/domain authority,
evidence truthfulness, rendering authority, accepted Jobs behavior, and
deterministic state invalidation.

## Pre-implementation frontend inventory

| Area | Current ownership |
| --- | --- |
| Composition and routing | frontend/app.py creates TailorResumeService and profile repository, creates JobsExperienceService for Jobs, renders app shell, and otherwise contains Profile/Resume/Cover Letter delivery |
| Navigation | frontend/app_shell.py owns app_active_page and consumes jobs_pending_page before its navigation widget |
| Profile | app.py owns bootstrap, import, extracted draft, structured editor, raw JSON fallback, save/load, and editor state |
| Resume | app.py owns pasted description, plan creation, claim approval, generated-content review, renderer call, and download controls |
| Cover letter | app.py owns recipient inputs, fingerprints, draft/review state, approvals, exact export, and download |
| Jobs | jobs_page.py, job_feed_view.py, job_preferences_view.py, saved_jobs_view.py, jobs_styles.py, and JobsExperienceService |
| Browser/AppTest | tests/streamlit_apps/jobs_test_app.py injects deterministic facade data into production Jobs frontend |

State authority that must be preserved:

- Global: app_active_page and jobs_pending_page.
- Profile: profile, profile_id, profile_load_status, profile_editor_state,
  profile_editor_source_key, profile_editor_raw_json, extracted draft/source,
  and errors.
- Resume: job-input widgets, posting, plan, resume, generated-content review,
  and workflow fingerprints.
- Cover letters: cover_letter, cover_letter_reviewed, and profile/posting/
  plan/evidence/recipient fingerprints.
- Jobs: profile, section, selection, excluded disclosure, refresh,
  preferences, saved-job, and Explore-sector keys.

## Target boundaries and dependencies

| Planned module group | Responsibility | Dependencies |
| --- | --- | --- |
| app.py | Streamlit configuration, service composition, active-profile bootstrap, route dispatch | Existing infrastructure factories and application services |
| app_shell.py and app_shell_styles.py | Desktop/mobile nav, active-profile context, pending route intent | Streamlit presentation only |
| design_tokens.py and shared_components.py | Scoped semantic tokens, headers, controls, state surfaces, workflow cues | Streamlit presentation only |
| profile_page.py, profile_editor_view.py, profile_import_view.py | Career Profile overview, import, focused editor, advanced area | TailorResumeService, MasterProfileRepository, application.profile_editor |
| resume_studio_page.py and resume_*_view.py | Job context, strategy, evidence, review, export stages | TailorResumeService and existing workflow invalidation |
| cover_letters_page.py and cover_letter_*_view.py | Setup, review, claim decision, export | Existing cover-letter methods on TailorResumeService |
| document_canvas.py | Shared structured review surface and optional inspector | Typed generated content only |
| Existing Jobs modules | Jobs presentation integrated with shared design system | JobsExperienceService remains the facade |

Page modules receive explicit dependencies. They do not construct repositories,
duplicate application policy, or reimplement domain decisions.

Document canvases are review surfaces, not DOCX/PDF rendering authority.
ResumeRenderer, CoverLetterRenderer, and exact page-count tooling remain export
authority. Token ownership is shared and semantic rather than page-local.
Streamlit selector ownership is centralized and browser-verified before
acceptance.

## app.py decomposition

1. Establish shell and route dispatch while retaining app.py as the single
   composition root. Consume pending navigation before native route widgets.
2. Extract Career Profile import/editor/persistence delivery into focused
   modules. Preserve profile editor keys, repository save path, schema
   validation, raw JSON advanced fallback, and derived-state invalidation.
3. Extract Resume Studio delivery into stage views. Preserve plan/posting
   fingerprints, evidence approval, document building, rendering, and exact
   export gate.
4. Extract Cover Letter delivery into setup/review/export views. Preserve
   separate cover-letter fingerprints and approvals independent from résumé
   state.
5. Dispatch exactly one route renderer from app.py and remove extracted UI
   blocks. Do not retain a feature-flagged duplicate frontend.

No extracted module imports app.py. Cross-page reuse is limited to explicit
presentation modules and existing application-layer contracts, preventing
circular imports.

## Internal implementation batches

### Batch 1 — Shared foundations

- Objective: semantic tokens, shell, target route vocabulary, editable vector
  workspace icons, shared state surfaces, desktop sidebar, mobile native bottom
  navigation, and shell harness.
- Expected production files: app.py, app_shell.py, app_shell_styles.py,
  design_tokens.py, shared_components.py, and only a small icon boundary if
  native Streamlit icon support cannot provide the approved semantic icons.
- Expected tests: token and shell AppTests plus shell-harness updates.
- Preserve: application/domain/infrastructure behavior and current Jobs facade.
- Browser gate: dark/light shell; mobile nav; active, hover, and focus; active
  profile context.
- Commit boundary: feat(frontend): add precision workbench shell foundations.

### Batch 2 — Career Profile

- Objective: Career Profile overview, sections, focused editor, evidence
  metadata, import review, validation, advanced tools, and default route.
- Expected production files: profile_page.py, profile_editor_view.py,
  profile_import_view.py, app.py.
- Expected tests: Profile AppTest and deterministic browser harness.
- Preserve: MasterProfileRepository, application.profile_editor, Pydantic
  validation, evidence authority, raw JSON fallback.
- Browser gate: overview/inspector, empty/import/error/completed states,
  focused experience/project editor, advanced area, mobile, dark/light.
- Commit boundary: feat(frontend): redesign career profile workspace.

### Batch 3 — Resume Studio

- Objective: Job context, Strategy, Evidence selection, Resume review, Export.
- Expected production files: resume_studio_page.py, resume_strategy_view.py,
  resume_evidence_view.py, resume_review_view.py, resume_export_view.py,
  document_canvas.py, app.py.
- Expected tests: Resume Studio AppTest and deterministic harness for pasted
  and Jobs-handoff starts.
- Preserve: one authoritative TailoringPlan, evidence approvals, renderer,
  exact page verification, profile/posting invalidation.
- Browser gate: all stages, pending approval, disabled export, blocked/success
  exact-page states, document canvas, mobile, dark/light.
- Commit boundary: feat(frontend): redesign resume studio workflow.

### Batch 4 — Cover Letters

- Objective: setup, linked context, recipient fields, evidence-backed draft,
  claim inspector, independent review, document canvas, exact gate.
- Expected production files: cover_letters_page.py, cover_letter_setup_view.py,
  cover_letter_review_view.py, cover_letter_export_view.py, app.py; update
  document_canvas.py only for genuinely shared behavior.
- Expected tests: Cover Letter AppTest and deterministic harness.
- Preserve: cover-letter service, claim evidence links, recipient model,
  independent approvals, renderer/page-count authority.
- Browser gate: setup, markers/inspector, approval/exclusion, disabled/enabled
  export, error/partial-success, mobile, dark/light.
- Commit boundary: feat(frontend): redesign cover letter review workflow.

### Batch 5 — Jobs integration

- Objective: integrate accepted Jobs with shared shell/tokens without changing
  its application behavior.
- Expected production files: jobs_styles.py, jobs_page.py, job_feed_view.py,
  job_preferences_view.py, saved_jobs_view.py, and only necessary shell wiring.
- Expected tests: existing Jobs AppTests/harness and focused visual-integration
  state checks.
- Preserve: JobsExperienceService, backend order, grade/eligibility/provisional
  semantics, excluded disclosure, snapshots, availability updates, safe handoff.
- Browser gate: Tailored, Explore, Saved, Preferences, selected-hover-focus,
  full-card keyboard/pointer interaction, partial/error states, desktop/mobile,
  dark/light.
- Commit boundary: feat(frontend): integrate jobs with precision workbench.

### Batch 6 — Cross-page hardening

- Objective: resolve verified responsive defects, verify keyboard/focus and
  dark/light behavior, collect screenshots, check exact documents, reconcile
  docs, and obtain independent review.
- Expected production files: only verified responsive/accessibility fixes in
  existing shell/page styles and views.
- Expected tests: focused route AppTests, explicit safe affected allowlists,
  and browser/manual evidence.
- Browser gate: desktop dark/light and mobile states for every primary route,
  document canvases, state surfaces, focus, and overflow.
- Code-hardening commit boundary, when verified production defects require code
  changes: fix(frontend): harden precision workbench across viewports.
- Final documentation commit boundary: docs(frontend): record precision
  workbench acceptance.
- Use the code-hardening commit only for verified production defects. Record
  final browser evidence and documentation reconciliation afterward in the
  documentation commit; do not mix unrelated code and documentation into
  either commit.

## State and invalidation

- Profile save/load clears derived workflow state only when the canonical
  profile changes.
- Pasted description changes are compared with stored posting fingerprints
  before stale output is shown.
- Jobs handoff writes profile/title/description, clears derived workflow,
  queues Resume Studio navigation, and generates nothing.
- Plan input changes clear generated résumé, review state, and Cover Letter
  derived state.
- Cover Letter profile/posting/plan/evidence/recipient changes clear only its
  derived draft/review state; résumé approvals remain independent.

## Testing and browser gates

- Unit tests cover deterministic state helpers and semantic adapters.
- Streamlit AppTest covers routing, state, disabled controls, save/discard,
  handoff, stage transitions, and semantic messages.
- Integration tests continue to prove application boundaries.
- CSS-string tests do not prove dimensions, hit targets, focus, selection
  precedence, document canvas, mobile overflow, or dark/light parity.
- Deterministic offline harnesses and the real persisted application are both
  required where populated and persisted paths differ.
- Exact DOCX page verification is independent from browser review. HTTP 503
  from unavailable exact tooling is blocked, not success.
- Playwright WinError 5 before Chromium starts is environment-only. It never
  justifies a browser pass claim; the user performs local browser acceptance
  where Codex cannot launch a browser.

## Risks and controls

| Risk | Control |
| --- | --- |
| Streamlit DOM selector fragility | Stable keyed containers, centralized selectors, rendered-browser inspection |
| CSS leakage | Scoped semantic variables; no global body or generated-class styling |
| Widget-owned state | Consume intent before native widgets; AppTest coverage |
| Monolith extraction | One route at a time with explicit dependencies and reviewable commits |
| Service duplication | app.py composes existing services; pages receive dependencies |
| State invalidation regression | Preserve fingerprints and workflow invalidation; focused tests |
| Jobs regression | Integrate Jobs last and retain accepted facade/harness contract |
| Mobile/light contrast | Browser screenshots at prescribed viewports in both themes |
| Document-preview confusion | Canvas is review only; renderer/page count remain export authority |
| Scope creep | No React migration, provider/scoring changes, product features, or renderer rewrite |

## Global constraints

- Preserve clean architecture and evidence-backed output.
- AI remains typed and evidence-referenced; it has no persistence or document
  formatting authority.
- Do not access tests/job_discovery/benchmark or inspect its parent broadly.
- Do not use broad pytest, pytest tests, broad rg, recursive listing, tree, or
  git ls-files for redesign work.
- Do not claim locked-release certification.
- Distinguish genuine regressions, pre-existing debt, environment-only limits,
  and browser-only acceptance.
