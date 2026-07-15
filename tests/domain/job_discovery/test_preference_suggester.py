import json
import os
import subprocess
import sys
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from resume_tailor.domain.job_discovery.models import JobLevel
from resume_tailor.domain.job_discovery.preferences import (
    DeterministicJobSearchPreferenceSuggester,
    _unique_sorted,
)
from resume_tailor.domain.models import MasterProfile, RoleFamily

WHEN = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


def _profile() -> MasterProfile:
    return MasterProfile(
        id="profile-1",
        user_id="user-1",
        display_name="Candidate",
        contact={"location": "Toronto, ON, Canada"},
        education=[
            {
                "school": "University of Toronto",
                "program": "Bachelor of Applied Science in Mechanical Engineering",
                "expected_graduation_date": "April 2029",
                "relevant_coursework": ["Embedded Systems"],
            }
        ],
        experiences=[
            {
                "id": "experience-autonomy",
                "title": "Autonomous Driving Engineer",
                "kind": "experience",
                "technologies": ["ROS 2", "OpenCV"],
                "capabilities": ["autonomous systems", "computer vision"],
            },
            {
                "id": "experience-software",
                "title": "Software Engineering Intern",
                "kind": "experience",
                "technologies": ["Python"],
                "capabilities": ["data engineering"],
            },
        ],
        projects=[
            {
                "id": "project-robotics",
                "title": "Robotics Arm",
                "kind": "project",
                "technologies": ["C++"],
                "capabilities": ["robotics", "kinematics"],
            }
        ],
        technical_skills=[{"category": "Languages", "values": ["Python", "C++"]}],
        evidence=[
            {
                "id": "evidence-autonomy",
                "entity_id": "experience-autonomy",
                "source_text": (
                    "Built an autonomous driving perception pipeline with ROS 2 and "
                    "OpenCV."
                ),
                "technologies": ["ROS 2", "OpenCV"],
                "capabilities": ["autonomous driving", "computer vision"],
                "confirmed": True,
            },
            {
                "id": "evidence-robotics",
                "entity_id": "project-robotics",
                "source_text": "Designed a robotic arm using kinematics and C++.",
                "technologies": ["C++"],
                "capabilities": ["robotics", "kinematics"],
                "confirmed": True,
            },
        ],
    )


def test_suggestion_is_reviewable_and_profile_derived():
    suggestion = DeterministicJobSearchPreferenceSuggester().suggest(_profile(), generated_at=WHEN)

    assert suggestion.profile_id == "profile-1"
    assert suggestion.generated_at == WHEN
    assert suggestion.role_family_priority[0] is RoleFamily.AUTONOMOUS_SYSTEMS
    assert suggestion.target_titles == [
        "Autonomous Driving Engineer",
        "Robotics Arm",
        "Software Engineering Intern",
    ]
    assert "Autonomous Vehicle Engineer" in suggestion.related_title_variants
    assert "autonomous driving" in suggestion.technical_themes
    assert "robotics" in suggestion.career_interests
    assert JobLevel.INTERN in suggestion.job_levels
    assert JobLevel.ENTRY in suggestion.job_levels
    assert suggestion.locations[0].raw == "Toronto, ON, Canada"
    assert suggestion.locations[0].parseable is False
    assert suggestion.rationale


def test_suggestion_is_deterministic_for_same_profile_and_timestamp():
    suggester = DeterministicJobSearchPreferenceSuggester()

    first = suggester.suggest(_profile(), generated_at=WHEN)
    second = suggester.suggest(_profile(), generated_at=WHEN)

    assert first == second


def test_suggestion_deduplicates_values_case_insensitively_using_first_spelling():
    assert _unique_sorted(["Python", "python", "ROS 2", "ros 2", "C++"]) == [
        "C++",
        "Python",
        "ROS 2",
    ]


def test_suggestion_order_is_stable_across_python_hash_seeds():
    script = (
        "import json; "
        "from resume_tailor.domain.job_discovery.preferences import _unique_sorted; "
        "print(json.dumps(_unique_sorted(['Python', 'python', 'ROS 2', 'ros 2', 'C++'])))"
    )
    project_root = Path(__file__).resolve().parents[3]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root / "src")
    outputs = []
    for seed in ("1", "2"):
        child_env = {**env, "PYTHONHASHSEED": seed}
        completed = subprocess.run(
            [sys.executable, "-c", script],
            check=True,
            capture_output=True,
            text=True,
            cwd=project_root,
            env=child_env,
        )
        outputs.append(json.loads(completed.stdout))

    assert outputs == [["C++", "Python", "ROS 2"], ["C++", "Python", "ROS 2"]]


def test_minimal_profile_returns_conservative_defaults_without_optional_evidence():
    profile = MasterProfile(id="minimal", user_id="user-1", display_name="Candidate")

    suggestion = DeterministicJobSearchPreferenceSuggester().suggest(
        profile,
        generated_at=WHEN,
    )

    assert suggestion.role_family_priority == []
    assert suggestion.target_titles == []
    assert suggestion.technical_themes == []
    assert suggestion.locations == []
    assert suggestion.preferred_companies == []
    assert suggestion.job_levels == [JobLevel.ENTRY]


def test_unconfirmed_evidence_is_excluded_from_suggested_themes_and_priorities():
    profile = MasterProfile(
        id="profile-unconfirmed",
        user_id="user-1",
        display_name="Candidate",
        experiences=[{"id": "entry-1", "title": "Research Assistant", "kind": "experience"}],
        evidence=[
            {
                "id": "unconfirmed-1",
                "entity_id": "entry-1",
                "source_text": "Built a quantum robotics system.",
                "technologies": ["quantum computing"],
                "capabilities": ["robotics"],
                "confirmed": False,
            }
        ],
    )

    suggestion = DeterministicJobSearchPreferenceSuggester().suggest(
        profile,
        generated_at=WHEN,
    )

    assert "quantum computing" not in suggestion.technical_themes
    assert RoleFamily.ROBOTICS_MECHATRONICS not in suggestion.role_family_priority


def test_suggester_does_not_mutate_input_profile():
    profile = _profile()
    before = deepcopy(profile.model_dump(mode="python"))

    DeterministicJobSearchPreferenceSuggester().suggest(profile, generated_at=WHEN)

    assert profile.model_dump(mode="python") == before
