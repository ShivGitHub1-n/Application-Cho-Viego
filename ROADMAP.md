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

- Completed MVP: provider-neutral Greenhouse and Lever connectors, offline
  fixture coverage, deterministic normalization, deduplication, eligibility,
  fit scoring, explicit match labels, refresh orchestration, SQLite discovery
  persistence, typed FastAPI delivery, thin Streamlit discovery delivery, and
  immutable saved-job snapshots with manual availability checks.
- Production source coverage remains empty by default. Employers are added
  only through explicitly approved curated registry configuration; unsupported
  sources are not scraped.
- Live source checks remain opt-in under the `job_source_integration` pytest
  marker and require explicit approved configuration.

### Batch 3 complete

- Added sanitized Tailored and Explore query contracts, provider capability
  declarations, bounded paged retrieval, partial-success source outcomes, and
  provider-safe serialization.
- Strengthened canonical identity, cross-provider deduplication, aliases, and
  provenance; retained unknown timestamp authority instead of inventing dates.
- Persisted every frozen-evaluator result, including excluded evaluations, with
  deterministic feed ordering and schema-version-2 atomic refresh persistence.
- Added typed feed refresh/read/excluded-feed APIs while retaining
  `/job-discovery/refresh` as the Tailored compatibility alias.
- Greenhouse and Lever remain the only approved connectors. Expansion beyond
  them is deferred by the provider audit. The dedicated Jobs UI is Batch 4.

### Batch 4 — dedicated Jobs experience

- Implemented a dedicated navigable Streamlit Jobs page with Tailored for you,
  Explore sectors, Saved, and Preferences sections.
- Added a typed application façade for reviewed profiles, profile-scoped feed
  reads, refreshes, semantic recommendation views, saved snapshots,
  availability checks, and tailoring handoffs.
- Normal Jobs UI shows Excellent/Good/Weak/Don't Match semantics through an
  accessible fit meter; numeric diagnostics remain absent. Eligibility and
  provisional state are independent, and excluded results require explicit
  expansion.
- Added scoped theme-aware Jobs styling, responsive split-panel/stacked feed
  behavior, a deterministic offline AppTest/browser harness, and a manual
  browser checklist. The user completed final manual browser validation in
  the populated harness and real application. Batch 4 is merged in the current
  baseline; its manual evidence remains the visual baseline for later changes.

### Batch 5 - final Jobs hardening

- Verify retrieval, persistence, migrations, saved snapshots, API delivery,
  Streamlit delivery, source/security boundaries, and historical compatibility
  with explicit offline tests.
- Enforce deterministic source, identity, feed, serialization, and refresh
  behavior across supported hash seeds.
- Record actual validation and manual evidence without claiming a locked
  benchmark result or new browser evidence.
- Batch 5 adds no new Jobs product feature. The next step is a separate
  independent review-only pass.

## Phase 7 — Application Management

- Add application records, version history, tracking, analytics, and interview preparation.

## Deferred job-discovery follow-up

- Keep deferred: background scheduling, automatic application submission,
  application-status tracking, authentication, LinkedIn or Indeed scraping,
  arbitrary career-page scraping, additional ATS providers, paid search
  providers, geocoding and radius calculations, Gemini job-fit analysis, and
  model-assisted finalist explanations.

## Architecture evolution

Start with JSON/SQLite repositories. Introduce PostgreSQL through repository implementations, object storage through a document-store port, and authentication through a current-user dependency without changing domain services.

## Batch 3.5 status

Implemented immutable provider/first-party compilation, Rocket Lab static
retrieval, bounded sitemap/XML and JSON-LD boundaries, constrained HTML
extraction, stable employer-detail identity, unified retrieval, schema-v3
runtime lifecycle state, fingerprints, aliases, locks, deterministic due
selection, CLI-only operations, and read-only source-health routes. The shared
browser fallback seam, Playwright adapter, and unavailable-runtime diagnostic
are implemented. Production first-party composition enforces robots policy,
refreshes through the existing evaluator/feed persistence boundary, stamps
compiled lifecycle identity and cadence state, applies a global run deadline,
enforces audited extraction profiles, and counts actual browser action attempts.
The real local browser gate was externally verified with Playwright `1.55.0`
and managed Chromium `140.0.7339.16` (build v1187): three integration tests
passed. Implementation is complete and merged in the current baseline. Its
provider, first-party, lifecycle, and source-health contracts are covered by
the Batch 5 offline hardening pass; a separate independent review remains the
next gate.
