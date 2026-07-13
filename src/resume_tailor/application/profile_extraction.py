from __future__ import annotations

import re
from hashlib import sha256

from resume_tailor.domain.models import (
    EvidenceItem,
    MasterProfile,
    ResumeItem,
    TechnicalSkillCategory,
)


class ProfileExtractionIncompleteError(ValueError):
    """The extracted profile has entries but no usable bullet-level evidence."""


_NON_EVIDENCE_LABELS = {
    "experience", "experiences", "employment", "projects", "project",
    "education", "skills", "technical skills", "contact", "references",
}


def normalize_extracted_profile(profile: MasterProfile, source_text: str = "") -> MasterProfile:
    """Canonicalize linked bullet content into stable top-level evidence items."""

    entries = [*profile.experiences, *profile.projects]
    entry_ids = {entry.id for entry in entries}
    source_items: list[tuple[str, EvidenceItem]] = []
    for evidence in profile.evidence:
        if evidence.entity_id not in entry_ids:
            raise ProfileExtractionIncompleteError(
                f"Evidence {evidence.id!r} references an unknown entry {evidence.entity_id!r}"
            )
        if _usable_evidence_text(evidence.source_text):
            source_items.append((evidence.entity_id, evidence))

    for entry in entries:
        existing_texts = {
            evidence.source_text.casefold().strip()
            for entity_id, evidence in source_items
            if entity_id == entry.id
        }
        for text in _entry_bullet_texts(entry):
            if not _usable_evidence_text(text) or text.casefold().strip() in existing_texts:
                continue
            source_items.append(
                (
                    entry.id,
                    EvidenceItem(
                        id="pending",
                        entity_id=entry.id,
                        source_text=text,
                        source_reference=entry.title,
                        technologies=list(entry.technologies),
                        capabilities=list(entry.capabilities),
                    ),
                )
            )
            existing_texts.add(text.casefold().strip())

    if entries and not source_items:
        raise ProfileExtractionIncompleteError(
            "Profile extraction returned entries but no recoverable bullet-level evidence."
        )

    occurrences: dict[str, int] = {}
    canonical: list[EvidenceItem] = []
    for entity_id, evidence in source_items:
        key = f"{entity_id}\0{evidence.source_text}"
        occurrence = occurrences.get(key, 0)
        occurrences[key] = occurrence + 1
        digest = sha256(f"{key}\0{occurrence}".encode()).hexdigest()[:16]
        canonical.append(
            evidence.model_copy(update={"id": f"evidence:{digest}", "entity_id": entity_id})
        )
    normalized = profile.model_copy(update={"evidence": canonical})
    if not normalized.technical_skills and source_text:
        categories = _extract_skill_categories(source_text)
        if categories:
            normalized = MasterProfile.model_validate(
                normalized.model_dump(mode="python") | {"technical_skills": categories}
            )
    return normalized


def audit_extracted_profile(profile: MasterProfile, source_text: str) -> list[str]:
    """Flag concrete extracted facts not supported by source text without banning paraphrase."""

    source = _normalize_for_matching(source_text)
    flags: list[str] = []
    concrete_fields = [
        ("display name", profile.display_name),
        *[("employer", item.organization) for item in [*profile.experiences, *profile.projects]],
        *[("title", item.title) for item in [*profile.experiences, *profile.projects]],
        *[("date", value) for item in [*profile.experiences, *profile.projects] for value in (item.start_date, item.end_date)],
        *[("location", item.location) for item in [*profile.experiences, *profile.projects]],
        *[("education", value) for item in profile.education for value in (item.school, item.program, item.location)],
        *[("award", value) for item in profile.education for value in item.awards],
        *[("technology", skill.value) for category in profile.technical_skills for skill in category.skills],
        *[("technology", value) for item in [*profile.experiences, *profile.projects] for value in item.technologies],
    ]
    for label, value in concrete_fields:
        if value and not _fact_supported(value, source):
            flags.append(f"Unsupported extracted {label}: {value}")
    extracted_values = [
        profile.display_name,
        *[value for item in [*profile.experiences, *profile.projects] for value in (item.title, item.organization, item.start_date, item.end_date, item.location, *item.technologies)],
        *[value for item in profile.education for value in (item.school, item.program, item.location, *item.awards)],
        *[evidence.source_text for evidence in profile.evidence],
    ]
    extracted_text = " ".join(value for value in extracted_values if value)
    source_numbers = set(re.findall(r"\d+(?:\.\d+)?", source))
    for number in sorted({*re.findall(r"\d+(?:\.\d+)?", extracted_text)} - source_numbers):
        flags.append(f"Unsupported extracted number: {number}")
    return flags


_SKILL_HEADINGS = {"skills", "technical skills", "technical expertise", "technologies"}
_SECTION_HEADINGS = _SKILL_HEADINGS | {
    "experience", "experience", "projects", "education", "awards", "certifications", "summary"
}


def _extract_skill_categories(source_text: str) -> list[TechnicalSkillCategory]:
    lines = [line.strip() for line in source_text.replace("\r\n", "\n").split("\n")]
    in_skills = False
    categories: list[TechnicalSkillCategory] = []
    for line in lines:
        heading = line.casefold().rstrip(":")
        if heading in _SKILL_HEADINGS:
            in_skills = True
            continue
        if in_skills and heading in _SECTION_HEADINGS:
            break
        if not in_skills or not line or ":" not in line:
            continue
        label, values = line.split(":", 1)
        label = label.strip()
        values = values.strip()
        if not label or not values or len(label.split()) > 5:
            continue
        skills = [value.strip(" •–—-") for value in re.split(r",|;|\||\s+•\s+", values)]
        skills = [skill for skill in skills if skill]
        if skills:
            categories.append(TechnicalSkillCategory(category=label, values=skills))
    return categories


def _fact_supported(value: str, source: str) -> bool:
    normalized = _normalize_for_matching(value)
    if not normalized:
        return True
    if normalized in source:
        return True
    tokens = [token for token in normalized.split() if len(token) > 2]
    return bool(tokens) and sum(token in source for token in tokens) / len(tokens) >= 0.6


def _normalize_for_matching(value: str) -> str:
    return " ".join(value.casefold().split())


def _entry_bullet_texts(entry: ResumeItem) -> list[str]:
    values = [*entry.bullets, *entry.bullet_points, *([entry.description] if entry.description else [])]
    return [line for value in values for line in value.splitlines() if line.strip()]


def _usable_evidence_text(text: str) -> bool:
    value = text.strip()
    if not value or value.casefold().rstrip(":") in _NON_EVIDENCE_LABELS:
        return False
    if re.fullmatch(r"[-–—•|_ .]+", value):
        return False
    if "@" in value and len(value.split()) <= 4:
        return False
    if re.fullmatch(r"(?:\+?\d[\d ()-]{6,}|https?://\S+)", value):
        return False
    return len(value.split()) >= 2
