from __future__ import annotations

import re
from enum import StrEnum
from math import isfinite

from pydantic import BaseModel

from resume_tailor.domain.llm_models import (
    ApprovedEvidenceGroup,
    BulletRewrite,
    BulletRewriteOutput,
    BulletShorteningOutput,
    BulletShorteningRequest,
    CompositionRecommendationOutput,
    ProposedDemonstratedSkill,
    RoleClassificationOutput,
    RoleClassificationRequest,
)
from resume_tailor.domain.models import ClaimConfidence, EvidenceItem

MAX_ROLE_SEMANTIC_ITEMS_PER_FIELD = 20
MAX_ROLE_SEMANTIC_ITEM_LENGTH = 500
MAX_ROLE_EVIDENCE_QUOTES = 20


class RoleClassificationStatus(StrEnum):
    VALID = "valid"
    LOW_CONFIDENCE = "low_confidence"
    INVALID = "invalid"


class RoleClassificationReasonCode(StrEnum):
    MISSING_PRIMARY_FAMILY = "missing_primary_family"
    NON_ENGINEERING_WITH_PRIMARY_FAMILY = "non_engineering_with_primary_family"
    NON_ENGINEERING_WITH_SECONDARY_FAMILIES = "non_engineering_with_secondary_families"
    DUPLICATE_SECONDARY_FAMILY = "duplicate_secondary_family"
    PRIMARY_REPEATED_AS_SECONDARY = "primary_repeated_as_secondary"
    UNGROUNDED_EVIDENCE_QUOTE = "ungrounded_evidence_quote"
    DUPLICATE_EVIDENCE_QUOTE = "duplicate_evidence_quote"
    SEMANTIC_ITEM_LIMIT_EXCEEDED = "semantic_item_limit_exceeded"
    SEMANTIC_ITEM_LENGTH_EXCEEDED = "semantic_item_length_exceeded"
    EVIDENCE_QUOTE_LIMIT_EXCEEDED = "evidence_quote_limit_exceeded"
    LOW_CONFIDENCE = "low_confidence"


class RoleClassificationValidationResult(BaseModel):
    status: RoleClassificationStatus
    reason_codes: list[RoleClassificationReasonCode]
    output: RoleClassificationOutput | None = None


def validate_minimum_confidence(minimum_confidence: float) -> None:
    if (
        isinstance(minimum_confidence, bool)
        or not isinstance(minimum_confidence, (int, float))
        or not isfinite(minimum_confidence)
        or not 0 <= minimum_confidence <= 1
    ):
        raise ValueError("minimum_confidence must be a finite number between 0 and 1 inclusive")


def validate_role_classification(
    request: RoleClassificationRequest,
    output: RoleClassificationOutput,
    *,
    minimum_confidence: float,
) -> RoleClassificationValidationResult:
    """Validate typed role classification without creating downstream evidence or policy.

    ``owned_responsibilities``, ``contextual_mentions``, ``managed_subjects``, and
    ``tools_and_skills`` are advisory metadata only. They do not independently
    create resume claims, role families, deterministic signals, or optimization
    evidence. Future orchestration may treat only validated exact evidence quotes
    as authoritative evidence.
    """
    validate_minimum_confidence(minimum_confidence)

    found: set[RoleClassificationReasonCode] = set()
    if output.is_engineering_role and output.primary_family is None:
        found.add(RoleClassificationReasonCode.MISSING_PRIMARY_FAMILY)
    if not output.is_engineering_role and output.primary_family is not None:
        found.add(RoleClassificationReasonCode.NON_ENGINEERING_WITH_PRIMARY_FAMILY)
    if not output.is_engineering_role and output.secondary_families:
        found.add(RoleClassificationReasonCode.NON_ENGINEERING_WITH_SECONDARY_FAMILIES)

    secondary_families = output.secondary_families
    if len(set(secondary_families)) != len(secondary_families):
        found.add(RoleClassificationReasonCode.DUPLICATE_SECONDARY_FAMILY)
    if output.primary_family is not None and output.primary_family in secondary_families:
        found.add(RoleClassificationReasonCode.PRIMARY_REPEATED_AS_SECONDARY)
    source_texts = (request.title, request.description)
    stripped_quotes = [evidence.quote.strip() for evidence in output.evidence_quotes]
    if len(output.evidence_quotes) > MAX_ROLE_EVIDENCE_QUOTES:
        found.add(RoleClassificationReasonCode.EVIDENCE_QUOTE_LIMIT_EXCEEDED)
    if len(set(stripped_quotes)) != len(stripped_quotes):
        found.add(RoleClassificationReasonCode.DUPLICATE_EVIDENCE_QUOTE)
    if any(not any(quote in source for source in source_texts) for quote in stripped_quotes):
        found.add(RoleClassificationReasonCode.UNGROUNDED_EVIDENCE_QUOTE)

    semantic_fields = (
        output.owned_responsibilities,
        output.contextual_mentions,
        output.managed_subjects,
        output.tools_and_skills,
    )
    if any(len(items) > MAX_ROLE_SEMANTIC_ITEMS_PER_FIELD for items in semantic_fields):
        found.add(RoleClassificationReasonCode.SEMANTIC_ITEM_LIMIT_EXCEEDED)
    if any(
        len(item) > MAX_ROLE_SEMANTIC_ITEM_LENGTH for items in semantic_fields for item in items
    ):
        found.add(RoleClassificationReasonCode.SEMANTIC_ITEM_LENGTH_EXCEEDED)

    ordered_reasons = [code for code in RoleClassificationReasonCode if code in found]
    if ordered_reasons:
        return RoleClassificationValidationResult(
            status=RoleClassificationStatus.INVALID,
            reason_codes=ordered_reasons,
        )
    if output.confidence < minimum_confidence:
        return RoleClassificationValidationResult(
            status=RoleClassificationStatus.LOW_CONFIDENCE,
            reason_codes=[RoleClassificationReasonCode.LOW_CONFIDENCE],
            output=output,
        )
    return RoleClassificationValidationResult(
        status=RoleClassificationStatus.VALID,
        reason_codes=[],
        output=output,
    )


class GroundingValidationError(ValueError):
    def __init__(self, failures: list[str]) -> None:
        super().__init__("; ".join(failures))
        self.failures = failures


def validate_composition(
    output: CompositionRecommendationOutput,
    known_entry_ids: set[str],
    evidence_to_entry: dict[str, str],
) -> None:
    failures: list[str] = []
    selected = set(output.selected_entry_ids)
    excluded = set(output.excluded_entry_ids)
    unknown_entries = (selected | excluded) - known_entry_ids
    if unknown_entries:
        failures.append(f"unknown entry IDs: {sorted(unknown_entries)}")
    if selected & excluded:
        failures.append("selected and excluded entries overlap")
    unknown_evidence = set(output.selected_evidence_ids) - set(evidence_to_entry)
    if unknown_evidence:
        failures.append(f"unknown evidence IDs: {sorted(unknown_evidence)}")
    for grouping in output.proposed_evidence_groupings:
        if grouping.entry_id not in known_entry_ids:
            failures.append(f"unknown grouping entry ID: {grouping.entry_id}")
            continue
        mismatched = [
            evidence_id
            for evidence_id in grouping.evidence_ids
            if evidence_to_entry.get(evidence_id) != grouping.entry_id
        ]
        if mismatched:
            failures.append(f"cross-entry or unknown evidence in grouping: {mismatched}")
    if failures:
        raise GroundingValidationError(failures)


def validate_demonstrated_skills(
    proposals: list[ProposedDemonstratedSkill],
    eligible_category_ids: set[str],
    evidence_to_entry: dict[str, str],
    evidence_by_id: dict[str, EvidenceItem] | None = None,
) -> None:
    failures: list[str] = []
    seen_values: set[tuple[str, str]] = set()
    for proposal in proposals:
        if proposal.category_id not in eligible_category_ids:
            failures.append(f"unknown or ineligible skill category: {proposal.category_id}")
        if proposal.confidence == ClaimConfidence.UNSUPPORTED:
            failures.append(f"unsupported demonstrated skill: {proposal.value}")
        if (
            proposal.confidence == ClaimConfidence.EXPLICITLY_SUPPORTED
            and evidence_by_id is not None
        ):
            source_text = " ".join(
                " ".join([item.source_text, *item.technologies, *item.capabilities, *item.outcomes])
                for evidence_id in proposal.source_evidence_ids
                if (item := evidence_by_id.get(evidence_id)) is not None
            ).casefold()
            if proposal.value.casefold() not in source_text:
                failures.append(
                    f"explicit demonstrated skill is not stated in evidence: {proposal.value}"
                )
        if len(set(proposal.source_evidence_ids)) != len(proposal.source_evidence_ids):
            failures.append(f"demonstrated skill repeats evidence IDs: {proposal.value}")
        entry_ids = {
            evidence_to_entry.get(evidence_id) for evidence_id in proposal.source_evidence_ids
        }
        if None in entry_ids:
            failures.append(f"demonstrated skill references unknown evidence: {proposal.value}")
        if len(entry_ids - {None}) > 1:
            failures.append(
                f"demonstrated skill combines evidence across entries: {proposal.value}"
            )
        key = (proposal.category_id, proposal.value.casefold())
        if key in seen_values:
            failures.append(f"demonstrated skill is duplicated: {proposal.value}")
        seen_values.add(key)
    if failures:
        raise GroundingValidationError(failures)


def validate_rewrites(
    output: BulletRewriteOutput,
    groups: list[ApprovedEvidenceGroup],
    *,
    max_bullets_per_entry: int = 4,
    max_total_lines: int | None = None,
) -> None:
    group_by_evidence = {
        evidence_id: group for group in groups for evidence_id in group.evidence_ids
    }
    failures: list[str] = []
    entry_bullet_counts: dict[str, int] = {}
    total_lines = 0
    for bullet in output.bullets:
        if len(set(bullet.source_evidence_ids)) != len(bullet.source_evidence_ids):
            failures.append(f"rewrite repeats evidence IDs: {bullet.source_evidence_ids}")
            continue
        source_groups = [
            group_by_evidence.get(evidence_id) for evidence_id in bullet.source_evidence_ids
        ]
        if any(group is None for group in source_groups):
            failures.append(f"unknown evidence group: {bullet.source_evidence_ids}")
            continue
        groups_for_bullet = [group for group in source_groups if group is not None]
        if any(group.entry_id != bullet.entry_id for group in groups_for_bullet):
            failures.append(f"cross-entry bullet for {bullet.source_evidence_ids}")
            continue
        if bullet.evidence_combined != (len(bullet.source_evidence_ids) > 1):
            failures.append(f"incorrect combination status for {bullet.source_evidence_ids}")
        if bullet.support == ClaimConfidence.UNSUPPORTED:
            failures.append(f"unsupported generated claim: {bullet.final_bullet_text}")
            continue
        _validate_claim_provenance(bullet, group_by_evidence, failures)
        _validate_protected_facts(
            bullet.final_bullet_text,
            [fact for item in groups_for_bullet for fact in [*item.technologies, *item.metrics]],
            [text for item in groups_for_bullet for text in item.source_texts],
            failures,
            require_preserved_facts=False,
        )
        known_terms = {
            term for item in groups_for_bullet for term in [*item.technologies, *item.metrics]
        }
        unknown_terms = set(bullet.preserved_technologies + bullet.preserved_metrics) - known_terms
        if unknown_terms:
            failures.append(f"unsupported preserved terms: {sorted(unknown_terms)}")
        _validate_factual_terms(
            bullet.final_bullet_text,
            [text for item in groups_for_bullet for text in item.source_texts],
            list(known_terms),
            failures,
            allow_new_terminology=bullet.support == ClaimConfidence.STRONGLY_IMPLIED,
        )
        _validate_ownership(
            bullet.final_bullet_text,
            [text for item in groups_for_bullet for text in item.source_texts],
            failures,
            allow_strong_inference=bullet.support == ClaimConfidence.STRONGLY_IMPLIED,
        )
        _validate_outcomes(
            bullet.final_bullet_text,
            [text for item in groups_for_bullet for text in item.source_texts],
            failures,
        )
        _validate_variant_text(
            bullet.concise_alternative,
            groups_for_bullet,
            bullet.support,
            failures,
            label="concise alternative",
        )
        entry_bullet_counts[bullet.entry_id] = entry_bullet_counts.get(bullet.entry_id, 0) + 1
        total_lines += _estimated_lines(bullet.final_bullet_text)
    if any(count > max_bullets_per_entry for count in entry_bullet_counts.values()):
        failures.append("rewrite exceeds the configured per-entry bullet budget")
    line_budget = (
        max_total_lines
        if max_total_lines is not None
        else sum(group.max_rendered_lines for group in groups)
    )
    if total_lines > line_budget:
        failures.append("rewrite exceeds the selected evidence line budget")
    if failures:
        raise GroundingValidationError(failures)


def _validate_claim_provenance(
    bullet: BulletRewrite,
    group_by_evidence: dict[str, ApprovedEvidenceGroup],
    failures: list[str],
) -> None:
    if not bullet.claims:
        return
    source_ids = set(bullet.source_evidence_ids)
    covered_spans: list[str] = []
    for claim in bullet.claims:
        if not set(claim.supporting_evidence_ids).issubset(source_ids):
            failures.append(
                f"claim references evidence outside its bundle: {claim.supporting_evidence_ids}"
            )
        if claim.text.casefold() not in bullet.final_bullet_text.casefold():
            failures.append(f"claim span is absent from rewritten bullet: {claim.text}")
        claim_groups = [
            group_by_evidence[evidence_id]
            for evidence_id in claim.supporting_evidence_ids
            if evidence_id in group_by_evidence
        ]
        source_texts = [source_text for group in claim_groups for source_text in group.source_texts]
        claim_terms = [
            term for group in claim_groups for term in [*group.technologies, *group.metrics]
        ]
        _validate_protected_facts(
            claim.text,
            claim_terms,
            source_texts,
            failures,
            require_preserved_facts=False,
        )
        _validate_factual_terms(
            claim.text,
            source_texts,
            claim_terms,
            failures,
            allow_new_terminology=(bullet.support == ClaimConfidence.STRONGLY_IMPLIED),
        )
        _validate_ownership(
            claim.text,
            source_texts,
            failures,
            allow_strong_inference=(bullet.support == ClaimConfidence.STRONGLY_IMPLIED),
        )
        _validate_outcomes(claim.text, source_texts, failures)
        covered_spans.append(claim.text)
    if not covered_spans:
        failures.append("rewritten bullet did not retain claim-level provenance")


def _validate_variant_text(
    text: str,
    groups: list[ApprovedEvidenceGroup],
    support: ClaimConfidence,
    failures: list[str],
    *,
    label: str,
) -> None:
    local_failures: list[str] = []
    source_texts = [source for group in groups for source in group.source_texts]
    known_terms = {term for group in groups for term in [*group.technologies, *group.metrics]}
    _validate_protected_facts(
        text,
        list(known_terms),
        source_texts,
        local_failures,
        require_preserved_facts=False,
    )
    _validate_factual_terms(
        text,
        source_texts,
        list(known_terms),
        local_failures,
        allow_new_terminology=support == ClaimConfidence.STRONGLY_IMPLIED,
    )
    _validate_ownership(
        text,
        source_texts,
        local_failures,
        allow_strong_inference=support == ClaimConfidence.STRONGLY_IMPLIED,
    )
    _validate_outcomes(text, source_texts, local_failures)
    failures.extend(f"{label}: {failure}" for failure in local_failures)


def validate_shortening(output: BulletShorteningOutput, request: BulletShorteningRequest) -> None:
    failures: list[str] = []
    if output.original_bullet_id != request.bullet_id:
        failures.append("shortening references an unknown bullet")
    if output.source_evidence_ids != request.source_evidence_ids:
        failures.append("shortening changed source evidence IDs")
    if not output.no_new_claim_introduced:
        failures.append("shortening did not confirm no new claim")
    _validate_protected_facts(
        output.shortened_text, request.protected_facts, request.source_texts, failures
    )
    if failures:
        raise GroundingValidationError(failures)


def _validate_protected_facts(
    text: str,
    protected_facts: list[str],
    source_texts: list[str],
    failures: list[str],
    *,
    require_preserved_facts: bool = True,
) -> None:
    normalized = text.casefold()
    if require_preserved_facts:
        missing = [fact for fact in protected_facts if fact and fact.casefold() not in normalized]
        if missing:
            failures.append(f"required facts dropped: {missing}")
    source_numbers = set(re.findall(r"\d+(?:\.\d+)?", " ".join(source_texts)))
    result_numbers = set(re.findall(r"\d+(?:\.\d+)?", text))
    introduced = result_numbers - source_numbers
    if introduced:
        failures.append(f"unsupported numeric facts: {sorted(introduced)}")


def _validate_factual_terms(
    text: str,
    source_texts: list[str],
    technologies: list[str],
    failures: list[str],
    *,
    allow_new_terminology: bool = False,
) -> None:
    if allow_new_terminology:
        return
    allowed = _special_terms(" ".join(source_texts)) | {term.casefold() for term in technologies}
    result_terms = _special_terms(text)
    unsupported = result_terms - allowed
    if unsupported:
        failures.append(f"unsupported technical or named terms: {sorted(unsupported)}")


def _special_terms(text: str) -> set[str]:
    acronyms = re.findall(r"\b[A-Z][A-Z0-9+.-]{1,}\b", text)
    camel_case = re.findall(r"\b[A-Z][a-z]+[A-Z][A-Za-z0-9+.-]*\b", text)
    return {term.casefold() for term in [*acronyms, *camel_case]}


def _validate_ownership(
    text: str,
    source_texts: list[str],
    failures: list[str],
    *,
    allow_strong_inference: bool = False,
) -> None:
    levels = {
        "supported": 0,
        "collaborated": 0,
        "developed": 1,
        "implemented": 1,
        "designed": 1,
        "led": 2,
        "owned": 2,
        "architected": 2,
    }
    source_text = " ".join(source_texts).casefold()
    source_level = max(
        (level for verb, level in levels.items() if verb in source_text),
        default=0,
    )
    if allow_strong_inference and any(
        verb in source_text
        for verb in ("built", "developed", "implemented", "designed", "tested", "validated")
    ):
        source_level = max(source_level, 1)
    result_level = max(
        (level for verb, level in levels.items() if verb in text.casefold()), default=0
    )
    if result_level > source_level:
        failures.append("ownership or causality was strengthened beyond source evidence")


def _validate_outcomes(
    text: str,
    source_texts: list[str],
    failures: list[str],
) -> None:
    outcome_terms = {
        "accelerated",
        "decreased",
        "doubled",
        "eliminated",
        "increased",
        "improved",
        "reduced",
        "resolved",
        "saved",
    }
    source = " ".join(source_texts).casefold()
    introduced = sorted(
        term for term in outcome_terms if term in text.casefold() and term not in source
    )
    if introduced:
        failures.append(f"unsupported outcomes: {introduced}")


def _estimated_lines(text: str) -> int:
    return max(1, (len(text) + 89) // 90)
