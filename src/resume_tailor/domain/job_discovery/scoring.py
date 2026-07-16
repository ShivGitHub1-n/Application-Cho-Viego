from __future__ import annotations

import math
from datetime import datetime

from resume_tailor.domain.job_discovery.models import (
    DiscoveredJob,
    JobRequirement,
    JobRequirementSignals,
    JobScoreBreakdown,
    JobSearchPreferences,
    MatchLabel,
    ProfileCapabilityEvidence,
    ProfileCapabilityIndex,
    RequirementEvidenceAllocation,
    RequirementCategory,
    RequirementImportance,
)
from resume_tailor.domain.job_discovery.normalization import normalize_job_term

MAX_DIRECT_TECHNICAL = 30.0
MAX_REQUIRED_COVERAGE = 20.0
MAX_PREFERRED_OCCUPATIONAL = 5.0
MAX_TRANSFERABLE = 15.0
MAX_OCCUPATIONAL_CORE = 70.0
MAX_EDUCATION = 10.0
MAX_LEVEL = 10.0
MAX_GENERIC_SUPPORT = MAX_EDUCATION + MAX_LEVEL
MAX_FIT_RAW = MAX_OCCUPATIONAL_CORE + MAX_GENERIC_SUPPORT

_GENERIC_CATEGORIES = {
    RequirementCategory.EDUCATION,
    RequirementCategory.AUTHORIZATION,
    RequirementCategory.LOCATION,
    RequirementCategory.WORK_ARRANGEMENT,
}
_OCCUPATIONAL_COVERAGE_CATEGORIES = {
    RequirementCategory.ROLE,
    RequirementCategory.RESPONSIBILITY,
    RequirementCategory.EXPERIENCE,
    RequirementCategory.CERTIFICATION,
}
_EXCLUDED_FROM_FIT = [
    "broad user preferences",
    "company preferences",
    "location and work-arrangement preferences",
    "posting recency",
    "posting completeness",
]


def score_label(total: float) -> MatchLabel:
    if total >= 85:
        return MatchLabel.STRONG
    if total >= 70:
        return MatchLabel.GOOD
    return MatchLabel.STRETCH


def recommendation_sort_key(
    job: DiscoveredJob,
    score: JobScoreBreakdown,
    preferences: JobSearchPreferences,
) -> tuple[float, int, str]:
    preferred = {normalize_job_term(company) for company in preferences.preferred_companies}
    preferred_rank = 0 if normalize_job_term(job.company_name) in preferred else 1
    return (-score.total, preferred_rank, job.id)


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = normalize_job_term(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _term_evidence(term: str, profile_index: ProfileCapabilityIndex) -> list[ProfileCapabilityEvidence]:
    return profile_index.terms.get(normalize_job_term(term), [])


def _demonstrated_evidence(
    term: str, profile_index: ProfileCapabilityIndex
) -> list[ProfileCapabilityEvidence]:
    return sorted(
        (item for item in _term_evidence(term, profile_index) if item.demonstrated),
        key=lambda item: (item.source_id, item.source_text),
    )


SemanticRequirementKey = tuple[str, str, str]


def _semantic_requirement_key(requirement: JobRequirement) -> SemanticRequirementKey:
    return (
        requirement.category.value,
        normalize_job_term(requirement.term),
        requirement.importance.value,
    )


def _requirements(job: DiscoveredJob) -> list[JobRequirement]:
    return sorted(
        job.requirements.requirements,
        key=_semantic_requirement_key,
    )


def _canonical_requirement_entries(
    job: DiscoveredJob,
) -> list[tuple[JobRequirement, SemanticRequirementKey]]:
    entries: list[tuple[JobRequirement, SemanticRequirementKey]] = []
    seen: set[SemanticRequirementKey] = set()
    for requirement in _requirements(job):
        semantic_key = _semantic_requirement_key(requirement)
        if semantic_key in seen:
            continue
        seen.add(semantic_key)
        entries.append((requirement, semantic_key))
    return entries


def _evidence_key(item: ProfileCapabilityEvidence) -> str:
    return item.source_id


def _diminishing_factor(previous_requirement_count: int) -> float:
    """Let one rich evidence item support distinct claims without saturating a component."""

    return 1.0 / math.sqrt(previous_requirement_count + 1)


def _allocate_requirement_points(
    requirements: list[tuple[JobRequirement, SemanticRequirementKey]],
    profile_index: ProfileCapabilityIndex,
    *,
    max_points: float,
    component: str,
    allowed_categories: set[RequirementCategory],
    required_only: bool = False,
    occupied_pairs: set[tuple[str, str]],
    evidence_requirement_counts: dict[str, int],
) -> tuple[float, list[RequirementEvidenceAllocation], list[str]]:
    candidates = [
        (requirement, requirement_key)
        for requirement, requirement_key in requirements
        if requirement.category in allowed_categories
        and (not required_only or requirement.importance is RequirementImportance.REQUIRED)
    ]
    if not candidates:
        return 0.0, [], []

    points_per_requirement = max_points / len(candidates)
    points = 0.0
    allocation: list[RequirementEvidenceAllocation] = []
    unmatched: list[str] = []
    for requirement, requirement_key in candidates:
        evidence = _demonstrated_evidence(requirement.term, profile_index)
        available = [
            item
            for item in evidence
            if (requirement_key, _evidence_key(item)) not in occupied_pairs
        ]
        if not available:
            unmatched.append(requirement.term)
            continue
        selected = available[0]
        pair = (requirement_key, _evidence_key(selected))
        occupied_pairs.add(pair)
        evidence_key = _evidence_key(selected)
        previous = evidence_requirement_counts.get(evidence_key, 0)
        evidence_requirement_counts[evidence_key] = previous + 1
        credit = points_per_requirement * _diminishing_factor(previous)
        points += credit
        allocation.append(
            RequirementEvidenceAllocation(
                category=requirement.category,
                term=normalize_job_term(requirement.term),
                importance=requirement.importance,
                component=component,
                evidence_ids=[evidence_key],
            )
        )
    return round(points, 2), allocation, unmatched


def _education_available(job: DiscoveredJob) -> float:
    return MAX_EDUCATION if (
        job.requirements.degree_requirements
        or job.requirements.graduation_requirements
    ) else 0.0


def _level_available(job: DiscoveredJob, preferences: JobSearchPreferences) -> float:
    return MAX_LEVEL if (
        preferences.job_levels
        and job.requirements.job_level.value != "unknown"
    ) else 0.0


def _score_components(
    job: DiscoveredJob,
    preferences: JobSearchPreferences,
    profile_index: ProfileCapabilityIndex,
) -> dict[str, object]:
    requirements = _canonical_requirement_entries(job)
    occupied_pairs: set[tuple[str, str]] = set()
    evidence_requirement_counts: dict[str, int] = {}
    allocation: list[RequirementEvidenceAllocation] = []

    direct_requirements = [
        (requirement, requirement_key)
        for requirement, requirement_key in requirements
        if requirement.importance is not RequirementImportance.PREFERRED
    ]
    direct, direct_allocation, _ = _allocate_requirement_points(
        direct_requirements,
        profile_index,
        max_points=MAX_DIRECT_TECHNICAL,
        component="direct_technical",
        allowed_categories={RequirementCategory.TECHNOLOGY},
        occupied_pairs=occupied_pairs,
        evidence_requirement_counts=evidence_requirement_counts,
    )
    allocation.extend(direct_allocation)

    required, required_allocation, unmatched = _allocate_requirement_points(
        requirements,
        profile_index,
        max_points=MAX_REQUIRED_COVERAGE,
        component="required_coverage",
        allowed_categories=_OCCUPATIONAL_COVERAGE_CATEGORIES,
        required_only=True,
        occupied_pairs=occupied_pairs,
        evidence_requirement_counts=evidence_requirement_counts,
    )
    allocation.extend(required_allocation)

    preferred_requirements = [
        (requirement, requirement_key)
        for requirement, requirement_key in requirements
        if requirement.importance is RequirementImportance.PREFERRED
        and requirement.category not in _GENERIC_CATEGORIES
    ]
    preferred, preferred_allocation, _ = _allocate_requirement_points(
        preferred_requirements,
        profile_index,
        max_points=MAX_PREFERRED_OCCUPATIONAL,
        component="preferred_occupational",
        allowed_categories={
            RequirementCategory.TECHNOLOGY,
            RequirementCategory.ROLE,
            RequirementCategory.RESPONSIBILITY,
        },
        occupied_pairs=occupied_pairs,
        evidence_requirement_counts=evidence_requirement_counts,
    )
    allocation.extend(preferred_allocation)

    transferable_requirements = [
        (requirement, requirement_key)
        for requirement, requirement_key in requirements
        if requirement.category in {
            RequirementCategory.ROLE,
            RequirementCategory.RESPONSIBILITY,
        }
        and requirement.importance is RequirementImportance.UNKNOWN
    ]
    transferable, transferable_allocation, _ = _allocate_requirement_points(
        transferable_requirements,
        profile_index,
        max_points=MAX_TRANSFERABLE,
        component="transferable",
        allowed_categories={RequirementCategory.ROLE, RequirementCategory.RESPONSIBILITY},
        occupied_pairs=occupied_pairs,
        evidence_requirement_counts=evidence_requirement_counts,
    )
    allocation.extend(transferable_allocation)

    occupational_core = round(direct + required + preferred + transferable, 2)
    factor = min(1.0, occupational_core / MAX_OCCUPATIONAL_CORE)
    education_available = _education_available(job)
    level_available = _level_available(job, preferences)
    education_admitted = round(education_available * factor, 2)
    level_admitted = round(level_available * factor, 2)
    generic_support = education_available + level_available
    generic_admitted = education_admitted + level_admitted
    fit_raw = occupational_core + generic_admitted
    total = round(100.0 * fit_raw / MAX_FIT_RAW, 2)
    return {
        "direct": direct,
        "required": required,
        "preferred": preferred,
        "transferable": transferable,
        "occupational_core": occupational_core,
        "factor": round(factor, 4),
        "education_available": education_available,
        "level_available": level_available,
        "education_admitted": education_admitted,
        "level_admitted": level_admitted,
        "generic_suppressed": round(generic_support - generic_admitted, 2),
        "total": total,
        "allocation": allocation,
        "unmatched": sorted(set(unmatched)),
    }


class ScoringPolicy:
    def score(
        self,
        job: DiscoveredJob,
        preferences: JobSearchPreferences,
        profile_index: ProfileCapabilityIndex,
        *,
        as_of: datetime,
    ) -> JobScoreBreakdown:
        del as_of  # Recency is recommendation metadata, not profile fit.
        components = _score_components(job, preferences, profile_index)
        provisional = bool(job.completeness or not job.description.strip())
        total = float(components["total"])
        return JobScoreBreakdown(
            demonstrated_technical_evidence=float(components["direct"]),
            required_coverage=float(components["required"]),
            role_alignment=0.0,
            level_alignment=float(components["level_admitted"]),
            education_coursework=float(components["education_admitted"]),
            preferred_skill_alignment=float(components["preferred"]),
            recency_completeness=0.0,
            total=total,
            label=MatchLabel.PROVISIONAL if provisional else score_label(total),
            provisional=provisional,
            transferable_evidence=float(components["transferable"]),
            profile_family_alignment=0.0,
            education_points_available=float(components["education_available"]),
            level_points_available=float(components["level_available"]),
            education_points_admitted=float(components["education_admitted"]),
            level_points_admitted=float(components["level_admitted"]),
            generic_points_suppressed=float(components["generic_suppressed"]),
            occupational_gating_factor=float(components["factor"]),
            unmatched_core_occupational_requirements=list(components["unmatched"]),
            evidence_allocation=list(components["allocation"]),
            recommendation_only_factors_excluded=list(_EXCLUDED_FROM_FIT),
        )


class DeterministicExplanationBuilder:
    def __init__(self, preferences: JobSearchPreferences | None = None) -> None:
        self._preferences = preferences

    def reasons_and_gaps(
        self,
        job: DiscoveredJob,
        requirements: JobRequirementSignals,
        profile_index: ProfileCapabilityIndex,
    ) -> tuple[list[str], list[str]]:
        components = _score_components(
            job,
            self._preferences or JobSearchPreferences.model_construct(job_levels=[]),
            profile_index,
        )
        reasons: list[str] = []
        gaps: list[str] = []
        required_terms = _unique(requirements.required_terms)
        preferred_terms = _unique(requirements.preferred_terms)
        for term in required_terms:
            evidence = _term_evidence(term, profile_index)
            demonstrated = [item for item in evidence if item.demonstrated]
            if demonstrated:
                first = demonstrated[0]
                entry_title = first.source_text.split(" â€” ", 1)[0].strip() or first.source_text
                reasons.append(f"Demonstrated {term} in {entry_title}.")
            elif any(item.source_type == "reviewed_skill" for item in evidence):
                reasons.append(f"Reviewed technical skill matches required {term}.")
                gaps.append(
                    f"Reviewed profile mentions {term}, but no confirmed evidence item demonstrates it."
                )
            else:
                gaps.append(
                    f"No reviewed profile evidence or skill was found for required {term}."
                )

        responsibility_terms = _unique(
            [*requirements.required_terms, *requirements.preferred_terms, *requirements.unknown_terms]
        )
        for responsibility in requirements.responsibilities:
            normalized = normalize_job_term(responsibility)
            matching = [
                term
                for term in responsibility_terms
                if term in normalized and _demonstrated_evidence(term, profile_index)
            ]
            if matching:
                reasons.append(f"Confirmed experience demonstrates {matching[0]} for this role.")

        for term in preferred_terms:
            if _demonstrated_evidence(term, profile_index):
                reasons.append(f"Demonstrated {term} in profile evidence.")
            elif not any(
                item.source_type in {"reviewed_skill", "confirmed_evidence", "resume_item"}
                for item in _term_evidence(term, profile_index)
            ):
                gaps.append(f"Preferred {term} is not present in reviewed profile evidence or skills.")

        for term in requirements.degree_requirements:
            normalized = normalize_job_term(term)
            if any(
                normalized == indexed or normalized in indexed or indexed in normalized
                for indexed in profile_index.terms
            ):
                if float(components["education_admitted"]):
                    reasons.append(f"Reviewed education or coursework matches {term}.")
                else:
                    gaps.append("Generic education evidence was suppressed because occupational fit was insufficient.")

        if self._preferences and job.requirements.job_level.value != "unknown":
            if job.requirements.job_level in self._preferences.job_levels:
                reasons.append(
                    f"Level compatibility was admitted after occupational gating ({components['factor']:.2f} factor)."
                )
        if float(components["occupational_core"]):
            reasons.append(
                "Occupational evidence points come from demonstrated responsibility and capability overlap."
            )
        else:
            gaps.append("No demonstrated occupational responsibility or capability overlap was found.")
        if float(components["transferable"]):
            reasons.append("Supported transferable responsibility evidence contributed to fit.")
        return reasons, gaps[:3]
