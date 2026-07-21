from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from resume_tailor.domain.hybrid_resume import (
    BulletLengthClass,
    GroundingFailureCode,
    ProviderRewriteMappingOutcome,
    ProviderRewriteMappingStatus,
)
from resume_tailor.domain.llm_models import (
    BulletRewrite,
    BulletRewriteClaim,
    BulletRewriteOutput,
    BulletRewriteRequest,
)
from resume_tailor.domain.models import ClaimConfidence

GEMINI_WRITER_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "rewrites": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_evidence_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "rewritten_text": {"type": "string"},
                    "length_class": {
                        "type": "string",
                        "enum": ["concise", "standard"],
                    },
                },
                "required": [
                    "source_evidence_ids",
                    "rewritten_text",
                    "length_class",
                ],
            },
        }
    },
    "required": ["rewrites"],
}


class GeminiProviderRewrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_evidence_ids: list[str]
    rewritten_text: str
    length_class: Literal["concise", "standard"]


class GeminiProviderWriterOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rewrites: list[GeminiProviderRewrite]


class GeminiWriterMappingError(ValueError):
    def __init__(self, failures: list[str]) -> None:
        self.failures = failures
        super().__init__("; ".join(failures))


class GeminiWriterMappingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output: BulletRewriteOutput
    mapping_outcomes: list[ProviderRewriteMappingOutcome]


def map_provider_writer_output(
    provider_output: GeminiProviderWriterOutput,
    request: BulletRewriteRequest,
) -> GeminiWriterMappingResult:
    """Reconstruct the rich internal contract from authorized request evidence."""

    group_by_evidence = {
        evidence_id: group
        for group in request.groups
        for evidence_id in group.evidence_ids
    }
    reconstructed: list[BulletRewrite] = []
    outcomes: list[ProviderRewriteMappingOutcome] = []
    seen_variants: set[tuple[tuple[str, ...], str]] = set()
    for index, rewrite in enumerate(provider_output.rewrites):
        evidence_ids = rewrite.source_evidence_ids
        if not evidence_ids:
            outcomes.append(
                _rejected_mapping(
                    index,
                    rewrite,
                    ProviderRewriteMappingStatus.REJECTED_EMPTY_EVIDENCE,
                    GroundingFailureCode.UNKNOWN_EVIDENCE,
                    f"provider rewrite {index} has no evidence IDs",
                )
            )
            continue
        if len(set(evidence_ids)) != len(evidence_ids):
            outcomes.append(
                _rejected_mapping(
                    index,
                    rewrite,
                    ProviderRewriteMappingStatus.REJECTED_DUPLICATE_EVIDENCE,
                    GroundingFailureCode.DUPLICATE_EVIDENCE,
                    f"provider rewrite {index} repeats evidence IDs",
                )
            )
            continue
        unknown_ids = [
            evidence_id for evidence_id in evidence_ids if evidence_id not in group_by_evidence
        ]
        if unknown_ids:
            outcomes.append(
                _rejected_mapping(
                    index,
                    rewrite,
                    ProviderRewriteMappingStatus.REJECTED_UNKNOWN_EVIDENCE,
                    GroundingFailureCode.UNKNOWN_EVIDENCE,
                    f"provider rewrite {index} references unknown evidence IDs: {unknown_ids}",
                )
            )
            continue
        groups = [group_by_evidence[evidence_id] for evidence_id in evidence_ids]
        entry_ids = {group.entry_id for group in groups}
        if len(entry_ids) != 1:
            outcomes.append(
                _rejected_mapping(
                    index,
                    rewrite,
                    ProviderRewriteMappingStatus.REJECTED_CROSS_ENTRY_EVIDENCE,
                    GroundingFailureCode.CROSS_ENTRY_EVIDENCE,
                    f"provider rewrite {index} combines evidence across entries",
                )
            )
            continue
        signature = (tuple(evidence_ids), rewrite.length_class)
        if signature in seen_variants:
            outcomes.append(
                _rejected_mapping(
                    index,
                    rewrite,
                    ProviderRewriteMappingStatus.REJECTED_DUPLICATE_VARIANT,
                    GroundingFailureCode.DUPLICATE_EVIDENCE,
                    f"provider rewrite {index} duplicates an existing variant",
                )
            )
            continue
        seen_variants.add(signature)
        present_technologies = _present_terms(
            rewrite.rewritten_text,
            [term for group in groups for term in group.technologies],
        )
        present_metrics = _present_terms(
            rewrite.rewritten_text,
            [term for group in groups for term in group.metrics],
        )
        present_target_terms = _present_terms(rewrite.rewritten_text, request.target_terms)
        try:
            mapped_bullet_index = len(reconstructed)
            reconstructed.append(
                BulletRewrite(
                    entry_id=next(iter(entry_ids)),
                    final_bullet_text=rewrite.rewritten_text,
                    source_evidence_ids=evidence_ids,
                    preserved_technologies=present_technologies,
                    preserved_metrics=present_metrics,
                    emphasized_terms=present_target_terms,
                    evidence_combined=len(evidence_ids) > 1,
                    confidence=0.0,
                    support=ClaimConfidence.EXPLICITLY_SUPPORTED,
                    support_rationale=(
                        "Reconstructed from an authorized evidence bundle; deterministic "
                        "grounding remains authoritative."
                    ),
                    claims=[
                        BulletRewriteClaim(
                            text=rewrite.rewritten_text,
                            supporting_evidence_ids=evidence_ids,
                        )
                    ],
                    intended_length_class=(
                        BulletLengthClass.CONCISE_ONE_LINE
                        if rewrite.length_class == "concise"
                        else BulletLengthClass.STANDARD_ONE_TO_TWO_LINES
                    ),
                )
            )
            outcomes.append(
                ProviderRewriteMappingOutcome(
                    rewrite_index=index,
                    evidence_ids=evidence_ids,
                    rewritten_text=rewrite.rewritten_text,
                    mapping_status=ProviderRewriteMappingStatus.MAPPED,
                    entry_id=next(iter(entry_ids)),
                    mapped_bullet_index=mapped_bullet_index,
                )
            )
        except ValidationError as error:
            paths = sorted(
                {
                    ".".join(str(part) for part in item.get("loc", ())) or "$"
                    for item in error.errors(include_url=False)
                }
            )
            outcomes.append(
                _rejected_mapping(
                    index,
                    rewrite,
                    ProviderRewriteMappingStatus.REJECTED_INTERNAL_CONTRACT,
                    GroundingFailureCode.INTERNAL_CONTRACT,
                    f"provider rewrite {index} violates the internal contract at: {paths}",
                )
            )
            continue
    try:
        return GeminiWriterMappingResult(
            output=BulletRewriteOutput(bullets=reconstructed),
            mapping_outcomes=outcomes,
        )
    except ValidationError as error:
        paths = sorted(
            {
                ".".join(str(part) for part in item.get("loc", ())) or "$"
                for item in error.errors(include_url=False)
            }
        )
        raise GeminiWriterMappingError(
            [f"provider writer batch violates the internal contract at: {paths}"]
        ) from error


def _rejected_mapping(
    index: int,
    rewrite: GeminiProviderRewrite,
    status: ProviderRewriteMappingStatus,
    code: GroundingFailureCode,
    detail: str,
) -> ProviderRewriteMappingOutcome:
    return ProviderRewriteMappingOutcome(
        rewrite_index=index,
        evidence_ids=rewrite.source_evidence_ids,
        rewritten_text=rewrite.rewritten_text,
        mapping_status=status,
        failure_codes=[code],
        failure_details=[detail],
    )


def _present_terms(text: str, terms: list[str]) -> list[str]:
    normalized = text.casefold()
    return list(
        dict.fromkeys(term for term in terms if term and term.casefold() in normalized)
    )


__all__ = [
    "GEMINI_WRITER_RESPONSE_SCHEMA",
    "GeminiProviderRewrite",
    "GeminiProviderWriterOutput",
    "GeminiWriterMappingError",
    "GeminiWriterMappingResult",
    "map_provider_writer_output",
]
