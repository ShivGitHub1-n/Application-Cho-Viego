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

Cover letters, authentication, multi-user deployment, application tracking, and recommendations are later-stage capabilities.
