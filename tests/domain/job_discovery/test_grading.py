from __future__ import annotations

from resume_tailor.domain.job_discovery.grading import (
    FitGrade,
    GradeCap,
    GradingContext,
    evaluate_grade,
)
from resume_tailor.domain.job_discovery.models import EligibilityStatus


def test_hard_ineligibility_caps_grade_without_replacing_provisional_status() -> None:
    decision = evaluate_grade(
        GradingContext(
            eligibility=EligibilityStatus.INELIGIBLE,
            role_relevant=True,
            critical_requirements_total=1,
            critical_requirements_met=1,
            important_requirements_total=0,
            important_requirements_met=0,
            severe_level_mismatch=False,
            provisional=True,
        )
    )

    assert decision.grade is FitGrade.DONT_MATCH
    assert decision.provisional is True
    assert any(cap.rule_id == "eligibility.hard_conflict" for cap in decision.caps)


def test_missing_critical_requirement_can_never_be_excellent() -> None:
    decision = evaluate_grade(
        GradingContext(
            eligibility=EligibilityStatus.ELIGIBLE,
            role_relevant=True,
            critical_requirements_total=2,
            critical_requirements_met=1,
            important_requirements_total=0,
            important_requirements_met=0,
            severe_level_mismatch=False,
            provisional=False,
        )
    )

    assert decision.grade is not FitGrade.EXCELLENT
    assert any(cap.rule_id == "fit.missing_critical" for cap in decision.caps)
    assert all(isinstance(cap, GradeCap) for cap in decision.caps)
