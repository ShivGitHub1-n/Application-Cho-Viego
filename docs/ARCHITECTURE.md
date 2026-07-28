# Architecture

## Design

The codebase uses a lightweight clean architecture. It favors explicit Python protocols and dependency injection over frameworks or agent orchestration.

```text
Streamlit UI / FastAPI API
          |
   application services
          |
 domain models + decision policy
          |
 repository / AI / research / renderer ports
          |
JSON or SQLite / Gemini adapter / approved web clients / python-docx
```

## Layers

| Layer | Responsibility | Must not do |
| --- | --- | --- |
| `domain` | Typed concepts, invariants, truthfulness classification | Call APIs, read files, or render documents |
| `application` | Use cases and orchestration | Depend on FastAPI, Streamlit, or vendor SDKs |
| `ports` | Interfaces for external capabilities | Contain implementation details |
| `infrastructure` | Implement ports and configuration | Hold product decision policy |
| `api`, `frontend` | Validate/display requests and responses | Reimplement business logic |

## Key boundaries

- `MasterProfileRepository` owns profile persistence; SQLite and PostgreSQL are interchangeable implementations.
- The Career Evidence layer owns facts, provenance, demonstrated capabilities, declared skills, preferences, and profile versions.
- The Opportunity Optimization layer owns posting analysis, strategy, content selection, claim proposals, and decision explanations. These are modules, not separately deployed MVP services.
- `ResumeOptimizer` creates a `TailoringPlan` from profile, posting, and template constraints. Its algorithm is replaceable.
- `ResumeLanguageModel` exposes only opportunity analysis, composition recommendation, bullet rewriting, and shortening. Provider adapters return typed schemas and never receive authority over evidence, budgets, or rendering.
- `ResumeRenderer` maps structured resume content to a versioned template; it owns all styling.
- `CompanyResearcher` returns sourced company facts, never candidate claims.

## Data flow

1. Ingest a document into a draft `MasterProfile`; retain source spans where possible.
2. Normalize a job posting into title, responsibilities, requirements, and optional company context.
3. Build one recommended strategy and decision plan before requesting prose.
4. Validate every proposed claim against evidence and policy; strong inferences require user approval.
5. Render only validated structured content. An exact DOCX page-count provider determines the strict one-page invariant; PDF rendering remains a separate delivery concern.

The MVP persists the reviewed `MasterProfile` through the `MasterProfileRepository` port; the local implementation stores schema-validated JSON payloads in SQLite and replaces records by stable profile ID. A missing or corrupt record is reported explicitly. Tailoring plans and generated documents remain derived session state and are invalidated when the active profile or pasted posting changes. A `TailoringPlan` carries the posting and template constraints used to create it. Before document writing, the application reconstructs the deterministic plan from those inputs and the supplied profile, then rejects changes to output-bearing plan fields. This protects both API and UI document construction without treating a client-supplied support label or claim as trusted. It is not a substitute for server-side plan storage or signed plans once plans need durable identity, authorization, or cross-version compatibility.

Gemini composition is advisory and evidence-grounded. The application may narrow or reorder optimizer-selected candidates, and a separate rewrite operation may create new candidate wording by combining or splitting same-entry evidence. Both paths are replayed through typed deterministic evidence, support, entry, grouping, bullet-count, section-budget, total-line, and entry-overhead checks. Strongly implied wording and demonstrated skills remain review-pending until approval. Reconciled plans retain their evidence links so the plan-integrity gate can reconstruct and verify them before writing.

## Job discovery MVP

Job discovery follows the same boundaries. Provider-neutral domain models and
ports own normalized postings, search preferences, eligibility, deterministic
deduplication, scoring, discovery runs, and saved jobs. Application services
orchestrate suggestion, confirmation, refresh, saving, and availability checks;
they do not import FastAPI, Streamlit, provider SDKs, or SQLite details.

Infrastructure contains the Greenhouse and Lever adapters and a curated source
registry. The registry is empty by default and only explicitly configured,
enabled Greenhouse or Lever sources are eligible for automatic discovery.
Unsupported sources are not scraped. Connector failures remain structured
warnings or explicit source errors; a transport failure is not treated as
confirmed unavailability.

The deterministic pipeline normalizes provider records, deduplicates them,
builds one canonical requirement set, evaluates structural eligibility and
title-first role relevance, allocates profile evidence through a single-use
ledger, and assigns typed fit grades before reaching the current persistence
boundary. Explanations retain exact posting and profile authority. Location
handling uses only the approved city, region, country, and work-arrangement
fields; it does not geocode or calculate radius or distance. SQLite stores
preferences, discovered jobs, runs, recommendations, and saved-job records
through repository ports, using the same application database as the existing
profile store. Recommendation/feed persistence uses the transactional Batch 3
schema-version-2 migration described below.

FastAPI exposes typed discovery contracts and delegates to application
services. Streamlit is a thin delivery layer that presents editable confirmed
preferences, explicit refresh status, recommendations, and saved-job actions;
it does not contain eligibility, scoring, persistence, or connector logic.
Saved jobs contain an immutable normalized posting snapshot. Availability checks
update only availability metadata and their check timestamp, retaining the
snapshot and unavailable saved rows. The UI reports the empty registry exactly
as `No approved job sources are configured` and does not present it as a
successful empty search.

Connector behavior is tested primarily with offline Greenhouse and Lever
fixtures. Live source smoke testing is opt-in, uses the
`job_source_integration` pytest marker, requires explicit approved source
configuration, and is never part of ordinary offline test execution.

## Evolution

Use local JSON or SQLite for MVP. Add a database adapter, object storage adapter, and authentication dependency without moving domain or application code. FastAPI is the stable product API; Streamlit is a replaceable client.

## Architectural risks and assumptions

- PDF-to-structured-resume extraction is unreliable; parsed data must be user-reviewable before use.
- One-page fit needs template-specific measurement; initial estimates are advisory until the renderer can measure actual output.
- AI inference needs conservative policy and evidence citations to remain trustworthy.
- Company research must respect source terms, permissions, rate limits, and clear provenance.
- DOCX-to-PDF conversion varies by platform; production export needs a chosen conversion service or runtime.

## Batch 3 job-discovery boundaries

Tailored queries may carry local profile and confirmed-preference references to
the application layer; Explore queries carry only approved sectors and
sanitized search controls. Conversion to `ProviderJobQuery` is an explicit
allow-list: provider payloads never contain resume text, profile evidence,
scores, explanations, gaps, or career-interest prose. Provider capabilities
declare pushdown support, while the retrieval service records pushed-down,
local, unsupported, and unrequested filters. Unsupported filters never
silently broaden a query.

Retrieval is bounded by source, page, record, timeout, and retry settings. It
protects against repeated cursors and preserves successful sources when
another source fails. Normalization and deduplication retain source-qualified
identity, canonical URL authority, aliases, and complete provenance
independently of provider or page order. Every deduplicated candidate is
evaluated by the frozen evaluator. Tailored and Explore feed ordering and
visibility are applied after evaluation; ordinary feeds hide Don't Match and
hard-ineligible items but report `excluded_count`, and excluded endpoints
return retained evaluations without recomputation.

Schema version 2 is the single permanent feed migration. Version-1
recommendations remain readable as explicitly earlier-policy records, and
saved-job snapshots remain immutable. FastAPI exposes independent Tailored and
Explore refresh/read/excluded-feed contracts; `/job-discovery/refresh` is a
Tailored compatibility alias. The policy is development-gate-approved but not
locked-release-certified; the locked split remains sealed. The dedicated Jobs
UI belongs to Batch 4.

## Batch 3.5 autonomous source discovery

The approved company registry compiles into immutable provider or first-party
runtime sources. Rocket Lab is explicit `FIRST_PARTY` and uses the employer
detail URL as stable identity. Static-first sitemap/index/detail retrieval,
bounded JobPosting JSON-LD, and declarative HTML extraction feed the existing
retrieval, normalization, deduplication, evaluator, and Tailored/Explore path.
Application URLs are terminal provenance and are never fetched.

Browser fallback is an injected isolated capability only after an explicit
`browser_required` result for an audited first-party plan. Static HTTP pins
validated destination IPs; browsers retain a DNS TOCTOU residual risk because
the browser resolves sockets. Host/path/resource interception, isolated
contexts, bounded requests/actions/render time, and close-on-failure bound that
risk. The real adapter is Playwright-backed, prefers Playwright-managed
Chromium, and otherwise locates only trusted system Chrome/Edge paths; registry
data cannot inject executable paths, launch arguments, scripts, or environment
variables. Schema version 3 stores runtime observations, separate content and
source-state fingerprints, aliases, and locks without copying registry
authority, raw HTML, credentials, or full descriptions. Broad/force refresh is
CLI-only and source visibility is read-only health data.

Production source-refresh hardening composes one fail-closed robots checker
into static and browser first-party retrieval without network work during
startup. The orchestrator uses sanctioned Explore queries and hands retrieved
records to the existing normalization, frozen evaluation, feed, alias, and
transactional SQLite persistence boundary. Runtime state stamps compiled
audit/plan/profile identity, separate content and source-state fingerprints,
bounded cadence/backoff, and next eligibility. A global deadline prevents new
source starts after expiry. Static and rendered indexes consume the same
audited declarative extraction profile; browser action limits count actual
attempts and stop unchanged bounded load-more DOM. CLI force bypasses cadence
only.
