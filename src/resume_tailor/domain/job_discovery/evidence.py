"""Evidence authority and single-use requirement contribution ledger."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable

from pydantic import BaseModel, Field

from resume_tailor.domain.job_discovery.capabilities import normalize_capability_term
from resume_tailor.domain.job_discovery.models import (
    EvidenceQuality,
    JobRequirement,
    ProfileCapabilityEvidence,
    ProfileCapabilityIndex,
    RequirementCriticality,
    RequirementImportance,
    RequirementMatchStatus,
)


class CanonicalRequirement(BaseModel):
    requirement_id: str
    term: str
    source_text: str
    source_context: str
    criticality: RequirementCriticality
    aliases: list[str] = Field(default_factory=list)
    source_start: int = 0
    source_end: int = 0
    profile_evidence_references: list[str] = Field(default_factory=list)


class RequirementEvidenceReference(BaseModel):
    evidence_id: str
    source_type: str
    source_text: str
    quality: EvidenceQuality


class RequirementMatch(BaseModel):
    requirement_id: str
    status: RequirementMatchStatus
    evidence: list[RequirementEvidenceReference] = Field(default_factory=list)
    evidence_quality: EvidenceQuality = EvidenceQuality.ABSENT
    allocated_evidence_id: str | None = None
    scored: bool = False
    authority_references: list[str] = Field(default_factory=list)


class EvidenceAllocation(BaseModel):
    evidence_id: str
    primary_requirement_id: str | None = None
    full_strength: bool = False
    contextual_requirement_ids: list[str] = Field(default_factory=list)


class EvidenceLedger(BaseModel):
    matches: list[RequirementMatch] = Field(default_factory=list)
    allocations: list[EvidenceAllocation] = Field(default_factory=list)

    @classmethod
    def allocate(
        cls,
        requirements: Iterable[CanonicalRequirement],
        profile_index: ProfileCapabilityIndex,
    ) -> EvidenceLedger:
        ordered_requirements = sorted(
            requirements,
            key=lambda item: (
                -_criticality_rank(item.criticality),
                item.requirement_id,
            ),
        )
        candidates: dict[str, list[RequirementEvidenceReference]] = {}
        for requirement in ordered_requirements:
            terms = sorted(
                {
                    normalize_capability_term(requirement.term),
                    *map(normalize_capability_term, requirement.aliases),
                }
            )
            found: dict[tuple[str, str], RequirementEvidenceReference] = {}
            for term in terms:
                if not term:
                    continue
                for evidence in profile_index.terms.get(term, []):
                    reference = _evidence_reference(evidence)
                    found[(reference.evidence_id, reference.quality.value)] = reference
            direct_ids = set(requirement.profile_evidence_references)
            if direct_ids:
                for reference in _all_evidence(profile_index):
                    if reference.evidence_id in direct_ids:
                        found[(reference.evidence_id, reference.quality.value)] = reference
            candidates[requirement.requirement_id] = sorted(found.values(), key=_evidence_sort_key)

        used: set[str] = set()
        matches: list[RequirementMatch] = []
        allocations: dict[str, EvidenceAllocation] = {}
        for requirement in ordered_requirements:
            evidence = candidates[requirement.requirement_id]
            primary = next(
                (item for item in evidence if _usable(item.quality)),
                None,
            )
            if primary is None:
                status = (
                    RequirementMatchStatus.UNRESOLVED if evidence else RequirementMatchStatus.ABSENT
                )
                matches.append(
                    RequirementMatch(
                        requirement_id=requirement.requirement_id,
                        status=status,
                        evidence=evidence,
                        evidence_quality=(
                            evidence[0].quality if evidence else EvidenceQuality.ABSENT
                        ),
                        authority_references=[requirement.requirement_id],
                    )
                )
                continue

            allocation = allocations.setdefault(
                primary.evidence_id,
                EvidenceAllocation(evidence_id=primary.evidence_id),
            )
            if primary.evidence_id not in used and _quality_is_usable_for(
                requirement, primary.quality
            ):
                used.add(primary.evidence_id)
                allocation.primary_requirement_id = requirement.requirement_id
                allocation.full_strength = True
                matches.append(
                    RequirementMatch(
                        requirement_id=requirement.requirement_id,
                        status=RequirementMatchStatus.MATCHED,
                        evidence=evidence,
                        evidence_quality=primary.quality,
                        allocated_evidence_id=primary.evidence_id,
                        scored=True,
                        authority_references=[requirement.requirement_id, primary.evidence_id],
                    )
                )
            else:
                if primary.evidence_id in used:
                    allocation.contextual_requirement_ids.append(requirement.requirement_id)
                matches.append(
                    RequirementMatch(
                        requirement_id=requirement.requirement_id,
                        status=(
                            RequirementMatchStatus.MATCHED
                            if primary.quality
                            in {EvidenceQuality.DEMONSTRATED, EvidenceQuality.TRANSFERABLE}
                            else RequirementMatchStatus.INSUFFICIENT
                        ),
                        evidence=evidence,
                        evidence_quality=primary.quality,
                        allocated_evidence_id=primary.evidence_id,
                        authority_references=[requirement.requirement_id, primary.evidence_id],
                    )
                )

        return cls(
            matches=sorted(matches, key=lambda item: item.requirement_id),
            allocations=sorted(allocations.values(), key=lambda item: item.evidence_id),
        )


def canonical_requirement_set(
    requirements: Iterable[JobRequirement],
) -> list[CanonicalRequirement]:
    grouped: dict[str, list[JobRequirement]] = {}
    for requirement in requirements:
        term = normalize_capability_term(requirement.term)
        if term:
            grouped.setdefault(term, []).append(requirement)

    result: list[CanonicalRequirement] = []
    for term, values in sorted(grouped.items()):
        ordered = sorted(
            values,
            key=lambda item: (item.source_start, item.source_end, item.source_text.casefold()),
        )
        first = ordered[0]
        criticality = max(
            (_criticality_for(item) for item in ordered),
            key=_criticality_rank,
        )
        aliases = sorted({term, *(normalize_capability_term(item.term) for item in ordered)})
        aliases = sorted({*aliases, *(alias for item in ordered for alias in item.aliases)})
        profile_evidence_references = sorted(
            {reference for item in ordered for reference in item.evidence_references}
        )
        requirement_id = first.requirement_id or _stable_requirement_id(
            term, first.source_text, first.source_start
        )
        result.append(
            CanonicalRequirement(
                requirement_id=requirement_id,
                term=term,
                source_text=first.source_text,
                source_context=first.source_text,
                criticality=criticality,
                aliases=aliases,
                source_start=min(item.source_start for item in ordered),
                source_end=max(item.source_end for item in ordered),
                profile_evidence_references=profile_evidence_references,
            )
        )
    return result


def evidence_quality(evidence: ProfileCapabilityEvidence) -> EvidenceQuality:
    if evidence.evidence_quality is not None:
        return evidence.evidence_quality
    if evidence.demonstrated and evidence.source_type in {"confirmed_evidence", "resume_item"}:
        return EvidenceQuality.DEMONSTRATED
    if evidence.source_type == "reviewed_skill":
        return EvidenceQuality.REVIEWED_SKILL
    if evidence.source_type in {"coursework", "education"}:
        return EvidenceQuality.COURSEWORK_CONTEXT
    if evidence.demonstrated:
        return EvidenceQuality.TRANSFERABLE
    return EvidenceQuality.ABSENT


def _criticality_for(requirement: JobRequirement) -> RequirementCriticality:
    if requirement.criticality is not None:
        return requirement.criticality
    text = requirement.source_text.casefold()
    if re.search(r"\bcritical\b|\bmust have\b|\bmandatory\b", text):
        return RequirementCriticality.CRITICAL
    if requirement.importance is RequirementImportance.REQUIRED:
        return RequirementCriticality.IMPORTANT
    return RequirementCriticality.SUPPORTING


def _criticality_rank(value: RequirementCriticality) -> int:
    return {
        RequirementCriticality.CRITICAL: 3,
        RequirementCriticality.IMPORTANT: 2,
        RequirementCriticality.SUPPORTING: 1,
    }[value]


def _evidence_reference(evidence: ProfileCapabilityEvidence) -> RequirementEvidenceReference:
    return RequirementEvidenceReference(
        evidence_id=evidence.source_id,
        source_type=evidence.source_type,
        source_text=evidence.source_text,
        quality=evidence_quality(evidence),
    )


def _evidence_sort_key(evidence: RequirementEvidenceReference) -> tuple[int, str, str]:
    rank = {
        EvidenceQuality.DEMONSTRATED: 5,
        EvidenceQuality.TRANSFERABLE: 4,
        EvidenceQuality.REVIEWED_SKILL: 3,
        EvidenceQuality.COURSEWORK_CONTEXT: 2,
        EvidenceQuality.ABSENT: 1,
    }
    return (-rank[evidence.quality], evidence.evidence_id, evidence.source_text.casefold())


def _usable(quality: EvidenceQuality) -> bool:
    return quality is not EvidenceQuality.ABSENT


def _quality_is_usable_for(requirement: CanonicalRequirement, quality: EvidenceQuality) -> bool:
    if requirement.criticality is RequirementCriticality.CRITICAL:
        return quality in {EvidenceQuality.DEMONSTRATED, EvidenceQuality.TRANSFERABLE}
    return quality in {
        EvidenceQuality.DEMONSTRATED,
        EvidenceQuality.TRANSFERABLE,
    }


def _all_evidence(profile_index: ProfileCapabilityIndex) -> list[RequirementEvidenceReference]:
    unique: dict[tuple[str, str], RequirementEvidenceReference] = {}
    for evidence_items in profile_index.terms.values():
        for evidence in evidence_items:
            reference = _evidence_reference(evidence)
            unique[(reference.evidence_id, reference.quality.value)] = reference
    return sorted(unique.values(), key=_evidence_sort_key)


def _stable_requirement_id(term: str, source_text: str, source_start: int) -> str:
    digest = hashlib.sha256(f"{term}|{source_start}|{source_text}".encode()).hexdigest()[:16]
    return f"requirement:{digest}"


__all__ = [
    "CanonicalRequirement",
    "EvidenceAllocation",
    "EvidenceLedger",
    "EvidenceQuality",
    "RequirementCriticality",
    "RequirementEvidenceReference",
    "RequirementMatch",
    "canonical_requirement_set",
    "evidence_quality",
]
