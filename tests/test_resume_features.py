from resume_tailor.application.resume_features import (
    TemplateV1BulletLineEstimator,
    extract_reviewed_text_features,
    match_reviewed_features,
    normalize_reviewed_text,
)
from resume_tailor.domain.resume_composition import LineFitVerificationStatus


def test_normalization_preserves_meaningful_technical_syntax_and_strips_noise() -> None:
    normalized = normalize_reviewed_text(
        "C++, C#, .NET 8.0; ISO-9001, CAN-FD/J1939, ROS 2 (Humble), XGBoost-v2.1...)"
    )

    assert normalized.split() == [
        "c++",
        "c#",
        ".net",
        "8.0",
        "iso-9001",
        "can-fd/j1939",
        "ros",
        "2",
        "humble",
        "xgboost-v2.1",
    ]
    assert not normalized.endswith(".")


def test_feature_extraction_handles_cross_domain_terms_without_optional_metadata() -> None:
    cases = {
        "software": "Built C++/CLI services with .NET 8.0 and Vue.js.",
        "mechanical": "Validated GD&T drawings under ISO-9001 using coordinate measurement.",
        "controls": "Integrated CAN-FD/J1939 sensors with PLC/HMI v3.2 hardware.",
        "data": "Deployed PostgreSQL 16 workloads on Amazon EKS with CI/CD.",
        "civil": "Inspected reinforced-concrete connections against CSA-S16 requirements.",
    }

    extracted = {domain: extract_reviewed_text_features(text) for domain, text in cases.items()}

    assert "c++/cli" in extracted["software"].meaningful_tokens
    assert "iso-9001" in extracted["mechanical"].meaningful_tokens
    assert "can-fd/j1939" in extracted["controls"].meaningful_tokens
    assert "postgresql" in extracted["data"].meaningful_tokens
    assert "reinforced-concrete" in extracted["civil"].meaningful_tokens
    assert all(features.technical_specificity > 0 for features in extracted.values())


def test_generic_actions_cannot_independently_admit_unrelated_evidence() -> None:
    posting = extract_reviewed_text_features(
        "Develop and implement finite element models for bridge fatigue assessment."
    )
    generic = extract_reviewed_text_features(
        "Developed, implemented, created, designed, tested, and improved applications."
    )
    specific = extract_reviewed_text_features(
        "Developed finite element models and validated fatigue loads."
    )

    generic_match = match_reviewed_features(generic, posting)
    specific_match = match_reviewed_features(specific, posting)

    assert generic_match.admitted is False
    assert generic_match.generic_only is True
    assert specific_match.admitted is True
    assert "finite element models" in specific_match.meaningful_overlap


def test_line_estimator_detects_balanced_and_awkward_two_line_bullets() -> None:
    estimator = TemplateV1BulletLineEstimator()
    awkward = estimator.estimate(
        "Implemented deterministic validation across distributed services using reviewed "
        "evidence and reproducible deployment checks tail fragment"
    )
    balanced = estimator.estimate(
        "Implemented deterministic validation across distributed services using reviewed "
        "evidence and reproducible deployment checks " + ("balanced " * 5) + "tail fragment"
    )

    assert awkward.verification_status is LineFitVerificationStatus.ESTIMATED
    assert awkward.expected_line_count == 2
    assert awkward.awkward_wrap_risk is True
    assert awkward.expected_final_line_width_ratio < 0.18
    assert awkward.future_rewrite_recommended is True
    assert balanced.expected_line_count == 2
    assert balanced.awkward_wrap_risk is False
    assert balanced.total_vertical_line_cost < awkward.total_vertical_line_cost


def test_line_estimator_marks_three_line_bullets_for_future_shortening() -> None:
    estimator = TemplateV1BulletLineEstimator()
    diagnostic = estimator.estimate(
        "Implemented deterministic validation across distributed services using reviewed "
        "evidence and reproducible deployment checks " + ("balanced " * 15) + "tail fragment"
    )

    assert diagnostic.expected_line_count == 3
    assert diagnostic.three_line_risk is True
    assert diagnostic.future_rewrite_recommended is True
    assert diagnostic.total_vertical_line_cost > 3
