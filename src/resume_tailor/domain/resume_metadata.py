from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, Field

from resume_tailor.domain.models import (
    EducationRecord,
    EntityKind,
    GraduationStatus,
    ResumeItem,
    StructuredResume,
)

_YEAR_ONLY = re.compile(r"^(?:19|20)\d{2}$")
_MONTH_YEAR = re.compile(
    r"^(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\.?\s+(?:19|20)\d{2}$",
    re.IGNORECASE,
)
_CURRENT = re.compile(r"^(?:present|current|ongoing)$", re.IGNORECASE)
_RANGE_DELIMITER = re.compile(r"\s+(?:\u2013|\u2014|-)\s+")
_METADATA_DELIMITER = re.compile(r"\s+(?:\u2013|\u2014|-)\s+|\s*\|\s*")


class ResumeMetadataIntegrityError(ValueError):
    """Raised when composed output metadata has lost single-value authority."""


class DatePrecision(StrEnum):
    ABSENT = "absent"
    YEAR = "year"
    MONTH_YEAR = "month_year"
    CURRENT = "current"
    REVIEWED_TEXT = "reviewed_text"


class EntryMetadataFidelity(BaseModel):
    entry_id: str
    entry_kind: EntityKind
    title: str
    organization: str | None = None
    location: str | None = None
    source_start_date: str | None = None
    source_end_date: str | None = None
    start_date_precision: DatePrecision
    end_date_precision: DatePrecision
    rendered_date_text: str | None = None


class EducationMetadataFidelity(BaseModel):
    education_index: int = Field(ge=0)
    institution: str
    program: str
    location: str | None = None
    source_start_date: str | None = None
    source_end_date: str | None = None
    start_date_precision: DatePrecision
    end_date_precision: DatePrecision
    rendered_date_text: str | None = None
    selected_detail_fields: list[str] = Field(default_factory=list)


class ResumeMetadataFidelityReport(BaseModel):
    entries: list[EntryMetadataFidelity] = Field(default_factory=list)
    education: list[EducationMetadataFidelity] = Field(default_factory=list)


def date_precision(value: str | None) -> DatePrecision:
    cleaned = (value or "").strip()
    if not cleaned:
        return DatePrecision.ABSENT
    if _YEAR_ONLY.fullmatch(cleaned):
        return DatePrecision.YEAR
    if _MONTH_YEAR.fullmatch(cleaned):
        return DatePrecision.MONTH_YEAR
    if _CURRENT.fullmatch(cleaned):
        return DatePrecision.CURRENT
    return DatePrecision.REVIEWED_TEXT


def compose_date_range(start: str | None, end: str | None) -> str | None:
    """Join two authoritative reviewed components without changing their precision."""

    values = [value for value in (start, end) if value]
    return " \u2013 ".join(values) or None


def education_end_date(record: EducationRecord) -> str | None:
    expected = record.expected_graduation_date
    if expected:
        if (
            record.graduation_status is GraduationStatus.EXPECTED
            and not expected.casefold().startswith(("expected ", "anticipated "))
        ):
            return f"Expected {expected}"
        return expected
    return record.graduation_date


def validate_structured_resume_metadata(
    resume: StructuredResume,
) -> ResumeMetadataFidelityReport:
    """Validate output-bearing metadata and return a typed fidelity trace."""

    _require_unique_ids(resume.experiences, "experience")
    _require_unique_ids(resume.projects, "project")
    _require_unique_ids(
        [*resume.experiences, *resume.projects],
        "cross-section",
    )
    entries: list[EntryMetadataFidelity] = []
    for item in resume.experiences:
        _validate_entry(item, EntityKind.EXPERIENCE)
        entries.append(
            EntryMetadataFidelity(
                entry_id=item.id,
                entry_kind=item.kind,
                title=item.title,
                organization=item.organization,
                location=item.location,
                source_start_date=item.start_date,
                source_end_date=item.end_date,
                start_date_precision=date_precision(item.start_date),
                end_date_precision=date_precision(item.end_date),
                rendered_date_text=compose_date_range(item.start_date, item.end_date),
            )
        )
    for item in resume.projects:
        _validate_entry(item, EntityKind.PROJECT)
        entries.append(
            EntryMetadataFidelity(
                entry_id=item.id,
                entry_kind=item.kind,
                title=item.title,
                organization=item.organization,
                location=item.location,
                source_start_date=item.start_date,
                source_end_date=item.end_date,
                start_date_precision=date_precision(item.start_date),
                end_date_precision=date_precision(item.end_date),
                rendered_date_text=compose_date_range(item.start_date, item.end_date),
            )
        )

    education: list[EducationMetadataFidelity] = []
    for index, record in enumerate(resume.education):
        end = education_end_date(record)
        _validate_metadata_value(
            f"education[{index}].school",
            record.school,
        )
        _validate_metadata_value(
            f"education[{index}].program",
            record.program,
        )
        _validate_metadata_value(
            f"education[{index}].location",
            record.location,
        )
        _validate_date_pair(
            f"education[{index}]",
            record.start_date,
            end,
        )
        details = [
            field
            for field, present in (
                ("minor_or_specialization", bool(record.minor_or_specialization)),
                ("co_op_designation", bool(record.co_op_designation)),
                ("gpa", bool(record.gpa)),
                ("awards", bool(record.awards)),
                ("relevant_coursework", bool(record.relevant_coursework)),
            )
            if present
        ]
        education.append(
            EducationMetadataFidelity(
                education_index=index,
                institution=record.school,
                program=record.program,
                location=record.location,
                source_start_date=record.start_date,
                source_end_date=end,
                start_date_precision=date_precision(record.start_date),
                end_date_precision=date_precision(
                    record.expected_graduation_date or record.graduation_date
                ),
                rendered_date_text=compose_date_range(record.start_date, end),
                selected_detail_fields=details,
            )
        )
    return ResumeMetadataFidelityReport(entries=entries, education=education)


def _require_unique_ids(items: list[ResumeItem], label: str) -> None:
    ids = [item.id for item in items]
    duplicates = sorted({item_id for item_id in ids if ids.count(item_id) > 1})
    if duplicates:
        raise ResumeMetadataIntegrityError(
            f"Composed {label} metadata contains duplicate entry IDs: {duplicates}"
        )


def _validate_entry(item: ResumeItem, expected_kind: EntityKind) -> None:
    if item.kind is not expected_kind:
        raise ResumeMetadataIntegrityError(
            f"Composed entry {item.id!r} is in the {expected_kind.value} section "
            f"but carries {item.kind.value} metadata."
        )
    for field, value in (
        ("title", item.title),
        ("organization", item.organization),
        ("location", item.location),
        ("subtitle", item.subtitle),
        ("technology_label", item.technology_label),
    ):
        _validate_metadata_value(f"{item.kind.value}[{item.id}].{field}", value)
    _validate_date_pair(
        f"{item.kind.value}[{item.id}]",
        item.start_date,
        item.end_date,
    )


def _validate_date_pair(
    label: str,
    start: str | None,
    end: str | None,
) -> None:
    _validate_metadata_value(f"{label}.start_date", start)
    _validate_metadata_value(f"{label}.end_date", end)
    if start and end and (_RANGE_DELIMITER.search(start) or _RANGE_DELIMITER.search(end)):
        raise ResumeMetadataIntegrityError(
            f"{label} date components contain an accumulated date range; "
            "start_date and end_date must each retain one authoritative reviewed value."
        )


def _validate_metadata_value(label: str, value: str | None) -> None:
    cleaned = (value or "").strip()
    if not cleaned:
        return
    pieces = [
        _normalize_metadata_piece(piece)
        for piece in _METADATA_DELIMITER.split(cleaned)
        if piece.strip()
    ]
    if len(pieces) < 2:
        return
    for width in range(1, (len(pieces) // 2) + 1):
        repeated = pieces[:width]
        if len(pieces) >= width * 2 and pieces[width : width * 2] == repeated:
            raise ResumeMetadataIntegrityError(
                f"{label} contains repeated composed metadata: {cleaned!r}"
            )


def _normalize_metadata_piece(value: str) -> str:
    return " ".join(value.casefold().split()).strip(" ,;:")


__all__ = [
    "DatePrecision",
    "EducationMetadataFidelity",
    "EntryMetadataFidelity",
    "ResumeMetadataFidelityReport",
    "ResumeMetadataIntegrityError",
    "compose_date_range",
    "date_precision",
    "education_end_date",
    "validate_structured_resume_metadata",
]
