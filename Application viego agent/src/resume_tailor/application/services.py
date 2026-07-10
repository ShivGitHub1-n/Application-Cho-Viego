from resume_tailor.domain.models import JobPosting, MasterProfile, StructuredResume, TailoringPlan
from resume_tailor.ports.interfaces import DecisionEngine, ResumeWriter


class TailorResumeService:
    """Coordinates planning and wording without knowing AI vendor details."""

    def __init__(self, decision_engine: DecisionEngine, resume_writer: ResumeWriter) -> None:
        self._decision_engine = decision_engine
        self._resume_writer = resume_writer

    def create_plan(self, profile: MasterProfile, posting: JobPosting) -> TailoringPlan:
        return self._decision_engine.create_plan(profile, posting)

    def tailor(self, profile: MasterProfile, posting: JobPosting) -> StructuredResume:
        plan = self.create_plan(profile, posting)
        return self._resume_writer.write(plan, profile, posting)

