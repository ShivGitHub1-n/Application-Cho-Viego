from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from resume_tailor.domain.cover_letter import CoverLetter


class CoverLetterPageMeasurement(Protocol):
    page_count: int
    provider: str
    exact: bool


class CoverLetterRenderedCandidate(Protocol):
    docx_path: Path
    docx_bytes: bytes
    measurement: CoverLetterPageMeasurement
    estimated_utilization: float
    estimated_remaining_lines: int
    pagination_failure: str | None
    blank_trailing_page: bool

    @property
    def page_count(self) -> int: ...


class CoverLetterBatchRenderer(Protocol):
    pagination_attempt_count: int

    def render_candidates(
        self,
        letters: list[CoverLetter],
        output_directory: Path,
    ) -> Sequence[CoverLetterRenderedCandidate]: ...


__all__ = [
    "CoverLetterBatchRenderer",
    "CoverLetterPageMeasurement",
    "CoverLetterRenderedCandidate",
]
