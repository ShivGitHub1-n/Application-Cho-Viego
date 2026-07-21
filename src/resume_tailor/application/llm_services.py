from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Callable
from difflib import SequenceMatcher
from hashlib import sha256
from typing import Any, TypeVar, cast

from pydantic import BaseModel

from resume_tailor.application.composition import (
    CompositionReconciliationError,
    DeterministicCompositionReconciler,
)
from resume_tailor.application.generation_diagnostics import GenerationTelemetry
from resume_tailor.application.llm_validation import (
    GroundingValidationError,
    compare_rewrite_grounding,
    grounding_failure_code,
    numeric_semantics_preserved,
    validate_composition,
    validate_rewrites,
    validate_shortening,
)
from resume_tailor.application.profile_extraction import (
    audit_extracted_profile,
    normalize_extracted_profile,
)
from resume_tailor.application.requirement_ranking import extract_posting_requirements
from resume_tailor.application.resume_features import (
    TemplateV1BulletLineEstimator,
    extract_reviewed_text_features,
)
from resume_tailor.application.resume_writing_policy import (
    DEFAULT_RESUME_WRITING_POLICY,
    ResumeWritingPolicy,
)
from resume_tailor.application.skill_composition import (
    DeterministicSkillCompositionReconciler,
    SkillCompositionReconciliationError,
)
from resume_tailor.application.writer_shortlist import build_writer_shortlist
from resume_tailor.domain.generated_artifact import GenerationStage
from resume_tailor.domain.hybrid_resume import (
    BulletLengthClass,
    BulletValidationStatus,
    BulletVariantRecord,
    ClaimValidationStatus,
    EvidenceRetrievalResult,
    GroundedClaim,
    GroundingFailureCode,
    HybridPlanningStatus,
    HybridResumeDiagnostic,
    ProviderRequestShapeDiagnostic,
    ProviderRewriteMappingOutcome,
    ProviderRewriteMappingStatus,
    WriterExecutionStatus,
    WriterPipelineFailureCode,
    WriterPipelineIssue,
    WriterPipelineStage,
    WriterRewriteDiagnostic,
)
from resume_tailor.domain.llm_models import (
    ApprovedEvidenceGroup,
    BulletRewrite,
    BulletRewriteClaim,
    BulletRewriteOutput,
    BulletRewriteRequest,
    BulletRewriteResult,
    BulletShorteningRequest,
    CompositionRecommendationRequest,
    EligibleEntry,
    EligibleEvidence,
    EligibleSkill,
    EligibleSkillCategory,
    EvidenceCoverageSummary,
    LanguageModelError,
    LanguageModelErrorKind,
    ModelResult,
    OpportunityAnalysisRequest,
    ProfileExtractionRequest,
    ProfileExtractionResult,
    SkillCompositionRequest,
)
from resume_tailor.domain.models import (
    ClaimCandidate,
    ClaimComposition,
    ClaimConfidence,
    ClaimSupport,
    CompositionEvidenceGroup,
    CompositionSelection,
    Decision,
    JobPosting,
    MasterProfile,
    SkillSelectionStatus,
    StructuredBullet,
    StructuredResume,
    TailoringPlan,
    TemplateConstraints,
)
from resume_tailor.domain.requirement_ranking import EvidenceRelationship, RequirementAuthority
from resume_tailor.domain.resume_composition import BulletLineFitDiagnostic
from resume_tailor.ports.interfaces import ResumeLanguageModel

RequestType = TypeVar("RequestType", bound=BaseModel)
ResultType = TypeVar("ResultType", bound=ModelResult)


class HybridLlmServices:
    def __init__(
        self,
        language_model: ResumeLanguageModel | None,
        retry_count: int,
        max_calls: int,
        enable_opportunity_analysis: bool,
        enable_composition: bool,
        enable_bullet_rewrite: bool,
        composition_reconciler: DeterministicCompositionReconciler | None = None,
        skill_composition_reconciler: DeterministicSkillCompositionReconciler | None = None,
        provider_name: str = "configured-provider",
        model_name: str = "configured-model",
        writing_policy: ResumeWritingPolicy = DEFAULT_RESUME_WRITING_POLICY,
        telemetry: GenerationTelemetry | None = None,
        provider_unavailable_reason: str | None = None,
    ) -> None:
        self._language_model = language_model
        self._retry_count = retry_count
        self._max_calls = max_calls
        self._enable_opportunity_analysis = enable_opportunity_analysis
        self._enable_composition = enable_composition
        self._enable_bullet_rewrite = enable_bullet_rewrite
        self._composition_reconciler = (
            composition_reconciler or DeterministicCompositionReconciler()
        )
        self._skill_composition_reconciler = (
            skill_composition_reconciler or DeterministicSkillCompositionReconciler()
        )
        self._generation_call_counts: dict[str, int] = {}
        self._generation_cache_hits: dict[str, int] = {}
        self._rewrite_cache: dict[str, TailoringPlan] = {}
        self._resume_rewrite_cache: dict[
            str,
            tuple[
                list[BulletVariantRecord],
                list[BulletVariantRecord],
                list[WriterRewriteDiagnostic],
                str | None,
                str | None,
                ProviderRequestShapeDiagnostic | None,
            ],
        ] = {}
        self._provider_name = provider_name
        self._model_name = model_name
        self._writing_policy = writing_policy
        self._telemetry = telemetry or GenerationTelemetry()
        self._line_estimator = TemplateV1BulletLineEstimator()
        self._last_validation_failures: list[str] = []
        self._last_planning_provider_calls = 0
        self._last_planning_cache_hits = 0
        self._last_planning_status = HybridPlanningStatus.DETERMINISTIC_ONLY
        self._last_planning_reason = "Deterministic planning remained authoritative."
        self._last_retry_failure_kind: str | None = None
        self._last_writer_pipeline_issue: WriterPipelineIssue | None = None
        self._provider_unavailable_reason = provider_unavailable_reason

    def set_telemetry(self, telemetry: GenerationTelemetry) -> None:
        self._telemetry = telemetry

    @property
    def writing_enabled(self) -> bool:
        return self._language_model is not None and self._enable_bullet_rewrite

    def enrich_plan(
        self, plan: TailoringPlan, profile: MasterProfile, posting: JobPosting
    ) -> TailoringPlan:
        generation_key = self._generation_key(plan)
        self._generation_call_counts[generation_key] = 0
        self._generation_cache_hits[generation_key] = 0
        if self._language_model is None or plan.strategy is None:
            self._last_planning_provider_calls = 0
            self._last_planning_cache_hits = 0
            self._last_planning_status = HybridPlanningStatus.DETERMINISTIC_ONLY
            self._last_planning_reason = (
                "Semantic planning was disabled or unavailable; deterministic "
                "planning remained authoritative."
            )
            return plan
        enriched = plan
        report = enriched.report.model_copy(deep=True)
        if self._enable_opportunity_analysis:
            opportunity_request = OpportunityAnalysisRequest(
                posting_id=posting.id,
                title=posting.title,
                description=posting.description,
                supported_role_families=sorted(
                    {signal.family for signal in report.role.signals},
                    key=lambda family: family.value,
                ),
                evidence_coverage=[
                    EvidenceCoverageSummary(
                        signal_id=signal.id,
                        direct_evidence_ids=(
                            plan.selected_claim_ids
                            if report.profile_fit
                            and signal.id in report.profile_fit.direct_signal_ids
                            else []
                        ),
                        declared_skill_names=(
                            profile.declared_skills
                            if report.profile_fit
                            and signal.id in report.profile_fit.declared_skill_signal_ids
                            else []
                        ),
                    )
                    for signal in report.role.signals
                ],
            )
            opportunity_result = self._retry(
                generation_key,
                self._language_model.analyze_opportunity,
                opportunity_request,
                None,
            )
            if opportunity_result is not None:
                report.assumptions.append(
                    f"LLM opportunity focus: {opportunity_result.output.primary_focus}"
                )
        enriched = plan.model_copy(update={"report": report})
        if self._enable_composition and enriched.ranked_skill_categories:
            skill_request = self._skill_composition_request(enriched, profile)
            if skill_request is not None:
                skill_result = self._retry(
                    generation_key,
                    self._language_model.recommend_skill_composition,
                    skill_request,
                    None,
                )
                if skill_result is not None:
                    try:
                        enriched = self._skill_composition_reconciler.reconcile(
                            enriched, profile, skill_result.output
                        )
                    except SkillCompositionReconciliationError as error:
                        enriched = self._skill_fallback(enriched, str(error))
                else:
                    enriched = self._skill_fallback(
                        enriched, "Provider or schema failure; deterministic selection preserved."
                    )
        if self._enable_composition:
            composition_request = self._composition_request(plan, profile)
            composition_result = self._retry(
                generation_key,
                self._language_model.recommend_composition,
                composition_request,
                lambda output: validate_composition(
                    output,
                    {entry.entry_id for entry in composition_request.entries},
                    {
                        evidence.evidence_id: entry.entry_id
                        for entry in composition_request.entries
                        for evidence in entry.evidence
                    },
                ),
            )
            if composition_result is not None:
                selection = CompositionSelection(
                    selected_entry_ids=composition_result.output.selected_entry_ids,
                    selected_evidence_ids=composition_result.output.selected_evidence_ids,
                    evidence_groups=[
                        CompositionEvidenceGroup(
                            entry_id=group.entry_id,
                            evidence_ids=group.evidence_ids,
                        )
                        for group in composition_result.output.proposed_evidence_groupings
                    ],
                    rationale=composition_result.output.rationale,
                )
                try:
                    enriched = self._composition_reconciler.reconcile(enriched, profile, selection)
                except CompositionReconciliationError:
                    pass
        self._last_planning_provider_calls = self._generation_call_counts.get(
            generation_key,
            0,
        )
        self._last_planning_cache_hits = self._generation_cache_hits.get(
            generation_key,
            0,
        )
        semantic_planning_enabled = self._enable_opportunity_analysis or self._enable_composition
        self._last_planning_status = (
            HybridPlanningStatus.ADVISORY_APPLIED
            if semantic_planning_enabled and enriched != plan
            else HybridPlanningStatus.ADVISORY_REJECTED
            if semantic_planning_enabled and self._last_planning_provider_calls
            else HybridPlanningStatus.DETERMINISTIC_ONLY
        )
        self._last_planning_reason = (
            "Bounded semantic planning adjusted only supplied evidence references; "
            "deterministic composition retained final authority."
            if self._last_planning_status is HybridPlanningStatus.ADVISORY_APPLIED
            else "Semantic planning returned no admissible adjustment; deterministic "
            "planning was preserved."
            if self._last_planning_status is HybridPlanningStatus.ADVISORY_REJECTED
            else "Semantic planning was disabled; deterministic planning remained authoritative."
        )
        return enriched

    def diagnostic_for_retrieval(
        self,
        retrieval: EvidenceRetrievalResult,
    ) -> HybridResumeDiagnostic:
        return HybridResumeDiagnostic(
            retrieval=retrieval,
            planning_status=self._last_planning_status,
            planning_reason=self._last_planning_reason,
            provider_call_count=self._last_planning_provider_calls,
            provider_cache_hits=self._last_planning_cache_hits,
        )

    def rewrite_composed_resume(
        self,
        resume: StructuredResume,
        profile: MasterProfile,
        posting: JobPosting,
        constraints: TemplateConstraints,
        approved_claim_ids: set[str],
    ) -> StructuredResume:
        """Write once from a deterministic shortlist, then reuse variants during page search."""

        diagnostic = resume.hybrid_diagnostic or HybridResumeDiagnostic()
        if not self._enable_bullet_rewrite:
            return resume.model_copy(
                update={
                    "hybrid_diagnostic": diagnostic.model_copy(
                        update={
                            "writing_status": HybridPlanningStatus.DETERMINISTIC_ONLY,
                            "writer_execution_status": (WriterExecutionStatus.REWRITING_DISABLED),
                            "writing_reason": "Rewriting is disabled by configuration.",
                            "rewrite_enabled": False,
                            "provider_call_count": self._last_planning_provider_calls,
                            "provider_cache_hits": self._last_planning_cache_hits,
                            "deterministic_fallback_used": True,
                            "layout_input": "reviewed_source_bullets",
                        }
                    )
                }
            )
        with self._telemetry.measure(GenerationStage.WRITER_SHORTLIST):
            if diagnostic.retrieval is not None:
                groups, shortlist_diagnostics = build_writer_shortlist(
                    resume,
                    profile,
                    diagnostic.retrieval,
                    policy=self._writing_policy,
                    line_estimator=self._line_estimator,
                )
            else:
                groups = self._shortlisted_groups(resume, profile)
                shortlist_diagnostics = []
        shortlisted_entry_ids = list(dict.fromkeys(group.entry_id for group in groups))
        shortlisted_evidence_ids = [
            evidence_id for group in groups for evidence_id in group.evidence_ids
        ]
        if self._language_model is None:
            return resume.model_copy(
                update={
                    "hybrid_diagnostic": diagnostic.model_copy(
                        update={
                            "writing_status": HybridPlanningStatus.DETERMINISTIC_ONLY,
                            "writer_execution_status": (WriterExecutionStatus.PROVIDER_UNAVAILABLE),
                            "writing_reason": (
                                self._provider_unavailable_reason
                                or "Rewriting is enabled, but the configured provider/model "
                                "is unavailable; reviewed source bullets were retained."
                            ),
                            "rewrite_enabled": True,
                            "provider_call_count": self._last_planning_provider_calls,
                            "provider_cache_hits": self._last_planning_cache_hits,
                            "deterministic_fallback_used": True,
                            "layout_input": "reviewed_source_bullets",
                            "writer_shortlist": shortlist_diagnostics,
                            "shortlisted_entry_ids": shortlisted_entry_ids,
                            "shortlisted_evidence_ids": shortlisted_evidence_ids,
                        }
                    )
                }
            )
        if not groups:
            return resume.model_copy(
                update={
                    "hybrid_diagnostic": diagnostic.model_copy(
                        update={
                            "rewrite_enabled": True,
                            "writing_status": HybridPlanningStatus.ADVISORY_REJECTED,
                            "writer_execution_status": (WriterExecutionStatus.SOURCE_FALLBACK_USED),
                            "writing_reason": "No reviewed evidence was eligible for writing.",
                            "provider_call_count": self._last_planning_provider_calls,
                            "provider_cache_hits": self._last_planning_cache_hits,
                            "deterministic_fallback_used": True,
                            "writer_shortlist": shortlist_diagnostics,
                            "shortlisted_entry_ids": shortlisted_entry_ids,
                            "shortlisted_evidence_ids": shortlisted_evidence_ids,
                        }
                    )
                }
            )
        request = BulletRewriteRequest(
            profile_fingerprint=(
                diagnostic.retrieval.profile_fingerprint
                if diagnostic.retrieval is not None
                else sha256(profile.model_dump_json().encode()).hexdigest()
            ),
            posting_fingerprint=(
                diagnostic.retrieval.posting_fingerprint
                if diagnostic.retrieval is not None
                else sha256(posting.model_dump_json().encode()).hexdigest()
            ),
            primary_focus=posting.title,
            target_terms=sorted(
                {
                    token
                    for requirement in _authoritative_posting_requirements(posting)
                    for token in requirement.casefold().split()
                }
                | set(posting.title.casefold().split())
            )[:80],
            target_requirements=(
                [
                    item.text
                    for item in diagnostic.retrieval.posting_requirements
                    if item.authority is not RequirementAuthority.INCIDENTAL
                ][:20]
                if diagnostic.retrieval is not None
                else _authoritative_posting_requirements(posting)[:20]
            ),
            groups=groups,
            max_bullets_per_entry=max(
                1,
                min(
                    constraints.max_bullets_per_entry,
                    self._writing_policy.maximum_shortlisted_evidence_per_entry,
                ),
            ),
            max_total_lines=max(
                constraints.max_total_lines,
                sum(
                    max(
                        group.max_rendered_lines,
                        max(
                            1,
                            (len(" ".join(group.source_texts)) + 89) // 90,
                        ),
                    )
                    for group in groups
                ),
            ),
            writing_policy_version=self._writing_policy.version,
            relevant_feature_flags={
                "bullet_rewrite": True,
                "writer_aware_portfolio": True,
                "claim_level_validation": True,
            },
            writing_instructions=list(self._writing_policy.instructions),
            prohibited_phrases=list(self._writing_policy.prohibited_phrases),
            discouraged_phrases=list(self._writing_policy.discouraged_phrases),
        )
        cache_key = self._variant_cache_key(request)
        with self._telemetry.measure(GenerationStage.WRITER_CACHE_LOOKUP):
            cached = self._resume_rewrite_cache.get(cache_key)
        generation_key = f"hybrid-write:{request.profile_fingerprint}:{request.posting_fingerprint}"
        provider_calls = 0
        cache_hits = 0
        rejected: list[BulletVariantRecord] = []
        rewrite_diagnostics: list[WriterRewriteDiagnostic] = []
        retry_reason: str | None = None
        if cached is None:
            self._generation_call_counts[generation_key] = 0
            self._last_validation_failures = []
            self._last_retry_failure_kind = None
            self._last_writer_pipeline_issue = None
            result = self._execute_writer_batch(
                generation_key,
                self._language_model.rewrite_bullets,
                request,
            )
            provider_calls = self._generation_call_counts.pop(generation_key, 0)
            retry_reason = (
                "The primary Gemini response was malformed, so the single "
                "permitted typed-output repair request was used."
                if provider_calls > 1
                else None
            )
            if result is None:
                issue = self._last_writer_pipeline_issue or WriterPipelineIssue(
                    code=WriterPipelineFailureCode.PROVIDER_TRANSPORT_OR_SDK_ERROR,
                    stage=WriterPipelineStage.PROVIDER_REQUEST,
                    provider_error_kind=self._last_retry_failure_kind,
                )
                execution_status = self._execution_status_for_issue(issue)
                return resume.model_copy(
                    update={
                        "hybrid_diagnostic": diagnostic.model_copy(
                            update={
                                "rewrite_enabled": True,
                                "writing_status": HybridPlanningStatus.ADVISORY_REJECTED,
                                "writer_execution_status": execution_status,
                                "writing_reason": self._writing_reason_for_issue(issue),
                                "writer_pipeline_issue": issue,
                                "provider_request_shape": issue.request_shape,
                                "provider_call_count": (
                                    self._last_planning_provider_calls + provider_calls
                                ),
                                "provider_retry_reason": (
                                    "The primary Gemini response was malformed; the "
                                    "single permitted typed-output repair also failed."
                                    if provider_calls > 1
                                    else None
                                ),
                                "provider_cache_hits": self._last_planning_cache_hits,
                                "deterministic_fallback_used": True,
                                "layout_input": "reviewed_source_bullets",
                                "validation_failures": list(self._last_validation_failures),
                                "writer_shortlist": shortlist_diagnostics,
                                "shortlisted_entry_ids": shortlisted_entry_ids,
                                "shortlisted_evidence_ids": shortlisted_evidence_ids,
                            }
                        )
                    }
                )
            cache_hits = int(result.metadata.cache_hit)
            provider_finish_reason = result.metadata.finish_reason
            provider_request_shape = result.metadata.request_shape
            with self._telemetry.measure(GenerationStage.CLAIM_VALIDATION):
                self._telemetry.increment("claim_validations")
                variants, rejected, rewrite_diagnostics = self._variant_records(
                    result.output.bullets,
                    groups,
                    result.mapping_outcomes,
                    provider=result.metadata.provider,
                    model=result.metadata.model,
                    posting=posting,
                    entry_kinds={
                        entry.id: entry.kind.value
                        for entry in [*profile.experiences, *profile.projects]
                    },
                )
            self._resume_rewrite_cache[cache_key] = (
                variants,
                rejected,
                rewrite_diagnostics,
                retry_reason,
                provider_finish_reason,
                provider_request_shape,
            )
        else:
            (
                cached_variants,
                cached_rejected,
                cached_rewrite_diagnostics,
                retry_reason,
                provider_finish_reason,
                provider_request_shape,
            ) = cached
            variants = [item.model_copy(deep=True) for item in cached_variants]
            rejected = [item.model_copy(deep=True) for item in cached_rejected]
            rewrite_diagnostics = [
                item.model_copy(deep=True) for item in cached_rewrite_diagnostics
            ]
            cache_hits = 1
        rewritten = self._apply_variants(
            resume,
            variants,
            approved_claim_ids,
        )
        selected_ids = {
            bullet.writing_variant.variant_id
            for bullet in _resume_bullets(rewritten)
            if bullet.writing_variant is not None
        }
        selected_variants = [
            item.model_copy(
                update={
                    "selected": item.variant_id in selected_ids,
                    "validation_status": (
                        BulletValidationStatus.VALIDATED
                        if item.variant_id in approved_claim_ids
                        else item.validation_status
                    ),
                    "selection_reason": (
                        "Explicitly approved by the user for this rebuilt artifact."
                        if item.variant_id in approved_claim_ids
                        else item.selection_reason
                    ),
                }
            )
            for item in variants
        ]
        selected_count = len(selected_ids)
        mapping_failure_count = sum(
            item.provider_contract_mapping_result
            is not ProviderRewriteMappingStatus.MAPPED
            for item in rewrite_diagnostics
        )
        if not variants and not rejected and not mapping_failure_count:
            execution_status = WriterExecutionStatus.NO_MATERIAL_IMPROVEMENT
        elif cache_hits:
            execution_status = WriterExecutionStatus.CACHE_HIT
        elif selected_count:
            execution_status = (
                WriterExecutionStatus.WRITER_PARTIALLY_SUCCEEDED
                if rejected
                or any(
                    item.validation_status is BulletValidationStatus.REVIEW_REQUIRED
                    for item in selected_variants
                )
                or any(
                    item.provider_contract_mapping_result
                    is not ProviderRewriteMappingStatus.MAPPED
                    for item in rewrite_diagnostics
                )
                else WriterExecutionStatus.WRITER_SUCCEEDED
            )
        elif (rejected or mapping_failure_count) and not variants:
            execution_status = WriterExecutionStatus.ALL_GENERATED_VARIANTS_REJECTED
        else:
            execution_status = WriterExecutionStatus.SOURCE_VARIANTS_SCORED_BETTER
        pipeline_issue = (
            WriterPipelineIssue(
                code=WriterPipelineFailureCode.NO_MATERIAL_IMPROVEMENT,
                stage=WriterPipelineStage.VARIANT_SELECTION,
                finish_reason=provider_finish_reason,
            )
            if execution_status is WriterExecutionStatus.NO_MATERIAL_IMPROVEMENT
            else WriterPipelineIssue(
                code=WriterPipelineFailureCode.CLAIM_GROUNDING_REJECTION,
                stage=WriterPipelineStage.CLAIM_VALIDATION,
                finish_reason=provider_finish_reason,
            )
            if execution_status is WriterExecutionStatus.ALL_GENERATED_VARIANTS_REJECTED
            else WriterPipelineIssue(
                code=WriterPipelineFailureCode.SOURCE_VARIANT_SELECTED,
                stage=WriterPipelineStage.VARIANT_SELECTION,
                finish_reason=provider_finish_reason,
            )
            if execution_status is WriterExecutionStatus.SOURCE_VARIANTS_SCORED_BETTER
            else None
        )
        return rewritten.model_copy(
            update={
                "hybrid_diagnostic": diagnostic.model_copy(
                    update={
                        "writing_status": HybridPlanningStatus.ADVISORY_APPLIED,
                        "writer_execution_status": execution_status,
                        "writing_reason": (
                            "A cached validated writer batch was reused."
                            if execution_status is WriterExecutionStatus.CACHE_HIT
                            else "Gemini returned no variants because it found no "
                            "materially stronger supported wording for the bounded shortlist."
                            if execution_status is WriterExecutionStatus.NO_MATERIAL_IMPROVEMENT
                            else "Typed provider output parsed successfully, but every "
                            "generated variant was rejected during claim grounding or "
                            "writing-policy validation."
                            if execution_status
                            is WriterExecutionStatus.ALL_GENERATED_VARIANTS_REJECTED
                            else "A bounded validated writer batch supplied materially "
                            "improved reusable variants; deterministic layout search "
                            "retained final authority."
                            if selected_count
                            else "Generated variants were valid, but source wording scored "
                            "better under material-improvement and readability checks."
                        ),
                        "source_writer_path": "bounded_evidence_rewrite_batch",
                        "layout_input": "validated_variants_with_source_fallbacks",
                        "writer_shortlist": shortlist_diagnostics,
                        "shortlisted_entry_ids": shortlisted_entry_ids,
                        "shortlisted_evidence_ids": shortlisted_evidence_ids,
                        "bullet_variants": selected_variants,
                        "rejected_variants": rejected,
                        "rewrite_diagnostics": rewrite_diagnostics,
                        "validation_failures": list(self._last_validation_failures),
                        "provider_call_count": (
                            self._last_planning_provider_calls + provider_calls
                        ),
                        "provider_retry_reason": retry_reason,
                        "provider_finish_reason": provider_finish_reason,
                        "provider_request_shape": provider_request_shape,
                        "writer_pipeline_issue": pipeline_issue,
                        "provider_cache_hits": (self._last_planning_cache_hits + cache_hits),
                        "rewrite_enabled": True,
                        "deterministic_fallback_used": not bool(selected_ids),
                        "rejected_variant_count": sum(
                            item.validation_status is BulletValidationStatus.REJECTED
                            for item in rewrite_diagnostics
                        ),
                        "review_required_variant_count": sum(
                            item.validation_status is BulletValidationStatus.REVIEW_REQUIRED
                            for item in rewrite_diagnostics
                        ),
                    }
                )
            }
        )

    def extract_profile_draft(
        self, profile_id: str, source_format: str, extracted_text: str
    ) -> ProfileExtractionResult:
        if self._language_model is None:
            raise LanguageModelError(
                LanguageModelErrorKind.CONFIGURATION,
                "Profile extraction requires a configured language model.",
            )
        request = ProfileExtractionRequest(
            profile_id=profile_id,
            source_format=source_format,
            extracted_text=extracted_text,
        )
        result = self._language_model.extract_profile(request)
        normalized_profile = normalize_extracted_profile(result.output.profile, extracted_text)
        fidelity_flags = [
            *result.output.fidelity_flags,
            *audit_extracted_profile(normalized_profile, extracted_text),
        ]
        return result.model_copy(
            update={
                "output": result.output.model_copy(
                    update={"profile": normalized_profile, "fidelity_flags": fidelity_flags}
                )
            }
        )

    @staticmethod
    def _skill_fallback(plan: TailoringPlan, reason: str) -> TailoringPlan:
        report = plan.report.model_copy(deep=True)
        report.decisions.append(
            Decision(
                action="gemini_skill_fallback",
                entity_id="technical-skills",
                reason=reason,
                constraint="deterministic categorized-skill selection preserved",
            )
        )
        return plan.model_copy(update={"report": report})

    def rewrite_plan(
        self,
        plan: TailoringPlan,
        profile: MasterProfile,
        approved_claim_ids: set[str] | None = None,
    ) -> TailoringPlan:
        if self._language_model is None or not self._enable_bullet_rewrite or plan.strategy is None:
            return plan
        rewrite_cache_key = sha256(plan.model_dump_json().encode()).hexdigest()
        cached = self._rewrite_cache.get(rewrite_cache_key)
        if cached is not None:
            return cached
        groups = self._approved_groups(plan, profile)
        if not groups:
            return plan
        request = BulletRewriteRequest(
            primary_focus=plan.strategy.primary_focus,
            target_terms=sorted(
                {
                    term
                    for signal in plan.report.role.signals
                    for term in [signal.label, *signal.keywords]
                }
            ),
            groups=groups,
            max_bullets_per_entry=plan.constraints.max_bullets_per_entry,
            max_total_lines=plan.constraints.max_total_lines,
        )
        generation_key = self._generation_key(plan)
        result = self._retry(
            generation_key,
            self._language_model.rewrite_bullets,
            request,
            lambda output: validate_rewrites(
                output,
                groups,
                max_bullets_per_entry=request.max_bullets_per_entry,
                max_total_lines=request.max_total_lines,
            ),
        )
        self._generation_call_counts.pop(generation_key, None)
        if result is None:
            return plan
        generated = [self._rewrite_candidate(bullet, groups) for bullet in result.output.bullets]
        generated_by_entry: defaultdict[str, list[ClaimCandidate]] = defaultdict(list)
        covered_by_entry: defaultdict[str, set[str]] = defaultdict(set)
        for candidate in generated:
            generated_by_entry[candidate.entity_id].append(candidate)
            covered_by_entry[candidate.entity_id].update(candidate.evidence_ids)

        candidates: list[ClaimCandidate] = []
        inserted_entries: set[str] = set()
        for candidate in plan.claim_candidates:
            covered = covered_by_entry[candidate.entity_id]
            if covered.intersection(candidate.evidence_ids) and set(
                candidate.evidence_ids
            ).issubset(covered):
                if candidate.entity_id not in inserted_entries:
                    candidates.extend(generated_by_entry[candidate.entity_id])
                    inserted_entries.add(candidate.entity_id)
                continue
            candidates.append(candidate)
        for entry_id, entry_candidates in generated_by_entry.items():
            if entry_id not in inserted_entries:
                candidates.extend(entry_candidates)
        report = plan.report.model_copy(deep=True)
        report.decisions.append(
            Decision(
                action="gemini_bullet_rewrite_applied",
                entity_id="document",
                reason=(
                    "Evidence-linked bullets were semantically tailored within "
                    "deterministic budgets."
                ),
                evidence_ids=[
                    evidence_id for candidate in generated for evidence_id in candidate.evidence_ids
                ],
                constraint=(
                    "validated evidence linkage, protected facts, and one-page content budget"
                ),
            )
        )
        rewritten_plan = plan.model_copy(update={"claim_candidates": candidates, "report": report})
        self._rewrite_cache[rewrite_cache_key] = rewritten_plan
        return rewritten_plan

    def _shortlisted_groups(
        self,
        resume: StructuredResume,
        profile: MasterProfile,
    ) -> list[ApprovedEvidenceGroup]:
        evidence_by_id = {item.id: item for item in profile.evidence if item.confirmed}
        selected_ids = [
            evidence_id
            for bullet in _resume_bullets(resume)
            for evidence_id in bullet.evidence_ids
            if evidence_id in evidence_by_id
        ]
        retrieved_ids = (
            [item.evidence_id for item in resume.hybrid_diagnostic.retrieval.admitted]
            if resume.hybrid_diagnostic is not None
            and resume.hybrid_diagnostic.retrieval is not None
            else []
        )
        ordered_ids = list(dict.fromkeys([*selected_ids, *retrieved_ids]))
        groups: list[ApprovedEvidenceGroup] = []
        for evidence_id in ordered_ids[: self._writing_policy.maximum_shortlisted_evidence]:
            evidence = evidence_by_id[evidence_id]
            line_fit = self._line_estimator.estimate(evidence.source_text)
            groups.append(
                ApprovedEvidenceGroup(
                    entry_id=evidence.entity_id,
                    evidence_ids=[evidence.id],
                    source_texts=[evidence.source_text],
                    technologies=evidence.technologies,
                    capabilities=evidence.capabilities,
                    metrics=evidence.outcomes,
                    max_rendered_lines=max(1, min(3, line_fit.expected_line_count)),
                )
            )
        return groups

    def _variant_records(
        self,
        rewrites: list[BulletRewrite],
        groups: list[ApprovedEvidenceGroup],
        mapping_outcomes: list[ProviderRewriteMappingOutcome] | None = None,
        *,
        provider: str,
        model: str,
        posting: JobPosting,
        entry_kinds: dict[str, str] | None = None,
    ) -> tuple[
        list[BulletVariantRecord],
        list[BulletVariantRecord],
        list[WriterRewriteDiagnostic],
    ]:
        group_by_evidence = {
            evidence_id: group for group in groups for evidence_id in group.evidence_ids
        }
        accepted: list[BulletVariantRecord] = []
        rejected: list[BulletVariantRecord] = []
        resolved_mapping_outcomes = mapping_outcomes or []
        rewrite_diagnostics = _mapping_rewrite_diagnostics(
            resolved_mapping_outcomes,
            group_by_evidence,
            entry_kinds or {},
        )
        self._last_validation_failures.extend(
            detail
            for item in rewrite_diagnostics
            for detail in item.validator_rejection_details
        )
        mapped_by_bullet_index = {
            outcome.mapped_bullet_index: outcome
            for outcome in resolved_mapping_outcomes
            if outcome.mapping_status is ProviderRewriteMappingStatus.MAPPED
            and outcome.mapped_bullet_index is not None
        }
        for rewrite_index, rewrite in enumerate(rewrites):
            mapping = mapped_by_bullet_index.get(rewrite_index)
            source_groups = [
                group_by_evidence[evidence_id]
                for evidence_id in rewrite.source_evidence_ids
                if evidence_id in group_by_evidence
            ]
            source_texts = [
                source_text
                for evidence_id in rewrite.source_evidence_ids
                for source_text in (
                    group_by_evidence[evidence_id].source_texts
                    if evidence_id in group_by_evidence
                    else []
                )
            ]
            retained_source_texts = source_texts or [
                "Provider output did not retain a known reviewed evidence reference."
            ]
            variants: tuple[
                tuple[str | None, BulletLengthClass, str],
                ...,
            ] = (
                (
                    rewrite.final_bullet_text,
                    rewrite.intended_length_class,
                    "standard",
                ),
                (
                    rewrite.concise_alternative,
                    BulletLengthClass.CONCISE_ONE_LINE,
                    "concise",
                ),
            )
            seen_variant_texts: set[str] = set()
            for text, length_class, suffix in variants[
                : self._writing_policy.maximum_variants_per_evidence_group
            ]:
                if text is None:
                    continue
                normalized_variant = " ".join(text.casefold().split())
                if normalized_variant in seen_variant_texts:
                    continue
                seen_variant_texts.add(normalized_variant)
                line_fit = self._line_estimator.estimate(text)
                target_requirements = (
                    rewrite.target_requirements_addressed
                    or _matched_target_requirements(text, posting)
                )
                improvement_reasons = _material_improvement_reasons(
                    text,
                    retained_source_texts,
                    posting,
                    line_fit,
                    self._line_estimator,
                )
                claims_for_validation = (
                    rewrite.claims
                    if rewrite.claims and suffix == "standard"
                    else [
                        BulletRewriteClaim(
                            text=text,
                            supporting_evidence_ids=rewrite.source_evidence_ids,
                        )
                    ]
                )
                validation_failures: list[str] = []
                try:
                    validate_rewrites(
                        BulletRewriteOutput(
                            bullets=[
                                rewrite.model_copy(
                                    update={
                                        "final_bullet_text": text,
                                        "concise_alternative": None,
                                        "claims": claims_for_validation,
                                    }
                                )
                            ]
                        ),
                        groups,
                        max_bullets_per_entry=1,
                        max_total_lines=max(
                            3,
                            (len(text) + 89) // 90,
                        ),
                    )
                except GroundingValidationError as error:
                    validation_failures.extend(dict.fromkeys(error.failures))
                reasons = [
                    *validation_failures,
                    *_writing_style_failures(
                        text,
                        retained_source_texts,
                        posting.description,
                        self._writing_policy,
                    ),
                ]
                structured_facts = [
                    value
                    for group in source_groups
                    for value in [
                        *group.technologies,
                        *group.capabilities,
                        *group.metrics,
                    ]
                ]
                introduced_semantic_features = _introduced_unverified_semantic_features(
                    text,
                    source_texts,
                    structured_facts,
                    self._writing_policy,
                )
                semantic_review_required = bool(introduced_semantic_features)
                review_required = (
                    rewrite.support == ClaimConfidence.STRONGLY_IMPLIED
                    or line_fit.three_line_risk
                    or semantic_review_required
                )
                validation_reasons = reasons or [
                    (
                        "New semantic terminology requires bounded entailment review "
                        f"before automatic rendering: {introduced_semantic_features}."
                        if semantic_review_required
                        else "Grounded output was valid but did not materially improve "
                        "structure, emphasis, clarity, relevance, or readability."
                        if not improvement_reasons
                        else "Grounded output passed deterministic fact, ownership, "
                        "provenance, and style checks."
                    )
                ]
                status = (
                    BulletValidationStatus.REJECTED
                    if reasons
                    else BulletValidationStatus.REVIEW_REQUIRED
                    if review_required
                    else BulletValidationStatus.VALIDATED
                )
                claims = [
                    GroundedClaim(
                        text=claim.text,
                        supporting_evidence_ids=claim.supporting_evidence_ids,
                        validation_status=(
                            ClaimValidationStatus.REVIEW_REQUIRED
                            if rewrite.support == ClaimConfidence.STRONGLY_IMPLIED
                            else ClaimValidationStatus.SUPPORTED
                        ),
                        reason=(
                            "Claim retained provider-supplied same-entry evidence "
                            "references and passed deterministic checks."
                        ),
                    )
                    for claim in claims_for_validation
                ]
                digest = sha256(
                    (
                        f"{rewrite.entry_id}\0{text}\0"
                        f"{'|'.join(rewrite.source_evidence_ids)}\0{suffix}"
                    ).encode()
                ).hexdigest()[:16]
                record = BulletVariantRecord(
                    variant_id=f"written-bullet:{digest}",
                    entry_id=rewrite.entry_id,
                    source_evidence_ids=rewrite.source_evidence_ids,
                    original_reviewed_text=retained_source_texts,
                    rewritten_text=text,
                    factual_claims=claims,
                    target_job_requirements=target_requirements,
                    relationship_tier=_strongest_relationship(
                        [group.relationship_tier for group in source_groups]
                    ),
                    intended_length_class=length_class,
                    writing_policy_version=self._writing_policy.version,
                    provider=provider,
                    model=model,
                    validation_status=status,
                    validation_reasons=validation_reasons,
                    line_fit=line_fit,
                    material_improvement=bool(improvement_reasons),
                    improvement_reasons=improvement_reasons,
                    future_user_review=review_required,
                )
                (rejected if status is BulletValidationStatus.REJECTED else accepted).append(record)
                comparison = compare_rewrite_grounding(
                    text,
                    retained_source_texts,
                    structured_facts,
                )
                rejection_codes = list(
                    dict.fromkeys(grounding_failure_code(reason) for reason in reasons)
                )
                if semantic_review_required:
                    rejection_codes.append(GroundingFailureCode.SEMANTIC_EQUIVALENCE_REVIEW)
                if not improvement_reasons:
                    rejection_codes.append(GroundingFailureCode.NO_MATERIAL_IMPROVEMENT)
                rewrite_diagnostics.append(
                    WriterRewriteDiagnostic(
                        rewrite_index=(
                            mapping.rewrite_index if mapping is not None else rewrite_index
                        ),
                        evidence_ids=rewrite.source_evidence_ids,
                        source_evidence_text=retained_source_texts,
                        rewritten_text=text,
                        reconstructed_claim=(
                            claims_for_validation[0].text if claims_for_validation else text
                        ),
                        supporting_evidence_ids=list(
                            dict.fromkeys(
                                evidence_id
                                for claim in claims_for_validation
                                for evidence_id in claim.supporting_evidence_ids
                            )
                        ),
                        entry_id=rewrite.entry_id,
                        entry_type=(entry_kinds or {}).get(rewrite.entry_id),
                        provider_contract_mapping_result=(
                            mapping.mapping_status
                            if mapping is not None
                            else ProviderRewriteMappingStatus.MAPPED
                        ),
                        validator_rejection_codes=list(dict.fromkeys(rejection_codes)),
                        validator_rejection_details=validation_reasons,
                        normalized_unsupported_terms=sorted(
                            set(comparison.normalized_unsupported_terms)
                            | set(introduced_semantic_features)
                        ),
                        ownership_comparison=comparison.ownership_comparison,
                        metric_comparison=comparison.metric_comparison,
                        causal_outcome_comparison=comparison.causal_outcome_comparison,
                        singular_plural_scope_comparison=(
                            comparison.singular_plural_scope_comparison
                        ),
                        validation_status=status,
                        batch_effect="pending_aggregate_result",
                    )
                )
                if reasons:
                    self._last_validation_failures.extend(reasons)
        accepted.sort(key=_variant_sort_key)
        rejected.sort(key=lambda item: item.variant_id)
        usable_count = sum(
            item.validation_status is BulletValidationStatus.VALIDATED
            and item.material_improvement
            for item in accepted
        )
        has_individual_failure = any(
            item.validation_status is not BulletValidationStatus.VALIDATED
            or item.provider_contract_mapping_result
            is not ProviderRewriteMappingStatus.MAPPED
            for item in rewrite_diagnostics
        )
        rewrite_diagnostics = [
            item.model_copy(
                update={
                    "batch_effect": (
                        "continued_to_variant_competition_with_rejected_siblings"
                        if item.validation_status is BulletValidationStatus.VALIDATED
                        and usable_count
                        and has_individual_failure
                        else "continued_to_variant_competition"
                        if item.validation_status is BulletValidationStatus.VALIDATED
                        and usable_count
                        else "rewrite_rejected_or_review_gated; valid_sibling_retained"
                        if usable_count
                        else "batch_source_fallback_no_usable_validated_rewrites"
                    )
                }
            )
            for item in rewrite_diagnostics
        ]
        return accepted, rejected, rewrite_diagnostics

    @staticmethod
    def _apply_variants(
        resume: StructuredResume,
        variants: list[BulletVariantRecord],
        approved_claim_ids: set[str],
    ) -> StructuredResume:
        usable = [
            item
            for item in variants
            if item.validation_status is not BulletValidationStatus.REJECTED
            and item.material_improvement
        ]
        by_entry: defaultdict[str, list[BulletVariantRecord]] = defaultdict(list)
        for item in usable:
            by_entry[item.entry_id].append(item)
        pending = list(resume.review_pending_bullets)

        def rewrite_section(
            source: dict[str, list[StructuredBullet]],
        ) -> dict[str, list[StructuredBullet]]:
            rewritten: dict[str, list[StructuredBullet]] = {}
            for entry_id, bullets in source.items():
                source_order = {
                    evidence_id: index
                    for index, bullet in enumerate(bullets)
                    for evidence_id in bullet.evidence_ids
                }
                selected_variants: list[BulletVariantRecord] = []
                covered: set[str] = set()
                entry_variants = sorted(
                    by_entry.get(entry_id, []),
                    key=lambda item: (
                        min(
                            (
                                source_order.get(evidence_id, 10_000)
                                for evidence_id in item.source_evidence_ids
                            ),
                            default=10_000,
                        ),
                        *_variant_sort_key(item),
                    ),
                )
                for item in entry_variants:
                    source_ids = set(item.source_evidence_ids)
                    if not source_ids.issubset(source_order) or source_ids & covered:
                        continue
                    if (
                        item.validation_status is BulletValidationStatus.REVIEW_REQUIRED
                        and item.variant_id not in approved_claim_ids
                    ):
                        pending.append(
                            StructuredBullet(
                                id=item.variant_id,
                                text=item.rewritten_text,
                                evidence_ids=item.source_evidence_ids,
                                support=ClaimSupport.STRONG_INFERENCE_PENDING_REVIEW,
                                writing_variant=item,
                            )
                        )
                        continue
                    selected_variants.append(item)
                    covered.update(source_ids)
                replacements = {
                    min(source_order[evidence_id] for evidence_id in item.source_evidence_ids): item
                    for item in selected_variants
                }
                output: list[StructuredBullet] = []
                for index, bullet in enumerate(bullets):
                    replacement = replacements.get(index)
                    if replacement is not None:
                        output.append(
                            StructuredBullet(
                                id=replacement.variant_id,
                                text=replacement.rewritten_text,
                                evidence_ids=replacement.source_evidence_ids,
                                support=ClaimSupport.DIRECT,
                                writing_variant=replacement,
                            )
                        )
                    if not set(bullet.evidence_ids) & covered:
                        output.append(bullet)
                rewritten[entry_id] = output
            return rewritten

        return resume.model_copy(
            update={
                "experience_bullets": rewrite_section(resume.experience_bullets),
                "project_bullets": rewrite_section(resume.project_bullets),
                "review_pending_bullets": list({item.id: item for item in pending}.values()),
                "review_required_claim_ids": list(
                    dict.fromkeys(
                        [
                            *resume.review_required_claim_ids,
                            *[item.id for item in pending if item.id not in approved_claim_ids],
                        ]
                    )
                ),
            }
        )

    def _variant_cache_key(self, request: BulletRewriteRequest) -> str:
        identity = {
            "profile_fingerprint": request.profile_fingerprint,
            "posting_fingerprint": request.posting_fingerprint,
            "evidence": [
                {
                    "entry_id": group.entry_id,
                    "evidence_ids": group.evidence_ids,
                    "source_texts": group.source_texts,
                    "technologies": group.technologies,
                    "capabilities": group.capabilities,
                    "metrics": group.metrics,
                }
                for group in request.groups
            ],
            "target_terms": request.target_terms,
            "target_requirements": request.target_requirements,
            "writing_policy_version": request.writing_policy_version,
            "contract_version": request.contract_version,
            "prompt_version": request.prompt_version,
            "relevant_feature_flags": request.relevant_feature_flags,
            "writing_instructions": request.writing_instructions,
            "prohibited_phrases": request.prohibited_phrases,
            "discouraged_phrases": request.discouraged_phrases,
            "provider": self._provider_name,
            "model": self._model_name,
        }
        return sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def _rewrite_candidate(
        self,
        bullet: BulletRewrite,
        groups: list[ApprovedEvidenceGroup],
    ) -> ClaimCandidate:
        group_by_evidence = {
            evidence_id: group for group in groups for evidence_id in group.evidence_ids
        }
        max_lines = min(
            group_by_evidence[evidence_id].max_rendered_lines
            for evidence_id in bullet.source_evidence_ids
        )
        digest = sha256(
            f"{bullet.entry_id}\0{bullet.final_bullet_text}\0{'|'.join(bullet.source_evidence_ids)}".encode()
        ).hexdigest()[:12]
        support = (
            ClaimSupport.DIRECT
            if bullet.support == ClaimConfidence.EXPLICITLY_SUPPORTED
            else ClaimSupport.STRONG_INFERENCE_PENDING_REVIEW
        )
        original_text = [
            source
            for evidence_id in bullet.source_evidence_ids
            for source in group_by_evidence[evidence_id].source_texts
        ]
        line_fit = self._line_estimator.estimate(bullet.final_bullet_text)
        variant = BulletVariantRecord(
            variant_id=f"written-bullet:{digest}",
            entry_id=bullet.entry_id,
            source_evidence_ids=bullet.source_evidence_ids,
            original_reviewed_text=original_text,
            rewritten_text=bullet.final_bullet_text,
            factual_claims=[
                GroundedClaim(
                    text=claim.text,
                    supporting_evidence_ids=claim.supporting_evidence_ids,
                    validation_status=(
                        ClaimValidationStatus.SUPPORTED
                        if support is ClaimSupport.DIRECT
                        else ClaimValidationStatus.REVIEW_REQUIRED
                    ),
                    reason="Validated same-entry evidence provenance.",
                )
                for claim in bullet.claims
            ]
            or [
                GroundedClaim(
                    text=bullet.final_bullet_text,
                    supporting_evidence_ids=bullet.source_evidence_ids,
                    validation_status=(
                        ClaimValidationStatus.SUPPORTED
                        if support is ClaimSupport.DIRECT
                        else ClaimValidationStatus.REVIEW_REQUIRED
                    ),
                    reason="Complete-bullet fallback claim retained evidence provenance.",
                )
            ],
            target_job_requirements=bullet.target_requirements_addressed,
            intended_length_class=bullet.intended_length_class,
            writing_policy_version=self._writing_policy.version,
            provider=self._provider_name,
            model=self._model_name,
            validation_status=(
                BulletValidationStatus.VALIDATED
                if support is ClaimSupport.DIRECT
                else BulletValidationStatus.REVIEW_REQUIRED
            ),
            validation_reasons=["Validated by the evidence-bound rewrite path."],
            line_fit=line_fit,
            future_user_review=support is not ClaimSupport.DIRECT,
        )
        return ClaimCandidate(
            id=f"gemini-bullet:{digest}",
            entity_id=bullet.entry_id,
            text=bullet.final_bullet_text,
            evidence_ids=bullet.source_evidence_ids,
            support=support,
            estimated_lines=max(1, (len(bullet.final_bullet_text) + 89) // 90),
            composition=(
                ClaimComposition.COMBINED
                if len(bullet.source_evidence_ids) > 1
                else ClaimComposition.SINGLE
            ),
            required_terms=[*bullet.preserved_technologies, *bullet.preserved_metrics],
            max_rendered_lines=max_lines,
            writing_variant=variant,
        )

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
        validator: Callable[[Any], None] | None,
    ) -> ResultType | None:
        current_request = request
        for attempt_index in range(self._retry_count + 1):
            if self._generation_call_counts.get(generation_key, 0) >= self._max_calls:
                return None
            self._telemetry.increment("provider_calls")
            if attempt_index:
                self._telemetry.increment("provider_retries")
            self._generation_call_counts[generation_key] = (
                self._generation_call_counts.get(generation_key, 0) + 1
            )
            try:
                with self._telemetry.measure(GenerationStage.PROVIDER_REQUEST):
                    result = operation(current_request)
                if validator is not None:
                    with self._telemetry.measure(GenerationStage.CLAIM_VALIDATION):
                        self._telemetry.increment("claim_validations")
                        validator(cast(Any, result).output)
                if result.metadata.cache_hit:
                    self._generation_cache_hits[generation_key] = (
                        self._generation_cache_hits.get(generation_key, 0) + 1
                    )
                return result
            except GroundingValidationError as error:
                self._last_validation_failures = list(error.failures)
                self._last_retry_failure_kind = "grounding_validation"
                current_request = current_request.model_copy(
                    update={"correction_notes": error.failures}
                )
            except LanguageModelError as error:
                self._last_retry_failure_kind = error.kind.value
                if not error.retryable:
                    return None
            except ValueError as error:
                self._last_retry_failure_kind = "malformed_output"
                current_request = current_request.model_copy(
                    update={"correction_notes": [str(error)]}
                )
        return None

    def _execute_writer_batch(
        self,
        generation_key: str,
        operation: Callable[[BulletRewriteRequest], BulletRewriteResult],
        request: BulletRewriteRequest,
    ) -> BulletRewriteResult | None:
        """Execute one writer request and one repair only for malformed typed output."""

        maximum_requests = min(
            self._max_calls,
            self._writing_policy.maximum_provider_batches
            + self._writing_policy.maximum_malformed_repairs,
        )
        current_request = request
        for attempt_index in range(maximum_requests):
            self._telemetry.increment("provider_calls")
            if attempt_index:
                self._telemetry.increment("provider_retries")
            self._generation_call_counts[generation_key] = (
                self._generation_call_counts.get(generation_key, 0) + 1
            )
            try:
                result = operation(current_request)
                self._last_writer_pipeline_issue = None
                return result
            except LanguageModelError as error:
                self._last_retry_failure_kind = error.kind.value
                self._last_writer_pipeline_issue = (
                    error.diagnostic or self._pipeline_issue_for_error(error)
                )
                repairable = error.kind is LanguageModelErrorKind.MALFORMED_RESPONSE
                if not repairable or attempt_index + 1 >= maximum_requests:
                    return None
                current_request = current_request.model_copy(
                    update={
                        "correction_notes": [
                            "The prior response was malformed. Return only valid JSON "
                            "matching the supplied typed schema."
                        ]
                    }
                )
            except ValueError as error:
                self._last_retry_failure_kind = "malformed_output"
                self._last_writer_pipeline_issue = WriterPipelineIssue(
                    code=WriterPipelineFailureCode.MALFORMED_JSON,
                    stage=WriterPipelineStage.JSON_PARSING,
                    provider_error_kind="malformed_output",
                    exception_type=type(error).__name__,
                )
                if attempt_index + 1 >= maximum_requests:
                    return None
                current_request = current_request.model_copy(
                    update={
                        "correction_notes": [
                            "The prior response was malformed. Return only valid JSON "
                            "matching the supplied typed schema."
                        ]
                    }
                )
        return None

    @staticmethod
    def _pipeline_issue_for_error(error: LanguageModelError) -> WriterPipelineIssue:
        if error.kind is LanguageModelErrorKind.TIMEOUT:
            code = WriterPipelineFailureCode.PROVIDER_TIMEOUT
            stage = WriterPipelineStage.PROVIDER_REQUEST
        elif error.kind is LanguageModelErrorKind.SAFETY_BLOCKED:
            code = WriterPipelineFailureCode.SAFETY_BLOCKED_RESPONSE
            stage = WriterPipelineStage.RESPONSE_EXTRACTION
        elif error.kind is LanguageModelErrorKind.EMPTY_RESPONSE:
            code = WriterPipelineFailureCode.EMPTY_PROVIDER_RESPONSE
            stage = WriterPipelineStage.RESPONSE_EXTRACTION
        elif error.kind in {
            LanguageModelErrorKind.RESPONSE_EXTRACTION,
            LanguageModelErrorKind.TRUNCATED_RESPONSE,
        }:
            code = WriterPipelineFailureCode.RESPONSE_EXTRACTION_FAILED
            stage = WriterPipelineStage.RESPONSE_EXTRACTION
        elif error.kind is LanguageModelErrorKind.MALFORMED_RESPONSE:
            code = WriterPipelineFailureCode.TYPED_SCHEMA_MISMATCH
            stage = WriterPipelineStage.TYPED_SCHEMA_VALIDATION
        else:
            code = WriterPipelineFailureCode.PROVIDER_TRANSPORT_OR_SDK_ERROR
            stage = WriterPipelineStage.PROVIDER_REQUEST
        return WriterPipelineIssue(
            code=code,
            stage=stage,
            provider_error_kind=error.kind.value,
            exception_type=type(error).__name__,
        )

    @staticmethod
    def _execution_status_for_issue(
        issue: WriterPipelineIssue,
    ) -> WriterExecutionStatus:
        if issue.code is WriterPipelineFailureCode.PROVIDER_TIMEOUT:
            return WriterExecutionStatus.PROVIDER_TIMEOUT
        if issue.code is WriterPipelineFailureCode.SAFETY_BLOCKED_RESPONSE:
            return WriterExecutionStatus.PROVIDER_SAFETY_BLOCKED
        if issue.code is WriterPipelineFailureCode.EMPTY_PROVIDER_RESPONSE:
            return WriterExecutionStatus.PROVIDER_EMPTY_RESPONSE
        if issue.code is WriterPipelineFailureCode.RESPONSE_EXTRACTION_FAILED:
            return WriterExecutionStatus.RESPONSE_EXTRACTION_FAILED
        if issue.code in {
            WriterPipelineFailureCode.MALFORMED_JSON,
            WriterPipelineFailureCode.TYPED_SCHEMA_MISMATCH,
        }:
            return WriterExecutionStatus.MALFORMED_WRITER_OUTPUT
        return WriterExecutionStatus.PROVIDER_REQUEST_FAILED

    @staticmethod
    def _writing_reason_for_issue(issue: WriterPipelineIssue) -> str:
        descriptions = {
            WriterPipelineFailureCode.PROVIDER_TRANSPORT_OR_SDK_ERROR: (
                "The Gemini transport or SDK request failed before a response was returned; "
                "response parsing and claim validation did not run."
            ),
            WriterPipelineFailureCode.INVALID_MODEL_OR_CONFIG: (
                "Gemini rejected a model or generation-config field before returning a "
                "response; parsing and claim validation did not run."
            ),
            WriterPipelineFailureCode.UNSUPPORTED_SCHEMA_KEYWORD: (
                "Gemini rejected an unsupported provider-facing JSON-Schema keyword; "
                "parsing and claim validation did not run."
            ),
            WriterPipelineFailureCode.SCHEMA_TOO_LARGE_OR_DEEP: (
                "Gemini rejected a provider-facing schema that exceeded a supported "
                "complexity boundary; parsing and claim validation did not run."
            ),
            WriterPipelineFailureCode.INCOMPATIBLE_SDK_API_VERSION: (
                "The installed google-genai SDK/API route is incompatible with the "
                "configured Gemini model; no provider response was available to parse."
            ),
            WriterPipelineFailureCode.UNKNOWN_INVALID_ARGUMENT: (
                "Gemini returned INVALID_ARGUMENT without a safe field violation; parsing "
                "and claim validation did not run."
            ),
            WriterPipelineFailureCode.PROVIDER_TIMEOUT: (
                "The Gemini request exceeded the 30-second interactive timeout; response "
                "parsing and claim validation did not run."
            ),
            WriterPipelineFailureCode.SAFETY_BLOCKED_RESPONSE: (
                "Gemini returned a safety-blocked response; no repair was attempted and "
                "claim validation did not run."
            ),
            WriterPipelineFailureCode.EMPTY_PROVIDER_RESPONSE: (
                "Gemini returned no candidate text; no malformed-output repair was "
                "attempted and claim validation did not run."
            ),
            WriterPipelineFailureCode.RESPONSE_EXTRACTION_FAILED: (
                "Gemini returned a response, but its candidate text could not be extracted; "
                "claim validation did not run."
            ),
            WriterPipelineFailureCode.MALFORMED_JSON: (
                "Gemini returned malformed JSON and the single permitted repair did not "
                "produce valid typed output."
            ),
            WriterPipelineFailureCode.TYPED_SCHEMA_MISMATCH: (
                "Gemini returned JSON that did not match the typed writer schema and the "
                "single permitted repair did not produce valid typed output."
            ),
        }
        return (
            descriptions.get(
                issue.code,
                "Gemini writing failed before a validated variant was available.",
            )
            + " Reviewed source bullets were retained."
        )

    @staticmethod
    def _generation_key(plan: TailoringPlan) -> str:
        return f"{plan.profile_id}:{plan.profile_version}:{plan.posting_id}"

    @staticmethod
    def _composition_request(
        plan: TailoringPlan, profile: MasterProfile
    ) -> CompositionRecommendationRequest:
        items = {item.id: item for item in profile.experiences + profile.projects}
        evidence = {item.id: item for item in profile.evidence}
        grouped: defaultdict[str, list[EligibleEvidence]] = defaultdict(list)
        for candidate in plan.claim_candidates:
            for evidence_id in candidate.evidence_ids:
                source = evidence[evidence_id]
                grouped[candidate.entity_id].append(
                    EligibleEvidence(
                        evidence_id=source.id,
                        entity_id=source.entity_id,
                        source_text=source.source_text,
                        technologies=source.technologies,
                        capabilities=source.capabilities,
                        outcomes=source.outcomes,
                        estimated_lines=candidate.estimated_lines,
                    )
                )
        entries = [
            EligibleEntry(
                entry_id=entry_id,
                title=items[entry_id].title,
                entry_cost_lines=(
                    plan.constraints.experience_entry_overhead_lines
                    if items[entry_id].kind.value == "experience"
                    else plan.constraints.project_entry_overhead_lines
                ),
                evidence=entry_evidence,
            )
            for entry_id, entry_evidence in grouped.items()
        ]
        return CompositionRecommendationRequest(
            posting_id=plan.posting_id,
            primary_focus=plan.strategy.primary_focus if plan.strategy else "",
            entries=entries,
            max_total_lines=plan.constraints.max_total_lines,
        )

    @staticmethod
    def _skill_composition_request(
        plan: TailoringPlan, profile: MasterProfile
    ) -> SkillCompositionRequest | None:
        categories = [
            EligibleSkillCategory(
                category_id=category.id,
                label=category.label,
                relevance_score=category.relevance_score,
                skills=[
                    EligibleSkill(
                        skill_id=skill.id,
                        value=skill.value,
                        relevance_score=skill.relevance_score,
                        supporting_job_signals=skill.supporting_job_signals,
                    )
                    for skill in category.skills
                    if skill.status != SkillSelectionStatus.EXCLUDED_UNRELATED
                ],
            )
            for category in plan.ranked_skill_categories
            if category.status != SkillSelectionStatus.EXCLUDED_UNRELATED
            and any(
                skill.status != SkillSelectionStatus.EXCLUDED_UNRELATED for skill in category.skills
            )
        ]
        if not categories:
            return None
        return SkillCompositionRequest(
            posting_id=plan.posting_id,
            job_signals=[f"{signal.id}: {signal.label}" for signal in plan.report.role.signals],
            categories=categories,
            evidence=[
                EligibleEvidence(
                    evidence_id=item.id,
                    entity_id=item.entity_id,
                    source_text=item.source_text,
                    technologies=item.technologies,
                    capabilities=item.capabilities,
                    outcomes=item.outcomes,
                    estimated_lines=1,
                )
                for item in profile.evidence
                if item.confirmed
                and item.entity_id in {candidate.entity_id for candidate in plan.claim_candidates}
            ],
        )

    @staticmethod
    def _approved_groups(
        plan: TailoringPlan, profile: MasterProfile
    ) -> list[ApprovedEvidenceGroup]:
        evidence_by_id = {item.id: item for item in profile.evidence}
        return [
            ApprovedEvidenceGroup(
                entry_id=candidate.entity_id,
                evidence_ids=candidate.evidence_ids,
                source_texts=[
                    evidence_by_id[evidence_id].source_text
                    for evidence_id in candidate.evidence_ids
                ],
                technologies=[
                    technology
                    for evidence_id in candidate.evidence_ids
                    for technology in evidence_by_id[evidence_id].technologies
                ],
                capabilities=[
                    capability
                    for evidence_id in candidate.evidence_ids
                    for capability in evidence_by_id[evidence_id].capabilities
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


def re_split_requirements(description: str) -> list[str]:
    return [
        item.strip() for item in re.split(r"[\r\n]+|(?<=[.!?;])\s+", description) if item.strip()
    ]


def _resume_bullets(resume: StructuredResume) -> list[StructuredBullet]:
    return [
        bullet
        for section in (resume.experience_bullets, resume.project_bullets)
        for bullets in section.values()
        for bullet in bullets
    ]


def _variant_sort_key(
    item: BulletVariantRecord,
) -> tuple[int, int, int, int, float, str]:
    return (
        0 if item.validation_status is BulletValidationStatus.VALIDATED else 1,
        0 if item.material_improvement else 1,
        item.line_fit.expected_line_count,
        int(item.line_fit.awkward_wrap_risk),
        item.line_fit.expected_final_line_width_ratio,
        item.variant_id,
    )


def _writing_style_failures(
    text: str,
    source_texts: list[str],
    posting_text: str,
    policy: ResumeWritingPolicy,
) -> list[str]:
    normalized = " ".join(text.casefold().split())
    failures = [
        f"writing policy prohibited phrase: {phrase}"
        for phrase in policy.prohibited_phrases
        if phrase in normalized
    ]
    source_normalized = " ".join(" ".join(source_texts).casefold().split())
    posting_normalized = " ".join(posting_text.casefold().split())
    copied_posting_phrases = [
        phrase
        for phrase in _word_ngrams(normalized, 8)
        if phrase in posting_normalized and phrase not in source_normalized
    ]
    if copied_posting_phrases:
        failures.append("rewritten bullet copied an unsupported long job-description phrase")
    return failures


def _material_improvement_reasons(
    text: str,
    source_texts: list[str],
    posting: JobPosting,
    line_fit: BulletLineFitDiagnostic,
    estimator: TemplateV1BulletLineEstimator,
) -> list[str]:
    source = " ".join(" ".join(source_texts).split())
    written = " ".join(text.split())
    if not source or written.casefold() == source.casefold():
        return []
    source_words = source.casefold().split()
    written_words = written.casefold().split()
    if len(source_words) == len(written_words) and source_words[1:] == written_words[1:]:
        return []
    reasons: list[str] = []
    source_line_fit = estimator.estimate(source)
    if line_fit.expected_line_count < source_line_fit.expected_line_count:
        reasons.append("reduced expected line cost")
    if source_line_fit.awkward_wrap_risk and not line_fit.awkward_wrap_risk:
        reasons.append("removed an awkward trailing fragment")
    if len(source_words) >= 8 and len(written_words) <= len(source_words) * 0.85:
        reasons.append("made the evidence materially more concise")
    similarity = SequenceMatcher(None, source_words, written_words).ratio()
    if similarity < 0.88 and len(written_words) >= 5:
        reasons.append("restructured the evidence for clearer technical emphasis")
    source_requirements = set(_matched_target_requirements(source, posting))
    written_requirements = set(_matched_target_requirements(written, posting))
    if written_requirements - source_requirements:
        reasons.append("foregrounded an already-supported target requirement")
    return list(dict.fromkeys(reasons))


def _mapping_rewrite_diagnostics(
    outcomes: list[ProviderRewriteMappingOutcome],
    group_by_evidence: dict[str, ApprovedEvidenceGroup],
    entry_kinds: dict[str, str],
) -> list[WriterRewriteDiagnostic]:
    diagnostics: list[WriterRewriteDiagnostic] = []
    for outcome in outcomes:
        if outcome.mapping_status is ProviderRewriteMappingStatus.MAPPED:
            continue
        groups = [
            group_by_evidence[evidence_id]
            for evidence_id in outcome.evidence_ids
            if evidence_id in group_by_evidence
        ]
        source_texts = [text for group in groups for text in group.source_texts]
        entry_ids = {group.entry_id for group in groups}
        entry_id = outcome.entry_id or (next(iter(entry_ids)) if len(entry_ids) == 1 else None)
        comparison = compare_rewrite_grounding(
            outcome.rewritten_text,
            source_texts,
            [
                value
                for group in groups
                for value in [*group.technologies, *group.capabilities, *group.metrics]
            ],
        )
        diagnostics.append(
            WriterRewriteDiagnostic(
                rewrite_index=outcome.rewrite_index,
                evidence_ids=outcome.evidence_ids,
                source_evidence_text=source_texts,
                rewritten_text=outcome.rewritten_text,
                reconstructed_claim=None,
                supporting_evidence_ids=[],
                entry_id=entry_id,
                entry_type=entry_kinds.get(entry_id) if entry_id is not None else None,
                provider_contract_mapping_result=outcome.mapping_status,
                validator_rejection_codes=outcome.failure_codes,
                validator_rejection_details=outcome.failure_details,
                normalized_unsupported_terms=list(
                    comparison.normalized_unsupported_terms
                ),
                ownership_comparison=comparison.ownership_comparison,
                metric_comparison=comparison.metric_comparison,
                causal_outcome_comparison=comparison.causal_outcome_comparison,
                singular_plural_scope_comparison=(
                    comparison.singular_plural_scope_comparison
                ),
                validation_status=BulletValidationStatus.REJECTED,
                batch_effect="pending_aggregate_result",
            )
        )
    return diagnostics


def _introduced_unverified_semantic_features(
    text: str,
    source_texts: list[str],
    structured_facts: list[str],
    policy: ResumeWritingPolicy,
) -> list[str]:
    """Quarantine new content-bearing terminology for bounded semantic review.

    Deterministic validation can prove that protected names, numbers, and known
    technologies were not contradicted. It cannot prove every novel lowercase
    synonym is entailed. Generic writing changes such as a stronger action verb
    are intentionally ignored by the shared feature extractor; any remaining new
    meaningful token therefore requires review before automatic rendering.
    """

    written = extract_reviewed_text_features(text)
    reviewed_bundle = " ".join([*source_texts, *structured_facts])
    reviewed = extract_reviewed_text_features(reviewed_bundle)
    reviewed_source_words = re.findall(
        r"[A-Za-z]+",
        reviewed_bundle.casefold(),
    )
    linguistic_canonical = {
        token: min(group) for group in policy.semantic_equivalence_groups for token in group
    }
    reviewed_tokens = {
        _linguistic_token(token, linguistic_canonical)
        for token in [*reviewed.meaningful_tokens, *reviewed_source_words]
    }
    introduced = {
        token
        for token in written.meaningful_tokens
        if _linguistic_token(token, linguistic_canonical) not in reviewed_tokens
        and not _ordinary_semantic_connective(token, text, reviewed_bundle)
    }
    return sorted(introduced)


def _ordinary_semantic_connective(token: str, text: str, source: str) -> bool:
    normalized = token.casefold()
    source_folded = source.casefold()
    text_folded = text.casefold()
    numeric_equivalent = numeric_semantics_preserved(text, source)
    text_numbers = set(re.findall(r"\d+(?:\.\d+)?", text))
    source_numbers = set(re.findall(r"\d+(?:\.\d+)?", source))
    shared_metric = bool(text_numbers & source_numbers) or numeric_equivalent
    if normalized.isdigit() and shared_metric:
        return True
    if normalized in {
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "over",
        "under",
        "percent",
        "percentage",
        "degrees",
    }:
        return numeric_equivalent
    if normalized in {"achieve", "achieved", "achieving"}:
        return shared_metric
    if normalized == "within":
        return numeric_equivalent and "within" in source_folded
    if normalized == "facilitate":
        return any(term in source_folded for term in ("enable", "enabled", "enabling"))
    if normalized == "up":
        return shared_metric and "up to" in text.casefold()
    if normalized in {"cross", "unit", "units", "cross-unit"} and "cross-unit" in text_folded:
        return "across business unit" in source_folded
    if normalized == "same":
        source_words = set(re.findall(r"[a-z]+", source_folded))
        text_words = set(re.findall(r"[a-z]+", text_folded))
        return len(source_words & text_words) >= 3
    return False


def _linguistic_token(
    token: str,
    canonical: dict[str, str],
) -> str:
    normalized = token.casefold().strip()
    return canonical.get(normalized, normalized)


def _strongest_relationship(
    relationships: list[EvidenceRelationship],
) -> EvidenceRelationship:
    order = {
        EvidenceRelationship.DIRECT: 0,
        EvidenceRelationship.ADJACENT: 1,
        EvidenceRelationship.COMPLEMENTARY: 2,
        EvidenceRelationship.INCIDENTAL: 3,
        EvidenceRelationship.REJECTED: 4,
    }
    return min(
        relationships,
        key=lambda item: order[item],
        default=EvidenceRelationship.REJECTED,
    )


def _word_ngrams(value: str, size: int) -> set[str]:
    words = value.split()
    return {" ".join(words[index : index + size]) for index in range(max(0, len(words) - size + 1))}


def _matched_target_requirements(
    text: str,
    posting: JobPosting,
) -> list[str]:
    normalized = text.casefold()
    return [
        requirement
        for requirement in _authoritative_posting_requirements(posting)
        if any(token in normalized for token in requirement.casefold().split() if len(token) >= 6)
    ][:6]


def _authoritative_posting_requirements(posting: JobPosting) -> list[str]:
    return [
        item.text
        for item in extract_posting_requirements(posting).requirements
        if item.authority is not RequirementAuthority.INCIDENTAL
    ]
