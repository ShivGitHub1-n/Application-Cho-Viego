import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from resume_tailor.application.llm_validation import (
    GroundingValidationError,
    validate_rewrites,
)
from resume_tailor.domain.hybrid_resume import BulletLengthClass, ProviderRewriteMappingStatus
from resume_tailor.domain.llm_models import ApprovedEvidenceGroup, BulletRewriteRequest
from resume_tailor.infrastructure.gemini_canary import (
    MINIMAL_WRITER_CANARY_EVIDENCE_ID,
    MINIMAL_WRITER_CANARY_SAFE_PARAPHRASES,
    MINIMAL_WRITER_CANARY_SOURCE,
)
from resume_tailor.infrastructure.gemini_schema import transform_gemini_schema
from resume_tailor.infrastructure.gemini_writer_contract import (
    GEMINI_WRITER_RESPONSE_SCHEMA,
    GeminiProviderWriterOutput,
    map_provider_writer_output,
)


def _request() -> BulletRewriteRequest:
    return BulletRewriteRequest(
        primary_focus="Embedded engineering",
        target_terms=["STM32", "SPI", "testing"],
        groups=[
            ApprovedEvidenceGroup(
                entry_id="embedded-entry",
                evidence_ids=["firmware", "sensor"],
                source_texts=[
                    "Developed STM32 firmware.",
                    "Validated SPI sensor communication.",
                ],
                technologies=["STM32", "SPI"],
                capabilities=["firmware", "validation", "sensor communication"],
                max_rendered_lines=2,
            ),
            ApprovedEvidenceGroup(
                entry_id="backend-entry",
                evidence_ids=["api"],
                source_texts=["Built and tested a Python API."],
                technologies=["Python"],
                capabilities=["API development", "testing"],
                max_rendered_lines=2,
            ),
        ],
        max_bullets_per_entry=2,
        max_total_lines=6,
    )


def _canary_request() -> BulletRewriteRequest:
    return BulletRewriteRequest(
        primary_focus="Backend engineering",
        target_terms=["Python", "API", "testing"],
        groups=[
            ApprovedEvidenceGroup(
                entry_id="canary-entry",
                evidence_ids=[MINIMAL_WRITER_CANARY_EVIDENCE_ID],
                source_texts=[MINIMAL_WRITER_CANARY_SOURCE],
                technologies=["Python", "API"],
                capabilities=["development", "testing", "request processing"],
                metrics=["500 requests per day"],
                max_rendered_lines=2,
            )
        ],
        max_bullets_per_entry=1,
        max_total_lines=2,
    )


def _provider_output(
    *,
    evidence_ids: list[str] | None = None,
    text: str = "Built STM32 firmware and validated SPI sensor communication.",
    length_class: str = "standard",
) -> GeminiProviderWriterOutput:
    return GeminiProviderWriterOutput.model_validate(
        {
            "rewrites": [
                {
                    "source_evidence_ids": evidence_ids or ["firmware", "sensor"],
                    "rewritten_text": text,
                    "length_class": length_class,
                }
            ]
        }
    )


def _schema_keywords(value: object) -> set[str]:
    keywords: set[str] = set()
    if isinstance(value, dict):
        keywords.update(str(key) for key in value)
        for child in value.values():
            keywords.update(_schema_keywords(child))
    elif isinstance(value, list):
        for child in value:
            keywords.update(_schema_keywords(child))
    return keywords


def test_captured_writer_fixture_is_sanitized_and_preserves_eight_returned_items() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "captured_gemini_writer_response.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    assert len(payload["rewrites"]) == 8
    fixture_text = fixture_path.read_text(encoding="utf-8")
    assert "GEMINI_API_KEY" not in fixture_text
    assert "Authorization" not in fixture_text
    assert all(item["source_evidence_ids"] for item in payload["rewrites"])


def test_minimal_writer_schema_is_shallow_and_uses_only_transport_fields() -> None:
    original = deepcopy(GEMINI_WRITER_RESPONSE_SCHEMA)
    transform = transform_gemini_schema(GEMINI_WRITER_RESPONSE_SCHEMA)

    assert GEMINI_WRITER_RESPONSE_SCHEMA == original
    assert transform.schema == GEMINI_WRITER_RESPONSE_SCHEMA
    assert set(transform.schema) == {"type", "properties", "required"}
    rewrite = transform.schema["properties"]["rewrites"]["items"]
    assert set(rewrite["properties"]) == {
        "source_evidence_ids",
        "rewritten_text",
        "length_class",
    }
    assert rewrite["required"] == [
        "source_evidence_ids",
        "rewritten_text",
        "length_class",
    ]
    assert rewrite["properties"]["length_class"]["enum"] == [
        "concise",
        "standard",
    ]
    assert _schema_keywords(transform.schema).isdisjoint(
        {
            "$defs",
            "$ref",
            "anyOf",
            "oneOf",
            "allOf",
            "additionalProperties",
            "default",
            "minLength",
            "maxLength",
            "minItems",
            "maxItems",
            "pattern",
        }
    )
    assert transform.provider_audit.property_count == 4
    assert transform.provider_audit.enum_count == 1
    assert transform.provider_audit.nesting_depth <= 5


def test_valid_provider_response_reconstructs_rich_internal_variant() -> None:
    output = map_provider_writer_output(_provider_output(), _request()).output

    assert len(output.bullets) == 1
    rewrite = output.bullets[0]
    assert rewrite.entry_id == "embedded-entry"
    assert rewrite.source_evidence_ids == ["firmware", "sensor"]
    assert rewrite.evidence_combined is True
    assert rewrite.preserved_technologies == ["STM32", "SPI"]
    assert rewrite.emphasized_terms == ["STM32", "SPI"]
    assert rewrite.intended_length_class is BulletLengthClass.STANDARD_ONE_TO_TWO_LINES
    assert rewrite.claims[0].supporting_evidence_ids == ["firmware", "sensor"]
    validate_rewrites(
        output,
        _request().groups,
        max_bullets_per_entry=2,
        max_total_lines=6,
    )


def test_exact_canary_source_accepts_structural_and_verb_equivalent_paraphrases() -> None:
    assert MINIMAL_WRITER_CANARY_SOURCE == (
        "Developed and tested a Python API that processed 500 requests per day."
    )
    assert MINIMAL_WRITER_CANARY_SAFE_PARAPHRASES == (
        "Built and tested a Python API that processed 500 requests per day.",
        "Tested and developed a Python API that processed 500 requests per day.",
    )
    request = _canary_request()

    for rewrite in MINIMAL_WRITER_CANARY_SAFE_PARAPHRASES:
        provider_output = GeminiProviderWriterOutput.model_validate(
            {
                "rewrites": [
                    {
                        "source_evidence_ids": [MINIMAL_WRITER_CANARY_EVIDENCE_ID],
                        "rewritten_text": rewrite,
                        "length_class": "standard",
                    }
                ]
            }
        )
        output = map_provider_writer_output(provider_output, request).output

        assert output.bullets[0].source_evidence_ids == [
            MINIMAL_WRITER_CANARY_EVIDENCE_ID
        ]
        assert output.bullets[0].claims[0].supporting_evidence_ids == [
            MINIMAL_WRITER_CANARY_EVIDENCE_ID
        ]
        validate_rewrites(
            output,
            request.groups,
            max_bullets_per_entry=1,
            max_total_lines=2,
        )


def test_built_equivalence_does_not_allow_real_ownership_expansion() -> None:
    request = BulletRewriteRequest(
        primary_focus="Backend engineering",
        groups=[
            ApprovedEvidenceGroup(
                entry_id="entry",
                evidence_ids=["evidence"],
                source_texts=["Collaborated on testing a Python API."],
                technologies=["Python", "API"],
                capabilities=["collaboration", "testing"],
                max_rendered_lines=2,
            )
        ],
        max_bullets_per_entry=1,
        max_total_lines=2,
    )
    output = map_provider_writer_output(
        GeminiProviderWriterOutput.model_validate(
            {
                "rewrites": [
                    {
                        "source_evidence_ids": ["evidence"],
                        "rewritten_text": "Built and tested a Python API.",
                        "length_class": "standard",
                    }
                ]
            }
        ),
        request,
    ).output

    with pytest.raises(GroundingValidationError, match="ownership or causality"):
        validate_rewrites(
            output,
            request.groups,
            max_bullets_per_entry=1,
            max_total_lines=2,
        )


def test_unknown_provider_evidence_id_is_rejected_during_mapping() -> None:
    mapped = map_provider_writer_output(
        _provider_output(evidence_ids=["not-authorized"]),
        _request(),
    )

    assert mapped.output.bullets == []
    assert mapped.mapping_outcomes[0].mapping_status is (
        ProviderRewriteMappingStatus.REJECTED_UNKNOWN_EVIDENCE
    )


def test_cross_entry_provider_combination_is_rejected_during_mapping() -> None:
    mapped = map_provider_writer_output(
        _provider_output(evidence_ids=["firmware", "api"]),
        _request(),
    )

    assert mapped.output.bullets == []
    assert mapped.mapping_outcomes[0].mapping_status is (
        ProviderRewriteMappingStatus.REJECTED_CROSS_ENTRY_EVIDENCE
    )


def test_duplicate_evidence_ids_are_rejected_during_mapping() -> None:
    mapped = map_provider_writer_output(
        _provider_output(evidence_ids=["firmware", "firmware"]),
        _request(),
    )

    assert mapped.output.bullets == []
    assert mapped.mapping_outcomes[0].mapping_status is (
        ProviderRewriteMappingStatus.REJECTED_DUPLICATE_EVIDENCE
    )


def test_duplicate_provider_variants_are_rejected_during_mapping() -> None:
    item = {
        "source_evidence_ids": ["firmware"],
        "rewritten_text": "Built STM32 firmware.",
        "length_class": "concise",
    }
    provider_output = GeminiProviderWriterOutput.model_validate(
        {"rewrites": [item, dict(item)]}
    )

    mapped = map_provider_writer_output(provider_output, _request())

    assert len(mapped.output.bullets) == 1
    assert mapped.mapping_outcomes[1].mapping_status is (
        ProviderRewriteMappingStatus.REJECTED_DUPLICATE_VARIANT
    )


def test_invalid_mapping_does_not_discard_valid_sibling() -> None:
    provider_output = GeminiProviderWriterOutput.model_validate(
        {
            "rewrites": [
                {
                    "source_evidence_ids": ["not-authorized"],
                    "rewritten_text": "Built an unauthorized system.",
                    "length_class": "standard",
                },
                {
                    "source_evidence_ids": ["firmware", "sensor"],
                    "rewritten_text": (
                        "Built STM32 firmware and validated SPI sensor communication."
                    ),
                    "length_class": "standard",
                },
            ]
        }
    )

    mapped = map_provider_writer_output(provider_output, _request())

    assert len(mapped.output.bullets) == 1
    assert mapped.output.bullets[0].source_evidence_ids == ["firmware", "sensor"]
    assert [item.mapping_status for item in mapped.mapping_outcomes] == [
        ProviderRewriteMappingStatus.REJECTED_UNKNOWN_EVIDENCE,
        ProviderRewriteMappingStatus.MAPPED,
    ]


def test_unsupported_claim_is_rejected_after_local_reconstruction() -> None:
    output = map_provider_writer_output(
        _provider_output(
            evidence_ids=["firmware"],
            text="Deployed STM32 firmware to AWS and reduced latency by 40%.",
        ),
        _request(),
    ).output

    with pytest.raises(GroundingValidationError) as raised:
        validate_rewrites(
            output,
            _request().groups,
            max_bullets_per_entry=2,
            max_total_lines=6,
        )

    failures = " ".join(raised.value.failures).casefold()
    assert "40" in failures
    assert "aws" in failures


def test_local_provider_model_remains_strict_beyond_transmitted_schema() -> None:
    with pytest.raises(ValidationError):
        GeminiProviderWriterOutput.model_validate(
            {
                "rewrites": [
                    {
                        "source_evidence_ids": ["firmware"],
                        "rewritten_text": "Built STM32 firmware.",
                        "length_class": "standard",
                        "confidence": 0.99,
                    }
                ]
            }
        )
