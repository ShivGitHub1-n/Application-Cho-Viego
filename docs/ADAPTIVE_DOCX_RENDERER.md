# Adaptive deterministic DOCX renderer

## Boundary

`render_structured_resume(resume, layout_profile, output_path)` is the
profile-driven experimental renderer used by reference-analysis and explicit
lower-level tests. It performs no selection, rewriting, Gemini calls,
shortening, underfill expansion, page fitting, or PDF conversion. It is not the
default Template V1 runtime.

`ManagedResumeRenderer` opens the packaged `template_v1.docx` by default and
delegates DOCX population to the static-template renderer. That renderer clones
source-derived OOXML prototypes and replaces semantic placeholders without
creating a blank document or reconstructing formatting from
`template_v1_layout.json`.

The managed renderer still owns the strict final DOCX page-count gate, bounded
overflow-only reduction loop, and typed page-utilization diagnostic; underfill
expansion remains disabled. The JSON profile remains available for occupancy
diagnostics and explicit profile-driven renderer experiments. Passing a
reference path without an explicit profile remains rejected.

## Role mapping

| Structured content | Layout role |
|---|---|
| Display name | `name` |
| Compact contact row | `contact_line` |
| Section labels | `section_heading` |
| School and dates | `education_institution_date_row` |
| Program and location | `education_program_location_row` |
| GPA and awards | `education_awards_row` |
| Coursework | `education_coursework_row` |
| Categorized skills | `skill_category_row` |
| Experience title and dates | `experience_title_date_row` |
| Employer and location | `employer_location_row` |
| Experience bullets | `experience_bullet` |
| Project title, technology, dates | `project_title_metadata_row` |
| Project bullets | `project_bullet` |
| Later entries and final paragraphs | transition roles plus the content role |

Metadata columns use actual `w:tab` runs and the tab stops recorded on the role. No repeated-space alignment or layout tables are used. Section-heading DrawingML rules are rendered as equivalent paragraph borders using the measured style, width, spacing, and color.

## Layout application

The renderer applies page geometry, orientation, columns, paragraph alignment, before/after spacing, auto-spacing flags, contextual spacing, line spacing, indentation, hanging indentation, keep/widow/page behavior, tabs, borders, primary and run-variant typography, font color, emphasis, underline, and character spacing. The Template V1 loader resolves canonical implicit single-line and zero-after behavior into explicit paragraph values: 240 twips with the exact line rule, and zero spacing-after except for verified nonzero role values such as the Education heading's 32 twips. Transition records replace, rather than add to, the matching source-after and destination-before components. An absent transition contribution cannot erase explicit role spacing, and the static Template V1 transition resolutions express canonical zero targets as numeric zero. Section-heading transitions are selected by the semantic role immediately following the heading when the reference contains distinct openings.

Bullets preserve the observed mechanism. Numbering-based reference bullets create a valid document-local numbering definition using the profile's marker text, marker-only font, level, format, and measured hanging geometry; no literal marker is emitted. Literal-marker roles remain literal and apply marker typography only to the marker run. Plain bullet bodies use the role's regular base typography and never inherit a reference paragraph's incidental emphasized-fragment position. Skill categories use separate paragraphs, preserve exact labels and selected values, and apply label emphasis separately from regular values.

Template V1 normalizes equivalent metadata rows to one explicit right-aligned anchor at 11,160 twips. Long metadata is kept intact and moves to a line break within the same paragraph when the anchor would collide or exceed the usable width.

For default Template V1 output, paragraph rhythm comes directly from the
packaged prototype paragraphs and retained styles. First and repeated
experience prototypes preserve their distinct source transitions. Optional
rows and unused prototypes are omitted completely, and no blank paragraphs are
added for spacing. Profile-driven transition resolution described elsewhere in
this document applies only to explicit adaptive-renderer experiments.

`ManagedResumeRenderer` requires an exact DOCX page-count provider (LibreOffice when available, with Microsoft Word COM as an optional fallback). Estimated or unavailable measurements raise a controlled verification error; they are never reported as an exact one-page result. If exact measurement reports overflow, only deterministic optional-content reduction is attempted, with geometry unchanged, through a bounded loop. A one-page document is then estimated for occupied vertical space: severe underfill is reported separately from acceptable one-page composition and never triggers automatic content insertion.

## Hyperlinks

Email and web-like contact items receive external DOCX hyperlink relationships. Missing items are removed before separators are emitted. Display text is preserved, implicit web schemes are added only to relationship targets, and profile hyperlink typography controls color and underline when available.

## Centralized fallbacks

Adaptive-renderer fallbacks are used only when an explicitly supplied profile
omits a property and are centralized in `_Fallbacks`: Times New Roman 10 pt,
black, a standard bullet marker, and a compact pipe separator. The default
static renderer has no formatting fallbacks. A missing, modified, or invalid
packaged Template V1 DOCX raises a controlled error.

When a content-specific role is absent but the profile contains a structurally equivalent role, the renderer uses that observed role rather than inventing geometry. In particular, missing project title/metadata and project-bullet roles can reuse the observed experience title/date and experience-bullet roles for typography, tabs, bullet geometry, and spacing while retaining project transition semantics.

## Limitations

- Contact data is currently delivered as a compact contact string, so hyperlink recognition is deterministic syntax recognition rather than typed contact-kind metadata.
- The low-level adaptive renderer remains diagnostic/experimental and is not
  the Template V1 formatting authority.
- The static renderer does not measure occupancy, shrink text, or alter
  selection. The managed renderer performs the final exact page-count gate and
  may reduce optional content only after overflow is measured.
- Structured bullets do not carry emphasized-span metadata. Dynamic bullet
  wording therefore uses the canonical plain bullet-run prototype rather than
  attempting to infer bold fragments.
- Visual fidelity must still be reviewed in Microsoft Word because font availability and Word layout behavior vary by installation.
