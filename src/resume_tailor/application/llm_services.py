from __future__ import annotations

from collections import defaultdict
from typing import Callable, TypeVar

from pydantic import BaseModel

from resume_tailor.application.llm_validation import (
    GroundingValidationError,
    validate_composition,
    validate_rewrites,
    validate_shortening,
)
from resume_tailor.domain.llm_models import (
    ApprovedEvidenceGroup,
    BulletRewriteRequest,
    BulletShorteningRequest,
    CompositionRecommendationRequest,
    EvidenceCoverageSummary,
    EligibleEntry,
    EligibleEvidence,
    LanguageModelError,
    OpportunityAnalysisRequest,
)
from resume_tailor.domain.models import ClaimCandidate, Decision, JobPosting, MasterProfile, TailoringPlan
from resume_tailor.ports.interfaces import ResumeLanguageModel

RequestType = TypeVar("RequestType", bound=BaseModel)
ResultType = TypeVar("ResultType", bound=BaseModel)


class HybridLlmServices:
    def __init__(
        self,
        language_model: ResumeLanguageModel | None,
        retry_count: int,
        max_calls: int,
        enable_opportunity_analysis: bool,
        enable_composition: bool,
        enable_bullet_rewrite: bool,
    ) -> None:
        self._language_model = language_model
        self._retry_count = retry_count
        self._max_calls = max_calls
        self._enable_opportunity_analysis = enable_opportunity_analysis
        self._enable_composition = enable_composition
        self._enable_bullet_rewrite = enable_bullet_rewrite
        self._generation_call_counts: dict[str, int] = {}

    def enrich_plan(self, plan: TailoringPlan, profile: MasterProfile, posting: JobPosting) -> TailoringPlan:
        generation_key = self._generation_key(plan)
        self._generation_call_counts[generation_key] = 0
        if self._language_model is None or plan.strategy is None:
            return plan
        report = plan.report.model_copy(deep=True)
        if self._enable_opportunity_analysis:
            request = OpportunityAnalysisRequest(
                posting_id=posting.id,
                title=posting.title,
                description=posting.description,
                supported_role_families=sorted(
                    {signal.family for signal in report.role.signals}, key=lambda family: family.value
                ),
                evidence_coverage=[
                    EvidenceCoverageSummary(
                        signal_id=signal.id,
                        direct_evidence_ids=(
                            plan.selected_claim_ids
                            if report.profile_fit and signal.id in report.profile_fit.direct_signal_ids
                            else []
                        ),
                        declared_skill_names=(
                            profile.declared_skills
                            if report.profile_fit and signal.id in report.profile_fit.declared_skill_signal_ids
                            else []
                        ),
                    )
                    for signal in report.role.signals
                ],
            )
            result = self._retry(generation_key, self._language_model.analyze_opportunity, request, None)
            if result is not None:
                report.assumptions.append(f"LLM opportunity focus: {result.output.primary_focus}")
        if self._enable_composition:
            request = self._composition_request(plan, profile)
            result = self._retry(
                generation_key,
                self._language_model.recommend_composition,
                request,
                lambda output: validate_composition(
                    output,
                    {entry.entry_id for entry in request.entries},
                    {
                        evidence.evidence_id: entry.entry_id
                        for entry in request.entries
                        for evidence in entry.evidence
                    },
                ),
            )
            if result is not None:
                report.decisions.append(
                    Decision(
                        action="composition_reviewed",
                        entity_id="document",
                        reason=result.output.rationale,
                        evidence_ids=result.output.selected_evidence_ids,
                        constraint="deterministic optimizer remains authoritative",
                    )
                )
        return plan.model_copy(update={"report": report})

    def rewrite_plan(self, plan: TailoringPlan, profile: MasterProfile) -> TailoringPlan:
        if self._language_model is None or not self._enable_bullet_rewrite or plan.strategy is None:
            return plan
        groups = self._approved_groups(plan, profile)
        if not groups:
            return plan
        request = BulletRewriteRequest(primary_focus=plan.strategy.primary_focus, groups=groups)
        generation_key = self._generation_key(plan)
        result = self._retry(generation_key, self._language_model.rewrite_bullets, request, lambda output: validate_rewrites(output, groups))
        self._generation_call_counts.pop(generation_key, None)
        if result is None:
            return plan
        rewritten = {tuple(bullet.source_evidence_ids): bullet for bullet in result.output.bullets}
        candidates: list[ClaimCandidate] = []
        for candidate in plan.claim_candidates:
            rewrite = rewritten.get(tuple(candidate.evidence_ids))
            candidates.append(candidate if rewrite is None else candidate.model_copy(update={"text": rewrite.final_bullet_text}))
        return plan.model_copy(update={"claim_candidates": candidates})

    def shorten_bullet(self, request: BulletShorteningRequest) -> str:
        if self._language_model is None:
            return request.original_text
        generation_key = f"shorten:{request.bullet_id}"
        self._generation_call_counts[generation_key] = 0
        result = self._retry(
            generation_key,
            self._language_model.shorten_bullets,
            request,
            lambda output: validate_shortening(output, request),
        )
        self._generation_call_counts.pop(generation_key, None)
        return request.original_text if result is None else result.output.shortened_text

    def _retry(
        self,
        generation_key: str,
        operation: Callable[[RequestType], ResultType],
        request: RequestType,
        validator: Callable[[object], None] | None,
    ) -> ResultType | None:
        current_request = request
        for _ in range(self._retry_count + 1):
            if self._generation_call_counts.get(generation_key, 0) >= self._max_calls:
                return None
            self._generation_call_counts[generation_key] = self._generation_call_counts.get(generation_key, 0) + 1
            try:
                result = operation(current_request)
                if validator is not None:
                    validator(result.output)
                return result
            except GroundingValidationError as error:
                current_request = current_request.model_copy(update={"correction_notes": error.failures})
            except LanguageModelError as error:
                if not error.retryable:
                    return None
            except ValueError as error:
                current_request = current_request.model_copy(update={"correction_notes": [str(error)]})
        return None

    @staticmethod
    def _generation_key(plan: TailoringPlan) -> str:
        return f"{plan.profile_id}:{plan.profile_version}:{plan.posting_id}"

    @staticmethod
    def _composition_request(plan: TailoringPlan, profile: MasterProfile) -> CompositionRecommendationRequest:
        items = {item.id: item for item in profile.experiences + profile.projects}
        evidence = {item.id: item for item in profile.evidence}
        grouped: defaultdict[str, list[EligibleEvidence]] = defaultdict(list)
        for candidate in plan.claim_candidates:
            source = evidence[candidate.evidence_ids[0]]
            grouped[candidate.entity_id].append(
                EligibleEvidence(
                    evidence_id=source.id,
                    entity_id=source.entity_id,
                    source_text=source.source_text,
                    technologies=source.technologies,
                    outcomes=source.outcomes,
                    estimated_lines=candidate.estimated_lines,
                )
            )
        entries = [
            EligibleEntry(
                entry_id=entry_id,
                title=items[entry_id].title,
                entry_cost_lines=0,
                evidence=entry_evidence,
            )
            for entry_id, entry_evidence in grouped.items()
        ]
        return CompositionRecommendationRequest(
            posting_id=plan.posting_id,
            primary_focus=plan.strategy.primary_focus if plan.strategy else "",
            entries=entries,
            max_total_lines=plan.estimated_lines or 1,
        )

    @staticmethod
    def _approved_groups(plan: TailoringPlan, profile: MasterProfile) -> list[ApprovedEvidenceGroup]:
        evidence_by_id = {item.id: item for item in profile.evidence}
        return [
            ApprovedEvidenceGroup(
                entry_id=candidate.entity_id,
                evidence_ids=candidate.evidence_ids,
                source_texts=[evidence_by_id[evidence_id].source_text for evidence_id in candidate.evidence_ids],
                technologies=[
                    technology
                    for evidence_id in candidate.evidence_ids
                    for technology in evidence_by_id[evidence_id].technologies
                ],
                metrics=[
                    outcome
                    for evidence_id in candidate.evidence_ids
                    for outcome in evidence_by_id[evidence_id].outcomes
                ],
                max_rendered_lines=candidate.max_rendered_lines,
            )
            for candidate in plan.claim_candidates
        ]
