from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.job_discovery.benchmark.report import generate_locked_aggregate


@pytest.mark.job_discovery_locked
def test_locked_gate_requires_explicit_authorization() -> None:
    assert os.environ.get("JOB_DISCOVERY_LOCKED_GATE") == "1"


@pytest.mark.job_discovery_locked
def test_authorized_locked_gate_records_aggregate_metrics_only() -> None:
    if os.environ.get("JOB_DISCOVERY_LOCKED_GATE") != "1":
        pytest.skip("locked execution requires explicit environment authorization")
    output = Path("generated/job-discovery/locked-aggregate.json")
    assert not output.exists(), "a prior locked aggregate exists in this branch"
    report = generate_locked_aggregate(output)
    metrics = report["metrics"]
    assert report["case_level_content"] is False
    assert metrics["exact_grade_agreement"] >= 0.85
    assert metrics["exact_or_adjacent_grade_agreement"] >= 0.95
    assert metrics["exact_eligibility_agreement"] >= 0.85
    assert metrics["pairwise_ranking_accuracy"]["pair_micro_accuracy"] >= 0.85
    assert all(value >= 0.80 for value in metrics["top_five_precision"].values())
    assert metrics["hard_ineligible_normal_feed_leakage"]["count"] == 0
    assert metrics["excellent_with_critical_gap_leakage"]["count"] == 0
