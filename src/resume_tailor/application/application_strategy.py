from __future__ import annotations

import math
import re

from resume_tailor.application.resume_features import normalize_reviewed_text
from resume_tailor.application.title_integrity import conflicting_role_titles
from resume_tailor.domain.application_strategy import (
    ApplicationRolePriority,
    ApplicationStrategyPlan,
    EvidencePriorityTier,
    LowPriorityEntry,
    StrategyEntryPlan,
    StrategyEvidenceChoice,
    StrategyExpansionAction,
    StrategyValidationIssue,
    StrategyValidationIssueCode,
)
from resume_tailor.domain.hybrid_resume import EvidenceRetrievalResult
from resume_tailor.domain.llm_models import ApplicationStrategyOutput
from resume_tailor.domain.models import (
    ClaimCandidate,
    ClaimComposition,
    ClaimSupport,
    Decision,
    EntityKind,
    MasterProfile,
    TailoringPlan,
)


class ApplicationStrategyValidationError(ValueError):
    """Raised when no safe usable part of a provider strategy remains."""


class DeterministicApplicationStrategyValidator:
    """Map provider-selected IDs into a truthful, bounded application strategy."""

    def validate(
        self,
        output: ApplicationStrategyOutput,
        profile: MasterProfile,
        retrieval: EvidenceRetrievalResult,
        plan: TailoringPlan,
        *,
        maximum_selected_entries: int = 7,
        maximum_selected_evidence: int = 24,
    ) -> ApplicationStrategyPlan:
        entries = {item.id: item for item in [*profile.experiences, *profile.projects]}
        evidence = {item.id: item for item in profile.evidence}
        relationships = {
            item.evidence_id: {
                *item.direct_requirement_ids,
                *item.adjacent_requirement_ids,
                *item.complementary_requirement_ids,
            }
            for item in [*retrieval.admitted, *retrieval.rejected]
        }
        requirement_ids = {item.id for item in retrieval.posting_requirements}
        issues: list[StrategyValidationIssue] = []
        selected_entries: list[StrategyEntryPlan] = []
        used_evidence: set[str] = set()

        for proposed_entry in output.selected_entries:
            if len(selected_entries) >= maximum_selected_entries:
                issues.append(
                    StrategyValidationIssue(
                        code=StrategyValidationIssueCode.STRUCTURAL_LIMIT,
                        entry_id=proposed_entry.entry_id,
                        detail="Entry was outside the bounded selected-entry limit.",
                    )
                )
                continue
            entry = entries.get(proposed_entry.entry_id)
            if entry is None:
                issues.append(
                    StrategyValidationIssue(
                        code=StrategyValidationIssueCode.UNKNOWN_ENTRY,
                        entry_id=proposed_entry.entry_id,
                        detail="Provider referenced an unknown profile entry.",
                    )
                )
                continue
            safe_choices: list[StrategyEvidenceChoice] = []
            proposed_choices = [
                *proposed_entry.selected_evidence,
                *proposed_entry.alternative_evidence,
            ]
            for proposed in proposed_choices:
                if len(used_evidence) >= maximum_selected_evidence:
                    issues.append(
                        StrategyValidationIssue(
                            code=StrategyValidationIssueCode.STRUCTURAL_LIMIT,
                            entry_id=entry.id,
                            evidence_id=proposed.evidence_id,
                            detail="Evidence was outside the bounded selected-evidence limit.",
                        )
                    )
                    continue
                source = evidence.get(proposed.evidence_id)
                if source is None:
                    issues.append(
                        StrategyValidationIssue(
                            code=StrategyValidationIssueCode.UNKNOWN_EVIDENCE,
                            entry_id=entry.id,
                            evidence_id=proposed.evidence_id,
                            detail="Provider referenced an unknown evidence item.",
                        )
                    )
                    continue
                if source.entity_id != entry.id:
                    issues.append(
                        StrategyValidationIssue(
                            code=StrategyValidationIssueCode.WRONG_ENTRY,
                            entry_id=entry.id,
                            evidence_id=source.id,
                            detail="Evidence ownership did not match the selected entry.",
                        )
                    )
                    continue
                if not source.confirmed:
                    issues.append(
                        StrategyValidationIssue(
                            code=StrategyValidationIssueCode.UNCONFIRMED_EVIDENCE,
                            entry_id=entry.id,
                            evidence_id=source.id,
                            detail="Unreviewed evidence cannot enter an application strategy.",
                        )
                    )
                    continue
                if source.id in used_evidence:
                    issues.append(
                        StrategyValidationIssue(
                            code=StrategyValidationIssueCode.DUPLICATE_EVIDENCE,
                            entry_id=entry.id,
                            evidence_id=source.id,
                            detail="Evidence may appear only once in the strategy.",
                        )
                    )
                    continue
                supported_requirements = relationships.get(source.id, set())
                safe_requirement_ids = [
                    requirement_id
                    for requirement_id in proposed.requirement_ids
                    if requirement_id in requirement_ids
                    and requirement_id in supported_requirements
                ]
                for requirement_id in proposed.requirement_ids:
                    if requirement_id not in safe_requirement_ids:
                        issues.append(
                            StrategyValidationIssue(
                                code=StrategyValidationIssueCode.UNSUPPORTED_REQUIREMENT,
                                entry_id=entry.id,
                                evidence_id=source.id,
                                detail=(
                                    "Provider requirement attribution was not supported by "
                                    "deterministic evidence matching and was removed."
                                ),
                            )
                        )
                used_evidence.add(source.id)
                safe_choices.append(
                    StrategyEvidenceChoice(
                        evidence_id=source.id,
                        priority=proposed.priority,
                        requirement_ids=list(dict.fromkeys(safe_requirement_ids)),
                        source_wording=proposed.source_wording,
                    )
                )
                if len(safe_choices) >= proposed_entry.desired_depth:
                    break
            if not safe_choices:
                issues.append(
                    StrategyValidationIssue(
                        code=StrategyValidationIssueCode.EMPTY_ENTRY,
                        entry_id=entry.id,
                        detail="No valid reviewed evidence remained for the selected entry.",
                    )
                )
                continue
            if entry.kind is EntityKind.EXPERIENCE and len(safe_choices) < 2:
                used_evidence.difference_update(choice.evidence_id for choice in safe_choices)
                issues.append(
                    StrategyValidationIssue(
                        code=StrategyValidationIssueCode.STRUCTURAL_LIMIT,
                        entry_id=entry.id,
                        detail=(
                            "A professional entry needs a coherent multi-bullet strategy "
                            "package; the isolated item was removed."
                        ),
                    )
                )
                continue
            reason = proposed_entry.reason.strip() or (
                "Selected from reviewed evidence for this application."
            )
            if _contains_conflicting_title_or_seniority(reason, entry.title):
                issues.append(
                    StrategyValidationIssue(
                        code=StrategyValidationIssueCode.TITLE_INTEGRITY,
                        entry_id=entry.id,
                        detail="Conflicting title language was removed from strategy diagnostics.",
                    )
                )
                reason = "Selected from reviewed evidence for this application."
            selected_entries.append(
                StrategyEntryPlan(
                    entry_id=entry.id,
                    reason=reason,
                    desired_depth=len(safe_choices),
                    evidence=safe_choices,
                )
            )

        if not selected_entries:
            raise ApplicationStrategyValidationError(
                "Provider strategy contained no eligible reviewed evidence."
            )

        selected_entry_ids = {item.entry_id for item in selected_entries}
        strategy_entry_ids = set(selected_entry_ids)
        expansion_reserve: list[StrategyExpansionAction] = []

        def add_reserve_action(
            *,
            entry_id: str,
            evidence_ids: list[str],
            priority: EvidencePriorityTier,
            reason: str,
            minimum_coherent_depth: int,
        ) -> None:
            entry = entries.get(entry_id)
            if entry is None:
                issues.append(
                    StrategyValidationIssue(
                        code=StrategyValidationIssueCode.UNKNOWN_ENTRY,
                        entry_id=entry_id,
                        detail="Expansion reserve referenced an unknown profile entry.",
                    )
                )
                return
            requires_heading = entry_id not in selected_entry_ids
            effective_minimum = max(
                minimum_coherent_depth,
                2 if requires_heading and entry.kind is EntityKind.EXPERIENCE else 1,
            )
            if requires_heading and entry_id not in strategy_entry_ids:
                if len(strategy_entry_ids) >= maximum_selected_entries:
                    issues.append(
                        StrategyValidationIssue(
                            code=StrategyValidationIssueCode.STRUCTURAL_LIMIT,
                            entry_id=entry_id,
                            detail="Reserve entry was outside the bounded selected-entry limit.",
                        )
                    )
                    return
            accepted_ids: list[str] = []
            for evidence_id in evidence_ids:
                if len(used_evidence) >= maximum_selected_evidence:
                    issues.append(
                        StrategyValidationIssue(
                            code=StrategyValidationIssueCode.STRUCTURAL_LIMIT,
                            entry_id=entry_id,
                            evidence_id=evidence_id,
                            detail=(
                                "Reserve evidence was outside the final selected-evidence bound."
                            ),
                        )
                    )
                    continue
                source = evidence.get(evidence_id)
                if source is None:
                    issues.append(
                        StrategyValidationIssue(
                            code=StrategyValidationIssueCode.UNKNOWN_EVIDENCE,
                            entry_id=entry_id,
                            evidence_id=evidence_id,
                            detail="Expansion reserve referenced an unknown evidence item.",
                        )
                    )
                    continue
                if source.entity_id != entry_id:
                    issues.append(
                        StrategyValidationIssue(
                            code=StrategyValidationIssueCode.WRONG_ENTRY,
                            entry_id=entry_id,
                            evidence_id=evidence_id,
                            detail="Reserve evidence ownership did not match its entry.",
                        )
                    )
                    continue
                if not source.confirmed:
                    issues.append(
                        StrategyValidationIssue(
                            code=StrategyValidationIssueCode.UNCONFIRMED_EVIDENCE,
                            entry_id=entry_id,
                            evidence_id=evidence_id,
                            detail="Unreviewed evidence cannot enter the expansion reserve.",
                        )
                    )
                    continue
                if source.id in used_evidence:
                    issues.append(
                        StrategyValidationIssue(
                            code=StrategyValidationIssueCode.DUPLICATE_EVIDENCE,
                            entry_id=entry_id,
                            evidence_id=evidence_id,
                            detail="Core and reserve evidence may appear only once.",
                        )
                    )
                    continue
                used_evidence.add(source.id)
                accepted_ids.append(source.id)
            if len(accepted_ids) < effective_minimum:
                used_evidence.difference_update(accepted_ids)
                issues.append(
                    StrategyValidationIssue(
                        code=StrategyValidationIssueCode.STRUCTURAL_LIMIT,
                        entry_id=entry_id,
                        detail=(
                            "Expansion action did not retain its minimum coherent evidence depth."
                        ),
                    )
                )
                return
            safe_reason = reason.strip() or "Adds distinct reviewed application evidence."
            if _contains_conflicting_title_or_seniority(safe_reason, entry.title):
                issues.append(
                    StrategyValidationIssue(
                        code=StrategyValidationIssueCode.TITLE_INTEGRITY,
                        entry_id=entry_id,
                        detail="Conflicting title language was removed from reserve diagnostics.",
                    )
                )
                safe_reason = "Adds distinct reviewed application evidence."
            strategy_entry_ids.add(entry_id)
            expansion_reserve.append(
                StrategyExpansionAction(
                    entry_id=entry_id,
                    evidence_ids=accepted_ids,
                    priority=priority,
                    marginal_value_reason=safe_reason,
                    requires_entry_heading=requires_heading,
                    minimum_coherent_depth=effective_minimum,
                )
            )

        for proposed_entry in output.selected_entries:
            for alternative in [
                *proposed_entry.selected_evidence,
                *proposed_entry.alternative_evidence,
            ]:
                if alternative.evidence_id in used_evidence:
                    continue
                add_reserve_action(
                    entry_id=proposed_entry.entry_id,
                    evidence_ids=[alternative.evidence_id],
                    priority=alternative.priority,
                    reason="Ranked same-entry alternative from the application strategist.",
                    minimum_coherent_depth=1,
                )

        for proposed_action in output.expansion_reserve:
            add_reserve_action(
                entry_id=proposed_action.entry_id,
                evidence_ids=proposed_action.evidence_ids,
                priority=proposed_action.priority,
                reason=proposed_action.marginal_value_reason,
                minimum_coherent_depth=proposed_action.minimum_coherent_depth,
            )

        selected_ids = [
            choice.evidence_id for entry in selected_entries for choice in entry.evidence
        ]
        proposed_global = [
            evidence_id
            for evidence_id in output.global_evidence_priority
            if evidence_id in set(selected_ids)
        ]
        global_priority = list(dict.fromkeys([*proposed_global, *selected_ids]))
        safe_role_priorities = [
            ApplicationRolePriority(
                theme=item.theme,
                requirement_ids=[
                    requirement_id
                    for requirement_id in item.requirement_ids
                    if requirement_id in requirement_ids
                ],
            )
            for item in output.role_priorities
            if item.theme.strip()
        ]
        low_priority_entries = [
            LowPriorityEntry(entry_id=item.entry_id, reason=item.reason)
            for item in output.low_priority_entries
            if item.entry_id in entries
            and item.entry_id not in strategy_entry_ids
        ]
        thesis = output.application_thesis.strip() or plan.strategy.primary_focus
        return ApplicationStrategyPlan(
            application_thesis=thesis,
            role_priorities=safe_role_priorities,
            selected_entries=selected_entries,
            expansion_reserve=expansion_reserve,
            low_priority_entries=low_priority_entries,
            global_evidence_priority=global_priority,
            validation_issues=issues,
        )

    def validate_persisted(
        self,
        strategy: ApplicationStrategyPlan,
        profile: MasterProfile,
        retrieval: EvidenceRetrievalResult,
        *,
        maximum_selected_entries: int = 7,
        maximum_selected_evidence: int = 24,
    ) -> None:
        entries = {item.id: item for item in [*profile.experiences, *profile.projects]}
        evidence = {item.id: item for item in profile.evidence}
        relationships = {
            item.evidence_id: {
                *item.direct_requirement_ids,
                *item.adjacent_requirement_ids,
                *item.complementary_requirement_ids,
            }
            for item in [*retrieval.admitted, *retrieval.rejected]
        }
        seen: set[str] = set()
        core_seen: set[str] = set()
        failures: list[str] = []
        if len(strategy.selected_entries) > maximum_selected_entries:
            failures.append("strategy exceeds selected-entry bound")
        for selected_entry in strategy.selected_entries:
            entry = entries.get(selected_entry.entry_id)
            if entry is None:
                failures.append(f"unknown strategy entry: {selected_entry.entry_id}")
                continue
            for choice in selected_entry.evidence:
                source = evidence.get(choice.evidence_id)
                if source is None:
                    failures.append(f"unknown strategy evidence: {choice.evidence_id}")
                    continue
                if source.entity_id != entry.id:
                    failures.append(f"wrong strategy evidence owner: {choice.evidence_id}")
                if not source.confirmed:
                    failures.append(f"unconfirmed strategy evidence: {choice.evidence_id}")
                if choice.evidence_id in seen:
                    failures.append(f"duplicate strategy evidence: {choice.evidence_id}")
                seen.add(choice.evidence_id)
                core_seen.add(choice.evidence_id)
                unsupported = set(choice.requirement_ids) - relationships.get(
                    choice.evidence_id,
                    set(),
                )
                if unsupported:
                    failures.append(f"unsupported requirement attribution: {choice.evidence_id}")
        strategy_entries = {item.entry_id for item in strategy.selected_entries}
        all_strategy_entries = set(strategy_entries)
        for action in strategy.expansion_reserve:
            entry = entries.get(action.entry_id)
            if entry is None:
                failures.append(f"unknown reserve entry: {action.entry_id}")
                continue
            requires_heading = action.entry_id not in strategy_entries
            if action.requires_entry_heading != requires_heading:
                failures.append(f"incorrect reserve heading authority: {action.entry_id}")
            effective_minimum = max(
                action.minimum_coherent_depth,
                2 if requires_heading and entry.kind is EntityKind.EXPERIENCE else 1,
            )
            valid_depth = 0
            for evidence_id in action.evidence_ids:
                source = evidence.get(evidence_id)
                if source is None:
                    failures.append(f"unknown reserve evidence: {evidence_id}")
                    continue
                if source.entity_id != entry.id:
                    failures.append(f"wrong reserve evidence owner: {evidence_id}")
                if not source.confirmed:
                    failures.append(f"unconfirmed reserve evidence: {evidence_id}")
                if evidence_id in seen:
                    failures.append(f"duplicate strategy evidence: {evidence_id}")
                seen.add(evidence_id)
                valid_depth += 1
            if valid_depth < effective_minimum:
                failures.append(f"incoherent reserve action: {action.entry_id}")
            all_strategy_entries.add(action.entry_id)
        if len(all_strategy_entries) > maximum_selected_entries:
            failures.append("strategy reserve exceeds selected-entry bound")
        if len(seen) > maximum_selected_evidence:
            failures.append("strategy exceeds selected-evidence bound")
        if strategy.global_evidence_priority != list(
            dict.fromkeys(strategy.global_evidence_priority)
        ):
            failures.append("strategy global priority contains duplicates")
        if set(strategy.global_evidence_priority) != core_seen:
            failures.append("strategy global priority does not match selected evidence")
        if failures:
            raise ApplicationStrategyValidationError("; ".join(failures))


class DeterministicApplicationStrategyReconciler:
    """Make a validated strategy the primary portfolio without adding facts."""

    def reconcile(
        self,
        plan: TailoringPlan,
        profile: MasterProfile,
        strategy: ApplicationStrategyPlan,
    ) -> TailoringPlan:
        evidence = {item.id: item for item in profile.evidence}
        entities = {item.id: item for item in [*profile.experiences, *profile.projects]}
        candidates: list[ClaimCandidate] = []
        for evidence_id in strategy.global_evidence_priority:
            source = evidence[evidence_id]
            candidates.append(
                ClaimCandidate(
                    id=f"strategy-source:{source.id}",
                    entity_id=source.entity_id,
                    text=source.source_text,
                    evidence_ids=[source.id],
                    support=ClaimSupport.DIRECT,
                    estimated_lines=max(1, math.ceil(len(source.source_text) / 90)),
                    composition=ClaimComposition.SINGLE,
                    required_terms=[*source.technologies, *source.outcomes],
                    max_rendered_lines=3,
                )
            )
        selected_entry_ids = [entry.entry_id for entry in strategy.selected_entries]
        report = plan.report.model_copy(deep=True)
        report.decisions.append(
            Decision(
                action="application_strategy_applied",
                entity_id="document",
                reason=strategy.application_thesis,
                evidence_ids=strategy.global_evidence_priority,
                constraint=(
                    "reviewed evidence IDs, authoritative entry ownership, structural "
                    "bounds, and deterministic requirement attribution"
                ),
            )
        )
        estimated_lines = sum(candidate.estimated_lines for candidate in candidates)
        estimated_lines += sum(
            plan.constraints.experience_entry_overhead_lines
            if entities[entry_id].kind is EntityKind.EXPERIENCE
            else plan.constraints.project_entry_overhead_lines
            for entry_id in selected_entry_ids
        )
        return plan.model_copy(
            update={
                "application_strategy": strategy,
                "selected_entity_ids": selected_entry_ids,
                "selected_claim_ids": [candidate.id for candidate in candidates],
                "claim_candidates": candidates,
                "selected_experiences": [
                    entities[entry_id]
                    for entry_id in selected_entry_ids
                    if entities[entry_id].kind is EntityKind.EXPERIENCE
                ],
                "selected_projects": [
                    entities[entry_id]
                    for entry_id in selected_entry_ids
                    if entities[entry_id].kind is EntityKind.PROJECT
                ],
                "estimated_lines": estimated_lines,
                "report": report,
            }
        )


__all__ = [
    "ApplicationStrategyValidationError",
    "DeterministicApplicationStrategyReconciler",
    "DeterministicApplicationStrategyValidator",
]


def _contains_conflicting_title_or_seniority(text: str, authoritative_title: str) -> bool:
    if conflicting_role_titles(text, authoritative_title):
        return True
    normalized_text = normalize_reviewed_text(text)
    normalized_title = normalize_reviewed_text(authoritative_title)
    return any(
        re.search(rf"\b{prefix}\s+{re.escape(normalized_title)}\b", normalized_text)
        for prefix in ("lead", "senior", "principal", "manager", "director", "head")
    )
