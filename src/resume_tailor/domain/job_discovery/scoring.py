from __future__ import annotations

from datetime import datetime

from resume_tailor.domain.job_discovery.models import (
    DiscoveredJob,
    JobRequirementSignals,
    JobScoreBreakdown,
    JobSearchPreferences,
    MatchLabel,
    ProfileCapabilityEvidence,
    ProfileCapabilityIndex,
    RequirementCategory,
)
from resume_tailor.domain.job_discovery.normalization import normalize_job_term


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
    preferred = {
        normalize_job_term(company) for company in preferences.preferred_companies
    }
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


def _strength(evidence: list[ProfileCapabilityEvidence]) -> float:
    if any(item.demonstrated for item in evidence):
        return 1.0
    if any(item.source_type == "reviewed_skill" for item in evidence):
        return 0.7
    if evidence:
        return 0.4
    return 0.0


def _has_demonstrated(evidence: list[ProfileCapabilityEvidence]) -> bool:
    return any(item.demonstrated for item in evidence)


def _term_evidence(
    term: str, profile_index: ProfileCapabilityIndex
) -> list[ProfileCapabilityEvidence]:
    normalized = normalize_job_term(term)
    return profile_index.terms.get(normalized, [])


def _requirement_terms(job: DiscoveredJob) -> dict[str, RequirementCategory]:
    result: dict[str, RequirementCategory] = {}
    for requirement in job.requirements.requirements:
        result.setdefault(requirement.term, requirement.category)
    return result


def _technical_component(
    job: DiscoveredJob, profile_index: ProfileCapabilityIndex
) -> float:
    technical_terms = [
        term
        for term, category in _requirement_terms(job).items()
        if category is RequirementCategory.TECHNOLOGY
    ]
    if not technical_terms:
        return 0.0
    demonstrated = sum(
        _has_demonstrated(_term_evidence(term, profile_index)) for term in technical_terms
    )
    return 30.0 * demonstrated / len(technical_terms)


def _required_component(
    job: DiscoveredJob, profile_index: ProfileCapabilityIndex
) -> float:
    terms = _unique(job.requirements.required_terms)
    if not terms:
        return 0.0
    return 20.0 * sum(_strength(_term_evidence(term, profile_index)) for term in terms) / len(terms)


def _role_component(job: DiscoveredJob, preferences: JobSearchPreferences) -> float:
    points = 0.0
    primary = job.role_family
    if primary is not None and preferences.role_family_priority:
        if primary is preferences.role_family_priority[0]:
            points += 8.0
        elif primary in preferences.role_family_priority:
            points += 6.0

    requested_titles = _unique(
        [*preferences.target_titles, *preferences.related_title_variants]
    )
    title = normalize_job_term(job.title)
    if requested_titles and any(
        candidate == title or candidate in title or title in candidate
        for candidate in requested_titles
    ):
        points += 4.0

    preference_terms = _unique(
        [*preferences.technical_themes, *preferences.career_interests]
    )
    job_terms = set(_unique(job.requirements.required_terms + job.requirements.preferred_terms))
    family_terms = _unique([primary.value if primary else ""])
    if preference_terms and any(
        term in job_terms or term in family_terms or any(term in value for value in family_terms)
        for term in preference_terms
    ):
        points += 3.0
    return min(15.0, points)


def _level_component(job: DiscoveredJob, preferences: JobSearchPreferences) -> float:
    if not preferences.job_levels or job.requirements.job_level.value == "unknown":
        return 0.0
    return 15.0 if job.requirements.job_level in preferences.job_levels else 0.0


def _education_component(
    job: DiscoveredJob, profile_index: ProfileCapabilityIndex
) -> float:
    terms = [*job.requirements.degree_requirements, *job.requirements.graduation_requirements]
    if not terms:
        terms.extend(
            requirement.term
            for requirement in job.requirements.requirements
            if requirement.category is RequirementCategory.EDUCATION
        )
    if not terms:
        return 0.0
    matched = 0
    for term in terms:
        normalized = normalize_job_term(term)
        if any(
            normalized in indexed or indexed in normalized
            for indexed in profile_index.terms
            if indexed
        ):
            matched += 1
    return 10.0 * matched / len(terms)


def _preferred_component(
    job: DiscoveredJob, profile_index: ProfileCapabilityIndex
) -> float:
    terms = _unique(job.requirements.preferred_terms)
    if not terms:
        return 0.0
    return 5.0 * sum(_strength(_term_evidence(term, profile_index)) for term in terms) / len(terms)


def _recency_completeness(
    job: DiscoveredJob, preferences: JobSearchPreferences, as_of: datetime
) -> float:
    recency = 2.5
    if job.posted_at is not None:
        if preferences.max_posting_age_days is None:
            recency = 2.5
        else:
            age = max(0, (as_of - job.posted_at).days)
            recency = 2.5 if age <= preferences.max_posting_age_days else 0.0
    completeness = 0.0 if job.completeness or not job.description else 2.5
    return recency + completeness


class ScoringPolicy:
    def score(
        self,
        job: DiscoveredJob,
        preferences: JobSearchPreferences,
        profile_index: ProfileCapabilityIndex,
        *,
        as_of: datetime,
    ) -> JobScoreBreakdown:
        components = {
            "demonstrated_technical_evidence": _technical_component(job, profile_index),
            "required_coverage": _required_component(job, profile_index),
            "role_alignment": _role_component(job, preferences),
            "level_alignment": _level_component(job, preferences),
            "education_coursework": _education_component(job, profile_index),
            "preferred_skill_alignment": _preferred_component(job, profile_index),
            "recency_completeness": _recency_completeness(job, preferences, as_of),
        }
        total = max(0.0, min(100.0, sum(components.values())))
        provisional = bool(job.completeness or not job.description.strip())
        if provisional:
            total = min(total, 54.0)
        total = round(total, 2)
        return JobScoreBreakdown(
            **components,
            total=total,
            label=MatchLabel.PROVISIONAL if provisional else score_label(total),
            provisional=provisional,
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
        demonstrated_required_reasons: list[str] = []
        responsibility_reasons: list[str] = []
        demonstrated_preferred_reasons: list[str] = []
        declared_required_reasons: list[str] = []
        role_reasons: list[str] = []
        level_reasons: list[str] = []
        education_reasons: list[str] = []
        preferred_company_reasons: list[str] = []
        gaps: list[tuple[int, float, str, str]] = []
        required = _unique(requirements.required_terms)
        preferred = _unique(requirements.preferred_terms)

        for term in required:
            evidence = _term_evidence(term, profile_index)
            demonstrated = [item for item in evidence if item.demonstrated]
            if demonstrated:
                first = sorted(demonstrated, key=lambda item: (item.source_id, item.source_text))[0]
                entry_title = first.source_text.split(" — ", 1)[0].strip() or first.source_text
                count = len([item for item in evidence if item.source_type == "confirmed_evidence"])
                count = count or len(demonstrated)
                suffix = "item" if count == 1 else "items"
                demonstrated_required_reasons.append(
                    f"Demonstrated {term} in {entry_title} ({count} confirmed evidence {suffix})."
                )
            elif any(item.source_type == "reviewed_skill" for item in evidence):
                declared_required_reasons.append(
                    f"Reviewed technical skill matches required {term}."
                )
                gaps.append(
                    (
                        0,
                        20.0 / max(1, len(required)),
                        term,
                        (
                            f"Reviewed profile mentions {term}, but no confirmed evidence "
                            "item demonstrates it."
                        ),
                    )
                )
            else:
                gaps.append(
                    (
                        0,
                        20.0 / max(1, len(required)),
                        term,
                        f"No reviewed profile evidence or skill was found for required {term}.",
                    )
                )

        responsibility_terms = _unique(
            [
                *requirements.required_terms,
                *requirements.preferred_terms,
                *requirements.unknown_terms,
            ]
        )
        for responsibility in requirements.responsibilities:
            normalized = normalize_job_term(responsibility)
            matching = sorted(
                term
                for term in responsibility_terms
                if term in normalized and _has_demonstrated(_term_evidence(term, profile_index))
            )
            if matching:
                responsibility_reasons.append(
                    f"Confirmed experience demonstrates {matching[0]} for this role."
                )

        for term in preferred:
            evidence = _term_evidence(term, profile_index)
            if any(item.demonstrated for item in evidence):
                demonstrated_items = sorted(
                    (item for item in evidence if item.demonstrated),
                    key=lambda item: (item.source_id, item.source_text),
                )
                demonstrated_evidence = demonstrated_items[0]
                count = len(
                    [item for item in evidence if item.source_type == "confirmed_evidence"]
                )
                count = count or len(demonstrated_items)
                suffix = "item" if count == 1 else "items"
                demonstrated_preferred_reasons.append(
                    f"Demonstrated {term} in {demonstrated_evidence.source_text} "
                    f"({count} confirmed evidence {suffix})."
                )
            elif not any(
                item.source_type in {"reviewed_skill", "confirmed_evidence", "resume_item"}
                for item in evidence
            ):
                gaps.append(
                    (
                        1,
                        5.0 / max(1, len(preferred)),
                        term,
                        f"Preferred {term} is not present in reviewed profile evidence or skills.",
                    )
                )

        education_terms = [
            *requirements.degree_requirements,
            *requirements.graduation_requirements,
        ]
        for term in education_terms:
            normalized = normalize_job_term(term)
            if any(
                normalized == indexed or normalized in indexed or indexed in normalized
                for indexed in profile_index.terms
            ):
                continue
            gaps.append(
                (
                    0,
                    10.0 / max(1, len(education_terms)),
                    normalized,
                    f"Reviewed education or coursework does not show {term}.",
                )
            )

        if (
            self._preferences
            and job.role_family
            and self._preferences.role_family_priority
            and job.role_family is self._preferences.role_family_priority[0]
        ):
            role_reasons.append(
                f"Selected role family {job.role_family.value.replace('_', ' ')} matches "
                "the posting's primary role family."
            )
        if (
            self._preferences
            and job.requirements.job_level.value != "unknown"
            and job.requirements.job_level in self._preferences.job_levels
        ):
            level_reasons.append(
                f"Selected job level {job.requirements.job_level.value} matches the posting."
            )
        for term in requirements.degree_requirements:
            if any(
                normalize_job_term(term) in indexed or indexed in normalize_job_term(term)
                for indexed in profile_index.terms
            ):
                education_reasons.append(f"Reviewed education or coursework matches {term}.")
        if self._preferences and job.company_name.casefold().strip() in {
            value.casefold().strip() for value in self._preferences.preferred_companies
        }:
            preferred_company_reasons.append("Company is on your preferred-company list.")

        gaps.sort(key=lambda item: (item[0], -item[1], item[2]))
        reasons = [
            *demonstrated_required_reasons,
            *responsibility_reasons,
            *demonstrated_preferred_reasons,
            *declared_required_reasons,
            *role_reasons,
            *level_reasons,
            *education_reasons,
            *preferred_company_reasons,
        ]
        return reasons, [gap[3] for gap in gaps[:5]]
