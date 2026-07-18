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
- The optimizer's `OpportunityAnalyzer` dependency is the single role-classification boundary for resume tailoring. When explicitly enabled, the hybrid analyzer may resolve a validated Gemini primary family over deterministic posting signals; default and fallback behavior remains the deterministic analyzer.
- `ResumeLanguageModel` exposes typed profile extraction, role classification, opportunity analysis, composition recommendation, bullet rewriting, shortening, and cover-letter drafting. Provider adapters return typed schemas and never receive authority over evidence, budgets, or rendering.
- `ResumeRenderer` maps structured resume content to a versioned template; it owns all styling.
  Template V1 opens the packaged, content-neutral `template_v1.docx` and
  populates or clones its semantic OOXML prototypes. The accompanying JSON
  layout profile is diagnostic only and is not a formatting source for the
  default renderer.
- `CompanyResearcher` returns sourced company facts, never candidate claims.

## Data flow

1. Ingest a document into a draft `MasterProfile`; retain source spans where possible.
2. Normalize a job posting into title, responsibilities, requirements, and optional company context.
3. Build one recommended strategy and decision plan before requesting prose.
4. Validate every proposed claim against evidence and policy; strong inferences require user approval.
5. Render only validated structured content by populating the packaged static
   DOCX template. An exact DOCX page-count provider determines the strict
   one-page invariant; PDF rendering remains a separate delivery concern.

The MVP persists the reviewed `MasterProfile` through the `MasterProfileRepository` port; the local implementation stores schema-validated JSON payloads in SQLite and replaces records by stable profile ID. A missing or corrupt record is reported explicitly. Tailoring plans and generated documents remain derived session state and are invalidated when the active profile or pasted posting changes. A `TailoringPlan` carries the posting and template constraints used to create it. Before document writing, the application reconstructs the deterministic plan from those inputs and the supplied profile, then rejects changes to output-bearing plan fields. This protects both API and UI document construction without treating a client-supplied support label or claim as trusted. It is not a substitute for server-side plan storage or signed plans once plans need durable identity, authorization, or cross-version compatibility.

Gemini composition is advisory and evidence-grounded. The application may narrow or reorder optimizer-selected candidates, and a separate rewrite operation may create new candidate wording by combining or splitting same-entry evidence. Both paths are replayed through typed deterministic evidence, support, entry, grouping, bullet-count, section-budget, total-line, and entry-overhead checks. Strongly implied wording and demonstrated skills remain review-pending until approval. Reconciled plans retain their evidence links so the plan-integrity gate can reconstruct and verify them before writing.

Gemini role classification is a separate opt-in tailoring concern. Production
wiring injects the configured adapter, model/cache identity, in-memory cache,
and confidence threshold into the hybrid opportunity analyzer. Only a validated
primary family already supported by deterministic posting signals can change
the resolved family. Deterministic signals remain the sole optimization signal
and evidence authority. Typed, sanitized diagnostics travel with the role
decision for delivery surfaces; raw prompts, payloads, credentials, exceptions,
and semantic advisory fields do not.

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
applies eligibility rules, and calculates profile-fit scores and labels before
persisting results. Location handling uses only the approved city, region,
country, and work-arrangement fields; it does not geocode or calculate radius
or distance. SQLite stores preferences, discovered jobs, runs,
recommendations, and saved-job records through repository ports, using the
same application database as the existing profile store.

Profile fit is separate from recommendation desirability. Its occupational
core scores demonstrated technical evidence, required responsibility and
capability coverage, preferred occupational evidence, and transferable
responsibility evidence. Education and level support are admitted only in
proportion to the occupational core, then the raw fit is normalized against
the documented 90-point maximum. Company and broad user preferences,
location and work arrangement, authorization, recency, and posting
completeness remain outside profile fit. Requirement identity is a structured
semantic tuple of category, normalized term, and importance; exact duplicate
requirements are scored once. Evidence provenance records component ownership
and evidence-to-requirement pairs, allowing one evidence item to support
distinct requirements without duplicate pair credit.

FastAPI exposes typed discovery contracts and delegates to application
services. Streamlit is a thin delivery layer that presents editable confirmed
preferences, explicit refresh status, recommendations, and saved-job actions;
it does not contain eligibility, scoring, persistence, or connector logic.
Saved jobs contain an immutable normalized posting snapshot. Availability checks
update only availability metadata and their check timestamp, retaining the
snapshot and unavailable saved rows. The UI reports the empty registry exactly
as `No approved job sources are configured` and does not present it as a
successful empty search.

The Streamlit shell exposes one selected workflow at a time: Home / Workspace,
Profile, Tailor Resume, Cover Letter, Job Search, and Settings / Diagnostics.
Session state carries reviewed profile and generated-workflow objects across
navigation. Structured profile controls are primary; raw JSON and long
diagnostics are collapsed delivery affordances. Job Discovery dependencies are
constructed only when Job Search is selected and a reviewed profile is loaded.

User-owned SQLite state is rooted in the centrally configured application data
directory documented in [APPLICATION_DATA.md](APPLICATION_DATA.md). Profile and
Job Discovery repositories share that database path. Infrastructure dependency
construction may perform an allowlisted compatibility import from one known
repository-local database; domain/application code remains unaware of paths or
SQLite.

Connector behavior is tested primarily with offline Greenhouse and Lever
fixtures. Live source smoke testing is opt-in, uses the
`job_source_integration` pytest marker, requires explicit approved source
configuration, and is never part of ordinary offline test execution.

## Evolution

Use local JSON or SQLite for MVP. Add a database adapter, object storage adapter, and authentication dependency without moving domain or application code. FastAPI is the stable product API; Streamlit is a replaceable client.

## Architectural risks and assumptions

- PDF-to-structured-resume extraction is unreliable; parsed data must be user-reviewable before use.
- Exact page count needs a configured DOCX provider. Template V1 utilization estimates are diagnostic and never substitute for exact verification.
- AI inference needs conservative policy and evidence citations to remain trustworthy.
- Company research must respect source terms, permissions, rate limits, and clear provenance.
- DOCX-to-PDF conversion varies by platform; production export needs a chosen conversion service or runtime.
