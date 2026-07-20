from __future__ import annotations

from collections import Counter

from resume_tailor.domain.hybrid_resume import (
    EvidenceRetrievalResult,
    RetrievalAdmissionStatus,
)
from resume_tailor.domain.models import (
    ClaimCandidate,
    ClaimSupport,
    Decision,
    EntityKind,
    MasterProfile,
    ResumeStrategy,
    TailoringPlan,
)


def apply_generic_technical_fallback(
    plan: TailoringPlan,
    profile: MasterProfile,
    retrieval: EvidenceRetrievalResult,
) -> TailoringPlan:
    """Permit evidence-grounded technical planning without changing role classification."""

    if plan.strategy is not None:
        return plan
    eligible = [
        item
        for item in retrieval.admitted
        if item.admission_status is RetrievalAdmissionStatus.ADMITTED_DIRECT
        and item.contextual_relevance >= 12.0
        and item.intrinsic_evidence_strength >= 10.0
    ]
    if not eligible:
        return plan
    evidence_by_id = {item.id: item for item in profile.evidence}
    entries = {item.id: item for item in [*profile.experiences, *profile.projects]}
    selected: list[ClaimCandidate] = []
    counts: Counter[str] = Counter()
    opened: set[str] = set()
    line_cost = 0
    for item in eligible:
        evidence = evidence_by_id[item.evidence_id]
        entry = entries[item.entry_id]
        estimated_lines = max(1, (len(evidence.source_text) + 89) // 90)
        overhead = (
            plan.constraints.experience_entry_overhead_lines
            if entry.kind is EntityKind.EXPERIENCE
            else plan.constraints.project_entry_overhead_lines
        )
        incremental = estimated_lines + (overhead if entry.id not in opened else 0)
        if (
            counts[entry.id] >= plan.constraints.max_bullets_per_entry
            or line_cost + incremental > plan.constraints.max_total_lines
        ):
            continue
        selected.append(
            ClaimCandidate(
                id=evidence.id,
                entity_id=entry.id,
                text=evidence.source_text,
                evidence_ids=[evidence.id],
                support=ClaimSupport.DIRECT,
                estimated_lines=estimated_lines,
                required_terms=[*evidence.technologies, *evidence.outcomes],
                max_rendered_lines=max(
                    plan.constraints.max_combined_bullet_lines,
                    estimated_lines,
                ),
            )
        )
        counts[entry.id] += 1
        opened.add(entry.id)
        line_cost += incremental
    if not selected:
        return plan
    selected_entry_ids = list(dict.fromkeys(candidate.entity_id for candidate in selected))
    report = plan.report.model_copy(deep=True)
    report.decisions.append(
        Decision(
            action="generic_evidence_grounded_resume_fallback",
            entity_id="document",
            reason=(
                "The existing role classifier remained unchanged; generic reviewed-text "
                "retrieval established sufficient specific technical evidence for resume "
                "planning."
            ),
            evidence_ids=[candidate.evidence_ids[0] for candidate in selected],
            constraint="specific direct posting overlap and reviewed evidence only",
        )
    )
    report.warnings.append(
        "Role-family classification was unsupported; generic evidence retrieval supplied "
        "the resume-planning strategy without changing classification output."
    )
    return plan.model_copy(
        update={
            "strategy": ResumeStrategy(
                role_family="evidence_grounded_technical",
                primary_focus=plan.posting.title,
                rationale=(
                    "Generic reviewed evidence directly supports the technical posting; "
                    "role-family classification is advisory rather than content authority."
                ),
            ),
            "selected_entity_ids": selected_entry_ids,
            "selected_claim_ids": [candidate.id for candidate in selected],
            "claim_candidates": selected,
            "education": profile.education,
            "selected_experiences": [
                item for item in profile.experiences if item.id in selected_entry_ids
            ],
            "selected_projects": [
                item for item in profile.projects if item.id in selected_entry_ids
            ],
            "estimated_lines": line_cost,
            "report": report,
        }
    )


__all__ = ["apply_generic_technical_fallback"]
