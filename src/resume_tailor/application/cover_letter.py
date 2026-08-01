from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from resume_tailor.application.company_research import BoundedCompanyResearchService
from resume_tailor.application.cover_letter_evidence import CoverLetterEvidencePortfolio
from resume_tailor.application.cover_letter_page_fit import (
    CoverLetterPageFitter,
)
from resume_tailor.application.cover_letter_policy import (
    COVER_LETTER_PROVIDER_CONTRACT_VERSION,
    COVER_LETTER_TEMPLATE_IDENTITY,
    COVER_LETTER_VALIDATION_POLICY_VERSION,
    COVER_LETTER_WRITING_CONSTRAINTS,
    COVER_LETTER_WRITING_POLICY_VERSION,
)
from resume_tailor.application.cover_letter_validation import (
    CoverLetterValidationResult,
    CoverLetterValidator,
    DeterministicCoverLetterComposer,
)
from resume_tailor.application.generated_artifact import content_fingerprint
from resume_tailor.domain.company_research import (
    CompanyFactConfidence,
    CompanyResearchBundle,
    CompanyResearchRequest,
    CompanyResearchStatus,
)
from resume_tailor.domain.cover_letter import (
    CoverLetter,
    CoverLetterArtifactFingerprintInputs,
    CoverLetterCallCounts,
    CoverLetterCandidateValidationDiagnostic,
    CoverLetterClaimDiagnostic,
    CoverLetterDownload,
    CoverLetterEvidenceRecord,
    CoverLetterFallbackReason,
    CoverLetterLayoutProfile,
    CoverLetterPageFitDiagnostic,
    CoverLetterPageFitStatus,
    CoverLetterParagraphPurpose,
    CoverLetterProviderDiagnostic,
    CoverLetterProviderStatus,
    CoverLetterQualityGateResult,
    CoverLetterQualityGateStatus,
    CoverLetterRecipient,
    CoverLetterResumeConsistencyFinding,
    CoverLetterReviewState,
    GeneratedCoverLetterArtifact,
)
from resume_tailor.domain.generated_artifact import GenerationStage, StageTiming
from resume_tailor.domain.llm_models import (
    CoverLetterCompanyFact,
    CoverLetterDraftOutput,
    CoverLetterDraftParagraph,
    CoverLetterDraftRequest,
    CoverLetterDraftResult,
    CoverLetterEvidence,
    LanguageModelError,
    LanguageModelErrorKind,
)
from resume_tailor.domain.models import JobPosting, MasterProfile, StructuredResume, TailoringPlan
from resume_tailor.ports.cover_letter_rendering import CoverLetterBatchRenderer
from resume_tailor.ports.interfaces import ResumeLanguageModel

Clock = Callable[[], float]
Now = Callable[[], datetime]


class CoverLetterValidationError(ValueError):
    pass


class CoverLetterCandidateRejectionError(CoverLetterValidationError):
    """Expose safe component-level reasons when every candidate is rejected."""

    def __init__(
        self,
        diagnostics: list[CoverLetterCandidateValidationDiagnostic],
    ) -> None:
        self.diagnostics = diagnostics
        summaries = []
        for diagnostic in diagnostics:
            failed = []
            for label, status in (
                ("structural", diagnostic.structural_validation),
                ("company", diagnostic.company_validation),
                ("narrative", diagnostic.narrative_validation),
                ("claim", diagnostic.claim_validation),
            ):
                if status is CoverLetterQualityGateStatus.FAILED:
                    failed.append(label)
            codes = ", ".join(diagnostic.rejection_codes[:3]) or "unspecified rejection"
            summaries.append(
                f"candidate {diagnostic.candidate_index + 1}: "
                f"{'/'.join(failed) or 'validation'} failed ({codes})"
            )
        super().__init__("No cover-letter candidate passed validation. " + "; ".join(summaries))


class CoverLetterPageFitError(ValueError):
    pass


@dataclass(frozen=True)
class _CandidateOutput:
    generation_source: str
    output: CoverLetterDraftOutput


class CoverLetterService:
    """Orchestrate one bounded, evidence-grounded cover-letter artifact build."""

    def __init__(
        self,
        language_model: ResumeLanguageModel | None = None,
        layout_profile: CoverLetterLayoutProfile | None = None,
        renderer: CoverLetterBatchRenderer | None = None,
        *,
        company_research: BoundedCompanyResearchService | None = None,
        evidence_portfolio: CoverLetterEvidencePortfolio | None = None,
        validator: CoverLetterValidator | None = None,
        deterministic_composer: DeterministicCoverLetterComposer | None = None,
        provider_name: str = "unconfigured",
        model_name: str = "unconfigured",
        provider_unavailable_reason: str | None = None,
        clock: Clock = perf_counter,
        now: Now | None = None,
    ) -> None:
        self._language_model = language_model
        self._layout_profile = layout_profile or CoverLetterLayoutProfile()
        self._renderer = renderer
        self._research = company_research or BoundedCompanyResearchService()
        self._evidence = evidence_portfolio or CoverLetterEvidencePortfolio()
        self._validator = validator or CoverLetterValidator()
        self._fallback = deterministic_composer or DeterministicCoverLetterComposer()
        self._provider_name = provider_name
        self._model_name = model_name
        self._provider_unavailable_reason = provider_unavailable_reason
        self._clock = clock
        self._now = now or (lambda: datetime.now(UTC))
        self._provider_cache: dict[str, CoverLetterDraftResult] = {}
        self._artifact_cache: dict[str, GeneratedCoverLetterArtifact] = {}
        self._artifact_version = 0

    @property
    def layout_profile(self) -> CoverLetterLayoutProfile:
        return self._layout_profile

    def generate_artifact(
        self,
        profile: MasterProfile,
        posting: JobPosting,
        plan: TailoringPlan,
        *,
        recipient: CoverLetterRecipient | None = None,
        final_resume: StructuredResume | None = None,
        research_request: CompanyResearchRequest | None = None,
        explicit_motivation: str | None = None,
        date_text: str | None = None,
    ) -> GeneratedCoverLetterArtifact:
        if self._renderer is None:
            raise CoverLetterValidationError(
                "A cover-letter renderer is required for artifact generation"
            )
        self._validate_inputs(profile, posting, plan)
        build_started = self._clock()
        timings: list[StageTiming] = []
        recipient = recipient or CoverLetterRecipient(company=posting.company_name)
        research_request = self._bind_research_request(posting, research_request)
        resolved_date_text = date_text or date.today().strftime("%B %d, %Y").replace(" 0", " ")

        started = self._clock()
        research = self._research.research(research_request)
        timings.append(self._timing(GenerationStage.COMPANY_RESEARCH, started))

        started = self._clock()
        evidence, evidence_diagnostic = self._evidence.select(
            profile,
            posting,
            plan,
            final_resume=final_resume,
            explicit_motivation=explicit_motivation,
        )
        timings.append(self._timing(GenerationStage.COVER_LETTER_EVIDENCE_SELECTION, started))
        if not evidence:
            raise CoverLetterValidationError("No reviewed evidence is available for a cover letter")
        request = self._create_request(posting, plan, evidence, research, final_resume)
        cache_identity = self._build_fingerprint_inputs(
            profile,
            posting,
            plan,
            final_resume,
            research_request,
            research,
            evidence,
            recipient,
            explicit_motivation,
            resolved_date_text,
        )
        artifact_key = self._artifact_fingerprint(cache_identity)
        cached_artifact = self._artifact_cache.get(artifact_key)
        if cached_artifact is not None:
            return cached_artifact

        provider_started = self._clock()
        provider_result, provider_diagnostic = self._provider_output(request)
        timings.append(self._timing(GenerationStage.PROVIDER_REQUEST, provider_started))

        validation_started = self._clock()
        outputs, fallback_reason, rejected, review_required, consistency = self._validated_outputs(
            provider_result.output if provider_result is not None else None,
            evidence,
            research,
            posting,
            final_resume,
            provider_diagnostic.fallback_reason,
        )
        timings.append(self._timing(GenerationStage.CLAIM_VALIDATION, validation_started))

        quality_started = self._clock()
        candidates: list[CoverLetter] = []
        candidate_validations: list[CoverLetterValidationResult] = []
        candidate_diagnostics: list[CoverLetterCandidateValidationDiagnostic] = []
        eligible_diagnostic_indexes: list[int] = []
        for candidate_index, candidate in enumerate(outputs):
            output = candidate.output
            validated = self._validator.validate_output(
                output,
                evidence,
                research,
                posting,
                final_resume=final_resume,
            )
            candidate_diagnostics.append(
                self._candidate_validation_diagnostic(
                    candidate_index,
                    candidate,
                    validated,
                    posting,
                    recipient,
                    research,
                    evidence,
                    final_resume,
                )
            )
            if not self._required_content_gates_pass(validated.quality_gates):
                continue
            eligible_diagnostic_indexes.append(candidate_index)
            candidates.append(
                self._assemble_letter(
                    profile,
                    posting,
                    plan,
                    recipient,
                    validated,
                    resolved_date_text,
                )
            )
            candidate_validations.append(validated)
        if not candidates:
            source_bound = _CandidateOutput(
                generation_source="deterministic:source_bound_fallback",
                output=self._fallback.source_bound_fallback(evidence, research, posting),
            )
            source_bound_index = len(outputs)
            source_bound_validation = self._validator.validate_output(
                source_bound.output,
                evidence,
                research,
                posting,
                final_resume=final_resume,
            )
            candidate_diagnostics.append(
                self._candidate_validation_diagnostic(
                    source_bound_index,
                    source_bound,
                    source_bound_validation,
                    posting,
                    recipient,
                    research,
                    evidence,
                    final_resume,
                )
            )
            if self._required_content_gates_pass(source_bound_validation.quality_gates):
                eligible_diagnostic_indexes.append(source_bound_index)
                candidates.append(
                    self._assemble_letter(
                        profile,
                        posting,
                        plan,
                        recipient,
                        source_bound_validation,
                        resolved_date_text,
                    )
                )
                candidate_validations.append(source_bound_validation)
                outputs.append(source_bound)
        if not candidates:
            raise CoverLetterCandidateRejectionError(candidate_diagnostics)
        for diagnostic_index in eligible_diagnostic_indexes:
            candidate_diagnostics[diagnostic_index] = candidate_diagnostics[
                diagnostic_index
            ].model_copy(update={"rendering_attempted": True})
        timings.append(self._timing(GenerationStage.COVER_LETTER_QUALITY_GATES, quality_started))

        fit_started = self._clock()
        with TemporaryDirectory(prefix="cover-letter-page-fit-") as directory:
            fitted = CoverLetterPageFitter(self._renderer).fit(candidates, Path(directory))
        timings.append(
            StageTiming(
                stage=GenerationStage.DOCX_RENDERING,
                elapsed_seconds=fitted.render_elapsed_seconds,
                invocation_count=len(candidates),
                detail="Bounded candidate-batch DOCX rendering and pagination measurement.",
            )
        )
        timings.append(self._timing(GenerationStage.COVER_LETTER_PAGE_FIT, fit_started))
        selected_index = int(fitted.diagnostic.selected_candidate_id.rsplit(":", 1)[-1])
        selected_validation = candidate_validations[selected_index]
        gates = [
            *selected_validation.quality_gates,
            self._page_fit_gate(fitted.diagnostic),
            self._research_gate(research),
        ]
        ready = not any(gate.status is CoverLetterQualityGateStatus.FAILED for gate in gates)
        state = (
            CoverLetterReviewState.GENERATED_AWAITING_REVIEW
            if ready
            else CoverLetterReviewState.RESEARCH_LIMITED
            if any(
                gate.gate == "company_research"
                and gate.status is CoverLetterQualityGateStatus.FAILED
                for gate in gates
            )
            else CoverLetterReviewState.GENERATION_FAILED
        )
        self._artifact_version += 1
        call_counts = CoverLetterCallCounts(
            research_calls=1,
            research_network_requests=research.network_request_count,
            provider_calls=provider_diagnostic.request_count,
            provider_repairs=provider_diagnostic.repair_count,
            claim_validations=sum(len(candidate.output.paragraphs) for candidate in outputs),
            composition_searches=1,
            docx_renders=len(candidates),
            pagination_attempts=min(1, self._renderer.pagination_attempt_count),
        )
        provider_diagnostic = provider_diagnostic.model_copy(
            update={
                "fallback_reason": fallback_reason or provider_diagnostic.fallback_reason,
                **(
                    {
                        "status": CoverLetterProviderStatus.VALIDATION_FALLBACK,
                        "safe_detail": (
                            "Provider prose failed semantic validation; locally grounded "
                            "deterministic paragraphs were selected."
                        ),
                    }
                    if fallback_reason is CoverLetterFallbackReason.ALL_PARAGRAPHS_REJECTED
                    else {}
                ),
            }
        )
        storage_started = self._clock()
        artifact = GeneratedCoverLetterArtifact(
            artifact_fingerprint=artifact_key,
            artifact_version=self._artifact_version,
            fingerprint_inputs=cache_identity,
            generation_timestamp=self._aware_now(),
            review_state=state,
            ready_for_review=ready,
            letter=fitted.letter,
            evidence_records=evidence,
            company_research=research,
            evidence_selection=evidence_diagnostic,
            quality_gates=gates,
            candidate_validations=candidate_diagnostics,
            rejected_claims=[*rejected, *selected_validation.rejected_claims],
            review_required_claims=[
                *review_required,
                *selected_validation.review_required_claims,
            ],
            resume_consistency=consistency or selected_validation.resume_consistency,
            provider_diagnostic=provider_diagnostic,
            page_fit=fitted.diagnostic,
            call_counts=call_counts,
            stage_timings=timings,
            total_build_seconds=0,
            docx_bytes=fitted.render.docx_bytes,
        )
        timings.append(self._timing(GenerationStage.GENERATED_ARTIFACT_STORAGE, storage_started))
        artifact = artifact.model_copy(
            update={
                "stage_timings": timings,
                "total_build_seconds": max(0.0, self._clock() - build_started),
            }
        )
        self._artifact_cache[artifact_key] = artifact
        return artifact

    def create_request(
        self,
        profile: MasterProfile,
        posting: JobPosting,
        plan: TailoringPlan,
        *,
        final_resume: StructuredResume | None = None,
        research_request: CompanyResearchRequest | None = None,
        explicit_motivation: str | None = None,
    ) -> CoverLetterDraftRequest:
        self._validate_inputs(profile, posting, plan)
        research = self._research.research(self._bind_research_request(posting, research_request))
        evidence, _ = self._evidence.select(
            profile,
            posting,
            plan,
            final_resume=final_resume,
            explicit_motivation=explicit_motivation,
        )
        return self._create_request(posting, plan, evidence, research, final_resume)

    def approve_artifact(
        self,
        artifact: GeneratedCoverLetterArtifact,
        *,
        expected_fingerprint: str,
        manual_word_inspection_confirmed: bool = False,
    ) -> GeneratedCoverLetterArtifact:
        if artifact.artifact_fingerprint != expected_fingerprint or not artifact.current:
            raise CoverLetterValidationError(
                "The cover-letter artifact is stale and must be regenerated"
            )
        if not artifact.ready_for_review:
            raise CoverLetterValidationError("The cover-letter artifact has failed quality gates")
        if (
            artifact.page_fit.manual_word_inspection_required
            and not manual_word_inspection_confirmed
        ):
            raise CoverLetterValidationError(
                "Manual Microsoft Word inspection is required before approval when "
                "pagination is unverified"
            )
        return artifact.model_copy(
            update={
                "review_state": CoverLetterReviewState.APPROVED,
                "approved_at": self._aware_now(),
            }
        )

    def prepare_download(
        self,
        artifact: GeneratedCoverLetterArtifact,
        *,
        expected_fingerprint: str,
    ) -> CoverLetterDownload:
        started = self._clock()
        if artifact.artifact_fingerprint != expected_fingerprint or not artifact.current:
            raise CoverLetterValidationError("A stale cover-letter artifact cannot be downloaded")
        if artifact.review_state not in {
            CoverLetterReviewState.APPROVED,
            CoverLetterReviewState.DOWNLOADED,
        }:
            raise CoverLetterValidationError(
                "Approve the current cover-letter artifact before download"
            )
        return CoverLetterDownload(
            artifact_fingerprint=artifact.artifact_fingerprint,
            artifact_version=artifact.artifact_version,
            docx_bytes=artifact.docx_bytes,
            elapsed_seconds=max(0.0, self._clock() - started),
            generation_call_counts=CoverLetterCallCounts(download_preparations=1),
        )

    @staticmethod
    def mark_downloaded(
        artifact: GeneratedCoverLetterArtifact,
    ) -> GeneratedCoverLetterArtifact:
        if artifact.review_state is not CoverLetterReviewState.APPROVED:
            raise CoverLetterValidationError(
                "Only an approved cover letter can be marked downloaded"
            )
        return artifact.model_copy(update={"review_state": CoverLetterReviewState.DOWNLOADED})

    def artifact_is_current(
        self,
        artifact: GeneratedCoverLetterArtifact,
        profile: MasterProfile,
        posting: JobPosting,
        plan: TailoringPlan,
        *,
        recipient: CoverLetterRecipient,
        final_resume: StructuredResume | None,
        research_request: CompanyResearchRequest,
        explicit_motivation: str | None,
        date_text: str | None = None,
    ) -> bool:
        inputs = artifact.fingerprint_inputs
        resolved_date_text = date_text or date.today().strftime("%B %d, %Y").replace(" 0", " ")
        bound_research_request = self._bind_research_request(posting, research_request)
        return all(
            (
                inputs.reviewed_profile_fingerprint == content_fingerprint(profile),
                inputs.posting_fingerprint == content_fingerprint(posting),
                inputs.plan_fingerprint == content_fingerprint(plan),
                inputs.final_resume_fingerprint
                == (content_fingerprint(final_resume) if final_resume is not None else None),
                inputs.research_request_fingerprint == content_fingerprint(bound_research_request),
                inputs.recipient_fingerprint == content_fingerprint(recipient),
                inputs.motivation_fingerprint
                == (content_fingerprint(explicit_motivation) if explicit_motivation else None),
                inputs.date_text == resolved_date_text,
            )
        )

    @staticmethod
    def default_research_request(posting: JobPosting) -> CompanyResearchRequest:
        return CompanyResearchRequest(
            company_name=posting.company_name,
            role_title=posting.title,
            job_url=posting.source_url,
            posting_fingerprint=content_fingerprint(posting),
            posting_description=posting.description,
            enabled=True,
        )

    @staticmethod
    def _bind_research_request(
        posting: JobPosting,
        request: CompanyResearchRequest | None,
    ) -> CompanyResearchRequest:
        """Keep optional research controls while restoring active-posting authority."""

        if request is None:
            return CoverLetterService.default_research_request(posting)
        return request.model_copy(
            update={
                "company_name": request.company_name or posting.company_name,
                "role_title": posting.title,
                "job_url": posting.source_url,
                "posting_fingerprint": content_fingerprint(posting),
                "posting_description": posting.description,
            }
        )

    def _create_request(
        self,
        posting: JobPosting,
        plan: TailoringPlan,
        evidence: list[CoverLetterEvidenceRecord],
        research: CompanyResearchBundle,
        final_resume: StructuredResume | None,
    ) -> CoverLetterDraftRequest:
        source_by_id = {source.id: source for source in research.sources}
        facts = [
            fact
            for fact in research.facts
            if fact.confidence is not CompanyFactConfidence.CONFLICTING
        ]
        return CoverLetterDraftRequest(
            job_title=posting.title,
            company_name=posting.company_name,
            job_description=posting.description,
            strategy=plan.strategy.primary_focus if plan.strategy else posting.title,
            selected_entry_ids=list(
                dict.fromkeys(item.entity_id for item in evidence if item.entity_id)
            ),
            selected_evidence=[
                CoverLetterEvidence(
                    evidence_id=item.id,
                    evidence_kind=item.kind.value,
                    source_text=item.source_text,
                    entity_id=item.entity_id,
                    entry_title=item.entry_title,
                    technologies=item.technologies,
                    outcomes=item.outcomes,
                    matched_requirements=item.matched_requirements,
                    selected_in_final_resume=item.selected_in_final_resume,
                )
                for item in evidence
            ],
            company_research=[
                CoverLetterCompanyFact(
                    research_id=fact.id,
                    fact=fact.fact,
                    supported_claim=fact.supported_claim,
                    source_title=source_by_id[fact.source_id].title,
                    source_type=source_by_id[fact.source_id].source_type.value,
                )
                for fact in facts
            ],
            final_resume_evidence_ids=sorted(self._resume_evidence_ids(final_resume)),
            approximate_body_lines=self._approximate_body_lines(),
            writing_constraints=list(COVER_LETTER_WRITING_CONSTRAINTS),
        )

    def _provider_output(
        self,
        request: CoverLetterDraftRequest,
    ) -> tuple[CoverLetterDraftResult | None, CoverLetterProviderDiagnostic]:
        started = self._clock()
        key = self._provider_cache_key(request)
        cached = self._provider_cache.get(key)
        if cached is not None:
            return cached, CoverLetterProviderDiagnostic(
                provider=cached.metadata.provider,
                model=cached.metadata.model,
                status=CoverLetterProviderStatus.CACHE_HIT,
                request_count=0,
                repair_count=0,
                cache_hit_count=1,
                elapsed_seconds=max(0.0, self._clock() - started),
                finish_reason=cached.metadata.finish_reason,
                safe_detail="Validated provider response reused from the cover-letter cache.",
            )
        if self._language_model is None:
            reason = (
                CoverLetterFallbackReason.CREDENTIALS_ABSENT
                if self._provider_unavailable_reason
                else CoverLetterFallbackReason.PROVIDER_DISABLED
            )
            return None, CoverLetterProviderDiagnostic(
                provider=self._provider_name,
                model=self._model_name,
                status=(
                    CoverLetterProviderStatus.CONFIGURATION_UNAVAILABLE
                    if self._provider_unavailable_reason
                    else CoverLetterProviderStatus.DISABLED
                ),
                request_count=0,
                repair_count=0,
                cache_hit_count=0,
                elapsed_seconds=max(0.0, self._clock() - started),
                fallback_reason=reason,
                safe_detail=self._provider_unavailable_reason
                or "Cover-letter provider is disabled.",
            )
        calls = 0
        repairs = 0
        try:
            calls += 1
            result = self._language_model.draft_cover_letter(request)
        except LanguageModelError as error:
            if error.kind is LanguageModelErrorKind.MALFORMED_RESPONSE:
                repairs = 1
                repair = request.model_copy(
                    update={
                        "repair_instruction": (
                            "Return the same intended letter using only the required typed schema. "
                            "Do not add fields or explanatory text."
                        )
                    }
                )
                try:
                    calls += 1
                    result = self._language_model.draft_cover_letter(repair)
                except LanguageModelError:
                    return None, self._provider_failure(
                        started,
                        calls,
                        repairs,
                        CoverLetterProviderStatus.MALFORMED_OUTPUT,
                        CoverLetterFallbackReason.PROVIDER_MALFORMED_AFTER_REPAIR,
                        "Provider output remained malformed after one repair request.",
                    )
            else:
                return None, self._provider_error_diagnostic(started, calls, error)
        self._provider_cache[key] = result
        cache_hit = result.metadata.cache_hit
        return result, CoverLetterProviderDiagnostic(
            provider=result.metadata.provider,
            model=result.metadata.model,
            status=(
                CoverLetterProviderStatus.CACHE_HIT
                if cache_hit
                else CoverLetterProviderStatus.SUCCEEDED
            ),
            request_count=0 if cache_hit else calls,
            repair_count=repairs,
            cache_hit_count=1 if cache_hit else 0,
            elapsed_seconds=max(0.0, self._clock() - started),
            finish_reason=result.metadata.finish_reason,
            safe_detail="Provider returned typed paragraph content for local validation.",
        )

    def _validated_outputs(
        self,
        provider_output: CoverLetterDraftOutput | None,
        evidence: list[CoverLetterEvidenceRecord],
        research: CompanyResearchBundle,
        posting: JobPosting,
        final_resume: StructuredResume | None,
        provider_fallback: CoverLetterFallbackReason | None,
    ) -> tuple[
        list[_CandidateOutput],
        CoverLetterFallbackReason | None,
        list[CoverLetterClaimDiagnostic],
        list[CoverLetterClaimDiagnostic],
        list[CoverLetterResumeConsistencyFinding],
    ]:
        deterministic = self._fallback.variants(evidence, research, posting)
        rejected: list[CoverLetterClaimDiagnostic] = []
        review_required: list[CoverLetterClaimDiagnostic] = []
        consistency: list[CoverLetterResumeConsistencyFinding] = []
        outputs: list[_CandidateOutput] = []
        fallback_reason = provider_fallback
        if provider_output is not None:
            validated = self._validator.validate_output(
                provider_output,
                evidence,
                research,
                posting,
                final_resume=final_resume,
            )
            rejected.extend(validated.rejected_claims)
            review_required.extend(validated.review_required_claims)
            consistency.extend(validated.resume_consistency)
            if validated.paragraphs:
                valid_text = {paragraph.text for paragraph in validated.paragraphs}
                fallback_by_purpose = {
                    paragraph.purpose: paragraph for paragraph in deterministic[-1].paragraphs
                }
                merged = []
                for paragraph in provider_output.paragraphs:
                    if " ".join(paragraph.text.split()) in valid_text:
                        merged.append(paragraph)
                    elif paragraph.purpose in fallback_by_purpose:
                        merged.append(fallback_by_purpose[paragraph.purpose])
                purposes = {paragraph.purpose for paragraph in merged}
                for required in (
                    CoverLetterParagraphPurpose.OPENING,
                    CoverLetterParagraphPurpose.CLOSING,
                ):
                    if required not in purposes:
                        merged.append(fallback_by_purpose[required])
                merged.sort(key=self._purpose_order)
                try:
                    repaired_output = CoverLetterDraftOutput(paragraphs=merged)
                except ValueError:
                    repaired_output = deterministic[-1]
                repaired_validation = self._validator.validate_output(
                    repaired_output,
                    evidence,
                    research,
                    posting,
                    final_resume=final_resume,
                )
                if self._required_content_gates_pass(repaired_validation.quality_gates):
                    outputs.append(
                        _CandidateOutput(
                            generation_source="provider_with_deterministic_repair",
                            output=repaired_output,
                        )
                    )
            if not outputs:
                fallback_reason = CoverLetterFallbackReason.ALL_PARAGRAPHS_REJECTED
        outputs.extend(
            _CandidateOutput(
                generation_source=(
                    "deterministic:"
                    f"{output.paragraphs[0].length_class.value if output.paragraphs else 'unknown'}"
                ),
                output=output,
            )
            for output in deterministic
        )
        unique: list[_CandidateOutput] = []
        seen: set[str] = set()
        for candidate in outputs:
            key = candidate.output.model_dump_json()
            if key not in seen:
                unique.append(candidate)
                seen.add(key)
        return unique, fallback_reason, rejected, review_required, consistency

    def _assemble_letter(
        self,
        profile: MasterProfile,
        posting: JobPosting,
        plan: TailoringPlan,
        recipient: CoverLetterRecipient,
        validated: CoverLetterValidationResult,
        date_text: str | None,
    ) -> CoverLetter:
        return CoverLetter(
            profile_id=profile.id,
            profile_version=profile.version,
            posting_id=posting.id,
            plan_fingerprint=content_fingerprint(plan),
            candidate_name=profile.display_name,
            contact=profile.contact,
            date_text=date_text or date.today().strftime("%B %d, %Y").replace(" 0", " "),
            job_title=posting.title,
            company_name=posting.company_name,
            recipient=recipient,
            salutation=f"Dear {recipient.name}," if recipient.name else "Dear Hiring Manager,",
            paragraphs=validated.paragraphs,
            signoff_name=profile.display_name,
            layout_profile=self._layout_profile,
        )

    def _build_fingerprint_inputs(
        self,
        profile: MasterProfile,
        posting: JobPosting,
        plan: TailoringPlan,
        final_resume: StructuredResume | None,
        research_request: CompanyResearchRequest,
        research: CompanyResearchBundle,
        evidence: list[CoverLetterEvidenceRecord],
        recipient: CoverLetterRecipient,
        explicit_motivation: str | None,
        date_text: str,
    ) -> CoverLetterArtifactFingerprintInputs:
        return CoverLetterArtifactFingerprintInputs(
            reviewed_profile_fingerprint=content_fingerprint(profile),
            posting_fingerprint=content_fingerprint(posting),
            plan_fingerprint=content_fingerprint(plan),
            final_resume_fingerprint=(
                content_fingerprint(final_resume) if final_resume is not None else None
            ),
            research_request_fingerprint=content_fingerprint(research_request),
            research_fingerprint=research.research_fingerprint,
            evidence_fingerprint=content_fingerprint(
                [item.model_dump(mode="json") for item in evidence]
            ),
            recipient_fingerprint=content_fingerprint(recipient),
            date_text=date_text,
            motivation_fingerprint=(
                content_fingerprint(explicit_motivation) if explicit_motivation else None
            ),
            writing_policy_version=COVER_LETTER_WRITING_POLICY_VERSION,
            provider_contract_version=COVER_LETTER_PROVIDER_CONTRACT_VERSION,
            validation_policy_version=COVER_LETTER_VALIDATION_POLICY_VERSION,
            template_identity=COVER_LETTER_TEMPLATE_IDENTITY,
            provider=self._provider_name,
            model=self._model_name,
        )

    def _provider_error_diagnostic(
        self,
        started: float,
        calls: int,
        error: LanguageModelError,
    ) -> CoverLetterProviderDiagnostic:
        fallback = {
            LanguageModelErrorKind.CONFIGURATION: CoverLetterFallbackReason.CREDENTIALS_ABSENT,
            LanguageModelErrorKind.TIMEOUT: CoverLetterFallbackReason.PROVIDER_TIMEOUT,
            LanguageModelErrorKind.RATE_LIMITED: CoverLetterFallbackReason.PROVIDER_RATE_LIMIT,
        }.get(error.kind, CoverLetterFallbackReason.PROVIDER_UNAVAILABLE)
        return self._provider_failure(
            started,
            calls,
            0,
            CoverLetterProviderStatus.REQUEST_FAILED,
            fallback,
            f"Provider failed with typed status {error.kind.value}; deterministic fallback used.",
        )

    def _provider_failure(
        self,
        started: float,
        calls: int,
        repairs: int,
        status: CoverLetterProviderStatus,
        fallback: CoverLetterFallbackReason,
        detail: str,
    ) -> CoverLetterProviderDiagnostic:
        return CoverLetterProviderDiagnostic(
            provider=self._provider_name,
            model=self._model_name,
            status=status,
            request_count=calls,
            repair_count=repairs,
            cache_hit_count=0,
            elapsed_seconds=max(0.0, self._clock() - started),
            fallback_reason=fallback,
            safe_detail=detail,
        )

    @staticmethod
    def _candidate_validation_diagnostic(
        candidate_index: int,
        candidate: _CandidateOutput,
        validated: CoverLetterValidationResult,
        posting: JobPosting,
        recipient: CoverLetterRecipient,
        research: CompanyResearchBundle,
        evidence: list[CoverLetterEvidenceRecord],
        final_resume: StructuredResume | None,
    ) -> CoverLetterCandidateValidationDiagnostic:
        output = candidate.output
        gates = {gate.gate: gate for gate in validated.quality_gates}

        def aggregate(names: set[str]) -> CoverLetterQualityGateStatus:
            statuses = [gates[name].status for name in names if name in gates]
            if CoverLetterQualityGateStatus.FAILED in statuses:
                return CoverLetterQualityGateStatus.FAILED
            if CoverLetterQualityGateStatus.REVIEW_REQUIRED in statuses:
                return CoverLetterQualityGateStatus.REVIEW_REQUIRED
            return CoverLetterQualityGateStatus.PASSED

        failed_gates = [
            gate
            for gate in validated.quality_gates
            if gate.status is CoverLetterQualityGateStatus.FAILED
        ]
        rejected_codes = [code for claim in validated.rejected_claims for code in claim.codes]
        rejected_summaries = [
            *[gate.detail for gate in failed_gates],
            *[claim.detail for claim in validated.rejected_claims],
        ]
        output_evidence_ids = {
            evidence_id
            for paragraph in output.paragraphs
            for evidence_id in paragraph.candidate_evidence_ids
        }
        candidate_payload = output.model_dump_json()
        return CoverLetterCandidateValidationDiagnostic(
            candidate_id=(
                f"cover-candidate:{candidate_index}:"
                f"{sha256(candidate_payload.encode()).hexdigest()[:12]}"
            ),
            candidate_index=candidate_index,
            generation_source=candidate.generation_source,
            paragraph_count=len(output.paragraphs),
            sentence_count=sum(
                len(CoverLetterValidator._sentences(paragraph.text))
                for paragraph in output.paragraphs
            ),
            source_bound_sentence_count=sum(
                len(paragraph.source_bound_sentences)
                for paragraph in output.paragraphs
            ),
            unbound_sentence_count=sum(
                len(CoverLetterValidator._sentences(paragraph.text))
                - len(paragraph.source_bound_sentences)
                for paragraph in output.paragraphs
            ),
            character_count=sum(len(paragraph.text) for paragraph in output.paragraphs),
            posting_fingerprint=content_fingerprint(posting),
            company_name=posting.company_name,
            recipient_company=recipient.company,
            posting_authority_fact_count=sum(
                fact.confidence is CompanyFactConfidence.POSTING_AUTHORITY
                for fact in research.facts
            ),
            verified_company_fact_count=sum(
                fact.confidence
                in {CompanyFactConfidence.VERIFIED, CompanyFactConfidence.USER_AUTHORITY}
                for fact in research.facts
            ),
            selected_evidence_ids=sorted(
                item.id for item in evidence if item.id in output_evidence_ids
            ),
            accepted_resume_narrative_fingerprint=(
                content_fingerprint(final_resume) if final_resume is not None else None
            ),
            structural_validation=aggregate(
                {
                    "generic_language",
                    "narrative_integrity",
                    "paragraph_structure",
                    "posting_reference",
                    "closing_structure",
                }
            ),
            company_validation=aggregate({"company_grounding", "interchangeability"}),
            narrative_validation=aggregate(
                {"narrative_structure", "resume_complement", "resume_consistency"}
            ),
            claim_validation=aggregate({"candidate_grounding"}),
            rejection_codes=list(
                dict.fromkeys([*[gate.code for gate in failed_gates], *rejected_codes])
            ),
            rejection_summaries=list(dict.fromkeys(rejected_summaries)),
            rejected_paragraph_indexes=sorted(
                {
                    claim.paragraph_index
                    for claim in validated.rejected_claims
                    if claim.paragraph_index is not None
                }
            ),
            rejected_sentence_indexes=sorted(
                {
                    claim.sentence_index
                    for claim in validated.rejected_claims
                    if claim.sentence_index is not None
                }
            ),
        )

    def _page_fit_gate(
        self,
        diagnostic: CoverLetterPageFitDiagnostic,
    ) -> CoverLetterQualityGateResult:
        status = diagnostic.status
        balanced = (
            diagnostic.page_count == 1
            and not diagnostic.blank_trailing_page
            and diagnostic.underfill_or_overflow == "balanced_one_page"
        )
        if status is CoverLetterPageFitStatus.PAGINATION_UNVERIFIED:
            gate_status = CoverLetterQualityGateStatus.REVIEW_REQUIRED
            detail = (
                "Exact pagination is unavailable. The rendered DOCX was retained for "
                "review, and manual Word inspection is required before approval."
            )
        elif balanced:
            gate_status = CoverLetterQualityGateStatus.PASSED
            detail = "The selected DOCX is one professionally filled page."
        else:
            gate_status = CoverLetterQualityGateStatus.FAILED
            detail = "The selected DOCX is underfilled, overflowing, or has a blank trailing page."
        return CoverLetterQualityGateResult(
            gate="page_fit",
            status=gate_status,
            code=status.value,
            detail=detail,
        )

    @staticmethod
    def _research_gate(research: CompanyResearchBundle) -> CoverLetterQualityGateResult:
        usable = bool(
            [
                fact
                for fact in research.facts
                if fact.confidence is not CompanyFactConfidence.CONFLICTING
            ]
        )
        if usable:
            status = (
                CoverLetterQualityGateStatus.PASSED
                if research.status is CompanyResearchStatus.VERIFIED
                else CoverLetterQualityGateStatus.REVIEW_REQUIRED
            )
            detail = (
                "Verified official or user-authorized company facts are available."
                if status is CoverLetterQualityGateStatus.PASSED
                else (
                    "Company specificity relies on the validated job posting; research "
                    "limitations remain visible."
                )
            )
        else:
            status = CoverLetterQualityGateStatus.FAILED
            detail = "No verified company or posting fact supports a company-specific connection."
        return CoverLetterQualityGateResult(
            gate="company_research",
            status=status,
            code=research.status.value,
            detail=detail,
        )

    def _timing(self, stage: GenerationStage, started: float) -> StageTiming:
        return StageTiming(
            stage=stage,
            elapsed_seconds=max(0.0, self._clock() - started),
        )

    def _approximate_body_lines(self) -> int:
        usable_points = self._layout_profile.usable_height_inches * 72
        line_height = self._layout_profile.body_size_pt * self._layout_profile.line_spacing
        return max(20, round(usable_points / line_height) - 12)

    @staticmethod
    def _required_content_gates_pass(gates: list[CoverLetterQualityGateResult]) -> bool:
        required = {
            "candidate_grounding",
            "company_grounding",
            "interchangeability",
            "generic_language",
            "narrative_integrity",
            "narrative_structure",
            "resume_complement",
            "paragraph_structure",
            "posting_reference",
            "closing_structure",
            "resume_consistency",
        }
        return not any(
            gate.gate in required and gate.status is CoverLetterQualityGateStatus.FAILED
            for gate in gates
        )

    @staticmethod
    def _purpose_order(paragraph: CoverLetterDraftParagraph) -> int:
        order = {
            CoverLetterParagraphPurpose.OPENING: 0,
            CoverLetterParagraphPurpose.EXPERIENCE_CONNECTION: 1,
            CoverLetterParagraphPurpose.CONTRIBUTION: 2,
            CoverLetterParagraphPurpose.ROLE_FIT: 3,
            CoverLetterParagraphPurpose.CLOSING: 4,
        }
        return order[paragraph.purpose]

    @staticmethod
    def _resume_evidence_ids(final_resume: StructuredResume | None) -> set[str]:
        if final_resume is None:
            return set()
        return {
            evidence_id
            for bullets in [
                *final_resume.experience_bullets.values(),
                *final_resume.project_bullets.values(),
            ]
            for bullet in bullets
            for evidence_id in bullet.evidence_ids
        }

    @staticmethod
    def _provider_cache_key(request: CoverLetterDraftRequest) -> str:
        payload = request.model_dump(mode="json", exclude={"repair_instruction"})
        return sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @staticmethod
    def _artifact_fingerprint(inputs: CoverLetterArtifactFingerprintInputs) -> str:
        return sha256(
            json.dumps(
                inputs.model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

    @staticmethod
    def _validate_inputs(
        profile: MasterProfile,
        posting: JobPosting,
        plan: TailoringPlan,
    ) -> None:
        if plan.profile_id != profile.id or plan.profile_version != profile.version:
            raise CoverLetterValidationError("Tailoring plan does not match the reviewed profile")
        if plan.posting_id != posting.id or plan.posting != posting:
            raise CoverLetterValidationError("Tailoring plan does not match the active posting")
        if plan.strategy is None:
            raise CoverLetterValidationError("A validated resume strategy is required")

    def _aware_now(self) -> datetime:
        value = self._now()
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


__all__ = [
    "CoverLetterPageFitError",
    "CoverLetterService",
    "CoverLetterValidationError",
]
