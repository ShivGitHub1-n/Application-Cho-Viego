from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from docx import Document
from docx.shared import Inches
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from resume_tailor.domain.models import StructuredBullet, StructuredResume


class PageOverflowError(ValueError):
    pass


@dataclass(frozen=True)
class ManagedRenderResult:
    docx_path: Path
    pdf_path: Path
    page_count: int


class ManagedResumeRenderer:
    _page_width, _page_height = letter
    _margin = 48
    _line_height = 12
    _body_font = "Helvetica"
    _body_size = 9

    def render(self, resume: StructuredResume, output_directory: Path) -> ManagedRenderResult:
        output_directory.mkdir(parents=True, exist_ok=True)
        stem = f"resume-{uuid4().hex}"
        docx_path = output_directory / f"{stem}.docx"
        pdf_path = output_directory / f"{stem}.pdf"
        try:
            self._render_pdf(resume, pdf_path)
            self._render_docx(resume, docx_path)
        except Exception:
            docx_path.unlink(missing_ok=True)
            pdf_path.unlink(missing_ok=True)
            raise
        return ManagedRenderResult(docx_path=docx_path, pdf_path=pdf_path, page_count=1)

    def _render_docx(self, resume: StructuredResume, path: Path) -> None:
        document = Document()
        section = document.sections[0]
        section.top_margin = Inches(0.55)
        section.bottom_margin = Inches(0.55)
        section.left_margin = Inches(0.6)
        section.right_margin = Inches(0.6)
        document.add_heading(resume.display_name, level=0)
        if resume.contact_line:
            document.add_paragraph(resume.contact_line)
        self._add_education(document, resume)
        self._add_docx_section(document, "Experience", resume.experience_bullets, resume.entity_titles)
        self._add_docx_section(document, "Projects", resume.project_bullets, resume.entity_titles)
        if resume.selected_skills:
            self._add_docx_text(document, "Skills", ", ".join(resume.selected_skills))
        if resume.selected_coursework:
            self._add_docx_text(document, "Coursework", ", ".join(resume.selected_coursework))
        document.save(path)

    def _add_docx_section(
        self,
        document: Document,
        heading: str,
        bullets: dict[str, list[StructuredBullet]],
        titles: dict[str, str],
    ) -> None:
        if not bullets:
            return
        document.add_heading(heading, level=1)
        for entity_id, entity_bullets in bullets.items():
            document.add_paragraph(titles.get(entity_id, entity_id), style="Heading 2")
            for bullet in entity_bullets:
                document.add_paragraph(bullet.text, style="List Bullet")

    def _add_docx_text(self, document: Document, heading: str, text: str) -> None:
        paragraph = document.add_paragraph()
        paragraph.add_run(f"{heading}: ").bold = True
        paragraph.add_run(text)

    def _add_education(self, document: Document, resume: StructuredResume) -> None:
        if not resume.education:
            return
        document.add_heading("Education", level=1)
        for record in resume.education:
            details = " — ".join(part for part in [record.school, record.program, record.graduation_date] if part)
            if record.gpa:
                details = f"{details}; GPA {record.gpa}"
            document.add_paragraph(details)

    def _render_pdf(self, resume: StructuredResume, path: Path) -> None:
        canvas = Canvas(str(path), pagesize=letter)
        y = self._page_height - self._margin
        y = self._draw_line(canvas, resume.display_name, y, "Helvetica-Bold", 16)
        if resume.contact_line:
            y = self._draw_line(canvas, resume.contact_line, y, "Helvetica", 9)
        y -= 6
        if resume.education:
            y = self._draw_line(canvas, "Education", y, "Helvetica-Bold", 10)
            for record in resume.education:
                details = " — ".join(part for part in [record.school, record.program, record.graduation_date] if part)
                if record.gpa:
                    details = f"{details}; GPA {record.gpa}"
                y = self._draw_wrapped_text(canvas, details, y)
            y -= 3
        y = self._draw_bullet_section(canvas, "Experience", resume.experience_bullets, resume.entity_titles, y)
        y = self._draw_bullet_section(canvas, "Projects", resume.project_bullets, resume.entity_titles, y)
        if resume.selected_skills:
            y = self._draw_line(canvas, "Skills", y, "Helvetica-Bold", 10)
            y = self._draw_wrapped_text(canvas, ", ".join(resume.selected_skills), y)
        if resume.selected_coursework:
            y = self._draw_line(canvas, "Coursework", y, "Helvetica-Bold", 10)
            y = self._draw_wrapped_text(canvas, ", ".join(resume.selected_coursework), y)
        if y < self._margin:
            raise PageOverflowError("The managed template overflowed one page; revise the content plan.")
        canvas.save()

    def _draw_bullet_section(
        self,
        canvas: Canvas,
        heading: str,
        bullets: dict[str, list[StructuredBullet]],
        titles: dict[str, str],
        y: float,
    ) -> float:
        if not bullets:
            return y
        y = self._draw_line(canvas, heading, y, "Helvetica-Bold", 10)
        for entity_id, entity_bullets in bullets.items():
            y = self._draw_line(canvas, titles.get(entity_id, entity_id), y, "Helvetica-Bold", 9)
            for bullet in entity_bullets:
                y = self._draw_wrapped_text(canvas, f"• {bullet.text}", y)
        return y - 3

    def _draw_line(self, canvas: Canvas, text: str, y: float, font: str, size: int) -> float:
        self._ensure_space(y)
        canvas.setFont(font, size)
        canvas.drawString(self._margin, y, text)
        return y - self._line_height

    def _draw_wrapped_text(self, canvas: Canvas, text: str, y: float) -> float:
        canvas.setFont(self._body_font, self._body_size)
        width = self._page_width - (self._margin * 2)
        line = ""
        lines: list[str] = []
        for word in text.split():
            trial = f"{line} {word}".strip()
            if stringWidth(trial, self._body_font, self._body_size) <= width:
                line = trial
            else:
                lines.append(line)
                line = word
        if line:
            lines.append(line)
        for line in lines:
            self._ensure_space(y)
            canvas.drawString(self._margin, y, line)
            y -= self._line_height
        return y

    def _ensure_space(self, y: float) -> None:
        if y < self._margin:
            raise PageOverflowError("The managed template overflowed one page; revise the content plan.")
