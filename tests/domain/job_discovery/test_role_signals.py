import pytest

from resume_tailor.application.job_intake import build_job_posting
from resume_tailor.domain.job_discovery.role_signals import (
    ROLE_SIGNAL_CATALOG,
    classify_role_signals,
)
from resume_tailor.domain.models import RoleFamily
from resume_tailor.infrastructure.optimization import MultiRoleOpportunityAnalyzer

EXPECTED_ROLE_SIGNALS = (
    (
        "autonomous-driving",
        "autonomous driving systems",
        "autonomous driving",
        ("autonomous driving", "drive-by-wire", "carla", "navsim", "autonomous vehicle"),
        1.0,
        False,
        RoleFamily.AUTONOMOUS_SYSTEMS,
    ),
    (
        "autonomy-integration",
        "autonomous system integration",
        "teleoperation",
        ("teleoperation", "ros 2", "real-time control", "safety override", "vehicle monitoring"),
        0.8,
        False,
        RoleFamily.AUTONOMOUS_SYSTEMS,
    ),
    (
        "robotics-mechatronics",
        "robotics and mechatronics",
        "robotics",
        ("robotics", "mechatronics", "actuator", "kinematics", "manipulator"),
        0.9,
        False,
        RoleFamily.ROBOTICS_MECHATRONICS,
    ),
    (
        "robotics-integration",
        "robotics systems integration",
        "sensor integration",
        ("ros 2", "sensor integration", "motor control", "teleoperation"),
        0.7,
        False,
        RoleFamily.ROBOTICS_MECHATRONICS,
    ),
    (
        "computer-vision-perception",
        "computer vision and perception",
        "computer vision",
        (
            "computer vision",
            "perception",
            "scene understanding",
            "lidar",
            "camera",
            "yolov8",
            "opencv",
        ),
        1.0,
        False,
        RoleFamily.COMPUTER_VISION_PERCEPTION,
    ),
    (
        "vision-language-research",
        "vision-language or vision-language-action models",
        "vision-language",
        ("vision-language", "vision language", "vla", "vlm", "multimodal reasoning"),
        1.1,
        True,
        RoleFamily.AI_ML_MULTIMODAL,
    ),
    (
        "deep-learning-research",
        "deep learning and transformer research",
        "deep learning",
        ("deep learning", "transformer", "pytorch", "foundation model", "model behaviors"),
        1.1,
        True,
        RoleFamily.AI_ML_MULTIMODAL,
    ),
    (
        "research-evaluation",
        "research evaluation and benchmarking",
        "benchmark",
        (
            "benchmark",
            "simulation",
            "driving datasets",
            "research projects",
            "publication",
            "jupyter",
        ),
        0.9,
        False,
        RoleFamily.AI_ML_MULTIMODAL,
    ),
    (
        "applied-ai-systems",
        "applied AI systems",
        "llm",
        ("llm", "rag", "multi-agent", "generative ai", "langgraph"),
        0.9,
        False,
        RoleFamily.AI_ML_MULTIMODAL,
    ),
    (
        "ai-evaluation-governance",
        "AI evaluation and governance",
        "ai governance",
        ("ai governance", "compliance auditing", "adversarial testing", "model evaluation"),
        0.8,
        False,
        RoleFamily.AI_ML_MULTIMODAL,
    ),
    (
        "embedded-firmware",
        "embedded firmware development",
        "embedded",
        ("embedded", "firmware", "microcontroller", "stm32", "rtos", "gpio"),
        1.0,
        False,
        RoleFamily.EMBEDDED_FIRMWARE,
    ),
    (
        "hardware-integration",
        "hardware integration and interfaces",
        "hardware",
        ("hardware", "sensor", "i2c", "spi", "uart", "canbus", "interface"),
        0.8,
        False,
        RoleFamily.EMBEDDED_FIRMWARE,
    ),
    (
        "software-data-engineering",
        "software and data engineering",
        "python",
        ("python", "etl", "pandas", "numpy", "api", "schema", "automation", "analytics"),
        0.9,
        False,
        RoleFamily.SOFTWARE_DATA_ENGINEERING,
    ),
    (
        "software-platforms",
        "software platforms and services",
        "fastapi",
        ("fastapi", "database", "docker", "backend", "data pipeline"),
        0.7,
        False,
        RoleFamily.SOFTWARE_DATA_ENGINEERING,
    ),
)


def test_role_catalog_preserves_existing_classification():
    result = classify_role_signals("autonomous driving perception engineer", "Perception Engineer")
    assert result.primary_family is RoleFamily.AUTONOMOUS_SYSTEMS
    assert result.family_scores[RoleFamily.AUTONOMOUS_SYSTEMS] > 0


def test_role_catalog_matches_pre_extraction_definitions():
    actual = tuple(
        (
            signal.id,
            signal.label,
            signal.canonical_term,
            signal.aliases,
            signal.weight,
            signal.required,
            signal.family,
        )
        for signal in ROLE_SIGNAL_CATALOG
    )

    assert actual == EXPECTED_ROLE_SIGNALS


@pytest.mark.parametrize(
    ("title", "content", "family"),
    [
        (
            "Autonomous Driving Engineer",
            "Build autonomous driving systems using CARLA.",
            RoleFamily.AUTONOMOUS_SYSTEMS,
        ),
        (
            "Robotics Mechatronics Engineer",
            "Design robotic manipulators and mechatronics systems.",
            RoleFamily.ROBOTICS_MECHATRONICS,
        ),
        (
            "Firmware Engineer",
            "Develop STM32 firmware and GPIO interface.",
            RoleFamily.EMBEDDED_FIRMWARE,
        ),
        (
            "Backend Engineer",
            "Build Python APIs with Docker.",
            RoleFamily.SOFTWARE_DATA_ENGINEERING,
        ),
    ],
)
def test_existing_role_classifications_remain_unchanged(title, content, family):
    result = classify_role_signals(title, content)

    assert result.primary_family is family


def test_unlisted_autonomous_systems_phrase_does_not_expand_catalog():
    result = classify_role_signals("Autonomous Systems Engineer", "")

    assert result.supported is False


@pytest.mark.parametrize(
    ("title", "content", "family", "confidence", "signal_ids"),
    [
        (
            "Autonomous Driving Engineer",
            "Build autonomous driving systems using CARLA.",
            RoleFamily.AUTONOMOUS_SYSTEMS,
            0.51,
            ["autonomous-driving"],
        ),
        (
            "Robotics Mechatronics Engineer",
            "Design robotic manipulators and mechatronics systems.",
            RoleFamily.ROBOTICS_MECHATRONICS,
            0.51,
            ["robotics-mechatronics"],
        ),
        (
            "Firmware Engineer",
            "Develop STM32 firmware and GPIO interface.",
            RoleFamily.EMBEDDED_FIRMWARE,
            0.59,
            ["embedded-firmware", "hardware-integration"],
        ),
        (
            "Backend Engineer",
            "Build Python APIs with Docker.",
            RoleFamily.SOFTWARE_DATA_ENGINEERING,
            0.59,
            ["software-data-engineering", "software-platforms"],
        ),
    ],
)
def test_compatibility_adapter_preserves_existing_contract(
    title,
    content,
    family,
    confidence,
    signal_ids,
):
    posting = build_job_posting("posting-compatibility", title, content)
    actual = MultiRoleOpportunityAnalyzer().analyze(posting)

    assert actual.role_family == family.value
    assert actual.confidence == confidence
    assert actual.supported is True
    assert [signal.id for signal in actual.signals] == signal_ids
    assert actual.secondary_role_families == []


def test_role_classifier_uses_phrase_boundaries_and_deterministic_ties():
    result = classify_role_signals("Engineer", "The platform uses python and backend services.")
    assert result.primary_family is RoleFamily.SOFTWARE_DATA_ENGINEERING
    assert not classify_role_signals(
        "Engineer", "A controllerless tool has no relevant terminology."
    ).signals


def test_role_classifier_returns_unsupported_when_no_signal_matches():
    result = classify_role_signals(
        "Product Manager", "Leads customer interviews and pricing strategy."
    )
    assert result.primary_family is None
    assert result.supported is False
    assert result.family_scores == {}
