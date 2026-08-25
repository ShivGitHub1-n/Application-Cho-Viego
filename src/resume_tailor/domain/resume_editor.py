from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from resume_tailor.domain.models import StructuredResume


class ResumeEditorFitStatus(StrEnum):
    FITS_ONE_PAGE = "fits_one_page"
    EXCEEDS_ONE_PAGE = "exceeds_one_page"
    PREVIEW_UNAVAILABLE = "preview_unavailable"


class ResumeEditorRender(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_fingerprint: str
    docx_bytes: bytes
    pdf_bytes: bytes | None = None
    page_count: int | None = Field(default=None, ge=1)
    exact_pagination: bool = False
    pagination_provider: str
    utilization_ratio: float | None = Field(default=None, ge=0)
    status: ResumeEditorFitStatus
    failure_reason: str | None = None


class ResumeEditorRevision(BaseModel):
    model_config = ConfigDict(frozen=True)

    revision_fingerprint: str
    application_fingerprint: str
    baseline_artifact_fingerprint: str
    revision_number: int = Field(ge=0)
    created_at: datetime
    resume: StructuredResume
    render: ResumeEditorRender


class ResumeEditorDownload(BaseModel):
    model_config = ConfigDict(frozen=True)

    revision_fingerprint: str
    docx_bytes: bytes


__all__ = [
    "ResumeEditorDownload",
    "ResumeEditorFitStatus",
    "ResumeEditorRender",
    "ResumeEditorRevision",
]
