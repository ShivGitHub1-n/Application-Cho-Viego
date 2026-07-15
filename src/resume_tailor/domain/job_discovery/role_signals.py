from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from pydantic import BaseModel, Field

from resume_tailor.domain.models import RoleFamily, RoleSignal


@dataclass(frozen=True)
class RoleSignalDefinition:
    id: str
    label: str
    canonical_term: str
    aliases: tuple[str, ...]
    weight: float
    family: RoleFamily
    required: bool = False
    title_weight: float = 2.0
    content_weight: float = 1.0

    @property
    def canonical(self) -> str:
        return self.canonical_term

    def as_role_signal(self) -> RoleSignal:
        return RoleSignal(
            id=self.id,
            label=self.label,
            keywords=list(self.aliases),
            weight=self.weight,
            required=self.required,
            family=self.family,
        )


ROLE_SIGNAL_CATALOG: Final[tuple[RoleSignalDefinition, ...]] = (
    RoleSignalDefinition(
        id="autonomous-driving",
        label="autonomous driving systems",
        canonical_term="autonomous driving",
        aliases=(
            "autonomous driving",
            "drive-by-wire",
            "carla",
            "navsim",
            "autonomous vehicle",
        ),
        weight=1.0,
        family=RoleFamily.AUTONOMOUS_SYSTEMS,
    ),
    RoleSignalDefinition(
        id="autonomy-integration",
        label="autonomous system integration",
        canonical_term="teleoperation",
        aliases=(
            "teleoperation",
            "ros 2",
            "real-time control",
            "safety override",
            "vehicle monitoring",
        ),
        weight=0.8,
        family=RoleFamily.AUTONOMOUS_SYSTEMS,
    ),
    RoleSignalDefinition(
        id="robotics-mechatronics",
        label="robotics and mechatronics",
        canonical_term="robotics",
        aliases=("robotics", "mechatronics", "actuator", "kinematics", "manipulator"),
        weight=0.9,
        family=RoleFamily.ROBOTICS_MECHATRONICS,
    ),
    RoleSignalDefinition(
        id="robotics-integration",
        label="robotics systems integration",
        canonical_term="sensor integration",
        aliases=("ros 2", "sensor integration", "motor control", "teleoperation"),
        weight=0.7,
        family=RoleFamily.ROBOTICS_MECHATRONICS,
    ),
    RoleSignalDefinition(
        id="computer-vision-perception",
        label="computer vision and perception",
        canonical_term="computer vision",
        aliases=(
            "computer vision",
            "perception",
            "scene understanding",
            "lidar",
            "camera",
            "yolov8",
            "opencv",
        ),
        weight=1.0,
        family=RoleFamily.COMPUTER_VISION_PERCEPTION,
    ),
    RoleSignalDefinition(
        id="vision-language-research",
        label="vision-language or vision-language-action models",
        canonical_term="vision-language",
        aliases=("vision-language", "vision language", "vla", "vlm", "multimodal reasoning"),
        weight=1.1,
        required=True,
        family=RoleFamily.AI_ML_MULTIMODAL,
    ),
    RoleSignalDefinition(
        id="deep-learning-research",
        label="deep learning and transformer research",
        canonical_term="deep learning",
        aliases=("deep learning", "transformer", "pytorch", "foundation model", "model behaviors"),
        weight=1.1,
        required=True,
        family=RoleFamily.AI_ML_MULTIMODAL,
    ),
    RoleSignalDefinition(
        id="research-evaluation",
        label="research evaluation and benchmarking",
        canonical_term="benchmark",
        aliases=(
            "benchmark",
            "simulation",
            "driving datasets",
            "research projects",
            "publication",
            "jupyter",
        ),
        weight=0.9,
        family=RoleFamily.AI_ML_MULTIMODAL,
    ),
    RoleSignalDefinition(
        id="applied-ai-systems",
        label="applied AI systems",
        canonical_term="llm",
        aliases=("llm", "rag", "multi-agent", "generative ai", "langgraph"),
        weight=0.9,
        family=RoleFamily.AI_ML_MULTIMODAL,
    ),
    RoleSignalDefinition(
        id="ai-evaluation-governance",
        label="AI evaluation and governance",
        canonical_term="ai governance",
        aliases=("ai governance", "compliance auditing", "adversarial testing", "model evaluation"),
        weight=0.8,
        family=RoleFamily.AI_ML_MULTIMODAL,
    ),
    RoleSignalDefinition(
        id="embedded-firmware",
        label="embedded firmware development",
        canonical_term="embedded",
        aliases=("embedded", "firmware", "microcontroller", "stm32", "rtos", "gpio"),
        weight=1.0,
        family=RoleFamily.EMBEDDED_FIRMWARE,
    ),
    RoleSignalDefinition(
        id="hardware-integration",
        label="hardware integration and interfaces",
        canonical_term="hardware",
        aliases=("hardware", "sensor", "i2c", "spi", "uart", "canbus", "interface"),
        weight=0.8,
        family=RoleFamily.EMBEDDED_FIRMWARE,
    ),
    RoleSignalDefinition(
        id="software-data-engineering",
        label="software and data engineering",
        canonical_term="python",
        aliases=("python", "etl", "pandas", "numpy", "api", "schema", "automation", "analytics"),
        weight=0.9,
        family=RoleFamily.SOFTWARE_DATA_ENGINEERING,
    ),
    RoleSignalDefinition(
        id="software-platforms",
        label="software platforms and services",
        canonical_term="fastapi",
        aliases=("fastapi", "database", "docker", "backend", "data pipeline"),
        weight=0.7,
        family=RoleFamily.SOFTWARE_DATA_ENGINEERING,
    ),
)


class RoleSignalClassification(BaseModel):
    primary_family: RoleFamily | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    supported: bool
    signals: list[RoleSignal] = Field(default_factory=list)
    secondary_role_families: list[RoleFamily] = Field(default_factory=list)
    family_scores: dict[RoleFamily, float] = Field(default_factory=dict)
    reason: str | None = None


def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    escaped = re.escape(phrase.casefold())
    escaped = escaped.replace(r"\ ", r"\s+")
    return re.compile(rf"(?<!\w){escaped}(?!\w)")


def _matches(phrase: str, text: str) -> bool:
    return _phrase_pattern(phrase).search(text) is not None


def classify_role_signals(title: str, content: str) -> RoleSignalClassification:
    normalized_title = title.casefold()
    normalized_content = content.casefold()
    matched: list[tuple[RoleSignalDefinition, bool, bool]] = []
    for definition in ROLE_SIGNAL_CATALOG:
        in_title = any(_matches(alias, normalized_title) for alias in definition.aliases)
        in_content = any(_matches(alias, normalized_content) for alias in definition.aliases)
        if in_title or in_content:
            matched.append((definition, in_title, in_content))

    family_scores: dict[RoleFamily, float] = {}
    for definition, in_title, _in_content in matched:
        score = definition.title_weight if in_title else definition.content_weight
        family_scores[definition.family] = (
            family_scores.get(definition.family, 0.0) + definition.weight * score
        )

    if not matched:
        return RoleSignalClassification(
            confidence=0.0,
            supported=False,
            reason="The posting does not contain recognized engineering role signals.",
        )

    ordered_families = sorted(
        family_scores,
        key=lambda family: (-family_scores[family], family.value),
    )
    confidence = min(1.0, 0.35 + (0.08 * len(matched)) + (0.08 * len(ordered_families)))
    return RoleSignalClassification(
        primary_family=ordered_families[0],
        confidence=confidence,
        supported=True,
        signals=[definition.as_role_signal() for definition, _, _ in matched],
        secondary_role_families=ordered_families[1:],
        family_scores=family_scores,
    )
