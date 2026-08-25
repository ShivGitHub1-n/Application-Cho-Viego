from __future__ import annotations

import os
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from pypdf import PdfReader

from resume_tailor.domain.models import StructuredResume
from resume_tailor.domain.resume_editor import ResumeEditorFitStatus, ResumeEditorRender
from resume_tailor.infrastructure.rendering import (
    ExactDocxPageCountProvider,
    PageCountMeasurement,
    PageCountVerificationError,
    diagnose_docx_page_utilization,
)
from resume_tailor.infrastructure.static_template_docx import render_template_v1_resume
from resume_tailor.infrastructure.template_v1 import load_template_v1_layout_profile


class ResumePreviewConversionError(ValueError):
    pass


class ExactDocxPdfConverter:
    """Convert the rendered DOCX itself to PDF without changing its content."""

    def __init__(self, *, timeout_seconds: float = 20.0) -> None:
        self._timeout_seconds = timeout_seconds

    def convert(self, docx_path: Path, pdf_path: Path) -> str:
        failures: list[str] = []
        executable = shutil.which("soffice") or shutil.which("libreoffice")
        if executable:
            try:
                return self._libreoffice(executable, docx_path, pdf_path)
            except ResumePreviewConversionError as error:
                failures.append(str(error))
        try:
            return self._microsoft_word(docx_path, pdf_path)
        except ResumePreviewConversionError as error:
            failures.append(str(error))
        raise ResumePreviewConversionError(" ".join(failures))

    def _libreoffice(self, executable: str, docx_path: Path, pdf_path: Path) -> str:
        try:
            result = subprocess.run(
                [
                    executable,
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(pdf_path.parent),
                    str(docx_path),
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=self._timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ResumePreviewConversionError(
                "LibreOffice could not create the résumé preview."
            ) from error
        generated = pdf_path.parent / f"{docx_path.stem}.pdf"
        if result.returncode != 0 or not generated.is_file():
            raise ResumePreviewConversionError(
                "LibreOffice did not produce the résumé preview PDF."
            )
        if generated != pdf_path:
            generated.replace(pdf_path)
        return "LibreOffice DOCX-to-PDF"

    def _microsoft_word(self, docx_path: Path, pdf_path: Path) -> str:
        powershell = shutil.which("powershell.exe") or shutil.which("powershell")
        if powershell is None:
            raise ResumePreviewConversionError(
                "Microsoft Word preview conversion requires PowerShell."
            )
        script = r"""
$word = $null
$document = $null
$ownedProcessPath = $env:RESUME_EDITOR_WORD_PROCESS_PATH
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class ResumeEditorWordNative {
    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
}
'@
    [uint32]$createdProcessId = 0
    if ($null -ne $word.Hwnd -and [long]$word.Hwnd -ne 0) {
        [void][ResumeEditorWordNative]::GetWindowThreadProcessId(
            [IntPtr][long]$word.Hwnd,
            [ref]$createdProcessId
        )
    }
    if ($createdProcessId -gt 0) {
        $createdProcess = Get-Process -Id $createdProcessId -ErrorAction Stop
        "$createdProcessId|$($createdProcess.StartTime.ToUniversalTime().Ticks)" |
            Set-Content -LiteralPath $ownedProcessPath -Encoding ASCII
    }
    $document = $word.Documents.Open(
        $env:RESUME_EDITOR_DOCX_PATH,
        $false,
        $true,
        $false
    )
    $document.ExportAsFixedFormat($env:RESUME_EDITOR_PDF_PATH, 17)
}
finally {
    if ($null -ne $document) { $document.Close($false) }
    if ($null -ne $word) { $word.Quit() }
}
"""
        environment = os.environ.copy()
        environment["RESUME_EDITOR_DOCX_PATH"] = str(docx_path)
        environment["RESUME_EDITOR_PDF_PATH"] = str(pdf_path)
        owned_process_path = pdf_path.parent / "owned-editor-word-process.txt"
        environment["RESUME_EDITOR_WORD_PROCESS_PATH"] = str(owned_process_path)
        try:
            result = subprocess.run(
                [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                check=False,
                timeout=self._timeout_seconds,
                env=environment,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            _cleanup_owned_word_process(owned_process_path, powershell)
            raise ResumePreviewConversionError(
                "Microsoft Word could not create the résumé preview."
            ) from error
        finally:
            if owned_process_path.is_file():
                _cleanup_owned_word_process(owned_process_path, powershell)
        if result.returncode != 0 or not pdf_path.is_file() or pdf_path.stat().st_size <= 0:
            raise ResumePreviewConversionError(
                "Microsoft Word did not produce the résumé preview PDF."
            )
        return "Microsoft Word DOCX-to-PDF"


class TemplateV1ResumeEditorRenderer:
    """Render one applied manual revision without semantic composition or trimming."""

    def __init__(
        self,
        *,
        converter: ExactDocxPdfConverter | None = None,
        page_count_provider: ExactDocxPageCountProvider | None = None,
    ) -> None:
        self._converter = converter or ExactDocxPdfConverter()
        self._page_count_provider = page_count_provider or ExactDocxPageCountProvider()
        self._layout_profile = load_template_v1_layout_profile()

    def render(
        self,
        resume: StructuredResume,
        *,
        source_docx_bytes: bytes | None = None,
    ) -> ResumeEditorRender:
        with TemporaryDirectory(prefix="resume-editor-render-") as directory:
            docx_path = Path(directory) / "edited-resume.docx"
            pdf_path = Path(directory) / "edited-resume.pdf"
            if source_docx_bytes is None:
                render_template_v1_resume(resume, docx_path)
            else:
                docx_path.write_bytes(source_docx_bytes)
            docx_bytes = docx_path.read_bytes()
            document_fingerprint = sha256(docx_bytes).hexdigest()
            try:
                provider = self._converter.convert(docx_path, pdf_path)
                pdf_bytes = pdf_path.read_bytes()
                page_count = len(PdfReader(str(pdf_path)).pages)
                measurement = PageCountMeasurement(
                    page_count=page_count,
                    provider=f"{provider} page tree",
                    confidence="exact",
                    exact=True,
                )
                utilization = diagnose_docx_page_utilization(
                    docx_path,
                    self._layout_profile,
                    measurement,
                )
                return ResumeEditorRender(
                    document_fingerprint=document_fingerprint,
                    docx_bytes=docx_bytes,
                    pdf_bytes=pdf_bytes,
                    page_count=page_count,
                    exact_pagination=True,
                    pagination_provider=measurement.provider,
                    utilization_ratio=utilization.estimated_utilization_ratio,
                    status=(
                        ResumeEditorFitStatus.FITS_ONE_PAGE
                        if page_count == 1
                        else ResumeEditorFitStatus.EXCEEDS_ONE_PAGE
                    ),
                )
            except (ResumePreviewConversionError, OSError, ValueError) as error:
                try:
                    measurement = self._page_count_provider.measure(docx_path)
                except PageCountVerificationError as pagination_error:
                    return ResumeEditorRender(
                        document_fingerprint=document_fingerprint,
                        docx_bytes=docx_bytes,
                        pagination_provider="unavailable",
                        status=ResumeEditorFitStatus.PREVIEW_UNAVAILABLE,
                        failure_reason=str(pagination_error),
                    )
                utilization = diagnose_docx_page_utilization(
                    docx_path,
                    self._layout_profile,
                    measurement,
                )
                return ResumeEditorRender(
                    document_fingerprint=document_fingerprint,
                    docx_bytes=docx_bytes,
                    page_count=measurement.page_count,
                    exact_pagination=measurement.exact,
                    pagination_provider=measurement.provider,
                    utilization_ratio=utilization.estimated_utilization_ratio,
                    status=ResumeEditorFitStatus.PREVIEW_UNAVAILABLE,
                    failure_reason=str(error),
                )


def _cleanup_owned_word_process(path: Path, powershell: str) -> None:
    script = r"""
$parts = (Get-Content -Raw -LiteralPath $env:RESUME_EDITOR_WORD_PROCESS_PATH).Trim().Split('|')
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
    environment["RESUME_EDITOR_WORD_PROCESS_PATH"] = str(path)
    try:
        subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired):
        return


__all__ = [
    "ExactDocxPdfConverter",
    "ResumePreviewConversionError",
    "TemplateV1ResumeEditorRenderer",
]
