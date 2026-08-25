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
- `ResumeEvidenceRetriever` returns a typed, bounded view over the complete
  current reviewed profile. The in-process implementation combines normalized
  lexical features, structured requirement authority, evidence relationships,
  intrinsic strength, short-token corroboration, and credible technical
  adjacency. A future lexical-plus-embedding or external RAG adapter can
  implement the same contract without changing the planner or writer.
- The optimizer's `OpportunityAnalyzer` dependency is the single role-classification boundary for resume tailoring. When explicitly enabled, the hybrid analyzer may resolve a validated Gemini primary family over deterministic posting signals; default and fallback behavior remains the deterministic analyzer.
- `ResumeLanguageModel` exposes typed profile extraction, role classification,
  application strategy, legacy advisory analysis, bullet rewriting, shortening,
  and cover-letter drafting. Provider adapters return typed schemas. The
  application strategist has semantic portfolio authority only over supplied
  reviewed entry/evidence IDs; it never receives factual, structural,
  pagination, persistence, or rendering authority.
- `ResumeRenderer` maps structured resume content to a versioned template; it owns all styling.
  Template V1 opens the packaged, content-neutral `template_v1.docx` and
  populates or clones its semantic OOXML prototypes. The accompanying JSON
  layout profile is diagnostic only and is not a formatting source for the
  default renderer.
- The live résumé editor starts from an immutable generated artifact and creates a separate,
  application-scoped `ResumeEditorRevision`. Editor operations preserve evidence IDs and
  canonical parents, validate manual wording and reviewed skills deterministically, and never
  call semantic planning or writing providers. Applying staged edits renders Template V1 once,
  converts that DOCX to the visible PDF preview, and verifies the exact PDF page tree without
  automatic content reduction. Export requires approval of the exact current revision
  fingerprint and returns its stored DOCX bytes. See [RESUME_EDITOR.md](RESUME_EDITOR.md).
- Composed metadata remains a direct reference to authoritative reviewed entry
  fields. A domain fidelity check rejects accumulated ranges, repeated
  output-bearing metadata, and duplicate selected entry IDs before final
  handoff and again before static Template V1 rendering. It reports source date
  precision without normalizing or inferring missing calendar components.
- `DeterministicResumeComposer` selects exact reviewed profile atoms after plan
  integrity validation. It depends on a page-fit evaluation port; the
  Template V1 infrastructure adapter renders and measures candidate documents.
  Posting requirements and evidence relationships are typed domain models.
  Experiences and projects enter final search as bounded, coherent depth
  frontiers; opening any entry pays its metadata cost and every deeper package
  remains a marginal decision in the same evidence-quality search. Legacy
  flat reviewed skills may be regrouped into bounded display-only semantic,
  non-contiguous groups with exact per-skill source-index provenance. Template
  V1 row width is estimated before adding a value; canonical profile data is
  unchanged.
- `BoundedCompanyResearchService` implements the company-research boundary for
  cover letters. It returns dated, attributable facts from the validated
  posting, explicit user facts, and at most three approved sources; it never
  returns candidate claims. The HTTP infrastructure adapter enforces HTTPS,
  first-party domain, public-address, redirect, content-type, and response-size
  restrictions.

## Data flow

1. Ingest a document into a draft `MasterProfile`; retain source spans where possible.
2. Normalize a job posting into title, responsibilities, requirements, and optional company context.
3. Build one recommended strategy and decision plan before requesting prose.
4. Validate every proposed claim against evidence and policy; strong inferences require user approval.
5. Compose validated reviewed atoms through bounded candidate search and render
   every evaluated state through the packaged static DOCX template.
6. Require exact DOCX page count as the one-page authority for a final artifact.
   Retain provider failures and fail closed when exact pagination is
   unavailable. Explicit non-final planning calls may return an unverified
   deterministic occupancy estimate; PDF rendering remains a separate delivery
   concern.

The MVP persists the reviewed `MasterProfile` through the `MasterProfileRepository` port; the local implementation stores schema-validated JSON payloads in SQLite and replaces records by stable profile ID. A missing or corrupt record is reported explicitly. Tailoring plans and generated documents remain derived session state and are invalidated when the active profile or pasted posting changes. A `TailoringPlan` carries the posting and template constraints used to create it. Before document writing, the application reconstructs the deterministic plan from those inputs and the supplied profile, then rejects changes to output-bearing plan fields. This protects both API and UI document construction without treating a client-supplied support label or claim as trusted. It is not a substitute for server-side plan storage or signed plans once plans need durable identity, authorization, or cross-version compatibility.

When semantic composition is enabled, Gemini application strategy is
evidence-grounded and portfolio-authoritative. One typed strategist request
receives the normalized full posting, every eligible confirmed evidence atom,
authoritative entry metadata, deterministic evidence/requirement relationships,
reviewed skill context, and structural bounds. It returns an application thesis,
ordered role priorities, selected entries, desired depth, selected and fallback
evidence IDs, a bounded ranked underfill-expansion reserve, global evidence
priority, and meaningful low-priority omissions. Same-entry fallback evidence
is retained automatically; the explicit reserve is the bounded way to authorize
a new entry when it adds distinct portfolio value. When materially useful unused
evidence exists, the same strategist call may return independent reserve actions
so exact pagination can reject one without exhausting the strategy. Reserve size
is never a target: the provider schema has no minimum and caps the optional bench
at eight actions. Deterministic validation also derives a bounded same-entry depth
reserve from direct, adjacent, or complementary reviewed evidence inside entries
Gemini already selected for the core. That supplies page-fit depth without asking
Gemini to weaken the application story or populate a quota.
The deterministic validator removes unknown, duplicated, cross-entry,
unconfirmed, structurally impossible, title-conflicting, or unsupported
requirement references item by item. A valid remainder survives; the system does
not replace it with unrelated heuristic selections.

The validated `ApplicationStrategyPlan` is persisted on the tailoring plan and
structured resume and is included in artifact identity. Its core selection
defines the only bullet evidence eligible for the writer. Its core plus validated
reserve defines the only evidence eligible for page fitting.
This fixes the former handoff where an advisory recommendation saw only already
narrowed deterministic candidates, then the composer reopened the full profile
and re-decided the portfolio. When the strategist is unavailable or its valid
remainder is empty, the existing deterministic retrieval, package frontier, and
page-fit search remains the explicit fallback.

Resume writing makes one bounded batch over only strategist-selected evidence.
Validated variants are cached and reused during page fitting. Source wording
remains a first-class candidate and wins when a rewrite is not materially
clearer, tighter, or more readable. Generated wording continues to derive all
relevance and requirement authority from the reviewed evidence bundle.

Within an already aligned entry, the strategist chooses the evidence
abstraction that best proves the posting's owned work. A hands-on implementation
or test responsibility can therefore favor concrete reviewed firmware, device,
interface, control, or physical-test evidence over a more abstract architecture
summary; an architecture role can make the opposite choice. This remains
provider judgment over supplied evidence IDs, not a deterministic role rule.
The versioned strategist request carries the prompt contract version so a prompt
change cannot silently reuse an older cached strategy.

The writer may express an already-proven concept using recognizable terminology
from the posting. This semantic normalization happens after evidence selection
and is accepted automatically only when a local, typed entailment check proves
the term from reviewed source text or reviewed structured facts. Proof may use a
direct reviewed fact or a bounded compositional rule whose required technical
dimensions are all present. Ordinary linguistic normalization remains safe but
does not receive material-rewrite authority from this layer. For
example, authored C++ control code on an STM32 can support `embedded firmware`;
STM32 interface integration without code authorship cannot. The target term
must appear in the authoritative posting as well as the rewrite, and the normal
technology, metric, outcome, ownership, title, provenance, and cross-entry
validators still run. An unproven semantic addition remains review-required or
is rejected. This does not add a provider call or create pre-selection generated
evidence.

Direct code contribution also remains contribution: reviewed STM32-family
microcontroller code, including a specific part such as STM32F4, may entail the
term `embedded firmware` when the posting uses it, but the rewrite must preserve
the source's contribution scope and cannot upgrade it to development ownership.
The writer may materially restructure and foreground supported technical
substance rather than stop at compression or synonym swaps. For a hands-on
posting it may remove unnecessary supervisory framing when the reviewed
technical contribution remains specific and the posting does not request
leadership; explicit titles, technologies, metrics, outcomes, and ownership
remain protected.

Each writer group now carries `entailed_target_terms`, computed locally from its
reviewed source bundle and matched posting requirements. This is a post-selection
editorial hint, not evidence: it helps the writer use a proven target term rather
than improvise a near-synonym, while the validator independently recomputes the
same entailment from the returned text. It adds no provider call and cannot alter
the selected evidence IDs.

The hybrid authority split is explicit:

- the application strategist may choose a semantic portfolio only from supplied
  reviewed entry/evidence IDs and cannot create facts;
- the Gemini writer may return only authorized source evidence IDs, rewritten
  text, and a bounded length class through a shallow transport contract;
- the adapter maps those IDs back to the shortlist and reconstructs the rich
  internal variant, including entry ownership and claim provenance, locally;
- evidence-ID mapping is per rewrite: an unknown, duplicate, cross-entry, or
  internally invalid item is rejected without discarding safely reconstructed
  siblings; only a top-level provider-contract failure invalidates the batch;
- deterministic validation rejects unsupported identifiers, numbers,
  technologies, outcomes, ownership expansion, cross-entry claims, or
  provenance loss;
- deterministic semantic normalization may admit job terminology only when the
  reviewed same-entry bundle proves every required component; the admitted term
  is recorded on the typed variant for diagnostics and writing comparison;
- a variant that introduces content-bearing terminology which deterministic
  checks cannot prove is quarantined for bounded semantic review rather than
  rendered automatically;
- the layout optimizer selects only validated or explicitly approved variants,
  compares them with reviewed source text, and derives every variant's
  relevance, requirement coverage, evidence relationship, and technical
  signals from its complete reviewed same-entry source bundle. Generated word
  order may affect readability and line fit, but cannot create selection
  authority. Explicit approval makes a review-required variant eligible; it
  does not force that wording to replace a stronger source candidate;
- in Gemini strategy mode, deterministic page fitting first renders the core
  strategy. Below the 88% preferred floor, it may add only validated ranked
  reserve actions that clear the same established material marginal-value floor
  used by ordinary composition, stopping at 88%-93%,
  the 95% acceptable ceiling, overflow, or reserve exhaustion. Rollback trims
  excess depth across core entries before removing an entire strategist-selected
  entry, then removes optional, medium, high, or critical evidence only when
  one-page fit requires it. Every material-value sibling remains eligible for the
  bounded exact-pagination batch, so an estimated winner that becomes two pages
  cannot hide a later fitting action. Within equal priority, readability,
  redundancy, line cost, and quality remain deterministic;
- in fallback mode, the existing optimizer remains authoritative for final entry
  selection and its full deterministic package frontier;
- deterministic code remains authoritative for structure, duplication,
  metadata-plus-bullet page cost, exact page fit, and export in both modes;
- Template V1 alone owns DOCX formatting.

In Gemini strategy mode, technical-skill display relevance is bounded by the
same strategy-compatible reviewed source evidence (core plus reserve). A skill
named in that reviewed evidence may anchor its canonical source row even when
other members of the row are unrelated; those unrelated members cannot enter
merely because they are demonstrated elsewhere in the full profile. The full
profile remains truth authority, while the validated strategy boundary supplies
application relevance. Deterministic fallback retains its established skill
composition behavior.

Cache identity includes profile and posting fingerprints, evidence bundles,
ordered shortlist IDs, exact source text, prompt, writing-policy and contract
versions, relevant writer flags, provider, and model. Page-fit thresholds are
deliberately excluded, so a validated wording variant is not regenerated merely
because a layout budget changes. Normal strategist-enabled generation makes one
strategist request and one writer request. The pair shares one additional repair
request, used only when a typed provider response is malformed or the bounded
portfolio-dominance audit detects a catastrophic substitution. Timeouts, network
failures, grounding rejections, and safety failures
do not enter a retry loop. The Gemini SDK retry count is explicitly one attempt.
The strategist has a dedicated 4,096-token output ceiling so the bounded typed
portfolio can coexist with the core plan without changing writer, extraction, or
general provider budgets. If a new-entry reserve is Pareto-dominated by a wholly
omitted entry with two independently direct reviewed evidence atoms, one bounded
same-request-contract repair may reconsider the portfolio. The comparison uses
only the top two direct atoms and requirement breadth, so profile volume alone
cannot trigger it.
Provider, parsing, validation, request, repair, and cache diagnostics are typed.
Per-rewrite diagnostics retain only the authorized evidence IDs and reviewed
source used by the smoke route, reconstructed claim, mapping outcome, typed
grounding codes, normalized unsupported terms, ownership/metric/outcome/scope
comparisons, final validation state, and aggregate batch effect. A mixed batch
is reported as `writer_partially_succeeded` when a validated sibling reaches
selection; complete source fallback requires zero usable validated rewrites.
With all LLM features disabled, no provider is constructed or called.

Résumé artifacts expose typed status for opportunity planning, skill
recommendation, composition recommendation, bullet writing, and final
deterministic recomposition, including bounded per-stage call counts. These
statuses describe participation rather than authority: deterministic
recomposition and exact page fit remain final. Streamlit fingerprints the
sanitized provider/model/feature configuration and rebuilds its session-scoped
service when that configuration changes, avoiding a provider-disabled service
surviving an environment update without retaining credentials in session state.

Authoritative entry metadata also bounds title claims. If reviewed source prose
asserts a different title or seniority, the canonical profile evidence remains
untouched, the conflicting phrase is removed from relevance authority, and a
sanitized claim-integrity diagnostic is emitted. In strategist mode, a
deterministic derived display candidate deletes only that conflicting self-title
so the supported technical remainder stays usable without rendering title
inflation. A generated variant that repeats or introduces the conflict is
rejected; approval cannot override authoritative entry metadata.

Every material review-required variant in the bounded writer shortlist is
carried to the approval surface, including alternatives that were absent from
the pre-writer source seed. Approval invalidates the artifact fingerprint and
recomposition compares the now-eligible wording with its source and the rest of
the portfolio without another provider call.

The Streamlit production flow completes generation through one typed immutable
`GeneratedResumeArtifact`. Its identity covers the reviewed profile, normalized
posting, validated plan, approvals, Template V1 hash, composition and writing
contract versions, relevant feature flags, provider, and model. The artifact
retains the final structured resume, diagnostics, stage timings, call counts,
pagination status, and exact final DOCX bytes. Unrelated reruns reuse this
object; any material identity change invalidates it.

Streamlit attaches one active normalized posting as the application context.
Jobs may open either Resume Studio or Cover Letters from that same posting, and
Cover Letters may also establish a direct pasted context. Resume Studio can add
its accepted plan later; Cover Letters does not require that plan, résumé
generation, résumé approval, or résumé export. For backward compatibility, a
rerun that retained an accepted plan but lost the duplicate delivery key
recovers `TailoringPlan.posting` rather than rebuilding a posting from blank
fields.

The cover-letter application service also binds posting-authority fields on
every research request to that accepted posting before research, composition,
validation, artifact-currentness checks, or cache identity are evaluated.
Optional company fields may add user-approved or official-source inputs, but
cannot clear or replace the normalized title, description, URL, or posting
fingerprint.

Composition continues to compare the same bounded exact finalist portfolio,
but the infrastructure adapter renders the finalist batch and opens Word once
for all page counts. Final artifact rendering is deterministic and does not
paginate again. Streamlit download reads the stored bytes with a frontend-only
download action, so it performs no retrieval, planning, provider, validation,
composition, rendering, or pagination work.

The composition diagnostic retains safe stable IDs and already-computed scores
for each bounded page-fit finalist, including the selected finalist. A
sanitized production decision trace joins those diagnostics to profile,
posting, plan, artifact, configuration, and provider-call fingerprints without
including contact fields, reviewed evidence text, prompts, or credentials.
Its selected/rejected frontier uses a shared portfolio base and records only
stable IDs, requirement IDs, marginal values, redundancy, entry-activation
line cost, and rendered-line cost.

Cover letters follow the same immutable-artifact rule without duplicating the
resume engine. The application reuses reviewed-profile retrieval, provider
configuration, local grounding primitives, timing models, and approval
patterns, but selects narrative evidence independently of the generated
résumé. Cover-letter-only services own bounded company research, a typed
narrative plan with distinct story functions and concrete-detail prompts,
title-safe writer inputs, paragraph and whole-letter validation, quality-aware
finalist ordering, a preferred 82–90% page-utilization band, and an acceptable
76–94% band. The single normal draft request includes an internal full-draft
editing pass and a four-or-five-paragraph typed structure with distinct story
threads; no additional semantic-review call is introduced. Its factual brief
explicitly preserves metrics, ownership, causality, and outcomes. Cover-letter
drafting may use its own configured temperature while resume operations retain
their established setting. Narrative quality remains ahead of small density
differences. The deterministic emergency writer remains evidence-bound, can
deepen already selected narrative threads, and does not open a weaker entry
merely to obtain a third story or more page length. A compatible validated
application strategy supplies an entry-level semantic boundary, but Cover
Letters select their own facts and narrative within it; generation still does
not require a résumé artifact. The emergency writer uses sentence-scoped,
minimally transformed reviewed facts and simple transitions rather than
invented component-list bridges. Its bounded candidate ladder adds story depth
gradually, removes duplicate prose candidates, keeps the opening fact out of
the body, and coordinates closely related same-entry facts without adding a
new semantic claim. Its posting-only opening carries one explicit substantive
posting fact and the opening evidence as sentence-level authority instead of
relying on company/title metadata or an unused posting-fact bundle. A content-
or page-fit-failed result is a
diagnostic candidate only and cannot expose approval or DOCX download actions.
Exact final pagination remains mandatory. The provider returns a minimal
paragraph/ID contract; provenance, diagnostics, research attribution, cache
state, artifact identity, DOCX formatting, and page fitting are reconstructed
locally. Provider-visible cover-letter schemas exclude deterministic sentence
authority objects, which are reconstructed only by local fallback paths. See
[COVER_LETTER_WORKFLOW.md](COVER_LETTER_WORKFLOW.md).

The versioned writing policy is centralized in
`application/resume_writing_policy.py`. It establishes evidence, tone,
ATS-readable text, discouraged/prohibited phrase, semantic-equivalence, and
one-to-two-line guidance. It asks for recruiter-readable ownership, technical
method, and supported result framing, and permits an XYZ-style structure only
when all three parts are reviewed facts; it never requires or fabricates a
metric. Generated
three-line variants require review unless a clean grounded alternative is
available. Deterministic validation accepts broad configured linguistic
equivalents, rejects contradictions and protected-fact changes, and
review-gates otherwise unprovable narrower terminology. This version does not
add a second semantic-provider call: uncertain entailment remains
review-required and falls back to reviewed source text.

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

The Streamlit Precision Workbench shell exposes one selected workflow at a
time: Career Profile, Jobs, Resume Studio, and Cover Letters. Career Profile is
the default route.
Session state carries reviewed profile and generated-workflow objects across
navigation. Structured profile controls are primary; raw JSON and long
diagnostics are collapsed delivery affordances. Job Discovery dependencies are
constructed only when Jobs is selected and are reused for the Streamlit session;
ordinary navigation, filtering, and card selection do not rebuild HTTP clients or
repositories. The normal/advanced surface rules and future-editor-ready Resume Studio
shell are documented in [FRONTEND_WORKSPACE.md](FRONTEND_WORKSPACE.md).

Each generated artifact owns a fresh telemetry window even when Streamlit reuses
the long-lived service and writer cache. Exact-pagination attempts therefore
remain build-local (`0` or `1`); prior builds, reruns, deterministic estimates,
and DOCX renders cannot accumulate into that diagnostic. Approved-wording
rebuilds reuse validated writer variants, create a new immutable artifact, and
replace the session artifact only after successful byte rendering. Download
continues to return those exact stored bytes without generation work.

User-owned SQLite state is rooted in the centrally configured application data
directory documented in [APPLICATION_DATA.md](APPLICATION_DATA.md). Profile and
Job Discovery repositories share that database path. Infrastructure dependency
construction may perform an allowlisted compatibility import from one known
repository-local database; domain/application code remains unaware of paths or
SQLite.

The Streamlit composition root injects its already-created
`MasterProfileRepository` into Job Discovery service construction. The Jobs
faÃ§ade resolves each selected profile's `user_id` from that same reviewed-profile
authority for suggestions, preferences, feeds, saved jobs, and handoffs; delivery
code does not substitute a workspace-wide placeholder user.

Connector behavior is tested primarily with offline Greenhouse and Lever
fixtures. Live source smoke testing is opt-in, uses the
`job_source_integration` pytest marker, requires explicit approved source
configuration, and is never part of ordinary offline test execution.

### Batch 4 Jobs workspace

The dedicated Jobs route is composed from `JobsExperienceService`, a typed
application-facing façade over the existing profile, preference, feed,
refresh, saved-job, availability, and handoff services. It returns semantic
view models without numeric diagnostics or persistence/provider objects. The
frontend owns section selection, selected-job state, draft preference widgets,
excluded disclosure state, and applying a prepared tailoring handoff to
Streamlit session state.

Tailored and Explore state is independent. The façade scopes persisted feed
reads to the selected profile and preserves repository order; the frontend
does not re-rank. Saved display uses the immutable posting snapshot. Jobs CSS
is scoped to Jobs markup and uses Streamlit theme variables for light and dark
themes. Tailor handoff invalidates only derived workflow state and switches the
existing application route; it does not invoke Gemini, rendering, or DOCX
generation.

## Evolution

Use local JSON or SQLite for MVP. Add a database adapter, object storage adapter, and authentication dependency without moving domain or application code. FastAPI is the stable product API; Streamlit is a replaceable client.

The retrieval port is the RAG seam. A later retriever may combine structured
profile evidence with embeddings, portfolio documents, Git repositories, or an
MCP-backed source while returning the same evidence IDs and provenance. Future
specialized planning, writing, and verification agents must communicate only
through typed evidence, plans, claims, and validation records; the
deterministic orchestrator continues to execute tools and authorize export. A
cover-letter agent can consume the approved plan, final resume, and additional
retrieved-but-omitted evidence through this same seam without changing the
current cover-letter implementation.

## Architectural risks and assumptions

- PDF-to-structured-resume extraction is unreliable; parsed data must be user-reviewable before use.
- Exact page count needs a configured DOCX provider. Template V1 utilization
  estimates may support explicitly non-final planning but never substitute for
  exact verification or authorize a generated artifact.
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

Engineering search vocabulary is centralized in
`domain/job_discovery/search_taxonomy.py`. Confirmed-profile role families and
reviewed multidisciplinary signals produce bounded title/search terms; Explore
sectors expand to the same provider-safe vocabulary. Local occupational
matching is title-focused so boilerplate descriptions cannot turn every
engineer into a software result or admit non-role postings merely because they
mention an engineering team. Seniority markers are likewise read from the
posting title; an unlabelled title remains eligible for downstream evaluation.
Explore sector selection changes retrieval scope before evaluation, while weak
fit remains visible in the freshness-led Explore feed.

Retrieval is bounded by source, page, record, timeout, and retry settings. It
protects against repeated cursors and preserves successful sources when
another source fails. Normalization and deduplication retain source-qualified
identity, canonical URL authority, aliases, and complete provenance
independently of provider or page order. Every deduplicated candidate is
evaluated by the frozen evaluator. Tailored and Explore feed ordering and
visibility are applied after evaluation; ordinary feeds hide Don't Match and
hard-ineligible items but report `excluded_count`, and excluded endpoints
return retained evaluations without recomputation.

When a healthy source returns records but none cross the requested local
boundary, retrieval emits the sanitized `local_filter_no_match` diagnostic.
Discovery runs separately retain provider-retrieved and locally accepted record
counts so delivery can distinguish an empty source from an empty match set.

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

The CLI source refresh queries the union of all approved engineering sectors;
it is not implicitly a Software Engineering refresh. Multi-sector inventory
runs are not labelled as a single Explore sector, so they cannot pollute a
sector-specific feed. The synchronous safe HTTP bridge retains one event loop
for a connector's bounded multi-request session, and permits a single trailing
slash when the approved path pattern explicitly allows it; traversal and
duplicate-slash normalization remain rejected.

## Batch 4 Jobs experience boundary

The dedicated Jobs page is a delivery feature over the existing job-discovery
contracts. The application-facing façade in
`application/job_discovery/experience.py` assembles typed page data and use
cases. `profile_queries.py` owns reviewed-profile lookup, and `handoff.py`
prepares existing tailoring input without generating anything. The frontend
modules have deliberately narrow responsibilities:

| Module | Responsibility |
| --- | --- |
| `frontend/jobs_page.py` | Jobs section orchestration and profile-scoped UI state |
| `frontend/job_feed_view.py` | Tailored/Explore cards, fit meter, eligibility, detail, and actions |
| `frontend/job_preferences_view.py` | Preference suggestion, editing, confirmation, and conflict display |
| `frontend/saved_jobs_view.py` | Immutable saved snapshots, availability, and saved handoffs |
| `frontend/jobs_styles.py` | Jobs-scoped visual tokens and stable DOM selectors |
| `frontend/app_shell.py` | Shared application navigation and profile shell |

The façade owns repository/service access and DTO assembly. The frontend owns
layout, native Streamlit widget interaction, selected-job state, draft widget
state, and the deferred navigation intent used by the shared router. Tailored
and Explore selection state is independent and keyed by feed context, profile,
sector where relevant, visibility, and stable job identity. Saved snapshots are
displayed as immutable posting snapshots; availability metadata may change
without rewriting the snapshot.

`tests/streamlit_apps/jobs_test_app.py` injects deterministic façade data into
the same production Jobs frontend for populated interaction and visual checks.
The real `frontend/app.py` uses persisted profiles, preferences, feeds, and
saved jobs and may correctly show an empty feed until a refresh has persisted
recommendations. Both paths are required acceptance surfaces; neither replaces
the other.

The frontend preserves backend-owned Tailored and Explore ordering and does not
re-evaluate eligibility, fit, or sort order. The normal UI renders semantic
grades, evidence, gaps, unresolved facts, verification, freshness, eligibility,
and provisional state without numeric fit scores. Tailor resume is an
application-boundary handoff only: it pre-fills the existing workflow and does
not call Gemini, generate a plan, render, export, or create a cover letter.

## Streamlit implementation lessons

Widget-owned session-state keys cannot be mutated after the corresponding
widget is instantiated. The Jobs router consumes `jobs_pending_page` before
creating the `app_active_page` widget; this fixed the `StreamlitAPIException`
caused by changing `app_active_page` after `st.pills` creation. Selection keys
must be context-safe, and Tailored and Explore must not share a selected-job
key.

The full-card action remains a native Streamlit button. Its keyed
`stElementContainer`, intermediate `stButton` wrapper, and native button are
all sized to the card; a selector targets the actual visible
`stVerticalBlock` card rather than merely a marker child. Selector existence in
source is not proof of a rendered match. Selected, hover, and focus precedence
is explicit, with selected-hover preserving the selected surface, border, and
glow. Stable keyed containers and documented data-test IDs are preferred over
generated class hashes. Interaction remains native and accessible; JavaScript,
React, Tailwind, Node, npm, and custom components are not part of this boundary.

## Figma and visual implementation rules

Figma is the source of truth for Jobs hierarchy, spacing, component
proportions, colors, selected state, navigation treatment, fit bars,
eligibility indicators, and responsive composition. It is not permission to
copy generated React, install Tailwind, replace Streamlit with fake HTML or
JavaScript, or build a static canvas. The six current references are:

- [Primary dark desktop](https://www.figma.com/design/a7UeLCf07LY1VlIJCeVlg1?node-id=16-3)
- [Dark components](https://www.figma.com/design/a7UeLCf07LY1VlIJCeVlg1?node-id=16-117)
- [Dark mobile](https://www.figma.com/design/a7UeLCf07LY1VlIJCeVlg1?node-id=16-174)
- [Light desktop](https://www.figma.com/design/a7UeLCf07LY1VlIJCeVlg1?node-id=8-2)
- [Light components](https://www.figma.com/design/a7UeLCf07LY1VlIJCeVlg1?node-id=9-2)
- [Light mobile](https://www.figma.com/design/a7UeLCf07LY1VlIJCeVlg1?node-id=10-2)

Early implementation attempts described Figma vaguely while also forbidding
explicit Figma color tokens, which produced repeated visual rework. The
improved practice is to inspect the frames directly, extract concrete values,
centralize Jobs-scoped tokens, preserve dark/light behavior, compare the real
browser result, and never claim fidelity from code or CSS-string tests alone.

## Frontend architecture — Precision Workbench

This section describes the implemented frontend structure. Browser-level visual
validation remains a manual release gate.

### Current state

The Streamlit composition in frontend/app.py constructs and caches the resume
and profile dependencies, bootstraps profile state, renders shared navigation,
and dispatches focused Career Profile, Jobs, Resume Studio, and Cover Letters
page modules. Jobs dependencies are scoped to the Jobs route. The staged resume
page delegates immutable artifact generation and exact-byte download to the
accepted resume workflow; the cover-letter page delegates its production
artifact lifecycle to the accepted evidence-backed cover-letter view.

### Intended module boundaries

| Boundary | Intended responsibility |
| --- | --- |
| app.py | Composition root and route dispatcher |
| app_shell.py and app_shell_styles.py | Desktop/mobile navigation, active-profile context, pending route intent |
| design_tokens.py and shared_components.py | Scoped semantic tokens and intentional shared Streamlit presentation |
| profile_page.py, profile_editor_view.py, profile_import_view.py | Career Profile overview, focused editor, import, advanced area |
| resume_studio_page.py and resume_*_view.py | Job context, strategy, evidence, review, and export stages |
| cover_letters_page.py and cover_letter_*_view.py | Setup, review, claim decision, and export |
| document_canvas.py | Structured review surface and optional inspector |
| Existing Jobs modules | Jobs presentation through the JobsExperienceService facade |

These modules are the current delivery boundaries; additional view modules may
be extracted without moving application or domain policy into the frontend.

### Authority and state rules

- app.py will construct dependencies and pass them explicitly. Page modules
  will not instantiate repositories, duplicate application policy, or
  reimplement domain decisions.
- Application services, domain models, ports, and repositories retain current
  authority. The frontend remains a delivery layer.
- MasterProfileRepository remains profile-persistence authority; current
  validation and evidence truthfulness rules remain unchanged.
- Tailoring plans, generated résumés, and cover letters remain derived session
  state. Existing deterministic invalidation for profile or posting changes is
  retained; page-local state must reset from the same inputs.
- Document canvases are review surfaces. ResumeRenderer, CoverLetterRenderer,
  and exact page-count tooling remain export authority.
- Jobs retains the JobsExperienceService boundary, backend-owned order,
  semantic fit/eligibility/provisional behavior, immutable snapshots, and safe
  tailoring handoff.

### Presentation and acceptance rules

The planned shell is responsive: a persistent desktop sidebar with active
profile context and optional inspector, plus four-item native mobile navigation
and one-column detail/editing surfaces. Semantic CSS variables will be scoped
to stable keyed Streamlit containers and mapped through available Streamlit
theme variables or another verified stable browser mechanism. This does not
claim a stable public Python API for resolving the active Streamlit theme.

Native Streamlit controls remain preferred for interaction; semantic HTML may
support non-interactive presentation only. Selector assumptions are not
authoritative until checked in a real browser. Unit and AppTest checks prove
state and semantic behavior, not visual fidelity. Browser evidence remains
required for physical dimensions, hit targets, selected-hover/focus states,
mobile overflow, document canvases, and dark/light parity.

The target, Figma authority, and behavior-preservation contract are documented
in docs/design/PRECISION_WORKBENCH_UI_REDESIGN.md. The execution sequence is in
docs/engineering/PRECISION_WORKBENCH_IMPLEMENTATION_PLAN.md.
