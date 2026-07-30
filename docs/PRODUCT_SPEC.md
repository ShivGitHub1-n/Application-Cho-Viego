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

The resume engine is accepted. The first evidence-grounded cover-letter
workflow is the next active product stage and must target a professionally
filled one-page output at 92–95% utilization, close to 95% when substantive
content supports it. Authentication, multi-user deployment, application
tracking, editor/template customization, broader frontend redesign, and Chrome
extension capture are later-stage capabilities.

Known cover-letter composition and export-quality issues are tracked in
[KNOWN_ISSUES.md](KNOWN_ISSUES.md) and are addressed by the current
cover-letter roadmap item, not by changing the accepted resume engine.

## Job discovery MVP

Job discovery uses confirmed search preferences separate from the reviewed
profile. The product may propose deterministic preference suggestions, but the
user can review and edit every field before confirming them. Discovery begins
only after the user explicitly selects `Refresh recommendations`.

Automatic recommendations come only from explicitly approved Greenhouse or
Lever sources. The production registry is empty by default; when it is empty,
the product displays `No approved job sources are configured` and does not
perform live discovery.

Recommendation results remain provisional. The system displays transparent
profile-fit reasoning and does not claim certainty when postings contain missing
or unknown eligibility information.

Users can save a job as an immutable timestamped posting snapshot and manually
check availability later. An unavailable or expired posting remains visible
with its saved snapshot; availability metadata does not rewrite or delete the
snapshot. Unknown availability remains explicit.

The MVP excludes background scheduling, automatic application submission,
application-status tracking, authentication, LinkedIn or Indeed scraping,
arbitrary career-page scraping, additional ATS providers, paid search
providers, geocoding or radius calculations, Gemini job-fit analysis, and
resume or cover-letter generation changes.
