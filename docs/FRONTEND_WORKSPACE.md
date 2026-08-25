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

The current preview is explicitly non-authoritative. DOCX rendering and exact one-page
verification remain final authority.

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
their existing approval/download restrictions.
