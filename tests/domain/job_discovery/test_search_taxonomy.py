from __future__ import annotations

import pytest

from resume_tailor.domain.job_discovery.search_taxonomy import (
    explore_sector_query_terms,
    matches_explore_sector,
    matches_title_query,
)


def test_hardware_sector_has_specific_multidisciplinary_query_terms() -> None:
    terms = explore_sector_query_terms("Hardware / Systems Integration")

    assert {
        "Hardware Engineer",
        "Electrical Engineer",
        "Systems Engineer",
        "Systems Integration Engineer",
        "Hardware Test Engineer",
        "Electromechanical Engineer",
    }.issubset(terms)
    assert "Engineer" not in terms
    assert "Software Engineer" not in terms


def test_engineering_sector_matching_is_title_focused_and_keeps_mixed_roles() -> None:
    assert matches_explore_sector(
        "Robotics Software Integration Engineer", "Robotics / Autonomous Systems"
    )
    assert matches_explore_sector(
        "Embedded Software Engineer - Battery Management Systems",
        "Embedded Systems / Firmware",
    )
    assert matches_explore_sector(
        "Software Engineer, Hardware Test & Automation",
        "Hardware / Systems Integration",
    )
    assert not matches_explore_sector(
        "Recruiter", "Hardware / Systems Integration"
    )
    assert not matches_explore_sector(
        "Technical Program Manager, Hardware Robotics",
        "Hardware / Systems Integration",
    )
    assert not matches_explore_sector(
        "Mechanical Engineer", "Software Engineering"
    )


def test_title_query_does_not_match_role_phrases_found_only_in_description() -> None:
    assert matches_title_query(
        "Senior Embedded Systems Engineer", ["Embedded Systems Engineer"]
    )
    assert not matches_title_query("Recruiter", ["Software Engineer"])


@pytest.mark.parametrize(
    "title",
    [
        "Low-Latency Software Engineer",
        "Backend C++ Engineer",
        "Hosted Model Infrastructure Engineer",
        "Telemetry Platform Engineer",
        "High Performance Computing (HPC) Systems Engineer",
        "Network Software Integration Engineer",
        "Mission Integration Engineer, Network and Infrastructure",
        "Test Automation Engineer",
        "Site Reliability Engineer, GNC",
        "Sourcing Specialist, PCBA",
    ],
)
def test_generic_software_titles_do_not_enter_hardware_sector(title: str) -> None:
    assert not matches_explore_sector(title, "Hardware / Systems Integration")


@pytest.mark.parametrize(
    "title",
    [
        "Hardware Development Engineer",
        "Electrical Engineer",
        "Mechanical Design Engineer",
        "Systems Integration Engineer",
        "Avionics Engineer",
        "Hardware Reliability Engineer",
        "Integration & Test Engineer",
        "Electromechanical Engineer",
        "PCB / PCBA Design Engineer",
        "Wiring Harness Engineer",
        "Manufacturing Engineer",
        "Control Systems Engineer",
        "Systems Engineer, Space",
        "Open Architecture Systems Engineer, C2",
        "Fluids Systems Engineer",
        "Weapons Integration Engineer",
        "Integration Engineer (Starship)",
        "Integration Engineer, Heatshield",
        "Mission Integration Engineer, C3",
        "Systems Engineer, Air Defense",
        "Systems Engineer, Launched Effects",
        "Systems Engineer, Maritime",
        "Wireless Systems Engineer",
    ],
)
def test_hardware_sector_keeps_explicit_physical_system_titles(title: str) -> None:
    assert matches_explore_sector(title, "Hardware / Systems Integration")


@pytest.mark.parametrize(
    "title",
    [
        "Embedded Software Engineer - Power Systems",
        "Software Engineer, Hardware Test & Automation",
        "Robotics Software Integration Engineer",
        "Firmware Integration Engineer",
        "GNC Engineer, Flight Controls",
    ],
)
def test_hardware_sector_keeps_legitimate_mixed_titles(title: str) -> None:
    assert matches_explore_sector(title, "Hardware / Systems Integration")


def test_sector_overlaps_are_explicit_without_collapsing_families() -> None:
    expected = {
        "Mechanical Engineer": {"Hardware / Systems Integration"},
        "Embedded Software Engineer": {
            "Software Engineering",
            "Embedded Systems / Firmware",
        },
        "Robotics Software Engineer": {
            "Software Engineering",
            "Robotics / Autonomous Systems",
        },
        "Motion Planning Engineer": {"Robotics / Autonomous Systems"},
        "Manufacturing Automation Engineer": {
            "Hardware / Systems Integration",
            "Controls / Mechatronics",
        },
        "Test Automation Engineer": {"Testing / Verification"},
        "Hardware Test Automation Engineer": {
            "Hardware / Systems Integration",
            "Testing / Verification",
        },
        "Firmware Validation Engineer": {
            "Embedded Systems / Firmware",
            "Testing / Verification",
        },
        "Controls Verification Engineer": {
            "Controls / Mechatronics",
            "Testing / Verification",
        },
        "Mechatronics Test Engineer": {
            "Controls / Mechatronics",
            "Testing / Verification",
        },
    }
    sectors = (
        "Software Engineering",
        "Embedded Systems / Firmware",
        "Robotics / Autonomous Systems",
        "Hardware / Systems Integration",
        "Controls / Mechatronics",
        "Testing / Verification",
    )

    for title, intended in expected.items():
        actual = {sector for sector in sectors if matches_explore_sector(title, sector)}
        assert actual == intended


def test_software_sector_requires_explicit_software_title_evidence() -> None:
    assert matches_explore_sector("Backend Software Engineer", "Software Engineering")
    assert matches_explore_sector("Software Engineer, Supply Chain", "Software Engineering")
    assert matches_explore_sector("Platform Engineer", "Software Engineering")
    assert not matches_explore_sector("Mechanical Platform Engineer", "Software Engineering")
    assert not matches_explore_sector("Electrical Systems Engineer", "Software Engineering")
