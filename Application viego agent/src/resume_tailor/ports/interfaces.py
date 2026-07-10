from pathlib import Path
from typing import Protocol

from resume_tailor.domain.models import (
    JobPosting,
    MasterProfile,
    StructuredResume,
    TailoringPlan,
)


class MasterProfileRepository(Protocol):
    def get(self, profile_id: str) -> MasterProfile | None: ...

    def save(self, profile: MasterProfile) -> None: ...


class DecisionEngine(Protocol):
    def create_plan(self, profile: MasterProfile, posting: JobPosting) -> TailoringPlan: ...


class ResumeWriter(Protocol):
    def write(self, plan: TailoringPlan, profile: MasterProfile, posting: JobPosting) -> StructuredResume: ...


class ResumeRenderer(Protocol):
    def render_docx(self, resume: StructuredResume, template_id: str) -> Path: ...

