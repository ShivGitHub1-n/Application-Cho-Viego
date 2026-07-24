"""Pure evidence-authoritative Jobs evaluation pipeline."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, Field

from resume_tailor.domain.job_discovery.eligibility import EligibilityEvaluator
from resume_tailor.domain.job_discovery.evidence import (
    CanonicalRequirement,
    EvidenceLedger,
    RequirementMatch,
    canonical_requirement_set,
)
from resume_tailor.domain.job_discovery.explanations import (
    MaterialGap,
    PositiveReason,
    UnresolvedFact,
)
from resume_tailor.domain.job_discovery.grading import (
    EVALUATION_POLICY_VERSION,
    FitGrade,
    GradeCap,
    GradingContext,
    evaluate_grade,
)
from resume_tailor.domain.job_discovery.models import (
    DiscoveredJob,
    EligibilityAssessment,
    EligibilityStatus,
    JobSearchPreferences,
    ProfileCapabilityIndex,
    RequirementMatchStatus,
)
from resume_tailor.domain.job_discovery.normalization import normalize_job_term
from resume_tailor.domain.job_discovery.requirements import RequirementExtractor
from resume_tailor.domain.job_discovery.role_signals import classify_role_signals
from resume_tailor.domain.models import MasterProfile


class RoleRelevanceAssessment(BaseModel):
    relevant: bool
    score: float = 0.0
    title_evidence: list[str] = Field(default_factory=list)
    responsibility_evidence: list[str] = Field(default_factory=list)
    team_function_evidence: list[str] = Field(default_factory=list)
    contextual_evidence: list[str] = Field(default_factory=list)
    mismatch_references: list[str] = Field(default_factory=list)
    uncertainty_references: list[str] = Field(default_factory=list)


class ProvisionalAssessment(BaseModel):
    is_provisional: bool = False
    reason_codes: list[str] = Field(default_factory=list)
    unresolved_facts: list[str] = Field(default_factory=list)


class InternalDiagnostics(BaseModel):
    demonstrated_technical_evidence: float = 0.0
    required_coverage: float = 0.0
    role_alignment: float = 0.0
    level_alignment: float = 0.0
    education_coursework: float = 0.0
    preferred_skill_alignment: float = 0.0
    recency_completeness: float = 0.0
    total: float = 0.0


class JobEvaluation(BaseModel):
    job_id: str
    eligibility: EligibilityAssessment
    role_relevance: RoleRelevanceAssessment
    requirements: list[CanonicalRequirement] = Field(default_factory=list)
    matches: list[RequirementMatch] = Field(default_factory=list)
    fit_grade: FitGrade
    diagnostics: InternalDiagnostics
    provisional: ProvisionalAssessment
    caps: list[GradeCap] = Field(default_factory=list)
    positive_reasons: list[PositiveReason] = Field(default_factory=list)
    material_gaps: list[MaterialGap] = Field(default_factory=list)
    unresolved_facts: list[UnresolvedFact] = Field(default_factory=list)
    evaluation_policy_version: str = EVALUATION_POLICY_VERSION


class JobEvaluatorProtocol(Protocol):
    def evaluate(
        self,
        job: DiscoveredJob,
        preferences: JobSearchPreferences,
        profile_index: ProfileCapabilityIndex,
        *,
        as_of: datetime,
        profile: MasterProfile | None = None,
    ) -> JobEvaluation: ...


class JobEvaluator:
    """Evaluate one posting once, in a fixed authority order."""

    def __init__(
        self,
        *,
        eligibility_evaluator: EligibilityEvaluator | None = None,
        requirement_extractor: RequirementExtractor | None = None,
    ) -> None:
        self._eligibility = eligibility_evaluator or EligibilityEvaluator()
        self._requirement_extractor = requirement_extractor

    def evaluate(
        self,
        job: DiscoveredJob,
        preferences: JobSearchPreferences,
        profile_index: ProfileCapabilityIndex,
        *,
        as_of: datetime,
        profile: MasterProfile | None = None,
    ) -> JobEvaluation:
        eligibility = self._eligibility.assess(
            job,
            preferences,
            as_of=as_of,
            profile=profile,
        )
        requirements_signals = job.requirements
        if not requirements_signals.requirements:
            extractor = self._requirement_extractor or RequirementExtractor(profile_index)
            requirements_signals = extractor.extract(
                job.title,
                job.description,
                job.location.raw,
                job.work_arrangement,
                profile_index,
            )
        requirements = canonical_requirement_set(requirements_signals.requirements)
        ledger = EvidenceLedger.allocate(requirements, profile_index)
        role = assess_role_relevance(job, preferences)
        provisional = _provisional_assessment(job, eligibility)
        matches_by_id = {match.requirement_id: match for match in ledger.matches}

        critical = [item for item in requirements if item.criticality.value == "critical"]
        important = [item for item in requirements if item.criticality.value == "important"]
        supporting = [item for item in requirements if item.criticality.value == "supporting"]

        def met(item: CanonicalRequirement) -> bool:
            return matches_by_id[item.requirement_id].status is RequirementMatchStatus.MATCHED

        severe_level_mismatch = _severe_level_mismatch(job, preferences)
        decision = evaluate_grade(
            GradingContext(
                eligibility=eligibility.status,
                role_relevant=role.relevant,
                critical_requirements_total=len(critical),
                critical_requirements_met=sum(met(item) for item in critical),
                important_requirements_total=len(important),
                important_requirements_met=sum(met(item) for item in important),
                supporting_requirements_total=len(supporting),
                supporting_requirements_met=sum(met(item) for item in supporting),
                severe_level_mismatch=severe_level_mismatch,
                insufficient_critical_depth=any(
                    matches_by_id[item.requirement_id].evidence_quality.value
                    in {"transferable", "reviewed_skill", "coursework_context"}
                    for item in critical
                    if matches_by_id[item.requirement_id].status is RequirementMatchStatus.MATCHED
                ),
                insufficient_important_depth=any(
                    matches_by_id[item.requirement_id].evidence_quality.value
                    in {"transferable", "reviewed_skill", "coursework_context"}
                    for item in important
                    if matches_by_id[item.requirement_id].status is RequirementMatchStatus.MATCHED
                ),
                role_strength=role.score,
                provisional=provisional.is_provisional,
                adjacent_scope=(
                    _adjacent_scope(job, preferences)
                    or (
                        provisional.is_provisional
                        and _title_exact_match(job, preferences)
                        and bool(
                            re.search(
                                r"\b(?:shortened|available copy|details? .*unresolved)\b",
                                job.description.casefold(),
                            )
                        )
                    )
                ),
                incomplete_scope_uncertainty=(
                    provisional.is_provisional
                    and (
                        job.requirements.job_level.value == "unknown"
                        and not _title_exact_match(job, preferences)
                    )
                ),
            )
        )
        diagnostics = _diagnostics(
            requirements,
            ledger,
            role,
            job,
            preferences,
            as_of,
        )
        positive_reasons, material_gaps = _explanations(requirements, ledger)
        unresolved = _unresolved_facts(eligibility, provisional)
        return JobEvaluation(
            job_id=job.id,
            eligibility=eligibility,
            role_relevance=role,
            requirements=requirements,
            matches=ledger.matches,
            fit_grade=decision.grade,
            diagnostics=diagnostics,
            provisional=provisional,
            caps=decision.caps,
            positive_reasons=positive_reasons,
            material_gaps=material_gaps,
            unresolved_facts=unresolved,
        )


def assess_role_relevance(
    job: DiscoveredJob, preferences: JobSearchPreferences
) -> RoleRelevanceAssessment:
    title = job.title.casefold()
    description = job.description.casefold()
    classification = classify_role_signals(job.title, job.description)
    title_evidence = [f"role:title:{job.title}"] if classification.primary_family else []
    responsibility_lines = [
        line.strip()
        for line in re.split(r"[.!?\n]+", description)
        if line.strip()
        and re.search(
            r"\b(build|design|develop|implement|maintain|test|analyze|deploy|integrate|verify|validate|own|curate|train|compare|work|coordinate|investigate|improve|partner|expand|reproduce|connect|use|execute|prepare|trace|package|review|commission|operate|support)\b",
            line,
        )
    ]
    responsibility_evidence = [f"role:responsibility:{line}" for line in responsibility_lines[:5]]
    target_terms = [
        normalize_job_term(value)
        for value in [*preferences.target_titles, *preferences.related_title_variants]
    ]
    normalized_title = normalize_job_term(job.title)
    title_match = any(
        term and (term in normalized_title or normalized_title in term) for term in target_terms
    )
    ignored_title_tokens = {
        "engineer",
        "engineering",
        "software",
        "systems",
        "system",
        "data",
        "developer",
        "senior",
        "junior",
        "staff",
        "principal",
        "lead",
        "level",
        "test",
        "testing",
    }
    target_core = {
        token
        for term in target_terms
        for token in term.split()
        if len(token) >= 4 and token not in ignored_title_tokens
    }
    title_context_match = any(
        any(token[:5] == title_token[:5] for title_token in normalized_title.split())
        for token in target_core
    )
    function_context_match = any(token in description for token in target_core)
    adjacent_family = "machine learning" in title and not any(
        "machine learning" in term or "ml" in term for term in target_terms
    )
    family_match = bool(job.role_family and job.role_family in preferences.role_family_priority)
    title_function_trap = bool(
        re.search(
            r"\b(program manager|operations coordinator|coordinator|consultant|product manager)\b",
            title,
        )
    )
    engineering_responsibility = bool(responsibility_lines)
    role_signal = classification.primary_family is not None
    relevant = (
        (
            title_match
            or title_context_match
            or function_context_match
            or family_match
            or role_signal
        )
        and engineering_responsibility
        and not title_function_trap
    )
    if not responsibility_lines and (title_match or family_match):
        relevant = not title_function_trap
    score = min(
        1.0,
        (0.45 if title_match else 0.0)
        + (0.45 if title_context_match and not title_match else 0.0)
        + (0.3 if responsibility_lines else 0.0)
        + (0.2 if family_match else 0.0)
        + (0.45 if function_context_match and not title_context_match else 0.0)
        + (0.05 if role_signal else 0.0),
    )
    if adjacent_family:
        score = max(0.0, score - 0.3)
    mismatches = ["role:title:function-mismatch"] if title_function_trap else []
    if not relevant:
        mismatches.extend(["role:title", "role:responsibilities"])
    return RoleRelevanceAssessment(
        relevant=relevant,
        score=score,
        title_evidence=title_evidence,
        responsibility_evidence=responsibility_evidence,
        team_function_evidence=[f"role:family:{classification.primary_family.value}"]
        if classification.primary_family
        else [],
        contextual_evidence=[f"role:context:{signal.id}" for signal in classification.signals],
        mismatch_references=sorted(set(mismatches)),
    )


def _provisional_assessment(
    job: DiscoveredJob, eligibility: EligibilityAssessment
) -> ProvisionalAssessment:
    codes: list[str] = []
    facts = list(eligibility.unresolved_facts)
    if job.completeness or not job.description.strip():
        codes.append("incomplete_posting")
    if eligibility.status is EligibilityStatus.UNKNOWN:
        codes.append("unknown_eligibility")
    if job.posted_at is None:
        codes.append("missing_posting_date")
    return ProvisionalAssessment(
        is_provisional=bool(codes),
        reason_codes=sorted(set(codes)),
        unresolved_facts=facts,
    )


def _severe_level_mismatch(job: DiscoveredJob, preferences: JobSearchPreferences) -> bool:
    level = job.requirements.job_level.value
    if level == "unknown" or not preferences.job_levels:
        return False
    desired = {item.value for item in preferences.job_levels}
    severe = {"staff", "principal", "director", "executive"}
    return level in severe and not desired.intersection(severe)


def _title_exact_match(job: DiscoveredJob, preferences: JobSearchPreferences) -> bool:
    title = normalize_job_term(job.title)
    return any(
        value and (value in title or title in value)
        for value in [
            normalize_job_term(item)
            for item in [*preferences.target_titles, *preferences.related_title_variants]
        ]
    )


def _adjacent_scope(job: DiscoveredJob, preferences: JobSearchPreferences) -> bool:
    title = normalize_job_term(job.title)
    targets = " ".join(
        normalize_job_term(item)
        for item in [*preferences.target_titles, *preferences.related_title_variants]
    )
    return bool(
        ("platform" in title and "platform" not in targets)
        or ("perception" in title and "perception" not in targets and "vision" not in targets)
        or ("driver" in title and "driver" not in targets)
        or ("robot" in title and "robot" not in targets)
        or ("controls" in title and "controls" not in targets)
        or (
            "verification and test" in title and "test" not in targets and "verification" in targets
        )
    )


def _diagnostics(
    requirements: list[CanonicalRequirement],
    ledger: EvidenceLedger,
    role: RoleRelevanceAssessment,
    job: DiscoveredJob,
    preferences: JobSearchPreferences,
    as_of: datetime,
) -> InternalDiagnostics:
    by_id = {match.requirement_id: match for match in ledger.matches}
    total = len(requirements)
    demonstrated = sum(
        match.scored and match.evidence_quality.value == "demonstrated" for match in ledger.matches
    )
    important = [
        item for item in requirements if item.criticality.value in {"critical", "important"}
    ]
    important_met = sum(
        by_id[item.requirement_id].status is RequirementMatchStatus.MATCHED for item in important
    )
    technical = 30.0 * demonstrated / total if total else 0.0
    required = 40.0 * important_met / len(important) if important else 0.0
    role_alignment = 20.0 * role.score
    level_alignment = (
        5.0
        if not preferences.job_levels or job.requirements.job_level.value == "unknown"
        else 5.0
        if job.requirements.job_level in preferences.job_levels
        else 0.0
    )
    recency = (
        2.5
        if job.posted_at is None or preferences.max_posting_age_days is None
        else 2.5
        if (as_of - job.posted_at).days <= preferences.max_posting_age_days
        else 0.0
    )
    completeness = 2.5 if job.description.strip() and not job.completeness else 0.0
    values = {
        "demonstrated_technical_evidence": round(technical, 2),
        "required_coverage": round(required, 2),
        "role_alignment": round(role_alignment, 2),
        "level_alignment": round(level_alignment, 2),
        "education_coursework": 0.0,
        "preferred_skill_alignment": 0.0,
        "recency_completeness": round(recency + completeness, 2),
    }
    return InternalDiagnostics(**values, total=round(sum(values.values()), 2))


def _explanations(
    requirements: list[CanonicalRequirement], ledger: EvidenceLedger
) -> tuple[list[PositiveReason], list[MaterialGap]]:
    by_id = {match.requirement_id: match for match in ledger.matches}
    reasons: list[PositiveReason] = []
    gaps: list[MaterialGap] = []
    for requirement in requirements:
        match = by_id[requirement.requirement_id]
        if match.status is RequirementMatchStatus.MATCHED and match.allocated_evidence_id:
            reasons.append(
                PositiveReason(
                    code="requirement_match",
                    statement=f"Evidence demonstrates {requirement.term} for this role.",
                    posting_references=[requirement.requirement_id],
                    profile_references=[match.allocated_evidence_id],
                )
            )
        elif match.status in {
            RequirementMatchStatus.INSUFFICIENT,
            RequirementMatchStatus.UNRESOLVED,
        }:
            authority = [requirement.requirement_id, *match.authority_references]
            gaps.append(
                MaterialGap(
                    code="insufficient_requirement",
                    statement=(
                        f"The posting requires {requirement.term}, but the reviewed evidence "
                        "is insufficient."
                    ),
                    posting_references=[requirement.requirement_id],
                    authority_references=sorted(set(authority)),
                )
            )
        else:
            gaps.append(
                MaterialGap(
                    code="missing_requirement",
                    statement=f"No reviewed evidence was found for required {requirement.term}.",
                    posting_references=[requirement.requirement_id],
                    authority_references=[requirement.requirement_id],
                )
            )
    return reasons, gaps


def _unresolved_facts(
    eligibility: EligibilityAssessment, provisional: ProvisionalAssessment
) -> list[UnresolvedFact]:
    return [
        UnresolvedFact(
            code="eligibility_unresolved",
            statement=fact,
            posting_references=["eligibility:posting"],
            profile_references=eligibility.profile_references,
        )
        for fact in provisional.unresolved_facts
    ]


__all__ = [
    "InternalDiagnostics",
    "JobEvaluation",
    "JobEvaluator",
    "JobEvaluatorProtocol",
    "ProvisionalAssessment",
    "RoleRelevanceAssessment",
    "assess_role_relevance",
]
