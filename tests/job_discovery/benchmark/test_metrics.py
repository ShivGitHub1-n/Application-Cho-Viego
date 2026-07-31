from __future__ import annotations

import json

import pytest

from tests.job_discovery.benchmark.loader import load_pilot_calibration_group_01
from tests.job_discovery.benchmark.metrics import (
    CurrentPrediction,
    MetricCase,
    RankingPair,
    canonical_json,
    categorized_failure_modes,
    eligibility_confusion_matrix,
    exact_or_adjacent_grade_agreement,
    grade_confusion_matrix,
    pairwise_ranking_accuracy,
    per_grade_precision_recall,
    top_five_precision,
    traceable_material_gap_rate,
    traceable_positive_reason_rate,
)


def _case(
    case_id: str,
    *,
    expected_eligibility: str = "eligible",
    proposed_grade: str = "excellent",
    ranking_group: str | None = None,
    apply_worthy: bool = True,
    positive_traceable: bool = True,
) -> MetricCase:
    return MetricCase(
        case_id=case_id,
        scenario_id=ranking_group or f"scenario-{case_id}",
        split="calibration",
        expected_eligibility=expected_eligibility,
        proposed_grade=proposed_grade,
        proposed_provisional=False,
        apply_worthy=apply_worthy,
        ranking_group=ranking_group,
        role_families=["software_engineering"],
        job_level="mid",
        evidence_quality="verified",
        posting_completeness="complete",
        critical_gap=False,
        positive_reason_traceable=positive_traceable,
        material_gap_traceable=True,
    )


def _prediction(
    case_id: str,
    *,
    current_label: str = "strong",
    current_eligibility: str = "eligible",
    rank: int | None = 1,
    failure_categories: list[str] | None = None,
) -> CurrentPrediction:
    return CurrentPrediction(
        case_id=case_id,
        current_label=current_label,
        current_eligibility=current_eligibility,
        provisional=current_label == "provisional",
        legacy_substantive_grade="excellent" if current_label == "provisional" else None,
        rank=rank,
        failure_categories=failure_categories or [],
    )


def test_eligibility_confusion_matrix_is_hand_calculated() -> None:
    cases = [_case("a"), _case("b", expected_eligibility="ineligible")]
    predictions = {
        "a": _prediction("a"),
        "b": _prediction("b", current_eligibility="eligible"),
    }

    assert eligibility_confusion_matrix(cases, predictions) == {
        "eligible": {"eligible": 1, "unknown": 0, "ineligible": 0},
        "unknown": {"eligible": 0, "unknown": 0, "ineligible": 0},
        "ineligible": {"eligible": 1, "unknown": 0, "ineligible": 0},
    }


def test_hard_ineligible_positive_is_not_adjacent_agreement() -> None:
    cases = [_case("a", expected_eligibility="ineligible", proposed_grade="dont_match")]
    predictions = {"a": _prediction("a", current_label="stretch")}

    assert exact_or_adjacent_grade_agreement(cases, predictions) == 0.0


def test_critical_gap_uses_referenced_fact_not_reason_code() -> None:
    cases = {
        case.case_id: case for case in load_pilot_calibration_group_01()
    }
    case010 = cases["calibration-010"]
    case006 = cases["calibration-006"]
    mutated = case010.model_copy(
        update={
            "proposed_material_gap_reasons": [
                reason.model_copy(update={"code": "arbitrary_gap_name"})
                for reason in case010.proposed_material_gap_reasons
            ]
        }
    )
    assert MetricCase.from_benchmark(mutated).critical_gap is True
    assert MetricCase.from_benchmark(case006).critical_gap is False


def test_adjacent_grade_agreement_is_symmetric_for_eligible_cases() -> None:
    cases = [_case("a", proposed_grade="good")]
    predictions = {"a": _prediction("a", current_label="strong")}

    assert exact_or_adjacent_grade_agreement(cases, predictions) == 1.0


def test_pairwise_accuracy_reports_macro_and_micro_values() -> None:
    cases = [
        _case("a", ranking_group="scenario-1"),
        _case("b", ranking_group="scenario-1"),
        _case("c", ranking_group="scenario-1"),
        _case("d", ranking_group="scenario-1"),
        _case("e", ranking_group="scenario-2"),
        _case("f", ranking_group="scenario-2"),
    ]
    predictions = {
        "a": _prediction("a", rank=2),
        "b": _prediction("b", rank=1),
        "c": _prediction("c", rank=3),
        "d": _prediction("d", rank=4),
        "e": _prediction("e", rank=1),
        "f": _prediction("f", rank=2),
    }
    pairs = [
        RankingPair(scenario_id="scenario-1", preferred_case_id="b", other_case_id="a"),
        RankingPair(scenario_id="scenario-1", preferred_case_id="d", other_case_id="c"),
        RankingPair(scenario_id="scenario-2", preferred_case_id="e", other_case_id="f"),
        RankingPair(scenario_id="scenario-2", preferred_case_id="e", other_case_id="f", tied=True),
    ]

    assert pairwise_ranking_accuracy(cases, predictions, pairs) == {
        "scenario_macro_accuracy": 0.75,
        "pair_micro_accuracy": 2 / 3,
        "correct": 2,
        "total": 3,
    }


def test_pairwise_accuracy_rejects_pairs_outside_the_evaluated_cases() -> None:
    cases = [_case("a", ranking_group="scenario-1"), _case("b", ranking_group="scenario-1")]
    predictions = {"a": _prediction("a"), "b": _prediction("b")}

    with pytest.raises(ValueError, match="pair case IDs"):
        pairwise_ranking_accuracy(
            cases,
            predictions,
            [RankingPair(scenario_id="scenario-1", preferred_case_id="a", other_case_id="missing")],
        )


def test_top_five_precision_uses_apply_worthy_labels() -> None:
    cases = [_case(f"c{i}", ranking_group="tailored-1", apply_worthy=i < 2) for i in range(10)]
    predictions = {
        case.case_id: _prediction(case.case_id, rank=index + 1) for index, case in enumerate(cases)
    }

    assert top_five_precision(cases, predictions) == {"tailored-1": 0.4}


def test_top_five_precision_requires_unique_ranks_for_ten_job_groups() -> None:
    cases = [_case(f"c{i}", ranking_group="tailored-1", apply_worthy=i < 2) for i in range(10)]
    predictions = {
        case.case_id: _prediction(case.case_id, rank=1 if index == 1 else index + 1)
        for index, case in enumerate(cases)
    }

    with pytest.raises(ValueError, match="ranks 1 through 10"):
        top_five_precision(cases, predictions)


def test_traceability_and_canonical_json_are_deterministic() -> None:
    cases = [_case("a", positive_traceable=True), _case("b", positive_traceable=False)]

    assert traceable_positive_reason_rate(cases) == 0.5
    assert traceable_material_gap_rate(cases) == 1.0
    payload = {"z": 1, "a": [2, 1]}
    assert canonical_json(payload) == json.dumps(payload, sort_keys=True, separators=(",", ":"))
    with pytest.raises(ValueError):
        canonical_json(float("nan"))


def test_additional_metric_outputs_are_hand_calculated() -> None:
    cases = [_case("a"), _case("b", proposed_grade="good")]
    predictions = {
        "a": _prediction("a", current_label="strong"),
        "b": _prediction("b", current_label="stretch"),
    }

    assert grade_confusion_matrix(cases, predictions)["excellent"]["excellent"] == 1
    assert per_grade_precision_recall(cases, predictions)["excellent"] == {
        "precision": 1.0,
        "recall": 1.0,
    }
    assert categorized_failure_modes(
        {"a": _prediction("a", failure_categories=["keyword_trap"]), "b": _prediction("b")}
    ) == {"keyword_trap": 1}


def test_ordinary_metrics_reject_locked_cases() -> None:
    locked_case = _case("locked")
    locked_case.split = "locked"
    with pytest.raises(ValueError, match="Locked"):
        eligibility_confusion_matrix([locked_case], {"locked": _prediction("locked")})
