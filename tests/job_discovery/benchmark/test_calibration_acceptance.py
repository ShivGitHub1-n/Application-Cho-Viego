from __future__ import annotations

from tests.job_discovery.benchmark.report import generate_policy_evaluation


def test_frozen_calibration_meets_batch_two_acceptance_gates() -> None:
    report = generate_policy_evaluation("calibration")
    metrics = report["metrics"]

    assert metrics["exact_grade_agreement"] >= 0.85
    assert metrics["exact_or_adjacent_grade_agreement"] >= 0.95
    assert metrics["exact_eligibility_agreement"] >= 0.85
    assert metrics["pairwise_ranking_accuracy"]["pair_micro_accuracy"] >= 0.85
    assert all(value >= 0.80 for value in metrics["top_five_precision"].values())
    assert metrics["hard_ineligible_normal_feed_leakage"]["count"] == 0
    assert metrics["excellent_with_critical_gap_leakage"]["count"] == 0
    assert report["traceability"]["positive_reason_rate"] == 1.0
    assert report["traceability"]["material_gap_rate"] == 1.0
