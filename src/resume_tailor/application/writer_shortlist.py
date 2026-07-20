from __future__ import annotations

from collections import Counter

from resume_tailor.application.resume_features import TemplateV1BulletLineEstimator
from resume_tailor.application.resume_writing_policy import (
    DEFAULT_RESUME_WRITING_POLICY,
    ResumeWritingPolicy,
)
from resume_tailor.domain.hybrid_resume import (
    EvidenceRetrievalResult,
    RetrievedEvidence,
    WriterShortlistCandidate,
)
from resume_tailor.domain.llm_models import ApprovedEvidenceGroup
from resume_tailor.domain.models import EvidenceItem, MasterProfile, StructuredResume
from resume_tailor.domain.requirement_ranking import (
    EvidenceRelationship,
    PostingRequirement,
)


def build_writer_shortlist(
    resume: StructuredResume,
    profile: MasterProfile,
    retrieval: EvidenceRetrievalResult,
    *,
    policy: ResumeWritingPolicy = DEFAULT_RESUME_WRITING_POLICY,
    line_estimator: TemplateV1BulletLineEstimator | None = None,
) -> tuple[list[ApprovedEvidenceGroup], list[WriterShortlistCandidate]]:
    """Build a bounded, entry-balanced writing set before final portfolio selection."""

    estimator = line_estimator or TemplateV1BulletLineEstimator()
    evidence_by_id = {item.id: item for item in profile.evidence if item.confirmed}
    selected_source_ids = {
        evidence_id
        for section in (resume.experience_bullets, resume.project_bullets)
        for bullets in section.values()
        for bullet in bullets
        for evidence_id in bullet.evidence_ids
    }
    eligible = [
        item
        for item in retrieval.admitted
        if item.evidence_id in evidence_by_id
        and (
            item.relationship is not EvidenceRelationship.COMPLEMENTARY
            or item.intrinsic_evidence_strength >= 15.0
        )
    ]
    by_id = {item.evidence_id: item for item in eligible}
    selected_first = [
        by_id[evidence_id] for evidence_id in selected_source_ids if evidence_id in by_id
    ]
    selected_first.sort(key=lambda item: (item.rank, item.evidence_id))

    best_by_entry: dict[str, RetrievedEvidence] = {}
    for item in eligible:
        best_by_entry.setdefault(item.entry_id, item)
    credible_alternatives = sorted(
        best_by_entry.values(),
        key=_shortlist_sort_key,
    )
    remaining = sorted(eligible, key=_shortlist_sort_key)
    ordered = _deduplicate_evidence([*selected_first, *credible_alternatives, *remaining])

    selected: list[RetrievedEvidence] = []
    entry_counts: Counter[str] = Counter()
    for item in ordered:
        if len(selected) >= policy.maximum_shortlisted_evidence:
            break
        if entry_counts[item.entry_id] >= policy.maximum_shortlisted_evidence_per_entry:
            continue
        selected.append(item)
        entry_counts[item.entry_id] += 1

    selected_ids = {item.evidence_id for item in selected}
    entry_first_ids = {item.evidence_id for item in credible_alternatives}
    requirements = {requirement.id: requirement for requirement in retrieval.posting_requirements}
    diagnostics = [
        WriterShortlistCandidate(
            evidence_id=item.evidence_id,
            entry_id=item.entry_id,
            entry_kind=item.entry_kind,
            relationship=item.relationship,
            contextual_relevance=item.contextual_relevance,
            intrinsic_evidence_strength=item.intrinsic_evidence_strength,
            selected=item.evidence_id in selected_ids,
            selection_reason=_selection_reason(
                item.evidence_id,
                item.entry_id,
                selected_source_ids,
                entry_first_ids,
                item.relationship,
                item.intrinsic_evidence_strength,
                selected=item.evidence_id in selected_ids,
            ),
        )
        for item in eligible
    ]
    groups = [
        _group_for(
            item,
            evidence_by_id[item.evidence_id],
            requirements,
            estimator,
            diagnostics,
        )
        for item in selected
    ]
    return groups, diagnostics


def _group_for(
    retrieved: RetrievedEvidence,
    evidence: EvidenceItem,
    requirements: dict[str, PostingRequirement],
    estimator: TemplateV1BulletLineEstimator,
    diagnostics: list[WriterShortlistCandidate],
) -> ApprovedEvidenceGroup:
    requirement_ids = [
        *retrieved.direct_requirement_ids,
        *retrieved.adjacent_requirement_ids,
        *retrieved.complementary_requirement_ids,
    ]
    diagnostic = next(item for item in diagnostics if item.evidence_id == retrieved.evidence_id)
    line_fit = estimator.estimate(evidence.source_text)
    return ApprovedEvidenceGroup(
        entry_id=evidence.entity_id,
        evidence_ids=[evidence.id],
        source_texts=[evidence.source_text],
        technologies=list(evidence.technologies),
        capabilities=list(evidence.capabilities),
        metrics=list(evidence.outcomes),
        relationship_tier=retrieved.relationship,
        posting_requirement_ids=list(dict.fromkeys(requirement_ids)),
        posting_requirements=[
            requirements[requirement_id].text
            for requirement_id in dict.fromkeys(requirement_ids)
            if requirement_id in requirements
        ],
        intrinsic_evidence_strength=retrieved.intrinsic_evidence_strength,
        shortlist_reason=diagnostic.selection_reason,
        max_rendered_lines=max(1, min(3, line_fit.expected_line_count)),
    )


def _shortlist_sort_key(
    item: RetrievedEvidence,
) -> tuple[int, float, float, int, str]:
    relationship_order = {
        EvidenceRelationship.DIRECT: 0,
        EvidenceRelationship.ADJACENT: 1,
        EvidenceRelationship.COMPLEMENTARY: 2,
        EvidenceRelationship.INCIDENTAL: 3,
        EvidenceRelationship.REJECTED: 4,
    }
    return (
        relationship_order[item.relationship],
        -item.contextual_relevance,
        -item.intrinsic_evidence_strength,
        item.rank,
        item.evidence_id,
    )


def _deduplicate_evidence(
    items: list[RetrievedEvidence],
) -> list[RetrievedEvidence]:
    output: list[RetrievedEvidence] = []
    seen: set[str] = set()
    for item in items:
        if item.evidence_id in seen:
            continue
        seen.add(item.evidence_id)
        output.append(item)
    return output


def _selection_reason(
    evidence_id: str,
    entry_id: str,
    selected_source_ids: set[str],
    entry_first_ids: set[str],
    relationship: EvidenceRelationship,
    intrinsic_strength: float,
    *,
    selected: bool,
) -> str:
    if not selected:
        return "Excluded by the bounded writer shortlist after stronger or more distinct evidence."
    reasons: list[str] = []
    if evidence_id in selected_source_ids:
        reasons.append("present in the initial deterministic composition")
    if evidence_id in entry_first_ids:
        reasons.append("keeps a credible alternative entry available to final portfolio search")
    if relationship is EvidenceRelationship.DIRECT:
        reasons.append("directly addresses a core or important posting requirement")
    elif relationship is EvidenceRelationship.ADJACENT:
        reasons.append("provides strong adjacent transferable evidence")
    else:
        reasons.append("provides intrinsically strong complementary evidence")
    if intrinsic_strength >= 30:
        reasons.append("retains substantial reviewed technical depth")
    return "Shortlisted because it " + "; ".join(reasons) + f" ({entry_id})."


__all__ = ["build_writer_shortlist"]
