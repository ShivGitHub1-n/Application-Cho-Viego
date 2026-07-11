from resume_tailor.application.llm_services import HybridLlmServices
from resume_tailor.application.plan_validation import DeterministicPlanIntegrityValidator
from resume_tailor.domain.models import (
    JobPosting,
    MasterProfile,
    StructuredResume,
    TailoringPlan,
    TemplateConstraints,
)
from resume_tailor.ports.interfaces import ResumeOptimizer, ResumeWriter


class TailorResumeService:
    """Coordinates opportunity-specific planning and evidence-bound document assembly."""

    def __init__(
        self,
        optimizer: ResumeOptimizer,
        resume_writer: ResumeWriter,
        hybrid_services: HybridLlmServices | None = None,
    ) -> None:
        self._optimizer = optimizer
        self._resume_writer = resume_writer
        self._hybrid_services = hybrid_services
        self._plan_validator = DeterministicPlanIntegrityValidator(optimizer)

    def create_plan(
        self,
        profile: MasterProfile,
        posting: JobPosting,
        constraints: TemplateConstraints,
    ) -> TailoringPlan:
        plan = self._optimizer.create_plan(profile, posting, constraints)
        if self._hybrid_services is None:
            return plan
        return self._hybrid_services.enrich_plan(plan, profile, posting)

    def build_document(
        self,
        plan: TailoringPlan,
        profile: MasterProfile,
        approved_claim_ids: set[str],
    ) -> StructuredResume:
        self._plan_validator.validate(plan, profile)
        rewritten_plan = (
            self._hybrid_services.rewrite_plan(plan, profile)
            if self._hybrid_services is not None
            else plan
        )
        return self._resume_writer.write(rewritten_plan, profile, approved_claim_ids)
