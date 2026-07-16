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
    _RELATED_TITLE_VARIANTS,
    _interleaved_family_title_candidates,
    _target_title_count,
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
            },
            {
                "id": "project-expense",
                "title": "Crest - AI-Powered Expense Intelligence Platform",
                "kind": "project",
                "technologies": ["Python"],
            },
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
    assert "Autonomous Systems Engineer" in suggestion.target_titles
    assert "Autonomous Driving Engineer" not in suggestion.target_titles
    assert "Crest - AI-Powered Expense Intelligence Platform" not in suggestion.target_titles
    assert len(suggestion.target_titles) < len(suggestion.related_title_variants)
    assert len(suggestion.target_titles) <= 6
    assert "Autonomous Vehicle Engineer" in suggestion.related_title_variants
    assert "autonomous driving" in suggestion.technical_themes
    assert "robotics" in suggestion.career_interests
    assert JobLevel.INTERN in suggestion.job_levels
    assert JobLevel.ENTRY in suggestion.job_levels
    assert suggestion.locations[0].raw == "Toronto, ON, Canada"
    assert suggestion.locations[0].parseable is False
    assert suggestion.rationale


def test_composite_experience_titles_keep_only_occupational_segments():
    profile = MasterProfile(
        id="composite",
        user_id="user-1",
        display_name="Candidate",
        experiences=[
            {
                "id": "digital",
                "title": "Digital Engineering Intern | LLMs, GenAI",
                "kind": "experience",
                "technologies": ["Python"],
                "capabilities": ["software engineering"],
            },
            {
                "id": "hardware",
                "title": "Principal Hardware Engineer | Embedded Systems, Mechatronics",
                "kind": "experience",
                "technologies": ["STM32"],
                "capabilities": ["embedded systems"],
            },
            {
                "id": "rd",
                "title": "R&D Hardware Engineer | Mechanical Integration, Hardware Design",
                "kind": "experience",
                "capabilities": ["robotics", "hardware integration"],
            },
            {
                "id": "software",
                "title": "Software Engineering Intern | Python, Pandas, Power BI",
                "kind": "experience",
                "technologies": ["Pandas"],
                "capabilities": ["data engineering"],
            },
        ],
    )

    suggestion = DeterministicJobSearchPreferenceSuggester().suggest(
        profile, generated_at=WHEN
    )

    assert set(suggestion.target_titles).issubset(suggestion.related_title_variants)
    assert any(
        title in suggestion.target_titles
        for title in ("Software Engineer", "Embedded Systems Engineer", "Robotics Engineer")
    )
    assert len(suggestion.target_titles) < len(suggestion.related_title_variants)
    assert "LLMs, GenAI" not in suggestion.target_titles
    assert "Python, Pandas, Power BI" not in suggestion.target_titles


def test_project_only_profile_gets_bounded_family_title_candidates():
    profile = MasterProfile(
        id="project-only",
        user_id="user-1",
        display_name="Candidate",
        projects=[
            {
                "id": "robotics-project",
                "title": "Autonomous Robot Navigation Platform",
                "kind": "project",
                "technologies": ["ROS 2"],
                "capabilities": ["autonomous systems", "robotics"],
            }
        ],
    )

    suggestion = DeterministicJobSearchPreferenceSuggester().suggest(
        profile, generated_at=WHEN
    )

    assert suggestion.target_titles
    assert "Autonomous Systems Engineer" in suggestion.target_titles
    assert "Robotics Software Engineer" in suggestion.target_titles
    assert "Autonomous Robot Navigation Platform" not in suggestion.target_titles


def test_different_supported_family_evidence_changes_target_shortlist():
    suggester = DeterministicJobSearchPreferenceSuggester()
    robotics = MasterProfile(
        id="robotics",
        user_id="user-1",
        display_name="Candidate",
        projects=[
            {
                "id": "robotics-project",
                "title": "Robot Manipulator Control",
                "kind": "project",
                "technologies": ["ROS 2"],
                "capabilities": ["robotics", "kinematics", "actuator control"],
            }
        ],
    )
    software = MasterProfile(
        id="software",
        user_id="user-1",
        display_name="Candidate",
        projects=[
            {
                "id": "software-project",
                "title": "Data Pipeline Service",
                "kind": "project",
                "technologies": ["Python", "FastAPI"],
                "capabilities": ["data engineering", "backend services"],
            }
        ],
    )

    robotics_suggestion = suggester.suggest(robotics, generated_at=WHEN)
    software_suggestion = suggester.suggest(software, generated_at=WHEN)

    assert robotics_suggestion.role_family_priority != software_suggestion.role_family_priority
    assert robotics_suggestion.target_titles != software_suggestion.target_titles


def test_target_shortlist_is_strictly_smaller_and_interleaves_supported_families():
    families = [RoleFamily.AUTONOMOUS_SYSTEMS, RoleFamily.ROBOTICS_MECHATRONICS]
    candidates = _interleaved_family_title_candidates(families)

    assert candidates[0] in _RELATED_TITLE_VARIANTS[families[0]]
    assert candidates[1] in _RELATED_TITLE_VARIANTS[families[1]]
    assert candidates[2] in _RELATED_TITLE_VARIANTS[families[0]]
    assert candidates[3] in _RELATED_TITLE_VARIANTS[families[1]]
    assert _target_title_count(1) == 1
    assert _target_title_count(2) == 1
    assert _target_title_count(6) == 5
    assert _target_title_count(7) == 6
    assert _target_title_count(20) == 6


def test_clean_experience_titles_do_not_suppress_role_candidates_or_admit_skill_phrases():
    profile = MasterProfile(
        id="clean-titles",
        user_id="user-1",
        display_name="Candidate",
        experiences=[
            {
                "id": "role",
                "title": "Mechanical Design Engineer",
                "kind": "experience",
                "capabilities": ["robotics", "mechanical integration"],
            },
            {
                "id": "skills",
                "title": "Python, Pandas, Power BI",
                "kind": "experience",
                "technologies": ["Python", "Pandas"],
            },
        ],
    )

    suggestion = DeterministicJobSearchPreferenceSuggester().suggest(
        profile, generated_at=WHEN
    )

    assert set(suggestion.target_titles).issubset(suggestion.related_title_variants)
    assert 0 < len(suggestion.target_titles) <= 6
    assert len(suggestion.target_titles) < len(suggestion.related_title_variants)
    assert "Python, Pandas, Power BI" not in suggestion.target_titles
    assert "Mechanical Design Engineer" not in suggestion.target_titles

    represented_families = sum(
        any(title in _RELATED_TITLE_VARIANTS[family] for title in suggestion.target_titles)
        for family in suggestion.role_family_priority
    )
    if len(suggestion.role_family_priority) > 1 and len(suggestion.target_titles) > 1:
        assert represented_families > 1


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
