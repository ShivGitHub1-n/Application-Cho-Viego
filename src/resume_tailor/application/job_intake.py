from __future__ import annotations

import re

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


def build_job_posting(
    posting_id: str,
    title: str,
    description: str,
    *,
    company_name: str | None = None,
) -> JobPosting:
    normalized_title = title.strip()
    if not normalized_title:
        raise InvalidJobDescriptionError("Job title must not be empty")
    normalized_description = normalize_job_description(description)
    return JobPosting(
        id=posting_id,
        title=normalized_title,
        description=normalized_description,
        company_name=(
            company_name.strip()
            if company_name and company_name.strip()
            else _explicit_company_name(normalized_description)
        ),
    )


def _explicit_company_name(description: str) -> str | None:
    """Read only explicitly labelled company metadata from pasted posting text."""

    lines = [line.strip() for line in description.splitlines()]
    for index, line in enumerate(lines):
        inline = re.fullmatch(r"(?:company|company name|employer)\s*:\s*(.+)", line, re.I)
        if inline is not None:
            value = inline.group(1).strip()
            return value or None
        if re.fullmatch(r"(?:company|company name|employer)\s*:?", line, re.I):
            for following in lines[index + 1 :]:
                if following:
                    return following
    return None
