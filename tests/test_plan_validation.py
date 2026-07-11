import pytest

from resume_tailor.application.llm_services import HybridLlmServices
from resume_tailor.application.plan_validation import PlanIntegrityError
from resume_tailor.application.services import TailorResumeService
from resume_tailor.domain.models import (
    ClaimCandidate,
    ClaimComposition,
    ClaimSupport,
    EntityKind,
    EvidenceItem,
    JobPosting,
    MasterProfile,
    ResumeItem,
    TailoringPlan,
    TemplateConstraints,
)
from resume_tailor.infrastructure.optimization import (
    DeterministicResumeOptimizer,
    EvidenceBoundResumeWriter,
)
from tests.fakes import FakeResumeLanguageModel


def _profile() -> MasterProfile:
    return MasterProfile(
        id="profile-integrity",
        user_id="user-integrity",
        display_name="Candidate",
        experiences=[
            ResumeItem(id="entry-1", title="Firmware Intern", kind=EntityKind.EXPERIENCE),
            ResumeItem(id="entry-2", title="Software Intern", kind=EntityKind.EXPERIENCE),
        ],
        evidence=[
            EvidenceItem(
                id="evidence-1",
                entity_id="entry-1",
                source_text="Developed STM32 firmware for SPI sensor integration.",
                technologies=["STM32", "SPI"],
            ),
            EvidenceItem(
                id="evidence-2",
                entity_id="entry-2",
                source_text="Built Python ETL automation for analytics data.",
                technologies=["Python"],
            ),
        ],
    )


def _service_and_plan() -> tuple[TailorResumeService, MasterProfile, TailoringPlan]:
    service = TailorResumeService(DeterministicResumeOptimizer(), EvidenceBoundResumeWriter())
    profile = _profile()
    posting = JobPosting(
        id="posting-integrity",
        title="Embedded Firmware Intern",
        description="Develop STM32 firmware and integrate SPI sensors.",
    )
    plan = service.create_plan(profile, posting, TemplateConstraints(max_experience_lines=6))
    return service, profile, plan


def _replacement_candidate(plan: TailoringPlan, **updates: object) -> TailoringPlan:
    candidate = plan.claim_candidates[0]
    return plan.model_copy(update={"claim_candidates": [candidate.model_copy(update=updates)]})


def test_unknown_evidence_id_is_rejected() -> None:
    service, profile, plan = _service_and_plan()
    invalid = _replacement_candidate(plan, evidence_ids=["unknown-evidence"])

    with pytest.raises(PlanIntegrityError, match="unknown candidate evidence ID"):
        service.build_document(invalid, profile, set())


def test_invalid_plan_fails_before_llm_rewrite() -> None:
    _, profile, plan = _service_and_plan()
    fake = FakeResumeLanguageModel()
    hybrid = HybridLlmServices(fake, 1, 4, False, False, True)
    service = TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
        hybrid_services=hybrid,
    )
    invalid = _replacement_candidate(plan, evidence_ids=["unknown-evidence"])

    with pytest.raises(PlanIntegrityError):
        service.build_document(invalid, profile, set())

    assert fake.calls["rewrite_bullets"] == 0


def test_evidence_assigned_to_wrong_entry_is_rejected() -> None:
    service, profile, plan = _service_and_plan()
    invalid = _replacement_candidate(plan, entity_id="entry-2")

    with pytest.raises(PlanIntegrityError, match="belongs to entry-1, not entry-2"):
        service.build_document(invalid, profile, set())


def test_fabricated_entity_id_is_rejected() -> None:
    service, profile, plan = _service_and_plan()
    invalid = _replacement_candidate(plan, entity_id="fabricated-entry")

    with pytest.raises(PlanIntegrityError, match="unknown candidate entity ID"):
        service.build_document(invalid, profile, set())


def test_cross_entry_evidence_group_is_rejected() -> None:
    service, profile, plan = _service_and_plan()
    invalid = _replacement_candidate(
        plan,
        evidence_ids=["evidence-1", "evidence-2"],
        composition=ClaimComposition.COMBINED,
    )

    with pytest.raises(PlanIntegrityError, match="evidence evidence-2 belongs to entry-2"):
        service.build_document(invalid, profile, set())


def test_fabricated_direct_support_is_rejected() -> None:
    service, profile, plan = _service_and_plan()
    fabricated = ClaimCandidate(
        id="fabricated-claim",
        entity_id="entry-2",
        text="Led a production data platform.",
        evidence_ids=["evidence-2"],
        support=ClaimSupport.DIRECT,
        estimated_lines=1,
    )
    invalid = plan.model_copy(
        update={
            "selected_entity_ids": [*plan.selected_entity_ids, "entry-2"],
            "selected_claim_ids": [*plan.selected_claim_ids, fabricated.id],
            "claim_candidates": [*plan.claim_candidates, fabricated],
        }
    )

    with pytest.raises(PlanIntegrityError, match="deterministic server reconstruction"):
        service.build_document(invalid, profile, set())


def test_valid_streamlit_generated_plan_still_builds() -> None:
    service, profile, plan = _service_and_plan()

    resume = service.build_document(plan, profile, set())

    assert resume.profile_id == profile.id
    assert any(resume.experience_bullets.values())
