# Roadmap

## Phase 0 — Foundation (current)

- Establish clean architecture, documentation, contracts, and local development tooling.
- Keep persistence and integrations replaceable while the product model stabilizes.

## Phase 1 — Resume Tailoring Engine

- Parse master resumes into a reviewable structured profile.
- Analyze job descriptions and detect role family automatically.
- Rank experiences, projects, skills, and coursework with evidence citations.
- Generate structured resume content and an explanation, never document formatting.

## Phase 2 — Template Engine

- Support versioned DOCX templates with explicit field mapping.
- Render deterministic DOCX output and export PDF.
- Add one-page measurement and iterative content-budget recommendations.

## Phase 3 — Frontend

- Add profile/template uploads, job input, reasoning review, and downloads.
- Preserve the API as the product boundary so Streamlit can later be replaced by React/Next.js.

## Phase 4 — Company Intelligence

- Research only allowed public sources when a URL is supplied.
- Extract verifiable company context and keep it separate from candidate evidence.

## Phase 5 — Cover Letters

- Produce evidence-backed, company-aware letters from the same structured inputs.

## Phase 6 — Job Discovery

- Add compliant job-source connectors, fit ranking, and direct handoff to tailoring.

## Phase 7 — Application Management

- Add application records, version history, tracking, analytics, and interview preparation.

## Architecture evolution

Start with JSON/SQLite repositories. Introduce PostgreSQL through repository implementations, object storage through a document-store port, and authentication through a current-user dependency without changing domain services.

