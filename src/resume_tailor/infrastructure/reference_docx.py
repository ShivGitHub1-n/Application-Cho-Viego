from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from zipfile import BadZipFile, ZipFile
import xml.etree.ElementTree as ET

from docx import Document

from resume_tailor.domain.layout import (
    Border,
    BulletLayout,
    HyperlinkLayout,
    LayoutProfile,
    MetadataAnchorGroup,
    ObservedValue,
    PageLayout,
    ParagraphLayout,
    RunPattern,
    SectionPattern,
    SemanticRoleLayout,
    TabStop,
    Typography,
    TransitionSpacing,
)

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


class ReferenceDocxAnalysisError(ValueError):
    """Raised when a reference DOCX cannot produce a trustworthy layout profile."""


@dataclass
class _Paragraph:
    index: int
    text: str
    style_id: str | None
    p: ET.Element
    runs: list[ET.Element]
    hyperlinks: list[ET.Element]
    paragraph_layout: ParagraphLayout
    typography: Typography
    run_typographies: list[Typography]
    tabs: list[TabStop]
    borders: list[Border]
    bullet: BulletLayout | None


def analyze_reference_docx(path: Path) -> LayoutProfile:
    """Derive a deterministic, content-free layout contract from a DOCX reference."""
    if not path.is_file():
        raise ReferenceDocxAnalysisError(f"Reference DOCX does not exist: {path}")
    try:
        # Deliberately exercise python-docx as one of the two authoritative views.
        object_document = Document(path)
        with ZipFile(path) as package:
            required = {"word/document.xml", "word/styles.xml"}
            missing = required - set(package.namelist())
            if missing:
                raise ReferenceDocxAnalysisError(
                    f"Reference DOCX is missing required parts: {sorted(missing)}"
                )
            parts = {name: package.read(name) for name in package.namelist() if name.endswith(".xml") or name.endswith(".rels")}
    except (BadZipFile, KeyError, ValueError) as error:
        raise ReferenceDocxAnalysisError(f"Invalid reference DOCX: {path}") from error

    document = ET.fromstring(parts["word/document.xml"])
    styles = ET.fromstring(parts["word/styles.xml"])
    numbering = ET.fromstring(parts["word/numbering.xml"]) if "word/numbering.xml" in parts else None
    rels = ET.fromstring(parts["word/_rels/document.xml.rels"]) if "word/_rels/document.xml.rels" in parts else None
    style_map, defaults = _style_map(styles)
    numbering_map = _numbering_map(numbering)
    external_rel_ids = _external_hyperlink_ids(rels)
    paragraphs = _paragraphs(document, style_map, defaults, numbering_map)
    if len(object_document.paragraphs) != len(document.findall(f".//{W}body/{W}p")):
        raise ReferenceDocxAnalysisError("python-docx and document.xml paragraph views disagree")
    nonempty = [paragraph for paragraph in paragraphs if paragraph.text.strip()]
    if not nonempty:
        raise ReferenceDocxAnalysisError("Reference DOCX contains no analyzable paragraphs")

    roles = _infer_roles(nonempty)
    semantic_roles = _aggregate_roles(nonempty, roles, external_rel_ids)
    page_layout = _page_layout(document)
    metadata_anchor_groups = _metadata_anchor_groups(page_layout, semantic_roles)
    _validate_metadata_anchor_groups(page_layout, metadata_anchor_groups)
    semantic_roles = _attach_metadata_anchor_group_ids(
        semantic_roles,
        metadata_anchor_groups,
    )
    return LayoutProfile(
        page=_page_layout(document),
        semantic_roles=semantic_roles,
        metadata_anchor_groups=metadata_anchor_groups,
        section_patterns=_section_patterns(nonempty, roles),
        transition_spacings=_transition_spacings(paragraphs, nonempty, roles),
        inspected_parts=sorted(
            name for name in parts if name in {
                "word/document.xml",
                "word/styles.xml",
                "word/numbering.xml",
                "word/_rels/document.xml.rels",
                "word/settings.xml",
                "word/theme/theme1.xml",
            }
        ),
    )


def _attr(element: ET.Element | None, name: str) -> str | None:
    return None if element is None else element.get(f"{W}{name}")


def _style_map(styles: ET.Element) -> tuple[dict[str, ET.Element], dict[str, ET.Element | None]]:
    mapping = {_attr(style, "styleId") or "": style for style in styles.findall(f"{W}style")}
    defaults = styles.find(f"{W}docDefaults")
    return mapping, {
        "pPr": defaults.find(f"{W}pPrDefault/{W}pPr") if defaults is not None else None,
        "rPr": defaults.find(f"{W}rPrDefault/{W}rPr") if defaults is not None else None,
    }


def _property(
    direct: ET.Element | None,
    style_id: str | None,
    style_map: dict[str, ET.Element],
    default: ET.Element | None,
    tag: str,
) -> tuple[ET.Element | None, str]:
    found = direct.find(f"{W}{tag}") if direct is not None else None
    if found is not None:
        return found, "direct_paragraph_property"
    seen: set[str] = set()
    current = style_id
    while current and current not in seen:
        seen.add(current)
        style = style_map.get(current)
        if style is None:
            break
        for container_name in ("pPr", "rPr"):
            container = style.find(f"{W}{container_name}")
            found = container.find(f"{W}{tag}") if container is not None else None
            if found is not None:
                return found, "named_style" if current == style_id else "inherited_style"
        based_on = style.find(f"{W}basedOn")
        current = _attr(based_on, "val")
    found = default.find(f"{W}{tag}") if default is not None else None
    return (found, "document_default") if found is not None else (None, "not_present")


def _value(element: ET.Element | None, provenance: str, attribute: str = "val", fallback=None) -> ObservedValue:
    raw = _attr(element, attribute)
    if element is None:
        value = fallback
    elif raw is None and attribute == "val":
        value = True
    elif raw in {"true", "1", "on"}:
        value = True
    elif raw in {"false", "0", "off", "none"}:
        value = False if raw != "none" else "none"
    else:
        try:
            value = int(raw) if raw is not None else fallback
        except ValueError:
            value = raw
    return ObservedValue(value=value, provenance=provenance)  # type: ignore[arg-type]


def _twips_value(element: ET.Element | None, provenance: str, attribute: str) -> ObservedValue:
    """Read a numeric spacing attribute without confusing auto flags for twips."""
    raw = _attr(element, attribute)
    if raw is None:
        return ObservedValue(value=None, provenance=provenance)
    try:
        return ObservedValue(value=int(raw), provenance=provenance)
    except ValueError:
        return ObservedValue(value=None, provenance=provenance)


def _flag_value(element: ET.Element | None, provenance: str, attribute: str) -> ObservedValue:
    raw = _attr(element, attribute)
    if raw is None:
        return ObservedValue(value=None, provenance=provenance)
    return ObservedValue(
        value=raw in {"true", "1", "on"},
        provenance=provenance,
    )


def _paragraph_layout(p_pr, style_id, styles, defaults) -> ParagraphLayout:
    def get(tag):
        return _property(p_pr, style_id, styles, defaults["pPr"], tag)
    spacing, spacing_source = get("spacing")
    ind, ind_source = get("ind")
    return ParagraphLayout(
        alignment=_value(*get("jc")),
        space_before_twips=_twips_value(spacing, spacing_source, "before"),
        space_after_twips=_twips_value(spacing, spacing_source, "after"),
        before_auto_spacing=_flag_value(spacing, spacing_source, "beforeAutospacing"),
        after_auto_spacing=_flag_value(spacing, spacing_source, "afterAutospacing"),
        contextual_spacing=_value(*get("contextualSpacing")),
        line_spacing_twips=_value(spacing, spacing_source, "line"),
        line_spacing_rule=_value(spacing, spacing_source, "lineRule"),
        left_indent_twips=_value(ind, ind_source, "left"),
        right_indent_twips=_value(ind, ind_source, "right"),
        first_line_indent_twips=_value(ind, ind_source, "firstLine"),
        hanging_indent_twips=_value(ind, ind_source, "hanging"),
        keep_with_next=_value(*get("keepNext")),
        keep_together=_value(*get("keepLines")),
        widow_control=_value(*get("widowControl")),
        page_break_before=_value(*get("pageBreakBefore")),
    )


def _typography(r_pr, style_id, styles, defaults, direct_source="direct_run_property") -> Typography:
    def get(tag):
        element, source = _property(r_pr, style_id, styles, defaults["rPr"], tag)
        if element is not None and source == "direct_paragraph_property":
            source = direct_source
        return element, source
    fonts, font_source = get("rFonts")
    return Typography(
        font_family=_value(fonts, font_source, "ascii"),
        font_size_half_points=_value(*get("sz")),
        bold=_value(*get("b"), fallback=False),
        italic=_value(*get("i"), fallback=False),
        underline=_value(*get("u"), fallback="none"),
        color=_value(*get("color")),
        character_spacing_twips=_value(*get("spacing")),
    )


def _paragraphs(document, styles, defaults, numbering_map) -> list[_Paragraph]:
    result = []
    for index, p in enumerate(document.findall(f".//{W}body/{W}p")):
        p_pr = p.find(f"{W}pPr")
        style_id = _attr(p_pr.find(f"{W}pStyle") if p_pr is not None else None, "val")
        runs = p.findall(f".//{W}r")
        hyperlinks = p.findall(f"{W}hyperlink")
        first_r_pr = runs[0].find(f"{W}rPr") if runs else None
        run_typographies = [
            _typography(run.find(f"{W}rPr"), style_id, styles, defaults)
            for run in runs
        ]
        text = "".join(node.text or "" for node in p.findall(f".//{W}t"))
        literal_tab_count = len(p.findall(f".//{W}r/{W}tab"))
        tabs = _tabs(
            p_pr,
            style_id,
            styles,
            defaults,
            has_literal_tab=literal_tab_count > 0,
        )
        bullet = _bullet(p_pr, style_id, styles, defaults, numbering_map, text)
        result.append(_Paragraph(
            index=index,
            text=text,
            style_id=style_id,
            p=p,
            runs=runs,
            hyperlinks=hyperlinks,
            paragraph_layout=_paragraph_layout(p_pr, style_id, styles, defaults),
            typography=_typography(first_r_pr, style_id, styles, defaults),
            run_typographies=run_typographies,
            tabs=tabs,
            borders=[
                *_borders(p_pr, style_id, styles, defaults),
                *_drawing_separator_borders(p, "direct_drawing_separator"),
            ],
            bullet=bullet,
        ))
    # Some Word-authored resumes place the visible rule in a dedicated, empty
    # drawing paragraph immediately after its heading. Associate that rule with
    # the preceding semantic paragraph before empty paragraphs are discarded.
    for current, following in zip(result, result[1:]):
        if current.text.strip() and not following.text.strip():
            current.borders.extend(
                _drawing_separator_borders(following.p, "adjacent_drawing_separator")
            )
    return result


def _tabs(p_pr, style_id, styles, defaults, *, has_literal_tab: bool) -> list[TabStop]:
    tabs, source = _property(p_pr, style_id, styles, defaults["pPr"], "tabs")
    if tabs is None:
        return []
    result = []
    for tab in tabs.findall(f"{W}tab"):
        alignment = _attr(tab, "val") or "left"
        semantic_use = None
        if alignment == "right":
            semantic_use = "right_aligned_metadata"
        elif has_literal_tab:
            # A literal w:tab followed by a positioned left/center/decimal stop
            # creates a reusable second metadata column even though its text is
            # not right-aligned at the stop.
            semantic_use = "positioned_metadata_column"
        result.append(TabStop(
            position_twips=int(_attr(tab, "pos") or 0),
            alignment=alignment,
            leader=_attr(tab, "leader"),
            semantic_use=semantic_use,
            provenance=source,
        ))
    return result


def _borders(p_pr, style_id, styles, defaults) -> list[Border]:
    borders, source = _property(p_pr, style_id, styles, defaults["pPr"], "pBdr")
    if borders is None:
        return []
    return [Border(
        position=node.tag.removeprefix(W),
        style=_attr(node, "val") or "none",
        thickness_eighth_points=int(_attr(node, "sz")) if _attr(node, "sz") else None,
        spacing_points=int(_attr(node, "space")) if _attr(node, "space") else None,
        color=_attr(node, "color"),
        provenance=source,
    ) for node in list(borders)]


def _drawing_separator_borders(paragraph: ET.Element, provenance: str) -> list[Border]:
    """Read horizontal DrawingML rules used visually as paragraph borders."""
    borders: list[Border] = []
    for line in paragraph.findall(f".//{A}ln"):
        dash = line.find(f"{A}prstDash")
        rgb = line.find(f"{A}solidFill/{A}srgbClr")
        system_color = line.find(f"{A}solidFill/{A}sysClr")
        width_emu = line.get("w")
        borders.append(
            Border(
                position="bottom",
                style=(dash.get("val") if dash is not None else None) or "solid",
                thickness_eighth_points=(
                    round(int(width_emu) * 8 / 12700) if width_emu else None
                ),
                color=(
                    rgb.get("val")
                    if rgb is not None
                    else system_color.get("lastClr") if system_color is not None else None
                ),
                provenance=provenance,
            )
        )
    return borders


def _numbering_map(root):
    if root is None:
        return {}
    abstracts = {}
    for abstract in root.findall(f"{W}abstractNum"):
        levels = {}
        for level in abstract.findall(f"{W}lvl"):
            levels[int(_attr(level, "ilvl") or 0)] = level
        abstracts[int(_attr(abstract, "abstractNumId") or 0)] = levels
    mapping = {}
    for num in root.findall(f"{W}num"):
        abstract_id = int(_attr(num.find(f"{W}abstractNumId"), "val") or 0)
        mapping[int(_attr(num, "numId") or 0)] = abstracts.get(abstract_id, {})
    return mapping


def _bullet(p_pr, style_id, styles, defaults, numbering_map, text):
    num_pr, _ = _property(p_pr, style_id, styles, defaults["pPr"], "numPr")
    ind, _ = _property(p_pr, style_id, styles, defaults["pPr"], "ind")
    num_id = level_id = None
    number_format = None
    representation = None
    marker_typography = None
    mechanism = "literal_marker"
    provenance = "direct_run_property"
    if num_pr is not None:
        num_id = int(_attr(num_pr.find(f"{W}numId"), "val") or 0)
        level_id = int(_attr(num_pr.find(f"{W}ilvl"), "val") or 0)
        level = numbering_map.get(num_id, {}).get(level_id)
        number_format = _attr(level.find(f"{W}numFmt") if level is not None else None, "val")
        representation = _attr(level.find(f"{W}lvlText") if level is not None else None, "val")
        level_r_pr = level.find(f"{W}rPr") if level is not None else None
        marker_typography = _typography(
            level_r_pr,
            None,
            styles,
            defaults,
            direct_source="numbering_definition",
        )
        mechanism = "numbering"
        provenance = "numbering_definition"
    elif text.lstrip().startswith(("•", "-", "–", "—")):
        representation = text.lstrip()[0]
    else:
        return None
    left = int(_attr(ind, "left")) if _attr(ind, "left") else None
    hanging = int(_attr(ind, "hanging")) if _attr(ind, "hanging") else None
    spacing, _ = _property(p_pr, style_id, styles, defaults["pPr"], "spacing")
    return BulletLayout(
        representation=representation,
        numbering_id=num_id,
        numbering_level=level_id,
        numbering_format=number_format,
        marker_typography=marker_typography,
        mechanism=mechanism,
        provenance=provenance,
        left_indent_twips=left,
        hanging_indent_twips=hanging,
        wrapped_line_alignment_twips=left,
        space_before_twips=_int_or_none(_attr(spacing, "before")),
        space_after_twips=_int_or_none(_attr(spacing, "after")),
    )


def _int_or_none(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _infer_roles(paragraphs: list[_Paragraph]) -> list[str]:
    roles = ["ordinary_paragraph"] * len(paragraphs)
    roles[0] = "name"
    if len(paragraphs) > 1:
        roles[1] = "contact_line"
    headings = {i for i, p in enumerate(paragraphs) if p.borders or _heading_shape(p)}
    for i in headings:
        if i > 1:
            roles[i] = "section_heading"
    boundaries = sorted(headings) + [len(paragraphs)]
    starts = [i + 1 for i in sorted(headings)]
    for section_ordinal, (start, end) in enumerate(zip(starts, boundaries[1:])):
        members = list(range(start, end))
        if not members:
            continue
        bullets = [i for i in members if paragraphs[i].bullet]
        skill_rows = [i for i in members if _skill_shape(paragraphs[i])]
        tab_rows = [
            i
            for i in members
            if any(
                tab.semantic_use in {"right_aligned_metadata", "positioned_metadata_column"}
                for tab in paragraphs[i].tabs
            )
        ]
        if skill_rows and len(skill_rows) >= max(1, len(members) - 1):
            for i in members:
                roles[i] = "skill_category_row"
        elif bullets and tab_rows:
            has_paired_metadata_rows = any(
                members[position - 1] in tab_rows
                for position in range(1, len(members))
                if members[position] in tab_rows
            )
            if section_ordinal == 0 and has_paired_metadata_rows:
                for position, i in enumerate(tab_rows):
                    roles[i] = (
                        "education_institution_date_row"
                        if position % 2 == 0
                        else "education_program_location_row"
                    )
                for i in bullets:
                    roles[i] = "education_detail_bullet"
                continue
            if not has_paired_metadata_rows:
                for i in tab_rows:
                    roles[i] = "project_title_metadata_row"
                for i in bullets:
                    roles[i] = "project_bullet"
                continue
            for position, i in enumerate(members):
                if paragraphs[i].bullet:
                    roles[i] = "experience_bullet"
                elif i in tab_rows:
                    previous_is_row = position > 0 and members[position - 1] in tab_rows
                    roles[i] = "employer_location_row" if previous_is_row else "experience_title_date_row"
        elif tab_rows:
            for position, i in enumerate(tab_rows):
                roles[i] = "education_institution_date_row" if position % 2 == 0 else "education_program_location_row"
            for i in bullets:
                roles[i] = "education_detail_bullet"
        elif bullets:
            # A project block may use numbered paragraphs without a semantic
            # metadata tab. Its structural shape is still a title followed by
            # bullets, so classify it from roles and neighbors, never text.
            first = members[0]
            if not paragraphs[first].bullet:
                roles[first] = "project_title_metadata_row"
            for i in bullets:
                roles[i] = "project_bullet"
    _mark_transitions(paragraphs, roles)
    return roles


def _heading_shape(paragraph: _Paragraph) -> bool:
    compact = paragraph.text.strip()
    return bool(compact) and len(compact) <= 48 and compact.upper() == compact and not paragraph.tabs and paragraph.bullet is None


def _skill_shape(paragraph: _Paragraph) -> bool:
    if paragraph.bullet or paragraph.tabs:
        return False
    texts = ["".join(t.text or "" for t in run.findall(f".//{W}t")) for run in paragraph.runs]
    return bool(texts) and any(text.rstrip().endswith(":") for text in texts[:2]) and len(paragraph.runs) > 1


def _mark_transitions(paragraphs, roles):
    section_headings = [i for i, role in enumerate(roles) if role == "section_heading"]
    for heading_index in section_headings:
        previous = heading_index - 1
        if previous >= 0 and roles[previous] in {"experience_bullet", "project_bullet", "education_detail_bullet"}:
            roles[previous] = "final_paragraph_in_section"
    for i in range(1, len(roles)):
        if roles[i] in {"experience_title_date_row", "project_title_metadata_row"} and roles[i - 1] in {"experience_bullet", "project_bullet"}:
            roles[i] = "interior_entry_transition"


def _aggregate_roles(paragraphs, roles, external_rel_ids):
    grouped = defaultdict(list)
    for paragraph, role in zip(paragraphs, roles):
        grouped[role].append(paragraph)
    result = {}
    for role, items in grouped.items():
        representative = items[0]
        neighbors = []
        for position, paragraph_role in enumerate(roles):
            if paragraph_role != role:
                continue
            for neighbor_position in (position - 1, position + 1):
                if 0 <= neighbor_position < len(roles):
                    neighbor_role = roles[neighbor_position]
                    if neighbor_role != role and neighbor_role not in neighbors:
                        neighbors.append(neighbor_role)
        patterns = [_run_pattern(item) for item in items]
        hyperlinks = _hyperlink_layout(items, external_rel_ids) if any(item.hyperlinks for item in items) else None
        result[role] = SemanticRoleLayout(
            role=role,
            occurrence_count=len(items),
            paragraph=representative.paragraph_layout,
            primary_typography=representative.typography,
            run_patterns=_dedupe_models(patterns),
            tab_stops=_dedupe_models(tab for item in items for tab in item.tabs),
            borders=_dedupe_models(border for item in items for border in item.borders),
            bullet=next((item.bullet for item in items if item.bullet), None),
            hyperlinks=hyperlinks,
            neighboring_roles=neighbors,
            inference_signals=_signals(role, representative),
        )
    if "section_heading" in result:
        result["section_transition"] = result["section_heading"].model_copy(
            update={
                "role": "section_transition",
                "inference_signals": [
                    "section_heading_spacing_and_border",
                    "relationship_to_previous_final_paragraph",
                ],
            }
        )
    return result


def _metadata_anchor_groups(
    page: PageLayout,
    semantic_roles: dict[str, SemanticRoleLayout],
) -> list[MetadataAnchorGroup]:
    """Cluster recurring metadata tabs using a usable-width-relative tolerance."""
    tolerance = max(1, round(page.usable_width_twips * 0.015))
    observations = sorted(
        (
            tab.position_twips,
            role_name,
        )
        for role_name, role in semantic_roles.items()
        if role_name != "section_transition"
        for tab in role.tab_stops
        if tab.semantic_use in {"right_aligned_metadata", "positioned_metadata_column"}
    )
    clusters: list[list[tuple[int, str]]] = []
    for position, role_name in observations:
        if not clusters or position - clusters[-1][-1][0] > tolerance:
            clusters.append([])
        clusters[-1].append((position, role_name))

    groups: list[MetadataAnchorGroup] = []
    for index, cluster in enumerate(clusters):
        positions = sorted(position for position, _ in cluster)
        middle = len(positions) // 2
        representative = (
            positions[middle]
            if len(positions) % 2
            else round((positions[middle - 1] + positions[middle]) / 2)
        )
        groups.append(
            MetadataAnchorGroup(
                group_id=f"metadata_anchor_{index}",
                observed_positions_twips=positions,
                representative_position_twips=representative,
                role_groups=sorted({role_name for _, role_name in cluster}),
                tolerance_twips=tolerance,
                relative_tolerance=tolerance / page.usable_width_twips,
                provenance=[
                    "direct_paragraph_property",
                    "clustered_by_usable_width_relative_tolerance",
                    "representative_median",
                ],
            )
        )
    return groups


def _attach_metadata_anchor_group_ids(
    semantic_roles: dict[str, SemanticRoleLayout],
    groups: list[MetadataAnchorGroup],
) -> dict[str, SemanticRoleLayout]:
    return {
        role_name: role.model_copy(
            update={
                "metadata_anchor_group_ids": [
                    group.group_id
                    for group in groups
                    if role_name in group.role_groups
                ]
            }
        )
        for role_name, role in semantic_roles.items()
    }


def _validate_metadata_anchor_groups(
    page: PageLayout,
    groups: list[MetadataAnchorGroup],
) -> None:
    for group in groups:
        for position in [
            *group.observed_positions_twips,
            group.representative_position_twips,
        ]:
            if position < 0 or position > page.usable_width_twips:
                raise ReferenceDocxAnalysisError(
                    "Reference metadata tab position falls outside the usable page width: "
                    f"{position} twips versus {page.usable_width_twips} twips."
                )


def _run_pattern(paragraph):
    bold = []
    italic = []
    hyperlink_positions = []
    variants = _dedupe_models(paragraph.run_typographies)
    hyperlink_runs = {id(run) for link in paragraph.hyperlinks for run in link.findall(f".//{W}r")}
    for index, run in enumerate(paragraph.runs):
        r_pr = run.find(f"{W}rPr")
        b = r_pr.find(f"{W}b") if r_pr is not None else None
        i = r_pr.find(f"{W}i") if r_pr is not None else None
        if b is not None and _attr(b, "val") not in {"0", "false", "off"}:
            bold.append(index)
        if i is not None and _attr(i, "val") not in {"0", "false", "off"}:
            italic.append(index)
        if id(run) in hyperlink_runs:
            hyperlink_positions.append(index)
    return RunPattern(run_count=len(paragraph.runs), bold_run_positions=bold, italic_run_positions=italic, hyperlink_run_positions=hyperlink_positions, typography_variants=variants)


def _external_hyperlink_ids(rels):
    if rels is None:
        return set()
    return {
        rel.get("Id") for rel in rels.findall(f"{PKG_REL}Relationship")
        if rel.get("TargetMode") == "External" and rel.get("Type", "").endswith("/hyperlink")
    }


def _hyperlink_layout(items, external_rel_ids):
    external = internal = 0
    compact = False
    for item in items:
        compact = compact or (item.paragraph_layout.alignment.value == "center" and len(item.hyperlinks) > 0)
        for link in item.hyperlinks:
            relationship_id = link.get(f"{R}id")
            if relationship_id in external_rel_ids:
                external += 1
            elif _attr(link, "anchor"):
                internal += 1
    typography = items[0].typography
    return HyperlinkLayout(
        present=True,
        external_relationship_count=external,
        internal_anchor_count=internal,
        display_typography=typography,
        underline_behavior=str(typography.underline.value),
        color_behavior=str(typography.color.value),
        compact_contact_line=compact,
    )


def _signals(role, paragraph):
    signals = ["position_and_neighbor_relationships", "recurring_formatting_signature"]
    if paragraph.borders:
        signals.append("paragraph_border")
    if paragraph.tabs:
        signals.append("tab_stop_pattern")
    if paragraph.bullet:
        signals.append("numbering_or_marker_and_indentation")
    if paragraph.hyperlinks:
        signals.append("hyperlink_presence")
    if role == "name":
        signals.append("first_nonempty_paragraph")
    return signals


def _section_patterns(paragraphs, roles):
    heading_positions = [i for i, role in enumerate(roles) if role == "section_heading"]
    result = []
    for ordinal, start in enumerate(heading_positions):
        end = heading_positions[ordinal + 1] if ordinal + 1 < len(heading_positions) else len(roles)
        transition = paragraphs[end - 1].paragraph_layout.space_after_twips.value if end > start else None
        result.append(SectionPattern(ordinal=ordinal, role_sequence=roles[start:end], transition_after_twips=transition if isinstance(transition, int) else None))
    return result


def _transition_spacings(
    all_paragraphs: list[_Paragraph],
    semantic_paragraphs: list[_Paragraph],
    roles: list[str],
) -> list[TransitionSpacing]:
    """Measure visual rhythm between adjacent semantic paragraphs.

    Word resolves a transition from both paragraphs plus any intervening empty
    paragraphs. Keeping those components separate avoids inventing a single
    rendered-gap value that OOXML does not contain.
    """
    grouped: dict[str, TransitionSpacing] = {}
    transitions: list[TransitionSpacing] = []
    for position in range(len(semantic_paragraphs) - 1):
        source = semantic_paragraphs[position]
        destination = semantic_paragraphs[position + 1]
        empty = [
            paragraph
            for paragraph in all_paragraphs
            if source.index < paragraph.index < destination.index
            and not paragraph.text.strip()
        ]
        provenance = [
            f"source_space_after:{source.paragraph_layout.space_after_twips.provenance}",
            f"destination_space_before:{destination.paragraph_layout.space_before_twips.provenance}",
        ]
        if empty:
            provenance.append("intervening_empty_paragraph_properties")
        if any(paragraph.borders for paragraph in empty):
            provenance.append("intervening_drawing_separator")
        transition = TransitionSpacing(
            source_role=roles[position],
            destination_role=roles[position + 1],
            destination_section_first_role=(
                roles[position + 2]
                if roles[position + 1] == "section_heading" and position + 2 < len(roles)
                else None
            ),
            source_space_after_twips=source.paragraph_layout.space_after_twips,
            destination_space_before_twips=destination.paragraph_layout.space_before_twips,
            empty_paragraph_count=len(empty),
            empty_space_before_twips=[
                paragraph.paragraph_layout.space_before_twips for paragraph in empty
            ],
            empty_space_after_twips=[
                paragraph.paragraph_layout.space_after_twips for paragraph in empty
            ],
            empty_line_spacing_twips=[
                paragraph.paragraph_layout.line_spacing_twips for paragraph in empty
            ],
            empty_line_spacing_rules=[
                paragraph.paragraph_layout.line_spacing_rule for paragraph in empty
            ],
            drawing_separator_present=any(paragraph.borders for paragraph in empty),
            provenance=provenance,
        )
        signature = transition.model_copy(update={"occurrence_count": 1}).model_dump_json()
        if signature in grouped:
            grouped[signature].occurrence_count += 1
        else:
            grouped[signature] = transition
    transitions = list(grouped.values())
    return _resolve_transition_values(transitions)


def _resolve_transition_values(
    transitions: list[TransitionSpacing],
) -> list[TransitionSpacing]:
    """Attach dominant, role-pair-specific values without flattening transitions."""
    groups: dict[tuple[str, str, str | None], list[TransitionSpacing]] = defaultdict(list)
    for transition in transitions:
        groups[
            (
                transition.source_role,
                transition.destination_role,
                transition.destination_section_first_role
                if transition.destination_role == "section_heading"
                else None,
            )
        ].append(transition)

    resolved: list[TransitionSpacing] = []
    for transition in transitions:
        group = groups[
            (
                transition.source_role,
                transition.destination_role,
                transition.destination_section_first_role
                if transition.destination_role == "section_heading"
                else None,
            )
        ]
        source = _dominant_twips(
            [
                (item.source_space_after_twips, item.occurrence_count)
                for item in group
            ]
        )
        destination = _dominant_twips(
            [
                (item.destination_space_before_twips, item.occurrence_count)
                for item in group
            ]
        )
        resolved.append(
            transition.model_copy(
                update={
                    "resolved_source_space_after_twips": source,
                    "resolved_destination_space_before_twips": destination,
                    "provenance": [
                        *transition.provenance,
                        "resolved_by_dominant_semantic_transition_value",
                    ],
                }
            )
        )
    return resolved


def _dominant_twips(values: list[tuple[ObservedValue, int]]) -> ObservedValue:
    counts: dict[int | None, int] = defaultdict(int)
    for observed, occurrence_count in values:
        value = observed.value if isinstance(observed.value, int) and not isinstance(observed.value, bool) else None
        counts[value] += occurrence_count
    value = max(counts, key=lambda item: (counts[item], item is not None, -(item or 0)))
    return ObservedValue(value=value, provenance="inferred_recurring_pattern")


def _page_layout(document):
    section = document.find(f".//{W}body/{W}sectPr")
    if section is None:
        raise ReferenceDocxAnalysisError("Reference DOCX has no section properties")
    size = section.find(f"{W}pgSz")
    margin = section.find(f"{W}pgMar")
    if size is None or margin is None:
        raise ReferenceDocxAnalysisError("Reference DOCX has incomplete page geometry")
    columns = section.find(f"{W}cols")
    return PageLayout(
        width_twips=int(_attr(size, "w") or 0),
        height_twips=int(_attr(size, "h") or 0),
        top_margin_twips=int(_attr(margin, "top") or 0),
        bottom_margin_twips=int(_attr(margin, "bottom") or 0),
        left_margin_twips=int(_attr(margin, "left") or 0),
        right_margin_twips=int(_attr(margin, "right") or 0),
        header_distance_twips=int(_attr(margin, "header") or 0),
        footer_distance_twips=int(_attr(margin, "footer") or 0),
        orientation=_attr(size, "orient") or "portrait",
        column_count=int(_attr(columns, "num") or 1),
        column_spacing_twips=int(_attr(columns, "space")) if _attr(columns, "space") else None,
        column_equal_width=(_attr(columns, "equalWidth") not in {"0", "false"}) if columns is not None else None,
    )


def _dedupe_models(models: Iterable):
    result = []
    seen = set()
    for model in models:
        key = model.model_dump_json()
        if key not in seen:
            seen.add(key)
            result.append(model)
    return result
