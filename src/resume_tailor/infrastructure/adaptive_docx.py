from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from docx import Document
from docx.document import Document as DocumentType
from docx.enum.section import WD_ORIENT
from docx.enum.text import (
    WD_ALIGN_PARAGRAPH,
    WD_LINE_SPACING,
    WD_TAB_ALIGNMENT,
    WD_TAB_LEADER,
)
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.shared import Pt, RGBColor, Twips
from docx.text.paragraph import Paragraph
from docx.text.run import Run

from resume_tailor.domain.layout import (
    Border,
    LayoutProfile,
    SemanticRoleLayout,
    TabStop,
    Typography,
)
from resume_tailor.domain.models import EntityKind, ResumeItem, StructuredBullet, StructuredResume


class AdaptiveDocxRenderError(ValueError):
    pass


@dataclass(frozen=True)
class _Fallbacks:
    """Generic values used only when a property is absent from LayoutProfile."""

    font_family: str = "Times New Roman"
    font_size_points: float = 10.0
    font_color: str = "000000"
    bullet_marker: str = "•"
    contact_separator: str = " | "


_FALLBACKS = _Fallbacks()


def render_structured_resume(
    resume: StructuredResume,
    layout_profile: LayoutProfile,
    output_path: Path,
) -> Path:
    renderer = AdaptiveStructuredResumeRenderer(layout_profile)
    return renderer.render(resume, output_path)


class AdaptiveStructuredResumeRenderer:
    def __init__(self, layout_profile: LayoutProfile) -> None:
        self._profile = layout_profile
        self._last_paragraph: Paragraph | None = None
        self._last_role: str | None = None

    def render(self, resume: StructuredResume, output_path: Path) -> Path:
        required_roles = {"name", "contact_line", "section_heading"}
        missing = required_roles - set(self._profile.semantic_roles)
        if missing:
            raise AdaptiveDocxRenderError(
                f"LayoutProfile is missing required semantic roles: {sorted(missing)}"
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        document = Document()
        self._apply_page_layout(document)
        self._add_text_paragraph(document, "name", [(resume.display_name, None)])
        if resume.contact_line:
            self._add_contact_line(document, resume.contact_line)
        if resume.education:
            self._add_section_heading(document, "Education")
            self._add_education(document, resume)
        if resume.technical_skills or resume.selected_skills:
            self._add_section_heading(document, "Technical Skills")
            self._add_skills(document, resume)
        if resume.experience_bullets:
            self._add_section_heading(document, "Technical Experience")
            self._add_experiences(document, resume)
        if resume.project_bullets:
            self._add_section_heading(document, "Projects")
            self._add_projects(document, resume)
        document.save(output_path)
        return output_path

    def _apply_page_layout(self, document: DocumentType) -> None:
        page = self._profile.page
        section = document.sections[0]
        section.page_width = Twips(page.width_twips)
        section.page_height = Twips(page.height_twips)
        section.top_margin = Twips(page.top_margin_twips)
        section.bottom_margin = Twips(page.bottom_margin_twips)
        section.left_margin = Twips(page.left_margin_twips)
        section.right_margin = Twips(page.right_margin_twips)
        section.header_distance = Twips(page.header_distance_twips)
        section.footer_distance = Twips(page.footer_distance_twips)
        section.orientation = (
            WD_ORIENT.LANDSCAPE if page.orientation == "landscape" else WD_ORIENT.PORTRAIT
        )
        section_properties = section._sectPr
        columns = section_properties.find(qn("w:cols"))
        if columns is None:
            columns = OxmlElement("w:cols")
            section_properties.append(columns)
        columns.set(qn("w:num"), str(page.column_count))
        if page.column_spacing_twips is not None:
            columns.set(qn("w:space"), str(page.column_spacing_twips))
        if page.column_equal_width is not None:
            columns.set(qn("w:equalWidth"), "1" if page.column_equal_width else "0")

    def _add_contact_line(self, document: DocumentType, contact_line: str) -> None:
        parts = [part.strip() for part in contact_line.split("|") if part.strip()]
        paragraph = self._new_paragraph(document, "contact_line")
        for index, part in enumerate(parts):
            if index:
                run = paragraph.add_run(_FALLBACKS.contact_separator)
                self._apply_run(run, self._role("contact_line"), index)
            target = _hyperlink_target(part)
            if target:
                self._add_hyperlink(paragraph, part, target, self._role("contact_line"))
            else:
                run = paragraph.add_run(part)
                self._apply_run(run, self._role("contact_line"), index)

    def _add_section_heading(self, document: DocumentType, label: str) -> None:
        self._add_text_paragraph(document, "section_heading", [(label, None)])

    def _add_education(self, document: DocumentType, resume: StructuredResume) -> None:
        for record in resume.education:
            date = _date_range(
                record.start_date,
                record.expected_graduation_date or record.graduation_date,
            )
            self._add_metadata_row(
                document,
                "education_institution_date_row",
                record.school,
                date,
            )
            self._add_metadata_row(
                document,
                "education_program_location_row",
                record.program,
                record.location,
            )
            details: list[str] = []
            if record.gpa:
                details.append(f"GPA: {record.gpa}")
            if record.awards:
                details.append(f"Awards: {', '.join(record.awards)}")
            coursework = record.relevant_coursework or resume.selected_coursework
            if coursework:
                details.append(f"Relevant Coursework: {', '.join(coursework)}")
            for detail in details:
                self._add_bullet(document, "education_detail_bullet", detail)
        if self._last_role == "education_detail_bullet":
            self._last_role = "final_paragraph_in_section"

    def _add_skills(self, document: DocumentType, resume: StructuredResume) -> None:
        if resume.technical_skills:
            for category in resume.technical_skills:
                values = category.values or [skill.value for skill in category.skills]
                if not values:
                    continue
                self._add_text_paragraph(
                    document,
                    "skill_category_row",
                    [(f"{category.category}: ", "label"), (", ".join(values), "values")],
                )
            return
        if resume.selected_skills:
            self._add_text_paragraph(
                document,
                "skill_category_row",
                [("Skills: ", "label"), (", ".join(resume.selected_skills), "values")],
            )

    def _add_experiences(self, document: DocumentType, resume: StructuredResume) -> None:
        records = _ordered_records(
            resume.experiences,
            resume.experience_bullets,
            resume.entity_titles,
            EntityKind.EXPERIENCE,
        )
        for entry_index, item in enumerate(records):
            role = "experience_title_date_row" if entry_index == 0 else "interior_entry_transition"
            left = item.title
            subtitle = item.subtitle or item.technology_label
            if subtitle and subtitle.casefold() not in left.casefold():
                left = f"{left} | {subtitle}"
            self._add_metadata_row(
                document,
                role,
                left,
                _date_range(item.start_date, item.end_date),
                layout_role="experience_title_date_row" if entry_index else None,
            )
            if item.organization or item.location:
                self._add_metadata_row(
                    document,
                    "employer_location_row",
                    item.organization,
                    item.location,
                )
            bullets = resume.experience_bullets.get(item.id, [])
            for bullet_index, bullet in enumerate(bullets):
                role = (
                    "final_paragraph_in_section"
                    if entry_index == len(records) - 1 and bullet_index == len(bullets) - 1
                    else "experience_bullet"
                )
                self._add_bullet(document, role, bullet.text, fallback_role="experience_bullet")

    def _add_projects(self, document: DocumentType, resume: StructuredResume) -> None:
        records = _ordered_records(
            resume.projects,
            resume.project_bullets,
            resume.entity_titles,
            EntityKind.PROJECT,
        )
        for entry_index, item in enumerate(records):
            left = item.title
            technology_label = item.technology_label or ", ".join(item.technologies)
            if technology_label and technology_label.casefold() not in left.casefold():
                left = f"{left} | {technology_label}"
            role = "project_title_metadata_row" if entry_index == 0 else "interior_entry_transition"
            self._add_metadata_row(
                document,
                role,
                left,
                _date_range(item.start_date, item.end_date),
                fallback_role="experience_title_date_row",
                layout_role="project_title_metadata_row" if entry_index else None,
            )
            bullets = resume.project_bullets.get(item.id, [])
            for bullet_index, bullet in enumerate(bullets):
                role = (
                    "final_paragraph_in_section"
                    if entry_index == len(records) - 1 and bullet_index == len(bullets) - 1
                    else "project_bullet"
                )
                self._add_bullet(document, role, bullet.text, fallback_role="experience_bullet")

    def _add_metadata_row(
        self,
        document: DocumentType,
        role_name: str,
        left: str | None,
        right: str | None,
        fallback_role: str | None = None,
        layout_role: str | None = None,
    ) -> Paragraph | None:
        if not left and not right:
            return None
        paragraph = self._new_paragraph(
            document,
            role_name,
            fallback_role,
            layout_role=layout_role,
        )
        role = self._role(layout_role or role_name, fallback_role)
        if left:
            left_run = paragraph.add_run(left)
            self._apply_run(left_run, role, 0)
        if right:
            if left:
                paragraph.add_run().add_tab()
            right_run = paragraph.add_run(right)
            self._apply_run(right_run, role, 1)
        return paragraph

    def _add_bullet(
        self,
        document: DocumentType,
        role_name: str,
        text: str,
        fallback_role: str | None = None,
    ) -> Paragraph:
        layout_role = fallback_role if role_name == "final_paragraph_in_section" else None
        paragraph = self._new_paragraph(
            document,
            role_name,
            fallback_role,
            layout_role=layout_role,
        )
        role = self._role(layout_role or role_name, fallback_role)
        marker = _bullet_marker(role)
        marker_run = paragraph.add_run(f"{marker}\t")
        self._apply_run(marker_run, role, 0)
        text_run = paragraph.add_run(text)
        self._apply_run(text_run, role, 1)
        return paragraph

    def _add_text_paragraph(
        self,
        document: DocumentType,
        role_name: str,
        pieces: list[tuple[str, str | None]],
        fallback_role: str | None = None,
    ) -> Paragraph:
        paragraph = self._new_paragraph(document, role_name, fallback_role)
        role = self._role(role_name, fallback_role)
        for index, (text, semantic) in enumerate(pieces):
            run = paragraph.add_run(text)
            self._apply_run(run, role, index)
            if semantic == "label":
                run.bold = True
        return paragraph

    def _new_paragraph(
        self,
        document: DocumentType,
        role_name: str,
        fallback_role: str | None = None,
        layout_role: str | None = None,
    ) -> Paragraph:
        paragraph = document.add_paragraph()
        role = self._role(layout_role or role_name, fallback_role)
        self._apply_paragraph(paragraph, role)
        self._apply_transition(paragraph, role_name)
        self._last_paragraph = paragraph
        self._last_role = role_name
        return paragraph

    def _role(
        self,
        role_name: str,
        fallback_role: str | None = None,
    ) -> SemanticRoleLayout:
        role = self._profile.semantic_roles.get(role_name)
        if role is None and fallback_role:
            role = self._profile.semantic_roles.get(fallback_role)
        if role is None:
            raise AdaptiveDocxRenderError(
                f"LayoutProfile is missing semantic role {role_name!r}"
            )
        return role

    def _apply_transition(self, destination: Paragraph, destination_role: str) -> None:
        if self._last_paragraph is None or self._last_role is None:
            return
        matches = [
            transition
            for transition in self._profile.transition_spacings
            if transition.source_role == self._last_role
            and transition.destination_role == destination_role
        ]
        if not matches:
            return
        transition = max(matches, key=lambda item: item.occurrence_count)
        source_after = transition.source_space_after_twips.value
        destination_before = transition.destination_space_before_twips.value
        if isinstance(source_after, int):
            self._last_paragraph.paragraph_format.space_after = Twips(source_after)
        if isinstance(destination_before, int):
            destination.paragraph_format.space_before = Twips(destination_before)

    def _apply_paragraph(self, paragraph: Paragraph, role: SemanticRoleLayout) -> None:
        layout = role.paragraph
        paragraph.alignment = _paragraph_alignment(layout.alignment.value)
        formatting = paragraph.paragraph_format
        _set_twips(formatting, "space_before", layout.space_before_twips.value)
        _set_twips(formatting, "space_after", layout.space_after_twips.value)
        _set_twips(formatting, "left_indent", layout.left_indent_twips.value)
        _set_twips(formatting, "right_indent", layout.right_indent_twips.value)
        if isinstance(layout.hanging_indent_twips.value, int):
            formatting.first_line_indent = Twips(-layout.hanging_indent_twips.value)
        elif isinstance(layout.first_line_indent_twips.value, int):
            formatting.first_line_indent = Twips(layout.first_line_indent_twips.value)
        if isinstance(layout.line_spacing_twips.value, int):
            formatting.line_spacing = Twips(layout.line_spacing_twips.value)
        formatting.line_spacing_rule = _line_spacing_rule(layout.line_spacing_rule.value)
        formatting.keep_with_next = _optional_bool(layout.keep_with_next.value)
        formatting.keep_together = _optional_bool(layout.keep_together.value)
        formatting.widow_control = _optional_bool(layout.widow_control.value)
        formatting.page_break_before = _optional_bool(layout.page_break_before.value)
        formatting.tab_stops.clear_all()
        for tab in role.tab_stops:
            formatting.tab_stops.add_tab_stop(
                Twips(tab.position_twips),
                _tab_alignment(tab),
                _tab_leader(tab.leader),
            )
        if role.bullet is not None:
            if role.bullet.left_indent_twips is not None:
                formatting.left_indent = Twips(role.bullet.left_indent_twips)
            if role.bullet.hanging_indent_twips is not None:
                formatting.first_line_indent = Twips(-role.bullet.hanging_indent_twips)
            if role.bullet.space_before_twips is not None:
                formatting.space_before = Twips(role.bullet.space_before_twips)
            if role.bullet.space_after_twips is not None:
                formatting.space_after = Twips(role.bullet.space_after_twips)
        self._apply_borders(paragraph, role.borders)

    def _apply_run(self, run: Run, role: SemanticRoleLayout, index: int) -> None:
        typography = _typography_for_run(role, index)
        family = typography.font_family.value or _FALLBACKS.font_family
        size = typography.font_size_half_points.value
        run.font.name = str(family)
        run._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:ascii"), str(family))
        run._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:hAnsi"), str(family))
        run.font.size = Pt(float(size) / 2 if isinstance(size, (int, float)) else _FALLBACKS.font_size_points)
        run.bold = _optional_bool(typography.bold.value)
        run.italic = _optional_bool(typography.italic.value)
        underline = typography.underline.value
        run.underline = False if underline in {None, False, "none"} else True
        color = typography.color.value
        color_text = _valid_rgb(color) or _FALLBACKS.font_color
        run.font.color.rgb = RGBColor.from_string(color_text)
        spacing = typography.character_spacing_twips.value
        if isinstance(spacing, int):
            spacing_element = OxmlElement("w:spacing")
            spacing_element.set(qn("w:val"), str(spacing))
            run._element.get_or_add_rPr().append(spacing_element)
        pattern = role.run_patterns[0] if role.run_patterns else None
        if pattern and index in pattern.bold_run_positions:
            run.bold = True
        if pattern and index in pattern.italic_run_positions:
            run.italic = True

    def _apply_borders(self, paragraph: Paragraph, borders: list[Border]) -> None:
        if not borders:
            return
        properties = paragraph._p.get_or_add_pPr()
        existing = properties.find(qn("w:pBdr"))
        if existing is not None:
            properties.remove(existing)
        container = OxmlElement("w:pBdr")
        for border in borders:
            element = OxmlElement(f"w:{border.position}")
            style = "single" if border.style == "solid" else border.style
            element.set(qn("w:val"), style)
            if border.thickness_eighth_points is not None:
                element.set(qn("w:sz"), str(border.thickness_eighth_points))
            if border.spacing_points is not None:
                element.set(qn("w:space"), str(border.spacing_points))
            element.set(qn("w:color"), _valid_rgb(border.color) or _FALLBACKS.font_color)
            container.append(element)
        properties.append(container)

    def _add_hyperlink(
        self,
        paragraph: Paragraph,
        display: str,
        target: str,
        role: SemanticRoleLayout,
    ) -> None:
        relationship_id = paragraph.part.relate_to(
            target,
            RELATIONSHIP_TYPE.HYPERLINK,
            is_external=True,
        )
        hyperlink = OxmlElement("w:hyperlink")
        hyperlink.set(qn("r:id"), relationship_id)
        run_element = OxmlElement("w:r")
        text_element = OxmlElement("w:t")
        text_element.text = display
        run_element.append(text_element)
        hyperlink.append(run_element)
        paragraph._p.append(hyperlink)
        run = Run(run_element, paragraph)
        hyperlink_typography = (
            role.hyperlinks.display_typography
            if role.hyperlinks and role.hyperlinks.display_typography
            else role.primary_typography
        )
        hyperlink_role = role.model_copy(
            update={"primary_typography": hyperlink_typography, "run_patterns": []}
        )
        self._apply_run(run, hyperlink_role, 0)
        if role.hyperlinks:
            run.underline = role.hyperlinks.underline_behavior not in {None, "none", "False"}
            color = _valid_rgb(role.hyperlinks.color_behavior)
            if color:
                run.font.color.rgb = RGBColor.from_string(color)


def _ordered_records(
    records: list[ResumeItem],
    bullets: dict[str, list[StructuredBullet]],
    titles: dict[str, str],
    kind: EntityKind,
) -> list[ResumeItem]:
    by_id = {item.id: item for item in records}
    ordered = [by_id[entity_id] for entity_id in bullets if entity_id in by_id]
    for entity_id in bullets:
        if entity_id not in by_id:
            ordered.append(
                ResumeItem(
                    id=entity_id,
                    title=titles.get(entity_id, entity_id),
                    kind=kind,
                )
            )
    return ordered


def _date_range(start: str | None, end: str | None) -> str | None:
    return " - ".join(part for part in (start, end) if part) or None


def _hyperlink_target(value: str) -> str | None:
    stripped = value.strip()
    if "@" in stripped and not re.search(r"\s", stripped):
        return stripped if stripped.casefold().startswith("mailto:") else f"mailto:{stripped}"
    if stripped.casefold().startswith(("http://", "https://")):
        return stripped
    if re.match(r"^(www\.|[a-z0-9-]+\.[a-z]{2,}/)", stripped, re.IGNORECASE):
        return f"https://{stripped}"
    return None


def _paragraph_alignment(value: object) -> WD_ALIGN_PARAGRAPH | None:
    return {
        "left": WD_ALIGN_PARAGRAPH.LEFT,
        "center": WD_ALIGN_PARAGRAPH.CENTER,
        "right": WD_ALIGN_PARAGRAPH.RIGHT,
        "both": WD_ALIGN_PARAGRAPH.JUSTIFY,
        "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
    }.get(str(value)) if value is not None else None


def _line_spacing_rule(value: object) -> WD_LINE_SPACING | None:
    return {
        "exact": WD_LINE_SPACING.EXACTLY,
        "atLeast": WD_LINE_SPACING.AT_LEAST,
        "auto": WD_LINE_SPACING.SINGLE,
    }.get(str(value)) if value is not None else None


def _tab_alignment(tab: TabStop) -> WD_TAB_ALIGNMENT:
    return {
        "right": WD_TAB_ALIGNMENT.RIGHT,
        "center": WD_TAB_ALIGNMENT.CENTER,
        "decimal": WD_TAB_ALIGNMENT.DECIMAL,
        "bar": WD_TAB_ALIGNMENT.BAR,
    }.get(tab.alignment, WD_TAB_ALIGNMENT.LEFT)


def _tab_leader(value: str | None) -> WD_TAB_LEADER:
    return {
        "dot": WD_TAB_LEADER.DOTS,
        "hyphen": WD_TAB_LEADER.DASHES,
        "underscore": WD_TAB_LEADER.LINES,
        "heavy": WD_TAB_LEADER.HEAVY,
        "middleDot": WD_TAB_LEADER.MIDDLE_DOT,
    }.get(value or "", WD_TAB_LEADER.SPACES)


def _typography_for_run(role: SemanticRoleLayout, index: int) -> Typography:
    if role.run_patterns:
        variants = role.run_patterns[0].typography_variants
        if index < len(variants):
            return variants[index]
    return role.primary_typography


def _bullet_marker(role: SemanticRoleLayout) -> str:
    marker = role.bullet.representation if role.bullet else None
    if marker and "%" not in marker and len(marker) <= 3:
        return marker
    return _FALLBACKS.bullet_marker


def _set_twips(target: object, attribute: str, value: object) -> None:
    if isinstance(value, int):
        setattr(target, attribute, Twips(value))


def _optional_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _valid_rgb(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.removeprefix("#").upper()
    return normalized if re.fullmatch(r"[0-9A-F]{6}", normalized) else None
