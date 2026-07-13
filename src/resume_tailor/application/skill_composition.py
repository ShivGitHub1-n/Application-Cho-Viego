from __future__ import annotations

from hashlib import sha256

from resume_tailor.application.llm_validation import (
    GroundingValidationError,
    validate_demonstrated_skills,
)
from resume_tailor.domain.llm_models import SkillCompositionOutput
from resume_tailor.domain.models import (
    ClaimConfidence,
    ClaimSupport,
    Decision,
    GeneratedSkill,
    MasterProfile,
    RankedSkillCategory,
    SkillCategorySelection,
    SkillCompositionSelection,
    SkillSelectionStatus,
    TailoringPlan,
)


class SkillCompositionReconciliationError(ValueError):
    pass


class DeterministicSkillCompositionReconciler:
    """Replays a model proposal using immutable reviewed skill records."""

    def reconcile(
        self,
        plan: TailoringPlan,
        profile: MasterProfile,
        output: SkillCompositionOutput,
    ) -> TailoringPlan:
        eligible_categories = {
            category.id: category
            for category in plan.ranked_skill_categories
            if category.status != SkillSelectionStatus.EXCLUDED_UNRELATED
            and category.id in {selected.id for selected in plan.selected_skill_categories}
        }
        reviewed_categories = {category.id: category for category in profile.technical_skills}
        evidence_to_entry = {item.id: item.entity_id for item in profile.evidence if item.confirmed}
        try:
            validate_demonstrated_skills(
                output.demonstrated_skills,
                set(eligible_categories),
                evidence_to_entry,
                {item.id: item for item in profile.evidence if item.confirmed},
            )
        except GroundingValidationError as error:
            raise SkillCompositionReconciliationError(str(error)) from error
        proposed_category_ids = [category.category_id for category in output.categories]
        if len(proposed_category_ids) > plan.constraints.max_skill_lines:
            raise SkillCompositionReconciliationError(
                "skill composition exceeds configured initial category bound"
            )
        if len(proposed_category_ids) != len(set(proposed_category_ids)):
            raise SkillCompositionReconciliationError("skill category appears more than once")
        seen_skills: set[str] = set()
        selected: list[RankedSkillCategory] = []
        selection_categories: list[SkillCategorySelection] = []
        for category_order, proposal in enumerate(output.categories):
            ranked = eligible_categories.get(proposal.category_id)
            reviewed = reviewed_categories.get(proposal.category_id)
            if ranked is None or reviewed is None:
                raise SkillCompositionReconciliationError("unknown or ineligible skill category")
            if proposal.label != ranked.label or proposal.label != reviewed.category:
                raise SkillCompositionReconciliationError("skill category label changed")
            ranked_skills = {skill.id: skill for skill in ranked.skills}
            reviewed_skills = {skill.id: skill for skill in reviewed.skills}
            skill_ids = [skill.skill_id for skill in proposal.skills]
            if len(skill_ids) != len(set(skill_ids)):
                raise SkillCompositionReconciliationError("skill appears more than once in a category")
            selected_skills = []
            for skill_order, proposed_skill in enumerate(proposal.skills):
                if proposed_skill.skill_id in seen_skills:
                    raise SkillCompositionReconciliationError("skill appears in multiple categories")
                ranked_skill = ranked_skills.get(proposed_skill.skill_id)
                reviewed_skill = reviewed_skills.get(proposed_skill.skill_id)
                if ranked_skill is None or reviewed_skill is None:
                    raise SkillCompositionReconciliationError(
                        "unknown skill or skill moved between categories"
                    )
                if (
                    proposed_skill.value != ranked_skill.value
                    or proposed_skill.value != reviewed_skill.value
                ):
                    raise SkillCompositionReconciliationError("skill value changed")
                seen_skills.add(proposed_skill.skill_id)
                selected_skills.append(
                    ranked_skill.model_copy(
                        update={
                            "status": SkillSelectionStatus.SELECTED,
                            "selected_order": skill_order,
                        }
                    )
                )
            selected.append(
                ranked.model_copy(
                    update={
                        "status": SkillSelectionStatus.SELECTED,
                        "selected_order": category_order,
                        "skills": selected_skills,
                    }
                )
            )
            selection_categories.append(
                SkillCategorySelection(category_id=proposal.category_id, skill_ids=skill_ids)
            )

        selected_category_ids = {category.id for category in selected}
        ranked_pool = []
        for category in plan.ranked_skill_categories:
            if category.id in selected_category_ids:
                chosen = next(item for item in selected if item.id == category.id)
                chosen_ids = {skill.id for skill in chosen.skills}
                pool_skills = [
                    next(skill for skill in chosen.skills if skill.id == original.id)
                    if original.id in chosen_ids
                    else original.model_copy(
                        update={
                            "status": (
                                SkillSelectionStatus.ALTERNATE
                                if original.relevance_score > 0
                                else original.status
                            ),
                            "selected_order": None,
                        }
                    )
                    for original in category.skills
                ]
                ranked_pool.append(chosen.model_copy(update={"skills": pool_skills}))
            else:
                ranked_pool.append(
                    category.model_copy(
                        update={
                            "status": (
                                SkillSelectionStatus.ALTERNATE
                                if category.status == SkillSelectionStatus.SELECTED
                                else category.status
                            ),
                            "selected_order": None,
                            "skills": [
                                skill.model_copy(
                                    update={
                                        "status": (
                                            SkillSelectionStatus.ALTERNATE
                                            if skill.status == SkillSelectionStatus.SELECTED
                                            else skill.status
                                        ),
                                        "selected_order": None,
                                    }
                                )
                                for skill in category.skills
                            ],
                        }
                    )
                )
        selected_profile_categories = []
        for category in selected:
            reviewed = reviewed_categories[category.id]
            selected_ids = {skill.id for skill in category.skills}
            skills = [skill for skill in reviewed.skills if skill.id in selected_ids]
            skills.sort(key=lambda skill: next(s.selected_order for s in category.skills if s.id == skill.id))
            selected_profile_categories.append(
                reviewed.model_copy(
                    update={"skills": skills, "values": [skill.value for skill in skills]}
                )
            )
        report = plan.report.model_copy(deep=True)
        report.decisions.append(
            Decision(
                action="gemini_skill_composition_applied",
                entity_id="technical-skills",
                reason=output.rationale,
                constraint="validated reviewed category and skill IDs only",
            )
        )
        deterministic_shape = [
            (category.id, [skill.id for skill in category.skills])
            for category in plan.selected_skill_categories
        ]
        selected_shape = [
            (category.id, [skill.id for skill in category.skills])
            for category in selected
        ]
        if [item[0] for item in selected_shape] != [item[0] for item in deterministic_shape]:
            report.decisions.append(
                Decision(
                    action="gemini_skill_reordering_applied",
                    entity_id="technical-skills",
                    reason="Validated composition changed category ordering or category emphasis.",
                )
            )
        deterministic_skill_ids = {
            skill_id for _, skill_ids in deterministic_shape for skill_id in skill_ids
        }
        selected_skill_ids = {skill_id for _, skill_ids in selected_shape for skill_id in skill_ids}
        if deterministic_skill_ids - selected_skill_ids:
            report.decisions.append(
                Decision(
                    action="gemini_skill_narrowing_applied",
                    entity_id="technical-skills",
                    reason="Validated composition removed weak or redundant skills from the initial set.",
                )
            )
        selection = SkillCompositionSelection(
            categories=selection_categories,
            rationale=output.rationale,
            demonstrated_skills=[
                _generated_skill(proposal.category_id, proposal.value, proposal.source_evidence_ids, proposal.confidence)
                for proposal in output.demonstrated_skills
            ],
        )
        return plan.model_copy(
            update={
                "technical_skills": selected_profile_categories,
                "selected_skill_categories": selected,
                "ranked_skill_categories": ranked_pool,
                "selected_skills": [
                    skill.value for category in selected for skill in category.skills
                ],
                "skill_composition_selection": selection,
                "demonstrated_skills": selection.demonstrated_skills,
                "report": report,
            }
        )

    def replay(
        self,
        plan: TailoringPlan,
        profile: MasterProfile,
        selection: SkillCompositionSelection,
    ) -> TailoringPlan:
        from resume_tailor.domain.llm_models import (
            ProposedSkill,
            ProposedSkillCategory,
            ProposedDemonstratedSkill,
            SkillCompositionOutput,
        )

        categories = {category.id: category for category in profile.technical_skills}
        return self.reconcile(
            plan,
            profile,
            SkillCompositionOutput(
                categories=[
                    ProposedSkillCategory(
                        category_id=item.category_id,
                        label=categories[item.category_id].category,
                        skills=[
                            ProposedSkill(
                                skill_id=skill_id,
                                value=next(
                                    skill.value
                                    for skill in categories[item.category_id].skills
                                    if skill.id == skill_id
                                ),
                            )
                            for skill_id in item.skill_ids
                        ],
                    )
                    for item in selection.categories
                ],
                demonstrated_skills=[
                    ProposedDemonstratedSkill(
                        category_id=skill.category_id,
                        value=skill.value,
                        source_evidence_ids=skill.evidence_ids,
                        confidence=(
                            ClaimConfidence.EXPLICITLY_SUPPORTED
                            if skill.support in {ClaimSupport.DIRECT, ClaimSupport.DERIVED}
                            else ClaimConfidence.STRONGLY_IMPLIED
                        ),
                        rationale="Replayed from validated skill composition selection.",
                    )
                    for skill in selection.demonstrated_skills
                ],
                rationale=selection.rationale,
            ),
        )


def _generated_skill(
    category_id: str,
    value: str,
    evidence_ids: list[str],
    confidence: ClaimConfidence,
) -> GeneratedSkill:
    digest = sha256(
        f"{category_id}\0{value.casefold()}\0{'|'.join(evidence_ids)}".encode()
    ).hexdigest()[:12]
    support = (
        ClaimSupport.DIRECT
        if confidence == ClaimConfidence.EXPLICITLY_SUPPORTED
        else ClaimSupport.STRONG_INFERENCE_PENDING_REVIEW
    )
    return GeneratedSkill(
        id=f"demonstrated-skill:{digest}",
        category_id=category_id,
        value=value,
        evidence_ids=evidence_ids,
        support=support,
    )
