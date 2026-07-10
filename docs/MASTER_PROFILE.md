# Master Profile

## Canonical structure

A `MasterProfile` is the source of truth for a user. It contains identity/contact fields, education, experiences, projects, skills, coursework, and an evidence catalog. Contact and education are deterministic template content; evidence-based selection applies to the opportunity-specific sections. Each entity has a stable ID so generated content can cite it.

## Evidence model

Store atomic evidence rather than only polished resume bullets:

- original text and source location
- linked entity ID
- technologies, outcomes, metrics, demonstrated capabilities, and dates when known
- confirmation state and user notes

Parsed uploads create a draft profile. The user confirms and corrects it before the profile becomes eligible for tailoring. Preserve original documents separately from normalized profile records.

Store declared skills separately from demonstrated capabilities. Verified declared skills can support a skills section and provide limited fit signal, but do not establish evidence for a role-relevant experience or project claim without confirmed supporting evidence.

## Versioning and ownership

Every profile belongs to a user ID, may have many master-resume versions, and is immutable once referenced by a generated resume. This supports future authentication and reproducibility without schema redesign.
