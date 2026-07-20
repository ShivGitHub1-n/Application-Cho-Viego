from __future__ import annotations

from collections import defaultdict

from resume_tailor.domain.llm_models import (
    BulletRewriteRequest,
    BulletRewriteResult,
    BulletShorteningRequest,
    BulletShorteningResult,
    CompositionRecommendationRequest,
    CompositionRecommendationResult,
    CoverLetterDraftRequest,
    CoverLetterDraftResult,
    LlmOperation,
    ModelCallMetadata,
    OpportunityAnalysisRequest,
    OpportunityAnalysisResult,
    ProfileExtractionRequest,
    ProfileExtractionResult,
    RoleClassificationRequest,
    RoleClassificationResult,
    SkillCompositionRequest,
    SkillCompositionResult,
)


class FakeResumeLanguageModel:
    def __init__(self, **responses: object) -> None:
        self.responses = {
            name: list(value) if isinstance(value, list) else [value]
            for name, value in responses.items()
        }
        self.calls: defaultdict[str, int] = defaultdict(int)
        self.requests: defaultdict[str, list[object]] = defaultdict(list)

    def analyze_opportunity(self, request: OpportunityAnalysisRequest) -> OpportunityAnalysisResult:
        return self._next("analyze_opportunity", request)

    def classify_role(self, request: RoleClassificationRequest) -> RoleClassificationResult:
        return self._next("classify_role", request)

    def extract_profile(self, request: ProfileExtractionRequest) -> ProfileExtractionResult:
        return self._next("extract_profile", request)

    def recommend_composition(
        self, request: CompositionRecommendationRequest
    ) -> CompositionRecommendationResult:
        return self._next("recommend_composition", request)

    def recommend_skill_composition(
        self, request: SkillCompositionRequest
    ) -> SkillCompositionResult:
        return self._next("recommend_skill_composition", request)

    def rewrite_bullets(self, request: BulletRewriteRequest) -> BulletRewriteResult:
        return self._next("rewrite_bullets", request)

    def shorten_bullets(self, request: BulletShorteningRequest) -> BulletShorteningResult:
        return self._next("shorten_bullets", request)

    def draft_cover_letter(self, request: CoverLetterDraftRequest) -> CoverLetterDraftResult:
        return self._next("draft_cover_letter", request)

    def _next(self, name: str, request: object) -> object:
        self.calls[name] += 1
        self.requests[name].append(request)
        response = self.responses[name].pop(0)
        if isinstance(response, Exception):
            raise response
        if callable(response):
            return response(request)
        return response


def metadata(operation: LlmOperation) -> ModelCallMetadata:
    return ModelCallMetadata(provider="fake", model="fake-model", operation=operation, latency_ms=1)
