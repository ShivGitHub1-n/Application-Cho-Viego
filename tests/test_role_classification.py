import pytest

from resume_tailor.domain.models import JobPosting, RoleFamily
from resume_tailor.infrastructure.optimization import MultiRoleOpportunityAnalyzer


@pytest.fixture
def analyzer() -> MultiRoleOpportunityAnalyzer:
    return MultiRoleOpportunityAnalyzer()


@pytest.mark.parametrize(
    ("title", "description", "expected_family"),
    [
        (
            "Embedded Systems Developer",
            "Build C and C++ device drivers for microcontrollers with RTOS scheduling and SPI, I2C, and UART interfaces.",
            RoleFamily.EMBEDDED_FIRMWARE,
        ),
        (
            "Robotics Integration Engineer",
            "Integrate robots and end-of-arm tooling, develop controls and perception, and validate mechanical and electrical sensor systems.",
            RoleFamily.ROBOTICS_MECHATRONICS,
        ),
        (
            "Data Analytics Engineer",
            "Build SQL ETL pipelines, data validation workflows, and dashboards for operational analytics.",
            RoleFamily.SOFTWARE_DATA_ENGINEERING,
        ),
    ],
)
def test_unambiguous_role_fixtures_have_exact_categories(
    analyzer: MultiRoleOpportunityAnalyzer,
    title: str,
    description: str,
    expected_family: RoleFamily,
) -> None:
    result = analyzer.analyze(JobPosting(id="synthetic-role", title=title, description=description))

    assert result.supported is True
    assert result.role_family == expected_family.value
    assert result.signals


def test_unambiguous_fixtures_have_family_score_separation(
    analyzer: MultiRoleOpportunityAnalyzer,
) -> None:
    embedded = JobPosting(
        id="score-embedded",
        title="Embedded Systems Developer",
        description="Build C and C++ device drivers for microcontrollers with RTOS scheduling and SPI, I2C, and UART interfaces.",
    )
    robotics = JobPosting(
        id="score-robotics",
        title="Robotics Integration Engineer",
        description="Integrate robots and end-of-arm tooling, develop controls and perception, and validate mechanical and electrical sensor systems.",
    )

    embedded_scores = analyzer.score_families(embedded)
    robotics_scores = analyzer.score_families(robotics)

    assert embedded_scores[RoleFamily.EMBEDDED_FIRMWARE] > embedded_scores.get(
        RoleFamily.ROBOTICS_MECHATRONICS, 0
    )
    assert robotics_scores[RoleFamily.ROBOTICS_MECHATRONICS] > robotics_scores.get(
        RoleFamily.EMBEDDED_FIRMWARE, 0
    )


def test_mixed_robotics_and_embedded_role_has_narrow_deterministic_classification(
    analyzer: MultiRoleOpportunityAnalyzer,
) -> None:
    posting = JobPosting(
        id="mixed-role",
        title="Robotic Device Integration Engineer",
        description=(
            "Integrate robotic manipulators and sensors, write embedded C++ device drivers, "
            "and validate real-time control interfaces."
        ),
    )

    first = analyzer.analyze(posting)
    second = analyzer.analyze(posting)
    allowed = {
        RoleFamily.ROBOTICS_MECHATRONICS.value,
        RoleFamily.EMBEDDED_FIRMWARE.value,
    }

    assert first == second
    assert first.supported is True
    assert first.role_family in allowed
    assert first.signals
    assert any(signal.family.value == first.role_family for signal in first.signals)


@pytest.mark.parametrize(
    "description",
    [
        "Integrate robotic workcells, fixtures, and sensor systems for automated assembly.",
        "Develop autonomous manipulation systems with tooling, controls, and machine vision.",
        "Validate electromechanical robot interfaces and perception in production cells.",
    ],
)
def test_robotics_paraphrases_preserve_dominant_family(
    analyzer: MultiRoleOpportunityAnalyzer,
    description: str,
) -> None:
    result = analyzer.analyze(
        JobPosting(id="robotics-paraphrase", title="Automation Engineer", description=description)
    )

    assert result.supported is True
    assert result.role_family == RoleFamily.ROBOTICS_MECHATRONICS.value
