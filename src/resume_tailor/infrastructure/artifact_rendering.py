from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from resume_tailor.application.generation_diagnostics import GenerationTelemetry
from resume_tailor.domain.generated_artifact import GenerationStage
from resume_tailor.domain.models import StructuredResume
from resume_tailor.infrastructure.static_template_docx import render_template_v1_resume


class TemplateV1ArtifactRenderer:
    """Render the selected final resume once without repeating pagination."""

    def __init__(self, telemetry: GenerationTelemetry | None = None) -> None:
        self._telemetry = telemetry or GenerationTelemetry()

    def render_docx_bytes(self, resume: StructuredResume) -> bytes:
        with TemporaryDirectory(prefix="resume-artifact-") as directory:
            path = Path(directory) / "final-resume.docx"
            with self._telemetry.measure(GenerationStage.DOCX_RENDERING):
                self._telemetry.increment("docx_renders")
                render_template_v1_resume(resume, path)
            return path.read_bytes()


__all__ = ["TemplateV1ArtifactRenderer"]
