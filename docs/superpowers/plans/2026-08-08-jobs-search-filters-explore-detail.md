# Jobs Search, Filters, and Explore Detail Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add local, order-preserving Jobs search and browse filters with independent section state, immutable Saved snapshot filtering, and shared Explore detail parity that matches approved Figma page 11.

**Architecture:** Keep retrieval, recommendation ordering, eligibility, scoring, and persistence behind `JobsExperienceService`. Add a pure application filtering module that projects already-normalized `RecommendationView` and `SavedJobView` objects. Keep Streamlit responsible for section-local widget/state orchestration and pass the projected objects through the existing shared card/detail renderer.

**Tech Stack:** Python 3, Pydantic view models, Streamlit native widgets/AppTest, pytest, Ruff, scoped CSS tokens, Figma MCP screenshots/design context.

## Global Constraints

- The repository must remain on `feature/jobs-search-and-filters`, start clean, and remain clean after each local commit.
- Never access, list, search, execute, or modify `tests/job_discovery/benchmark`.
- Use `..\\.venv\\Scripts\\python.exe` from the repository root for every Python command.
- Do not run broad `pytest`, `pytest tests`, `Get-ChildItem -Recurse`, `tree`, `rg --files`, or `git ls-files`.
- Filtering must not perform provider refresh, network I/O, recommendation scoring, evaluator execution, Gemini calls, discovery refresh, or persistence mutation.
- The frontend must preserve backend relative order and must not rerank.
- Do not expand or reinterpret domain evaluator `JobLevel`; browse seniority is application-level.
- Saved filtering must use immutable `posting_snapshot` fields, not availability metadata.
- No push, merge, PR, history rewrite, amend, stash, reset, restore, checkout, or rebase.
- Every production behavior change follows a failing-test, minimal-implementation, green-refactor cycle.
- Before every commit: inspect diff, run explicit focused tests, run Ruff on every changed Python file, and run `git diff --check`.
- Automated green tests do not satisfy visual acceptance; the real Streamlit app must be rendered and compared to Figma frames `91:15`, `91:112`, `91:249`, and `91:346`.

---

### Task 1: Documentation and design authority

**Files:**
- Create: `docs/design/JOBS_SEARCH_FILTERS_AND_EXPLORE_DETAIL.md`
- Create: `docs/superpowers/plans/2026-08-08-jobs-search-filters-explore-detail.md`

**Interfaces:**
- Consumes: approved Jobs Search + Filters + Explore Detail Parity prompt and Figma page 11.
- Produces: reviewed contract and executable plan used by all later tasks.

- [x] **Step 1: Record the approved contracts.** Document independent section state, pure local projection, browse filter semantics, Saved snapshot authority, Explore sector scope, shared detail parity, visual authority, and deferred performance work.
- [x] **Step 2: Record concrete implementation tasks.** Name the filtering module, view-model changes, frontend modules, tests, TDD commands, verification gates, visual comparison, and local commit boundaries.
- [x] **Step 3: Self-review the plan.** Read both documents fully, scan for `TBD`, `TODO`, vague placeholder language, and undefined interface names; correct omissions before committing.
- [x] **Step 4: Verify the documentation batch.** Run `git diff --check`, inspect the diff, and commit only the two documentation files:

```powershell
git diff --check
git diff -- docs/design/JOBS_SEARCH_FILTERS_AND_EXPLORE_DETAIL.md docs/superpowers/plans/2026-08-08-jobs-search-filters-explore-detail.md
git add docs/design/JOBS_SEARCH_FILTERS_AND_EXPLORE_DETAIL.md docs/superpowers/plans/2026-08-08-jobs-search-filters-explore-detail.md
git commit -m "docs(jobs): specify search filters and explore detail parity"
```

### Task 2: Pure filtering projection

**Files:**
- Create: `src/resume_tailor/application/job_discovery/filtering.py`
- Create: `tests/application/job_discovery/test_filtering.py`
- Modify: `src/resume_tailor/application/job_discovery/experience.py`

**Interfaces:**
- Consumes: frozen `RecommendationView`, frozen `SavedJobView`, `SavedJob.posting_snapshot`, domain `JobLevel`, `WorkArrangement`, and injected timezone-aware `now`.
- Produces: `BrowseSeniority`, `DatePostedWindow`, `BrowseFilterState`, `LocationFacet`, `filter_recommendations`, `filter_saved_jobs`, `available_locations`, and active-chip/reset helpers.

- [x] **Step 1: Write the failing unit tests.** Cover title/company-only casefolded substring search, whitespace queries, order preservation, conservative Co-op/New Grad/Manager/title signals, JobLevel fallbacks, Unknown, OR within groups, AND across groups, arrangement/location, date boundaries, unknown dates, Any time, location facets, Saved snapshot fields, active-chip removal, and Clear all.
- [x] **Step 2: Run the explicit test file and confirm the expected failure.**

```powershell
.\\.venv\\Scripts\\python.exe -m pytest tests/application/job_discovery/test_filtering.py -q
```

Expected: collection or assertion failure because the filtering module and public functions do not yet exist.
- [x] **Step 3: Implement the smallest pure module.** Use frozen Pydantic/dataclass state, `casefold()` plus whitespace normalization, title signals before domain fallback, timezone-aware threshold comparisons, base-collection location facets, and a single ordered list comprehension applying AND/OR semantics. Do not import Streamlit, repositories, SQLite, providers, or Gemini.
- [x] **Step 4: Extend application view projection minimally.** Add browse seniority and authoritative posted/location facets to the application-facing views, deriving Saved facets from `posting_snapshot`. Leave domain `JobLevel` and recommendation behavior unchanged.
- [x] **Step 5: Rerun the explicit unit file and refactor only while green.**

```powershell
.\\.venv\\Scripts\\python.exe -m pytest tests/application/job_discovery/test_filtering.py -q
```

- [ ] **Step 6: Verify and commit the pure application batch.**

```powershell
.\\.venv\\Scripts\\python.exe -m ruff check src/resume_tailor/application/job_discovery/filtering.py src/resume_tailor/application/job_discovery/experience.py tests/application/job_discovery/test_filtering.py
git diff --check
git diff --stat
git add src/resume_tailor/application/job_discovery/filtering.py src/resume_tailor/application/job_discovery/experience.py tests/application/job_discovery/test_filtering.py
git commit -m "feat(jobs): add instant search and browse filters"
```

### Task 3: Section-local Streamlit state and UI controls

**Files:**
- Modify: `src/resume_tailor/frontend/jobs_page.py`
- Modify: `src/resume_tailor/frontend/job_feed_view.py`
- Modify: `src/resume_tailor/frontend/saved_jobs_view.py`
- Modify: `src/resume_tailor/frontend/jobs_styles.py`
- Modify: `tests/streamlit_apps/jobs_test_app.py`
- Modify: `tests/test_jobs_app_streamlit.py`
- Modify: `tests/test_jobs_page_streamlit.py`

**Interfaces:**
- Consumes: pure filtering types/functions and application view facets from Task 2.
- Produces: independent Tailored/Explore/Saved search/filter widget state, chips, reset actions, counts, no-match state, inline filter workspace, and preserved backend order.

- [x] **Step 1: Write failing AppTest/UI tests.** Add tests that set Tailored, Explore, and Saved search independently; exercise filter controls, active chip removal, Clear all, counts, no-match reset, and profile reset. Add an Explore sector transition test proving filters persist while selection is scoped by sector.
- [x] **Step 2: Run only the new/affected explicit AppTest files and confirm failure.**

```powershell
.\\.venv\\Scripts\\python.exe -m pytest tests/test_jobs_app_streamlit.py tests/test_jobs_page_streamlit.py -q
```

Expected: failures for absent search/filter widgets, state keys, counts, and reset behavior.
- [x] **Step 3: Implement section state before widgets are instantiated.** Store state under section/profile/sector-safe keys, consume pending reset values before constructing widgets, keep search separate from Clear all, and clear profile-specific state during profile changes without mutating instantiated widget keys.
- [x] **Step 4: Render shared controls and projected collections.** Add the 42px search row, 132px filter button, result count, 26px removable chips, 224px inline filter panel, grouped seniority/location/arrangement/date controls, and no-match reset. Feed the filtered list into the existing shared `render_feed`; derive locations from the unfiltered base collection.
- [x] **Step 5: Integrate Saved snapshots.** Filter `SavedJobView` values using snapshot-authoritative facets, preserve availability/check actions, show filtered snapshots/total saved snapshots, and select the first visible saved item or clear the detail panel.
- [x] **Step 6: Rerun focused AppTests and refactor only while green.**

```powershell
.\\.venv\\Scripts\\python.exe -m pytest tests/test_jobs_app_streamlit.py tests/test_jobs_page_streamlit.py -q
```

- [ ] **Step 7: Perform frontend commit verification.** Inspect the diff, run Ruff on every changed Python file, run `git diff --check`, launch the harness for the four required states, capture screenshots, compare against Figma, correct Jobs-only discrepancies, repeat screenshots, then commit:

```powershell
.\\.venv\\Scripts\\python.exe -m ruff check src/resume_tailor/frontend/jobs_page.py src/resume_tailor/frontend/job_feed_view.py src/resume_tailor/frontend/saved_jobs_view.py src/resume_tailor/frontend/jobs_styles.py tests/streamlit_apps/jobs_test_app.py tests/test_jobs_app_streamlit.py tests/test_jobs_page_streamlit.py
git diff --check
git add src/resume_tailor/frontend/jobs_page.py src/resume_tailor/frontend/job_feed_view.py src/resume_tailor/frontend/saved_jobs_view.py src/resume_tailor/frontend/jobs_styles.py tests/streamlit_apps/jobs_test_app.py tests/test_jobs_app_streamlit.py tests/test_jobs_page_streamlit.py
git commit -m "feat(jobs): add instant search and browse filters"
```

### Task 4: Explore detail root-cause regression and fix

**Files:**
- Modify: `src/resume_tailor/frontend/jobs_page.py`
- Modify: `src/resume_tailor/frontend/job_feed_view.py`
- Modify: `src/resume_tailor/application/job_discovery/experience.py`
- Modify: `tests/streamlit_apps/jobs_test_app.py`
- Modify: `tests/test_jobs_app_streamlit.py`

**Interfaces:**
- Consumes: Task 2 projected Explore views, Task 3 sector-safe selection state, and the shared detail renderer.
- Produces: a reproduced and documented root cause, sector-correct detail lookup, safe filtered selection transitions, and unchanged Tailored detail behavior.

- [x] **Step 1: Reproduce before fixing.** Run the offline harness, select Explore, select a card, change sector, reselect a card, and apply a filter that hides the selected card. Capture AppTest state and the detail lookup inputs. Establish whether the failure is caused by the missing protocol `sector` contract, stale sector selection, detail lookup against the wrong feed, or selection being cleared after projection.
- [x] **Step 2: Write the focused failing regression test.** Assert Explore card selection resolves a detail in the active sector, the shared renderer receives non-`None` detail data, a hidden selected item transitions to the first remaining item or no-match state, and a prior-sector job cannot populate the new sector.
- [x] **Step 3: Run the regression test and confirm the expected failure before editing production code.**

```powershell
.\\.venv\\Scripts\\python.exe -m pytest tests/test_jobs_app_streamlit.py -q
```

- [x] **Step 4: Apply one root-cause fix.** Align the protocol signature and shared detail callback with the sector-aware application lookup, scope selection and render keys to the active sector, and ensure the projection is the sole source for visible selection. Do not create a second detail renderer or alter Tailored policy.
- [x] **Step 5: Rerun the regression and existing Jobs tests.**

```powershell
.\\.venv\\Scripts\\python.exe -m pytest tests/test_jobs_app_streamlit.py tests/test_jobs_page_streamlit.py -q
```

- [ ] **Step 6: Verify and commit the defect fix.** Run Ruff on all changed Python files, `git diff --check`, inspect the exact diff, and commit:

```powershell
.\\.venv\\Scripts\\python.exe -m ruff check src/resume_tailor/application/job_discovery/experience.py src/resume_tailor/frontend/jobs_page.py src/resume_tailor/frontend/job_feed_view.py tests/streamlit_apps/jobs_test_app.py tests/test_jobs_app_streamlit.py
git diff --check
git add src/resume_tailor/application/job_discovery/experience.py src/resume_tailor/frontend/jobs_page.py src/resume_tailor/frontend/job_feed_view.py tests/streamlit_apps/jobs_test_app.py tests/test_jobs_app_streamlit.py
git commit -m "fix(jobs): restore explore detail panel parity"
```

### Task 5: Final focused verification and visual acceptance

**Files:**
- Modify only if visual or test verification exposes an in-scope defect.

**Interfaces:**
- Consumes: committed implementation and Figma frames `91:15`, `91:112`, `91:249`, `91:346`.
- Produces: fresh evidence for functional correctness, lint, diff hygiene, rendered visual comparison, clean worktree, and local commit SHAs.

- [x] **Step 1: Run the explicit final focused suite without descending into the sealed benchmark.** Include `tests/application/job_discovery/test_filtering.py`, `tests/test_jobs_page_streamlit.py`, and `tests/test_jobs_app_streamlit.py`, plus any explicitly changed safe test files.
- [x] **Step 2: Run Ruff on every changed Python file and `git diff --check`.** Read the full outputs and stop if either fails.
- [x] **Step 3: Launch the actual documented Streamlit app with `..\\.venv\\Scripts\\python.exe`, not the harness only.** Use an available browser/screenshot mechanism at about 1440px wide. If Playwright returns WinError 5, record it and try another usable mechanism.
- [ ] **Step 4: Capture and compare all four required states.** Compare hierarchy, proportions, spacing, density, typography, chips, filter panel, selected cards, detail sections, action layout, Explore sector state, and Saved snapshot messaging. Record discrepancies and make only Jobs-scoped corrections.
- [ ] **Step 5: Repeat the browser comparison after corrections.** Do not claim visual parity unless the rendered comparison was actually inspected. If no browser/screenshot path works, report the visual gate as blocked and do not declare the frontend complete.
- [ ] **Step 6: Confirm repository state.** Run `git status --short`, `git log -5 --oneline --decorate`, and `git rev-list --left-right --count main...HEAD`; verify a clean worktree, no push, and coherent local commits.
