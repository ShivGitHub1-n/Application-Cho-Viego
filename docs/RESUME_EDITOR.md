# Live résumé editor

## Authority boundary

The live editor modifies only the generated résumé for one application. The reviewed
`MasterProfile` remains unchanged and continues to own candidate facts, canonical entry
metadata, and reviewed skills.

The editor begins from an immutable `GeneratedResumeArtifact`. Each applied edit creates a
separate immutable `ResumeEditorRevision` whose identity covers the application context and
the complete structured résumé. The generated artifact is retained as the reset baseline.

Manual editor actions never invoke the strategist, evidence selector, reserve selector, skill
recommender, or writer. A free-form bullet edit retains the original evidence IDs and must pass
the existing deterministic rewrite-grounding checks before it can become an applied revision.
Suggestions retain their reviewed evidence IDs and canonical experience/project parent.

## Editing and rendering flow

```text
generated artifact
      ↓
application-scoped staged résumé
      ↓  user chooses Apply changes
deterministic evidence/parent validation
      ↓
Template V1 DOCX render
      ↓
Word/LibreOffice DOCX-to-PDF preview + exact page count
      ↓
immutable editor revision
      ↓  explicit review of this fingerprint
stored-byte DOCX export
```

Typing and individual staging actions do not render. Multiple changes are rendered once on
Apply. An unchanged applied revision reuses its stored DOCX/PDF preview bytes. A stale render is
discarded if its application fingerprint no longer matches the active application.

The PDF preview is converted from the same rendered DOCX; it is not a separately styled HTML or
ReportLab résumé. The exact PDF page tree supplies the editor page count. A two-page revision is
retained exactly as edited and is not semantically recomposed or automatically trimmed. It is
not exportable until the user restores a verified one-page revision.

## Suggestions and omitted entries

A direct rewrite identifies one exact current bullet. A suggestion synthesized from multiple
reviewed facts is presented as a new supported bullet with its facts disclosed separately; the
facts are never displayed as one fictional current bullet.

When a suggestion belongs to an omitted experience or project, the shared canonical-parent
resolver validates every evidence ID against the reviewed profile. Applying it adds the real
parent metadata and bullet together. The heading, metadata, spacing, and bullet therefore all
participate in the next exact render. Child content can never attach to another entry.

## Skills and formatting

Visible skills may be removed or added only from reviewed Career Profile skills. Posting terms
and arbitrary text are not accepted as new skills.

Template V1 remains the single formatting authority. The current static template does not offer
independent runtime font, margin, or spacing parameters, so this editor pass intentionally does
not expose controls that would imply unsupported geometry. Any future formatting controls must
be typed renderer inputs and must rerender and repaginate the exact document.

## Approval and state

Editor workspaces are keyed by reviewed profile, posting, and baseline artifact fingerprints.
Edits from one job cannot appear in another job. Session-scoped workspaces may restore an edited
revision when the same artifact is reopened during the same session.

Staging, applying, undoing, or resetting content invalidates the prior editor approval and clears
prepared export bytes. Export is allowed only when the approved revision fingerprint matches the
current applied revision and that revision has an exact one-page result. Download returns the
stored bytes and performs no rendering, pagination, selection, or provider call.
