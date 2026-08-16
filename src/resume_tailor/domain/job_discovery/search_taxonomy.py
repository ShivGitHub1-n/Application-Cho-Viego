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
        "PCB",
        "PCBA",
        "PCB Designer",
        "Harness",
        "Wiring",
        "Instrumentation Engineer",
        "Reliability Engineer",
        "Hardware Test",
        "Sensor Integration",
        "Vehicle Systems",
        "Power Systems",
        "Flight Controls",
        "Manufacturing Engineer",
        "Manufacturing Systems",
        "Manufacturing Automation",
        "Manufacturing Test Engineer",
        "Production Test Engineer",
        "Test Automation Engineer",
    ),
    "Controls / Mechatronics": (
        "Controls Engineer",
        "Control Systems Engineer",
        "Controls Verification",
        "Controls Test",
        "Mechatronics",
        "Mechatronics Engineer",
        "Automation Engineer",
        "Motion Control",
        "Motion Planning",
        "GNC",
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

_SOFTWARE_SECTOR_DIRECT_TERMS: Final[tuple[str, ...]] = (
    "Software Engineer",
    "Software",
    "Developer",
    "Backend Engineer",
    "Frontend Engineer",
    "Full Stack Engineer",
    "Site Reliability Engineer",
    "DevOps Engineer",
)

_NON_SOFTWARE_PLATFORM_TITLE_TERMS: Final[tuple[str, ...]] = (
    "Hardware",
    "Electrical",
    "Electronics",
    "Mechanical",
    "Electromechanical",
    "Avionics",
    "Manufacturing",
    "Robotics",
    "Vehicle",
)

_HARDWARE_DIRECT_TITLE_TERMS: Final[tuple[str, ...]] = (
    "Hardware",
    "Electrical",
    "Electronics",
    "Mechanical",
    "Electromechanical",
    "Electro-Mechanical",
    "Avionics",
    "FPGA",
    "ASIC",
    "Silicon",
    "PCB",
    "PCBA",
    "Harness",
    "Wiring",
    "Instrumentation Engineer",
    "Manufacturing Engineer",
    "Manufacturing Systems",
    "Manufacturing Test",
    "Production Test",
    "Hardware Test",
    "Sensor Integration",
    "Vehicle Systems",
    "Power Systems",
    "Flight Controls",
    "Manufacturing Automation",
)

_HARDWARE_AMBIGUOUS_TITLE_TERMS: Final[tuple[str, ...]] = (
    "Systems Integration",
    "Integration & Test",
    "Integration and Test",
    "Systems Engineer",
    "Integration Engineer",
    "Reliability Engineer",
    "Test Automation Engineer",
)

_HARDWARE_ADJACENT_TITLE_TERMS: Final[tuple[str, ...]] = (
    "Embedded",
    "Firmware",
    "Robotics",
    "Robot",
    "Autonomy",
    "Autonomous",
    "Controls",
    "Control Systems",
    "GNC",
    "Guidance Navigation and Control",
    "RF",
    "Radar",
    "Flight",
    "Launch",
    "Launched Effects",
    "Vehicle",
    "Spacecraft",
    "Starship",
    "Booster",
    "Heatshield",
    "Wireless",
    "Air Defense",
    "Maritime",
    "C3",
    "Power Systems",
    "Energy Systems",
    "Fluid Systems",
    "Fuel Systems",
    "Propulsion",
    "Thermal",
    "Mechanisms",
    "Mission Systems",
    "Ground Systems",
    "C2 Integration",
    "C2",
    "Battlespace",
    "Electronic Warfare",
    "EW",
    "Fluids Systems",
    "Reliability",
    "Space",
    "Weapons",
    "Verification",
    "Validation",
)

_SOFTWARE_ONLY_TITLE_CONTEXT: Final[tuple[str, ...]] = (
    "Software",
    "Backend",
    "Application",
    "Cloud",
    "Data Platform",
    "Hosted Model",
    "HPC",
    "High Performance Computing",
    "Infrastructure",
    "Network",
    "Platform",
    "Site Reliability",
    "Telemetry",
)

_HARDWARE_MIXED_INTEGRATION_TERMS: Final[tuple[str, ...]] = (
    "Embedded",
    "Firmware",
    "Robotics",
    "Robot",
    "Autonomy",
    "Autonomous",
    "Controls",
    "Control Systems",
    "GNC",
    "Sensor",
)

_HARDWARE_NON_ENGINEERING_TITLE_TERMS: Final[tuple[str, ...]] = (
    "Buyer",
    "Procurement",
    "Sourcing",
    "Supply Chain",
)

_CONTROLS_DIRECT_TITLE_TERMS: Final[tuple[str, ...]] = (
    "Controls Engineer",
    "Control Systems Engineer",
    "Controls Verification",
    "Controls Test",
    "Mechatronics",
    "Mechatronics Engineer",
    "Motion Control",
    "GNC",
    "GNC Engineer",
    "Guidance Navigation and Control",
    "Robot Controls",
    "Manufacturing Automation",
)

_CONTROLS_AUTOMATION_CONTEXT: Final[tuple[str, ...]] = (
    "Manufacturing",
    "Industrial",
    "Factory",
    "Production",
    "Process",
    "Assembly",
    "Welding",
    "Robotics",
    "Robot",
    "Controls",
    "Motion",
    "PLC",
    "Instrumentation",
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
    if sector == "Software Engineering":
        return _matches_software_sector(title)
    if sector == "Hardware / Systems Integration":
        return _matches_hardware_sector(title)
    if sector == "Controls / Mechatronics":
        return _matches_controls_sector(title)
    return matches_title_query(title, explore_sector_query_terms(sector))


def _matches_software_sector(title: str) -> bool:
    """Require an explicit software occupation rather than a generic platform label."""

    if matches_title_query(title, _SOFTWARE_SECTOR_DIRECT_TERMS):
        return True
    return matches_title_query(title, ("Platform Engineer",)) and not matches_title_query(
        title, _NON_SOFTWARE_PLATFORM_TITLE_TERMS
    )


def _matches_hardware_sector(title: str) -> bool:
    """Classify from title evidence, with bounded rules for ambiguous systems roles."""

    if matches_title_query(title, _HARDWARE_NON_ENGINEERING_TITLE_TERMS):
        return False
    if matches_title_query(title, _HARDWARE_DIRECT_TITLE_TERMS):
        return True
    if not matches_title_query(title, _HARDWARE_AMBIGUOUS_TITLE_TERMS):
        return False
    if matches_title_query(title, _SOFTWARE_ONLY_TITLE_CONTEXT):
        return matches_title_query(
            title,
            ("Systems Integration", "Integration Engineer"),
        ) and matches_title_query(title, _HARDWARE_MIXED_INTEGRATION_TERMS)
    if matches_title_query(title, _HARDWARE_ADJACENT_TITLE_TERMS):
        return True
    return matches_title_query(
        title,
        ("Systems Integration", "Integration & Test", "Integration and Test"),
    )


def _matches_controls_sector(title: str) -> bool:
    """Keep controls terms specific and qualify otherwise-generic automation roles."""

    if matches_title_query(title, _CONTROLS_DIRECT_TITLE_TERMS):
        return True
    return matches_title_query(title, ("Automation Engineer",)) and matches_title_query(
        title, _CONTROLS_AUTOMATION_CONTEXT
    )


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
