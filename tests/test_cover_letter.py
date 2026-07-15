from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from resume_tailor.application.cover_letter import CoverLetterService, CoverLetterValidationError
from resume_tailor.application.llm_prompts import task_prompt
from resume_tailor.application.workflow_state import get_active_posting
from resume_tailor.domain.cover_letter import CoverLetterParagraphPurpose, CoverLetterRecipient
from resume_tailor.domain.llm_models import (
    CoverLetterDraftClaim,
    CoverLetterDraftOutput,
    CoverLetterDraftParagraph,
    CoverLetterDraftResult,
    LlmOperation,
    ModelCallMetadata,
)
from resume_tailor.domain.models import EntityKind, EvidenceItem, JobPosting, MasterProfile, ResumeItem, TemplateConstraints
from resume_tailor.infrastructure.cover_letter_rendering import CoverLetterRenderResult
from resume_tailor.infrastructure.rendering import PageCountMeasurement
from resume_tailor.infrastructure.optimization import DeterministicResumeOptimizer
from tests.fakes import FakeResumeLanguageModel


def _metadata() -> ModelCallMetadata:
    return ModelCallMetadata(provider="fake", model="fake", operation=LlmOperation.COVER_LETTER_DRAFT, latency_ms=1)


def _fixture():
    profile = MasterProfile(
        id="cover-profile",
        user_id="user",
        display_name="Candidate Name",
        contact={"location": "Toronto, ON", "email": "candidate@example.com", "links": ["https://github.com/candidate"]},
        experiences=[ResumeItem(id="entry-1", title="Firmware Intern", kind=EntityKind.EXPERIENCE)],
        evidence=[
            EvidenceItem(
                id="evidence-1",
                entity_id="entry-1",
                source_text="Developed STM32 firmware and validated SPI sensor communication at 30 FPS.",
                technologies=["STM32", "SPI"],
                outcomes=["30 FPS"],
            )
        ],
    )
    posting = JobPosting(id="cover-posting", title="Embedded Firmware Intern", company_name="Example Robotics", description="Develop STM32 firmware and validate sensors.")
    plan = DeterministicResumeOptimizer().create_plan(profile, posting, TemplateConstraints(max_experience_lines=4))
    return profile, posting, plan


def _response(
    *,
    confidence="explicitly_supported",
    purpose="evidence",
    compact=False,
    role="Embedded Firmware Intern",
    company="Example Robotics",
):
    return CoverLetterDraftResult(
        metadata=_metadata(),
        output=CoverLetterDraftOutput(
            paragraphs=[
                CoverLetterDraftParagraph(
                    purpose="introduction",
                    text=f"I am applying for the {role} role at {company}.",
                    claims=[CoverLetterDraftClaim(text="I am applying for the role.", evidence_ids=["evidence-1"], confidence="explicitly_supported")],
                ),
                CoverLetterDraftParagraph(
                    purpose=purpose,
                    text=("My firmware and sensor validation experience would help me contribute to this work." if not compact else "My firmware experience supports this work."),
                    claims=[CoverLetterDraftClaim(text="Developed firmware and validated sensors.", evidence_ids=["evidence-1"], confidence=confidence, optional=True, reduction_priority=10)],
                    optional=True,
                    reduction_priority=10,
                ),
                CoverLetterDraftParagraph(purpose="closing", text="I would welcome the opportunity to discuss my fit for the role."),
            ]
        ),
    )


class _FakeRenderer:
    def __init__(self, counts: list[int]):
        self.counts = counts
        self.calls = 0

    def render_candidate(self, letter, output_directory: Path) -> CoverLetterRenderResult:
        self.calls += 1
        path = Path(output_directory) / "cover-letter.docx"
        path.write_bytes(b"docx")
        measurement = PageCountMeasurement(self.counts.pop(0), "fake", "exact", True)
        return CoverLetterRenderResult(path, measurement)


def test_request_reuses_selected_plan_evidence_and_draft_is_cached() -> None:
    profile, posting, plan = _fixture()
    fake = FakeResumeLanguageModel(draft_cover_letter=_response())
    service = CoverLetterService(fake)
    request = service.create_request(profile, posting, plan)
    assert request.selected_entry_ids == ["entry-1"]
    assert [item.evidence_id for item in request.selected_evidence] == ["evidence-1"]
    service.draft(profile, posting, plan)
    service.draft(profile, posting, plan)
    assert fake.calls["draft_cover_letter"] == 1


def test_canonical_introduction_purpose_is_accepted() -> None:
    profile, posting, plan = _fixture()
    service = CoverLetterService(FakeResumeLanguageModel(draft_cover_letter=_response()))

    letter = service.draft(profile, posting, plan)

    assert letter.paragraphs[0].purpose == CoverLetterParagraphPurpose.INTRODUCTION
    assert "Embedded Firmware Intern" in letter.paragraphs[0].text
    assert "Example Robotics" in letter.paragraphs[0].text


def test_cover_letter_prompt_requires_machine_readable_purposes() -> None:
    profile, posting, plan = _fixture()
    service = CoverLetterService(FakeResumeLanguageModel(draft_cover_letter=_response()))

    prompt = task_prompt(LlmOperation.COVER_LETTER_DRAFT, service.create_request(profile, posting, plan))

    assert "introduction, evidence, closing" in prompt
    assert "role-specific or company-specific descriptions in paragraph text" in prompt


@pytest.mark.parametrize(
    ("role", "company"),
    [("Robotics Co-op", "Northstar Automation"), ("Controls Engineer", "Harbor Systems")],
)
def test_role_and_company_variation_does_not_change_introduction_purpose(role: str, company: str) -> None:
    profile, posting, plan = _fixture()
    response = _response(role=role, company=company)
    service = CoverLetterService(FakeResumeLanguageModel(draft_cover_letter=response))

    letter = service.draft(profile, posting, plan)

    assert letter.paragraphs[0].purpose == CoverLetterParagraphPurpose.INTRODUCTION
    assert role in letter.paragraphs[0].text
    assert company in letter.paragraphs[0].text


def test_evidence_and_closing_purposes_remain_canonical() -> None:
    profile, posting, plan = _fixture()
    service = CoverLetterService(FakeResumeLanguageModel(draft_cover_letter=_response()))

    letter = service.draft(profile, posting, plan)

    assert letter.paragraphs[1].purpose == CoverLetterParagraphPurpose.EVIDENCE
    assert letter.paragraphs[-1].purpose == CoverLetterParagraphPurpose.CLOSING


def test_former_opening_identifier_normalizes_deterministically() -> None:
    paragraph = CoverLetterDraftParagraph(
        purpose="  OPENING ",
        text="I am applying for this role.",
    )

    assert paragraph.purpose == CoverLetterParagraphPurpose.INTRODUCTION


def test_unknown_paragraph_purpose_is_rejected_by_typed_schema() -> None:
    with pytest.raises(ValidationError, match="Unsupported paragraph purpose"):
        CoverLetterDraftParagraph(
            purpose="Introduction and interest in any role",
            text="I am applying for this role.",
        )


def test_streamlit_style_rerun_uses_authoritative_posting_for_drafting() -> None:
    profile, posting, plan = _fixture()
    session_state: dict[str, object] = {"posting": posting}
    service = CoverLetterService(FakeResumeLanguageModel(draft_cover_letter=_response()))

    rerun_posting = get_active_posting(session_state)
    assert rerun_posting is posting
    letter = service.draft(profile, rerun_posting, plan)

    assert letter.posting_id == posting.id
    assert letter.job_title == posting.title


def test_strong_inference_requires_review_and_rejection_is_excluded(tmp_path: Path) -> None:
    profile, posting, plan = _fixture()
    fake = FakeResumeLanguageModel(draft_cover_letter=_response(confidence="strongly_implied"))
    service = CoverLetterService(fake)
    letter = service.draft(profile, posting, plan)
    assert len(letter.pending_claims) == 1
    reviewed = service.approve(letter, set(), reviewed=True)
    assert not reviewed.pending_claims
    renderer = _FakeRenderer([1])
    export_service = CoverLetterService(fake, renderer=renderer)
    export_service._contexts[letter.plan_fingerprint] = (profile, posting, plan, None, letter.date_text)
    exported = export_service.export(reviewed, tmp_path)
    assert exported.page_count == 1


def test_overlong_letter_reduces_without_second_draft_call(tmp_path: Path) -> None:
    profile, posting, plan = _fixture()
    fake = FakeResumeLanguageModel(draft_cover_letter=_response())
    renderer = _FakeRenderer([2, 1])
    service = CoverLetterService(fake, renderer=renderer)
    letter = service.approve(service.draft(profile, posting, plan), set(), reviewed=True)
    exported = service.export(letter, tmp_path)
    assert exported.page_count == 1
    assert fake.calls["draft_cover_letter"] == 1


def test_unsupported_claim_is_rejected_before_export() -> None:
    profile, posting, plan = _fixture()
    fake = FakeResumeLanguageModel(draft_cover_letter=_response(confidence="unsupported"))
    service = CoverLetterService(fake)
    try:
        service.draft(profile, posting, plan)
    except CoverLetterValidationError as error:
        assert "Unsupported claim" in str(error)
    else:
        raise AssertionError("Unsupported cover-letter claim was accepted")
