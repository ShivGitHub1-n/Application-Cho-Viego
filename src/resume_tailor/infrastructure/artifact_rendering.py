from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from docx import Document
from docx.shared import Pt

from resume_tailor.application.generation_diagnostics import GenerationTelemetry
from resume_tailor.domain.generated_artifact import ExactResumeArtifactRender, GenerationStage
from resume_tailor.domain.models import StructuredResume
from resume_tailor.infrastructure.rendering import (
    ExactDocxPageCountProvider,
    diagnose_docx_page_utilization,
)
from resume_tailor.infrastructure.static_template_docx import render_template_v1_resume
from resume_tailor.infrastructure.template_v1 import load_template_v1_layout_profile


class TemplateV1ArtifactRenderer:
    """Render the selected final resume once without repeating pagination."""

    def __init__(
        self,
        telemetry: GenerationTelemetry | None = None,
        *,
        page_count_provider: ExactDocxPageCountProvider | None = None,
    ) -> None:
        self._telemetry = telemetry or GenerationTelemetry()
        self._page_count_provider = page_count_provider or ExactDocxPageCountProvider()

    def render_docx_bytes(self, resume: StructuredResume) -> bytes:
        with TemporaryDirectory(prefix="resume-artifact-") as directory:
            path = Path(directory) / "final-resume.docx"
            with self._telemetry.measure(GenerationStage.DOCX_RENDERING):
                self._telemetry.increment("docx_renders")
                render_template_v1_resume(resume, path)
            return path.read_bytes()

    def render_demo_artifact(self, resume: StructuredResume) -> ExactResumeArtifactRender:
        """Render the temporary dense demo fixture with bounded readable geometry."""

        with TemporaryDirectory(prefix="resume-demo-artifact-") as directory:
            path = Path(directory) / "final-demo-resume.docx"
            with self._telemetry.measure(GenerationStage.DOCX_RENDERING):
                self._telemetry.increment("docx_renders")
                render_template_v1_resume(resume, path)
                _apply_temporary_demo_geometry(path)
            measurement = self._page_count_provider.measure(path)
            utilization = diagnose_docx_page_utilization(
                path,
                load_template_v1_layout_profile(),
                measurement,
            ).estimated_utilization_ratio
            return ExactResumeArtifactRender(
                docx_bytes=path.read_bytes(),
                page_count=measurement.page_count,
                exact=measurement.exact,
                pagination_provider=measurement.provider,
                utilization_ratio=utilization,
            )


def _apply_temporary_demo_geometry(path: Path) -> None:
    """TEMPORARY DEMO OVERRIDE — remove after demo recording."""

    document = Document(str(path))
    font_scale = 0.95
    spacing_scale = 0.60
    for style in document.styles:
        font = getattr(style, "font", None)
        if font is not None and font.size is not None and font.size.pt <= 11:
            font.size = Pt(font.size.pt * font_scale)
        paragraph_format = getattr(style, "paragraph_format", None)
        if paragraph_format is None:
            continue
        if paragraph_format.space_before is not None:
            paragraph_format.space_before = Pt(
                paragraph_format.space_before.pt * spacing_scale
            )
        if paragraph_format.space_after is not None:
            paragraph_format.space_after = Pt(
                paragraph_format.space_after.pt * spacing_scale
            )
    for paragraph in document.paragraphs:
        paragraph_format = paragraph.paragraph_format
        if paragraph_format.space_before is not None:
            paragraph_format.space_before = Pt(
                paragraph_format.space_before.pt * spacing_scale
            )
        if paragraph_format.space_after is not None:
            paragraph_format.space_after = Pt(
                paragraph_format.space_after.pt * spacing_scale
            )
        for run in paragraph.runs:
            if run.font.size is not None and run.font.size.pt <= 11:
                run.font.size = Pt(run.font.size.pt * font_scale)
    document.save(str(path))


__all__ = ["TemplateV1ArtifactRenderer"]
