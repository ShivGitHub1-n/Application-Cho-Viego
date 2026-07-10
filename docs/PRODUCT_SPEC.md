# Product Specification

## Vision

Resume Tailor helps job seekers create one-page, role-specific resumes that remain truthful to their actual experience. It behaves as a resume strategist: it decides what deserves space, explains those tradeoffs, and produces content ready for a deterministic renderer.

## Target users

The initial user is an engineering student applying for internships, co-ops, and entry-level roles. The data model supports any job seeker and future multi-user accounts.

## Core workflow

1. A user creates a master profile from one or more resumes and supporting evidence.
2. The user selects a versioned template and supplies a job description, optionally with a job URL.
3. The system classifies the role, optionally gathers company context, and evaluates candidate evidence.
4. The decision engine allocates the one-page content budget and returns a tailored structured resume plus a decision report.
5. The renderer applies only approved structured content to the chosen template and exports DOCX/PDF.
6. The user reviews reasoning and claims before downloading or saving a version.

## Success criteria

- Every resume claim is supported or explicitly labeled as safe inferred wording.
- Every material inclusion, removal, or reorder decision has an understandable reason.
- A result is reproducible from its profile version, posting snapshot, template version, and model configuration.
- The final layout is controlled by templates and remains stable across generations.

## Non-goals for the MVP

- Autonomous job applications, fabricated achievements, free-form document styling, or unreviewed web scraping.

