# Template Engine

## Rule

AI generates structured content only. The template engine exclusively controls fonts, margins, spacing, dates, hierarchy, alignment, bolding, and pagination.

## Template contract

Templates are versioned assets with a declared schema and field mapping. A
renderer receives `StructuredResume`, validates section capacities, and emits
managed DOCX and PDF artifacts from the same structured content. The MVP owns
one renderer and the static [Template V1 contract](TEMPLATE_V1.md). It opens
only the controlled packaged `template_v1.docx`, populates its semantic
placeholders, and clones its prototype blocks; it does not inspect arbitrary
user DOCX files at runtime.

## One-page optimization

The renderer receives template constraints as a content budget. The final DOCX is rendered through an exact provider and measured for actual page count. If it overflows, only deterministic optional-content reduction may run; geometry is never changed by page fitting. Estimated or unavailable measurement raises a controlled verification error. After exact measurement, a typed diagnostic distinguishes overflow, acceptable one-page composition, severe underfill, and unverified fit. Underfill expansion remains disabled.

## MVP choices

Use the packaged, sanitized Template V1 DOCX derived from the reviewed
canonical document. The actual DOCX is the formatting authority; the layout
profile is diagnostic only. Placeholders name typed insertion points but never
contain candidate facts. Avoid arbitrary editing of user DOCX files.
