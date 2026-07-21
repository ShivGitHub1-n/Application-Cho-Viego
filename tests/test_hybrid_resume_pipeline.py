# Provider fixture prose is intentionally retained as exact test input.
# ruff: noqa: E501

from __future__ import annotations

import pytest

from resume_tailor.application.llm_services import HybridLlmServices
from resume_tailor.application.resume_composition import (
    DeterministicResumeComposer,
    _posting_context,
    _State,
)
from resume_tailor.application.resume_retrieval import InProcessResumeEvidenceRetriever
from resume_tailor.application.services import TailorResumeService
from resume_tailor.domain.hybrid_resume import (
    BulletValidationStatus,
    HybridPlanningStatus,
    RetrievalAdmissionStatus,
    WriterExecutionStatus,
)
from resume_tailor.domain.layout import PageUtilizationStatus
from resume_tailor.domain.llm_models import (
    ApprovedEvidenceGroup,
    BulletRewrite,
    BulletRewriteClaim,
    BulletRewriteOutput,
    BulletRewriteResult,
    CompositionRecommendationOutput,
    CompositionRecommendationResult,
    EvidenceGrouping,
    LanguageModelError,
    LanguageModelErrorKind,
    LlmOperation,
)
from resume_tailor.domain.models import (
    EntityKind,
    EvidenceItem,
    JobPosting,
    MasterProfile,
    ResumeItem,
    TechnicalSkillCategory,
    TemplateConstraints,
)
from resume_tailor.domain.resume_composition import PageFitEvaluation
from resume_tailor.infrastructure.optimization import (
    DeterministicResumeOptimizer,
    EvidenceBoundResumeWriter,
)
from tests.fakes import FakeResumeLanguageModel, metadata


class ExactFixedPageFit:
    def evaluate(
        self,
        resume: object,
        *,
        attempt_exact: bool = True,
    ) -> PageFitEvaluation:
        return PageFitEvaluation(
            status=PageUtilizationStatus.ACCEPTABLE_ONE_PAGE,
            page_count=1,
            exact=attempt_exact,
            provider="controlled exact page fit",
            utilization_ratio=0.91,
            fits_one_page=True,
        )


def _profile(
    *,
    evidence_text: str = ("Developed STM32 firmware and validated SPI sensor communication."),
    skills: list[TechnicalSkillCategory] | None = None,
) -> MasterProfile:
    return MasterProfile(
        id="hybrid-profile",
        user_id="hybrid-user",
        display_name="Jordan Candidate",
        experiences=[
            ResumeItem(
                id="embedded-entry",
                title="Embedded Systems Developer",
                kind=EntityKind.EXPERIENCE,
                organization="Engineering Lab",
                start_date="2024",
                end_date="Present",
                location="Toronto, ON",
            )
        ],
        technical_skills=skills or [],
        evidence=[
            EvidenceItem(
                id="embedded-evidence",
                entity_id="embedded-entry",
                source_text=evidence_text,
                technologies=["STM32", "SPI"],
                capabilities=["firmware", "sensor validation"],
            ),
            EvidenceItem(
                id="embedded-debug-evidence",
                entity_id="embedded-entry",
                source_text="Debugged STM32 timing faults with reviewed SPI traces.",
                technologies=["STM32", "SPI"],
                capabilities=["firmware debugging", "timing validation"],
            ),
        ],
    )


def _posting() -> JobPosting:
    return JobPosting(
        id="embedded-posting",
        title="Embedded Firmware Developer",
        description=("Develop STM32 embedded firmware and validate SPI sensor communication."),
    )


def _rewrite_result() -> BulletRewriteResult:
    text = "Built and validated STM32 firmware for SPI sensor communication."
    return BulletRewriteResult(
        metadata=metadata(LlmOperation.REWRITE_BULLETS),
        output=BulletRewriteOutput(
            bullets=[
                BulletRewrite(
                    entry_id="embedded-entry",
                    final_bullet_text=text,
                    source_evidence_ids=["embedded-evidence"],
                    preserved_technologies=["STM32", "SPI"],
                    preserved_metrics=[],
                    emphasized_terms=["embedded firmware"],
                    evidence_combined=False,
                    concise_alternative=(
                        "Built STM32 firmware and validated SPI sensor communication."
                    ),
                    confidence=0.95,
                    claims=[
                        BulletRewriteClaim(
                            text=text,
                            supporting_evidence_ids=["embedded-evidence"],
                        )
                    ],
                    target_requirements_addressed=[
                        "Develop STM32 embedded firmware",
                        "validate SPI sensor communication",
                    ],
                )
            ]
        ),
    )


def test_production_page_fill_consumes_validated_rewrite_and_reuses_cache() -> None:
    profile = _profile()
    posting = _posting()
    fake = FakeResumeLanguageModel(rewrite_bullets=_rewrite_result())
    hybrid = HybridLlmServices(fake, 0, 2, False, False, True)
    service = TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
        hybrid_services=hybrid,
        resume_composer=DeterministicResumeComposer(ExactFixedPageFit()),
    )
    plan = service.create_plan(profile, posting, TemplateConstraints())

    first = service.build_document(plan, profile, set())
    second = service.build_document(plan, profile, set())

    first_bullet = first.experience_bullets["embedded-entry"][0]
    assert first_bullet.text == ("Built and validated STM32 firmware for SPI sensor communication.")
    assert first_bullet.evidence_ids == ["embedded-evidence"]
    assert first_bullet.writing_variant is not None
    assert first_bullet.writing_variant.validation_status is (BulletValidationStatus.VALIDATED)
    assert first.hybrid_diagnostic is not None
    assert first.hybrid_diagnostic.provider_call_count == 1
    assert first.hybrid_diagnostic.layout_input == ("validated_variants_with_source_fallbacks")
    assert first.hybrid_diagnostic.writer_execution_status is (
        WriterExecutionStatus.WRITER_SUCCEEDED
    )
    assert first.hybrid_diagnostic.rewritten_bullet_count == 1
    assert first.hybrid_diagnostic.source_bullet_count == 1
    assert second.hybrid_diagnostic is not None
    assert second.hybrid_diagnostic.provider_cache_hits == 1
    assert second.hybrid_diagnostic.writer_execution_status is (
        WriterExecutionStatus.CACHE_HIT
    )
    assert fake.calls["rewrite_bullets"] == 1


def test_cosmetic_action_verb_rewrite_does_not_displace_stronger_source() -> None:
    profile = _profile()
    posting = _posting()
    source = profile.evidence[0].source_text
    cosmetic = source.replace("Developed", "Built", 1)
    fake = FakeResumeLanguageModel(
        rewrite_bullets=BulletRewriteResult(
            metadata=metadata(LlmOperation.REWRITE_BULLETS),
            output=BulletRewriteOutput(
                bullets=[
                    BulletRewrite(
                        entry_id="embedded-entry",
                        final_bullet_text=cosmetic,
                        source_evidence_ids=["embedded-evidence"],
                        preserved_technologies=["STM32", "SPI"],
                        preserved_metrics=[],
                        emphasized_terms=[],
                        evidence_combined=False,
                        concise_alternative=cosmetic,
                        confidence=0.95,
                        claims=[
                            BulletRewriteClaim(
                                text=cosmetic,
                                supporting_evidence_ids=["embedded-evidence"],
                            )
                        ],
                    )
                ]
            ),
        )
    )
    service = TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
        hybrid_services=HybridLlmServices(fake, 0, 2, False, False, True),
        resume_composer=DeterministicResumeComposer(ExactFixedPageFit()),
    )
    plan = service.create_plan(profile, posting, TemplateConstraints())

    resume = service.build_document(plan, profile, set())

    assert resume.experience_bullets["embedded-entry"][0].text == source
    assert resume.hybrid_diagnostic is not None
    assert resume.hybrid_diagnostic.writer_execution_status is (
        WriterExecutionStatus.SOURCE_VARIANTS_SCORED_BETTER
    )
    assert resume.hybrid_diagnostic.rewritten_bullet_count == 0
    assert "zero rewrites reached" in resume.hybrid_diagnostic.writing_reason


def test_cached_all_rejected_writer_batch_keeps_explicit_rejection_status() -> None:
    profile = _profile()
    posting = _posting()
    rejected_text = (
        "Results-driven dynamic professional who validated STM32 firmware "
        "and SPI sensor communication."
    )
    fake = FakeResumeLanguageModel(
        rewrite_bullets=BulletRewriteResult(
            metadata=metadata(LlmOperation.REWRITE_BULLETS),
            output=BulletRewriteOutput(
                bullets=[
                    BulletRewrite(
                        entry_id="embedded-entry",
                        final_bullet_text=rejected_text,
                        source_evidence_ids=["embedded-evidence"],
                        preserved_technologies=["STM32", "SPI"],
                        preserved_metrics=[],
                        emphasized_terms=[],
                        evidence_combined=False,
                        concise_alternative=rejected_text,
                        confidence=0.95,
                        claims=[
                            BulletRewriteClaim(
                                text=rejected_text,
                                supporting_evidence_ids=["embedded-evidence"],
                            )
                        ],
                    )
                ]
            ),
        )
    )
    service = TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
        hybrid_services=HybridLlmServices(fake, 0, 2, False, False, True),
        resume_composer=DeterministicResumeComposer(ExactFixedPageFit()),
    )
    plan = service.create_plan(profile, posting, TemplateConstraints())

    first = service.build_document(plan, profile, set())
    second = service.build_document(plan, profile, set())

    assert first.hybrid_diagnostic is not None
    assert second.hybrid_diagnostic is not None
    assert first.hybrid_diagnostic.writer_execution_status is (
        WriterExecutionStatus.ALL_GENERATED_VARIANTS_REJECTED
    )
    assert second.hybrid_diagnostic.writer_execution_status is (
        WriterExecutionStatus.ALL_GENERATED_VARIANTS_REJECTED
    )
    assert second.hybrid_diagnostic.provider_cache_hits == 1
    assert second.hybrid_diagnostic.rejected_variant_count == 1
    assert fake.calls["rewrite_bullets"] == 1


def test_enabled_rewriting_reports_provider_unavailable_explicitly() -> None:
    profile = _profile()
    service = TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
        hybrid_services=HybridLlmServices(
            None,
            0,
            2,
            False,
            False,
            True,
            provider_name="gemini",
            model_name="unconfigured",
        ),
        resume_composer=DeterministicResumeComposer(ExactFixedPageFit()),
    )
    plan = service.create_plan(profile, _posting(), TemplateConstraints())

    resume = service.build_document(plan, profile, set())

    assert resume.hybrid_diagnostic is not None
    assert resume.hybrid_diagnostic.writer_execution_status is (
        WriterExecutionStatus.PROVIDER_UNAVAILABLE
    )
    assert resume.hybrid_diagnostic.provider_call_count == 0
    assert resume.hybrid_diagnostic.fallback_bullet_count == 2


def test_llm_disabled_uses_source_text_and_zero_provider_calls() -> None:
    profile = _profile()
    posting = _posting()
    fake = FakeResumeLanguageModel(rewrite_bullets=_rewrite_result())
    service = TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
        hybrid_services=HybridLlmServices(
            fake,
            0,
            2,
            False,
            False,
            False,
        ),
        resume_composer=DeterministicResumeComposer(ExactFixedPageFit()),
    )
    plan = service.create_plan(profile, posting, TemplateConstraints())

    resume = service.build_document(plan, profile, set())

    assert resume.experience_bullets["embedded-entry"][0].text == (
        profile.evidence[0].source_text
    )
    assert resume.hybrid_diagnostic is not None
    assert resume.hybrid_diagnostic.provider_call_count == 0
    assert resume.hybrid_diagnostic.planning_status is (HybridPlanningStatus.DETERMINISTIC_ONLY)
    assert fake.calls["rewrite_bullets"] == 0


def test_provider_timeout_retries_are_bounded_and_use_safe_source_fallback() -> None:
    profile = _profile()
    posting = _posting()
    timeout = LanguageModelError(
        LanguageModelErrorKind.TIMEOUT,
        "Controlled provider timeout.",
        retryable=True,
    )
    fake = FakeResumeLanguageModel(rewrite_bullets=[timeout])
    hybrid = HybridLlmServices(fake, 1, 8, False, False, True)
    service = TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
        hybrid_services=hybrid,
        resume_composer=DeterministicResumeComposer(ExactFixedPageFit()),
    )
    plan = service.create_plan(profile, posting, TemplateConstraints())

    resume = service.build_document(plan, profile, set())

    assert fake.calls["rewrite_bullets"] == 1
    assert resume.experience_bullets["embedded-entry"][0].text == (profile.evidence[0].source_text)
    assert resume.hybrid_diagnostic is not None
    assert resume.hybrid_diagnostic.deterministic_fallback_used is True
    assert resume.hybrid_diagnostic.provider_call_count == 1
    assert resume.hybrid_diagnostic.writer_execution_status is (
        WriterExecutionStatus.PROVIDER_TIMEOUT
    )
    assert service.telemetry.call_counts().provider_retries == 0


def test_semantic_planning_is_bounded_advice_and_counted_in_final_diagnostic() -> None:
    source_profile = _profile()
    profile = source_profile.model_copy(
        update={
            "evidence": [
                *source_profile.evidence,
                EvidenceItem(
                    id="embedded-release-evidence",
                    entity_id="embedded-entry",
                    source_text="Documented STM32 firmware release checks.",
                    technologies=["STM32"],
                    capabilities=["firmware release validation"],
                ),
            ]
        }
    )
    posting = _posting()
    recommendation = CompositionRecommendationResult(
        metadata=metadata(LlmOperation.RECOMMEND_COMPOSITION),
        output=CompositionRecommendationOutput(
            selected_entry_ids=["embedded-entry"],
            selected_evidence_ids=[
                "embedded-debug-evidence",
                "embedded-release-evidence",
            ],
            proposed_evidence_groupings=[
                EvidenceGrouping(
                    entry_id="embedded-entry",
                    evidence_ids=[
                        "embedded-debug-evidence",
                        "embedded-release-evidence",
                    ],
                )
            ],
            rationale="Use the supplied firmware evidence package.",
        ),
    )
    fake = FakeResumeLanguageModel(recommend_composition=recommendation)
    service = TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
        hybrid_services=HybridLlmServices(
            fake,
            0,
            2,
            False,
            True,
            False,
        ),
        resume_composer=DeterministicResumeComposer(ExactFixedPageFit()),
    )

    plan = service.create_plan(profile, posting, TemplateConstraints())
    resume = service.build_document(plan, profile, set())

    assert resume.hybrid_diagnostic is not None
    assert resume.hybrid_diagnostic.planning_status is (HybridPlanningStatus.ADVISORY_APPLIED)
    assert resume.hybrid_diagnostic.writing_status is (HybridPlanningStatus.DETERMINISTIC_ONLY)
    assert resume.hybrid_diagnostic.provider_call_count == 1
    assert fake.calls["recommend_composition"] == 1


@pytest.mark.parametrize(
    ("title", "description", "evidence_text"),
    [
        (
            "Controls Engineer",
            "Validate PLC/SCADA controls and Modbus TCP devices.",
            "Validated PLC/SCADA controls with Modbus TCP field devices.",
        ),
        (
            "Manufacturing Engineer",
            "Design GD&T fixtures for CNC manufacturing validation.",
            "Designed GD&T fixtures for CNC manufacturing validation.",
        ),
        (
            "Backend Engineer",
            "Deploy .NET 8 APIs to Kubernetes with CI/CD.",
            "Deployed .NET 8 APIs to Kubernetes through CI/CD release gates.",
        ),
        (
            "Machine Learning Engineer",
            "Deploy PyTorch inference pipelines and validate model drift.",
            "Deployed PyTorch inference pipelines and validated model drift.",
        ),
        (
            "Cybersecurity Engineer",
            "Harden OAuth 2.0 services and investigate SIEM alerts.",
            "Hardened OAuth 2.0 services and investigated SIEM alerts.",
        ),
        (
            "Civil Infrastructure Engineer",
            "Inspect reinforced-concrete structures using CSA S6 requirements.",
            "Inspected reinforced-concrete structures against CSA S6 requirements.",
        ),
        (
            "Systems Engineer",
            "Integrate sensors, wiring, controls, and verification plans.",
            "Integrated sensors, wiring, controls, and verification plans.",
        ),
        (
            "Technical Program Manager",
            "Coordinate engineering validation, risks, and release reviews.",
            "Coordinated engineering validation risks and release reviews.",
        ),
    ],
)
def test_cross_domain_retrieval_uses_one_generic_contract(
    title: str,
    description: str,
    evidence_text: str,
) -> None:
    profile = _profile(evidence_text=evidence_text)
    posting = JobPosting(
        id="cross-domain",
        title=title,
        description=description,
    )

    result = InProcessResumeEvidenceRetriever().retrieve(profile, posting)

    assert result.admitted
    assert result.admitted[0].admission_status in {
        RetrievalAdmissionStatus.ADMITTED_DIRECT,
        RetrievalAdmissionStatus.ADMITTED_ADJACENT,
    }
    assert result.contract_version == "resume-evidence-retrieval-v1"


def test_generic_soft_verbs_do_not_admit_unrelated_evidence() -> None:
    profile = _profile(evidence_text="Developed and supported various tasks.")
    posting = JobPosting(
        id="soft-only",
        title="Coordinator",
        description="Developed, supported, improved, and worked on tasks.",
    )

    result = InProcessResumeEvidenceRetriever().retrieve(profile, posting)

    assert not result.admitted
    assert result.rejected[0].admission_status in {
        RetrievalAdmissionStatus.REJECTED_GENERIC_ONLY,
        RetrievalAdmissionStatus.REJECTED_LOW_RELEVANCE,
    }


def test_three_credible_skill_categories_are_normally_retained() -> None:
    profile = _profile(
        evidence_text=(
            "Developed STM32 firmware in C++, validated SPI sensors with an "
            "oscilloscope, and automated Python test reports."
        ),
        skills=[
            TechnicalSkillCategory(category="Languages", values=["C++", "Python"]),
            TechnicalSkillCategory(category="Embedded", values=["STM32", "SPI"]),
            TechnicalSkillCategory(
                category="Test Equipment",
                values=["Oscilloscope"],
            ),
        ],
    )
    service = TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
        resume_composer=DeterministicResumeComposer(ExactFixedPageFit()),
    )
    plan = service.create_plan(profile, _posting(), TemplateConstraints())

    resume = service.build_document(plan, profile, set())

    assert resume.composition_diagnostic is not None
    assert len(resume.composition_diagnostic.selected_skill_category_ids) == 3
    assert resume.composition_diagnostic.credible_skill_category_count == 3
    assert resume.composition_diagnostic.skill_category_shortfall_reason is None


def test_new_reviewed_profile_content_is_retrieved_without_code_changes() -> None:
    retriever = InProcessResumeEvidenceRetriever()
    profile = _profile(evidence_text="Documented general laboratory procedures.")
    first = retriever.retrieve(profile, _posting())
    grown = profile.model_copy(
        update={
            "version": 2,
            "evidence": [
                *profile.evidence,
                EvidenceItem(
                    id="new-firmware-proof",
                    entity_id="embedded-entry",
                    source_text=(
                        "Implemented STM32 firmware and validated SPI sensor communication."
                    ),
                    technologies=["STM32", "SPI"],
                    capabilities=["firmware"],
                ),
            ],
        }
    )

    second = retriever.retrieve(grown, _posting())

    assert "new-firmware-proof" not in {item.evidence_id for item in first.admitted}
    assert "new-firmware-proof" in {item.evidence_id for item in second.admitted}


def test_generic_dominance_suppresses_weaker_overlapping_evidence() -> None:
    profile = MasterProfile(
        id="dominance-profile",
        user_id="dominance-user",
        display_name="Candidate",
        experiences=[
            ResumeItem(
                id="strong-entry",
                title="Security Engineer",
                kind=EntityKind.EXPERIENCE,
            ),
            ResumeItem(
                id="weak-entry",
                title="Security Assistant",
                kind=EntityKind.EXPERIENCE,
            ),
        ],
        evidence=[
            EvidenceItem(
                id="strong-proof",
                entity_id="strong-entry",
                source_text=(
                    "Architected, deployed, debugged, and validated OAuth 2.0 "
                    "identity services across production systems."
                ),
                technologies=["OAuth 2.0"],
                capabilities=[
                    "architecture",
                    "deployment",
                    "debugging",
                    "validation",
                ],
            ),
            EvidenceItem(
                id="weak-keywords",
                entity_id="weak-entry",
                source_text="Implemented and tested OAuth 2.0 identity services.",
                technologies=["OAuth 2.0"],
            ),
        ],
    )
    posting = JobPosting(
        id="dominance-posting",
        title="Security Engineer",
        description=("Design, deploy, debug, and validate OAuth 2.0 identity services."),
    )
    composer = DeterministicResumeComposer(ExactFixedPageFit())
    bullets = composer._rank_bullets(profile, _posting_context(posting))
    by_id = {item.evidence_id: item for item in bullets}

    penalty, dominated, relationship = composer._dominance_penalty(
        by_id["weak-keywords"],
        _State(frozenset({"strong-proof"}), frozenset()),
        by_id,
    )

    assert dominated is True
    assert penalty == by_id["weak-keywords"].score
    assert relationship is not None
    assert "stronger intrinsic proof" in relationship


def test_generic_retrieval_allows_new_technical_domain_without_reclassifying_it() -> None:
    profile = _profile(evidence_text=("Hardened OAuth 2.0 services and investigated SIEM alerts."))
    posting = JobPosting(
        id="cyber-posting",
        title="Cybersecurity Engineer",
        description=("Harden OAuth 2.0 services and investigate SIEM alerts."),
    )
    service = TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
    )

    plan = service.create_plan(profile, posting, TemplateConstraints())

    assert plan.report.role.supported is False
    assert plan.strategy is not None
    assert plan.strategy.role_family == "evidence_grounded_technical"


def test_weaker_evidence_survives_when_it_adds_unique_required_capability() -> None:
    profile = MasterProfile(
        id="unique-capability-profile",
        user_id="unique-user",
        display_name="Candidate",
        experiences=[
            ResumeItem(
                id="identity-entry",
                title="Identity Engineer",
                kind=EntityKind.EXPERIENCE,
            ),
            ResumeItem(
                id="monitoring-entry",
                title="Security Assistant",
                kind=EntityKind.EXPERIENCE,
            ),
        ],
        evidence=[
            EvidenceItem(
                id="identity-proof",
                entity_id="identity-entry",
                source_text=("Architected and deployed OAuth 2.0 identity services."),
                technologies=["OAuth 2.0"],
            ),
            EvidenceItem(
                id="siem-proof",
                entity_id="monitoring-entry",
                source_text=("Investigated SIEM alerts for OAuth 2.0 identity services."),
                technologies=["SIEM", "OAuth 2.0"],
            ),
        ],
    )
    posting = JobPosting(
        id="unique-posting",
        title="Security Engineer",
        description=("Deploy OAuth 2.0 identity services and investigate SIEM alerts."),
    )
    composer = DeterministicResumeComposer(ExactFixedPageFit())
    bullets = composer._rank_bullets(profile, _posting_context(posting))
    by_id = {item.evidence_id: item for item in bullets}

    _penalty, dominated, _relationship = composer._dominance_penalty(
        by_id["siem-proof"],
        _State(frozenset({"identity-proof"}), frozenset()),
        by_id,
    )

    assert dominated is False


def test_clean_grounded_variant_beats_awkward_or_three_line_variant() -> None:
    base = (
        "Implemented deterministic validation across distributed services "
        "using reviewed evidence and reproducible deployment checks "
    )
    long_text = base + ("balanced " * 15) + "tail fragment"
    concise = "Implemented deterministic validation with reproducible deployment checks."
    group = ApprovedEvidenceGroup(
        entry_id="embedded-entry",
        evidence_ids=["embedded-evidence"],
        source_texts=[long_text],
        max_rendered_lines=3,
    )
    rewrite = BulletRewrite(
        entry_id="embedded-entry",
        final_bullet_text=long_text,
        source_evidence_ids=["embedded-evidence"],
        preserved_technologies=[],
        preserved_metrics=[],
        emphasized_terms=[],
        evidence_combined=False,
        concise_alternative=concise,
        confidence=0.9,
    )
    service = HybridLlmServices(None, 0, 1, False, False, False)

    accepted, rejected, _diagnostics = service._variant_records(
        [rewrite],
        [group],
        provider="fake",
        model="fake",
        posting=JobPosting(
            id="line-posting",
            title="Validation Engineer",
            description="Implement deterministic validation and deployment checks.",
        ),
    )

    assert not rejected
    assert accepted[0].rewritten_text == concise
    assert accepted[0].line_fit.expected_line_count <= 2
    long_variant = next(item for item in accepted if item.rewritten_text == long_text)
    assert long_variant.line_fit.three_line_risk is True
    assert long_variant.validation_status is BulletValidationStatus.REVIEW_REQUIRED


def test_unique_three_line_generated_variant_is_review_gated() -> None:
    text = (
        "Implemented deterministic validation across distributed services "
        "using reviewed evidence and reproducible deployment checks "
        + ("balanced " * 16)
        + "tail fragment"
    )
    group = ApprovedEvidenceGroup(
        entry_id="embedded-entry",
        evidence_ids=["embedded-evidence"],
        source_texts=[text],
        max_rendered_lines=3,
    )
    rewrite = BulletRewrite(
        entry_id="embedded-entry",
        final_bullet_text=text,
        source_evidence_ids=["embedded-evidence"],
        preserved_technologies=[],
        preserved_metrics=[],
        emphasized_terms=[],
        evidence_combined=False,
        concise_alternative=text,
        confidence=0.9,
    )
    service = HybridLlmServices(None, 0, 1, False, False, False)

    accepted, _rejected, _diagnostics = service._variant_records(
        [rewrite],
        [group],
        provider="fake",
        model="fake",
        posting=JobPosting(
            id="line-posting",
            title="Validation Engineer",
            description="Implement deterministic validation and deployment checks.",
        ),
    )

    assert accepted
    assert all(
        item.validation_status is BulletValidationStatus.REVIEW_REQUIRED for item in accepted
    )
    assert all(item.future_user_review for item in accepted)


def test_ambiguous_new_mechanism_is_quarantined_for_semantic_review() -> None:
    source = "Integrated an actuator with the reviewed control system."
    rewritten = "Integrated a hydraulic actuator with the reviewed control system."
    group = ApprovedEvidenceGroup(
        entry_id="embedded-entry",
        evidence_ids=["embedded-evidence"],
        source_texts=[source],
        max_rendered_lines=2,
    )
    rewrite = BulletRewrite(
        entry_id="embedded-entry",
        final_bullet_text=rewritten,
        source_evidence_ids=["embedded-evidence"],
        preserved_technologies=[],
        preserved_metrics=[],
        emphasized_terms=[],
        evidence_combined=False,
        concise_alternative=rewritten,
        confidence=0.9,
    )
    service = HybridLlmServices(None, 0, 1, False, False, False)

    accepted, rejected, _diagnostics = service._variant_records(
        [rewrite],
        [group],
        provider="fake",
        model="fake",
        posting=JobPosting(
            id="controls-posting",
            title="Controls Engineer",
            description="Integrate actuators with control systems.",
        ),
    )

    assert not rejected
    assert accepted
    assert all(
        item.validation_status is BulletValidationStatus.REVIEW_REQUIRED for item in accepted
    )
    assert all("entailment review" in " ".join(item.validation_reasons) for item in accepted)


def test_legitimate_broad_semantic_equivalent_passes_without_factual_freedom() -> None:
    source = "Tested sensor timing with the reviewed control system."
    rewritten = "Validated sensor timing with the reviewed control system."
    group = ApprovedEvidenceGroup(
        entry_id="embedded-entry",
        evidence_ids=["embedded-evidence"],
        source_texts=[source],
        max_rendered_lines=2,
    )
    rewrite = BulletRewrite(
        entry_id="embedded-entry",
        final_bullet_text=rewritten,
        source_evidence_ids=["embedded-evidence"],
        preserved_technologies=[],
        preserved_metrics=[],
        emphasized_terms=[],
        evidence_combined=False,
        concise_alternative=rewritten,
        confidence=0.9,
    )
    service = HybridLlmServices(None, 0, 1, False, False, False)

    accepted, rejected, _diagnostics = service._variant_records(
        [rewrite],
        [group],
        provider="fake",
        model="fake",
        posting=JobPosting(
            id="semantic-posting",
            title="Validation Engineer",
            description="Validate sensor timing with control systems.",
        ),
    )

    assert not rejected
    assert accepted
    assert all(
        item.validation_status is BulletValidationStatus.VALIDATED
        for item in accepted
    )


@pytest.mark.parametrize(
    ("written", "posting", "expected_reason"),
    [
        (
            "Results-driven dynamic professional who validated the sensor interface.",
            "Validate sensor interfaces.",
            "prohibited phrase",
        ),
        (
            "Deliver secure reliable scalable services through automated production deployment controls.",
            (
                "Deliver secure reliable scalable services through automated production "
                "deployment controls."
            ),
            "job-description phrase",
        ),
    ],
)
def test_ai_like_or_copied_writing_is_rejected_without_rigid_templates(
    written: str,
    posting: str,
    expected_reason: str,
) -> None:
    group = ApprovedEvidenceGroup(
        entry_id="embedded-entry",
        evidence_ids=["embedded-evidence"],
        source_texts=["Validated the sensor interface."],
        max_rendered_lines=2,
    )
    rewrite = BulletRewrite(
        entry_id="embedded-entry",
        final_bullet_text=written,
        source_evidence_ids=["embedded-evidence"],
        preserved_technologies=[],
        preserved_metrics=[],
        emphasized_terms=[],
        evidence_combined=False,
        concise_alternative=written,
        confidence=0.9,
    )
    service = HybridLlmServices(None, 0, 1, False, False, False)

    accepted, rejected, _diagnostics = service._variant_records(
        [rewrite],
        [group],
        provider="fake",
        model="fake",
        posting=JobPosting(
            id="style-posting",
            title="Validation Engineer",
            description=posting,
        ),
    )

    assert not accepted
    assert rejected
    assert expected_reason in " ".join(rejected[0].validation_reasons)
