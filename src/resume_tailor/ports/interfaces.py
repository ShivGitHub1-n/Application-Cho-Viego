from pathlib import Path
from typing import Protocol

from resume_tailor.domain.models import (
    JobPosting,
    MasterProfile,
    RoleClassification,
    StructuredResume,
    TailoringPlan,
    TemplateConstraints,
)
from resume_tailor.domain.llm_models import (
    BulletRewriteRequest,
    BulletRewriteResult,
    BulletShorteningRequest,
    BulletShorteningResult,
    CompositionRecommendationRequest,
    CompositionRecommendationResult,
    OpportunityAnalysisRequest,
    OpportunityAnalysisResult,
    SkillCompositionRequest,
    SkillCompositionResult,
)


class MasterProfileRepository(Protocol):
    def get(self, profile_id: str) -> MasterProfile | None: ...

    def save(self, profile: MasterProfile) -> None: ...


class OpportunityAnalyzer(Protocol):
    def analyze(self, posting: JobPosting) -> RoleClassification: ...


class ResumeOptimizer(Protocol):
    def create_plan(
        self,
        profile: MasterProfile,
        posting: JobPosting,
        constraints: TemplateConstraints,
    ) -> TailoringPlan: ...


class ResumeWriter(Protocol):
    def write(
        self,
        plan: TailoringPlan,
        profile: MasterProfile,
        approved_claim_ids: set[str],
    ) -> StructuredResume: ...


class ResumeLanguageModel(Protocol):
    def analyze_opportunity(self, request: OpportunityAnalysisRequest) -> OpportunityAnalysisResult: ...

    def recommend_composition(
        self, request: CompositionRecommendationRequest
    ) -> CompositionRecommendationResult: ...

    def recommend_skill_composition(
        self, request: SkillCompositionRequest
    ) -> SkillCompositionResult: ...

    def rewrite_bullets(self, request: BulletRewriteRequest) -> BulletRewriteResult: ...

    def shorten_bullets(self, request: BulletShorteningRequest) -> BulletShorteningResult: ...


class RenderResult(Protocol):
    docx_path: Path
    pdf_path: Path
    page_count: int


class ResumeRenderer(Protocol):
    def render(self, resume: StructuredResume, output_directory: Path) -> RenderResult: ...
