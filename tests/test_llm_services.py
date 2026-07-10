from resume_tailor.application.llm_services import HybridLlmServices
from resume_tailor.domain.llm_models import (
    BulletRewrite,
    BulletRewriteOutput,
    BulletRewriteResult,
    CompositionRecommendationOutput,
    CompositionRecommendationResult,
    LanguageModelError,
    LanguageModelErrorKind,
    LlmOperation,
)
from resume_tailor.domain.models import EntityKind, EvidenceItem, JobPosting, MasterProfile, ResumeItem, TemplateConstraints
from resume_tailor.infrastructure.optimization import DeterministicResumeOptimizer
from tests.fakes import FakeResumeLanguageModel, metadata


def _profile() -> MasterProfile:
    return MasterProfile(
        id="profile-llm",
        user_id="user-llm",
        display_name="Candidate",
        experiences=[ResumeItem(id="experience-1", title="Firmware Intern", kind=EntityKind.EXPERIENCE)],
        evidence=[
            EvidenceItem(
                id="evidence-1",
                entity_id="experience-1",
                source_text="Developed STM32 firmware and validated SPI sensor communication at 30 FPS.",
                technologies=["STM32", "SPI"],
                outcomes=["30 FPS"],
            )
        ],
    )


def _plan() -> tuple[MasterProfile, JobPosting, object]:
    profile = _profile()
    posting = JobPosting(id="posting-llm", title="Embedded Firmware Intern", description="Develop STM32 firmware.")
    plan = DeterministicResumeOptimizer().create_plan(profile, posting, TemplateConstraints(max_experience_lines=4))
    return profile, posting, plan


def test_rewrite_uses_valid_grounded_response() -> None:
    profile, _, plan = _plan()
    rewrite = BulletRewrite(
        entry_id="experience-1",
        final_bullet_text="Developed STM32 firmware and validated SPI sensor communication at 30 FPS.",
        source_evidence_ids=["evidence-1"],
        preserved_technologies=["STM32", "SPI"],
        preserved_metrics=["30 FPS"],
        emphasized_terms=["firmware"],
        evidence_combined=False,
        concise_alternative="Developed STM32 firmware with SPI validation at 30 FPS.",
        confidence=0.9,
    )
    fake = FakeResumeLanguageModel(
        rewrite_bullets=BulletRewriteResult(
            metadata=metadata(LlmOperation.REWRITE_BULLETS),
            output=BulletRewriteOutput(bullets=[rewrite]),
        )
    )
    service = HybridLlmServices(fake, 1, 4, False, False, True)

    rewritten = service.rewrite_plan(plan, profile)

    assert rewritten.claim_candidates[0].text == rewrite.final_bullet_text
    assert fake.calls["rewrite_bullets"] == 1


def test_invalid_rewrite_retries_then_uses_original_evidence() -> None:
    profile, _, plan = _plan()
    invalid = BulletRewrite(
        entry_id="experience-1",
        final_bullet_text="Led a 60 FPS firmware platform.",
        source_evidence_ids=["evidence-1"],
        preserved_technologies=[],
        preserved_metrics=[],
        emphasized_terms=[],
        evidence_combined=False,
        concise_alternative="Invalid.",
        confidence=0.9,
    )
    fake = FakeResumeLanguageModel(
        rewrite_bullets=[
            BulletRewriteResult(
                metadata=metadata(LlmOperation.REWRITE_BULLETS),
                output=BulletRewriteOutput(bullets=[invalid]),
            ),
            LanguageModelError(LanguageModelErrorKind.RATE_LIMITED, "limited", True),
        ]
    )
    service = HybridLlmServices(fake, 1, 4, False, False, True)

    rewritten = service.rewrite_plan(plan, profile)

    assert rewritten.claim_candidates[0].text == plan.claim_candidates[0].text
    assert fake.calls["rewrite_bullets"] == 2


def test_invalid_composition_retries_without_changing_deterministic_selection() -> None:
    profile, posting, plan = _plan()
    invalid = CompositionRecommendationResult(
        metadata=metadata(LlmOperation.RECOMMEND_COMPOSITION),
        output=CompositionRecommendationOutput(
            selected_entry_ids=["unknown-entry"],
            rationale="Invalid ID.",
        ),
    )
    fake = FakeResumeLanguageModel(recommend_composition=[invalid, invalid])
    service = HybridLlmServices(fake, 1, 4, False, True, False)

    enriched = service.enrich_plan(plan, profile, posting)

    assert enriched.selected_claim_ids == plan.selected_claim_ids
    assert fake.calls["recommend_composition"] == 2
