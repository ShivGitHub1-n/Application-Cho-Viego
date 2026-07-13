# Adaptive deterministic DOCX renderer

## Boundary

`render_structured_resume(resume, layout_profile, output_path)` maps validated `StructuredResume` content to semantic roles in a reference-derived `LayoutProfile`. It performs no selection, rewriting, Gemini calls, shortening, underfill expansion, page fitting, or PDF conversion. The authoritative reference document is analyzed separately and is never opened for writing or used as a body-content template. Resume-layout refinement is frozen for the MVP except for submission-blocking defects; see `KNOWN_ISSUES.md`.

`ManagedResumeRenderer` derives the profile from `manual-test/reference-resume.docx` by default and delegates its DOCX path to the adaptive renderer. It owns the strict final DOCX page-count gate and bounded overflow-only reduction loop; underfill expansion is disabled. Its ReportLab PDF typography and drawing behavior remain unchanged; the reference-derived geometry applies to the DOCX path. Passing an already derived profile supports deterministic tests and callers that cache profile analysis.

## Role mapping

| Structured content | Layout role |
|---|---|
| Display name | `name` |
| Compact contact row | `contact_line` |
| Section labels | `section_heading` |
| School and dates | `education_institution_date_row` |
| Program and location | `education_program_location_row` |
| GPA, awards, coursework | `education_detail_bullet` |
| Categorized skills | `skill_category_row` |
| Experience title and dates | `experience_title_date_row` |
| Employer and location | `employer_location_row` |
| Experience bullets | `experience_bullet` |
| Project title, technology, dates | `project_title_metadata_row` |
| Project bullets | `project_bullet` |
| Later entries and final paragraphs | transition roles plus the content role |

Metadata columns use actual `w:tab` runs and the tab stops recorded on the role. No repeated-space alignment or layout tables are used. Section-heading DrawingML rules are rendered as equivalent paragraph borders using the measured style, width, spacing, and color.

## Layout application

The renderer applies page geometry, orientation, columns, paragraph alignment, before/after spacing, auto-spacing flags, contextual spacing, line spacing, indentation, hanging indentation, keep/widow/page behavior, tabs, borders, primary and run-variant typography, font color, emphasis, underline, and character spacing. Transition records override both source-after and destination-before components for matching semantic pairs. Missing numeric contributions are applied as no direct spacing, so a role representative's spacing cannot leak into a structurally different transition. Section-heading transitions are selected by the semantic role immediately following the heading when the reference contains distinct openings.

Bullets preserve the observed mechanism. Numbering-based reference bullets create a valid document-local numbering definition using the profile's marker text, marker-only font, level, format, and measured hanging geometry; no literal marker is emitted. Literal-marker roles remain literal and apply marker typography only to the marker run. Plain bullet bodies use the role's regular base typography and never inherit a reference paragraph's incidental emphasized-fragment position. Skill categories use separate paragraphs, preserve exact labels and selected values, and apply label emphasis separately from regular values.

Reference metadata rows may contain small position differences because their left tabs were manually adjusted for source text widths. The analyzer clusters observed metadata tab stops using a tolerance derived from usable page width and records observed positions, representative medians, participating semantic roles, tolerance, and provenance in `MetadataAnchorGroup`. Equivalent metadata rows use their role group's representative; roles with multiple observed right-side anchors deterministically use the rightmost applicable group. Long metadata is kept intact and moves to a line break within the same paragraph when the anchor would collide or exceed the usable width.

Paragraph rhythm is resolved from matching source/destination semantic transitions after applying the destination role. Dominant values are derived by the reference analyzer per role pair; structurally equivalent transitions use the observed compact bullet transition when the reference does not contain a repeated exact pair. Interior entry titles and final education-detail rows retain their transition identity while reusing their content-role typography and geometry. The renderer does not add blank paragraphs for spacing. The reference's empty DrawingML separator is represented by the measured heading border rather than by inserting a generic empty paragraph.

`ManagedResumeRenderer` requires an exact DOCX page-count provider (LibreOffice when available, with Microsoft Word COM as an optional fallback). Estimated or unavailable measurements raise a controlled verification error; they are never reported as an exact one-page result. If exact measurement reports overflow, only deterministic optional-content reduction is attempted, with geometry unchanged, through a bounded loop.

## Hyperlinks

Email and web-like contact items receive external DOCX hyperlink relationships. Missing items are removed before separators are emitted. Display text is preserved, implicit web schemes are added only to relationship targets, and profile hyperlink typography controls color and underline when available.

## Centralized fallbacks

Fallbacks are used only when the profile omits a property and are centralized in `_Fallbacks`: Times New Roman 10 pt, black, a standard bullet marker, and a compact pipe separator. They are generic rather than reference measurements. A missing required semantic role or missing reference file raises a controlled error instead of returning to the former generic Word-heading path.

When a content-specific role is absent but the profile contains a structurally equivalent role, the renderer uses that observed role rather than inventing geometry. In particular, missing project title/metadata and project-bullet roles can reuse the observed experience title/date and experience-bullet roles for typography, tabs, bullet geometry, and spacing while retaining project transition semantics.

## Limitations

- `StructuredResume` currently has no separately typed minor, co-op designation, project award, or placement fields; the renderer cannot output metadata the contract does not contain.
- Contact data is currently delivered as a compact contact string, so hyperlink recognition is deterministic syntax recognition rather than typed contact-kind metadata.
- The low-level adaptive renderer does not measure occupancy, shrink text, alter content, or guarantee one-page fit; the managed renderer performs the final exact page-count gate and may reduce optional content only after overflow is measured.
- Visual fidelity must still be reviewed in Microsoft Word because font availability and Word layout behavior vary by installation.
