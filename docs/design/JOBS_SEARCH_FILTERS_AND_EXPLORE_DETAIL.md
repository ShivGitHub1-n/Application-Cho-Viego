# Jobs Search, Filters, and Explore Detail Parity

## Status and visual authority

This is the approved design/specification for the Jobs Search + Filters + Explore Detail Parity batch. Figma page `11 — Jobs Search & Filters` is the visual authority:

- Page node: `91:2`
- Tailored search and active filters: `91:15`
- Tailored expanded filter panel: `91:112`
- Explore selected-job detail parity: `91:249`
- Saved immutable-snapshot filtering: `91:346`

The implementation is native Streamlit adapted to the existing Precision Workbench tokens. The Figma generated implementation is reference material only; it is not permission to introduce React, Tailwind, JavaScript, or a static canvas.

## Product contracts

### Independent browse state

Tailored, Explore, and Saved each own an independent search query and filter state. Preferences receives no search or browse-filter UI. Profile changes clear profile-specific search, filters, selected jobs, sector-scoped selection, and expanded-filter state before the next widgets are instantiated.

Search is local, case-insensitive, partial substring matching over normalized company name or title only. It never searches descriptions, reasons, evidence, gaps, source IDs, or locations. Each projection preserves the relative order supplied by the application feed.

### Pure application projection

The existing feed retrieval boundary remains unchanged. The application loads already-normalized view objects, then a pure filtering projection removes non-matching objects without reordering them. Search and filters perform no provider refresh, network request, recommendation scoring, evaluator execution, Gemini call, discovery refresh, or persistence mutation. A Streamlit rerun may re-read the existing persisted feed through the existing service boundary, but no additional I/O is introduced per filter operation.

The frontend renders the projection and owns only delivery state. It does not reimplement recommendation, eligibility, fit, persistence, or ordering policy.

### Browse filter set

The four groups are:

1. Seniority: Internship, Co-op, New Grad, Junior, Mid-level, Senior, Lead, Staff, Principal, Manager, Unknown.
2. Location: searchable multi-select options generated from the base loaded collection's authoritative normalized/snapshot location labels. Labels are deduplicated case-insensitively with a stable display spelling. No invented locations or geocoding are allowed.
3. Work arrangement: Remote, Hybrid, On-site, Unknown, using authoritative `WorkArrangement` data.
4. Date posted: Past 24 hours, Past 3 days, Past week, Past 2 weeks, Past month, Any time. `Any time` is the default and appears last visually.

Groups combine with AND. Multiple selections within one group combine with OR. Date windows use timezone-aware `posted_at` comparisons against injected `now`, with thresholds of 24 hours, 3, 7, 14, and 30 days. Unknown `posted_at` is visible under Any time and never matches a bounded window.

Active constraints render as removable chips and expose Clear all. Removing one chip removes only that constraint. Clear all resets filters for that section; search remains separate unless the existing UX contract explicitly requires clearing it.

The sprint does not add Company, Fit Grade, Eligibility, or Employment Type filters. Company lookup is search. Fit and eligibility remain part of recommendation status/order. Employment type is deferred because no authoritative first-class source/domain field exists.

### Browse seniority authority

Browse seniority is an application-facing concept separate from evaluator/scoring `JobLevel`. The evaluator enum and all scoring/eligibility semantics remain unchanged.

Classification uses conservative title signals first: Co-op, Intern/Internship, explicit New Grad, Manager, Principal, Staff, Lead, Senior, and then the normalized domain `JobLevel` fallback. The fallback maps Intern to Internship, Entry to Junior unless an explicit New Grad title signal exists, Junior to Junior, Mid to Mid-level, Senior to Senior, Lead to Lead, Staff to Staff, Principal to Principal, Director to Manager, and Unknown to Unknown. Free-form descriptions are not used for aggressive inference.

### Counts and no-match behavior

Tailored and Explore display `filtered count of base loaded visible count`; excluded Tailored roles remain behind the existing excluded disclosure and never enter the normal count or projection. Saved displays `filtered snapshots of total saved snapshots`. An empty projection shows `No jobs match your search and filters.` with a reset action and does not refresh or widen the query.

### Saved immutable snapshots

Saved search and filtering use `SavedJob.posting_snapshot` for title, company, browse seniority, location, work arrangement, and `posted_at`. Availability/check metadata may change, but it never replaces or mutates snapshot authority. The saved count is based on the original saved snapshot collection.

### Explore state and detail parity

Explore search and filters survive sector changes. The selected job is scoped by profile, feed kind, and sector; a selected job from another sector cannot leak into the current detail panel. If the selected item becomes invisible, the first remaining visible item is selected; if none remain, the shared detail panel is cleared and the no-match state is rendered.

Tailored and Explore use the same shared detail renderer and application detail lookup path. Explore detail must include title, company, location, work arrangement, Posted, First seen, Checked, fit grade, eligibility, provisional state, verification, freshness, source/confidence, official-posting action, save action, safe Tailor Resume handoff, normalized description, reasons, exact supporting evidence, gaps, and unresolved facts whenever data exists.

The Explore defect is investigated root-cause-first with a focused regression test/harness before any fix. The fix must preserve Tailored behavior and must pass the sector through the same shared detail path rather than creating an Explore-only renderer.

#### Investigation record for the current batch

The pre-fix AppTest reproduction selected an Explore card and rendered the shared detail panel, so the failure was not reproducible with the original single-sector offline fixture. Data-flow tracing nevertheless found an unsafe boundary mismatch: the concrete application service and callback were sector-aware, while the `JobsPageExperience` protocol omitted the keyword-only `sector` contract and there was no sector-specific detail regression fixture. The diagnostic harness was tightened to return different roles for different sectors. The regression now proves the active sector reaches the shared lookup and that a prior-sector role cannot populate the new detail panel. The exact fix is the protocol signature alignment plus sector-scoped selection/projection handling; no Explore-only detail renderer was added.

### Safe tailoring and performance scope

Tailor Resume prepares the existing Resume Studio handoff only. Jobs clicks do not generate with Gemini, plan, render, export DOCX, or create a cover letter. The broader Streamlit transition/recomposition performance investigation is deferred; only inappropriate provider/scoring/network work caused by filtering is in scope.

## Visual acceptance

After automated tests are green, the real Streamlit app must be launched with the repository virtual environment and inspected at approximately 1440px wide. The rendered Tailored active-filter state, expanded filter panel, Explore selected detail, and Saved snapshot filtering state must be captured and compared side-by-side with Figma frames `91:15`, `91:112`, `91:249`, and `91:346`. Compare hierarchy, tabs, controls, count placement, chip geometry, list/detail proportions, card selection, panel spacing, typography, borders, radii, action arrangement, and information density. Obvious Jobs-specific mismatches must be corrected and the comparison repeated. If no usable browser/screenshot mechanism is available, visual acceptance is blocked and parity must not be claimed.

Unrelated visual differences in Career Profile, Resume Studio, and Cover Letters are documented as follow-up rather than expanded into this sprint.

### Deterministic visual acceptance presets

The offline acceptance harness uses the same `render_application_shell` and
`render_jobs_page` composition as the production route, with deterministic
facade data. Select one of these scenarios from the shell's Offline scenario
control before capturing screenshots:

- `visual-tailored-active`: Tailored, populated, Senior/Toronto/Hybrid/Past
  week, active chips, selected detail.
- `visual-tailored-expanded`: Tailored, populated, Mid-level/Toronto/Hybrid/
  Past week, expanded filter panel.
- `visual-explore-detail`: Explore, Software Engineering, `good` search,
  Hybrid/Past month, selected shared detail.
- `visual-saved-filtering`: Saved, `immutable` search, Toronto/Hybrid/Past
  month, selected immutable snapshot detail.

Use a desktop viewport of at least 1440px with the sidebar expanded. These
presets are fixture state only; they do not alter production filtering or
ordering behavior.
