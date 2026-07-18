from __future__ import annotations

from collections import OrderedDict

from resume_tailor.domain.models import TechnicalSkillCategory

_CATEGORY_TERMS: tuple[tuple[str, frozenset[str]], ...] = (
    (
        "Mechanical Design & CAD",
        frozenset(
            {
                "ansys",
                "autocad",
                "cad",
                "fusion 360",
                "mechanical design",
                "solidworks",
            }
        ),
    ),
    (
        "Embedded Systems & Microcontrollers",
        frozenset(
            {
                "arduino",
                "embedded",
                "esp32",
                "firmware",
                "microcontroller",
                "raspberry pi",
                "stm32",
            }
        ),
    ),
    (
        "Circuitry & Electronics",
        frozenset(
            {
                "altium",
                "circuit design",
                "circuitry",
                "electronics",
                "ltspice",
                "pcb",
            }
        ),
    ),
    (
        "Robotics & Perception",
        frozenset(
            {
                "jetson",
                "lidar",
                "nvidia jetson orin",
                "opencv",
                "perception",
                "robotics",
                "ros",
                "ros 2",
                "ros2",
                "sensor fusion",
                "teleoperation systems",
                "yolo",
                "yolov8",
            }
        ),
    ),
    (
        "Data & AI",
        frozenset(
            {
                "data analysis",
                "data engineering",
                "etl",
                "etl pipelines",
                "gemini",
                "gemini api",
                "llm",
                "llm applications",
                "matplotlib",
                "numpy",
                "pandas",
                "power bi",
                "pytorch",
                "tensorflow",
            }
        ),
    ),
    (
        "Programming & Scripting",
        frozenset(
            {
                "bash",
                "c",
                "c++",
                "html/css",
                "java",
                "javascript",
                "matlab",
                "node.js",
                "python",
                "react",
                "sql",
                "typescript",
            }
        ),
    ),
)


def propose_reviewed_skill_categories(
    declared_skills: list[str],
) -> list[TechnicalSkillCategory]:
    """Group existing reviewed values without adding or renaming a skill."""

    grouped: OrderedDict[str, list[str]] = OrderedDict()
    seen: set[str] = set()
    for raw_skill in declared_skills:
        skill = raw_skill.strip()
        key = skill.casefold()
        if not skill or key in seen:
            continue
        seen.add(key)
        category = next(
            (label for label, terms in _CATEGORY_TERMS if key in terms),
            "Other reviewed skills",
        )
        grouped.setdefault(category, []).append(skill)
    return [
        TechnicalSkillCategory(category=label, values=values) for label, values in grouped.items()
    ]


__all__ = ["propose_reviewed_skill_categories"]
