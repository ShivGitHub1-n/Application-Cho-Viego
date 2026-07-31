# Product Specification

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
- The system must verify that the generated resume is exactly one page before export.
- Exported formatting must ultimately conform to the established resume template; styling remains the renderer's responsibility.

## Later-stage scope

Authentication, multi-user deployment, and application tracking are later-stage capabilities. The first evidence-grounded cover-letter workflow is part of the MVP; job discovery MVP behavior is described below.

## Job discovery MVP

Job discovery uses confirmed search preferences separate from the reviewed
profile. The product may propose deterministic preference suggestions, but the
user can review and edit every field before confirming them. Discovery begins
only after the user explicitly selects `Refresh recommendations`.

Automatic recommendations come only from explicitly approved Greenhouse or
Lever sources. The production registry is empty by default; when it is empty,
the product displays `No approved job sources are configured` and does not
describe that state as a successful empty search.

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
