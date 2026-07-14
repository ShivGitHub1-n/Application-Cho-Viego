import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from resume_tailor.domain.models import (
    EducationRecord,
    EntityKind,
    EvidenceItem,
    MasterProfile,
    ResumeItem,
    TechnicalSkillCategory,
)
from resume_tailor.domain.profile_completeness import (
    validate_master_profile_completeness,
)


def _profile(**updates: object) -> MasterProfile:
    payload = {
        "id": "profile-safe",
        "user_id": "user-safe",
        "display_name": "Example Person",
        "contact": {"email": "private@example.test", "phone": "555-0100"},
        "education": [{"school": "Example Institute", "program": "Engineering"}],
        "experiences": [
            {"id": "entry-one", "title": "Engineer", "kind": "experience"}
        ],
        "evidence": [
            {
                "id": "evidence-one",
                "entity_id": "entry-one",
                "source_text": "Private evidence sentence must never enter diagnostics.",
            }
        ],
    }
    payload.update(updates)
    return MasterProfile.model_validate(payload)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(3.72, "3.72"), (4, "4"), ("3.72", "3.72"), ("3.72/4.00", "3.72/4.00")],
)
def test_gpa_accepts_numeric_and_preserves_reviewed_text(value: object, expected: str) -> None:
    assert EducationRecord(school="School", program="Program", gpa=value).gpa == expected


@pytest.mark.parametrize("value", [True, False, {"value": 3.72}, [3.72]])
def test_gpa_rejects_boolean_and_structured_values(value: object) -> None:
    with pytest.raises(ValidationError):
        EducationRecord(school="School", program="Program", gpa=value)


def test_incomplete_optional_metadata_is_safe_diagnostic_not_invalid() -> None:
    profile = _profile(declared_skills=["Legacy Tool"])
    report = validate_master_profile_completeness(profile)
    serialized = report.model_dump_json()

    assert report.valid is True
    assert report.technical_skills.legacy_flat_only is True
    assert "education[0].start_date" in report.incomplete_field_paths
    assert "private@example.test" not in serialized
    assert "555-0100" not in serialized
    assert "Private evidence sentence" not in serialized


def test_categorized_skills_and_duplicates_are_reported_deterministically() -> None:
    profile = _profile(
        technical_skills=[
            {"category": "Systems", "values": ["Python", "SPI"]},
            {"category": "Tools", "values": ["python", "Git"]},
        ]
    )
    report = validate_master_profile_completeness(profile)

    assert report.technical_skills.categorized_skills_present is True
    assert report.technical_skills.legacy_flat_only is False
    assert report.technical_skills.duplicate_skill_count == 1
    assert report.technical_skills.duplicate_skill_source_category_ids == [
        profile.technical_skills[1].id
    ]
    assert list(report.technical_skills.skill_count_per_category.values()) == [2, 1]


def test_invalid_skill_categories_or_evidence_relationships_are_rejected() -> None:
    with pytest.raises(ValidationError, match="non-empty label"):
        _profile(technical_skills=[{"category": " ", "values": ["Python"]}])
    with pytest.raises(ValidationError, match="no unique skills|empty skill"):
        _profile(technical_skills=[{"category": "Tools", "values": [" "]}])
    with pytest.raises(ValidationError, match="unknown entities"):
        _profile(
            evidence=[
                {"id": "orphan", "entity_id": "missing", "source_text": "Fact"}
            ]
        )


@pytest.mark.parametrize("duplicate_kind", ["entry", "evidence"])
def test_duplicate_stable_ids_are_rejected(duplicate_kind: str) -> None:
    if duplicate_kind == "entry":
        with pytest.raises(ValidationError, match="Duplicate resume entry IDs"):
            _profile(
                experiences=[
                    {"id": "same", "title": "One", "kind": "experience"},
                    {"id": "same", "title": "Two", "kind": "experience"},
                ],
                evidence=[],
            )
    else:
        with pytest.raises(ValidationError, match="Duplicate evidence IDs"):
            _profile(
                evidence=[
                    {"id": "same", "entity_id": "entry-one", "source_text": "One"},
                    {"id": "same", "entity_id": "entry-one", "source_text": "Two"},
                ]
            )


def test_education_coursework_is_canonical_and_cannot_diverge() -> None:
    canonical = _profile(
        education=[
            {
                "school": "Example Institute",
                "program": "Engineering",
                "relevant_coursework": ["Controls", "Circuits"],
            }
        ]
    )
    assert canonical.coursework == ["Controls", "Circuits"]

    migrated = _profile(coursework=["Legacy Course"])
    assert migrated.education[0].relevant_coursework == ["Legacy Course"]

    with pytest.raises(ValidationError, match="must match"):
        _profile(
            education=[
                {
                    "school": "Example Institute",
                    "program": "Engineering",
                    "relevant_coursework": ["Controls"],
                }
            ],
            coursework=["Different Course"],
        )


def test_fixture_profile_is_canonical_complete_and_evidence_valid() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "profile_completeness.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    profile = MasterProfile.model_validate(payload)
    report = validate_master_profile_completeness(profile)

    assert len(profile.technical_skills) == 4
    assert all(category.id and category.skills for category in profile.technical_skills)
    education = profile.education[0]
    assert education.start_date and education.expected_graduation_date
    assert education.location and education.awards and education.relevant_coursework
    assert all(item.organization and item.start_date and item.end_date for item in profile.experiences)
    assert sum(bool(item.location) for item in profile.experiences) == 3
    assert all(item.technology_label for item in profile.projects)
    assert profile.projects[1].award_or_placement == "3rd Place, Example Hacks"
    assert report.evidence_integrity.all_evidence_references_valid is True
    assert report.evidence_integrity.orphan_evidence_ids == []
    assert report.evidence_integrity.duplicate_entry_ids == []
    assert report.evidence_integrity.duplicate_evidence_ids == []
