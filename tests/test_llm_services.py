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
from resume_tailor.infrastructure.optimization import (
    DeterministicResumeOptimizer,
    EvidenceBoundResumeWriter,
)
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


def test_strongly_implied_rewrite_is_pending_until_approved_and_cached() -> None:
    profile, posting, plan = _plan()
    rewrite = BulletRewrite(
        entry_id="experience-1",
        final_bullet_text="Integrated STM32 firmware with SPI sensor validation at 30 FPS.",
        source_evidence_ids=["evidence-1"],
        preserved_technologies=[],
        preserved_metrics=[],
        emphasized_terms=["real-time", "embedded validation"],
        evidence_combined=False,
        concise_alternative="Integrated sensor firmware validation.",
        confidence=0.8,
        support="strongly_implied",
        support_rationale="The workflow is strongly implied by the supplied firmware and validation evidence.",
    )
    fake = FakeResumeLanguageModel(
        rewrite_bullets=BulletRewriteResult(
            metadata=metadata(LlmOperation.REWRITE_BULLETS),
            output=BulletRewriteOutput(bullets=[rewrite]),
        )
    )
    service = HybridLlmServices(fake, 0, 4, False, False, True)
    tailored = service.rewrite_plan(plan, profile)
    writer = EvidenceBoundResumeWriter()

    pending = writer.write(tailored, profile, set())
    generated_id = tailored.claim_candidates[0].id
    assert generated_id in pending.review_required_claim_ids
    assert pending.review_pending_bullets[0].text == rewrite.final_bullet_text

    approved = writer.write(tailored, profile, {generated_id})
    assert approved.experience_bullets["experience-1"][0].text == rewrite.final_bullet_text
    assert fake.calls["rewrite_bullets"] == 1


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


def test_combined_candidate_exposes_all_evidence_to_composition() -> None:
    profile = MasterProfile(
        id="profile-combined-composition",
        user_id="user-llm",
        display_name="Candidate",
        experiences=[
            ResumeItem(
                id="entry-combined",
                title="Autonomy Intern",
                kind=EntityKind.EXPERIENCE,
            )
        ],
        evidence=[
            EvidenceItem(
                id="combined-1",
                entity_id="entry-combined",
                source_text="Built ROS 2 teleoperation controls.",
                technologies=["ROS 2"],
                capabilities=["teleoperation"],
            ),
            EvidenceItem(
                id="combined-2",
                entity_id="entry-combined",
                source_text="Tested ROS 2 safety override controls.",
                technologies=["ROS 2"],
                capabilities=["teleoperation"],
            ),
        ],
    )
    posting = JobPosting(
        id="posting-combined",
        title="Autonomy Intern",
        description="Build ROS 2 teleoperation.",
    )
    plan = DeterministicResumeOptimizer().create_plan(
        profile,
        posting,
        TemplateConstraints(max_total_lines=3),
    )

    request = HybridLlmServices._composition_request(plan, profile)

    assert {item.evidence_id for entry in request.entries for item in entry.evidence} == {
        "combined-1",
        "combined-2",
    }
