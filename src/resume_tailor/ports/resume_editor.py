from __future__ import annotations

from typing import Protocol

from resume_tailor.domain.models import StructuredResume
from resume_tailor.domain.resume_editor import ResumeEditorRender


class ResumeEditorRenderer(Protocol):
    def render(
        self,
        resume: StructuredResume,
        *,
        source_docx_bytes: bytes | None = None,
    ) -> ResumeEditorRender: ...


__all__ = ["ResumeEditorRenderer"]
