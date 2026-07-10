from __future__ import annotations

import re

from resume_tailor.domain.llm_models import (
    ApprovedEvidenceGroup,
    BulletRewriteOutput,
    BulletShorteningRequest,
    BulletShorteningOutput,
    CompositionRecommendationOutput,
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


def validate_rewrites(output: BulletRewriteOutput, groups: list[ApprovedEvidenceGroup]) -> None:
    group_by_ids = {tuple(group.evidence_ids): group for group in groups}
    failures: list[str] = []
    if len(output.bullets) != len(groups):
        failures.append("rewrite count does not match approved evidence groups")
    for bullet in output.bullets:
        group = group_by_ids.get(tuple(bullet.source_evidence_ids))
        if group is None:
            failures.append(f"unknown or reordered evidence group: {bullet.source_evidence_ids}")
            continue
        if bullet.entry_id != group.entry_id:
            failures.append(f"cross-entry bullet for {bullet.source_evidence_ids}")
            continue
        if bullet.evidence_combined != (len(group.evidence_ids) > 1):
            failures.append(f"incorrect combination status for {bullet.source_evidence_ids}")
        _validate_protected_facts(
            bullet.final_bullet_text,
            [*group.technologies, *group.metrics],
            group.source_texts,
            failures,
        )
        unknown_terms = set(bullet.preserved_technologies + bullet.preserved_metrics) - set(
            group.technologies + group.metrics
        )
        if unknown_terms:
            failures.append(f"unsupported preserved terms: {sorted(unknown_terms)}")
        _validate_factual_terms(bullet.final_bullet_text, group.source_texts, group.technologies, failures)
        _validate_ownership(bullet.final_bullet_text, group.source_texts, failures)
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
) -> None:
    normalized = text.casefold()
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
) -> None:
    allowed = _special_terms(" ".join(source_texts)) | {term.casefold() for term in technologies}
    result_terms = _special_terms(text)
    unsupported = result_terms - allowed
    if unsupported:
        failures.append(f"unsupported technical or named terms: {sorted(unsupported)}")


def _special_terms(text: str) -> set[str]:
    acronyms = re.findall(r"\b[A-Z][A-Z0-9+.-]{1,}\b", text)
    camel_case = re.findall(r"\b[A-Z][a-z]+[A-Z][A-Za-z0-9+.-]*\b", text)
    return {term.casefold() for term in [*acronyms, *camel_case]}


def _validate_ownership(text: str, source_texts: list[str], failures: list[str]) -> None:
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
    source_level = max(
        (level for verb, level in levels.items() if verb in " ".join(source_texts).casefold()),
        default=0,
    )
    result_level = max((level for verb, level in levels.items() if verb in text.casefold()), default=0)
    if result_level > source_level:
        failures.append("ownership or causality was strengthened beyond source evidence")
