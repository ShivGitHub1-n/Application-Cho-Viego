from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from resume_tailor.application.cover_letter import CoverLetterService
from resume_tailor.application.generated_artifact import (
    ResumeGenerationConfiguration,
    artifact_fingerprint,
    build_fingerprint_inputs,
    generation_timestamp,
)
from resume_tailor.application.generation_diagnostics import GenerationTelemetry
from resume_tailor.application.hybrid_plan import apply_generic_technical_fallback
from resume_tailor.application.llm_services import HybridLlmServices
from resume_tailor.application.plan_validation import DeterministicPlanIntegrityValidator
from resume_tailor.application.resume_composition import DeterministicResumeComposer
from resume_tailor.application.resume_retrieval import InProcessResumeEvidenceRetriever
from resume_tailor.domain.cover_letter import CoverLetter, CoverLetterRecipient
from resume_tailor.domain.generated_artifact import (
    ArtifactFingerprintInputs,
    GeneratedResumeArtifact,
    GenerationStage,
    PaginationExecutionDiagnostic,
    ProviderExecutionDiagnostic,
)
from resume_tailor.domain.hybrid_resume import (
    HybridResumeDiagnostic,
    WriterExecutionStatus,
)
from resume_tailor.domain.llm_models import ProfileExtractionResult
from resume_tailor.domain.models import (
    JobPosting,
    MasterProfile,
    StructuredResume,
    TailoringPlan,
    TemplateConstraints,
)
from resume_tailor.domain.resume_composition import (
    TEMPLATE_V1_DENSITY_INVESTIGATION_FLOOR,
    CompositionUnderfillReason,
)
from resume_tailor.domain.resume_metadata import validate_structured_resume_metadata
from resume_tailor.ports.interfaces import (
    ResumeArtifactRenderer,
    ResumeEvidenceRetriever,
    ResumeOptimizer,
    ResumeWriter,
)


class TailorResumeService:
    """Coordinates opportunity-specific planning and evidence-bound document assembly."""

    def __init__(
        self,
        optimizer: ResumeOptimizer,
        resume_writer: ResumeWriter,
        hybrid_services: HybridLlmServices | None = None,
        cover_letter_service: CoverLetterService | None = None,
        resume_composer: DeterministicResumeComposer | None = None,
        evidence_retriever: ResumeEvidenceRetriever | None = None,
        artifact_renderer: ResumeArtifactRenderer | None = None,
        generation_configuration: ResumeGenerationConfiguration | None = None,
        telemetry: GenerationTelemetry | None = None,
    ) -> None:
        self._optimizer = optimizer
        self._resume_writer = resume_writer
        self._hybrid_services = hybrid_services
        self._cover_letter_service = cover_letter_service
        self._resume_composer = resume_composer
        self._evidence_retriever = evidence_retriever or InProcessResumeEvidenceRetriever()
        self._artifact_renderer = artifact_renderer
        self._generation_configuration = generation_configuration
        self._telemetry = telemetry or GenerationTelemetry()
        if self._hybrid_services is not None:
            self._hybrid_services.set_telemetry(self._telemetry)
        self._plan_validator = DeterministicPlanIntegrityValidator(
            optimizer,
            self._evidence_retriever,
        )

    @property
    def telemetry(self) -> GenerationTelemetry:
        return self._telemetry

    def start_generation(self) -> None:
        self._telemetry.reset()

    def create_plan(
        self,
        profile: MasterProfile,
        posting: JobPosting,
        constraints: TemplateConstraints,
    ) -> TailoringPlan:
        with self._telemetry.measure(GenerationStage.EVIDENCE_RETRIEVAL):
            self._telemetry.increment("evidence_retrievals")
            retrieval = self._evidence_retriever.retrieve(profile, posting)
        with self._telemetry.measure(GenerationStage.DETERMINISTIC_PLANNING):
            self._telemetry.increment("deterministic_plans")
            plan = apply_generic_technical_fallback(
                self._optimizer.create_plan(profile, posting, constraints),
                profile,
                retrieval,
            )
        if self._hybrid_services is None:
            self._telemetry.skip(
                GenerationStage.SEMANTIC_PLANNING,
                "Semantic planning service is not configured.",
            )
            return plan
        with self._telemetry.measure(GenerationStage.SEMANTIC_PLANNING):
            self._telemetry.increment("semantic_plans")
            return self._hybrid_services.enrich_plan(plan, profile, posting)

    def extract_profile_draft(
        self, profile_id: str, source_format: str, extracted_text: str
    ) -> ProfileExtractionResult:
        if self._hybrid_services is None:
            raise ValueError("Profile extraction requires a configured language model")
        return self._hybrid_services.extract_profile_draft(
            profile_id, source_format, extracted_text
        )

    def build_document(
        self,
        plan: TailoringPlan,
        profile: MasterProfile,
        approved_claim_ids: set[str],
    ) -> StructuredResume:
        with self._telemetry.measure(GenerationStage.CLAIM_VALIDATION):
            self._telemetry.increment("claim_validations")
            self._plan_validator.validate(plan, profile)
        with self._telemetry.measure(GenerationStage.EVIDENCE_RETRIEVAL):
            self._telemetry.increment("evidence_retrievals")
            retrieval = self._evidence_retriever.retrieve(profile, plan.posting)
        resume = self._resume_writer.write(
            plan,
            profile,
            approved_claim_ids,
        ).model_copy(
            update={
                "hybrid_diagnostic": (
                    self._hybrid_services.diagnostic_for_retrieval(retrieval)
                    if self._hybrid_services is not None
                    else HybridResumeDiagnostic(retrieval=retrieval)
                )
            }
        )
        if self._resume_composer is None:
            final_without_composition = (
                self._hybrid_services.rewrite_composed_resume(
                    resume,
                    profile,
                    plan.posting,
                    plan.constraints,
                    approved_claim_ids,
                )
                if self._hybrid_services is not None
                else resume
            )
            validate_structured_resume_metadata(final_without_composition)
            return final_without_composition
        writing_enabled = (
            self._hybrid_services is not None and self._hybrid_services.writing_enabled
        )
        source_composed = self._resume_composer.compose(
            resume,
            profile,
            plan.posting,
            plan.constraints,
            attempt_exact_final=not writing_enabled,
        )
        rewritten = (
            self._hybrid_services.rewrite_composed_resume(
                source_composed,
                profile,
                plan.posting,
                plan.constraints,
                approved_claim_ids,
            )
            if self._hybrid_services is not None
            else source_composed
        )
        final = (
            self._resume_composer.compose(
                rewritten,
                profile,
                plan.posting,
                plan.constraints,
                attempt_exact_final=True,
            )
            if writing_enabled
            else rewritten
        )
        composition = final.composition_diagnostic
        hybrid = final.hybrid_diagnostic
        if composition is None or hybrid is None:
            validate_structured_resume_metadata(final)
            return final
        rendered_variant_ids = {
            bullet.writing_variant.variant_id
            for section in (
                final.experience_bullets,
                final.project_bullets,
            )
            for bullets in section.values()
            for bullet in bullets
            if bullet.writing_variant is not None
        }
        final_bullets = [
            bullet
            for section in (final.experience_bullets, final.project_bullets)
            for bullets in section.values()
            for bullet in bullets
        ]
        rewritten_bullet_count = sum(
            bullet.writing_variant is not None for bullet in final_bullets
        )
        source_bullet_count = len(final_bullets) - rewritten_bullet_count
        writer_execution_status = hybrid.writer_execution_status
        writing_reason = hybrid.writing_reason
        if hybrid.rewrite_enabled and rendered_variant_ids:
            if writer_execution_status is not WriterExecutionStatus.CACHE_HIT:
                writer_execution_status = WriterExecutionStatus.WRITER_SUCCEEDED
            writing_reason = (
                f"{rewritten_bullet_count} validated materially improved rewrite(s) "
                "survived deterministic portfolio and page-fit selection."
            )
        elif hybrid.rewrite_enabled and hybrid.bullet_variants:
            writer_execution_status = WriterExecutionStatus.SOURCE_VARIANTS_SCORED_BETTER
            writing_reason = (
                "Rewriting was enabled and valid variants were available, but zero "
                "rewrites reached the document because reviewed source variants scored "
                "better for material improvement, evidence value, readability, or fit."
            )
        elif hybrid.rewrite_enabled and hybrid.rejected_variants:
            writer_execution_status = (
                WriterExecutionStatus.ALL_GENERATED_VARIANTS_REJECTED
            )
            writing_reason = (
                "Rewriting was enabled, but every generated variant failed grounding "
                "or writing-policy validation; reviewed source bullets were retained."
            )
        underfill_reasons = list(composition.underfill_reasons)
        if (
            composition.final_utilization_ratio < TEMPLATE_V1_DENSITY_INVESTIGATION_FLOOR
            and (hybrid.rejected_variants or hybrid.validation_failures)
            and not rendered_variant_ids
        ):
            underfill_reasons.append(CompositionUnderfillReason.VALIDATION_LIMITED)
        underfill_reasons = list(dict.fromkeys(underfill_reasons))
        updated_composition = composition.model_copy(
            update={"underfill_reasons": underfill_reasons}
        )
        final = final.model_copy(
            update={
                "composition_diagnostic": updated_composition,
                "hybrid_diagnostic": hybrid.model_copy(
                    update={
                        "estimated_remaining_lines": max(
                            0,
                            round(
                                (1 - composition.final_utilization_ratio)
                                * plan.constraints.max_total_lines
                            ),
                        ),
                        "exact_pagination": (composition.verification_status.value == "exact"),
                        "page_verification_provider": (composition.verification_provider),
                        "underfill_reason": (
                            ", ".join(item.value for item in underfill_reasons) or None
                        ),
                        "bullet_variants": [
                            item.model_copy(
                                update={"selected": (item.variant_id in rendered_variant_ids)}
                            )
                            for item in hybrid.bullet_variants
                        ],
                        "writer_execution_status": writer_execution_status,
                        "writing_reason": writing_reason,
                        "source_bullet_count": source_bullet_count,
                        "rewritten_bullet_count": rewritten_bullet_count,
                        "fallback_bullet_count": (
                            source_bullet_count if hybrid.rewrite_enabled else 0
                        ),
                        "rejected_variant_count": len(hybrid.rejected_variants),
                        "deterministic_fallback_used": (
                            hybrid.rewrite_enabled and rewritten_bullet_count == 0
                        ),
                    }
                ),
            }
        )
        validate_structured_resume_metadata(final)
        return final

    def artifact_fingerprint_inputs(
        self,
        plan: TailoringPlan,
        profile: MasterProfile,
        approved_claim_ids: set[str],
    ) -> ArtifactFingerprintInputs:
        configuration = self._require_generation_configuration()
        return build_fingerprint_inputs(
            profile=profile,
            posting=plan.posting,
            plan=plan,
            approved_claim_ids=approved_claim_ids,
            template_identity=configuration.template_identity,
            composition_contract_version=configuration.composition_contract_version,
            writing_policy_version=configuration.writing_policy_version,
            writing_contract_version=configuration.writing_contract_version,
            feature_flags=configuration.feature_flags,
            provider=configuration.provider,
            model=configuration.model,
        )

    def expected_artifact_fingerprint(
        self,
        plan: TailoringPlan,
        profile: MasterProfile,
        approved_claim_ids: set[str],
    ) -> str:
        return artifact_fingerprint(
            self.artifact_fingerprint_inputs(plan, profile, approved_claim_ids)
        )

    def build_generated_artifact(
        self,
        plan: TailoringPlan,
        profile: MasterProfile,
        approved_claim_ids: set[str],
        *,
        existing_artifact: GeneratedResumeArtifact | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> GeneratedResumeArtifact:
        configuration = self._require_generation_configuration()
        if self._artifact_renderer is None:
            raise ValueError("Generated-resume artifact rendering is not configured")
        fingerprint_inputs = self.artifact_fingerprint_inputs(
            plan,
            profile,
            approved_claim_ids,
        )
        fingerprint = artifact_fingerprint(fingerprint_inputs)
        if (
            existing_artifact is not None
            and existing_artifact.artifact_fingerprint == fingerprint
        ):
            return existing_artifact
        build_started = self._telemetry.clock()
        prior_elapsed = sum(
            self._telemetry.elapsed(stage)
            for stage in (
                GenerationStage.PROFILE_LOADING,
                GenerationStage.POSTING_NORMALIZATION,
                GenerationStage.EVIDENCE_RETRIEVAL,
                GenerationStage.DETERMINISTIC_PLANNING,
                GenerationStage.SEMANTIC_PLANNING,
                GenerationStage.STREAMLIT_RERUN_OVERHEAD,
            )
        )
        final_resume = self.build_document(plan, profile, approved_claim_ids)
        docx_bytes = self._artifact_renderer.render_docx_bytes(final_resume)
        if not docx_bytes:
            raise ValueError("Generated resume artifact contains no DOCX bytes")
        composition = final_resume.composition_diagnostic
        writing = final_resume.hybrid_diagnostic
        counts = self._telemetry.call_counts()
        provider_status = (
            writing.writer_execution_status.value
            if writing is not None
            else "provider_unavailable"
        )
        provider_reason = (
            writing.writing_reason
            if writing is not None
            else "No hybrid writing diagnostic was produced."
        )
        provider_diagnostic = ProviderExecutionDiagnostic(
            writing_enabled=configuration.feature_flags.get("bullet_rewrite", False),
            provider=configuration.provider,
            model=configuration.model,
            status=provider_status,
            call_count=counts.provider_calls,
            retry_count=counts.provider_retries,
            cache_hit_count=writing.provider_cache_hits if writing is not None else 0,
            request_timeout_seconds=configuration.provider_timeout_seconds,
            configured_retry_count=configuration.provider_retry_count,
            deterministic_fallback_used=(
                writing.deterministic_fallback_used if writing is not None else True
            ),
            reason=provider_reason,
        )
        exact = composition is not None and composition.verification_status.value == "exact"
        pagination_diagnostic = PaginationExecutionDiagnostic(
            status="exact" if exact else "pagination_unverified",
            attempt_count=counts.pagination_attempts,
            provider=(
                composition.verification_provider
                if composition is not None
                else "not configured"
            ),
            elapsed_seconds=self._telemetry.elapsed(
                GenerationStage.EXACT_WORD_PAGINATION
            ),
            failure_reason=(
                composition.verification_failure if composition is not None else None
            ),
        )
        selected_variants = (
            [item for item in writing.bullet_variants if item.selected]
            if writing is not None
            else []
        )
        return GeneratedResumeArtifact(
            artifact_fingerprint=fingerprint,
            fingerprint_inputs=fingerprint_inputs,
            generation_timestamp=generation_timestamp(now),
            template_identity=configuration.template_identity,
            composition_contract_version=configuration.composition_contract_version,
            writing_policy_version=configuration.writing_policy_version,
            writing_contract_version=configuration.writing_contract_version,
            final_validated_plan=plan,
            final_resume=final_resume,
            selected_bullet_variants=selected_variants,
            composition_diagnostic=composition,
            writing_diagnostic=writing,
            stage_timings=self._telemetry.timings(),
            call_counts=counts,
            provider_diagnostic=provider_diagnostic,
            pagination_diagnostic=pagination_diagnostic,
            total_build_seconds=prior_elapsed + (self._telemetry.clock() - build_started),
            docx_bytes=docx_bytes,
        )

    def _require_generation_configuration(self) -> ResumeGenerationConfiguration:
        if self._generation_configuration is None:
            raise ValueError("Generated-resume artifact identity is not configured")
        return self._generation_configuration

    def draft_cover_letter(
        self,
        profile: MasterProfile,
        posting: JobPosting,
        plan: TailoringPlan,
        *,
        recipient: CoverLetterRecipient | None = None,
        compact: bool = False,
    ) -> CoverLetter:
        if self._cover_letter_service is None:
            raise ValueError("Cover-letter service is not configured")
        return self._cover_letter_service.draft(
            profile, posting, plan, recipient=recipient, compact=compact
        )

    def approve_cover_letter(
        self, letter: CoverLetter, approved_claim_ids: set[str], *, reviewed: bool
    ) -> CoverLetter:
        if self._cover_letter_service is None:
            raise ValueError("Cover-letter service is not configured")
        return self._cover_letter_service.approve(letter, approved_claim_ids, reviewed=reviewed)

    def export_cover_letter(self, letter: CoverLetter, output_directory: Path) -> CoverLetter:
        if self._cover_letter_service is None:
            raise ValueError("Cover-letter service is not configured")
        return self._cover_letter_service.export(letter, output_directory)
