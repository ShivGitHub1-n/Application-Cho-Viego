from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime

from resume_tailor.domain.job_discovery.models import (
    JobLevel,
    JobSearchPreferenceSuggestion,
    NormalizedLocation,
    WorkArrangement,
    WorkArrangementPreferenceMode,
)
from resume_tailor.domain.job_discovery.role_signals import classify_role_signals
from resume_tailor.domain.models import MasterProfile, ResumeItem, RoleFamily

_RELATED_TITLE_VARIANTS: dict[RoleFamily, tuple[str, ...]] = {
    RoleFamily.AUTONOMOUS_SYSTEMS: (
        "Autonomous Systems Engineer",
        "Autonomous Vehicle Engineer",
        "Autonomy Engineer",
    ),
    RoleFamily.ROBOTICS_MECHATRONICS: (
        "Robotics Engineer",
        "Robotics Software Engineer",
        "Mechatronics Engineer",
    ),
    RoleFamily.COMPUTER_VISION_PERCEPTION: (
        "Computer Vision Engineer",
        "Perception Engineer",
    ),
    RoleFamily.AI_ML_MULTIMODAL: (
        "Machine Learning Engineer",
        "Applied AI Engineer",
        "AI Engineer",
    ),
    RoleFamily.EMBEDDED_FIRMWARE: (
        "Embedded Systems Engineer",
        "Firmware Engineer",
    ),
    RoleFamily.SOFTWARE_DATA_ENGINEERING: (
        "Software Engineer",
        "Backend Engineer",
        "Data Engineer",
    ),
}

_CAREER_INTEREST_LABELS: dict[RoleFamily, str] = {
    RoleFamily.AUTONOMOUS_SYSTEMS: "autonomous systems",
    RoleFamily.ROBOTICS_MECHATRONICS: "robotics",
    RoleFamily.COMPUTER_VISION_PERCEPTION: "computer vision",
    RoleFamily.AI_ML_MULTIMODAL: "AI and machine learning",
    RoleFamily.EMBEDDED_FIRMWARE: "embedded systems",
    RoleFamily.SOFTWARE_DATA_ENGINEERING: "software and data engineering",
}

def _unique_sorted(values: list[str]) -> list[str]:
    unique_by_casefold: dict[str, str] = {}
    for value in values:
        stripped = value.strip()
        if stripped and stripped.casefold() not in unique_by_casefold:
            unique_by_casefold[stripped.casefold()] = stripped
    return sorted(
        unique_by_casefold.values(),
        key=lambda value: (value.casefold(), value),
    )


def _entry_text(profile: MasterProfile, entity_id: str) -> str:
    evidence = [
        item.source_text
        for item in profile.evidence
        if item.entity_id == entity_id and item.confirmed
    ]
    return " ".join(evidence)


class DeterministicJobSearchPreferenceSuggester:
    def suggest(
        self,
        profile: MasterProfile,
        *,
        generated_at: datetime,
    ) -> JobSearchPreferenceSuggestion:
        family_scores: defaultdict[RoleFamily, float] = defaultdict(float)
        entries = [*profile.experiences, *profile.projects]
        for entry in entries:
            content = " ".join(
                [
                    _entry_text(profile, entry.id),
                    *entry.technologies,
                    *entry.capabilities,
                    entry.description or "",
                ]
            )
            result = classify_role_signals(entry.title, content)
            for family, score in result.family_scores.items():
                family_scores[family] += score

        if not family_scores:
            family_scores.update(self._fallback_family_scores(entries))
        role_family_priority = sorted(
            family_scores,
            key=lambda family: (-family_scores[family], family.value),
        )

        target_titles = _unique_sorted([entry.title for entry in entries])
        related_title_variants = _unique_sorted(
            [
                variant
                for family in role_family_priority
                for variant in _RELATED_TITLE_VARIANTS[family]
            ]
        )
        technical_themes = _unique_sorted(
            [
                *[
                    term
                    for item in profile.evidence
                    if item.confirmed
                    for term in [*item.capabilities, *item.technologies]
                ],
                *[
                    term
                    for entry in entries
                    for term in [*entry.capabilities, *entry.technologies]
                ],
                *[
                    skill.value
                    for category in profile.technical_skills
                    for skill in category.skills
                ],
            ]
        )
        career_interests = _unique_sorted(
            [_CAREER_INTEREST_LABELS[family] for family in role_family_priority]
        )
        job_levels = self._suggest_job_levels(profile)
        locations = (
            [NormalizedLocation(raw=profile.contact.location)]
            if profile.contact.location
            else []
        )
        rationale = [
            (
                "Role-family priority is derived from confirmed profile evidence and "
                "reviewed resume entries."
            ),
            (
                "Target titles are copied from reviewed experience and project titles "
                "for user confirmation."
            ),
            (
                "Related title variants are bounded deterministic search terms and "
                "require user review."
            ),
            (
                "Technical themes and career interests are derived from confirmed "
                "evidence and reviewed skills."
            ),
            (
                "Job-level and location defaults are conservative suggestions, not "
                "inferred career intent."
            ),
        ]
        return JobSearchPreferenceSuggestion(
            profile_id=profile.id,
            generated_at=generated_at,
            role_family_priority=role_family_priority,
            target_titles=target_titles,
            related_title_variants=related_title_variants,
            technical_themes=technical_themes,
            career_interests=career_interests,
            job_levels=job_levels,
            locations=locations,
            work_arrangement=WorkArrangement.UNKNOWN,
            work_arrangement_mode=WorkArrangementPreferenceMode.PREFERRED,
            preferred_companies=[],
            rationale=rationale,
        )

    @staticmethod
    def _fallback_family_scores(entries: list[ResumeItem]) -> dict[RoleFamily, float]:
        scores: dict[RoleFamily, float] = {}
        for entry in entries:
            title = entry.title.casefold()
            family = (
                RoleFamily.SOFTWARE_DATA_ENGINEERING
                if any(term in title for term in ("software", "backend", "data"))
                else None
            )
            if family is not None:
                scores[family] = scores.get(family, 0.0) + 1.0
        return scores

    @staticmethod
    def _suggest_job_levels(profile: MasterProfile) -> list[JobLevel]:
        if profile.education:
            return [JobLevel.INTERN, JobLevel.ENTRY]
        if any(
            re.search(r"\bintern(ship)?\b|\bco[- ]?op\b", entry.title, re.IGNORECASE)
            for entry in [*profile.experiences, *profile.projects]
        ):
            return [JobLevel.INTERN, JobLevel.ENTRY]
        return [JobLevel.ENTRY]
