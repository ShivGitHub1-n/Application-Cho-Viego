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

## Resume Studio workspace

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

## Cover Letter failures

The normal failure state is concise and recoverable. Full candidate validation,
provider, grounding, research, and page-fit details remain available under **Advanced
diagnostics** for the known production investigation. Diagnostic-only candidates retain
their existing approval/download restrictions.
