# Master Profile

## Canonical structure

A `MasterProfile` is the source of truth for a user. It contains identity/contact fields, education, experiences, projects, categorized skills, coursework, and an evidence catalog. Education (including dates, location, GPA, awards, and relevant coursework) and categorized technical skills are deterministic baseline content. Evidence-based selection applies to experience/project entries and their bullets; selecting an entry preserves its employer, dates, location, subtitle, and technology label. Each entity has a stable ID so generated content can cite it.

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

Opportunity planning scores every verified category and skill. The plan carries both a selected categorized set and the complete ranked verified pool so later page-fit work can expand or reduce the section without another model call. Category scoring combines the strongest skill matches, relevant-skill density, signal coverage, and category-label context. A single match does not automatically include unrelated neighbors.

Gemini may narrow or reorder only the eligible IDs, labels, and values supplied in the typed skill-composition request. Deterministic reconciliation rejects invented, renamed, moved, or duplicated categories and skills. Failures preserve the deterministic selection. Gemini receives no experience evidence or unrelated profile content for this operation.

`TailoringPlan.selected_skills` and `StructuredResume.selected_skills` remain as deprecated renderer-compatibility fields. For categorized profiles they are derived from the selected category/skill ordering and must not be used for semantic decisions. A later renderer should consume `StructuredResume.technical_skills` directly. The current scorer uses posting text and recognized signals; it does not yet parse a separately typed required/preferred technology taxonomy or perform rendered-space expansion.

## Versioning and ownership

Every profile belongs to a user ID, may have many master-resume versions, and is immutable once referenced by a generated resume. This supports future authentication and reproducibility without schema redesign.
