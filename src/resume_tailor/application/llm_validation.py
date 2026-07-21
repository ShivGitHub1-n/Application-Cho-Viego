from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from pydantic import BaseModel

from resume_tailor.domain.hybrid_resume import GroundingFailureCode
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


@dataclass(frozen=True)
class RewriteGroundingComparison:
    normalized_unsupported_terms: tuple[str, ...]
    ownership_comparison: str
    metric_comparison: str
    causal_outcome_comparison: str
    singular_plural_scope_comparison: str


_NUMBER_WORDS = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
}
_NUMBER_PATTERN = "|".join([r"\d+(?:\.\d+)?", *_NUMBER_WORDS])
_NUMERIC_FACT_PATTERN = re.compile(
    rf"(?P<comparator><=|>=|<|>|\bover\b|\bunder\b|\bmore\s+than\b|"
    rf"\bless\s+than\b|\bwithin\b|\bat\s+most\b|\bup\s+to\b)?\s*"
    rf"(?P<number>{_NUMBER_PATTERN})\s*"
    r"(?P<unit>%|percent(?:age)?|cm|centimeters?|Â°|°|degrees?)?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _NumericFact:
    comparator: str
    number: str
    unit: str


def numeric_semantics_preserved(rewrite: str, source: str) -> bool:
    """Return whether every numeric fact in a rewrite exists in the source.

    Equivalent number words, symbols, and units are canonicalized. Comparator
    direction and boundary strength remain exact; in particular ``within`` is
    not treated as equivalent to a strict less-than claim.
    """

    source_facts = set(_numeric_facts(source))
    return all(fact in source_facts for fact in _numeric_facts(rewrite))


def _numeric_facts(text: str) -> list[_NumericFact]:
    facts: list[_NumericFact] = []
    for match in _NUMERIC_FACT_PATTERN.finditer(text):
        raw_number = match.group("number").casefold()
        number = _NUMBER_WORDS.get(raw_number, raw_number)
        comparator = _canonical_comparator(match.group("comparator") or "")
        unit = _canonical_unit(match.group("unit") or "")
        facts.append(_NumericFact(comparator=comparator, number=number, unit=unit))
    return facts


def _canonical_comparator(value: str) -> str:
    normalized = " ".join(value.casefold().split())
    return {
        "over": ">",
        "more than": ">",
        "under": "<",
        "less than": "<",
        "at most": "<=",
        "up to": "<=",
        "within": "within",
    }.get(normalized, normalized)


def _canonical_unit(value: str) -> str:
    normalized = value.casefold()
    if normalized in {"%", "percent", "percentage"}:
        return "percent"
    if normalized in {"Â°", "°", "degree", "degrees"}:
        return "degree"
    if normalized in {"centimeter", "centimeters"}:
        return "cm"
    return normalized


def grounding_failure_code(failure: str) -> GroundingFailureCode:
    normalized = failure.casefold()
    if "repeat" in normalized or "duplicate" in normalized:
        return GroundingFailureCode.DUPLICATE_EVIDENCE
    if "unknown evidence" in normalized:
        return GroundingFailureCode.UNKNOWN_EVIDENCE
    if "cross-entry" in normalized or "outside its bundle" in normalized:
        return GroundingFailureCode.CROSS_ENTRY_EVIDENCE
    if "incorrect combination" in normalized:
        return GroundingFailureCode.INCORRECT_COMBINATION_STATUS
    if "unsupported generated claim" in normalized:
        return GroundingFailureCode.UNSUPPORTED_CLAIM
    if "claim" in normalized or "provenance" in normalized:
        return GroundingFailureCode.CLAIM_PROVENANCE
    if "numeric" in normalized or "required facts dropped" in normalized:
        return GroundingFailureCode.CHANGED_NUMBER_OR_METRIC
    if "technical or named terms" in normalized or "preserved terms" in normalized:
        return GroundingFailureCode.UNSUPPORTED_TECHNOLOGY_OR_ENTITY
    if "ownership or causality" in normalized:
        return GroundingFailureCode.OWNERSHIP_EXPANSION
    if "causal outcome" in normalized:
        return GroundingFailureCode.UNSUPPORTED_CAUSAL_OUTCOME
    if "unsupported outcomes" in normalized:
        return GroundingFailureCode.UNSUPPORTED_OUTCOME
    if "scope" in normalized or "narrow" in normalized:
        return GroundingFailureCode.UNSUPPORTED_NARROWING_OR_SCOPE
    if "writing policy" in normalized or "job-description phrase" in normalized:
        return GroundingFailureCode.WRITING_POLICY_REJECTION
    return GroundingFailureCode.OTHER_VALIDATION_RULE


def compare_rewrite_grounding(
    text: str,
    source_texts: list[str],
    structured_facts: list[str],
) -> RewriteGroundingComparison:
    source = " ".join(source_texts)
    source_numbers = sorted({item.number for item in _numeric_facts(source)})
    result_numbers = sorted({item.number for item in _numeric_facts(text)})
    source_level = _ownership_level(source)
    result_level = _ownership_level(text)
    introduced_outcomes = _introduced_outcomes(text, source_texts)
    introduced_causal = _introduced_causal_outcomes(text, source_texts)
    allowed_terms = _special_terms(source) | {
        term.casefold() for term in structured_facts
    }
    unsupported_terms = sorted(_special_terms(text) - allowed_terms)
    scope_changes = _singular_plural_scope_changes(text, source)
    return RewriteGroundingComparison(
        normalized_unsupported_terms=tuple(unsupported_terms),
        ownership_comparison=(
            f"source_level={source_level}; rewrite_level={result_level}; "
            f"expanded={result_level > source_level}"
        ),
        metric_comparison=(
            f"source={source_numbers}; rewrite={result_numbers}; "
            f"introduced={sorted(set(result_numbers) - set(source_numbers))}; "
            f"omitted={sorted(set(source_numbers) - set(result_numbers))}"
        ),
        causal_outcome_comparison=(
            f"introduced_outcomes={introduced_outcomes}; "
            f"introduced_causal_phrases={introduced_causal}"
        ),
        singular_plural_scope_comparison=(
            f"pluralized_source_terms={scope_changes}"
            if scope_changes
            else "no_singular_plural_scope_change_detected"
        ),
    )


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
        if len(groups_for_bullet) > 1 and not _same_entry_bundle_is_coherent(
            groups_for_bullet
        ):
            failures.append(
                "same-entry evidence bundle does not describe one coherent engineering story: "
                f"{bullet.source_evidence_ids}"
            )
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
            term
            for item in groups_for_bullet
            for term in [*item.technologies, *item.capabilities, *item.metrics]
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
        if bullet.concise_alternative is not None:
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


def _same_entry_bundle_is_coherent(groups: list[ApprovedEvidenceGroup]) -> bool:
    """Require a connected reviewed-fact story before combining same-entry evidence."""

    if len(groups) < 2:
        return True
    stopwords = {
        "and",
        "built",
        "created",
        "developed",
        "designed",
        "for",
        "from",
        "implemented",
        "the",
        "using",
        "with",
    }

    def group_terms(group: ApprovedEvidenceGroup) -> set[str]:
        exact = {
            " ".join(value.casefold().split())
            for value in [*group.technologies, *group.capabilities]
            if len(value.strip()) >= 3
        }
        lexical = {
            token
            for token in re.findall(
                r"[a-z0-9+#./-]+",
                " ".join(group.source_texts).casefold(),
            )
            if len(token) >= 5 and token not in stopwords
        }
        return exact | lexical

    terms = [group_terms(group) for group in groups]
    reached = {0}
    changed = True
    while changed:
        changed = False
        for index, candidate_terms in enumerate(terms):
            if index in reached:
                continue
            if any(candidate_terms & terms[seen] for seen in reached):
                reached.add(index)
                changed = True
    return len(reached) == len(groups)


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
            term
            for group in claim_groups
            for term in [*group.technologies, *group.capabilities, *group.metrics]
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
    known_terms = {
        term
        for group in groups
        for term in [*group.technologies, *group.capabilities, *group.metrics]
    }
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
    source_text = " ".join(source_texts)
    source_facts = set(_numeric_facts(source_text))
    result_facts = set(_numeric_facts(text))
    introduced = result_facts - source_facts
    if introduced:
        rendered_introduced = sorted(
            f"{item.comparator}{item.number}{item.unit}" for item in introduced
        )
        failures.append(
            "unsupported numeric facts or changed inequality meaning: "
            f"{rendered_introduced}"
        )


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
        "supporting": 0,
        "collaborated": 0,
        "collaborating": 0,
        "built": 1,
        "building": 1,
        "developed": 1,
        "developing": 1,
        "implemented": 1,
        "implementing": 1,
        "designed": 1,
        "designing": 1,
        "led": 2,
        "leading": 2,
        "owned": 2,
        "owning": 2,
        "architected": 2,
        "architecting": 2,
    }
    source_text = " ".join(source_texts)
    source_tokens = set(re.findall(r"[a-z]+", source_text.casefold()))
    source_level = _ownership_level(source_text, levels)
    if allow_strong_inference and any(
        verb in source_tokens
        for verb in ("built", "developed", "implemented", "designed", "tested", "validated")
    ):
        source_level = max(source_level, 1)
    result_level = _ownership_level(text, levels)
    if result_level > source_level:
        failures.append("ownership or causality was strengthened beyond source evidence")


def _validate_outcomes(
    text: str,
    source_texts: list[str],
    failures: list[str],
) -> None:
    introduced = _introduced_outcomes(text, source_texts)
    if introduced:
        failures.append(f"unsupported outcomes: {introduced}")
    introduced_causal = _introduced_causal_outcomes(text, source_texts)
    if introduced_causal:
        failures.append(f"unsupported causal outcome: {introduced_causal}")


def _ownership_level(text: str, levels: dict[str, int] | None = None) -> int:
    configured = levels or {
        "supported": 0,
        "supporting": 0,
        "collaborated": 0,
        "collaborating": 0,
        "built": 1,
        "building": 1,
        "developed": 1,
        "developing": 1,
        "implemented": 1,
        "implementing": 1,
        "designed": 1,
        "designing": 1,
        "led": 2,
        "leading": 2,
        "owned": 2,
        "owning": 2,
        "architected": 2,
        "architecting": 2,
    }
    tokens = set(re.findall(r"[a-z]+", text.casefold()))
    return max(
        (level for verb, level in configured.items() if verb in tokens),
        default=0,
    )


def _introduced_outcomes(text: str, source_texts: list[str]) -> list[str]:
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
    return sorted(
        term for term in outcome_terms if term in text.casefold() and term not in source
    )


def _introduced_causal_outcomes(text: str, source_texts: list[str]) -> list[str]:
    source_tokens = set(re.findall(r"[a-z]+", " ".join(source_texts).casefold()))
    result_tokens = set(re.findall(r"[a-z]+", text.casefold()))
    causal_terms = {"ensure", "ensured", "ensures", "ensuring"}
    return sorted((result_tokens & causal_terms) - source_tokens)


def _singular_plural_scope_changes(text: str, source: str) -> list[str]:
    source_tokens = set(re.findall(r"[a-z][a-z0-9-]*", source.casefold()))
    result_tokens = set(re.findall(r"[a-z][a-z0-9-]*", text.casefold()))
    measurement_units = {"degrees", "milliseconds", "percentages", "seconds"}
    return sorted(
        token
        for token in result_tokens
        if token.endswith("s")
        and token not in measurement_units
        and len(token) > 4
        and token[:-1] in source_tokens
        and token not in source_tokens
    )


def _estimated_lines(text: str) -> int:
    return max(1, (len(text) + 89) // 90)
