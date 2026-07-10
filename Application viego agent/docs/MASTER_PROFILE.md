# Master Profile

## Canonical structure

A `MasterProfile` is the source of truth for a user. It contains identity/contact fields, education, experiences, projects, skills, coursework, and an evidence catalog. Each entity has a stable ID so generated content can cite it.

## Evidence model

Store atomic evidence rather than only polished resume bullets:

- original text and source location
- linked entity ID
- technologies, outcomes, metrics, and dates when known
- confirmation state and user notes

Parsed uploads create a draft profile. The user confirms and corrects it before the profile becomes eligible for tailoring. Preserve original documents separately from normalized profile records.

## Versioning and ownership

Every profile belongs to a user ID, may have many master-resume versions, and is immutable once referenced by a generated resume. This supports future authentication and reproducibility without schema redesign.

