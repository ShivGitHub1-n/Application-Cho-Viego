# Template Engine

## Rule

AI generates structured content only. The template engine exclusively controls fonts, margins, spacing, dates, hierarchy, alignment, bolding, and pagination.

## Template contract

Templates are versioned assets with a declared schema and field mapping. A renderer receives `StructuredResume`, validates section capacities, and emits managed DOCX and PDF artifacts from the same structured content. The MVP owns one renderer and template; it does not inspect arbitrary user DOCX files.

## One-page optimization

The decision engine receives template constraints as a content budget. The PDF rendered by the controlled application runtime is authoritative for page count. If the result overflows, return a new constrained plan with explicit recommended reductions or fail clearly; never silently alter formatting to make content fit. DOCX is an editable artifact and may repaginate in another office runtime.

## MVP choices

Begin with a small, supported placeholder vocabulary and one known-good DOCX template. Avoid arbitrary editing of user DOCX files until template introspection and validation are robust.
