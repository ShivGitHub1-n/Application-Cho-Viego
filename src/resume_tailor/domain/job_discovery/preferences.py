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
from resume_tailor.domain.job_discovery.search_taxonomy import (
    ROLE_FAMILY_TITLE_VARIANTS,
)
from resume_tailor.domain.models import MasterProfile, ResumeItem, RoleFamily

_RELATED_TITLE_VARIANTS = ROLE_FAMILY_TITLE_VARIANTS

_CAREER_INTEREST_LABELS: dict[RoleFamily, str] = {
    RoleFamily.AUTONOMOUS_SYSTEMS: "autonomous systems",
    RoleFamily.ROBOTICS_MECHATRONICS: "robotics",
    RoleFamily.COMPUTER_VISION_PERCEPTION: "computer vision",
    RoleFamily.AI_ML_MULTIMODAL: "AI and machine learning",
    RoleFamily.EMBEDDED_FIRMWARE: "embedded systems",
    RoleFamily.SOFTWARE_DATA_ENGINEERING: "software and data engineering",
}

_EVIDENCE_TITLE_EXPANSIONS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ("solidworks", "fusion360", "fusion 360", "gd&t", "mechanical", "cad"),
        (
            "Mechanical Engineer",
            "Mechanical Design Engineer",
            "Electromechanical Engineer",
        ),
    ),
    (
        ("dfm", "dfa", "bill of materials", "bom ownership", "manufacturing"),
        ("Manufacturing Engineer", "Manufacturing Test Engineer"),
    ),
    (
        ("closed-loop", "closed loop", "motor control", "actuator control"),
        ("Controls Engineer", "Control Systems Engineer"),
    ),
    (
        ("hardware test", "test automation", "hardware validation", "hil"),
        ("Hardware Test Engineer", "Test Automation Engineer"),
    ),
)

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


def _unique_in_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.casefold()
        if value.strip() and key not in seen:
            seen.add(key)
            result.append(value.strip())
    return result


def _target_title_count(candidate_count: int) -> int:
    if candidate_count <= 1:
        return candidate_count
    return min(6, candidate_count - 1)


def _interleaved_family_title_candidates(
    role_family_priority: list[RoleFamily],
) -> list[str]:
    """Give each supported family a primary candidate before secondary variants."""

    family_variants = [list(_RELATED_TITLE_VARIANTS[family]) for family in role_family_priority]
    return _unique_in_order(
        [
            variant
            for index in range(max((len(variants) for variants in family_variants), default=0))
            for variants in family_variants
            if index < len(variants)
            for variant in [variants[index]]
        ]
    )


def _entry_text(profile: MasterProfile, entity_id: str) -> str:
    evidence = [
        item.source_text
        for item in profile.evidence
        if item.entity_id == entity_id and item.confirmed
    ]
    return " ".join(evidence)


def _contains_evidence_signal(text: str, signal: str) -> bool:
    escaped = re.escape(signal).replace(r"\ ", r"\s+")
    return re.search(rf"(?<!\w){escaped}(?!\w)", text) is not None


def _evidence_title_candidates(profile: MasterProfile, entries: list[ResumeItem]) -> list[str]:
    reviewed_text = " ".join(
        [
            *[
                " ".join(
                    [
                        entry.title,
                        entry.description or "",
                        *entry.technologies,
                        *entry.capabilities,
                    ]
                )
                for entry in entries
            ],
            *[
                " ".join(
                    [item.source_text, *item.technologies, *item.capabilities]
                )
                for item in profile.evidence
                if item.confirmed
            ],
            *[
                skill.value
                for category in profile.technical_skills
                for skill in category.skills
            ],
        ]
    ).casefold()
    return _unique_in_order(
        [
            title
            for signals, titles in _EVIDENCE_TITLE_EXPANSIONS
            if any(_contains_evidence_signal(reviewed_text, signal) for signal in signals)
            for title in titles
        ]
    )


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

        reviewed_skill_terms = [
            skill.value
            for category in profile.technical_skills
            for skill in category.skills
        ]
        if reviewed_skill_terms:
            skill_result = classify_role_signals("", " ".join(reviewed_skill_terms))
            for family, score in skill_result.family_scores.items():
                family_scores[family] += score

        if not family_scores:
            family_scores.update(self._fallback_family_scores(entries))
        role_family_priority = sorted(
            family_scores,
            key=lambda family: (-family_scores[family], family.value),
        )

        family_title_candidates = _unique_in_order(
            [
                *_interleaved_family_title_candidates(role_family_priority),
                *_evidence_title_candidates(profile, entries),
            ]
        )
        target_titles = family_title_candidates[: _target_title_count(len(family_title_candidates))]
        related_title_variants = _unique_sorted(family_title_candidates)
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
                "Target titles are a bounded shortlist of role-family variants ranked "
                "by support from the complete reviewed profile."
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
