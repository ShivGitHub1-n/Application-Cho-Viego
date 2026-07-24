from __future__ import annotations

import json

import pytest

from tests.job_discovery.benchmark.metrics import (
    CurrentPrediction,
    LockedAggregateAuthorization,
    MetricCase,
    calculate_locked_quality_metrics,
    calculate_quality_metrics,
)
from tests.job_discovery.benchmark.report import (
    build_locked_aggregate_report,
    generate_locked_aggregate,
    generate_policy_evaluation,
)


def _locked_case() -> MetricCase:
    return MetricCase(
        case_id="synthetic-locked-only",
        scenario_id="synthetic-locked-scenario",
        split="locked",
        expected_eligibility="eligible",
        proposed_grade="excellent",
        proposed_provisional=False,
        apply_worthy=True,
        ranking_group=None,
        role_families=["software_engineering"],
        job_level="mid",
        posting_level="mid",
        candidate_target_levels=["mid"],
        evidence_quality="verified",
        posting_completeness="complete",
        critical_gap=False,
        positive_reason_traceable=True,
        material_gap_traceable=True,
    )


def _prediction() -> CurrentPrediction:
    return CurrentPrediction(
        case_id="synthetic-locked-only",
        current_label="strong",
        current_eligibility="eligible",
        provisional=False,
    )


def test_ordinary_metrics_continue_rejecting_locked_synthetic_cases() -> None:
    case = _locked_case()
    with pytest.raises(ValueError, match="Locked"):
        calculate_quality_metrics([case], {case.case_id: _prediction()})


def test_ordinary_report_path_excludes_locked_without_loading_it() -> None:
    with pytest.raises(ValueError, match="approved calibration and validation"):
        generate_policy_evaluation("locked")


def test_locked_aggregate_requires_local_explicit_authorization() -> None:
    case = _locked_case()
    prediction = {case.case_id: _prediction()}
    with pytest.raises(PermissionError, match="explicit authorization"):
        calculate_locked_quality_metrics(
            [case], prediction, [], authorization=None
        )
    with pytest.raises(PermissionError):
        LockedAggregateAuthorization.from_explicit_gate(
            marker_enabled=False,
            project_owner_authorized=True,
        )


def test_authorized_locked_adapter_returns_aggregate_fields_only() -> None:
    case = _locked_case()
    authorization = LockedAggregateAuthorization.from_explicit_gate(
        marker_enabled=True,
        project_owner_authorized=True,
    )
    report = build_locked_aggregate_report(
        [case],
        {case.case_id: _prediction()},
        [],
        authorization=authorization,
    )
    encoded = json.dumps(report, sort_keys=True)
    assert report["evaluation_policy_version"] == "jobs-fit-v2.1-calibrated"
    assert report["case_level_content"] is False
    assert "synthetic-locked-only" not in encoded
    assert "case_id" not in encoded
    assert "prediction" not in encoded
    assert "rationale" not in encoded
    assert "posting_body" not in encoded
    assert "profile_body" not in encoded
    assert "expected_label" not in encoded


def test_authorization_does_not_leak_to_later_calls() -> None:
    case = _locked_case()
    authorization = LockedAggregateAuthorization.from_explicit_gate(
        marker_enabled=True,
        project_owner_authorized=True,
    )
    build_locked_aggregate_report(
        [case],
        {case.case_id: _prediction()},
        [],
        authorization=authorization,
    )
    with pytest.raises(ValueError, match="Locked"):
        calculate_quality_metrics([case], {case.case_id: _prediction()})
    with pytest.raises(PermissionError):
        generate_locked_aggregate()


def test_locked_adapter_requires_the_command_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JOB_DISCOVERY_LOCKED_GATE", raising=False)
    with pytest.raises(PermissionError, match="explicit marker"):
        generate_locked_aggregate()
