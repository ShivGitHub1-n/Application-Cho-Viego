from __future__ import annotations

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
