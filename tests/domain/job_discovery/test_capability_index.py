from __future__ import annotations

import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

from resume_tailor.domain.job_discovery.capabilities import (
    ProfileCapabilityIndexBuilder,
)
from resume_tailor.domain.models import MasterProfile


def _profile() -> MasterProfile:
    return MasterProfile(
        id="profile-1",
        user_id="user-1",
        display_name="Candidate",
        declared_skills=["Unsupported Declared Skill"],
        education=[
            {
                "school": "University of Toronto",
                "program": "Bachelor of Applied Science in Mechanical Engineering",
                "relevant_coursework": ["Embedded Systems", "Control Systems"],
            }
        ],
        experiences=[
            {
                "id": "experience-1",
                "title": "Software Engineering Intern",
                "kind": "experience",
                "technologies": ["Python", "ROS 2"],
                "capabilities": ["data engineering"],
            }
        ],
        projects=[
            {
                "id": "project-1",
                "title": "Robotics Arm",
                "kind": "project",
                "technologies": ["C++"],
                "capabilities": ["robotics"],
            }
        ],
        technical_skills=[
            {
                "id": "category-languages",
                "category": "Languages",
                "skills": [{"id": "skill-python", "value": "Python"}],
            }
        ],
        evidence=[
            {
                "id": "evidence-1",
                "entity_id": "experience-1",
                "source_text": "Built a Python data pipeline with ROS 2.",
                "technologies": ["Python", "ROS 2"],
                "capabilities": ["data engineering"],
                "confirmed": True,
            },
            {
                "id": "evidence-unconfirmed",
                "entity_id": "experience-1",
                "source_text": "Built an unsupported quantum system.",
                "technologies": ["quantum computing"],
                "capabilities": ["quantum systems"],
                "confirmed": False,
            },
        ],
    )


def test_minimal_profile_returns_empty_capability_index():
    index = ProfileCapabilityIndexBuilder().build(
        MasterProfile(id="minimal", user_id="user-1", display_name="Candidate")
    )

    assert index.terms == {}


def test_confirmed_and_contextual_sources_are_indexed_with_traceability():
    index = ProfileCapabilityIndexBuilder().build(_profile())

    python_sources = index.terms["python"]
    assert any(
        source.source_id == "evidence-1"
        and source.source_type == "confirmed_evidence"
        and source.demonstrated
        and source.source_text == "Built a Python data pipeline with ROS 2."
        for source in python_sources
    )
    assert any(
        source.source_id == "project-1"
        and source.source_type == "resume_item"
        and source.demonstrated
        for source in index.terms["c++"]
    )
    assert any(
        source.source_type == "coursework"
        and not source.demonstrated
        for source in index.terms["embedded systems"]
    )
    assert any(
        source.source_type == "education"
        and not source.demonstrated
        for source in index.terms["bachelor of applied science in mechanical engineering"]
    )


def test_unconfirmed_evidence_and_legacy_declared_skills_are_excluded():
    index = ProfileCapabilityIndexBuilder().build(_profile())

    assert "quantum computing" not in index.terms
    assert "quantum systems" not in index.terms
    assert "unsupported declared skill" not in index.terms


def test_reviewed_skills_are_distinct_from_demonstrated_experience():
    index = ProfileCapabilityIndexBuilder().build(_profile())

    reviewed = [
        source
        for source in index.terms["python"]
        if source.source_type == "reviewed_skill"
    ]
    assert reviewed
    assert all(not source.demonstrated for source in reviewed)
    assert any(
        source.source_type == "confirmed_evidence" and source.demonstrated
        for source in index.terms["python"]
    )


def test_capability_terms_are_normalized_and_case_insensitive_duplicates_preserve_provenance():
    profile = _profile().model_copy(deep=True)
    profile.experiences[0].technologies = ["python", "PYTHON", "cpp"]
    profile.experiences[0].capabilities = ["Data-Engineering"]

    index = ProfileCapabilityIndexBuilder().build(profile)

    assert set(index.terms) >= {"python", "c++", "data engineering"}
    assert len(index.terms["python"]) == 3
    assert {source.source_type for source in index.terms["python"]} == {
        "confirmed_evidence",
        "resume_item",
        "reviewed_skill",
    }


def test_capability_index_is_deterministic_does_not_mutate_profile_or_use_repository():
    profile = _profile()
    before = deepcopy(profile.model_dump(mode="python"))
    builder = ProfileCapabilityIndexBuilder()

    assert builder.build(profile) == builder.build(profile)
    assert profile.model_dump(mode="python") == before

    script = (
        "import json; "
        "from resume_tailor.domain.job_discovery.capabilities import "
        "ProfileCapabilityIndexBuilder; "
        "from resume_tailor.domain.models import MasterProfile; "
        "profile = MasterProfile(id='p', user_id='u', display_name='C', "
        "experiences=[{'id':'e','title':'Engineer','kind':'experience',"
        "'technologies':['Python','C++']}]); "
        "print(json.dumps(ProfileCapabilityIndexBuilder().build(profile).model_dump(), "
        "sort_keys=True))"
    )
    project_root = Path(__file__).resolve().parents[3]
    env = {**os.environ, "PYTHONPATH": str(project_root / "src")}
    outputs = []
    for seed in ("1", "2"):
        child = subprocess.run(
            [sys.executable, "-c", script],
            check=True,
            capture_output=True,
            text=True,
            cwd=project_root,
            env={**env, "PYTHONHASHSEED": seed},
        )
        outputs.append(json.loads(child.stdout))
    assert outputs[0] == outputs[1]
    assert profile.model_dump(mode="python") == before
