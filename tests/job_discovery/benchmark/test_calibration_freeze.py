# ruff: noqa: E501

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tests.job_discovery.benchmark.loader import LockedBenchmarkAccessError, load_locked_cases

ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "job_discovery" / "benchmark"


def test_approved_calibration_loader_exposes_proposed_values_as_ground_truth() -> None:
    from tests.job_discovery.benchmark.approval import load_approved_calibration

    cases = load_approved_calibration()
    assert len(cases) == 60
    assert all(case.approval_status == "approved" for case in cases)
    raw = json.loads((ROOT / "calibration.json").read_text(encoding="utf-8"))
    by_id = {item["case_id"]: item for item in raw}
    assert all(by_id[case.case_id]["proposed_grade"] == case.proposed_grade for case in cases)


def test_approved_checksum_changes_for_semantic_mutation_but_not_review_presentation() -> None:
    from tests.job_discovery.benchmark.approval import approved_calibration_checksum

    cases = [copy.deepcopy(item) for item in json.loads((ROOT / "calibration.json").read_text(encoding="utf-8"))]
    baseline = approved_calibration_checksum(cases)
    cases[0]["reviewer_notes"] = "presentation-only note"
    assert approved_calibration_checksum(cases) == baseline
    cases[0]["proposed_grade"] = "weak"
    assert approved_calibration_checksum(cases) != baseline


def test_approved_checksum_includes_case_006_source_wording() -> None:
    from tests.job_discovery.benchmark.approval import approved_calibration_checksum

    cases = [copy.deepcopy(item) for item in json.loads((ROOT / "calibration.json").read_text(encoding="utf-8"))]
    baseline = approved_calibration_checksum(cases)
    case = next(item for item in cases if item["case_id"] == "calibration-006")
    case["posting"]["description"] += " Additional source wording."
    assert approved_calibration_checksum(cases) != baseline


def test_locked_cases_remain_guarded() -> None:
    with pytest.raises(LockedBenchmarkAccessError):
        load_locked_cases(authorized=True)
