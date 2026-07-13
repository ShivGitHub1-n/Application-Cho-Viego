# Reference DOCX layout analysis

## Purpose and boundary

`analyze_reference_docx(path: Path) -> LayoutProfile` derives a reusable formatting contract from a supplied DOCX. Values are read from the file rather than copied into source constants, so replacing or modifying the reference changes the profile without a code change. The analyzer is opt-in and is not connected to resume rendering, optimization, composition, shortening, page fitting, or document export.

A missing or structurally invalid reference raises `ReferenceDocxAnalysisError`; the analyzer does not invent fallback formatting.

## Schema

`LayoutProfile` is a Pydantic model and round-trips through readable JSON. It contains:

- page geometry, margins, header/footer distances, orientation, and columns;
- semantic role definitions containing paragraph formatting, primary typography, run patterns, tabs, borders, bullets, and hyperlink behavior;
- content-free section role sequences and neighboring-role relationships;
- inspected package-part names.

Measurements use native OOXML units (`twips`, `half_points`, and border `eighth_points`) to avoid lossy conversion. Each scalar formatting property includes provenance: direct paragraph/run property, named style, document default, section property, numbering definition, relationship, inferred recurring pattern, or not present.

## Semantic-role inference

The analyzer reads paragraph position, formatting signatures, capitalization shape, borders, alignment, tabs, indentation, numbering, hyperlinks, style inheritance, and neighboring paragraph patterns. It does not persist or compare personal names, schools, employers, projects, contact details, or exact resume sentences.

The first nonempty structural title block is separated into name and contact roles. Bordered or compact uppercase transition paragraphs identify section headings. Sections are then characterized by recurring shapes: category-label run patterns, paired right-tab metadata rows, single metadata rows, and numbered or marked paragraphs. Neighbor relationships distinguish primary title/date rows from tighter employer/location rows, entry transitions, section transitions, and final paragraphs.

The output may preserve discovered section order as ordinal role sequences, but does not encode section labels, counts, employers, institutions, projects, skill-category limits, or bullet-count limits.

## Properties inspected

The python-docx object model validates document and section access. Direct OOXML inspection covers:

- `document.xml`: paragraphs, runs, paragraph/run properties, tabs, borders, indentation, spacing, keep/page controls, hyperlinks, section properties, and columns;
- `styles.xml`: named style chains and document defaults;
- `numbering.xml`: numbering IDs, levels, formats, marker text, and list indentation;
- `document.xml.rels`: hyperlink relationship presence and external/internal handling, with targets deliberately omitted;
- theme, settings, page, header, and footer metadata where present.

## JSON safety

Serialization contains formatting and inferred structural relationships only. Hyperlink targets and visible document text are excluded. Example shape:

```json
{
  "schema_version": "1.0",
  "page": {"width_twips": 0, "orientation": "portrait"},
  "semantic_roles": {
    "section_heading": {
      "occurrence_count": 0,
      "borders": [{"position": "bottom", "provenance": "direct_paragraph_property"}],
      "neighboring_roles": ["skill_category_row"]
    }
  }
}
```

The zeroes above illustrate the schema only; real values always come from the analyzed DOCX.

## Known limitations

- Semantic inference is intentionally heuristic because DOCX has no resume-role vocabulary. Highly unusual structures or table/text-box-based resumes may need additional structural classifiers.
- Theme-font resolution is recorded through observed style properties but theme substitution can vary by Word installation.
- Floating shapes, text boxes, tracked changes, and field-result layout are not yet semantic-role inputs.
- Visual rendering is a verification aid; DOCX structure remains authoritative.
- A later renderer should accept a validated `LayoutProfile`, map structured resume elements to semantic roles, and apply the observed values deterministically. It should not re-infer roles or silently fall back to hardcoded layout values.

