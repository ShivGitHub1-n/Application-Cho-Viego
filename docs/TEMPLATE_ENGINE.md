# Template Engine

## Rule

AI generates structured content only. The template engine exclusively controls fonts, margins, spacing, dates, hierarchy, alignment, bolding, and pagination.

## Template contract

Templates are versioned assets with a declared schema and field mapping. A renderer receives `StructuredResume`, validates section capacities, and emits managed DOCX and PDF artifacts from the same structured content. The MVP owns one renderer and template; it does not inspect arbitrary user DOCX files.

## One-page optimization

The renderer receives template constraints as a content budget. The final DOCX is rendered through an exact provider and measured for actual page count. If it overflows, only deterministic optional-content reduction may run; geometry is never changed by page fitting. Estimated or unavailable measurement raises a controlled verification error. Underfill expansion is disabled while reference-derived geometry is being validated.

## MVP choices

Begin with a small, supported placeholder vocabulary and one known-good DOCX template. Avoid arbitrary editing of user DOCX files until template introspection and validation are robust.
