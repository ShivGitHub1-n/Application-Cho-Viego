# Template Engine

## Rule

AI generates structured content only. The template engine exclusively controls fonts, margins, spacing, dates, hierarchy, alignment, bolding, and pagination.

## Template contract

Templates are versioned assets with a declared schema and field mapping. A renderer receives `StructuredResume`, validates section capacities, applies values to DOCX placeholders or generated table/paragraph regions, and emits DOCX. PDF is derived from the DOCX through a selected conversion adapter.

## One-page optimization

The decision engine receives template constraints as a content budget. Final page count must be checked after rendering. If the result overflows, return a new constrained plan with explicit recommended reductions; never silently alter formatting to make content fit.

## MVP choices

Begin with a small, supported placeholder vocabulary and one known-good DOCX template. Avoid arbitrary editing of user DOCX files until template introspection and validation are robust.

