"""Deterministic, provider-safe search terms for engineering job discovery."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Final

from resume_tailor.domain.job_discovery.models import JobLevel
from resume_tailor.domain.models import RoleFamily

ROLE_FAMILY_TITLE_VARIANTS: Final[dict[RoleFamily, tuple[str, ...]]] = {
    RoleFamily.AUTONOMOUS_SYSTEMS: (
        "Autonomous Systems Engineer",
        "Autonomy Engineer",
        "Autonomous Vehicle Engineer",
        "GNC Engineer",
        "Vehicle Systems Engineer",
        "Flight Controls Engineer",
    ),
    RoleFamily.ROBOTICS_MECHATRONICS: (
        "Robotics Engineer",
        "Robotics Software Engineer",
        "Mechatronics Engineer",
        "Controls Engineer",
        "Robotics Integration Engineer",
        "Robot Controls Engineer",
        "Automation Engineer",
        "Electromechanical Engineer",
    ),
    RoleFamily.COMPUTER_VISION_PERCEPTION: (
        "Computer Vision Engineer",
        "Perception Engineer",
        "Sensor Fusion Engineer",
        "Sensor Integration Engineer",
        "Imaging Engineer",
    ),
    RoleFamily.AI_ML_MULTIMODAL: (
        "Machine Learning Engineer",
        "Applied AI Engineer",
        "AI Engineer",
        "ML Systems Engineer",
    ),
    RoleFamily.EMBEDDED_FIRMWARE: (
        "Embedded Software Engineer",
        "Embedded Systems Engineer",
        "Firmware Engineer",
        "Hardware Engineer",
        "Electrical Engineer",
        "Electronics Engineer",
        "Systems Integration Engineer",
        "Hardware Test Engineer",
        "Avionics Engineer",
        "FPGA Engineer",
    ),
    RoleFamily.SOFTWARE_DATA_ENGINEERING: (
        "Software Engineer",
        "Backend Engineer",
        "Data Engineer",
        "Platform Software Engineer",
        "Application Software Engineer",
    ),
}

EXPLORE_SECTOR_TITLE_TERMS: Final[dict[str, tuple[str, ...]]] = {
    "Software Engineering": (
        "Software Engineer",
        "Software",
        "Developer",
        "Backend Engineer",
        "Frontend Engineer",
        "Full Stack Engineer",
        "Platform Engineer",
        "Site Reliability Engineer",
        "DevOps Engineer",
    ),
    "Data Engineering": (
        "Data Engineer",
        "Analytics Engineer",
        "Data Platform",
        "Data Infrastructure",
    ),
    "AI / Machine Learning": (
        "Machine Learning",
        "Artificial Intelligence",
        "AI Engineer",
        "ML Engineer",
        "Applied Scientist",
    ),
    "Computer Vision": (
        "Computer Vision",
        "Perception",
        "Sensor Fusion",
        "Imaging Engineer",
    ),
    "Robotics / Autonomous Systems": (
        "Robotics",
        "Robot",
        "Autonomy",
        "Autonomous",
        "Motion Planning",
        "GNC",
        "Guidance Navigation and Control",
        "Robotics Integration Engineer",
    ),
    "Embedded Systems / Firmware": (
        "Embedded",
        "Firmware",
        "RTOS",
        "BSP Engineer",
        "Device Driver",
        "Microcontroller",
        "Flight Software",
        "Avionics Software",
    ),
    "Hardware / Systems Integration": (
        "Hardware",
        "Hardware Engineer",
        "Hardware Test Engineer",
        "Electrical",
        "Electrical Engineer",
        "Electronics",
        "Electronics Engineer",
        "Mechanical",
        "Mechanical Engineer",
        "Mechanical Design Engineer",
        "Electromechanical",
        "Electromechanical Engineer",
        "Electro-Mechanical",
        "Electro-Mechanical Engineer",
        "Systems Engineer",
        "Systems Integration Engineer",
        "Integration Engineer",
        "Integration & Test",
        "Integration and Test",
        "Avionics",
        "Avionics Engineer",
        "FPGA",
        "FPGA Engineer",
        "ASIC",
        "ASIC Engineer",
        "Silicon",
        "Silicon Engineer",
        "PCB Designer",
        "Hardware Test",
        "Sensor Integration",
        "Vehicle Systems",
        "Manufacturing Engineer",
        "Manufacturing Systems",
        "Manufacturing Test Engineer",
        "Production Test Engineer",
        "Test Automation Engineer",
    ),
    "Controls / Mechatronics": (
        "Controls Engineer",
        "Control Systems Engineer",
        "Mechatronics Engineer",
        "Automation Engineer",
        "Motion Control",
        "Motion Planning",
        "GNC Engineer",
        "Guidance Navigation and Control",
        "Robot Controls",
        "Manufacturing Automation",
        "Test Automation Engineer",
    ),
    "Testing / Verification": (
        "Test Engineer",
        "Test Automation Engineer",
        "Verification Engineer",
        "Validation Engineer",
        "Hardware Test",
        "Manufacturing Test",
        "Systems Test",
        "Flight Test",
        "HIL Engineer",
        "SIL Engineer",
    ),
}

APPROVED_EXPLORE_SECTORS: Final[tuple[str, ...]] = tuple(
    EXPLORE_SECTOR_TITLE_TERMS
)

_AMBIGUOUS_NON_ENGINEERING_TITLE_TERMS: Final[tuple[str, ...]] = (
    "counsel",
    "legal",
    "recruiter",
    "talent acquisition",
)

_ENGINEERING_OCCUPATION_TERMS: Final[tuple[str, ...]] = (
    "engineer",
    "engineering",
    "developer",
    "architect",
    "scientist",
    "technician",
    "designer",
    "specialist",
)

_LEVEL_TERMS: Final[dict[JobLevel, tuple[str, ...]]] = {
    JobLevel.INTERN: ("intern", "internship", "co-op", "co op"),
    JobLevel.ENTRY: (
        "entry level",
        "early career",
        "new grad",
        "new graduate",
        "junior",
        "associate engineer",
    ),
    JobLevel.JUNIOR: ("junior", "jr", "entry level", "early career"),
    JobLevel.MID: ("mid level", "mid-level", "engineer ii"),
    JobLevel.SENIOR: ("senior", "sr"),
    JobLevel.LEAD: ("lead",),
    JobLevel.STAFF: ("staff",),
    JobLevel.PRINCIPAL: ("principal",),
    JobLevel.DIRECTOR: ("director",),
}

_KNOWN_SENIORITY_TERMS: Final[tuple[str, ...]] = tuple(
    dict.fromkeys(
        term
        for terms in _LEVEL_TERMS.values()
        for term in terms
    )
) + ("manager", "head", "chief")


def _normalized(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9+#]+", " ", value.casefold()).split())


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized_text = _normalized(text)
    normalized_phrase = _normalized(phrase)
    if not normalized_phrase:
        return False
    return re.search(
        rf"(?<![a-z0-9]){re.escape(normalized_phrase)}(?![a-z0-9])",
        normalized_text,
    ) is not None


def explore_sector_query_terms(sector: str) -> tuple[str, ...]:
    return EXPLORE_SECTOR_TITLE_TERMS.get(sector, ())


def matches_title_query(title: str, terms: Iterable[str]) -> bool:
    return any(_contains_phrase(title, term) for term in terms)


def matches_explore_sector(title: str, sector: str) -> bool:
    if any(_contains_phrase(title, term) for term in _AMBIGUOUS_NON_ENGINEERING_TITLE_TERMS):
        return False
    if not any(_contains_phrase(title, term) for term in _ENGINEERING_OCCUPATION_TERMS):
        return False
    return matches_title_query(title, explore_sector_query_terms(sector))


def matches_any_explore_sector(title: str, sectors: Iterable[str]) -> bool:
    return any(matches_explore_sector(title, sector) for sector in sectors)


def matches_requested_levels(title: str, levels: Iterable[JobLevel]) -> bool:
    requested = tuple(level for level in levels if level is not JobLevel.UNKNOWN)
    if not requested:
        return True
    has_known_level = any(_contains_phrase(title, term) for term in _KNOWN_SENIORITY_TERMS)
    if not has_known_level:
        return True
    return any(
        _contains_phrase(title, term)
        for level in requested
        for term in _LEVEL_TERMS.get(level, ())
    )


__all__ = [
    "APPROVED_EXPLORE_SECTORS",
    "EXPLORE_SECTOR_TITLE_TERMS",
    "ROLE_FAMILY_TITLE_VARIANTS",
    "explore_sector_query_terms",
    "matches_any_explore_sector",
    "matches_explore_sector",
    "matches_requested_levels",
    "matches_title_query",
]
