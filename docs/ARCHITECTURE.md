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
5. Render only validated structured content. Authoritative PDF measurement determines one-page fit.

## Evolution

Use local JSON or SQLite for MVP. Add a database adapter, object storage adapter, and authentication dependency without moving domain or application code. FastAPI is the stable product API; Streamlit is a replaceable client.

## Architectural risks and assumptions

- PDF-to-structured-resume extraction is unreliable; parsed data must be user-reviewable before use.
- One-page fit needs template-specific measurement; initial estimates are advisory until the renderer can measure actual output.
- AI inference needs conservative policy and evidence citations to remain trustworthy.
- Company research must respect source terms, permissions, rate limits, and clear provenance.
- DOCX-to-PDF conversion varies by platform; production export needs a chosen conversion service or runtime.
