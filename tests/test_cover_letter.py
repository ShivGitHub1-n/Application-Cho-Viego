from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from resume_tailor.application.cover_letter import (
    CoverLetterCandidateRejectionError,
    CoverLetterService,
    CoverLetterValidationError,
)
from resume_tailor.application.cover_letter_validation import DeterministicCoverLetterComposer
from resume_tailor.application.llm_prompts import task_prompt
from resume_tailor.application.workflow_state import get_active_posting
from resume_tailor.domain.cover_letter import (
    CoverLetterFallbackReason,
    CoverLetterParagraphPurpose,
    CoverLetterProviderStatus,
    CoverLetterQualityGateStatus,
    CoverLetterReviewState,
)
from resume_tailor.domain.generated_artifact import GenerationStage
from resume_tailor.domain.llm_models import (
    CoverLetterDraftOutput,
    CoverLetterDraftParagraph,
    LanguageModelError,
    LanguageModelErrorKind,
    LlmOperation,
)
from tests.cover_letter_helpers import (
    ControlledCoverLetterRenderer,
    cover_letter_case,
    provider_result,
    recipient,
    rich_cover_letter_case,
)
from tests.fakes import FakeResumeLanguageModel


def test_minimal_provider_request_reuses_ranked_reviewed_evidence() -> None:
    profile, posting, plan = cover_letter_case()
    service = CoverLetterService()

    request = service.create_request(profile, posting, plan)

    assert 1 <= len(request.selected_evidence) <= 4
    assert set(item.evidence_id for item in request.selected_evidence) <= {
        item.id for item in profile.evidence
    }
    assert request.company_research
    assert not hasattr(request, "diagnostics")
    assert not hasattr(request, "docx_formatting")


def test_all_candidate_rejection_reports_validator_separation_and_stays_fatal() -> None:
    profile, posting, plan = rich_cover_letter_case()

    class UnsupportedCandidateComposer:
        @staticmethod
        def _reject(
            output: CoverLetterDraftOutput,
            company_name: str,
        ) -> CoverLetterDraftOutput:
            paragraphs = list(output.paragraphs)
            paragraph = paragraphs[0]
            rejected_text = (
                f"{company_name} operates an unsupported CUDA production fleet. "
                "I built STM32 firmware."
            )
            if paragraph.source_bound_sentences:
                sentences = list(paragraph.source_bound_sentences)
                sentences[-1] = sentences[-1].model_copy(update={"text": rejected_text})
                paragraphs[0] = paragraph.model_copy(
                    update={
                        "text": " ".join(sentence.text for sentence in sentences),
                        "source_bound_sentences": sentences,
                    }
                )
            else:
                paragraphs[0] = paragraph.model_copy(update={"text": rejected_text})
            return output.model_copy(update={"paragraphs": paragraphs})

        def variants(self, evidence, research, active_posting):
            outputs = DeterministicCoverLetterComposer().variants(
                evidence, research, active_posting
            )
            return [
                self._reject(output, active_posting.company_name or "Example Robotics")
                for output in outputs
            ]

        def source_bound_fallback(self, evidence, research, active_posting):
            output = DeterministicCoverLetterComposer().source_bound_fallback(
                evidence, research, active_posting
            )
            return self._reject(
                output,
                active_posting.company_name or "Example Robotics",
            )

    renderer = ControlledCoverLetterRenderer([0.94])
    service = CoverLetterService(
        renderer=renderer,
        deterministic_composer=UnsupportedCandidateComposer(),
    )

    with pytest.raises(CoverLetterCandidateRejectionError) as captured:
        service.generate_artifact(profile, posting, plan, recipient=recipient(posting))

    diagnostics = captured.value.diagnostics
    assert len(diagnostics) >= 2
    assert all(
        diagnostic.claim_validation is CoverLetterQualityGateStatus.FAILED
        for diagnostic in diagnostics
    )
    assert all(
        "company_fact_not_verified" in diagnostic.rejection_codes for diagnostic in diagnostics
    )
    assert all(diagnostic.rejected_paragraph_indexes == [0] for diagnostic in diagnostics)
    assert all(not diagnostic.rendering_attempted for diagnostic in diagnostics)
    assert "candidate 1" in str(captured.value)
    assert renderer.render_calls == 0


def test_source_bound_fallback_is_used_only_after_richer_candidates_fail() -> None:
    profile, posting, plan = rich_cover_letter_case()

    class RichCandidatesRejectedComposer(DeterministicCoverLetterComposer):
        def variants(self, evidence, research, active_posting):
            outputs = super().variants(evidence, research, active_posting)
            rejected = []
            for output in outputs:
                paragraphs = list(output.paragraphs)
                paragraphs[0] = paragraphs[0].model_copy(
                    update={
                        "text": (
                            f"{active_posting.description} This copied posting language "
                            "does not form a grounded connection."
                        )
                    }
                )
                rejected.append(output.model_copy(update={"paragraphs": paragraphs}))
            return rejected

    renderer = ControlledCoverLetterRenderer([0.94])
    service = CoverLetterService(
        renderer=renderer,
        deterministic_composer=RichCandidatesRejectedComposer(),
    )

    artifact = service.generate_artifact(
        profile,
        posting,
        plan,
        recipient=recipient(posting),
    )

    source_bound = next(
        diagnostic
        for diagnostic in artifact.candidate_validations
        if diagnostic.generation_source == "deterministic:source_bound_fallback"
    )
    assert source_bound.structural_validation is CoverLetterQualityGateStatus.PASSED
    assert source_bound.company_validation is CoverLetterQualityGateStatus.PASSED
    assert source_bound.narrative_validation is CoverLetterQualityGateStatus.PASSED
    assert source_bound.claim_validation is CoverLetterQualityGateStatus.PASSED
    assert source_bound.source_bound_sentence_count == source_bound.sentence_count
    assert source_bound.unbound_sentence_count == 0
    assert source_bound.rendering_attempted
    # A source-bound emergency letter uses only the viable evidence threads. It
    # must not invent or reopen a weak third story merely to satisfy a fixed
    # paragraph count.
    assert 4 <= len(artifact.letter.paragraphs) <= 5
    assert all(paragraph.sentence_authorities for paragraph in artifact.letter.paragraphs)
    assert all(
        sentence.posting_fact_ids
        or sentence.candidate_evidence_ids
        or sentence.verified_company_fact_ids
        or sentence.canonical_metadata
        for paragraph in artifact.letter.paragraphs
        for sentence in paragraph.sentence_authorities
    )
    assert artifact.ready_for_review


def test_cover_letter_prompt_requires_coherent_grounded_narrative() -> None:
    profile, posting, plan = cover_letter_case()
    request = CoverLetterService().create_request(profile, posting, plan)

    prompt = task_prompt(LlmOperation.COVER_LETTER_DRAFT, request)

    assert "why this company" in prompt.casefold()
    assert "authorized candidate evidence IDs" in prompt
    assert "company research IDs" in prompt
    assert "Do not return diagnostics" in prompt
    assert "first sentence worth reading" in prompt.casefold()
    assert "each paragraph reveal something new" in prompt.casefold()
    assert "grammatically awkward" in prompt.casefold()
    assert "corporate ai rhythm" in prompt.casefold()


def test_paragraph_purpose_normalizes_legacy_names_but_rejects_unknown() -> None:
    paragraph = CoverLetterDraftParagraph(
        purpose="  OPENING ",
        text="A specific technical opening.",
    )
    assert paragraph.purpose is CoverLetterParagraphPurpose.OPENING
    with pytest.raises(ValidationError, match="Unsupported paragraph purpose"):
        CoverLetterDraftParagraph(
            purpose="company praise and enthusiasm",
            text="Generic prose.",
        )


def test_no_provider_builds_reviewable_deterministic_artifact() -> None:
    profile, posting, plan = cover_letter_case()
    renderer = ControlledCoverLetterRenderer([0.90])
    service = CoverLetterService(renderer=renderer)

    artifact = service.generate_artifact(profile, posting, plan)

    assert artifact.review_state is CoverLetterReviewState.GENERATED_AWAITING_REVIEW
    assert artifact.provider_diagnostic.status is CoverLetterProviderStatus.DISABLED
    assert (
        artifact.provider_diagnostic.fallback_reason is CoverLetterFallbackReason.PROVIDER_DISABLED
    )
    assert artifact.page_fit.estimated_utilization == 0.90
    assert artifact.page_fit.preferred_density_reachable
    assert artifact.call_counts.provider_calls == 0
    assert artifact.call_counts.research_network_requests == 0
    assert artifact.docx_bytes.startswith(b"PK\x03\x04")
    stages = {timing.stage for timing in artifact.stage_timings}
    assert {
        GenerationStage.COVER_LETTER_QUALITY_GATES,
        GenerationStage.DOCX_RENDERING,
        GenerationStage.COVER_LETTER_PAGE_FIT,
        GenerationStage.GENERATED_ARTIFACT_STORAGE,
    } <= stages


def test_absent_credentials_exposes_typed_fallback() -> None:
    profile, posting, plan = cover_letter_case()
    service = CoverLetterService(
        renderer=ControlledCoverLetterRenderer([0.94]),
        provider_name="gemini",
        model_name="configured-model",
        provider_unavailable_reason="GEMINI_API_KEY is missing.",
    )

    artifact = service.generate_artifact(profile, posting, plan)

    assert (
        artifact.provider_diagnostic.status is CoverLetterProviderStatus.CONFIGURATION_UNAVAILABLE
    )
    assert (
        artifact.provider_diagnostic.fallback_reason is CoverLetterFallbackReason.CREDENTIALS_ABSENT
    )
    assert artifact.provider_diagnostic.request_count == 0


def test_provider_response_is_cached_without_duplicate_request() -> None:
    profile, posting, plan = cover_letter_case()
    fake = FakeResumeLanguageModel(draft_cover_letter=provider_result(profile, posting, plan))
    service = CoverLetterService(
        language_model=fake,
        renderer=ControlledCoverLetterRenderer([0.94]),
        provider_name="fake",
        model_name="fake-model",
    )

    first = service.generate_artifact(profile, posting, plan, date_text="July 21, 2026")
    second = service.generate_artifact(profile, posting, plan, date_text="July 22, 2026")

    assert first is not second
    assert fake.calls["draft_cover_letter"] == 1
    assert second.provider_diagnostic.status is CoverLetterProviderStatus.CACHE_HIT


def test_one_repair_is_allowed_only_for_malformed_output() -> None:
    profile, posting, plan = cover_letter_case()
    malformed = LanguageModelError(LanguageModelErrorKind.MALFORMED_RESPONSE, "bad json")
    result = provider_result(profile, posting, plan)
    fake = FakeResumeLanguageModel(draft_cover_letter=[malformed, result])
    service = CoverLetterService(
        language_model=fake,
        renderer=ControlledCoverLetterRenderer([0.94]),
    )

    artifact = service.generate_artifact(profile, posting, plan)

    assert fake.calls["draft_cover_letter"] == 2
    assert artifact.provider_diagnostic.repair_count == 1
    repair_request = fake.requests["draft_cover_letter"][1]
    assert repair_request.repair_instruction


def test_semantically_invalid_typed_output_uses_local_fallback_without_repair() -> None:
    profile, posting, plan = cover_letter_case()
    result = provider_result(profile, posting, plan)
    paragraphs = list(result.output.paragraphs)
    paragraphs[0] = paragraphs[0].model_copy(
        update={"text": "I am thrilled to apply for this exciting opportunity."}
    )
    for index in range(1, len(paragraphs) - 1):
        paragraphs[index] = paragraphs[index].model_copy(
            update={"text": "I deployed CUDA globally in production for millions of users."}
        )
    paragraphs[-1] = paragraphs[-1].model_copy(
        update={"text": "I look forward to the opportunity to make a meaningful impact."}
    )
    invalid = result.model_copy(
        update={"output": result.output.model_copy(update={"paragraphs": paragraphs})}
    )
    fake = FakeResumeLanguageModel(draft_cover_letter=invalid)
    service = CoverLetterService(
        language_model=fake,
        renderer=ControlledCoverLetterRenderer([0.94]),
    )

    artifact = service.generate_artifact(profile, posting, plan)

    assert fake.calls["draft_cover_letter"] == 1
    assert artifact.provider_diagnostic.repair_count == 0
    assert artifact.provider_diagnostic.status is CoverLetterProviderStatus.VALIDATION_FALLBACK
    assert (
        artifact.provider_diagnostic.fallback_reason
        is CoverLetterFallbackReason.ALL_PARAGRAPHS_REJECTED
    )


@pytest.mark.parametrize(
    ("kind", "fallback"),
    [
        (LanguageModelErrorKind.TIMEOUT, CoverLetterFallbackReason.PROVIDER_TIMEOUT),
        (LanguageModelErrorKind.RATE_LIMITED, CoverLetterFallbackReason.PROVIDER_RATE_LIMIT),
    ],
)
def test_provider_timeout_or_rate_limit_falls_back_once(
    kind: LanguageModelErrorKind,
    fallback: CoverLetterFallbackReason,
) -> None:
    profile, posting, plan = cover_letter_case()
    fake = FakeResumeLanguageModel(
        draft_cover_letter=LanguageModelError(kind, "provider unavailable")
    )
    service = CoverLetterService(
        language_model=fake,
        renderer=ControlledCoverLetterRenderer([0.94]),
    )

    artifact = service.generate_artifact(profile, posting, plan)

    assert fake.calls["draft_cover_letter"] == 1
    assert artifact.provider_diagnostic.fallback_reason is fallback


def test_approval_and_download_reuse_exact_stored_bytes_with_zero_generation_calls() -> None:
    profile, posting, plan = cover_letter_case()
    renderer = ControlledCoverLetterRenderer([0.94])
    service = CoverLetterService(renderer=renderer)
    artifact = service.generate_artifact(profile, posting, plan)
    approved = service.approve_artifact(
        artifact,
        expected_fingerprint=artifact.artifact_fingerprint,
    )
    render_calls = renderer.render_calls

    download = service.prepare_download(
        approved,
        expected_fingerprint=approved.artifact_fingerprint,
    )

    assert download.docx_bytes == approved.docx_bytes
    assert download.generation_call_counts.provider_calls == 0
    assert download.generation_call_counts.research_calls == 0
    assert download.generation_call_counts.claim_validations == 0
    assert download.generation_call_counts.docx_renders == 0
    assert download.generation_call_counts.pagination_attempts == 0
    assert renderer.render_calls == render_calls
    assert service.mark_downloaded(approved).review_state is CoverLetterReviewState.DOWNLOADED


def test_stale_or_unapproved_artifact_cannot_download() -> None:
    profile, posting, plan = cover_letter_case()
    service = CoverLetterService(renderer=ControlledCoverLetterRenderer([0.94]))
    artifact = service.generate_artifact(profile, posting, plan)
    with pytest.raises(CoverLetterValidationError, match="Approve"):
        service.prepare_download(
            artifact,
            expected_fingerprint=artifact.artifact_fingerprint,
        )
    stale = artifact.model_copy(update={"current": False})
    with pytest.raises(CoverLetterValidationError, match="stale"):
        service.prepare_download(
            stale,
            expected_fingerprint=stale.artifact_fingerprint,
        )


def test_severely_underfilled_failed_candidate_cannot_be_approved_or_downloaded() -> None:
    profile, posting, plan = cover_letter_case()
    service = CoverLetterService(renderer=ControlledCoverLetterRenderer([0.48]))

    failed = service.generate_artifact(profile, posting, plan)

    assert failed.page_fit.estimated_utilization == 0.48
    assert not failed.ready_for_review
    assert failed.review_state is CoverLetterReviewState.GENERATION_FAILED
    with pytest.raises(CoverLetterValidationError, match="failed quality gates"):
        service.approve_artifact(
            failed,
            expected_fingerprint=failed.artifact_fingerprint,
        )

    forged_approval = failed.model_copy(
        update={"review_state": CoverLetterReviewState.APPROVED}
    )
    with pytest.raises(CoverLetterValidationError, match="production eligibility"):
        service.prepare_download(
            forged_approval,
            expected_fingerprint=forged_approval.artifact_fingerprint,
        )
    with pytest.raises(CoverLetterValidationError, match="production eligibility"):
        service.mark_downloaded(forged_approval)


def test_changed_date_or_recipient_invalidates_current_artifact() -> None:
    profile, posting, plan = cover_letter_case()
    service = CoverLetterService(renderer=ControlledCoverLetterRenderer([0.94]))
    request = service.default_research_request(posting)
    current_recipient = recipient(posting)
    artifact = service.generate_artifact(
        profile,
        posting,
        plan,
        recipient=current_recipient,
        research_request=request,
        date_text="July 21, 2026",
    )

    assert service.artifact_is_current(
        artifact,
        profile,
        posting,
        plan,
        recipient=current_recipient,
        final_resume=None,
        research_request=request,
        explicit_motivation=None,
        date_text="July 21, 2026",
    )
    assert not service.artifact_is_current(
        artifact,
        profile,
        posting,
        plan,
        recipient=current_recipient,
        final_resume=None,
        research_request=request,
        explicit_motivation=None,
        date_text="July 22, 2026",
    )


def test_streamlit_rerun_uses_authoritative_active_posting() -> None:
    _profile, posting, _plan = cover_letter_case()
    assert get_active_posting({"posting": posting}) is posting


def test_renderer_protocol_does_not_require_output_path_persistence(tmp_path: Path) -> None:
    profile, posting, plan = cover_letter_case()
    renderer = ControlledCoverLetterRenderer([0.94])
    artifact = CoverLetterService(renderer=renderer).generate_artifact(profile, posting, plan)
    assert artifact.docx_bytes
    assert not list(tmp_path.iterdir())
