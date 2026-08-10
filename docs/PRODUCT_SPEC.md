# Product Specification

Current product status and execution order are maintained in
[PROJECT_STATUS.md](PROJECT_STATUS.md) and [ROADMAP.md](ROADMAP.md). This
specification defines the product boundary; it does not override those current
status documents.

## Vision

Resume Tailor helps job seekers create one-page, role-specific resumes that remain truthful to their actual experience. It decides what deserves space, explains those tradeoffs, and produces content ready for a deterministic renderer.

## Stable product requirements

- The product stores a persistent, user-reviewed master resume/profile.
- A pasted job description is the required baseline input for tailoring.
- A job URL and web research may optionally enrich the pasted description; pasted text remains the fallback when URL research is unavailable.
- Gemini provides semantic matching, evidence-grounded rewriting, skill and course selection, and content prioritization. AI output is typed structured content with evidence references.
- Tailored wording may be materially different from the source wording when it remains grounded in the user's evidence.
- Education, awards, certifications, dates, employers, titles, and locations are locked by default and remain unchanged unless the user edits them.
- Job-specific changes may select or rewrite coursework, technical skills, entries, projects, bullets, and emphasis.
- The system must use exact Word pagination when available before export;
  otherwise it must retain a typed unverified estimate and require manual Word
  review rather than claiming exact pagination.
- Exported formatting must ultimately conform to the established resume template; styling remains the renderer's responsibility.

## Current MVP status and later-stage scope

The resume engine is accepted. The integrated evidence-grounded cover-letter
workflow remains under product review and must target a professionally
filled one-page output at 92–95% utilization, close to 95% when substantive
content supports it. Precision Workbench now provides the shared Career
Profile, Jobs, Resume Studio, and Cover Letters shell. Authentication,
multi-user deployment, application tracking, editor/template customization,
and Chrome extension capture remain later-stage capabilities.

Known cover-letter composition and export-quality issues are tracked in
[`KNOWN_ISSUES.md`](KNOWN_ISSUES.md). The implemented evidence, research,
artifact, page-fit, and review contracts are documented in
[`COVER_LETTER_WORKFLOW.md`](COVER_LETTER_WORKFLOW.md).

## Job discovery MVP

Job discovery uses confirmed search preferences separate from the reviewed
profile. The product may propose deterministic preference suggestions, but the
user can review and edit every field before confirming them. Discovery begins
only after the user explicitly selects `Refresh recommendations`.

Automatic recommendations come only from explicitly approved Greenhouse or
Lever sources. The production registry is empty by default; when it is empty,
the product displays `No approved job sources are configured` and does not
perform live discovery.

Recommendations show a deterministic evidence-authoritative profile fit, never
interview, hiring, offer, or other outcome probability. Fit grades are
Excellent, Good, Weak, and Don't Match, stored as `excellent`, `good`, `weak`,
and `dont_match`. Provisional is an independent uncertainty flag and never
replaces a substantive grade. Each result exposes its source, official posting
URL, verification state, typed matching reasons, material gaps, and important
provisional or unknown eligibility information. Interests and preferred
companies do not contribute qualification points.

Users can save a job as an immutable timestamped posting snapshot and manually
check availability later. An unavailable or expired posting remains visible
with its saved snapshot; availability metadata does not rewrite or delete the
snapshot. Unknown availability remains explicit.

The MVP excludes background scheduling, automatic application submission,
application-status tracking, authentication, LinkedIn or Indeed scraping,
arbitrary career-page scraping, additional ATS providers, paid search
providers, geocoding or radius calculations, Gemini job-fit analysis, and
resume or cover-letter generation changes.

### Batch 3 feed contract

Tailored uses confirmed preferences and the reviewed profile locally. Explore
uses one or more approved sectors: Software Engineering, Data Engineering,
AI / Machine Learning, Computer Vision, Robotics / Autonomous Systems,
Embedded Systems / Firmware, Hardware / Systems Integration, Controls /
Mechatronics, and Testing / Verification. Both feeds use the same frozen
eligibility and fit evaluator; Explore uses fit only as a tie-break.

Provider requests are sanitized through an explicit allow-list containing only
controlled role/title filters, approved sectors, locations, work arrangement,
levels, supported employment types, posting-age boundaries, source
restrictions, page size, and cursor. Profile text, resume evidence, skills
inventories, grades, scores, explanations, and gaps never cross this boundary.
Pagination, local fallback filtering, source warnings/errors, partial success,
and complete provenance are typed and bounded.

Tailored orders by substantive FitGrade, substantive diagnostics, eligibility
before unknown within equivalent fit, known freshness, and stable identity.
Explore orders known posted timestamps newest first, then substantive fit and
stable identity. Interests and preferred companies add no points or eligibility
effect and can only be a documented final equal-fit tie-break. Every evaluation
is retained, including excluded and unknown outcomes; ordinary feeds hide
Don't Match and hard-ineligible items while excluded endpoints expose their
reasons, gaps, unresolved facts, provisional status, and policy metadata.

Feed persistence uses one transactional schema-version-2 migration and keeps
legacy Strong/Good/Stretch/Provisional records labeled as earlier-policy
results. The dedicated Jobs UI is deferred to Batch 4; this batch changes
compatibility wiring and API contracts only.

### Batch 4 dedicated Jobs experience

Jobs is a dedicated navigable Streamlit workspace with four sections:
Tailored for you, Explore sectors, Saved, and Preferences. Tailored keeps the
approved backend fit ordering. Explore keeps newest known posting dates first,
then unknown dates, with fit only as a tie-break. The page shows Excellent,
Good, Weak, and Don't Match through a three-bar meter; numeric score values are
not rendered. Eligibility (Eligible, Unknown, Ineligible) and Provisional are
independent states, and each visible result retains exact reasons/evidence,
material gaps, unresolved facts, verification, and freshness.

Don't Match and excluded recommendations are absent from the normal rendered
feed until the user expands `Show excluded jobs (N)`. Saved records display
immutable posting snapshots and allow explicit availability checks. Tailor
resume prepares the existing title/description inputs and invalidates stale
derived output without generating a plan or document. The implementation uses
scoped theme-aware styling and native Streamlit interaction; no React,
Tailwind, JavaScript, provider controls, or live crawling are added. Final
light/dark and responsive browser verification remains manual.

### Batch 3.5 source-discovery boundary

Approved first-party pages use one static-first, bounded connector shared with
the existing provider-neutral pipeline. Rocket Lab remains the only active
first-party source; Greenhouse remains terminal application authority only.
JSON-LD and constrained HTML supply observed facts only. Browser fallback is
optional and authorized only after an explicit static browser-required result.
When authorized, the isolated Playwright adapter executes only bounded,
allowlisted first-party browser work; it never authenticates, submits an
application, inherits a user profile, or accepts registry-controlled launch
configuration.
No arbitrary scraping, private endpoints, resume/profile transfer, scoring
changes, automatic applications, or resume, cover-letter, rendering, DOCX, or
Jobs UI behavior is introduced.

Runtime health, lifecycle timestamps, separate fingerprints, aliases, and
refresh locks use schema version 3. The registry remains the only editable
source-plan authority. Broad and force refresh are CLI-only; the API exposes
safe read-only source summaries and health.

## Batch 4 Jobs product contract

Jobs is a dedicated Streamlit workspace with Tailored for you, Explore
sectors, Saved, and Preferences. It is profile-scoped and exposes refresh,
excluded-result expansion, immutable saved posting snapshots, explicit saved
availability checks, and a Tailor resume handoff into the existing workflow.
The deterministic offline harness supplies populated scenarios; the real app
uses persisted data and can remain empty until a successful refresh.

The user-facing fit grades are exactly Excellent, Good, Weak, and Don’t Match;
the domain value for the last grade is `dont_match`. Provisional is independent
of grade. Eligibility is also independent and has exactly Eligible, Unknown,
and Ineligible states. Numeric fit scores are not shown in the normal UI.
Don’t Match results are hidden until the user deliberately expands excluded
jobs. Tailored ordering is backend-owned: grade, substantive fit, eligible
before unknown, freshness, stable ID. Explore ordering is known newest
`posted_at`, unknown dates, fit tie-break, stable ID. Presentation must not
re-sort or recalculate either feed.

Tailor resume prepares existing title and description inputs only. It does not
invoke Gemini, generate a plan, render or export a document, or create a cover
letter. These constraints preserve evidence truthfulness and the existing
resume-generation boundary.

Figma references guide hierarchy, spacing, proportions, selected state, fit
bars, eligibility indicators, and responsive composition. They do not authorize
a static canvas, fake HTML interaction, or a replacement frontend framework.
Visual acceptance requires both dark and light browser checks in the offline
harness and the persisted-data application.
