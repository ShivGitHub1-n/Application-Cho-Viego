from __future__ import annotations

from collections import Counter

from tests.job_discovery.benchmark.approval import (
    load_approved_calibration,
    load_approved_validation,
)
from tests.job_discovery.benchmark.report import (
    _current_inputs,
    benchmark_profile_to_master_profile,
    current_prediction,
)


def test_development_adapter_preserves_each_eligibility_value() -> None:
    cases = [*load_approved_calibration(), *load_approved_validation()]
    matrix = Counter()
    for case in cases:
        prediction = current_prediction(case)
        matrix[(case.expected_eligibility, prediction.current_eligibility)] += 1

    assert matrix["eligible", "eligible"] == 52
    assert matrix["unknown", "unknown"] == 8
    assert matrix["ineligible", "ineligible"] == 20
    assert sum(matrix.values()) == 80


def test_stage_and_approval_metadata_do_not_change_the_adapter_path() -> None:
    cases = [*load_approved_calibration(), *load_approved_validation()]
    for case in cases:
        baseline = current_prediction(case)
        simulated_locked_load = case.model_copy(
            update={"stage": "A", "approval_status": "unapproved"}
        )
        comparison = current_prediction(simulated_locked_load)
        assert comparison.current_eligibility == baseline.current_eligibility
        assert comparison.current_label == baseline.current_label


def test_benchmark_profile_authority_fields_survive_conversion() -> None:
    cases = [*load_approved_calibration(), *load_approved_validation()]
    for case in cases:
        converted = benchmark_profile_to_master_profile(case.profile)
        assert converted.authorized_work_locations == case.profile.authorized_work_locations
        assert converted.requires_sponsorship is case.profile.requires_sponsorship
        assert converted.professional_license_status == case.profile.professional_license_status
        assert converted.clearance_status == case.profile.clearance_status


def test_complete_adapter_uses_the_same_production_inputs_for_development_splits() -> None:
    cases = [*load_approved_calibration(), *load_approved_validation()]
    for case in cases:
        job, preferences, profile_index, profile = _current_inputs(case)
        repeated_job, repeated_preferences, repeated_index, repeated_profile = _current_inputs(
            case.model_copy(update={"stage": "A", "approval_status": "unapproved"})
        )
        assert job.model_dump(mode="json") == repeated_job.model_dump(mode="json")
        assert preferences.model_dump(mode="json") == repeated_preferences.model_dump(mode="json")
        assert profile_index.model_dump(mode="json") == repeated_index.model_dump(mode="json")
        assert profile.model_dump(mode="json") == repeated_profile.model_dump(mode="json")
