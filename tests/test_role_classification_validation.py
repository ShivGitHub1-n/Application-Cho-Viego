from __future__ import annotations

from copy import deepcopy

import pytest

from resume_tailor.application.llm_validation import (
    MAX_ROLE_EVIDENCE_QUOTES,
    MAX_ROLE_SEMANTIC_ITEM_LENGTH,
    MAX_ROLE_SEMANTIC_ITEMS_PER_FIELD,
    RoleClassificationReasonCode,
    RoleClassificationStatus,
    validate_role_classification,
)
from resume_tailor.domain.llm_models import RoleClassificationOutput, RoleClassificationRequest, RoleEvidenceQuote
from resume_tailor.domain.models import RoleFamily


def _request() -> RoleClassificationRequest:
    return RoleClassificationRequest(
        title="Firmware Engineer",
        description="Design and implement firmware for STM32 motor-control boards.",
    )


def _output(**overrides: object) -> RoleClassificationOutput:
    values: dict[str, object] = {
        "is_engineering_role": True,
        "primary_family": RoleFamily.EMBEDDED_FIRMWARE,
        "confidence": 0.8,
    }
    values.update(overrides)
    return RoleClassificationOutput(**values)


def _validate(output: RoleClassificationOutput, *, threshold: float = 0.7):
    return validate_role_classification(_request(), output, minimum_confidence=threshold)


def test_valid_engineering_and_non_engineering_outputs() -> None:
    engineering = _validate(_output())
    non_engineering = _validate(_output(is_engineering_role=False, primary_family=None))

    assert engineering.status is RoleClassificationStatus.VALID
    assert engineering.reason_codes == []
    assert engineering.output is not None
    assert non_engineering.status is RoleClassificationStatus.VALID


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"primary_family": None}, RoleClassificationReasonCode.MISSING_PRIMARY_FAMILY),
        ({"is_engineering_role": False}, RoleClassificationReasonCode.NON_ENGINEERING_WITH_PRIMARY_FAMILY),
        (
            {"is_engineering_role": False, "primary_family": None, "secondary_families": [RoleFamily.EMBEDDED_FIRMWARE]},
            RoleClassificationReasonCode.NON_ENGINEERING_WITH_SECONDARY_FAMILIES,
        ),
        (
            {"secondary_families": [RoleFamily.SOFTWARE_DATA_ENGINEERING] * 2},
            RoleClassificationReasonCode.DUPLICATE_SECONDARY_FAMILY,
        ),
        (
            {"secondary_families": [RoleFamily.EMBEDDED_FIRMWARE]},
            RoleClassificationReasonCode.PRIMARY_REPEATED_AS_SECONDARY,
        ),
    ],
)
def test_family_consistency_violations_are_invalid(changes: dict[str, object], reason: RoleClassificationReasonCode) -> None:
    result = _validate(_output(**changes))

    assert result.status is RoleClassificationStatus.INVALID
    assert reason in result.reason_codes
    assert result.output is None


@pytest.mark.parametrize(
    ("quote", "status", "reason_codes"),
    [
        ("Firmware Engineer", RoleClassificationStatus.VALID, []),
        (
            "Design and implement firmware for STM32 motor-control boards.",
            RoleClassificationStatus.VALID,
            [],
        ),
        (
            "firmware engineer",
            RoleClassificationStatus.INVALID,
            [RoleClassificationReasonCode.UNGROUNDED_EVIDENCE_QUOTE],
        ),
        (
            "Design and implement firmware for STM32 motor-control boards,",
            RoleClassificationStatus.INVALID,
            [RoleClassificationReasonCode.UNGROUNDED_EVIDENCE_QUOTE],
        ),
        (
            "not supplied",
            RoleClassificationStatus.INVALID,
            [RoleClassificationReasonCode.UNGROUNDED_EVIDENCE_QUOTE],
        ),
    ],
)
def test_evidence_grounding_cases_are_explicit(
    quote: str,
    status: RoleClassificationStatus,
    reason_codes: list[RoleClassificationReasonCode],
) -> None:
    result = _validate(
        _output(evidence_quotes=[RoleEvidenceQuote(quote=quote, category="responsibility")])
    )

    assert result.status is status
    assert result.reason_codes == reason_codes


@pytest.mark.parametrize("categories", [("responsibility", "responsibility"), ("responsibility", "tool_or_skill")])
def test_duplicate_evidence_quotes_are_invalid(categories: tuple[str, str]) -> None:
    quote = "firmware"
    result = _validate(
        _output(
            evidence_quotes=[
                RoleEvidenceQuote(quote=quote, category=categories[0]),
                RoleEvidenceQuote(quote=f" {quote} ", category=categories[1]),
            ]
        )
    )

    assert result.status is RoleClassificationStatus.INVALID
    assert result.reason_codes == [RoleClassificationReasonCode.DUPLICATE_EVIDENCE_QUOTE]


def test_grounded_quotes_allow_title_or_description_and_trim_outer_whitespace() -> None:
    result = _validate(
        _output(
            evidence_quotes=[
                RoleEvidenceQuote(quote=" Firmware Engineer ", category="responsibility"),
                RoleEvidenceQuote(quote=" firmware ", category="tool_or_skill"),
            ]
        )
    )

    assert result.status is RoleClassificationStatus.VALID


def test_confidence_threshold_is_strictly_below_and_equality_is_accepted() -> None:
    assert _validate(_output(confidence=0.7)).status is RoleClassificationStatus.VALID
    assert _validate(_output(confidence=0.699)).status is RoleClassificationStatus.LOW_CONFIDENCE
    assert _validate(_output(confidence=0.699)).reason_codes == [RoleClassificationReasonCode.LOW_CONFIDENCE]


def test_invalid_output_remains_invalid_when_confidence_is_low() -> None:
    result = _validate(_output(primary_family=None, confidence=0.1))

    assert result.status is RoleClassificationStatus.INVALID
    assert result.reason_codes == [RoleClassificationReasonCode.MISSING_PRIMARY_FAMILY]


@pytest.mark.parametrize("threshold", [-0.01, 1.01])
def test_minimum_confidence_must_be_between_zero_and_one(threshold: float) -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        validate_role_classification(_request(), _output(), minimum_confidence=threshold)


@pytest.mark.parametrize(
    "field_name",
    [
        "owned_responsibilities",
        "contextual_mentions",
        "managed_subjects",
        "tools_and_skills",
    ],
)
def test_each_semantic_field_rejects_excess_item_count(field_name: str) -> None:
    result = _validate(
        _output(**{field_name: ["x"] * (MAX_ROLE_SEMANTIC_ITEMS_PER_FIELD + 1)})
    )

    assert result.status is RoleClassificationStatus.INVALID
    assert result.reason_codes == [RoleClassificationReasonCode.SEMANTIC_ITEM_LIMIT_EXCEEDED]


@pytest.mark.parametrize(
    "field_name",
    [
        "owned_responsibilities",
        "contextual_mentions",
        "managed_subjects",
        "tools_and_skills",
    ],
)
def test_each_semantic_field_rejects_oversized_items(field_name: str) -> None:
    result = _validate(
        _output(**{field_name: ["x" * (MAX_ROLE_SEMANTIC_ITEM_LENGTH + 1)]})
    )

    assert result.status is RoleClassificationStatus.INVALID
    assert result.reason_codes == [RoleClassificationReasonCode.SEMANTIC_ITEM_LENGTH_EXCEEDED]


def test_evidence_quote_count_bound_is_rejected() -> None:
    evidence_count = _validate(
        _output(
            evidence_quotes=[
                RoleEvidenceQuote(quote="firmware", category="tool_or_skill")
                for _ in range(MAX_ROLE_EVIDENCE_QUOTES + 1)
            ]
        )
    )

    assert evidence_count.status is RoleClassificationStatus.INVALID
    assert evidence_count.reason_codes == [
        RoleClassificationReasonCode.DUPLICATE_EVIDENCE_QUOTE,
        RoleClassificationReasonCode.EVIDENCE_QUOTE_LIMIT_EXCEEDED,
    ]


def test_validation_does_not_mutate_request_or_output() -> None:
    request = _request()
    output = _output(evidence_quotes=[RoleEvidenceQuote(quote="firmware", category="tool_or_skill")])
    request_before = deepcopy(request.model_dump())
    output_before = deepcopy(output.model_dump())

    validate_role_classification(request, output, minimum_confidence=0.7)

    assert request.model_dump() == request_before
    assert output.model_dump() == output_before


def test_reason_codes_have_deterministic_contract_order() -> None:
    result = _validate(
        _output(
            primary_family=None,
            secondary_families=[RoleFamily.SOFTWARE_DATA_ENGINEERING] * 2,
            evidence_quotes=[RoleEvidenceQuote(quote="not supplied", category="responsibility")] * (MAX_ROLE_EVIDENCE_QUOTES + 1),
            owned_responsibilities=["x"] * (MAX_ROLE_SEMANTIC_ITEMS_PER_FIELD + 1),
        )
    )

    assert result.reason_codes == [
        RoleClassificationReasonCode.MISSING_PRIMARY_FAMILY,
        RoleClassificationReasonCode.DUPLICATE_SECONDARY_FAMILY,
        RoleClassificationReasonCode.UNGROUNDED_EVIDENCE_QUOTE,
        RoleClassificationReasonCode.DUPLICATE_EVIDENCE_QUOTE,
        RoleClassificationReasonCode.SEMANTIC_ITEM_LIMIT_EXCEEDED,
        RoleClassificationReasonCode.EVIDENCE_QUOTE_LIMIT_EXCEEDED,
    ]
