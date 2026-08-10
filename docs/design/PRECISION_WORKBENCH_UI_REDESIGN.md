# Precision Workbench UI Redesign

## Status

**Implemented; automated integration validation complete. Browser visual QA remains required.**

This is the canonical contract for the approved full-product UI redesign of
Application Cho Viego. It records the implemented Streamlit structure and its
acceptance boundaries; it does not claim production deployment or completed
browser-level visual acceptance.

## Design authority

- Figma: https://www.figma.com/file/a7UeLCf07LY1VlIJCeVlg1?type=design
- Selected direction: **Precision Workbench**.
- 00 — Audit & Visual Directions: selected comparison frame 43:157.
- 01 — Foundations: representative frame 51:3.
- 02 — Components: representative frame 52:3.
- 03 — Global Shell: representative frame 53:3.
- 04 — Career Profile: representative frame 55:3.
- 05 — Jobs: representative frame 56:3.
- 06 — Resume Studio: representative frame 57:3.
- 07 — Cover Letters: representative frame 59:3.
- 08 — Light Theme Reference: representative frame 60:3.
- 09 — Prototype & Handoff: representative frame 62:7.
- 10 — End-to-End Prototype: desktop frame 67:3; mobile frame 67:1218.
- Workspace Icon component set: 84:526. It contains editable vector semantic
  line icons for Career Profile/person, Jobs/briefcase, Resume Studio/document,
  and Cover Letters/envelope.

The affected Figma frame is the visual and structural authority for each
implementation batch. Figma-generated code is reference material only: it
does not authorize React, Next.js, Tailwind, JavaScript controls, a static
canvas, or a replacement frontend framework. The target may use inline SVG or
native Streamlit icon support; rasterized Figma icons are not required.

## Product structure

The approved target navigation is:

1. Career Profile
2. Jobs
3. Resume Studio
4. Cover Letters

Career Profile is the intended default route. No dashboard or landing page is
planned.

Desktop will use a persistent left sidebar with semantic workspace icons and
active-profile context near its bottom, a primary workspace, an optional
context inspector, and document-focused review shells. Mobile will use
four-item bottom navigation, one-column layouts, full-screen detail/evidence
editing where appropriate, and narrow document review. A dedicated tablet-only
implementation batch is not planned.

The implementation remains Streamlit and migration-friendly. FastAPI remains
the product boundary. A React, Next.js, or Tailwind rewrite is not part of
this redesign.

## Visual system

Precision Workbench is dark-primary, technical, dense, and workflow-led.

- Graphite and blue-black form the primary canvas; blue-gray supports
  operational surfaces.
- Mint denotes primary actions and confirmed-positive actions.
- Blue denotes selection and informational state.
- Amber denotes review, uncertainty, and approval-required state.
- Red is reserved for invalid, destructive, blocked, or critical state.
- Thin borders, moderate radii, high information density, limited shadows, and
  visible keyboard focus are required.
- Decorative glowing AI panels, chatbot framing, sparkle iconography, generic
  purple-gradient AI styling, oversized pill-heavy layouts, and decoration
  without workflow value are excluded.
- Dark is primary; light mode must be fully supported.

Implementation should use scoped semantic tokens rather than hard-coded
page-specific palettes. Semantic CSS variables should be mapped through
available Streamlit theme variables or another verified stable browser
mechanism. This document does not claim that Streamlit exposes a stable public
Python API for resolving the active theme. Browser verification remains
required for actual theme behavior and contrast.

## Converged frontend

| Area | Previous frontend | Implemented target |
| --- | --- | --- |
| Routing | frontend/app.py renders shared navigation and branches to dedicated Jobs; Profile, résumé, and cover-letter flows are still largely co-located | app.py remains composition root and dispatches one focused route renderer |
| Navigation | Jobs, Resume Tailor, Cover letters, Master profile | Career Profile, Jobs, Resume Studio, Cover Letters |
| Profile | Existing Master Profile import, structured editor, raw JSON fallback, save/load flow | Career Profile overview, section navigation, focused editors, evidence library, validation/save status, advanced tools |
| Resume | Sequential tailoring controls | Five stages: Job context, Strategy, Evidence selection, Resume review, Export |
| Cover letters | Sequential drafting/review/export controls | Linked setup, document review, claim inspector, independent approval, export |
| Jobs | Dedicated accepted modules and deterministic harness | Same accepted behavior integrated with shared shell and semantic token system |
| Styling | Jobs-scoped CSS; default Streamlit presentation elsewhere | Shared scoped semantic tokens and intentional Streamlit-compatible components |
| Responsive | Jobs-specific responsive rules | Cross-page shell and mobile detail patterns |

The Career Profile, Jobs, Resume Studio, and Cover Letters routes now use the
Precision Workbench shell and focused page modules. Existing application,
evidence, artifact, and rendering authority remains behind those pages.

## Behavior-preservation boundaries

### Career Profile

Career Profile is the product-facing name for the existing Master Profile
workflow. It remains the reviewed source of truth for Jobs, résumé tailoring,
and cover letters.

The target includes an overview; section navigation; personal information;
education; experience; projects; skills; an evidence library; focused
experience/project editors; individually editable evidence statements;
technologies, capabilities, outcomes, source references, and confirmation
state; résumé import and extracted-draft review; validation/save state; and raw
JSON/developer controls in an advanced area.

MasterProfileRepository, profile schemas, validation, persistence behavior,
and evidence authority remain unchanged.

### Jobs

Accepted Jobs behavior remains unchanged: Tailored for you, Explore sectors,
Saved, Preferences, reviewed-profile selection, backend-owned ordering, no
frontend re-ranking, and no numeric fit scores. The exact grades remain
Excellent, Good, Weak, and Don’t Match. Eligibility remains Eligible, Unknown,
or Ineligible; Provisional remains separate from grade. Ordinary feeds hide
Don’t Match until excluded results are explicitly expanded.

Saved snapshots remain immutable; availability metadata may change without
rewriting a snapshot. Tailored and Explore selection remains independent.
Full-card interaction remains keyboard accessible, with selected, hover,
selected-hover, and focus precedence visible. Tailor Resume remains a safe
handoff only: it must not call Gemini, create a strategy, generate/export a
document, or create a cover letter.

### Resume Studio

The target workflow is:

1. Job context
2. Strategy
3. Evidence selection
4. Resume review
5. Export

It preserves equal entry from a discovered Jobs posting or pasted job
description, one authoritative recommendation, no multi-version comparison,
visible strategy/rationale/gaps/approval-required claims, reviewed profile
evidence authority, document-first review, exact-page verification before
export, current rendering and DOCX authority, deterministic profile/posting
invalidation, and the rule that generated text never becomes source evidence.

### Cover Letters

Cover Letters preserve active-job and tailoring-plan linkage where available,
recipient/company context, evidence-backed drafting, document-oriented review,
subtle approval-required markers, a dedicated claim inspector, approval or
exclusion decisions, full-review confirmation, and exact-page verification
before export. Cover-letter approvals remain independent from résumé approvals;
generated letter text never becomes source evidence.

## Planned architecture and component boundaries

The planned frontend uses boundaries resembling:

| Boundary | Intended responsibility |
| --- | --- |
| app.py | Composition root and route dispatcher |
| app_shell.py and app_shell_styles.py | Desktop/mobile navigation, active-profile context, route intent |
| design_tokens.py and shared_components.py | Scoped semantic tokens and intentional shared Streamlit presentation |
| profile_page.py, profile_editor_view.py, profile_import_view.py | Career Profile overview, editing, import, advanced area |
| resume_studio_page.py and resume_*_view.py | Five-stage Resume Studio |
| cover_letters_page.py and cover_letter_*_view.py | Setup, review, claim decisions, export |
| document_canvas.py | Structured review surface and optional inspector |
| Existing Jobs modules | Jobs presentation through existing JobsExperienceService facade |

These file names are intended module boundaries, not implemented modules or a
rigid requirement to create every file exactly as named.

app.py will construct dependencies and pass them explicitly. Page modules will
not instantiate repositories, duplicate application policy, or reimplement
domain decisions. Application services remain authoritative. Document canvases
are review surfaces, not document-rendering authority; ResumeRenderer,
CoverLetterRenderer, and exact page-count tooling remain export authority.
Session-state invalidation remains deterministic. Streamlit selectors must be
centralized and verified in the browser. Interactive actions remain native
Streamlit controls where practical.

## Implementation roadmap

This is one coherent implementation project with six internal, reviewable
batches and recommended commit boundaries. They are not separate product
branches or mandatory pull requests.

1. **Shared foundations** — semantic tokens, shell, route vocabulary,
   workspace icons, reusable controls/state surfaces, desktop sidebar, mobile
   bottom navigation, shell harness.
2. **Career Profile** — overview, sections, focused editing, evidence
   metadata, import/extraction review, validation, advanced tools, default
   route transition.
3. **Resume Studio** — five stages, Jobs/pasted intake, strategy, evidence,
   document review, exact export gate.
4. **Cover Letters** — setup, linked context, recipient information,
   evidence-backed draft, claim approval, document review, exact export gate.
5. **Jobs integration** — shared shell/token integration while preserving
   accepted behavior; refresh browser evidence for full-card, selection,
   hover/focus, mobile, Saved, Preferences, Tailored, and Explore.
6. **Cross-page hardening** — responsive defects, keyboard/focus verification,
   dark/light checks, screenshots, exact document checks, documentation
   reconciliation, independent review.

The maintainable execution detail is in
docs/engineering/PRECISION_WORKBENCH_IMPLEMENTATION_PLAN.md.

## Testing and browser authority

- Unit tests prove deterministic helper behavior.
- Streamlit AppTest proves state, routing, disabled controls, and semantic
  output.
- Integration tests prove application-boundary behavior.
- CSS-string assertions do not prove browser appearance.
- Deterministic offline harnesses and the real persisted application are both
  required acceptance surfaces.
- Exact DOCX page verification is separate from browser visual review.
- Real-browser screenshots are authoritative for dimensions, hit areas,
  selected-hover and focus appearance, document canvas behavior, mobile
  overflow, and dark/light parity.
- The user performs final local browser acceptance where Codex cannot launch a
  browser.

Playwright WinError 5 before Chromium starts is environment-only, not visual
acceptance. HTTP 503 from unavailable exact page tooling is a blocked export
state, not success. Neither condition authorizes a visual or export pass claim.

## Definition of done

The redesign is complete only when approved routes and preserved behavior are
implemented; focused and affected tests pass; browser evidence exists for
desktop/mobile dark/light states; exact document gates behave truthfully;
accessibility interactions are checked; relevant Figma frames are compared;
independent review is complete; and documentation distinguishes verified
results from environment limits. No locked-release certification is implied.

## Locked benchmark disclosure

The sealed path tests/job_discovery/benchmark must not be inspected, opened,
read, searched, listed, enumerated, summarized, modified, inferred from, or
run. Its parent directory must not be inspected broadly. Broad recursive
inventory, broad rg, git ls-files, pytest, pytest tests, tree, and similar
commands are prohibited.

Three historical incidents remain accurately disclosed:

1. A historical broad pytest command accidentally collected the locked
   benchmark gate.
2. A later broad rg diagnostic surfaced benchmark fixture lines.
3. A Batch 5 inventory attempt listed path names beneath the benchmark
   directory.

No benchmark cases, labels, metrics, expected outputs, or artifacts were used.
The redesign must not claim new locked-release certification.
