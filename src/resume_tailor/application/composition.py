from collections import defaultdict

from resume_tailor.domain.models import (
    ClaimCandidate,
    ClaimSupport,
    CompositionSelection,
    Decision,
    EntityKind,
    MasterProfile,
    ResumeItem,
    TailoringPlan,
)


class CompositionReconciliationError(ValueError):
    pass


class DeterministicCompositionReconciler:
    """Applies an LLM selection only by reusing trusted deterministic candidates."""

    def reconcile(
        self,
        plan: TailoringPlan,
        profile: MasterProfile,
        selection: CompositionSelection,
    ) -> TailoringPlan:
        evidence = {item.id: item for item in profile.evidence}
        entities = {item.id: item for item in profile.experiences + profile.projects}
        selected_evidence = selection.selected_evidence_ids
        if len(selected_evidence) != len(set(selected_evidence)):
            raise CompositionReconciliationError("selected evidence IDs contain duplicates")

        candidates_by_group = {
            (candidate.entity_id, tuple(candidate.evidence_ids)): candidate
            for candidate in plan.claim_candidates
        }
        used: set[str] = set()
        selected_candidates: list[ClaimCandidate] = []
        for group in selection.evidence_groups:
            key = (group.entry_id, tuple(group.evidence_ids))
            candidate = candidates_by_group.get(key)
            if candidate is None:
                raise CompositionReconciliationError("group is not an eligible deterministic candidate")
            if used.intersection(group.evidence_ids):
                raise CompositionReconciliationError("evidence appears in multiple groups")
            used.update(group.evidence_ids)
            selected_candidates.append(candidate)

        for evidence_id in selected_evidence:
            if evidence_id in used:
                continue
            matches = [
                candidate
                for candidate in plan.claim_candidates
                if candidate.evidence_ids == [evidence_id]
            ]
            if len(matches) != 1:
                raise CompositionReconciliationError(
                    f"evidence {evidence_id} is not an eligible standalone candidate"
                )
            selected_candidates.append(matches[0])
            used.add(evidence_id)

        if used != set(selected_evidence):
            raise CompositionReconciliationError("grouped evidence does not match selected evidence")
        for candidate in selected_candidates:
            if candidate.support not in {ClaimSupport.DIRECT, ClaimSupport.DERIVED}:
                raise CompositionReconciliationError("composition cannot promote weak support")
            if candidate.entity_id not in entities:
                raise CompositionReconciliationError("composition references an unknown entity")
            for evidence_id in candidate.evidence_ids:
                item = evidence.get(evidence_id)
                if item is None or not item.confirmed:
                    raise CompositionReconciliationError("composition references ineligible evidence")
                if item.entity_id != candidate.entity_id:
                    raise CompositionReconciliationError("composition combines evidence across entries")

        by_entity: defaultdict[str, list[ClaimCandidate]] = defaultdict(list)
        for candidate in selected_candidates:
            by_entity[candidate.entity_id].append(candidate)
        if set(selection.selected_entry_ids) != set(by_entity):
            raise CompositionReconciliationError("selected entries do not match selected evidence")
        if len(selection.selected_entry_ids) != len(set(selection.selected_entry_ids)):
            raise CompositionReconciliationError("selected entry IDs contain duplicates")

        ordered = [candidate for entry_id in selection.selected_entry_ids for candidate in by_entity[entry_id]]
        self._validate_budgets(ordered, entities, plan)
        estimated_lines = self._line_cost(ordered, entities, plan)
        report = plan.report.model_copy(deep=True)
        report.decisions.append(
            Decision(
                action="composition_applied",
                entity_id="document",
                reason=selection.rationale,
                evidence_ids=selected_evidence,
                constraint="validated against deterministic eligibility and content budgets",
            )
        )
        selected_ids = {candidate.id for candidate in ordered}
        for candidate in plan.claim_candidates:
            if candidate.id not in selected_ids:
                report.decisions.append(
                    Decision(
                        action="composition_removed",
                        entity_id=candidate.entity_id,
                        reason="Excluded by the validated composition recommendation.",
                        evidence_ids=candidate.evidence_ids,
                        constraint="deterministic candidate remained eligible but was not selected",
                    )
                )
        return plan.model_copy(
            update={
                "selected_entity_ids": selection.selected_entry_ids,
                "selected_claim_ids": [candidate.id for candidate in ordered],
                "claim_candidates": ordered,
                "estimated_lines": estimated_lines,
                "composition_selection": selection,
                "report": report,
            }
        )

    def _validate_budgets(
        self,
        candidates: list[ClaimCandidate],
        entities: dict[str, ResumeItem],
        plan: TailoringPlan,
    ) -> None:
        constraints = plan.constraints
        counts: defaultdict[str, int] = defaultdict(int)
        section_lines = {EntityKind.EXPERIENCE: 0, EntityKind.PROJECT: 0}
        opened: set[str] = set()
        for candidate in candidates:
            counts[candidate.entity_id] += 1
            if counts[candidate.entity_id] > constraints.max_bullets_per_entry:
                raise CompositionReconciliationError("composition exceeds bullets per entry")
            entity = entities[candidate.entity_id]
            kind = entity.kind
            if candidate.entity_id not in opened:
                section_lines[kind] += (
                    constraints.experience_entry_overhead_lines
                    if kind == EntityKind.EXPERIENCE
                    else constraints.project_entry_overhead_lines
                )
                opened.add(candidate.entity_id)
            section_lines[kind] += candidate.estimated_lines
        if section_lines[EntityKind.EXPERIENCE] > constraints.max_experience_lines:
            raise CompositionReconciliationError("composition exceeds experience line budget")
        if section_lines[EntityKind.PROJECT] > constraints.max_project_lines:
            raise CompositionReconciliationError("composition exceeds project line budget")
        if self._line_cost(candidates, entities, plan) > constraints.max_total_lines:
            raise CompositionReconciliationError("composition exceeds total line budget")

    @staticmethod
    def _line_cost(
        candidates: list[ClaimCandidate],
        entities: dict[str, ResumeItem],
        plan: TailoringPlan,
    ) -> int:
        opened: set[str] = set()
        total = int(bool(plan.selected_skills)) + int(bool(plan.selected_coursework))
        for candidate in candidates:
            if candidate.entity_id not in opened:
                kind = entities[candidate.entity_id].kind
                total += (
                    plan.constraints.experience_entry_overhead_lines
                    if kind == EntityKind.EXPERIENCE
                    else plan.constraints.project_entry_overhead_lines
                )
                opened.add(candidate.entity_id)
            total += candidate.estimated_lines
        return total
