from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import re
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import ValidationError

from resume_tailor.domain.models import (
    ContactInfo,
    EducationRecord,
    EntityKind,
    EvidenceItem,
    MasterProfile,
    ResumeItem,
    ReviewedTechnicalSkill,
    SkillNormalizationDecision,
    TechnicalSkillCategory,
)


EditorState = dict[str, Any]
EntryKind = Literal["experiences", "projects"]


def _new_id(namespace: str, value: str, used: set[str]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-") or "item"
    digest = sha256(f"{namespace}\0{value}\0{len(used)}".encode()).hexdigest()[:10]
    candidate = f"{namespace}-{slug}-{digest}"
    while candidate in used:
        digest = sha256(f"{candidate}\0next".encode()).hexdigest()[:10]
        candidate = f"{namespace}-{slug}-{digest}"
    used.add(candidate)
    return candidate


def _clean_optional(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _clean_list(values: Any) -> list[str]:
    if isinstance(values, str):
        values = values.split(",")
    if not isinstance(values, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        key = text.casefold()
        if text and key not in seen:
            result.append(text)
            seen.add(key)
    return result


def _contact_link_rows(links: list[str]) -> list[dict[str, str]]:
    return [{"id": f"link-{index}", "value": link} for index, link in enumerate(links)]


def _entry_state(profile: MasterProfile, kind: EntityKind) -> list[dict[str, Any]]:
    entries = profile.experiences if kind == EntityKind.EXPERIENCE else profile.projects
    evidence_by_entry: dict[str, list[dict[str, Any]]] = {}
    for item in profile.evidence:
        evidence_by_entry.setdefault(item.entity_id, []).append(
            {
                "id": item.id,
                "text": item.source_text,
                "source_reference": item.source_reference,
                "capabilities": list(item.capabilities),
                "technologies": list(item.technologies),
                "outcomes": list(item.outcomes),
                "confirmed": item.confirmed,
                "is_evidence": True,
            }
        )
    used_evidence = {item.id for item in profile.evidence}
    output: list[dict[str, Any]] = []
    for entry in entries:
        bullets = evidence_by_entry.get(entry.id, [])
        existing_bullet_texts = {str(item.get("text", "")).strip() for item in bullets}
        for legacy_field, legacy_values in (
            ("bullets", entry.bullets),
            ("bullet_points", entry.bullet_points),
        ):
            for legacy_text in legacy_values:
                text = str(legacy_text).strip()
                if text and text not in existing_bullet_texts:
                    bullets.append(
                        {
                            "id": _new_id(f"evidence-{entry.id}", text, used_evidence),
                            "text": text,
                            "source_reference": None,
                            "capabilities": [],
                            "technologies": [],
                            "outcomes": [],
                            "confirmed": True,
                            "is_evidence": False,
                            "legacy_field": legacy_field,
                        }
                    )
        if not bullets:
            legacy_bullets = [*entry.bullets, *entry.bullet_points]
            bullets = [
                {
                    "id": _new_id(f"evidence-{entry.id}", text, used_evidence),
                    "text": text,
                    "source_reference": None,
                    "capabilities": [],
                    "technologies": [],
                    "outcomes": [],
                    "confirmed": True,
                    "is_evidence": False,
                }
                for text in legacy_bullets
            ]
        output.append(
            {
                "id": entry.id,
                "title": entry.title,
                "kind": entry.kind.value,
                "organization": entry.organization or "",
                "start_date": entry.start_date or "",
                "end_date": entry.end_date or "",
                "location": entry.location or "",
                "subtitle": entry.subtitle or "",
                "technology_label": entry.technology_label or "",
                "award_or_placement": entry.award_or_placement or "",
                "technologies": list(entry.technologies),
                "capabilities": list(entry.capabilities),
                "description": entry.description or "",
                "bullets": bullets,
                "legacy_bullets": list(entry.bullets),
                "legacy_bullet_points": list(entry.bullet_points),
            }
        )
    return output


def profile_to_editor_state(profile: MasterProfile) -> EditorState:
    """Create a detached, widget-friendly state without changing the domain model."""

    return deepcopy(
        {
            "id": profile.id,
            "user_id": profile.user_id,
            "version": profile.version,
            "display_name": profile.display_name,
            "contact": {
                "email": profile.contact.email or "",
                "phone": profile.contact.phone or "",
                "location": profile.contact.location or "",
                "links": _contact_link_rows(profile.contact.links),
            },
            "education": [
                {
                    **record.model_dump(mode="json"),
                    "awards": list(record.awards),
                    "relevant_coursework": list(record.relevant_coursework),
                }
                for record in profile.education
            ],
            "experiences": _entry_state(profile, EntityKind.EXPERIENCE),
            "projects": _entry_state(profile, EntityKind.PROJECT),
            "technical_skills": [
                {
                    "id": category.id,
                    "category": category.category,
                    "source_reference": category.source_reference,
                    "skills": [skill.model_dump(mode="json") for skill in category.skills],
                }
                for category in profile.technical_skills
            ],
            "declared_skills": list(profile.declared_skills),
            "coursework": list(profile.coursework),
            "evidence": [item.model_dump(mode="json") for item in profile.evidence],
            "skill_normalization_decisions": [
                item.model_dump(mode="json") for item in profile.skill_normalization_decisions
            ],
        }
    )


def _education(state: EditorState) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for record in state.get("education", []):
        if not str(record.get("school", "")).strip() or not str(record.get("program", "")).strip():
            raise ValueError("Education entries require both institution and program.")
        records.append(
            {
                "school": str(record.get("school", "")).strip(),
                "program": str(record.get("program", "")).strip(),
                "minor_or_specialization": _clean_optional(record.get("minor_or_specialization")),
                "co_op_designation": _clean_optional(record.get("co_op_designation")),
                "start_date": _clean_optional(record.get("start_date")),
                "expected_graduation_date": _clean_optional(record.get("expected_graduation_date")),
                "graduation_date": _clean_optional(record.get("graduation_date")),
                "location": _clean_optional(record.get("location")),
                "gpa": _clean_optional(record.get("gpa")),
                "awards": _clean_list(record.get("awards", [])),
                "relevant_coursework": _clean_list(record.get("relevant_coursework", [])),
            }
        )
    return records


def _entries(state: EditorState, key: EntryKind, used_ids: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    entries: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    kind = EntityKind.EXPERIENCE if key == "experiences" else EntityKind.PROJECT
    for raw in state.get(key, []):
        supplied_id = str(raw.get("id", "")).strip()
        entry_id = supplied_id or _new_id(kind.value, str(raw.get("title", "entry")), used_ids)
        if supplied_id and entry_id in used_ids:
            raise ValueError(f"Duplicate entry ID: {entry_id}")
        used_ids.add(entry_id)
        if not entry_id.strip() or not str(raw.get("title", "")).strip():
            raise ValueError(f"{kind.title()} entries require a name or title.")
        legacy_bullets = [str(value) for value in raw.get("legacy_bullets", [])]
        entry = {
            "id": entry_id,
            "title": str(raw.get("title", "")).strip(),
            "kind": kind,
            "organization": _clean_optional(raw.get("organization")),
            "start_date": _clean_optional(raw.get("start_date")),
            "end_date": _clean_optional(raw.get("end_date")),
            "location": _clean_optional(raw.get("location")),
            "subtitle": _clean_optional(raw.get("subtitle")),
            "technology_label": _clean_optional(raw.get("technology_label")),
            "award_or_placement": _clean_optional(raw.get("award_or_placement")),
            "technologies": _clean_list(raw.get("technologies", [])),
            "capabilities": _clean_list(raw.get("capabilities", [])),
            "description": _clean_optional(raw.get("description")),
            "bullets": legacy_bullets,
            "bullet_points": [str(value) for value in raw.get("legacy_bullet_points", [])],
        }
        for raw_bullet in raw.get("bullets", []):
            text = str(raw_bullet.get("text", "") if isinstance(raw_bullet, dict) else raw_bullet).strip()
            if not text:
                raise ValueError(f"Entry {entry_id} contains a blank bullet.")
            if isinstance(raw_bullet, dict) and not raw_bullet.get("is_evidence", True):
                legacy_field = raw_bullet.get("legacy_field", "bullets")
                target = entry["bullet_points"] if legacy_field == "bullet_points" else entry["bullets"]
                if text not in target:
                    target.append(text)
                continue
            bullet_id = str(raw_bullet.get("id", "")).strip() if isinstance(raw_bullet, dict) else ""
            bullet_id = bullet_id or _new_id(f"evidence-{entry_id}", text, {item["id"] for item in evidence})
            if any(item["id"] == bullet_id for item in evidence):
                raise ValueError(f"Duplicate evidence ID: {bullet_id}")
            bullet = {
                "id": bullet_id,
                "entity_id": entry_id,
                "source_text": text,
                "source_reference": _clean_optional(raw_bullet.get("source_reference")) if isinstance(raw_bullet, dict) else None,
                "capabilities": _clean_list(raw_bullet.get("capabilities", [])) if isinstance(raw_bullet, dict) else [],
                "technologies": _clean_list(raw_bullet.get("technologies", [])) if isinstance(raw_bullet, dict) else [],
                "outcomes": _clean_list(raw_bullet.get("outcomes", [])) if isinstance(raw_bullet, dict) else [],
                "confirmed": bool(raw_bullet.get("confirmed", True)) if isinstance(raw_bullet, dict) else True,
                "is_evidence": True,
            }
            evidence.append(bullet)
        entries.append(entry)
    return entries, evidence


def editor_state_to_profile(state: EditorState) -> MasterProfile:
    """Normalize the UI transport and let MasterProfile enforce canonical validity."""

    used_ids: set[str] = set()
    experiences, experience_evidence = _entries(state, "experiences", used_ids)
    projects, project_evidence = _entries(state, "projects", used_ids)
    original_evidence = [
        item for item in state.get("evidence", []) if isinstance(item, dict) and item.get("id")
    ]
    edited_evidence = [*experience_evidence, *project_evidence]
    edited_by_id = {item["id"]: item for item in edited_evidence}
    serialized_evidence: list[dict[str, Any]] = []
    for original in original_evidence:
        evidence_id = str(original["id"])
        if evidence_id in edited_by_id:
            serialized_evidence.append(edited_by_id.pop(evidence_id))
    serialized_evidence.extend(edited_by_id.values())
    categories: list[dict[str, Any]] = []
    used_category_ids = {str(item.get("id")) for item in state.get("technical_skills", []) if item.get("id")}
    seen_skill_values: dict[str, tuple[int, dict[str, Any]]] = {}
    for raw in state.get("technical_skills", []):
        category_id = str(raw.get("id", "")).strip() or _new_id(
            "category", str(raw.get("category", "category")), used_category_ids
        )
        used_category_ids.add(category_id)
        cleaned_skills: list[dict[str, Any]] = []
        for skill in raw.get("skills", []):
            if not isinstance(skill, dict):
                continue
            value = str(skill.get("value", "")).strip()
            value_key = value.casefold()
            if not value:
                continue
            raw_skill_id = skill.get("id")
            supplied_skill_id = str(raw_skill_id).strip() if raw_skill_id else None
            normalized_skill = {
                "id": supplied_skill_id,
                "value": value,
                "source_reference": skill.get("source_reference"),
            }
            previous = seen_skill_values.get(value_key)
            if previous is not None:
                previous_category_index, previous_skill = previous
                if previous_category_index == len(categories):
                    continue
                previous_category = categories[previous_category_index]
                previous_category["skills"] = [
                    item for item in previous_category["skills"] if item is not previous_skill
                ]
                if normalized_skill["id"] is None:
                    normalized_skill["id"] = previous_skill.get("id")
            cleaned_skills.append(normalized_skill)
            seen_skill_values[value_key] = (len(categories), normalized_skill)
        categories.append(
            {
                "id": category_id,
                "category": str(raw.get("category", "")).strip(),
                "skills": cleaned_skills,
                "source_reference": _clean_optional(raw.get("source_reference")),
            }
        )
    links = [
        str(item.get("value", "")).strip()
        for item in state.get("contact", {}).get("links", [])
        if isinstance(item, dict) and str(item.get("value", "")).strip()
    ]
    invalid_links = [link for link in links if not editor_link_is_structurally_valid(link)]
    if invalid_links:
        raise ValueError(f"Invalid profile link: {invalid_links[0]}")
    display_name = str(state.get("display_name", "")).strip()
    if not display_name:
        raise ValueError("Candidate name is required.")
    location = _clean_optional(state.get("contact", {}).get("location"))
    if location and location.casefold() == "canada":
        location = None
    payload = {
        "id": str(state.get("id", "")).strip(),
        "user_id": str(state.get("user_id", "")).strip(),
        "version": int(state.get("version", 1)),
        "display_name": str(state.get("display_name", "")).strip(),
        "contact": {
            "email": _clean_optional(state.get("contact", {}).get("email")),
            "phone": _clean_optional(state.get("contact", {}).get("phone")),
            "location": location,
            "links": links,
        },
        "education": _education(state),
        "experiences": experiences,
        "projects": projects,
        "technical_skills": categories,
        "declared_skills": _clean_list(state.get("declared_skills", [])),
        "coursework": _clean_list(state.get("coursework", [])),
        "evidence": serialized_evidence,
        "skill_normalization_decisions": state.get("skill_normalization_decisions", []),
    }
    return MasterProfile.model_validate(payload)


def profile_change_fingerprint(profile: MasterProfile) -> str:
    return profile.model_dump_json()


def add_entry(state: EditorState, kind: EntryKind) -> EditorState:
    updated = deepcopy(state)
    used = {str(item.get("id")) for item in [*updated.get("experiences", []), *updated.get("projects", [])]}
    title = "New experience" if kind == "experiences" else "New project"
    entry_id = _new_id("experience" if kind == "experiences" else "project", title, used)
    updated.setdefault(kind, []).append({"id": entry_id, "title": title, "kind": "experience" if kind == "experiences" else "project", "bullets": []})
    return updated


def remove_entry(state: EditorState, kind: EntryKind, entry_id: str) -> EditorState:
    updated = deepcopy(state)
    updated[kind] = [item for item in updated.get(kind, []) if item.get("id") != entry_id]
    return updated


def move_item(state: EditorState, key: str, index: int, direction: int) -> EditorState:
    updated = deepcopy(state)
    items = updated.get(key, [])
    target = index + direction
    if 0 <= index < len(items) and 0 <= target < len(items):
        items[index], items[target] = items[target], items[index]
    return updated


def add_bullet(state: EditorState, kind: EntryKind, entry_id: str) -> EditorState:
    updated = deepcopy(state)
    used = {str(bullet.get("id")) for entry in [*updated.get("experiences", []), *updated.get("projects", [])] for bullet in entry.get("bullets", []) if isinstance(bullet, dict)}
    for entry in updated.get(kind, []):
        if entry.get("id") == entry_id:
            bullet_id = _new_id(f"evidence-{entry_id}", "new bullet", used)
            entry.setdefault("bullets", []).append(
                {"id": bullet_id, "text": "", "confirmed": True, "is_evidence": True}
            )
            break
    return updated


def remove_bullet(state: EditorState, kind: EntryKind, entry_id: str, bullet_id: str) -> EditorState:
    updated = deepcopy(state)
    for entry in updated.get(kind, []):
        if entry.get("id") == entry_id:
            entry["bullets"] = [bullet for bullet in entry.get("bullets", []) if bullet.get("id") != bullet_id]
    return updated


def add_education(state: EditorState) -> EditorState:
    updated = deepcopy(state)
    updated.setdefault("education", []).append({"school": "", "program": "", "awards": [], "relevant_coursework": []})
    return updated


def remove_education(state: EditorState, index: int) -> EditorState:
    updated = deepcopy(state)
    if 0 <= index < len(updated.get("education", [])):
        updated["education"].pop(index)
    return updated


def add_skill_category(state: EditorState) -> EditorState:
    updated = deepcopy(state)
    used = {str(item.get("id")) for item in updated.get("technical_skills", [])}
    updated.setdefault("technical_skills", []).append({"id": _new_id("category", "new category", used), "category": "", "skills": []})
    return updated


def remove_skill_category(state: EditorState, category_id: str) -> EditorState:
    updated = deepcopy(state)
    updated["technical_skills"] = [item for item in updated.get("technical_skills", []) if item.get("id") != category_id]
    return updated


def editor_link_is_structurally_valid(value: str) -> bool:
    text = value.strip()
    if not text:
        return True
    parsed = urlparse(text if "://" in text else f"https://{text}")
    return bool(parsed.netloc) and " " not in text


def unknown_profile_fields(payload: dict[str, Any]) -> list[str]:
    nested_models: dict[str, tuple[type[Any], bool]] = {
        "contact": (ContactInfo, False),
        "education": (EducationRecord, True),
        "experiences": (ResumeItem, True),
        "projects": (ResumeItem, True),
        "technical_skills": (TechnicalSkillCategory, True),
        "evidence": (EvidenceItem, True),
        "skill_normalization_decisions": (SkillNormalizationDecision, True),
    }
    unknown: list[str] = []

    def visit(value: Any, model: type[Any], path: str) -> None:
        if not isinstance(value, dict):
            return
        for key in set(value) - set(model.model_fields):
            unknown.append(f"{path}.{key}" if path else key)
        if model is MasterProfile:
            for key, (child_model, is_list) in nested_models.items():
                if key not in value:
                    continue
                child_values = value[key] if is_list else [value[key]]
                for index, child in enumerate(child_values):
                    child_path = f"{path}.{key}[{index}]" if is_list else f"{path}.{key}"
                    visit(child, child_model, child_path)
        elif model is TechnicalSkillCategory:
            for index, child in enumerate(value.get("skills", [])):
                visit(child, ReviewedTechnicalSkill, f"{path}.skills[{index}]")

    visit(payload, MasterProfile, "")
    return sorted(unknown)
