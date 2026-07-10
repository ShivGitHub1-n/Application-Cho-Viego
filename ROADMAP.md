# Roadmap

## Phase 0 — Foundation (complete)

- Establish clean architecture, documentation, contracts, and local development tooling.
- Keep persistence and integrations replaceable while the product model stabilizes.

## Phase 1 — Resume Tailoring Engine (in progress)

- Implemented: reviewed-profile inputs, embedded/firmware opportunity analysis, deterministic evidence selection, decision reports, claim approval gating, and one managed template.
- Next: parse master resumes into reviewable profiles, add bounded LLM wording proposals, and expand the expert-reviewed evaluation set.

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
