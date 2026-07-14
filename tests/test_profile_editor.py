from __future__ import annotations

import json
from pathlib import Path

import pytest

from resume_tailor.application.profile_editor import (
    add_bullet,
    add_entry,
    add_skill_category,
    editor_state_to_profile,
    move_item,
    profile_to_editor_state,
    remove_bullet,
    remove_entry,
)
from resume_tailor.domain.models import MasterProfile


def _profile() -> MasterProfile:
    payload = json.loads(
        (Path(__file__).parent / "fixtures" / "profile_completeness.json").read_text(encoding="utf-8")
    )
    return MasterProfile.model_validate(payload)


def test_unchanged_realistic_profile_round_trips_without_losing_ids() -> None:
    profile = _profile()
    state = profile_to_editor_state(profile)
    edited = editor_state_to_profile(state)

    assert edited.model_dump(mode="json") == profile.model_dump(mode="json")
    assert [item.id for item in edited.evidence] == [item.id for item in profile.evidence]


def test_unchanged_legacy_bullet_fields_and_evidence_order_round_trip() -> None:
    profile = _profile().model_copy(deep=True)
    profile.experiences[0].bullets = ["Legacy bullet"]
    profile.experiences[1].bullet_points = ["Legacy point"]
    state = profile_to_editor_state(profile)

    edited = editor_state_to_profile(state)

    assert edited.model_dump(mode="json") == profile.model_dump(mode="json")
    assert [item.id for item in edited.evidence] == [item.id for item in profile.evidence]


def test_existing_evidence_edit_preserves_position_and_metadata() -> None:
    profile = _profile()
    state = profile_to_editor_state(profile)
    state["experiences"][1]["bullets"][0]["text"] = "Updated evidence text."

    edited = editor_state_to_profile(state)

    assert [item.id for item in edited.evidence] == [item.id for item in profile.evidence]
    assert edited.evidence[1].source_text == "Updated evidence text."
    assert edited.evidence[1].technologies == profile.evidence[1].technologies
    assert edited.evidence[1].capabilities == profile.evidence[1].capabilities


def test_add_remove_reorder_entries_and_nested_bullets() -> None:
    state = profile_to_editor_state(_profile())
    original_id = state["experiences"][0]["id"]
    state = add_entry(state, "experiences")
    new_id = state["experiences"][-1]["id"]
    assert new_id != original_id
    assert state["experiences"][-1]["bullets"] == []
    state = move_item(state, "experiences", len(state["experiences"]) - 1, -1)
    state = add_bullet(state, "experiences", new_id)
    new_entry = next(entry for entry in state["experiences"] if entry["id"] == new_id)
    bullet_id = new_entry["bullets"][-1]["id"]
    new_entry["bullets"][-1]["text"] = "Built a deterministic test fixture."
    profile = editor_state_to_profile(state)
    assert any(item.id == new_id for item in profile.experiences)
    assert any(item.id == bullet_id for item in profile.evidence)
    state = remove_bullet(state, "experiences", new_id, bullet_id)
    state = remove_entry(state, "experiences", new_id)
    assert all(item["id"] != new_id for item in state["experiences"])


def test_skill_cleanup_and_new_category_identifier() -> None:
    state = profile_to_editor_state(_profile())
    state["technical_skills"][0]["skills"].extend(
        [{"id": None, "value": " Python "}, {"id": None, "value": ""}]
    )
    state = add_skill_category(state)
    state["technical_skills"][-1]["category"] = "New Tools"
    state["technical_skills"][-1]["skills"] = [{"id": None, "value": "  Git  "}]
    profile = editor_state_to_profile(state)
    values = [skill.value for category in profile.technical_skills for skill in category.skills]
    assert values.count("Python") == 1
    assert "Git" in values
    assert profile.technical_skills[-1].id


def test_duplicate_skill_moved_to_later_category_keeps_one_skill_and_valid_categories() -> None:
    state = profile_to_editor_state(_profile())
    moved = state["technical_skills"][0]["skills"][0]
    state["technical_skills"][1]["skills"].append(
        {"id": None, "value": f"  {moved['value']}  ", "source_reference": "moved"}
    )

    profile = editor_state_to_profile(state)

    occurrences = [
        (category.id, skill.id, skill.value)
        for category in profile.technical_skills
        for skill in category.skills
        if skill.value.casefold() == moved["value"].casefold()
    ]
    assert len(occurrences) == 1
    assert occurrences[0][0] == profile.technical_skills[1].id
    assert occurrences[0][1] == moved["id"]


def test_existing_evidence_ids_are_preserved_and_blank_required_values_fail() -> None:
    profile = _profile()
    state = profile_to_editor_state(profile)
    evidence_id = state["experiences"][0]["bullets"][0]["id"]
    state["experiences"][0]["bullets"][0]["text"] = "Edited factual statement."
    edited = editor_state_to_profile(state)
    assert edited.evidence[0].id == evidence_id
    assert edited.evidence[0].source_text == "Edited factual statement."

    state["display_name"] = "  "
    with pytest.raises(ValueError, match="Candidate name"):
        editor_state_to_profile(state)

    state = profile_to_editor_state(profile)
    state["experiences"][0]["bullets"][0]["text"] = ""
    with pytest.raises(ValueError, match="blank bullet"):
        editor_state_to_profile(state)


def test_missing_optional_project_metadata_is_allowed_and_standalone_country_is_removed() -> None:
    state = profile_to_editor_state(_profile())
    state["contact"]["location"] = "Canada"
    state["projects"][0]["start_date"] = ""
    state["projects"][0]["location"] = ""
    profile = editor_state_to_profile(state)
    assert profile.contact.location is None
    assert profile.projects[0].start_date is None
    assert profile.projects[0].location is None
