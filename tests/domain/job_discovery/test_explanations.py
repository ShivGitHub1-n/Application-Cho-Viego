from __future__ import annotations

from resume_tailor.domain.job_discovery.explanations import (
    MaterialGap,
    PositiveReason,
    validate_explanation_traceability,
)


def test_positive_reason_requires_posting_and_profile_authority() -> None:
    reason = PositiveReason(
        code="requirement_match",
        statement="Python service ownership is demonstrated.",
        posting_references=["posting:requirement:python"],
        profile_references=["profile:e-python"],
    )
    gap = MaterialGap(
        code="missing_requirement",
        statement="A required license is not confirmed.",
        posting_references=["posting:requirement:license"],
        authority_references=["profile:license-status"],
    )

    assert validate_explanation_traceability([reason], [gap]) is True


def test_positive_reason_cannot_contain_gap_language() -> None:
    try:
        PositiveReason(
            code="invalid",
            statement="Python is demonstrated but Docker is missing.",
            posting_references=["posting:python"],
            profile_references=["profile:python"],
        )
    except ValueError as error:
        assert "positive" in str(error).lower()
    else:
        raise AssertionError("gap commentary must not enter positive reasons")
