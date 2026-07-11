import pytest

from resume_tailor.application.composition import (
    CompositionReconciliationError,
    DeterministicCompositionReconciler,
)
from resume_tailor.application.llm_services import HybridLlmServices
from resume_tailor.application.services import TailorResumeService
from resume_tailor.domain.llm_models import (
    CompositionRecommendationOutput,
    CompositionRecommendationResult,
    EvidenceGrouping,
    LanguageModelError,
    LanguageModelErrorKind,
    LlmOperation,
)
from resume_tailor.domain.models import (
    ClaimSupport,
    CompositionEvidenceGroup,
    CompositionSelection,
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
from tests.fakes import FakeResumeLanguageModel, metadata


def _inputs() -> tuple[MasterProfile, JobPosting, TailoringPlan]:
    profile = MasterProfile(
        id="profile-composition",
        user_id="user-composition",
        display_name="Candidate",
        experiences=[ResumeItem(id="firmware", title="Firmware Intern", kind=EntityKind.EXPERIENCE)],
        evidence=[
            EvidenceItem(
                id="firmware-1",
                entity_id="firmware",
                source_text="Developed STM32 firmware for sensor interfaces.",
                technologies=["STM32"],
            ),
            EvidenceItem(
                id="firmware-2",
                entity_id="firmware",
                source_text="Validated SPI hardware integration during debugging.",
                technologies=["SPI"],
            ),
            EvidenceItem(
                id="unconfirmed",
                entity_id="firmware",
                source_text="Led production firmware architecture.",
                confirmed=False,
            ),
        ],
    )
    posting = JobPosting(
        id="posting-composition",
        title="Embedded Firmware Intern",
        description="Develop STM32 firmware and validate SPI hardware interfaces.",
    )
    plan = DeterministicResumeOptimizer().create_plan(
        profile,
        posting,
        TemplateConstraints(max_total_lines=8, max_experience_lines=8),
    )
    return profile, posting, plan


def _result(*, evidence_ids: list[str], groups: list[EvidenceGrouping] | None = None):
    return CompositionRecommendationResult(
        metadata=metadata(LlmOperation.RECOMMEND_COMPOSITION),
        output=CompositionRecommendationOutput(
            selected_entry_ids=["firmware"],
            selected_evidence_ids=evidence_ids,
            proposed_evidence_groupings=groups or [],
            rationale="Prefer the strongest focused evidence.",
        ),
    )


def _hybrid(fake: FakeResumeLanguageModel, retry_count: int = 0) -> HybridLlmServices:
    return HybridLlmServices(fake, retry_count, 4, False, True, False)


def test_valid_composition_changes_plan_and_final_document() -> None:
    profile, posting, plan = _inputs()
    fake = FakeResumeLanguageModel(recommend_composition=_result(evidence_ids=["firmware-2"]))
    hybrid = _hybrid(fake)
    service = TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
        hybrid_services=hybrid,
    )

    reconciled = service.create_plan(profile, posting, plan.constraints)
    resume = service.build_document(reconciled, profile, set())

    assert reconciled.selected_claim_ids == ["firmware-2"]
    assert [bullet.id for bullet in resume.experience_bullets["firmware"]] == ["firmware-2"]
    assert any(decision.action == "composition_applied" for decision in reconciled.report.decisions)


def test_invalid_and_failed_composition_preserve_deterministic_plan() -> None:
    profile, posting, plan = _inputs()
    invalid = _result(evidence_ids=["unknown-evidence"])
    failure = LanguageModelError(LanguageModelErrorKind.UNAVAILABLE, "unavailable")
    for response in (invalid, failure):
        fake = FakeResumeLanguageModel(recommend_composition=response)
        enriched = _hybrid(fake).enrich_plan(plan, profile, posting)
        assert enriched.selected_claim_ids == plan.selected_claim_ids
        assert enriched.claim_candidates == plan.claim_candidates
        assert enriched.composition_selection is None


def test_cross_entry_grouping_is_rejected() -> None:
    profile, posting, plan = _inputs()
    invalid = _result(
        evidence_ids=["firmware-1"],
        groups=[EvidenceGrouping(entry_id="unknown-entry", evidence_ids=["firmware-1"])],
    )
    enriched = _hybrid(FakeResumeLanguageModel(recommend_composition=invalid)).enrich_plan(
        plan, profile, posting
    )

    assert enriched.selected_claim_ids == plan.selected_claim_ids


def test_over_budget_proposal_is_rejected() -> None:
    profile, _, plan = _inputs()
    constrained = plan.model_copy(
        update={"constraints": plan.constraints.model_copy(update={"max_total_lines": 2})}
    )
    selection = CompositionSelection(
        selected_entry_ids=["firmware"],
        selected_evidence_ids=["firmware-1"],
        rationale="Open the entry.",
    )

    with pytest.raises(CompositionReconciliationError, match="total line budget"):
        DeterministicCompositionReconciler().reconcile(constrained, profile, selection)


def test_unconfirmed_evidence_cannot_be_promoted() -> None:
    profile, _, plan = _inputs()
    request = HybridLlmServices._composition_request(plan, profile)

    assert "unconfirmed" not in {
        evidence.evidence_id for entry in request.entries for evidence in entry.evidence
    }
    selection = CompositionSelection(
        selected_entry_ids=["firmware"],
        selected_evidence_ids=["unconfirmed"],
        evidence_groups=[
            CompositionEvidenceGroup(entry_id="firmware", evidence_ids=["unconfirmed"])
        ],
        rationale="Promote weak evidence.",
    )
    with pytest.raises(CompositionReconciliationError, match="eligible deterministic candidate"):
        DeterministicCompositionReconciler().reconcile(plan, profile, selection)


def test_weak_support_cannot_be_promoted() -> None:
    profile, _, plan = _inputs()
    weak = plan.claim_candidates[0].model_copy(
        update={"support": ClaimSupport.STRONG_INFERENCE_PENDING_REVIEW}
    )
    altered = plan.model_copy(update={"claim_candidates": [weak, *plan.claim_candidates[1:]]})
    selection = CompositionSelection(
        selected_entry_ids=[weak.entity_id],
        selected_evidence_ids=weak.evidence_ids,
        evidence_groups=[
            CompositionEvidenceGroup(
                entry_id=weak.entity_id,
                evidence_ids=weak.evidence_ids,
            )
        ],
        rationale="Promote weak support.",
    )

    with pytest.raises(CompositionReconciliationError, match="weak support"):
        DeterministicCompositionReconciler().reconcile(altered, profile, selection)
