from __future__ import annotations

import re

from resume_tailor.domain.llm_models import (
    ApprovedEvidenceGroup,
    BulletRewriteOutput,
    BulletShorteningRequest,
    BulletShorteningOutput,
    CompositionRecommendationOutput,
    ProposedDemonstratedSkill,
)
from resume_tailor.domain.models import ClaimConfidence, EvidenceItem


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
        if proposal.confidence == ClaimConfidence.EXPLICITLY_SUPPORTED and evidence_by_id is not None:
            source_text = " ".join(
                " ".join(
                    [item.source_text, *item.technologies, *item.capabilities, *item.outcomes]
                )
                for evidence_id in proposal.source_evidence_ids
                if (item := evidence_by_id.get(evidence_id)) is not None
            ).casefold()
            if proposal.value.casefold() not in source_text:
                failures.append(f"explicit demonstrated skill is not stated in evidence: {proposal.value}")
        if len(set(proposal.source_evidence_ids)) != len(proposal.source_evidence_ids):
            failures.append(f"demonstrated skill repeats evidence IDs: {proposal.value}")
        entry_ids = {
            evidence_to_entry.get(evidence_id)
            for evidence_id in proposal.source_evidence_ids
        }
        if None in entry_ids:
            failures.append(f"demonstrated skill references unknown evidence: {proposal.value}")
        if len(entry_ids - {None}) > 1:
            failures.append(f"demonstrated skill combines evidence across entries: {proposal.value}")
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
        evidence_id: group
        for group in groups
        for evidence_id in group.evidence_ids
    }
    failures: list[str] = []
    entry_bullet_counts: dict[str, int] = {}
    total_lines = 0
    for bullet in output.bullets:
        if len(set(bullet.source_evidence_ids)) != len(bullet.source_evidence_ids):
            failures.append(f"rewrite repeats evidence IDs: {bullet.source_evidence_ids}")
            continue
        source_groups = [group_by_evidence.get(evidence_id) for evidence_id in bullet.source_evidence_ids]
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
        _validate_protected_facts(
            bullet.final_bullet_text,
            [
                fact
                for item in groups_for_bullet
                for fact in [*item.technologies, *item.metrics]
            ],
            [text for item in groups_for_bullet for text in item.source_texts],
            failures,
            require_preserved_facts=False,
        )
        known_terms = {
            term
            for item in groups_for_bullet
            for term in [*item.technologies, *item.metrics]
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
        entry_bullet_counts[bullet.entry_id] = entry_bullet_counts.get(bullet.entry_id, 0) + 1
        total_lines += _estimated_lines(bullet.final_bullet_text)
    if any(count > max_bullets_per_entry for count in entry_bullet_counts.values()):
        failures.append("rewrite exceeds the configured per-entry bullet budget")
    line_budget = max_total_lines if max_total_lines is not None else sum(
        group.max_rendered_lines for group in groups
    )
    if total_lines > line_budget:
        failures.append("rewrite exceeds the selected evidence line budget")
    if failures:
        raise GroundingValidationError(failures)


def validate_shortening(output: BulletShorteningOutput, request: BulletShorteningRequest) -> None:
    failures: list[str] = []
    if output.original_bullet_id != request.bullet_id:
        failures.append("shortening references an unknown bullet")
    if output.source_evidence_ids != request.source_evidence_ids:
        failures.append("shortening changed source evidence IDs")
    if not output.no_new_claim_introduced:
        failures.append("shortening did not confirm no new claim")
    _validate_protected_facts(output.shortened_text, request.protected_facts, request.source_texts, failures)
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
        verb in source_text for verb in ("built", "developed", "implemented", "designed", "tested", "validated")
    ):
        source_level = max(source_level, 1)
    result_level = max((level for verb, level in levels.items() if verb in text.casefold()), default=0)
    if result_level > source_level:
        failures.append("ownership or causality was strengthened beyond source evidence")


def _estimated_lines(text: str) -> int:
    return max(1, (len(text) + 89) // 90)
