# Master Profile

## Canonical structure

A `MasterProfile` is the source of truth for a user. It contains identity/contact fields, education, experiences, projects, categorized skills, coursework, and an evidence catalog. Education (including dates, location, GPA, awards, and relevant coursework) and categorized technical skills are deterministic baseline content. Evidence-based selection applies to experience/project entries and their bullets; selecting an entry preserves its employer, dates, location, subtitle, and technology label. Each entity has a stable ID so generated content can cite it.

Education records are authoritative for institution, program, optional minor or specialization, optional co-op designation, start and graduation dates, reviewed graduation status (`expected`, `completed`, or `unknown`), location, GPA, awards, and relevant coursework. The renderer adds the word `Expected` only when that status is explicitly reviewed as `expected`. GPA accepts reviewed strings, integers, or floating-point numbers and normalizes numeric input to its non-rounded string representation. Reviewed display text such as `3.72/4.00` is preserved. Booleans and structured values are invalid.

`education[*].relevant_coursework` is canonical. The legacy top-level `coursework` list is derived from education-specific coursework. For backward compatibility, a top-level list supplied with exactly one education record is migrated into that record when its canonical list is empty. Conflicting representations are rejected instead of silently diverging.

## Evidence model

Store atomic evidence rather than only polished resume bullets:

- original text and source location
- linked entity ID
- technologies, outcomes, metrics, demonstrated capabilities, and dates when known
- confirmation state and user notes

Parsed uploads create a draft profile. The user confirms and corrects it before the profile becomes eligible for tailoring. Preserve original documents separately from normalized profile records.

Store declared skills separately from demonstrated capabilities. Verified declared skills can support a skills section and provide limited fit signal, but do not establish evidence for a role-relevant experience or project claim without confirmed supporting evidence.

## Categorized technical skills

Categorized technical skills are the authoritative skills representation. Reviewed category labels and skill values are preserved verbatim. Missing IDs are generated deterministically from the reviewed label/value and namespace; supplied IDs remain authoritative. Exact duplicates retain their first reviewed category and produce a normalization decision rather than being silently reassigned.

Opportunity planning scores every verified category and skill. The plan carries both a selected categorized set and the complete ranked verified pool so later page-fit work can expand or reduce the section without another model call. Category scoring combines the strongest skill matches, relevant-skill density, signal coverage, and category-label context. A single match does not automatically include unrelated neighbors. Underfill expansion is disabled while reference-derived layout geometry and exact page-count verification are being validated.

Gemini may narrow or reorder only the eligible IDs, labels, and values supplied in the typed skill-composition request. Deterministic reconciliation rejects invented, renamed, moved, or duplicated categories and skills. Failures preserve the deterministic selection. Gemini receives no experience evidence or unrelated profile content for this operation.

`TailoringPlan.selected_skills` and `StructuredResume.selected_skills` remain as deprecated renderer-compatibility fields. For categorized profiles they are derived from the selected category/skill ordering and must not be used for semantic decisions. A later renderer should consume `StructuredResume.technical_skills` directly. The current scorer uses posting text and recognized signals; it does not yet parse a separately typed required/preferred technology taxonomy or perform rendered-space expansion.

The legacy `declared_skills` list remains accepted. When categorized skills are present it is derived from those reviewed categories and cannot act as an independent competing source. A deterministic editor action may propose controlled category labels from the flat list; it preserves every proposed skill verbatim, adds none, and requires normal profile review before save.

## Validity and completeness

Validity protects structural integrity. Empty required identifiers, duplicate entry or evidence IDs, orphan evidence, empty category labels, and empty skill values are rejected during model validation. Missing optional dates, graduation status, locations, awards, coursework, or subtitles remain usable but are identified by `validate_master_profile_completeness()`.

`ProfileCompletenessReport` contains only profile and entry IDs, field-presence booleans, counts, duplicate indicators, and incomplete field paths. It never contains contact values, URLs, evidence prose, or bullet text. Manual fixtures print this report before planning so missing output can first be traced through `MasterProfile -> TailoringPlan -> StructuredResume`; renderer code must not be patched to compensate for absent source data.

Manual reviewed fixtures should be maintained from the factual master resume, with layout references used only for formatting. Preserve explicit source wording and confirmation state, record ambiguity rather than guessing, keep categorized skills canonical, and rerun completeness diagnostics after each fixture update.

## Versioning and ownership

Every profile belongs to a user ID, may have many master-resume versions, and is immutable once referenced by a generated resume. This supports future authentication and reproducibility without schema redesign.

## Structured review editor

The Streamlit extraction-review workflow uses a detached structured editor state for contact information, education, experiences, projects, evidence statements, and categorized technical skills. A successful upload extraction populates these visible controls. Conversion back to `MasterProfile` is deterministic and runs the existing Pydantic validation before persistence. Existing entry and evidence IDs are preserved; new IDs are generated deterministically. The SQLite `MasterProfileRepository` remains the only save pathway. Resume and cover-letter derived state is invalidated only when the canonical saved profile changes. An explicitly labeled, collapsed raw JSON fallback uses the same validation and repository pathway, refuses unsupported top-level fields, rejects empty input with a normal validation message, and sanitizes JSON syntax errors to line/column guidance.
