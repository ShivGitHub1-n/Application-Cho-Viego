"""Deterministic monotone fit-grade policy and typed caps."""

from __future__ import annotations

from pydantic import BaseModel, Field

from resume_tailor.domain.job_discovery.models import (
    EligibilityStatus,
    FitGrade,
)

EVALUATION_POLICY_VERSION = "jobs-fit-v2.1-calibrated"


class GradeCap(BaseModel):
    rule_id: str
    reason: str
    authority_references: list[str] = Field(min_length=1)
    maximum_grade: FitGrade


class GradingContext(BaseModel):
    eligibility: EligibilityStatus
    role_relevant: bool
    critical_requirements_total: int = 0
    critical_requirements_met: int = 0
    important_requirements_total: int = 0
    important_requirements_met: int = 0
    supporting_requirements_total: int = 0
    supporting_requirements_met: int = 0
    severe_level_mismatch: bool = False
    insufficient_critical_depth: bool = False
    insufficient_important_depth: bool = False
    role_strength: float = 0.0
    provisional: bool = False
    adjacent_scope: bool = False
    incomplete_scope_uncertainty: bool = False


class GradeDecision(BaseModel):
    grade: FitGrade
    provisional: bool
    caps: list[GradeCap] = Field(default_factory=list)
    diagnostic_total: float = 0.0


def evaluate_grade(context: GradingContext) -> GradeDecision:
    caps: list[GradeCap] = []
    grade = FitGrade.WEAK

    if context.eligibility is EligibilityStatus.INELIGIBLE:
        caps.append(
            GradeCap(
                rule_id="eligibility.hard_conflict",
                reason=(
                    "A known eligibility conflict prevents this opportunity from being "
                    "eligible."
                ),
                authority_references=["eligibility:conflict"],
                maximum_grade=FitGrade.DONT_MATCH,
            )
        )
        grade = FitGrade.DONT_MATCH
    elif not context.role_relevant:
        caps.append(
            GradeCap(
                rule_id="role.severe_irrelevance",
                reason=(
                    "The title and substantive responsibilities do not describe a "
                    "relevant role."
                ),
                authority_references=["role:title", "role:responsibilities"],
                maximum_grade=FitGrade.DONT_MATCH,
            )
        )
        grade = FitGrade.DONT_MATCH
    elif context.severe_level_mismatch:
        caps.append(
            GradeCap(
                rule_id="level.severe_scope_mismatch",
                reason="The posting scope is materially outside the reviewed target level.",
                authority_references=["role:level", "profile:target-level"],
                maximum_grade=FitGrade.DONT_MATCH,
            )
        )
        grade = FitGrade.DONT_MATCH
    elif context.critical_requirements_total > context.critical_requirements_met:
        caps.append(
            GradeCap(
                rule_id="fit.missing_critical",
                reason="At least one critical requirement is missing or insufficient.",
                authority_references=["requirement:critical"],
                maximum_grade=FitGrade.WEAK,
            )
        )
        grade = FitGrade.DONT_MATCH
    elif context.incomplete_scope_uncertainty:
        caps.append(
            GradeCap(
                rule_id="posting.incomplete_scope_uncertainty",
                reason="Incomplete posting authority leaves the role scope materially unresolved.",
                authority_references=["posting:scope", "posting:level"],
                maximum_grade=FitGrade.WEAK,
            )
        )
        grade = FitGrade.WEAK
    elif context.adjacent_scope:
        caps.append(
            GradeCap(
                rule_id="role.adjacent_scope",
                reason=(
                    "The role sits at an adjacent responsibility boundary despite "
                    "overlapping terminology."
                ),
                authority_references=["role:title", "role:responsibilities"],
                maximum_grade=FitGrade.GOOD,
            )
        )
        grade = FitGrade.GOOD
    elif context.insufficient_critical_depth:
        caps.append(
            GradeCap(
                rule_id="fit.critical_depth",
                reason="Critical production depth is not demonstrated at the required level.",
                authority_references=["requirement:critical", "profile:evidence"],
                maximum_grade=FitGrade.WEAK,
            )
        )
        grade = FitGrade.WEAK
    elif context.insufficient_important_depth:
        caps.append(
            GradeCap(
                rule_id="fit.important_depth",
                reason=(
                    "A required non-critical responsibility is supported only by "
                    "transferable or contextual evidence."
                ),
                authority_references=["requirement:important", "profile:evidence"],
                maximum_grade=FitGrade.WEAK,
            )
        )
        grade = FitGrade.WEAK
    elif context.important_requirements_met < context.important_requirements_total:
        caps.append(
            GradeCap(
                rule_id="fit.required_noncritical_gap",
                reason="A required non-critical requirement remains a material gap.",
                authority_references=["requirement:important"],
                maximum_grade=FitGrade.GOOD,
            )
        )
        missing_important = (
            context.important_requirements_total - context.important_requirements_met
        )
        grade = (
            FitGrade.GOOD
            if missing_important == 1 and context.role_strength >= 0.45
            else FitGrade.WEAK
        )
    elif context.role_strength >= 0.8:
        grade = FitGrade.EXCELLENT
    else:
        grade = FitGrade.GOOD

    diagnostic_total = round(
        100.0
        * (
            (context.critical_requirements_met / context.critical_requirements_total)
            if context.critical_requirements_total
            else 0.0
        )
        * 0.6
        + 40.0
        * (
            (context.important_requirements_met / context.important_requirements_total)
            if context.important_requirements_total
            else 1.0
        )
        * 0.4,
        2,
    )
    return GradeDecision(
        grade=grade,
        provisional=context.provisional,
        caps=caps,
        diagnostic_total=diagnostic_total,
    )


def grade_rank(grade: FitGrade) -> int:
    return {
        FitGrade.EXCELLENT: 0,
        FitGrade.GOOD: 1,
        FitGrade.WEAK: 2,
        FitGrade.DONT_MATCH: 3,
    }[grade]


__all__ = [
    "EVALUATION_POLICY_VERSION",
    "FitGrade",
    "GradeCap",
    "GradeDecision",
    "GradingContext",
    "evaluate_grade",
    "grade_rank",
]
