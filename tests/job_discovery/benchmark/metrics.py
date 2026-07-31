from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from tests.job_discovery.benchmark.models import BenchmarkCase, FitGrade

Eligibility = Literal["eligible", "unknown", "ineligible"]
CurrentLabel = Literal["strong", "good", "stretch", "provisional", "dont_match"]
_GRADES: tuple[FitGrade, ...] = ("excellent", "good", "weak", "dont_match")
_ELIGIBILITY: tuple[Eligibility, ...] = ("eligible", "unknown", "ineligible")
_ADJACENT: dict[FitGrade, FitGrade | None] = {
    "excellent": "good",
    "good": "weak",
    "weak": "dont_match",
    "dont_match": None,
}


class MetricCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    scenario_id: str
    split: Literal["calibration", "validation", "locked"]
    expected_eligibility: Eligibility
    proposed_grade: FitGrade
    proposed_provisional: bool
    apply_worthy: bool
    ranking_group: str | None = None
    role_families: list[str]
    job_level: str
    posting_level: str = "unknown"
    candidate_target_levels: list[str] = Field(default_factory=list)
    evidence_quality: str
    posting_completeness: str
    critical_gap: bool
    positive_reason_traceable: bool
    material_gap_traceable: bool

    @classmethod
    def from_benchmark(cls, case: BenchmarkCase) -> MetricCase:
        posting_fact_text = " ".join(
            fact.statement.casefold() for fact in case.posting.posting_facts
        )
        incomplete_posting = (
            case.proposed_provisional
            or bool(case.provisional_reason_codes)
            or case.posting.posted_date is None
            or any(
                marker in posting_fact_text
                for marker in ("unknown", "not specified", "not stated", "unresolved", "missing")
            )
        )
        return cls(
            case_id=case.case_id,
            scenario_id=case.scenario_id,
            split=case.split,
            expected_eligibility=case.expected_eligibility,
            proposed_grade=case.proposed_grade,
            proposed_provisional=case.proposed_provisional,
            apply_worthy=case.apply_worthy,
            ranking_group=case.ranking_group,
            role_families=case.preferences.role_families,
            job_level=case.posting.posting_level,
            posting_level=case.posting.posting_level,
            candidate_target_levels=case.preferences.target_levels,
            evidence_quality=case.evidence_assessment.quality,
            posting_completeness="incomplete" if incomplete_posting else "complete",
            critical_gap=_has_critical_gap(case),
            positive_reason_traceable=bool(case.proposed_positive_reasons)
            and all(bool(reason.evidence_references) for reason in case.proposed_positive_reasons),
            material_gap_traceable=bool(case.proposed_material_gap_reasons)
            and all(
                bool(reason.evidence_references)
                for reason in case.proposed_material_gap_reasons
            ),
        )


class CurrentPrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    current_label: CurrentLabel
    current_eligibility: Eligibility
    provisional: bool
    legacy_substantive_grade: FitGrade | None = None
    score: float | None = None
    score_components: dict[str, float] = Field(default_factory=dict)
    rank: int | None = Field(default=None, ge=1)
    failure_categories: list[str] = Field(default_factory=list)
    adapter_failure: str | None = None
    current_explanation_traceable: bool | None = None
    current_explanation_reasons: list[str] = Field(default_factory=list)
    current_explanation_gaps: list[str] = Field(default_factory=list)
    ranking_key: tuple[object, ...] = (0.0, 0, "")


class RankingPair(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    preferred_case_id: str
    other_case_id: str
    tied: bool = False


@dataclass(frozen=True)
class LockedAggregateAuthorization:
    """Non-global authorization token for the dedicated locked aggregate path."""

    marker_enabled: bool
    project_owner_authorized: bool

    @classmethod
    def from_explicit_gate(
        cls, *, marker_enabled: bool, project_owner_authorized: bool
    ) -> LockedAggregateAuthorization:
        if not marker_enabled or not project_owner_authorized:
            raise PermissionError(
                "Locked aggregate metrics require explicit marker and owner authorization"
            )
        return cls(
            marker_enabled=marker_enabled,
            project_owner_authorized=project_owner_authorized,
        )


def _ensure_development(
    cases: list[MetricCase], predictions: Mapping[str, CurrentPrediction] | None = None
) -> None:
    if any(case.split == "locked" for case in cases):
        raise ValueError("Locked benchmark cases are not eligible for ordinary metrics")
    if predictions is not None:
        case_ids = {case.case_id for case in cases}
        missing = case_ids - set(predictions)
        if missing:
            raise ValueError(f"Missing predictions for case IDs: {sorted(missing)}")
        mismatched = [key for key, prediction in predictions.items() if key != prediction.case_id]
        if mismatched:
            raise ValueError("Prediction mapping keys must match prediction case IDs")


def _predictions_by_id(
    predictions: Mapping[str, CurrentPrediction],
) -> dict[str, CurrentPrediction]:
    return dict(predictions)


def _comparison_grade(prediction: CurrentPrediction) -> FitGrade:
    if prediction.current_label == "provisional":
        if prediction.legacy_substantive_grade is None:
            raise ValueError("Current Provisional requires a legacy substantive grade")
        return prediction.legacy_substantive_grade
    return {
        "strong": "excellent",
        "good": "good",
        "stretch": "weak",
        "dont_match": "dont_match",
    }[prediction.current_label]


def eligibility_confusion_matrix(
    cases: list[MetricCase], predictions: Mapping[str, CurrentPrediction]
) -> dict[Eligibility, dict[Eligibility, int]]:
    _ensure_development(cases, predictions)
    result = {expected: {actual: 0 for actual in _ELIGIBILITY} for expected in _ELIGIBILITY}
    for case in cases:
        result[case.expected_eligibility][predictions[case.case_id].current_eligibility] += 1
    return result


def exact_eligibility_agreement(
    cases: list[MetricCase], predictions: Mapping[str, CurrentPrediction]
) -> float:
    _ensure_development(cases, predictions)
    return (
        sum(
            case.expected_eligibility == predictions[case.case_id].current_eligibility
            for case in cases
        )
        / len(cases)
        if cases
        else 0.0
    )


def grade_confusion_matrix(
    cases: list[MetricCase], predictions: Mapping[str, CurrentPrediction]
) -> dict[FitGrade, dict[FitGrade, int]]:
    _ensure_development(cases, predictions)
    result = {expected: {actual: 0 for actual in _GRADES} for expected in _GRADES}
    for case in cases:
        result[case.proposed_grade][_comparison_grade(predictions[case.case_id])] += 1
    return result


def exact_grade_agreement(
    cases: list[MetricCase], predictions: Mapping[str, CurrentPrediction]
) -> float:
    _ensure_development(cases, predictions)
    return (
        sum(case.proposed_grade == _comparison_grade(predictions[case.case_id]) for case in cases)
        / len(cases)
        if cases
        else 0.0
    )


def exact_or_adjacent_grade_agreement(
    cases: list[MetricCase], predictions: Mapping[str, CurrentPrediction]
) -> float:
    _ensure_development(cases, predictions)
    matched = 0
    for case in cases:
        actual = _comparison_grade(predictions[case.case_id])
        if case.expected_eligibility == "ineligible" and actual != "dont_match":
            continue
        expected_index = _GRADES.index(case.proposed_grade)
        actual_index = _GRADES.index(actual)
        if abs(expected_index - actual_index) <= 1:
            matched += 1
    return matched / len(cases) if cases else 0.0


def per_grade_precision_recall(
    cases: list[MetricCase], predictions: Mapping[str, CurrentPrediction]
) -> dict[FitGrade, dict[str, float]]:
    matrix = grade_confusion_matrix(cases, predictions)
    result: dict[FitGrade, dict[str, float]] = {}
    for grade in _GRADES:
        true_positive = matrix[grade][grade]
        predicted = sum(matrix[expected][grade] for expected in _GRADES)
        actual = sum(matrix[grade].values())
        result[grade] = {
            "precision": true_positive / predicted if predicted else 0.0,
            "recall": true_positive / actual if actual else 0.0,
        }
    return result


def false_excellent_cases(
    cases: list[MetricCase], predictions: Mapping[str, CurrentPrediction]
) -> list[str]:
    _ensure_development(cases, predictions)
    return sorted(
        case.case_id
        for case in cases
        if _comparison_grade(predictions[case.case_id]) == "excellent"
        and case.proposed_grade != "excellent"
    )


def hard_ineligible_normal_feed_leakage(
    cases: list[MetricCase], predictions: Mapping[str, CurrentPrediction]
) -> dict[str, Any]:
    _ensure_development(cases, predictions)
    leaked = sorted(
        case.case_id
        for case in cases
        if case.expected_eligibility == "ineligible"
        and _comparison_grade(predictions[case.case_id]) != "dont_match"
    )
    return {"count": len(leaked), "case_ids": leaked}


def excellent_with_critical_gap_leakage(
    cases: list[MetricCase], predictions: Mapping[str, CurrentPrediction]
) -> dict[str, Any]:
    _ensure_development(cases, predictions)
    leaked = sorted(
        case.case_id
        for case in cases
        if case.critical_gap and _comparison_grade(predictions[case.case_id]) == "excellent"
    )
    return {"count": len(leaked), "case_ids": leaked}


def provisional_agreement(
    cases: list[MetricCase], predictions: Mapping[str, CurrentPrediction]
) -> float:
    _ensure_development(cases, predictions)
    return (
        sum(case.proposed_provisional == predictions[case.case_id].provisional for case in cases)
        / len(cases)
        if cases
        else 0.0
    )


def pairwise_ranking_accuracy(
    cases: list[MetricCase],
    predictions: Mapping[str, CurrentPrediction],
    pairs: list[RankingPair],
) -> dict[str, float | int]:
    _ensure_development(cases, predictions)
    case_by_id = {case.case_id: case for case in cases}
    by_scenario: dict[str, list[bool]] = defaultdict(list)
    for pair in pairs:
        if pair.tied:
            continue
        if (
            pair.preferred_case_id not in case_by_id
            or pair.other_case_id not in case_by_id
            or case_by_id[pair.preferred_case_id].scenario_id != pair.scenario_id
            or case_by_id[pair.other_case_id].scenario_id != pair.scenario_id
        ):
            raise ValueError("Ranking pair case IDs and scenario_id must match evaluated cases")
        preferred = predictions[pair.preferred_case_id].rank
        other = predictions[pair.other_case_id].rank
        if preferred is None or other is None:
            continue
        by_scenario[pair.scenario_id].append(preferred < other)
    all_results = [value for values in by_scenario.values() for value in values]
    scenario_scores = [sum(values) / len(values) for values in by_scenario.values() if values]
    return {
        "scenario_macro_accuracy": sum(scenario_scores) / len(scenario_scores)
        if scenario_scores
        else 0.0,
        "pair_micro_accuracy": sum(all_results) / len(all_results) if all_results else 0.0,
        "correct": sum(all_results),
        "total": len(all_results),
    }


def top_five_precision(
    cases: list[MetricCase], predictions: Mapping[str, CurrentPrediction]
) -> dict[str, float]:
    _ensure_development(cases, predictions)
    groups: dict[str, list[MetricCase]] = defaultdict(list)
    for case in cases:
        if case.ranking_group:
            groups[case.ranking_group].append(case)
    result: dict[str, float] = {}
    for group, group_cases in sorted(groups.items()):
        if len(group_cases) != 10:
            raise ValueError("Tailored ranking groups must contain exactly ten cases")
        ranks = [predictions[case.case_id].rank for case in group_cases]
        if set(ranks) != set(range(1, 11)):
            raise ValueError("Tailored ranking groups require unique ranks 1 through 10")
        top_five = [case for case in group_cases if predictions[case.case_id].rank <= 5]
        result[group] = sum(case.apply_worthy for case in top_five) / 5
    return result


def traceable_positive_reason_rate(cases: list[MetricCase]) -> float:
    _ensure_development(cases)
    return sum(case.positive_reason_traceable for case in cases) / len(cases) if cases else 0.0


def traceable_material_gap_rate(cases: list[MetricCase]) -> float:
    _ensure_development(cases)
    return sum(case.material_gap_traceable for case in cases) / len(cases) if cases else 0.0


def _reference_texts(case: BenchmarkCase) -> dict[str, str]:
    references = {
        item.evidence_id: item.statement for item in case.profile.evidence_items
    }
    references.update(
        {fact.fact_id: fact.statement for fact in case.posting.posting_facts}
    )
    references.update(
        {
            (
                item.requirement_id
                if hasattr(item, "requirement_id")
                else item.qualification_id
            ): item.text
            for item in [
                *case.critical_requirements,
                *case.required_qualifications,
                *case.preferred_qualifications,
            ]
        }
    )
    references.update(
        {
            f"profile:{case.profile.profile_ref}:experience-years": (
                f"profile experience years {case.profile.experience_years:g}"
            ),
            f"profile:{case.profile.profile_ref}:education": case.profile.education_summary,
            f"profile:{case.profile.profile_ref}:professional-license-status": (
                case.profile.professional_license_status
            ),
            f"profile:{case.profile.profile_ref}:clearance-status": case.profile.clearance_status,
            f"preferences:{case.profile.profile_ref}:work_authorization": (
                f"authorized work locations {', '.join(case.profile.authorized_work_locations)}; "
                f"requires sponsorship {case.profile.requires_sponsorship}"
            ),
            f"preferences:{case.profile.profile_ref}:target_level": (
                f"candidate target levels {', '.join(case.preferences.target_levels)}"
            ),
        }
    )
    return references


def _critical_requirement_fact_ids(case: BenchmarkCase) -> set[str]:
    return {
        item.fact_id or item.requirement_id
        for item in case.critical_requirements
    }


def _has_critical_gap(case: BenchmarkCase) -> bool:
    return bool(_critical_gap_fact_ids(case))


def _critical_gap_fact_ids(case: BenchmarkCase) -> set[str]:
    critical_ids = _critical_requirement_fact_ids(case)
    if not critical_ids:
        return set()
    gap_refs = {
        reference
        for reason in case.proposed_material_gap_reasons
        for reference in reason.evidence_references
    }
    if critical_ids & gap_refs:
        return critical_ids & gap_refs
    return {
        item.fact_id or item.requirement_id
        for item in case.critical_requirements
        if not item.evidence_references
    }


def critical_gap_fact_ids(case: BenchmarkCase) -> list[str]:
    return sorted(_critical_gap_fact_ids(case))


def _reference_group_metrics(cases: list[BenchmarkCase], attribute: str) -> dict[str, float | int]:
    reasons = [reason for case in cases for reason in getattr(case, attribute)]
    complete = sum(bool(reason.evidence_references) for reason in reasons)
    references = {_case.case_id: _reference_texts(_case) for _case in cases}
    valid = sum(
        (
            _reason_structurally_valid(case, reason, attribute, references[case.case_id])
        )
        for case in cases
        for reason in getattr(case, attribute)
    )
    total = len(reasons)
    return {
        "complete": complete,
        "valid": valid,
        "total": total,
        "completeness_rate": complete / total if total else 0.0,
        "validity_rate": valid / total if total else 0.0,
    }


def _reason_structurally_valid(
    case: BenchmarkCase,
    reason: object,
    attribute: str,
    references: dict[str, str],
) -> bool:
    reason_refs = getattr(reason, "evidence_references", [])
    if not reason_refs or any(reference not in references for reference in reason_refs):
        return False
    profile_refs = {
        *[item.evidence_id for item in case.profile.evidence_items],
        f"profile:{case.profile.profile_ref}:experience-years",
        f"profile:{case.profile.profile_ref}:education",
        f"profile:{case.profile.profile_ref}:professional-license-status",
        f"profile:{case.profile.profile_ref}:clearance-status",
        f"preferences:{case.profile.profile_ref}:work_authorization",
        f"preferences:{case.profile.profile_ref}:target_level",
    }
    posting_refs = {
        fact.fact_id for fact in case.posting.posting_facts
    } | {
        item.requirement_id
        for item in case.critical_requirements
    } | {
        item.qualification_id
        for item in [
            *case.required_qualifications,
            *case.preferred_qualifications,
        ]
    }
    has_profile = bool(set(reason_refs) & profile_refs)
    has_posting = bool(set(reason_refs) & posting_refs)
    if attribute == "proposed_positive_reasons":
        return has_profile and has_posting
    if attribute == "proposed_eligibility_reasons":
        return has_profile and has_posting
    if attribute == "proposed_material_gap_reasons":
        statement = getattr(reason, "statement", "").casefold()
        requires_existing_evidence = any(
            marker in statement
            for marker in ("insufficient", "reviewed-only", "reviewed only")
        )
        return has_posting and (has_profile if requires_existing_evidence else True)
    return False


def _qualification_coverage(cases: list[BenchmarkCase]) -> dict[str, float | int]:
    total = 0
    covered = 0
    for case in cases:
        gap_refs = {
            reference
            for reason in case.proposed_material_gap_reasons
            for reference in reason.evidence_references
        }
        for item in [
            *case.critical_requirements,
            *case.required_qualifications,
        ]:
            total += 1
            fact_id = item.fact_id or (
                item.requirement_id
                if hasattr(item, "requirement_id")
                else item.qualification_id
            )
            if item.evidence_references or fact_id in gap_refs:
                covered += 1
    return {
        "total": total,
        "covered": covered,
        "coverage_rate": covered / total if total else 0.0,
    }


def proposed_reference_structural_validity(cases: list[BenchmarkCase]) -> dict[str, object]:
    """Check reference structure; semantic correctness remains a human decision."""

    groups = {
        "positive_reasons": _reference_group_metrics(cases, "proposed_positive_reasons"),
        "gap_reasons": _reference_group_metrics(cases, "proposed_material_gap_reasons"),
        "eligibility_reasons": _reference_group_metrics(cases, "proposed_eligibility_reasons"),
    }
    total = sum(int(group["total"]) for group in groups.values())
    complete = sum(int(group["complete"]) for group in groups.values())
    valid = sum(int(group["valid"]) for group in groups.values())
    return {
        **groups,
        "qualification_coverage": _qualification_coverage(cases),
        "complete": complete,
        "valid": valid,
        "total": total,
        "completeness_rate": complete / total if total else 0.0,
        "validity_rate": valid / total if total else 0.0,
    }


def current_explanation_heuristic_traceability(
    predictions: Mapping[str, CurrentPrediction],
) -> float | None:
    measured = [
        prediction.current_explanation_traceable
        for prediction in predictions.values()
        if prediction.current_explanation_traceable is not None
    ]
    return sum(measured) / len(measured) if measured else None


def results_by_dimension(
    cases: list[MetricCase], predictions: Mapping[str, CurrentPrediction]
) -> dict[str, dict[str, dict[str, float | int]]]:
    _ensure_development(cases, predictions)
    dimensions: dict[str, dict[str, list[MetricCase]]] = {
        "role_family": defaultdict(list),
        "job_level": defaultdict(list),
        "evidence_quality": defaultdict(list),
        "posting_completeness": defaultdict(list),
    }
    for case in cases:
        for family in case.role_families:
            dimensions["role_family"][family].append(case)
        dimensions["job_level"][case.job_level].append(case)
        dimensions["evidence_quality"][case.evidence_quality].append(case)
        dimensions["posting_completeness"][case.posting_completeness].append(case)
    return {
        dimension: {
            key: {
                "count": len(group),
                "exact_grade_agreement": exact_grade_agreement(group, predictions),
                "exact_eligibility_agreement": exact_eligibility_agreement(group, predictions),
            }
            for key, group in sorted(groups.items())
        }
        for dimension, groups in dimensions.items()
    }


def categorized_failure_modes(predictions: Mapping[str, CurrentPrediction]) -> dict[str, int]:
    counts = Counter(
        category
        for prediction in predictions.values()
        for category in prediction.failure_categories
    )
    return dict(sorted(counts.items()))


def calculate_quality_metrics(
    cases: list[MetricCase],
    predictions: Mapping[str, CurrentPrediction],
    pairs: list[RankingPair] | None = None,
) -> dict[str, Any]:
    _ensure_development(cases, predictions)
    result: dict[str, Any] = {
        "eligibility_confusion_matrix": eligibility_confusion_matrix(cases, predictions),
        "exact_eligibility_agreement": exact_eligibility_agreement(cases, predictions),
        "grade_confusion_matrix": grade_confusion_matrix(cases, predictions),
        "exact_grade_agreement": exact_grade_agreement(cases, predictions),
        "exact_or_adjacent_grade_agreement": exact_or_adjacent_grade_agreement(cases, predictions),
        "per_grade_precision_recall": per_grade_precision_recall(cases, predictions),
        "false_excellent_cases": false_excellent_cases(cases, predictions),
        "hard_ineligible_normal_feed_leakage": hard_ineligible_normal_feed_leakage(
            cases, predictions
        ),
        "excellent_with_critical_gap_leakage": excellent_with_critical_gap_leakage(
            cases, predictions
        ),
        "provisional_agreement": provisional_agreement(cases, predictions),
        "top_five_precision": top_five_precision(cases, predictions),
        "proposed_reason_reference_completeness": traceable_positive_reason_rate(cases),
        "proposed_material_gap_reference_completeness": traceable_material_gap_rate(cases),
        "results_by_dimension": results_by_dimension(cases, predictions),
        "failure_modes": categorized_failure_modes(predictions),
    }
    if pairs is not None:
        result["pairwise_ranking_accuracy"] = pairwise_ranking_accuracy(cases, predictions, pairs)
    return result


def calculate_locked_quality_metrics(
    cases: list[MetricCase],
    predictions: Mapping[str, CurrentPrediction],
    pairs: list[RankingPair] | None = None,
    *,
    authorization: LockedAggregateAuthorization | None,
) -> dict[str, Any]:
    """Calculate locked metrics only through an explicit aggregate scope.

    The public development function deliberately rejects locked cases. This
    separate entry point validates a local authorization token, creates
    development-shaped metric views without exposing them, and returns only
    the shared aggregate metrics needed by the locked gate.
    """

    if authorization is None:
        raise PermissionError("Locked aggregate metrics require explicit authorization")
    if not authorization.marker_enabled or not authorization.project_owner_authorized:
        raise PermissionError("Locked aggregate metrics authorization is invalid")
    if not cases or any(case.split != "locked" for case in cases):
        raise ValueError("Locked aggregate metrics require locked cases only")

    metric_views = [case.model_copy(update={"split": "validation"}) for case in cases]
    return calculate_quality_metrics(metric_views, predictions, pairs)


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


__all__ = [
    "CurrentPrediction",
    "LockedAggregateAuthorization",
    "MetricCase",
    "RankingPair",
    "calculate_quality_metrics",
    "calculate_locked_quality_metrics",
    "canonical_json",
    "categorized_failure_modes",
    "eligibility_confusion_matrix",
    "exact_eligibility_agreement",
    "exact_grade_agreement",
    "exact_or_adjacent_grade_agreement",
    "excellent_with_critical_gap_leakage",
    "false_excellent_cases",
    "grade_confusion_matrix",
    "hard_ineligible_normal_feed_leakage",
    "pairwise_ranking_accuracy",
    "per_grade_precision_recall",
    "provisional_agreement",
    "results_by_dimension",
    "top_five_precision",
    "traceable_material_gap_rate",
    "traceable_positive_reason_rate",
    "proposed_reference_structural_validity",
    "critical_gap_fact_ids",
    "current_explanation_heuristic_traceability",
]
