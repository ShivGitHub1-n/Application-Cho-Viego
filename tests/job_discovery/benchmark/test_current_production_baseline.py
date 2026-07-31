# ruff: noqa: E501

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from tests.job_discovery.benchmark.loader import (
    load_development_cases,
    load_pilot_calibration_group_01,
)
from tests.job_discovery.benchmark.report import (
    AdapterFailureError,
    _current_inputs,
    _rank_prediction_ids,
    generate_current_baseline,
    generate_pilot_artifacts,
    generate_review_artifact,
)


def test_stage_a_reports_are_readable_and_leave_review_fields_blank(tmp_path: Path) -> None:
    review_path = tmp_path / "review.html"

    selected = generate_review_artifact(review_path)

    html = review_path.read_text(encoding="utf-8")
    csv_text = review_path.with_suffix(".csv").read_text(encoding="utf-8")
    assert selected
    assert "PRELIMINARY" in html
    assert "PROPOSED LABELS" in html
    assert "LOCKED SPLIT NOT EVALUATED" in html
    assert "User review required before Stage B" in html
    assert "Reviewer decision" in html
    assert "Reviewer notes" in html
    assert all(case_id in html for case_id in selected)
    assert "value=''" in html
    assert "Primary queue" in html
    assert "Complete disagreement appendix" in html
    assert all(field in csv_text for field in ("reviewer_decision", "reviewer_grade", "reviewer_eligibility", "reviewer_provisional", "reviewer_notes"))
    # Mandatory archetypes can exceed the desirable range when the current
    # production policy disagrees with many proposed hard cases.
    assert 30 <= len(selected) <= 60


def test_current_baseline_is_calibration_validation_only_and_byte_stable(tmp_path: Path) -> None:
    output = tmp_path / "current-baseline.html"
    json_output = output.with_suffix(".json")

    generate_current_baseline(output, ["calibration", "validation"])
    first_html = output.read_bytes()
    first_json = json_output.read_bytes()
    generate_current_baseline(output, ["calibration", "validation"])

    assert first_html == output.read_bytes()
    assert first_json == json_output.read_bytes()
    assert "PRELIMINARY" in output.read_text(encoding="utf-8")
    assert "NOT APPROVED GROUND TRUTH" in output.read_text(encoding="utf-8")
    assert "LOCKED SPLIT NOT EVALUATED" in output.read_text(encoding="utf-8")
    assert not any(
        case.case_id.startswith("synthetic-locked-") for case in load_development_cases()
    )
    baseline_json = json_output.read_text(encoding="utf-8")
    payload = json.loads(baseline_json)
    assert "synthetic-locked-" not in baseline_json
    assert set(payload["metrics"]["top_five_precision"]) == {
        "calibration-group-01", "calibration-group-02", "calibration-group-03", "calibration-group-04",
        "calibration-group-05", "calibration-group-06", "validation-group-01", "validation-group-02",
    }
    assert payload["locked_split"] == "not evaluated"
    assert payload["adapter_failures"] == 0
    assert payload["ranking_mode"].startswith("scorer_only_diagnostic")
    assert "proposed_reference_structural_validity" in payload
    assert payload["current_explanation_heuristic_traceability"] is not None
    assert set(payload["metrics_by_split"]) == {"calibration", "validation"}
    assert payload["metrics_by_split"]["calibration"]["top_five_precision"]
    assert payload["metrics_by_split"]["validation"]["top_five_precision"]
    assert payload["provider_order_diagnostics"]
    assert all(item["equivalent_canonical_output"] for item in payload["provider_order_diagnostics"])
    assert payload["duplicate_identity_diagnostics"]
    assert all(item["duplicate_count"] == 1 for item in payload["duplicate_identity_diagnostics"])


def test_baseline_rejects_locked_split_request(tmp_path: Path) -> None:
    try:
        generate_current_baseline(tmp_path / "baseline.html", ["locked"])
    except ValueError as error:
        assert "locked" in str(error).lower()
    else:
        raise AssertionError("locked baseline request must fail")


def test_adapter_failures_are_not_converted_to_predictions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import tests.job_discovery.benchmark.report as report

    monkeypatch.setattr(report, "current_prediction", lambda case: (_ for _ in ()).throw(ValueError("broken adapter")))
    with pytest.raises(AdapterFailureError):
        generate_current_baseline(tmp_path / "baseline.html", ["calibration"])


def test_benchmark_profile_uses_production_capability_authority() -> None:
    case = load_pilot_calibration_group_01()[0]
    _, _, profile_index, _ = _current_inputs(case)

    assert "python" in profile_index.terms
    assert "postgresql" in profile_index.terms
    assert all(not key.startswith("profile:") for key in profile_index.terms)
    assert any(item.demonstrated for item in profile_index.terms["python"])
    assert any(item.source_id == "profile:pilot-backend:python-api" for item in profile_index.terms["python"])
    assert "kubernetes" in profile_index.terms
    assert not any(item.demonstrated for item in profile_index.terms["kubernetes"])
    assert "kafka" in profile_index.terms
    assert not any(item.demonstrated for item in profile_index.terms["kafka"])
    assert "astronomy" not in profile_index.terms


def test_pilot_baseline_exposes_complete_current_score_components(tmp_path: Path) -> None:
    from tests.job_discovery.benchmark.report import current_prediction, generate_pilot_artifacts

    case = load_pilot_calibration_group_01()[0]
    prediction = current_prediction(case)
    assert prediction.score_components["demonstrated_technical_evidence"] > 0
    assert prediction.score_components["required_coverage"] > 0
    assert prediction.current_explanation_traceable is True

    generate_pilot_artifacts(
        tmp_path / "pilot.html",
        tmp_path / "pilot.csv",
        tmp_path / "pilot.json",
    )
    payload = json.loads((tmp_path / "pilot.json").read_text(encoding="utf-8"))
    assert len(payload["predictions"]) == 10
    assert all(
        set(row["score_components"]) == {
            "demonstrated_technical_evidence",
            "required_coverage",
            "role_alignment",
            "level_alignment",
            "education_coursework",
            "preferred_skill_alignment",
            "recency_completeness",
        }
        for row in payload["predictions"]
    )


def test_numeric_ranking_precedes_preferred_company_and_uses_stable_id() -> None:
    from tests.job_discovery.benchmark.metrics import CurrentPrediction

    predictions = {
        "score-90": CurrentPrediction(case_id="score-90", current_label="strong", current_eligibility="eligible", provisional=False, ranking_key=(-90.0, 1, "z")),
        "score-75": CurrentPrediction(case_id="score-75", current_label="good", current_eligibility="eligible", provisional=False, ranking_key=(-75.0, 0, "a")),
        "score-17": CurrentPrediction(case_id="score-17", current_label="stretch", current_eligibility="eligible", provisional=False, ranking_key=(-17.0, 0, "b")),
    }
    assert _rank_prediction_ids(predictions) == ["score-90", "score-75", "score-17"]
    assert _rank_prediction_ids(dict(reversed(list(predictions.items())))) == ["score-90", "score-75", "score-17"]
    tied = {
        "preferred": predictions["score-75"].model_copy(update={"ranking_key": (-75.0, 0, "z")}),
        "ordinary": predictions["score-75"].model_copy(update={"ranking_key": (-75.0, 1, "a")}),
        "same-score-id-b": predictions["score-75"].model_copy(update={"case_id": "same-score-id-b", "ranking_key": (-75.0, 1, "b")}),
    }
    assert _rank_prediction_ids(tied) == ["preferred", "ordinary", "same-score-id-b"]


def test_pilot_numeric_ranks_follow_real_production_sort_key() -> None:
    from tests.job_discovery.benchmark.report import _prediction_map

    cases = load_pilot_calibration_group_01()
    predictions = _prediction_map(cases)
    ordered = sorted(cases, key=lambda case: predictions[case.case_id].rank or 999)
    assert [predictions[case.case_id].score for case in ordered] == sorted(
        (predictions[case.case_id].score for case in cases), reverse=True
    )
    assert [predictions[case.case_id].rank for case in ordered] == list(range(1, 11))


def test_baseline_uses_heuristic_traceability_name() -> None:
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory)
        generate_pilot_artifacts(output / "review.html", output / "review.csv", output / "baseline.json")
        payload = json.loads((output / "baseline.json").read_text(encoding="utf-8"))
    assert "current_explanation_heuristic_traceability" in payload
    assert "current_explanation_traceability" not in payload


def test_pilot_baseline_exposes_structural_reference_metrics() -> None:
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory)
        generate_pilot_artifacts(
            output / "review.html",
            output / "review.csv",
            output / "baseline.json",
        )
        payload = json.loads((output / "baseline.json").read_text(encoding="utf-8"))
    assert "proposed_reference_structural_validity" in payload
    assert "proposed_reference_validity" not in payload
