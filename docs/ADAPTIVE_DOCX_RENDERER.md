# Adaptive deterministic DOCX renderer

## Boundary

`render_structured_resume(resume, layout_profile, output_path)` maps validated `StructuredResume` content to semantic roles in a reference-derived `LayoutProfile`. It performs no selection, rewriting, Gemini calls, shortening, page fitting, or PDF conversion. The authoritative reference document is analyzed separately and is never opened for writing or used as a body-content template.

`ManagedResumeRenderer` derives the profile from `manual-test/reference-resume.docx` by default and delegates its DOCX path to the adaptive renderer. Its existing ReportLab PDF and overflow path is unchanged. Passing an already derived profile supports deterministic tests and callers that cache profile analysis.

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

The renderer applies page geometry, orientation, columns, paragraph alignment, before/after spacing, line spacing, indentation, hanging indentation, keep/widow/page behavior, tabs, borders, primary and run-variant typography, font color, emphasis, underline, and character spacing. Transition records can override the source-after and destination-before components for a matching semantic pair.

Bullets use the observed marker and measured hanging geometry. The marker is emitted once as content with a real tab; Word numbering is not also applied, preventing duplicate markers. Skill categories use separate paragraphs and preserve exact labels and selected values. Reference-derived hanging indentation controls wrapped continuation alignment.

## Hyperlinks

Email and web-like contact items receive external DOCX hyperlink relationships. Missing items are removed before separators are emitted. Display text is preserved, implicit web schemes are added only to relationship targets, and profile hyperlink typography controls color and underline when available.

## Centralized fallbacks

Fallbacks are used only when the profile omits a property and are centralized in `_Fallbacks`: Times New Roman 10 pt, black, a standard bullet marker, and a compact pipe separator. They are generic rather than reference measurements. A missing required semantic role or missing reference file raises a controlled error instead of returning to the former generic Word-heading path.

When a content-specific role is absent but the profile contains a structurally equivalent role, the renderer uses that observed role rather than inventing geometry. In particular, missing project title/metadata and project-bullet roles can reuse the observed experience title/date and experience-bullet roles for typography, tabs, bullet geometry, and spacing while retaining project transition semantics.

## Limitations

- `StructuredResume` currently has no separately typed minor, co-op designation, project award, or placement fields; the renderer cannot output metadata the contract does not contain.
- Contact data is currently delivered as a compact contact string, so hyperlink recognition is deterministic syntax recognition rather than typed contact-kind metadata.
- The renderer does not measure occupancy, shrink text, alter content, or guarantee one-page fit.
- Visual fidelity must still be reviewed in Microsoft Word because font availability and Word layout behavior vary by installation.
