from resume_tailor.application.composition import (
    CompositionReconciliationError,
    DeterministicCompositionReconciler,
)
from resume_tailor.application.hybrid_plan import apply_generic_technical_fallback
from resume_tailor.application.skill_composition import (
    DeterministicSkillCompositionReconciler,
    SkillCompositionReconciliationError,
)
from resume_tailor.domain.models import MasterProfile, TailoringPlan
from resume_tailor.ports.interfaces import ResumeEvidenceRetriever, ResumeOptimizer


class PlanIntegrityError(ValueError):
    """Raised when an untrusted plan differs from deterministic server reconstruction."""


class DeterministicPlanIntegrityValidator:
    def __init__(
        self,
        optimizer: ResumeOptimizer,
        evidence_retriever: ResumeEvidenceRetriever | None = None,
    ) -> None:
        self._optimizer = optimizer
        self._composition_reconciler = DeterministicCompositionReconciler()
        self._skill_composition_reconciler = DeterministicSkillCompositionReconciler()
        self._evidence_retriever = evidence_retriever

    def validate(self, plan: TailoringPlan, profile: MasterProfile) -> None:
        failures = self._structural_failures(plan, profile)
        if not failures:
            trusted = self._optimizer.create_plan(profile, plan.posting, plan.constraints)
            if self._evidence_retriever is not None:
                trusted = apply_generic_technical_fallback(
                    trusted,
                    profile,
                    self._evidence_retriever.retrieve(profile, plan.posting),
                )
            if plan.composition_selection is not None:
                try:
                    trusted = self._composition_reconciler.reconcile(
                        trusted, profile, plan.composition_selection
                    )
                except CompositionReconciliationError as error:
                    failures.append(str(error))
            if plan.skill_composition_selection is not None:
                try:
                    trusted = self._skill_composition_reconciler.replay(
                        trusted, profile, plan.skill_composition_selection
                    )
                except (SkillCompositionReconciliationError, KeyError, StopIteration) as error:
                    failures.append(f"invalid skill composition: {error}")
            failures.extend(self._reconstruction_failures(plan, trusted))
        if failures:
            raise PlanIntegrityError("Invalid tailoring plan: " + "; ".join(failures))

    @staticmethod
    def _structural_failures(plan: TailoringPlan, profile: MasterProfile) -> list[str]:
        failures: list[str] = []
        if plan.profile_id != profile.id or plan.profile_version != profile.version:
            failures.append("profile identity or version does not match")
        if plan.posting_id != plan.posting.id:
            failures.append("posting identity does not match")
        if plan.template_id != plan.constraints.template_id:
            failures.append("template identity does not match")

        entities = {item.id for item in profile.experiences + profile.projects}
        evidence_to_entity = {item.id: item.entity_id for item in profile.evidence}
        for candidate in plan.claim_candidates:
            if candidate.entity_id not in entities:
                failures.append(f"unknown candidate entity ID: {candidate.entity_id}")
            for evidence_id in candidate.evidence_ids:
                evidence_entity = evidence_to_entity.get(evidence_id)
                if evidence_entity is None:
                    failures.append(f"unknown candidate evidence ID: {evidence_id}")
                elif evidence_entity != candidate.entity_id:
                    failures.append(
                        f"evidence {evidence_id} belongs to {evidence_entity}, "
                        f"not {candidate.entity_id}"
                    )
        return failures

    @staticmethod
    def _reconstruction_failures(plan: TailoringPlan, trusted: TailoringPlan) -> list[str]:
        failures: list[str] = []
        comparable_fields = (
            "strategy",
            "selected_entity_ids",
            "selected_claim_ids",
            "claim_candidates",
            "selected_skills",
            "selected_coursework",
            "education",
            "technical_skills",
            "selected_skill_categories",
            "ranked_skill_categories",
            "skill_composition_selection",
            "selected_experiences",
            "selected_projects",
            "estimated_lines",
            "composition_selection",
            "demonstrated_skills",
        )
        for field in comparable_fields:
            if getattr(plan, field) != getattr(trusted, field):
                failures.append(f"{field} differs from deterministic server reconstruction")
        return failures
