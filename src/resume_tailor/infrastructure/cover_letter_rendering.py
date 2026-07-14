from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

from resume_tailor.domain.cover_letter import CoverLetter, CoverLetterLayoutProfile
from resume_tailor.infrastructure.rendering import (
    DocxPageCountProvider,
    ExactDocxPageCountProvider,
    PageCountMeasurement,
    PageCountVerificationError,
)


@dataclass(frozen=True)
class CoverLetterRenderResult:
    docx_path: Path
    measurement: PageCountMeasurement

    @property
    def page_count(self) -> int:
        return self.measurement.page_count


class CoverLetterRenderer:
    """Fixed, independent one-page DOCX renderer for cover letters."""

    def __init__(
        self,
        layout_profile: CoverLetterLayoutProfile | None = None,
        page_count_provider: DocxPageCountProvider | None = None,
    ) -> None:
        self._profile = layout_profile or CoverLetterLayoutProfile()
        self._page_count_provider = page_count_provider or ExactDocxPageCountProvider()

    def render_candidate(self, letter: CoverLetter, output_directory: Path) -> CoverLetterRenderResult:
        output_directory = Path(output_directory).expanduser().resolve()
        output_directory.mkdir(parents=True, exist_ok=True)
        output_path = (output_directory / "cover-letter.docx").resolve()
        self._render_docx(letter, output_path)
        if not output_path.is_file() or output_path.stat().st_size <= 0:
            raise PageCountVerificationError("Cover-letter renderer did not produce a usable DOCX.")
        measurement = self._page_count_provider.measure(output_path)
        return CoverLetterRenderResult(output_path, measurement)

    def render(self, letter: CoverLetter, output_directory: Path) -> CoverLetterRenderResult:
        result = self.render_candidate(letter, output_directory)
        if not result.measurement.exact or result.measurement.page_count != 1:
            raise PageCountVerificationError(
                f"Cover letter must be exactly one page; measured {result.measurement.page_count}."
            )
        return result

    def _render_docx(self, letter: CoverLetter, output_path: Path) -> None:
        p = self._profile
        document = Document()
        section = document.sections[0]
        section.page_width = Inches(p.page_width_inches)
        section.page_height = Inches(p.page_height_inches)
        section.top_margin = Inches(p.top_margin_inches)
        section.bottom_margin = Inches(p.bottom_margin_inches)
        section.left_margin = Inches(p.left_margin_inches)
        section.right_margin = Inches(p.right_margin_inches)

        normal = document.styles["Normal"]
        normal.font.name = p.body_font
        normal.font.size = Pt(p.body_size_pt)
        normal._element.rPr.rFonts.set(qn("w:eastAsia"), p.body_font)

        name = document.add_paragraph()
        name.alignment = WD_ALIGN_PARAGRAPH.CENTER
        name.paragraph_format.space_after = Pt(p.header_spacing_pt)
        self._add_run(name, letter.candidate_name, bold=True, size=p.header_name_size_pt, font_family=p.body_font)

        contact_lines = self._contact_lines(letter)
        for line in contact_lines:
            contact = document.add_paragraph()
            contact.alignment = WD_ALIGN_PARAGRAPH.CENTER
            contact.paragraph_format.space_after = Pt(0)
            for index, part in enumerate(line):
                if index:
                    self._add_run(contact, p.contact_separator, size=p.body_size_pt, font_family=p.body_font)
                if isinstance(part, tuple):
                    self._add_hyperlink(contact, part[0], part[1], p.body_size_pt, p.body_font)
                else:
                    self._add_run(contact, part, size=p.body_size_pt, font_family=p.body_font)

        rule = document.add_paragraph()
        rule.paragraph_format.space_after = Pt(p.rule_spacing_pt)
        self._add_bottom_border(rule)

        date_paragraph = self._body_paragraph(document, p)
        date_paragraph.add_run(letter.date_text)
        recipient_values = [letter.recipient.name, letter.recipient.title, letter.recipient.company, *letter.recipient.address_lines]
        if any(value for value in recipient_values):
            for value in recipient_values:
                if value:
                    paragraph = self._body_paragraph(document, p)
                    paragraph.add_run(value)
        salutation = self._body_paragraph(document, p)
        salutation.add_run(letter.salutation)
        for paragraph_data in letter.paragraphs:
            paragraph = self._body_paragraph(document, p)
            paragraph.add_run(paragraph_data.text)
        closing = self._body_paragraph(document, p)
        closing.add_run(letter.closing)
        signoff = self._body_paragraph(document, p)
        signoff.paragraph_format.space_after = Pt(p.signoff_spacing_pt)
        signoff.add_run(letter.signoff)
        name_paragraph = self._body_paragraph(document, p)
        self._add_run(name_paragraph, letter.signoff_name, bold=True, size=p.body_size_pt, font_family=p.body_font)
        document.save(output_path)

    @staticmethod
    def _body_paragraph(document: Document, profile: CoverLetterLayoutProfile):
        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
        paragraph.paragraph_format.space_after = Pt(profile.paragraph_spacing_pt)
        paragraph.paragraph_format.line_spacing = profile.line_spacing
        paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
        return paragraph

    def _contact_lines(self, letter: CoverLetter) -> list[list[str | tuple[str, str]]]:
        values: list[str | tuple[str, str]] = []
        location = (letter.contact.location or "").strip()
        if location and location.casefold() != "canada":
            values.append(location)
        for value in (letter.contact.phone, letter.contact.email):
            if value:
                values.append(value)
        for link in letter.contact.links:
            label = self._link_label(link)
            values.append((label, link))
        if not values:
            return [[]]
        rough_length = sum(len(value[0] if isinstance(value, tuple) else value) for value in values) + 3 * (len(values) - 1)
        if rough_length <= 105:
            return [values]
        midpoint = max(1, len(values) // 2)
        return [values[:midpoint], values[midpoint:]]

    @staticmethod
    def _link_label(link: str) -> str:
        host = urlparse(link).netloc.casefold()
        if "linkedin" in host:
            return "LinkedIn"
        if "github" in host:
            return "GitHub"
        return "Portfolio"

    @staticmethod
    def _add_run(paragraph, text: str, *, bold: bool = False, size: float = 10.5, font_family: str = "Times New Roman"):
        run = paragraph.add_run(text)
        run.font.name = font_family
        run._element.rPr.rFonts.set(qn("w:eastAsia"), font_family)
        run.font.size = Pt(size)
        run.bold = bold
        return run

    @staticmethod
    def _add_hyperlink(paragraph, label: str, url: str, size: float, font_family: str):
        part = paragraph.part
        relationship = part.relate_to(url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", is_external=True)
        hyperlink = OxmlElement("w:hyperlink")
        hyperlink.set(qn("r:id"), relationship)
        run = OxmlElement("w:r")
        properties = OxmlElement("w:rPr")
        font = OxmlElement("w:rFonts")
        font.set(qn("w:ascii"), font_family)
        font.set(qn("w:hAnsi"), font_family)
        properties.append(font)
        size_element = OxmlElement("w:sz")
        size_element.set(qn("w:val"), str(round(size * 2)))
        properties.append(size_element)
        color = OxmlElement("w:color")
        color.set(qn("w:val"), "0563C1")
        properties.append(color)
        underline = OxmlElement("w:u")
        underline.set(qn("w:val"), "single")
        properties.append(underline)
        run.append(properties)
        text = OxmlElement("w:t")
        text.text = label
        run.append(text)
        hyperlink.append(run)
        paragraph._p.append(hyperlink)

    @staticmethod
    def _add_bottom_border(paragraph) -> None:
        ppr = paragraph._p.get_or_add_pPr()
        borders = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "4")
        bottom.set(qn("w:space"), "1")
        bottom.set(qn("w:color"), "808080")
        borders.append(bottom)
        ppr.append(borders)
