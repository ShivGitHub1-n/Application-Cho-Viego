from __future__ import annotations

from pathlib import Path

from resume_tailor.application.cover_letter import CoverLetterService, CoverLetterValidationError
from resume_tailor.domain.cover_letter import CoverLetterRecipient
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


def _response(*, confidence="explicitly_supported", purpose="evidence", compact=False):
    return CoverLetterDraftResult(
        metadata=_metadata(),
        output=CoverLetterDraftOutput(
            paragraphs=[
                CoverLetterDraftParagraph(
                    purpose="opening",
                    text="I am applying for the Embedded Firmware Intern role at Example Robotics.",
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
