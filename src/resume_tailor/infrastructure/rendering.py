from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol
from uuid import uuid4

from docx import Document
from docx.text.paragraph import Paragraph
from reportlab.lib.pagesizes import letter  # type: ignore[import-untyped]
from reportlab.pdfbase.pdfmetrics import stringWidth  # type: ignore[import-untyped]
from reportlab.pdfgen.canvas import Canvas  # type: ignore[import-untyped]

from resume_tailor.domain.layout import (
    LayoutProfile,
    PageUtilizationDiagnostic,
    PageUtilizationStatus,
)
from resume_tailor.domain.models import (
    EducationRecord,
    EntityKind,
    ResumeItem,
    StructuredBullet,
    StructuredResume,
)
from resume_tailor.domain.resume_composition import TEMPLATE_V1_UTILIZATION_TARGET_FLOOR
from resume_tailor.domain.resume_metadata import compose_date_range, education_end_date
from resume_tailor.infrastructure.adaptive_docx import render_structured_resume
from resume_tailor.infrastructure.static_template_docx import render_template_v1_resume
from resume_tailor.infrastructure.template_v1 import load_template_v1_layout_profile


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

    def __init__(
        self,
        executable: str | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("LibreOffice pagination timeout must be positive")
        self._executable = executable or shutil.which("soffice") or shutil.which("libreoffice")
        self._timeout_seconds = timeout_seconds

    def measure(self, docx_path: Path) -> PageCountMeasurement:
        return self.measure_many([docx_path])[0]

    def measure_many(self, docx_paths: list[Path]) -> list[PageCountMeasurement]:
        if not docx_paths:
            return []
        validated_paths = [
            _validated_docx_path(path, "LibreOffice") for path in docx_paths
        ]
        if self._executable is None:
            raise PageCountVerificationError(
                "Exact DOCX page-count verification requires LibreOffice or Microsoft Word; "
                "no supported provider is available."
            )
        with TemporaryDirectory(prefix="resume-page-count-") as directory:
            try:
                result = subprocess.run(
                    [
                        self._executable,
                        "--headless",
                        "--convert-to",
                        "pdf",
                        "--outdir",
                        directory,
                        *[str(path) for path in validated_paths],
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=self._timeout_seconds,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                raise PageCountVerificationError(
                    "LibreOffice page-count verification could not complete within "
                    f"{self._timeout_seconds:g} seconds: {error}"
                ) from error
            if result.returncode != 0:
                raise PageCountVerificationError(
                    f"LibreOffice could not render the DOCX for page-count verification: "
                    f"{result.stderr.strip() or result.stdout.strip()} "
                    f"({_docx_diagnostics(validated_paths[0], 'LibreOffice')})"
                )
            measurements: list[PageCountMeasurement] = []
            for path in validated_paths:
                pdf_path = Path(directory) / f"{path.stem}.pdf"
                if not pdf_path.is_file():
                    raise PageCountVerificationError(
                        "LibreOffice reported success but did not produce a PDF for page "
                        f"counting ({_docx_diagnostics(path, 'LibreOffice')})."
                    )
                measurements.append(
                    PageCountMeasurement(
                        page_count=_count_pdf_pages(pdf_path),
                        provider="LibreOffice DOCX->PDF page tree",
                        confidence="exact",
                        exact=True,
                    )
                )
            return measurements


class MicrosoftWordDocxPageCountProvider:
    """Measure DOCX pages with Word through its native Windows COM automation."""

    def __init__(self, timeout_seconds: float = 15.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("Microsoft Word pagination timeout must be positive")
        self._timeout_seconds = timeout_seconds

    def measure(self, docx_path: Path) -> PageCountMeasurement:
        return self.measure_many([docx_path])[0]

    def measure_many(self, docx_paths: list[Path]) -> list[PageCountMeasurement]:
        if not docx_paths:
            return []
        validated_paths = [
            _validated_docx_path(path, "Microsoft Word") for path in docx_paths
        ]
        powershell = shutil.which("powershell.exe") or shutil.which("powershell")
        if powershell is None:
            raise PageCountVerificationError(
                "Microsoft Word page-count verification is unavailable because "
                "PowerShell is not available."
            )
        script = r"""
$Paths = @(Get-Content -LiteralPath $env:RESUME_DOCX_PATHS_FILE)
$OwnedProcessPath = $env:RESUME_WORD_OWNED_PROCESS_PATH
$word = $null
$document = $null
$counts = @()
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class ResumeWordNative {
    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
}
'@
    [uint32]$createdProcessId = 0
    [void][ResumeWordNative]::GetWindowThreadProcessId(
        [IntPtr]$word.Hwnd,
        [ref]$createdProcessId
    )
    if ($createdProcessId -gt 0) {
        $createdProcess = Get-Process -Id $createdProcessId -ErrorAction Stop
        "$createdProcessId|$($createdProcess.StartTime.ToUniversalTime().Ticks)" |
            Set-Content -LiteralPath $OwnedProcessPath -Encoding ASCII
    }
    foreach ($path in $Paths) {
        try {
            $document = $word.Documents.Open($path, $false, $true, $false)
            $counts += [int]$document.ComputeStatistics(2)
        }
        finally {
            if ($null -ne $document) {
                $document.Close($false)
                $document = $null
            }
        }
    }
    $counts -join ','
}
finally {
    if ($null -ne $document) { $document.Close($false) }
    if ($null -ne $word) { $word.Quit() }
    Remove-Item -LiteralPath $OwnedProcessPath -Force -ErrorAction SilentlyContinue
}
"""
        environment = os.environ.copy()
        with TemporaryDirectory(prefix="resume-word-pagination-") as directory:
            paths_file = Path(directory) / "docx-paths.txt"
            paths_file.write_text(
                "\n".join(str(path) for path in validated_paths),
                encoding="utf-8",
            )
            owned_process_path = Path(directory) / "owned-word-process.txt"
            environment["RESUME_DOCX_PATHS_FILE"] = str(paths_file)
            environment["RESUME_WORD_OWNED_PROCESS_PATH"] = str(owned_process_path)
            try:
                result = subprocess.run(
                    [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=self._timeout_seconds,
                    env=environment,
                )
            except subprocess.TimeoutExpired as error:
                _cleanup_owned_word_process(owned_process_path, powershell)
                raise PageCountVerificationError(
                    "Microsoft Word page-count verification timed out after "
                    f"{self._timeout_seconds:g} seconds."
                ) from error
            except OSError as error:
                _cleanup_owned_word_process(owned_process_path, powershell)
                raise PageCountVerificationError(
                    f"Microsoft Word page-count verification could not run: {error}"
                ) from error
        if result.returncode != 0:
            raise PageCountVerificationError(
                "Microsoft Word could not render the DOCX for page-count verification: "
                f"{result.stderr.strip() or result.stdout.strip()} "
                f"({_docx_diagnostics(validated_paths[0], 'Microsoft Word')})"
            )
        try:
            raw_counts = result.stdout.strip().splitlines()[-1].split(",")
            page_counts = [int(value) for value in raw_counts]
        except (IndexError, ValueError) as error:
            raise PageCountVerificationError(
                "Microsoft Word returned no usable page-count batch "
                f"({_docx_diagnostics(validated_paths[0], 'Microsoft Word')})."
            ) from error
        if len(page_counts) != len(validated_paths):
            raise PageCountVerificationError(
                "Microsoft Word returned an incomplete page-count batch."
            )
        return [
            PageCountMeasurement(
                page_count=page_count,
                provider="Microsoft Word ComputeStatistics",
                confidence="exact",
                exact=True,
            )
            for page_count in page_counts
        ]


class ExactDocxPageCountProvider:
    """Prefer LibreOffice and fall back to Microsoft Word if available."""

    def __init__(self, *, word_timeout_seconds: float = 15.0) -> None:
        self._providers: tuple[DocxPageCountProvider, ...] = (
            LibreOfficeDocxPageCountProvider(),
            MicrosoftWordDocxPageCountProvider(word_timeout_seconds),
        )

    def measure(self, docx_path: Path) -> PageCountMeasurement:
        failures: list[str] = []
        for provider in self._providers:
            try:
                return provider.measure(docx_path)
            except PageCountVerificationError as error:
                failures.append(str(error))
        raise PageCountVerificationError(
            "Exact DOCX page-count verification failed: " + " ".join(failures)
        )

    def measure_many(self, docx_paths: list[Path]) -> list[PageCountMeasurement]:
        failures: list[str] = []
        for provider in self._providers:
            try:
                batch_measure = getattr(provider, "measure_many", None)
                if callable(batch_measure):
                    return list(batch_measure(docx_paths))
                return [provider.measure(path) for path in docx_paths]
            except PageCountVerificationError as error:
                failures.append(str(error))
        raise PageCountVerificationError(
            "Exact DOCX page-count verification failed: " + " ".join(failures)
        )


def _cleanup_owned_word_process(owned_process_path: Path, powershell: str) -> None:
    """Terminate only the Word PID recorded by this application's COM instance."""

    if not owned_process_path.is_file():
        return
    cleanup_script = r"""
$parts = (Get-Content -Raw -LiteralPath $env:RESUME_WORD_OWNED_PROCESS_PATH).Trim().Split('|')
if ($parts.Count -ne 2) { exit 0 }
[int]$ownedProcessId = $parts[0]
[long]$ownedStartTicks = $parts[1]
$owned = Get-Process -Id $ownedProcessId -ErrorAction SilentlyContinue
if (
    $null -ne $owned -and
    $owned.ProcessName -eq 'WINWORD' -and
    $owned.StartTime.ToUniversalTime().Ticks -eq $ownedStartTicks
) {
    Stop-Process -Id $ownedProcessId -Force -ErrorAction SilentlyContinue
}
"""
    environment = os.environ.copy()
    environment["RESUME_WORD_OWNED_PROCESS_PATH"] = str(owned_process_path)
    try:
        subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-Command", cleanup_script],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired):
        return


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
    page_utilization: PageUtilizationDiagnostic
    verification_failure: str | None = None


class ManagedResumeRenderer:
    _page_width, _page_height = letter
    _margin = 48
    _line_height = 12
    _body_font = "Helvetica"
    _body_size = 9
    _max_overflow_reductions = 32
    _severe_underfill_threshold = TEMPLATE_V1_UTILIZATION_TARGET_FLOOR

    def __init__(
        self,
        layout_profile: LayoutProfile | None = None,
        reference_path: Path | None = None,
        page_count_provider: DocxPageCountProvider | None = None,
    ) -> None:
        if reference_path is not None and layout_profile is None:
            raise ValueError(
                "Template V1 uses its reviewed static layout contract; "
                "pass an explicit layout_profile for renderer experiments."
            )
        self._uses_static_template_v1 = layout_profile is None
        self._layout_profile = layout_profile or load_template_v1_layout_profile()
        self._page_count_provider = page_count_provider or ExactDocxPageCountProvider()
        self._last_measurement: PageCountMeasurement | None = None
        self._initial_measurement: PageCountMeasurement | None = None
        self._last_overflow_reduction_count = 0
        self._last_page_utilization: PageUtilizationDiagnostic | None = None
        self._last_verification_failure: str | None = None

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
    def last_page_utilization(self) -> PageUtilizationDiagnostic | None:
        return self._last_page_utilization

    @property
    def last_verification_failure(self) -> str | None:
        return self._last_verification_failure

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
        utilization = self._last_page_utilization
        if utilization is None:
            raise PageCountVerificationError("The final DOCX has no page-utilization diagnostic.")
        return ManagedRenderResult(
            docx_path=docx_path,
            pdf_path=pdf_path,
            page_count=measurement.page_count,
            measurement_provider=measurement.provider,
            measurement_confidence=measurement.confidence,
            exact_page_count_verified=measurement.exact,
            overflow_reduction_count=self._last_overflow_reduction_count,
            page_utilization=utilization,
            verification_failure=self._last_verification_failure,
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
        self._last_page_utilization = None
        self._last_verification_failure = None
        for _ in range(self._max_overflow_reductions + 1):
            if self._uses_static_template_v1:
                render_template_v1_resume(candidate, path)
            else:
                render_structured_resume(candidate, self._layout_profile, path)
            if not path.is_file() or path.stat().st_size <= 0:
                raise PageCountVerificationError(
                    "DOCX rendering completed without a non-empty candidate file "
                    f"({_docx_diagnostics(path, 'page-count verification')})."
                )
            try:
                measurement = self._page_count_provider.measure(path)
            except PageCountVerificationError as error:
                self._last_verification_failure = str(error)
                return self._accept_estimated_candidate(candidate, path)
            self._last_measurement = measurement
            if self._initial_measurement is None:
                self._initial_measurement = measurement
            if not measurement.exact:
                self._last_verification_failure = (
                    f"Page-count provider {measurement.provider!r} is not exact; "
                    "the one-page invariant cannot be verified."
                )
                return self._accept_estimated_candidate(
                    candidate,
                    path,
                    provider=measurement.provider,
                )
            if measurement.page_count == 1:
                self._last_page_utilization = diagnose_docx_page_utilization(
                    path,
                    self._layout_profile,
                    measurement,
                    severe_underfill_threshold=self._severe_underfill_threshold,
                )
                return candidate
            if measurement.page_count < 1:
                path.unlink(missing_ok=True)
                raise PageCountVerificationError(
                    "The DOCX page-count provider returned an invalid count."
                )
            reduced = _reduce_optional_content(candidate)
            if reduced is None:
                path.unlink(missing_ok=True)
                raise PageOverflowError(
                    "The rendered DOCX exceeds one page and has no optional content left to remove."
                )
            candidate = reduced
            self._last_overflow_reduction_count += 1
        path.unlink(missing_ok=True)
        raise PageOverflowError(
            "The rendered DOCX did not reach one page within the bounded reduction loop."
        )

    def _accept_estimated_candidate(
        self,
        candidate: StructuredResume,
        path: Path,
        *,
        provider: str = "deterministic Template V1 occupancy estimate",
    ) -> StructuredResume:
        provisional = PageCountMeasurement(
            page_count=1,
            provider=provider,
            confidence="estimated",
            exact=False,
        )
        diagnostic = diagnose_docx_page_utilization(
            path,
            self._layout_profile,
            provisional,
            severe_underfill_threshold=self._severe_underfill_threshold,
        )
        estimated_page_count = max(
            1,
            math.ceil(diagnostic.estimated_utilization_ratio),
        )
        self._last_measurement = PageCountMeasurement(
            page_count=estimated_page_count,
            provider=provider,
            confidence="estimated",
            exact=False,
        )
        self._last_page_utilization = diagnostic
        if diagnostic.estimated_utilization_ratio <= 1.0:
            return candidate
        path.unlink(missing_ok=True)
        failure = (
            f" Exact pagination failure: {self._last_verification_failure}"
            if self._last_verification_failure
            else ""
        )
        raise PageOverflowError(
            "The deterministic Template V1 occupancy estimate exceeds one page while "
            f"exact pagination is unavailable.{failure}"
        )

    def _render_pdf(self, resume: StructuredResume, path: Path) -> None:
        canvas = Canvas(str(path), pagesize=letter)
        left = self._layout_profile.page.left_margin_twips / 20
        right = self._page_width - (self._layout_profile.page.right_margin_twips / 20)
        self._pdf_bottom_margin = self._layout_profile.page.bottom_margin_twips / 20
        y = self._page_height - (self._layout_profile.page.top_margin_twips / 20)
        canvas.setFont("Times-Bold", 16)
        canvas.drawCentredString((left + right) / 2, y, resume.display_name)
        y -= 17
        if resume.contact_line:
            canvas.setFont("Times-Roman", 9)
            canvas.drawCentredString((left + right) / 2, y, resume.contact_line)
            y -= 12
        if resume.education:
            y = self._pdf_heading(canvas, "Education", y, left, right)
            for record in resume.education:
                y = self._pdf_metadata(
                    canvas,
                    record.school,
                    compose_date_range(record.start_date, education_end_date(record)),
                    y,
                    left,
                    right,
                    "Times-Bold",
                )
                y = self._pdf_metadata(
                    canvas,
                    _pdf_education_program(record),
                    record.location,
                    y,
                    left,
                    right,
                    "Times-Italic",
                )
                awards = f"Awards: {', '.join(record.awards)}" if record.awards else ""
                gpa = f"GPA: {record.gpa}" if record.gpa else ""
                if awards or gpa:
                    y = self._pdf_bullet(
                        canvas,
                        ", ".join(value for value in (awards, gpa) if value),
                        y,
                        left,
                        right,
                    )
                coursework = record.relevant_coursework or resume.selected_coursework
                if coursework:
                    y = self._pdf_bullet(
                        canvas,
                        f"Relevant Courses: {', '.join(coursework)}",
                        y,
                        left,
                        right,
                    )
        if resume.technical_skills or resume.selected_skills:
            y = self._pdf_heading(canvas, "Technical Skills", y, left, right)
            if resume.technical_skills:
                rows = [
                    f"{category.category}: "
                    + ", ".join(category.values or [skill.value for skill in category.skills])
                    for category in resume.technical_skills
                ]
            else:
                rows = [f"Skills: {', '.join(resume.selected_skills)}"]
            for row in rows:
                y = self._draw_wrapped_text_at(canvas, row, y, left, right - left)
        if resume.experiences or resume.experience_bullets:
            y = self._pdf_heading(canvas, "Technical Experience", y, left, right)
            y = self._pdf_entries(
                canvas,
                resume.experiences,
                resume.experience_bullets,
                resume.entity_titles,
                EntityKind.EXPERIENCE,
                y,
                left,
                right,
            )
        if resume.projects or resume.project_bullets:
            y = self._pdf_heading(canvas, "Projects", y, left, right)
            y = self._pdf_entries(
                canvas,
                resume.projects,
                resume.project_bullets,
                resume.entity_titles,
                EntityKind.PROJECT,
                y,
                left,
                right,
            )
        if y < self._pdf_bottom_margin:
            raise PageOverflowError(
                "The managed template overflowed one page; revise the content plan."
            )
        canvas.save()

    def _pdf_entries(
        self,
        canvas: Canvas,
        records: list[ResumeItem],
        bullets: dict[str, list[StructuredBullet]],
        titles: dict[str, str],
        kind: EntityKind,
        y: float,
        left: float,
        right: float,
    ) -> float:
        known_ids = {item.id for item in records}
        ordered = [
            *records,
            *[
                ResumeItem(
                    id=entity_id,
                    title=titles.get(entity_id, entity_id),
                    kind=kind,
                )
                for entity_id in bullets
                if entity_id not in known_ids
            ],
        ]
        for index, item in enumerate(ordered):
            if index:
                y -= 2
            title = item.title
            if (
                item.award_or_placement
                and item.award_or_placement.casefold() not in title.casefold()
            ):
                title += f" ({item.award_or_placement})"
            technology = item.technology_label or ", ".join(item.technologies)
            if technology and technology.casefold() not in title.casefold():
                title += f" | {technology}"
            y = self._pdf_metadata(
                canvas,
                title,
                compose_date_range(item.start_date, item.end_date),
                y,
                left,
                right,
                "Times-Bold",
            )
            if item.organization or item.location:
                y = self._pdf_metadata(
                    canvas,
                    item.organization,
                    item.location,
                    y,
                    left,
                    right,
                    "Times-Italic",
                )
            for bullet in bullets.get(item.id, []):
                y = self._pdf_bullet(canvas, bullet.text, y, left, right)
        return y

    def _pdf_heading(
        self,
        canvas: Canvas,
        text: str,
        y: float,
        left: float,
        right: float,
    ) -> float:
        self._ensure_pdf_space(y)
        y -= 3
        canvas.setFont("Times-Bold", 10)
        canvas.drawString(left, y, text)
        canvas.setLineWidth(0.6)
        canvas.line(left, y - 2, right, y - 2)
        return y - 12

    def _pdf_metadata(
        self,
        canvas: Canvas,
        left_text: str | None,
        right_text: str | None,
        y: float,
        left: float,
        right: float,
        font: str,
    ) -> float:
        if not left_text and not right_text:
            return y
        left_value = left_text or ""
        right_value = right_text or ""
        canvas.setFont(font, 10)
        collision = bool(
            left_value
            and right_value
            and stringWidth(left_value, font, 10) + stringWidth(right_value, font, 10) + 12
            > right - left
        )
        self._ensure_pdf_space(y)
        if left_value:
            canvas.drawString(left, y, left_value)
        if right_value and not collision:
            canvas.drawRightString(right, y, right_value)
        y -= 11
        if right_value and collision:
            self._ensure_pdf_space(y)
            canvas.drawRightString(right, y, right_value)
            y -= 11
        return y

    def _pdf_bullet(
        self,
        canvas: Canvas,
        text: str,
        y: float,
        left: float,
        right: float,
    ) -> float:
        self._ensure_pdf_space(y)
        canvas.setFont("Times-Roman", 9)
        canvas.drawString(left + 4, y, "•")
        return self._draw_wrapped_text_at(
            canvas,
            text,
            y,
            left + 14,
            right - left - 14,
        )

    def _draw_wrapped_text_at(
        self,
        canvas: Canvas,
        text: str,
        y: float,
        x: float,
        width: float,
    ) -> float:
        canvas.setFont("Times-Roman", 9)
        line = ""
        lines: list[str] = []
        for word in text.split():
            trial = f"{line} {word}".strip()
            if stringWidth(trial, "Times-Roman", 9) <= width:
                line = trial
            else:
                if line:
                    lines.append(line)
                line = word
        if line:
            lines.append(line)
        for wrapped_line in lines:
            self._ensure_pdf_space(y)
            canvas.drawString(x, y, wrapped_line)
            y -= 10
        return y

    def _ensure_pdf_space(self, y: float) -> None:
        if y < getattr(self, "_pdf_bottom_margin", self._margin):
            raise PageOverflowError(
                "The managed template overflowed one page; revise the content plan."
            )


def _pdf_education_program(record: EducationRecord) -> str:
    values = [
        getattr(record, "program", ""),
        getattr(record, "minor_or_specialization", None),
        getattr(record, "co_op_designation", None),
    ]
    output: list[str] = []
    for value in values:
        if value and value.casefold() not in " ".join(output).casefold():
            output.append(value)
    return ", ".join(output)


def _count_pdf_pages(pdf_path: Path) -> int:
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]

        return len(PdfReader(str(pdf_path)).pages)
    except ImportError:
        pass
    try:
        from PyPDF2 import PdfReader  # type: ignore[import-not-found]

        return len(PdfReader(str(pdf_path)).pages)
    except ImportError:
        pass
    data = pdf_path.read_bytes()
    pages = re.findall(rb"/Type\s*/Page(?!s)\b", data)
    if not pages:
        raise PageCountVerificationError("Unable to count pages in the rendered PDF page tree.")
    return len(pages)


def diagnose_docx_page_utilization(
    docx_path: Path,
    layout_profile: LayoutProfile,
    measurement: PageCountMeasurement,
    *,
    severe_underfill_threshold: float = TEMPLATE_V1_UTILIZATION_TARGET_FLOOR,
) -> PageUtilizationDiagnostic:
    """Estimate occupied vertical space while keeping exact page count authoritative."""

    document = Document(str(docx_path))
    occupied = 0
    blank_paragraphs = 0
    for paragraph in document.paragraphs:
        if not paragraph.text.strip():
            blank_paragraphs += 1
            continue
        occupied += _estimated_paragraph_height_twips(
            paragraph,
            layout_profile.page.usable_width_twips,
        )
    usable_height = layout_profile.page.usable_height_twips
    ratio = occupied / usable_height
    if not measurement.exact:
        status = PageUtilizationStatus.UNVERIFIED
        message = "Page utilization is unverified because the page count is not exact."
    elif measurement.page_count > 1:
        status = PageUtilizationStatus.OVERFLOW
        message = "The resume overflows the one-page Template V1 contract."
    elif measurement.page_count == 1 and ratio < severe_underfill_threshold:
        status = PageUtilizationStatus.SEVERE_UNDERFILL
        message = (
            "The resume is one page but severely underfilled; no additional admissible "
            "evidence was selected."
        )
    elif measurement.page_count == 1:
        status = PageUtilizationStatus.ACCEPTABLE_ONE_PAGE
        message = "The resume is an acceptably utilized one-page composition."
    else:
        status = PageUtilizationStatus.UNVERIFIED
        message = "The page-count provider returned no usable page."
    return PageUtilizationDiagnostic(
        status=status,
        page_count=measurement.page_count,
        exact_page_count=measurement.exact,
        estimated_occupied_height_twips=occupied,
        usable_height_twips=usable_height,
        estimated_utilization_ratio=ratio,
        severe_underfill_threshold=severe_underfill_threshold,
        uncontrolled_blank_paragraph_count=blank_paragraphs,
        message=message,
    )


def _estimated_paragraph_height_twips(
    paragraph: Paragraph,
    usable_width_twips: int,
) -> int:
    formatting = paragraph.paragraph_format
    left_indent = formatting.left_indent.twips if formatting.left_indent else 0
    right_indent = formatting.right_indent.twips if formatting.right_indent else 0
    available_width = max(720, usable_width_twips - left_indent - right_indent)
    run_sizes = [run.font.size.pt for run in paragraph.runs if run.font.size is not None]
    font_size_twips = int(max(run_sizes, default=10.0) * 20)
    visual_lines = sum(
        _estimated_wrapped_line_count(segment, available_width, font_size_twips)
        for segment in paragraph.text.splitlines() or [paragraph.text]
    )
    explicit_line_spacing = formatting.line_spacing
    if hasattr(explicit_line_spacing, "twips"):
        line_height = max(font_size_twips, int(explicit_line_spacing.twips))
    else:
        line_height = int(font_size_twips * 1.08)
    before = formatting.space_before.twips if formatting.space_before else 0
    after = formatting.space_after.twips if formatting.space_after else 0
    return before + after + max(1, visual_lines) * line_height


def _estimated_wrapped_line_count(
    text: str,
    available_width_twips: int,
    font_size_twips: int,
) -> int:
    if not text:
        return 1
    width = 0.0
    lines = 1
    for character in text:
        if character == "\t":
            continue
        if character.isspace():
            factor = 0.25
        elif character in "MW@%&":
            factor = 0.85
        elif character in "ilI.,:;'|!":
            factor = 0.28
        elif character.isupper():
            factor = 0.62
        else:
            factor = 0.5
        character_width = font_size_twips * factor
        if width and width + character_width > available_width_twips:
            lines += 1
            width = character_width
        else:
            width += character_width
    return lines


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
                    bullets[entity_id] = []
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
