"""Focused editing surfaces for the Career Profile workspace."""

from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
from typing import Any

from pydantic import ValidationError

from resume_tailor.application.profile_editor import (
    EntryKind,
    add_bullet,
    add_education,
    add_entry,
    add_skill_category,
    editor_state_to_profile,
    move_item,
    remove_bullet,
    remove_education,
    remove_entry,
    remove_skill_category,
)
from resume_tailor.domain.models import MasterProfile


def _widget_key(token: str, *parts: object) -> str:
    material = token + ":" + ":".join(map(str, parts))
    return "profile-editor-" + sha256(material.encode()).hexdigest()[:18]


def candidate_name_widget_key(token: str) -> str:
    """Return the source-scoped key for the focused candidate-name field."""

    return _widget_key(token, "display-name")


def editor_ui_identity(
    registry: dict[str, str], namespace: str, record: dict[str, Any]
) -> str:
    """Return a stable session-local key for a row without a canonical ID."""

    canonical_id = str(record.get("id") or "").strip()
    if canonical_id:
        return canonical_id
    ui_marker = str(record.get("_profile_editor_ui_id") or "")
    if ui_marker:
        return ui_marker
    registry_key = f"{namespace}:{id(record)}"
    if registry_key not in registry:
        registry[registry_key] = f"ui-{namespace}-{len(registry) + 1}"
    record["_profile_editor_ui_id"] = registry[registry_key]
    return registry[registry_key]


def next_link_ui_id(links: list[dict[str, Any]]) -> str:
    """Allocate a collision-free editor-only contact-link ID."""

    used = {str(item.get("id") or "") for item in links}
    index = 0
    while f"link-{index}" in used:
        index += 1
    return f"link-{index}"


def _comma_text(value: list[str]) -> str:
    return ", ".join(value)


def _render_personal_information(
    streamlit_module: Any, state: dict[str, Any], token: str, registry: dict[str, str]
) -> None:
    streamlit_module.subheader("Personal information")
    streamlit_module.caption(
        "Contact details are retained locally until you save the reviewed profile."
    )
    state["display_name"] = streamlit_module.text_input(
        "Candidate name",
        state.get("display_name", ""),
        key=candidate_name_widget_key(token),
    )
    contact = state.setdefault("contact", {})
    contact["phone"] = streamlit_module.text_input(
        "Phone", contact.get("phone", ""), key=_widget_key(token, "phone")
    )
    contact["email"] = streamlit_module.text_input(
        "Email", contact.get("email", ""), key=_widget_key(token, "email")
    )
    contact["location"] = streamlit_module.text_input(
        "Meaningful location",
        contact.get("location", ""),
        key=_widget_key(token, "location"),
    )
    if str(contact.get("location", "")).strip().casefold() == "canada":
        streamlit_module.warning(
            "A standalone country is not a meaningful resume location and is omitted on save."
        )
    streamlit_module.markdown("**Links**")
    for index, link in enumerate(list(contact.get("links", []))):
        link_key = editor_ui_identity(registry, "contact-link", link)
        label_column, value_column, remove_column = streamlit_module.columns((2, 4, 1))
        with label_column:
            link["label"] = streamlit_module.text_input(
                f"Link {index + 1} display text",
                link.get("label", ""),
                key=_widget_key(token, "link-label", link_key),
            )
        with value_column:
            link["value"] = streamlit_module.text_input(
                f"Link {index + 1} destination",
                link.get("value", ""),
                key=_widget_key(token, "link", link_key),
            )
        with remove_column:
            if streamlit_module.button(
                "Remove", key=_widget_key(token, "remove-link", link_key)
            ):
                contact["links"].pop(index)
                streamlit_module.rerun()
    if streamlit_module.button("Add link", key=_widget_key(token, "add-link")):
        links = contact.setdefault("links", [])
        links.append({"id": next_link_ui_id(links), "label": "", "value": ""})
        streamlit_module.rerun()


def _render_education(
    streamlit_module: Any, state: dict[str, Any], token: str, registry: dict[str, str]
) -> None:
    streamlit_module.subheader("Education")
    for index, record in enumerate(state.get("education", [])):
        record_id = editor_ui_identity(registry, "education", record)
        with streamlit_module.container(border=True):
            streamlit_module.markdown(f"**Education {index + 1}**")
            record["school"] = streamlit_module.text_input(
                "Institution",
                record.get("school", ""),
                key=_widget_key(token, "education", record_id, "school"),
            )
            record["program"] = streamlit_module.text_input(
                "Degree or program",
                record.get("program", ""),
                key=_widget_key(token, "education", record_id, "program"),
            )
            record["minor_or_specialization"] = streamlit_module.text_input(
                "Minor or specialization",
                record.get("minor_or_specialization", "") or "",
                key=_widget_key(token, "education", record_id, "minor"),
            )
            left, right = streamlit_module.columns(2)
            with left:
                record["start_date"] = streamlit_module.text_input(
                    "Start date",
                    record.get("start_date", ""),
                    key=_widget_key(token, "education", record_id, "start"),
                )
                record["graduation_date"] = streamlit_module.text_input(
                    "Graduation date",
                    record.get("graduation_date", ""),
                    key=_widget_key(token, "education", record_id, "graduation"),
                )
                record["location"] = streamlit_module.text_input(
                    "Location",
                    record.get("location", ""),
                    key=_widget_key(token, "education", record_id, "location"),
                )
            with right:
                record["expected_graduation_date"] = streamlit_module.text_input(
                    "Expected graduation date",
                    record.get("expected_graduation_date", ""),
                    key=_widget_key(token, "education", record_id, "expected"),
                )
                record["gpa"] = streamlit_module.text_input(
                    "GPA",
                    record.get("gpa", ""),
                    key=_widget_key(token, "education", record_id, "gpa"),
                )
                record["co_op_designation"] = streamlit_module.text_input(
                    "Co-op designation",
                    record.get("co_op_designation", ""),
                    key=_widget_key(token, "education", record_id, "coop"),
                )
            record["awards"] = streamlit_module.text_input(
                "Awards (comma-separated)",
                _comma_text(record.get("awards", [])),
                key=_widget_key(token, "education", record_id, "awards"),
            ).split(",")
            record["relevant_coursework"] = streamlit_module.text_input(
                "Relevant coursework",
                _comma_text(record.get("relevant_coursework", [])),
                key=_widget_key(token, "education", record_id, "coursework"),
            ).split(",")
            controls = streamlit_module.columns(3)
            with controls[0]:
                if index and streamlit_module.button(
                    "Move up", key=_widget_key(token, "education-up", record_id)
                ):
                    streamlit_module.session_state["profile_editor_state"] = move_item(
                        state, "education", index, -1
                    )
                    streamlit_module.rerun()
            with controls[1]:
                if index < len(state.get("education", [])) - 1 and streamlit_module.button(
                    "Move down", key=_widget_key(token, "education-down", record_id)
                ):
                    streamlit_module.session_state["profile_editor_state"] = move_item(
                        state, "education", index, 1
                    )
                    streamlit_module.rerun()
            with controls[2]:
                if streamlit_module.button(
                    "Remove education", key=_widget_key(token, "education-remove", record_id)
                ):
                    streamlit_module.session_state["profile_editor_state"] = remove_education(
                        state, index
                    )
                    streamlit_module.rerun()
    if streamlit_module.button("Add education", key=_widget_key(token, "education-add")):
        streamlit_module.session_state["profile_editor_state"] = add_education(state)
        streamlit_module.rerun()


def _render_entries(
    streamlit_module: Any,
    state: dict[str, Any],
    token: str,
    kind: EntryKind,
    heading: str,
) -> None:
    streamlit_module.subheader(heading)
    for index, entry in enumerate(state.get(kind, [])):
        entry_id = entry.get("id", f"{kind}-{index}")
        with streamlit_module.container(border=True):
            streamlit_module.markdown(f"**{heading[:-1]} {index + 1}**")
            entry["title"] = streamlit_module.text_input(
                "Name or title",
                entry.get("title", ""),
                key=_widget_key(token, kind, entry_id, "title"),
            )
            entry["organization"] = streamlit_module.text_input(
                "Employer or organization",
                entry.get("organization", ""),
                key=_widget_key(token, kind, entry_id, "organization"),
            )
            entry["subtitle"] = streamlit_module.text_input(
                "Subtitle",
                entry.get("subtitle", "") or "",
                key=_widget_key(token, kind, entry_id, "subtitle"),
            )
            dates = streamlit_module.columns(3)
            with dates[0]:
                entry["start_date"] = streamlit_module.text_input(
                    "Start date",
                    entry.get("start_date", ""),
                    key=_widget_key(token, kind, entry_id, "start"),
                )
            with dates[1]:
                entry["end_date"] = streamlit_module.text_input(
                    "End date",
                    entry.get("end_date", ""),
                    key=_widget_key(token, kind, entry_id, "end"),
                )
            with dates[2]:
                entry["location"] = streamlit_module.text_input(
                    "Location",
                    entry.get("location", ""),
                    key=_widget_key(token, kind, entry_id, "location"),
                )
            entry["technology_label"] = streamlit_module.text_input(
                "Technology label",
                entry.get("technology_label", "") or "",
                key=_widget_key(token, kind, entry_id, "technology-label"),
            )
            entry["award_or_placement"] = streamlit_module.text_input(
                "Award or placement",
                entry.get("award_or_placement", "") or "",
                key=_widget_key(token, kind, entry_id, "award-placement"),
            )
            entry["technologies"] = streamlit_module.text_input(
                "Technologies (comma-separated)",
                _comma_text(entry.get("technologies", [])),
                key=_widget_key(token, kind, entry_id, "technologies"),
            ).split(",")
            entry["capabilities"] = streamlit_module.text_input(
                "Capabilities (comma-separated)",
                _comma_text(entry.get("capabilities", [])),
                key=_widget_key(token, kind, entry_id, "capabilities"),
            ).split(",")
            entry["description"] = streamlit_module.text_area(
                "Description",
                entry.get("description", ""),
                key=_widget_key(token, kind, entry_id, "description"),
            )
            streamlit_module.markdown("**Evidence statements**")
            for bullet_index, bullet in enumerate(list(entry.get("bullets", []))):
                bullet_id = bullet.get("id", f"bullet-{bullet_index}")
                bullet["text"] = streamlit_module.text_area(
                    f"Evidence {bullet_index + 1}",
                    bullet.get("text", ""),
                    key=_widget_key(token, kind, entry_id, "bullet", bullet_id),
                )
                with streamlit_module.expander("Evidence details", expanded=False):
                    metadata = streamlit_module.columns(2)
                    with metadata[0]:
                        bullet["source_reference"] = streamlit_module.text_input(
                            "Source reference",
                            bullet.get("source_reference", "") or "",
                            key=_widget_key(token, kind, entry_id, "bullet-source", bullet_id),
                        )
                        bullet["technologies"] = streamlit_module.text_input(
                            "Evidence technologies",
                            _comma_text(bullet.get("technologies", [])),
                            key=_widget_key(token, kind, entry_id, "bullet-tech", bullet_id),
                        ).split(",")
                    with metadata[1]:
                        bullet["capabilities"] = streamlit_module.text_input(
                            "Evidence capabilities",
                            _comma_text(bullet.get("capabilities", [])),
                            key=_widget_key(
                                token, kind, entry_id, "bullet-capabilities", bullet_id
                            ),
                        ).split(",")
                        bullet["outcomes"] = streamlit_module.text_input(
                            "Evidence outcomes",
                            _comma_text(bullet.get("outcomes", [])),
                            key=_widget_key(token, kind, entry_id, "bullet-outcomes", bullet_id),
                        ).split(",")
                bullet["confirmed"] = streamlit_module.checkbox(
                    "Evidence is confirmed",
                    bool(bullet.get("confirmed", True)),
                    key=_widget_key(token, kind, entry_id, "bullet-confirmed", bullet_id),
                )
                if streamlit_module.button(
                    "Remove evidence",
                    key=_widget_key(token, kind, entry_id, "bullet-remove", bullet_id),
                ):
                    streamlit_module.session_state["profile_editor_state"] = remove_bullet(
                        state, kind, entry_id, bullet_id
                    )
                    streamlit_module.rerun()
            if streamlit_module.button(
                "Add evidence", key=_widget_key(token, kind, entry_id, "bullet-add")
            ):
                streamlit_module.session_state["profile_editor_state"] = add_bullet(
                    state, kind, entry_id
                )
                streamlit_module.rerun()
            controls = streamlit_module.columns(3)
            with controls[0]:
                if index and streamlit_module.button(
                    "Move up", key=_widget_key(token, kind, entry_id, "up")
                ):
                    streamlit_module.session_state["profile_editor_state"] = move_item(
                        state, kind, index, -1
                    )
                    streamlit_module.rerun()
            with controls[1]:
                if index < len(state.get(kind, [])) - 1 and streamlit_module.button(
                    "Move down", key=_widget_key(token, kind, entry_id, "down")
                ):
                    streamlit_module.session_state["profile_editor_state"] = move_item(
                        state, kind, index, 1
                    )
                    streamlit_module.rerun()
            with controls[2]:
                if streamlit_module.button(
                    f"Remove {heading[:-1].lower()}",
                    key=_widget_key(token, kind, entry_id, "remove"),
                ):
                    streamlit_module.session_state["profile_editor_state"] = remove_entry(
                        state, kind, entry_id
                    )
                    streamlit_module.rerun()
    if streamlit_module.button(
        f"Add {heading[:-1].lower()}", key=_widget_key(token, kind, "add")
    ):
        streamlit_module.session_state["profile_editor_state"] = add_entry(state, kind)
        streamlit_module.rerun()


def _render_skills(
    streamlit_module: Any, state: dict[str, Any], token: str, registry: dict[str, str]
) -> None:
    streamlit_module.subheader("Skills")
    state["declared_skills"] = streamlit_module.text_input(
        "Declared skills (comma-separated)",
        _comma_text(state.get("declared_skills", [])),
        key=_widget_key(token, "declared-skills"),
    ).split(",")
    state["coursework"] = streamlit_module.text_input(
        "Top-level coursework",
        _comma_text(state.get("coursework", [])),
        key=_widget_key(token, "coursework"),
    ).split(",")
    for category in list(state.get("technical_skills", [])):
        category_id = editor_ui_identity(registry, "skill-category", category)
        with streamlit_module.container(border=True):
            category["category"] = streamlit_module.text_input(
                "Category name",
                category.get("category", ""),
                key=_widget_key(token, "category", category_id, "label"),
            )
            for skill_index, skill in enumerate(list(category.get("skills", []))):
                skill_id = editor_ui_identity(registry, f"skill:{category_id}", skill)
                value_column, remove_column = streamlit_module.columns((5, 1))
                with value_column:
                    skill["value"] = streamlit_module.text_input(
                        "Skill",
                        skill.get("value", ""),
                        key=_widget_key(token, "category", category_id, "skill", skill_id),
                    )
                with remove_column:
                    if streamlit_module.button(
                        "Remove",
                        key=_widget_key(token, "category", category_id, "skill-remove", skill_id),
                    ):
                        category["skills"].pop(skill_index)
                        streamlit_module.rerun()
            if streamlit_module.button(
                "Add skill", key=_widget_key(token, "category", category_id, "skill-add")
            ):
                category.setdefault("skills", []).append({"id": None, "value": ""})
                streamlit_module.rerun()
            if streamlit_module.button(
                "Remove category", key=_widget_key(token, "category", category_id, "remove")
            ):
                streamlit_module.session_state["profile_editor_state"] = remove_skill_category(
                    state, category_id
                )
                streamlit_module.rerun()
            with streamlit_module.expander("Skill provenance", expanded=False):
                category["source_reference"] = streamlit_module.text_input(
                    "Category source reference",
                    category.get("source_reference", "") or "",
                    key=_widget_key(token, "category", category_id, "source-reference"),
                )
                for skill in list(category.get("skills", [])):
                    skill_id = editor_ui_identity(registry, f"skill:{category_id}", skill)
                    skill["source_reference"] = streamlit_module.text_input(
                        "Skill source reference",
                        skill.get("source_reference", "") or "",
                        key=_widget_key(
                            token, "category", category_id, "skill-source", skill_id
                        ),
                    )
    if streamlit_module.button("Add skill category", key=_widget_key(token, "category-add")):
        streamlit_module.session_state["profile_editor_state"] = add_skill_category(state)
        streamlit_module.rerun()


def _render_evidence_library(streamlit_module: Any, state: dict[str, Any]) -> None:
    streamlit_module.subheader("Evidence library")
    streamlit_module.caption(
        "Evidence remains reviewed source material. Generated documents never add evidence here."
    )
    records = [
        (kind, entry.get("title") or entry.get("organization") or entry.get("id"), bullet)
        for kind in ("experiences", "projects")
        for entry in state.get(kind, [])
        for bullet in entry.get("bullets", [])
    ]
    if not records:
        streamlit_module.info(
            "No evidence statements are available yet. Add evidence in an experience or project."
        )
        return
    for kind, owner, bullet in records:
        with streamlit_module.container(border=True):
            confirmation = "Confirmed" if bullet.get("confirmed", True) else "Needs review"
            streamlit_module.markdown(f"**{confirmation}** · {kind[:-1].title()} · {owner}")
            streamlit_module.write(bullet.get("text", ""))
            metadata = [
                value
                for value in (
                    bullet.get("source_reference"),
                    ", ".join(item for item in bullet.get("technologies", []) if item.strip()),
                    ", ".join(item for item in bullet.get("capabilities", []) if item.strip()),
                    ", ".join(item for item in bullet.get("outcomes", []) if item.strip()),
                )
                if value
            ]
            if metadata:
                streamlit_module.caption(" · ".join(metadata))


def render_profile_editor(
    streamlit_module: Any,
    profile: MasterProfile,
    section: str,
    *,
    on_save: Callable[[MasterProfile], bool],
    on_discard: Callable[[], None],
) -> None:
    """Render one focused profile section; mutations stay session-local until save."""

    state = streamlit_module.session_state["profile_editor_state"]
    registry = streamlit_module.session_state.setdefault("profile_editor_ui_identities", {})
    token = str(
        streamlit_module.session_state.get("profile_editor_source_key", f"saved:{profile.id}")
    )
    renderers: dict[str, Callable[[], None]] = {
        "Personal information": lambda: _render_personal_information(
            streamlit_module, state, token, registry
        ),
        "Education": lambda: _render_education(streamlit_module, state, token, registry),
        "Experiences": lambda: _render_entries(
            streamlit_module, state, token, "experiences", "Experiences"
        ),
        "Projects": lambda: _render_entries(streamlit_module, state, token, "projects", "Projects"),
        "Skills": lambda: _render_skills(streamlit_module, state, token, registry),
        "Evidence library": lambda: _render_evidence_library(streamlit_module, state),
    }
    renderer = renderers.get(section)
    review_fields = streamlit_module.session_state.get("profile_extraction_review_fields", ())
    if review_fields:
        count = len(review_fields)
        noun = "field" if count == 1 else "fields"
        streamlit_module.info(
            f"{count} {noun} need review before saving. Check the relevant section below."
        )
    if renderer is not None:
        renderer()
    errors = streamlit_module.session_state.get("profile_editor_errors", [])
    for error in errors:
        streamlit_module.error(error)
    actions = streamlit_module.columns((1, 1, 4))
    with actions[0]:
        save = streamlit_module.button(
            "Save reviewed profile", key="profile-save-edits", type="primary"
        )
    with actions[1]:
        discard = streamlit_module.button("Discard changes", key="profile-discard-edits")
    if discard:
        on_discard()
        streamlit_module.rerun()
    if save:
        try:
            edited_profile = editor_state_to_profile(state)
            if edited_profile.id != profile.id:
                raise ValueError("Profile ID cannot be changed in the editor.")
            if on_save(edited_profile):
                streamlit_module.session_state["profile_pending_section"] = "Reviewed profile"
                streamlit_module.rerun()
        except (ValidationError, ValueError, TypeError) as error:
            streamlit_module.session_state["profile_editor_errors"] = [str(error)]
            streamlit_module.error(f"Profile was not saved: {error}")


__all__ = [
    "candidate_name_widget_key",
    "editor_ui_identity",
    "next_link_ui_id",
    "render_profile_editor",
]
