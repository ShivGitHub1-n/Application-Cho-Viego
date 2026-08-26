# Frontend Workspace Contract

The Streamlit application presents four product workspaces: Career Profile, Jobs,
Resume Studio, and Cover Letters. They share the semantic design tokens and shell in
`frontend/design_tokens.py`, `frontend/app_shell.py`, and
`frontend/app_shell_styles.py`.

## User and diagnostic surfaces

The normal surface shows application context, document state, decisions the user can
act on, and clear recovery guidance. Evidence IDs, provider payloads, candidate gate
codes, policy versions, raw JSON, and pagination internals belong under an explicitly
collapsed **Advanced diagnostics** or **Advanced** section.

## Application context and reruns

Job handoff establishes one active posting shared by Resume Studio and Cover Letters.
Posting/profile changes invalidate derived current artifacts; navigation by itself does
not regenerate documents or call a provider. Immutable completed artifacts are reused
when the user returns to the same context. The Jobs service graph is session-reused so
ordinary filter, selection, and navigation reruns do not rebuild HTTP clients and
repositories.

## Career Profile workspace

Career Profile is read-first. The default reviewed-profile canvas presents the complete
canonical education, categorized skills, experiences, projects, and reviewed evidence in
a document hierarchy. Structured forms are entered deliberately through **Edit profile**;
raw JSON and provenance stay under **Advanced**. The current repository does not persist
the uploaded source document, so **Source résumé** never fabricates an original preview.
It shows extracted source text only during an active import review and labels that boundary
explicitly. When no source artifact is available, the normal action becomes **Import or
replace résumé** and opens the existing review-first import flow; the persistence limitation
is documented under **Advanced** rather than presented as an error-like destination.

## Jobs refresh behavior

User-triggered tailored and Explore refreshes run in a session-owned background
coordinator, keyed by profile/feed/sector. The coordinator starts at most one operation for
the same key, never mutates Streamlit session state from its worker thread, and publishes a
typed terminal snapshot for a small polling fragment. Existing recommendations remain
rendered and navigation remains available while refresh is running.

Already-built feed, excluded-result, and Saved view projections are cached by the
session-owned Jobs façade and returned as defensive copies. Search, filtering, selection,
and detail opening therefore do not repeat repository projection work. Explicit refresh,
save, remove, or availability mutation invalidates only the affected profile's delivery
cache. Saved snapshots can be explicitly removed through a user-scoped repository operation;
removal never mutates the discovered posting or recommendation.

Independent approved sources are retrieved concurrently with a bounded worker pool. Each
connector retains its configured network timeout and pagination boundary. Source failures
remain isolated: successful fresh records are persisted, while recommendations from a
failed source in the immediately preceding matching feed are retained when available. A
failed source cannot erase the usable feed, and a completion for one context cannot mutate
the selected page, job, or another profile's refresh state. The refresh service exposes
non-persisted runtime timings for profile/query preparation, retrieval/parsing,
normalization, failed-source cache recovery,
deduplication, capability indexing, evaluation/scoring, feed assembly, and persistence.

## Deployment ownership boundary

The current local persistence layer is **not an authenticated multi-user boundary**.
`MasterProfile.user_id` is profile data rather than an identity established by an
authentication provider. The profile repository is keyed by `profile_id` and its list
operation returns every stored profile; no repository query is scoped by an authenticated
principal. Jobs may carry a `user_id`, but the Streamlit client obtains it from the selected
profile rather than from trusted authentication. Résumé and cover-letter artifacts are
derived Streamlit session state rather than a durable user-owned artifact repository.

Consequently, a shared deployment must not claim account isolation. Before multi-user
deployment, authentication must establish a trusted user identifier and every profile,
job/application, and durable artifact repository operation must require that principal in
its key and query predicate. Frontend filtering is not a substitute for repository-level
authorization. The intended first-session/create/restore-only-my-profiles behavior remains
a deployment blocker until that boundary exists.

## Resume Studio workspace

The normal résumé workflow is Job context → Generate → Review → Export. One
generation action orchestrates strategy, evidence selection, writing, validation, and exact
page fitting while keeping those internals under Advanced details. An unchanged profile,
posting, approval set, and artifact fingerprint reuses the stored immutable artifact.

Resume review uses a stable two-area shell:

- a control rail for structure, suggestions, and future formatting/edit controls;
- a document area for the preview and, later, the actual rendered live document.

The editor preview consists of page images rendered from the exact current PDF produced from
the current DOCX revision. It shows real page geometry while DOCX rendering and exact
pagination remain final export authority. An unchanged revision fingerprint reuses its
preview rather than converting the document again.

Generated suggestions name their canonical experience/project owner and show reviewed
source evidence beside suggested wording. When an approved suggestion belongs to an
entry omitted from the initial resume, the canonical parent is added with its metadata.
The existing final composition and exact-pagination pass then charges the heading,
metadata, spacing, and bullet cost. A child suggestion is never attached to another
entry and cannot bypass page fit.

Suggestion choices are staged in one form. Checkbox changes do not compose or paginate a
document. The explicit Apply action records the complete choice set, performs one rebuild,
and runs exact pagination once. This is also the state boundary for the future live editor.

## Cover Letter failures

The normal failure state is concise and recoverable. Full candidate validation,
provider, grounding, research, and page-fit details remain available under **Advanced
diagnostics** for the known production investigation. Diagnostic-only candidates retain
their existing approval/download restrictions and their draft is collapsed by default.
