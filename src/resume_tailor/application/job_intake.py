from __future__ import annotations

from resume_tailor.domain.models import JobPosting


class InvalidJobDescriptionError(ValueError):
    pass


def normalize_job_description(text: str) -> str:
    """Normalize transport whitespace while preserving paragraphs and list lines."""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalized.split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    result = "\n".join(lines)
    if not result.strip():
        raise InvalidJobDescriptionError("Job description must not be empty")
    return result


def build_job_posting(posting_id: str, title: str, description: str) -> JobPosting:
    normalized_title = title.strip()
    if not normalized_title:
        raise InvalidJobDescriptionError("Job title must not be empty")
    return JobPosting(
        id=posting_id,
        title=normalized_title,
        description=normalize_job_description(description),
    )
