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

## Evolution

Use local JSON or SQLite for MVP. Add a database adapter, object storage adapter, and authentication dependency without moving domain or application code. FastAPI is the stable product API; Streamlit is a replaceable client.

## Architectural risks and assumptions

- PDF-to-structured-resume extraction is unreliable; parsed data must be user-reviewable before use.
- One-page fit needs template-specific measurement; initial estimates are advisory until the renderer can measure actual output.
- AI inference needs conservative policy and evidence citations to remain trustworthy.
- Company research must respect source terms, permissions, rate limits, and clear provenance.
- DOCX-to-PDF conversion varies by platform; production export needs a chosen conversion service or runtime.
