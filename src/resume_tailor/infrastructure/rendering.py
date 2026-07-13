from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory
from typing import Protocol
from uuid import uuid4

from docx import Document
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from resume_tailor.domain.layout import LayoutProfile
from resume_tailor.domain.models import StructuredBullet, StructuredResume
from resume_tailor.infrastructure.adaptive_docx import render_structured_resume
from resume_tailor.infrastructure.reference_docx import analyze_reference_docx


class PageOverflowError(ValueError):
    pass


class PageCountVerificationError(PageOverflowError):
    """Raised when exact DOCX page-count verification is unavailable or fails."""


@dataclass(frozen=True)
class PageCountMeasurement:
    page_count: int
    provider: str
    confidence: str
    exact: bool


class DocxPageCountProvider(Protocol):
    def measure(self, docx_path: Path) -> PageCountMeasurement: ...


class LibreOfficeDocxPageCountProvider:
    """Measure DOCX pages through LibreOffice and its converted PDF page tree."""

    def __init__(self, executable: str | None = None) -> None:
        self._executable = executable or shutil.which("soffice") or shutil.which("libreoffice")

    def measure(self, docx_path: Path) -> PageCountMeasurement:
        docx_path = _validated_docx_path(docx_path, "LibreOffice")
        if self._executable is None:
            raise PageCountVerificationError(
                "Exact DOCX page-count verification requires LibreOffice or Microsoft Word; "
                "no supported provider is available."
            )
        with TemporaryDirectory(prefix="resume-page-count-") as directory:
            result = subprocess.run(
                [
                    self._executable,
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    directory,
                    str(docx_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                raise PageCountVerificationError(
                    f"LibreOffice could not render the DOCX for page-count verification: "
                    f"{result.stderr.strip() or result.stdout.strip()} "
                    f"({_docx_diagnostics(docx_path, 'LibreOffice')})"
                )
            pdf_path = Path(directory) / f"{docx_path.stem}.pdf"
            if not pdf_path.is_file():
                raise PageCountVerificationError(
                    "LibreOffice reported success but did not produce a PDF for page counting "
                    f"({_docx_diagnostics(docx_path, 'LibreOffice')})."
                )
            page_count = _count_pdf_pages(pdf_path)
            return PageCountMeasurement(
                page_count=page_count,
                provider="LibreOffice DOCX->PDF page tree",
                confidence="exact",
                exact=True,
            )


class MicrosoftWordDocxPageCountProvider:
    """Measure DOCX pages with Word through its native Windows COM automation."""

    def measure(self, docx_path: Path) -> PageCountMeasurement:
        docx_path = _validated_docx_path(docx_path, "Microsoft Word")
        powershell = shutil.which("powershell.exe") or shutil.which("powershell")
        if powershell is None:
            raise PageCountVerificationError(
                "Microsoft Word page-count verification is unavailable because PowerShell is not available."
            )
        script = r'''
$Path = $env:RESUME_DOCX_PATH
$beforeWordIds = @(Get-Process WINWORD -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
$word = $null
$document = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $document = $word.Documents.Open($Path, $false, $true, $false)
    [int]$document.ComputeStatistics(2)
}
finally {
    if ($null -ne $document) { $document.Close($false) }
    if ($null -ne $word) { $word.Quit() }
    if ($null -eq $word) {
        $afterWordIds = @(Get-Process WINWORD -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
        foreach ($id in $afterWordIds) {
            if ($beforeWordIds -notcontains $id) {
                Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
            }
        }
    }
}
'''
        environment = os.environ.copy()
        environment["RESUME_DOCX_PATH"] = str(docx_path)
        try:
            result = subprocess.run(
                [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
                env=environment,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise PageCountVerificationError(
                f"Microsoft Word page-count verification could not run: {error}"
            ) from error
        if result.returncode != 0:
            raise PageCountVerificationError(
                "Microsoft Word could not render the DOCX for page-count verification: "
                f"{result.stderr.strip() or result.stdout.strip()} "
                f"({_docx_diagnostics(docx_path, 'Microsoft Word')})"
            )
        try:
            page_count = int(result.stdout.strip().splitlines()[-1])
        except (IndexError, ValueError) as error:
            raise PageCountVerificationError(
                "Microsoft Word returned no usable page count for the DOCX "
                f"({_docx_diagnostics(docx_path, 'Microsoft Word')})."
            ) from error
        return PageCountMeasurement(
            page_count=page_count,
            provider="Microsoft Word ComputeStatistics",
            confidence="exact",
            exact=True,
        )


class ExactDocxPageCountProvider:
    """Prefer LibreOffice and fall back to Microsoft Word if available."""

    def __init__(self) -> None:
        self._providers: tuple[DocxPageCountProvider, ...] = (
            LibreOfficeDocxPageCountProvider(),
            MicrosoftWordDocxPageCountProvider(),
        )

    def measure(self, docx_path: Path) -> PageCountMeasurement:
        failures: list[str] = []
        for provider in self._providers:
            try:
                return provider.measure(docx_path)
            except PageCountVerificationError as error:
                failures.append(str(error))
        raise PageCountVerificationError("Exact DOCX page-count verification failed: " + " ".join(failures))


def _validated_docx_path(path: Path, provider: str) -> Path:
    resolved = Path(path).expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    if not resolved.is_file() or resolved.stat().st_size <= 0:
        raise PageCountVerificationError(
            f"{provider} cannot measure the DOCX because the candidate file is unavailable "
            f"({_docx_diagnostics(resolved, provider)})."
        )
    return resolved


def _docx_diagnostics(path: Path, provider: str) -> str:
    exists = path.is_file()
    size = path.stat().st_size if exists else 0
    return f"provider={provider}; path={path}; exists={exists}; size={size} bytes"


@dataclass(frozen=True)
class ManagedRenderResult:
    docx_path: Path
    pdf_path: Path
    page_count: int
    measurement_provider: str
    measurement_confidence: str
    exact_page_count_verified: bool
    overflow_reduction_count: int


class ManagedResumeRenderer:
    _page_width, _page_height = letter
    _margin = 48
    _line_height = 12
    _body_font = "Helvetica"
    _body_size = 9
    _max_overflow_reductions = 32

    def __init__(
        self,
        layout_profile: LayoutProfile | None = None,
        reference_path: Path | None = None,
        page_count_provider: DocxPageCountProvider | None = None,
    ) -> None:
        resolved_reference = reference_path or (
            Path(__file__).resolve().parents[3] / "manual-test" / "reference-resume.docx"
        )
        self._layout_profile = (
            layout_profile
            if layout_profile is not None
            else analyze_reference_docx(resolved_reference)
        )
        self._page_count_provider = page_count_provider or ExactDocxPageCountProvider()
        self._last_measurement: PageCountMeasurement | None = None
        self._initial_measurement: PageCountMeasurement | None = None
        self._last_overflow_reduction_count = 0

    @property
    def layout_profile(self) -> LayoutProfile:
        return self._layout_profile

    @property
    def last_measurement(self) -> PageCountMeasurement | None:
        return self._last_measurement

    @property
    def initial_measurement(self) -> PageCountMeasurement | None:
        return self._initial_measurement

    @property
    def last_overflow_reduction_count(self) -> int:
        return self._last_overflow_reduction_count

    @property
    def underfill_expansion_enabled(self) -> bool:
        return False

    def render(self, resume: StructuredResume, output_directory: Path) -> ManagedRenderResult:
        output_directory = Path(output_directory).expanduser().resolve()
        output_directory.mkdir(parents=True, exist_ok=True)
        stem = f"resume-{uuid4().hex}"
        docx_path = output_directory / f"{stem}.docx"
        pdf_path = output_directory / f"{stem}.pdf"
        try:
            candidate = self._render_verified_docx(resume, docx_path)
            self._render_pdf(candidate, pdf_path)
        except Exception:
            docx_path.unlink(missing_ok=True)
            pdf_path.unlink(missing_ok=True)
            raise
        measurement = self._last_measurement
        if measurement is None:
            raise PageCountVerificationError("The final DOCX has no page-count measurement.")
        return ManagedRenderResult(
            docx_path=docx_path,
            pdf_path=pdf_path,
            page_count=measurement.page_count,
            measurement_provider=measurement.provider,
            measurement_confidence=measurement.confidence,
            exact_page_count_verified=measurement.exact,
            overflow_reduction_count=self._last_overflow_reduction_count,
        )

    def _render_docx(self, resume: StructuredResume, path: Path) -> None:
        self._render_verified_docx(resume, path)

    def render_docx(self, resume: StructuredResume, output_path: Path) -> Path:
        """Render DOCX only; used by delivery surfaces that do not request PDF."""
        self._render_verified_docx(resume, output_path)
        return output_path

    def _render_verified_docx(self, resume: StructuredResume, path: Path) -> StructuredResume:
        path = Path(path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        candidate = resume
        self._last_measurement = None
        self._initial_measurement = None
        self._last_overflow_reduction_count = 0
        for _ in range(self._max_overflow_reductions + 1):
            render_structured_resume(candidate, self._layout_profile, path)
            if not path.is_file() or path.stat().st_size <= 0:
                raise PageCountVerificationError(
                    "DOCX rendering completed without a non-empty candidate file "
                    f"({_docx_diagnostics(path, 'page-count verification')})."
                )
            try:
                measurement = self._page_count_provider.measure(path)
            except Exception:
                path.unlink(missing_ok=True)
                raise
            self._last_measurement = measurement
            if self._initial_measurement is None:
                self._initial_measurement = measurement
            if not measurement.exact:
                path.unlink(missing_ok=True)
                raise PageCountVerificationError(
                    f"Page-count provider {measurement.provider!r} is not exact; "
                    "the one-page invariant cannot be verified."
                )
            if measurement.page_count == 1:
                return candidate
            if measurement.page_count < 1:
                path.unlink(missing_ok=True)
                raise PageCountVerificationError("The DOCX page-count provider returned an invalid count.")
            reduced = _reduce_optional_content(candidate)
            if reduced is None:
                path.unlink(missing_ok=True)
                raise PageOverflowError(
                    "The rendered DOCX exceeds one page and has no optional content left to remove."
                )
            candidate = reduced
            self._last_overflow_reduction_count += 1
        path.unlink(missing_ok=True)
        raise PageOverflowError("The rendered DOCX did not reach one page within the bounded reduction loop.")

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
        width = self._page_width - (2 * self._margin)
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


def _count_pdf_pages(pdf_path: Path) -> int:
    try:
        from pypdf import PdfReader

        return len(PdfReader(str(pdf_path)).pages)
    except ImportError:
        pass
    try:
        from PyPDF2 import PdfReader

        return len(PdfReader(str(pdf_path)).pages)
    except ImportError:
        pass
    data = pdf_path.read_bytes()
    pages = re.findall(rb"/Type\s*/Page(?!s)\b", data)
    if not pages:
        raise PageCountVerificationError("Unable to count pages in the rendered PDF page tree.")
    return len(pages)


def _reduce_optional_content(resume: StructuredResume) -> StructuredResume | None:
    """Remove one deterministic optional claim without changing layout geometry."""
    for field_name in ("project_bullets", "experience_bullets"):
        bullets = dict(getattr(resume, field_name))
        for entity_id in reversed(list(bullets)):
            if bullets[entity_id]:
                updated = list(bullets[entity_id][:-1])
                if updated:
                    bullets[entity_id] = updated
                else:
                    del bullets[entity_id]
                return resume.model_copy(update={field_name: bullets})

    if resume.technical_skills:
        categories = list(resume.technical_skills)
        for index in range(len(categories) - 1, -1, -1):
            category = categories[index]
            skills = list(category.skills or [])
            values = list(category.values or [])
            if skills:
                skills.pop()
                values = [skill.value for skill in skills]
            elif values:
                values.pop()
            else:
                continue
            categories[index] = category.model_copy(update={"skills": skills, "values": values})
            return resume.model_copy(update={"technical_skills": categories})

    if resume.selected_skills:
        return resume.model_copy(update={"selected_skills": resume.selected_skills[:-1]})
    if resume.selected_coursework:
        return resume.model_copy(update={"selected_coursework": resume.selected_coursework[:-1]})

    for index in range(len(resume.education) - 1, -1, -1):
        record = resume.education[index]
        if record.relevant_coursework:
            education = list(resume.education)
            education[index] = record.model_copy(
                update={"relevant_coursework": record.relevant_coursework[:-1]}
            )
            return resume.model_copy(update={"education": education})
        if record.awards:
            education = list(resume.education)
            education[index] = record.model_copy(update={"awards": record.awards[:-1]})
            return resume.model_copy(update={"education": education})
        if record.gpa:
            education = list(resume.education)
            education[index] = record.model_copy(update={"gpa": None})
            return resume.model_copy(update={"education": education})
    return None
