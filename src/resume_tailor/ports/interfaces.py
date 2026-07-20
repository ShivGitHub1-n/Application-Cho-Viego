from pathlib import Path
from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

from resume_tailor.domain.hybrid_resume import EvidenceRetrievalResult
from resume_tailor.domain.llm_models import (
    BulletRewriteRequest,
    BulletRewriteResult,
    BulletShorteningRequest,
    BulletShorteningResult,
    CompositionRecommendationRequest,
    CompositionRecommendationResult,
    CoverLetterDraftRequest,
    CoverLetterDraftResult,
    OpportunityAnalysisRequest,
    OpportunityAnalysisResult,
    ProfileExtractionRequest,
    ProfileExtractionResult,
    RoleClassificationRequest,
    RoleClassificationResult,
    SkillCompositionRequest,
    SkillCompositionResult,
)
from resume_tailor.domain.models import (
    JobPosting,
    MasterProfile,
    RoleClassification,
    StructuredResume,
    TailoringPlan,
    TemplateConstraints,
)
from resume_tailor.domain.resume_composition import PageFitEvaluation

CacheModelT = TypeVar("CacheModelT", bound=BaseModel)


class RoleClassificationCacheError(RuntimeError):
    """Expected operational failure while reading or writing role-classification cache data."""


@runtime_checkable
class RoleClassificationCache(Protocol):
    def key_for(self, operation: str, model: str, payload: BaseModel) -> str: ...

    def get(self, key: str, result_type: type[CacheModelT]) -> CacheModelT | None: ...

    def set(self, key: str, value: BaseModel) -> None: ...


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


class ResumeEvidenceRetriever(Protocol):
    def retrieve(
        self,
        profile: MasterProfile,
        posting: JobPosting,
    ) -> EvidenceRetrievalResult: ...


class ResumeWriter(Protocol):
    def write(
        self,
        plan: TailoringPlan,
        profile: MasterProfile,
        approved_claim_ids: set[str],
    ) -> StructuredResume: ...


class ResumeLanguageModel(Protocol):
    def extract_profile(self, request: ProfileExtractionRequest) -> ProfileExtractionResult: ...

    def classify_role(self, request: RoleClassificationRequest) -> RoleClassificationResult: ...

    def analyze_opportunity(
        self,
        request: OpportunityAnalysisRequest,
    ) -> OpportunityAnalysisResult: ...

    def recommend_composition(
        self, request: CompositionRecommendationRequest
    ) -> CompositionRecommendationResult: ...

    def recommend_skill_composition(
        self, request: SkillCompositionRequest
    ) -> SkillCompositionResult: ...

    def rewrite_bullets(self, request: BulletRewriteRequest) -> BulletRewriteResult: ...

    def shorten_bullets(self, request: BulletShorteningRequest) -> BulletShorteningResult: ...

    def draft_cover_letter(self, request: CoverLetterDraftRequest) -> CoverLetterDraftResult: ...


class RenderResult(Protocol):
    docx_path: Path
    pdf_path: Path
    page_count: int


class ResumeRenderer(Protocol):
    def render(self, resume: StructuredResume, output_directory: Path) -> RenderResult: ...


class ResumeArtifactRenderer(Protocol):
    def render_docx_bytes(self, resume: StructuredResume) -> bytes: ...


class ResumePageFitEvaluator(Protocol):
    def evaluate(
        self,
        resume: StructuredResume,
        *,
        attempt_exact: bool = True,
    ) -> PageFitEvaluation: ...
