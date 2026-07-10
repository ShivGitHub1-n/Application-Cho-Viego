from __future__ import annotations

from collections import defaultdict

from resume_tailor.domain.llm_models import (
    BulletRewriteRequest,
    BulletRewriteResult,
    BulletShorteningRequest,
    BulletShorteningResult,
    CompositionRecommendationRequest,
    CompositionRecommendationResult,
    LlmOperation,
    ModelCallMetadata,
    OpportunityAnalysisRequest,
    OpportunityAnalysisResult,
)


class FakeResumeLanguageModel:
    def __init__(self, **responses: object) -> None:
        self.responses = {name: list(value) if isinstance(value, list) else [value] for name, value in responses.items()}
        self.calls: defaultdict[str, int] = defaultdict(int)

    def analyze_opportunity(self, request: OpportunityAnalysisRequest) -> OpportunityAnalysisResult:
        return self._next("analyze_opportunity")

    def recommend_composition(
        self, request: CompositionRecommendationRequest
    ) -> CompositionRecommendationResult:
        return self._next("recommend_composition")

    def rewrite_bullets(self, request: BulletRewriteRequest) -> BulletRewriteResult:
        return self._next("rewrite_bullets")

    def shorten_bullets(self, request: BulletShorteningRequest) -> BulletShorteningResult:
        return self._next("shorten_bullets")

    def _next(self, name: str) -> object:
        self.calls[name] += 1
        response = self.responses[name].pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def metadata(operation: LlmOperation) -> ModelCallMetadata:
    return ModelCallMetadata(provider="fake", model="fake-model", operation=operation, latency_ms=1)
