# Template V1 contract

## Canonical source

Template V1 is the static MVP layout derived once from
`manual-test/reference-resume.docx` (SHA-256
`2B9DD1474B9E4A303A87B8A147F3511460988104EFDE7CFA053CAD64294369CD`).
The canonical DOCX is a reviewed source and is never edited.

The runtime authority is the sanitized, content-neutral packaged DOCX at
`resume_tailor/templates/template_v1.docx` (SHA-256
`2B4EEAE9BED52FF27B86CB1E9F75516D0A9935359658849589B37FFEF0A5974E`).
It retains the canonical section, style, numbering, theme, font-table,
paragraph, run, indentation, spacing, and DrawingML structures. Personal body
text, external hyperlink relationships, custom properties, author metadata,
and revision-session identifiers are removed.

`resume_tailor/templates/template_v1_layout.json` remains available for
diagnostics, occupancy estimation, reference-analysis tests, and explicit
lower-level renderer experiments. It does not reconstruct the default
document's formatting.

## Placeholders and prototypes

The packaged DOCX exposes explicit `{{UPPER_SNAKE_CASE}}` placeholders for
name, contact, education fields, categorized skills, experience metadata and
bullets, and project metadata and bullets. `TPL_*` bookmarks delimit:

- one education-entry prototype;
- one skill-category row;
- first and repeated experience-entry variants with a cloneable bullet;
- one project-entry prototype with a cloneable bullet.

Runtime population opens the packaged DOCX, clones the relevant paragraph or
block OOXML, replaces placeholder text only, removes unused optional rows, and
rebuilds the body in structured-resume order. Repeating entries and bullets
clone their corresponding prototype XML; they are not created with generic
`add_paragraph` calls. Generated output contains neither placeholders nor
prototype bookmarks.

## Geometry and semantic rows

The document uses US Letter portrait geometry: 12,240 × 15,840 twips, with top,
right, bottom, and left margins of 640, 360, 280, and 720 twips. Education,
experience, and project metadata shares a deterministic right-aligned tab at
11,160 twips, the usable-width boundary.

Template V1 contains distinct static paragraph prototypes for:

- name and contact;
- section headings;
- education institution/date, program/GPA/location, awards, and coursework;
- categorized skills;
- experience title/date, organization/location, and bullets;
- entry gaps;
- project title/technology, optional organization/location, and bullets.

Each prototype retains its source style, direct run formatting, indentation,
line behavior, numbering, keep behavior, and paragraph spacing. Dynamic
metadata rows contain a static right-aligned tab at 11,160 twips, the usable
width boundary. Runtime never discovers or reapplies tab geometry.

The canonical Education rule occupied a source-only empty DrawingML paragraph.
The packaged template folds that rule into the nonblank Education heading as a
0.5-point black bottom border. Other section rules retain their canonical
anchored DrawingML. This one-time sanitization allows generated output to have
zero blank paragraphs while preserving the section transition.

## Content and truthfulness

The renderer consumes only typed `StructuredResume` content. Candidate facts
come from reviewed profile fields and confirmed evidence; layout analysis never
creates a candidate fact. Selected education, experience, project, and skill
records are emitted in their structured order even when a selected entry has no
bullet. Missing metadata remains missing and is reported through profile
completeness rather than replaced.

No candidate facts are embedded in the packaged template. Expected-graduation
status, labels, titles, dates, locations, organizations, technologies, awards,
coursework, skills, and bullet wording come only from the structured document
model. The renderer does not infer content from the canonical reference.

## Fit diagnostics

Exact DOCX page count remains the page-fit authority. A typed utilization diagnostic
then distinguishes overflow, acceptable one-page composition, severe underfill,
and an unverified result. A one-page document with estimated occupied height
below the calibrated 72% Template V1 target floor is underfilled. The
composition objective stops rewarding additional occupancy at the 97% upper
target, which is anchored by the accepted canonical reference's 96.43%
estimate. The renderer never adds
unselected evidence or fabricates content. The application composer uses this
signal while rendering bounded reviewed-content alternatives through Template
V1. Exact-provider failure is retained and produces an unverified estimate,
never an exact one-page claim.
