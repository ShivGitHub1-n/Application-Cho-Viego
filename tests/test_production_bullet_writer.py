from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from resume_tailor.application.job_intake import build_job_posting
from resume_tailor.application.llm_services import HybridLlmServices
from resume_tailor.application.resume_composition import (
    CompositionSearchBounds,
    DeterministicResumeComposer,
)
from resume_tailor.application.services import TailorResumeService
from resume_tailor.domain.hybrid_resume import (
    BulletValidationStatus,
    WriterExecutionStatus,
)
from resume_tailor.domain.layout import PageUtilizationStatus
from resume_tailor.domain.llm_models import (
    ApprovedEvidenceGroup,
    BulletRewrite,
    BulletRewriteClaim,
    BulletRewriteOutput,
    BulletRewriteRequest,
    BulletRewriteResult,
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
    TemplateConstraints,
)
from resume_tailor.domain.requirement_ranking import EvidenceRelationship
from resume_tailor.domain.resume_composition import PageFitEvaluation
from resume_tailor.infrastructure.optimization import (
    DeterministicResumeOptimizer,
    EvidenceBoundResumeWriter,
)
from tests.fakes import FakeResumeLanguageModel, metadata

ROOT = Path(__file__).resolve().parents[1]


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


@pytest.mark.parametrize(
    ("domain", "source", "rewrite", "technologies", "capabilities"),
    [
        (
            "embedded/robotics",
            "Developed STM32 firmware and validated SPI sensor communication for robotic controls.",
            "Built STM32 firmware for robotic controls and validated SPI sensor communication.",
            ["STM32", "SPI"],
            ["firmware", "sensor validation", "robotic controls"],
        ),
        (
            "mechanical/manufacturing",
            (
                "Designed CNC machined aluminum fixtures and tested assembly "
                "tolerances for manufacturing."
            ),
            (
                "Tested assembly tolerances for CNC machined aluminum fixtures "
                "designed for manufacturing."
            ),
            ["CNC"],
            ["fixture design", "tolerance testing", "manufacturing"],
        ),
        (
            "backend/cloud",
            (
                "Implemented Python APIs with PostgreSQL transactions and tested "
                "production failure handling."
            ),
            "Tested production failure handling for Python APIs with PostgreSQL transactions.",
            ["Python", "PostgreSQL"],
            ["APIs", "testing", "production failure handling"],
        ),
        (
            "cybersecurity",
            "Implemented OAuth 2.0 access controls and validated Docker deployment security tests.",
            "Validated Docker deployment security tests and implemented OAuth 2.0 access controls.",
            ["OAuth 2.0", "Docker"],
            ["access controls", "deployment security testing"],
        ),
        (
            "data/AI",
            (
                "Developed Python evaluation pipelines and tested model outputs "
                "using reviewed datasets."
            ),
            (
                "Tested model outputs using reviewed datasets and developed Python "
                "evaluation pipelines."
            ),
            ["Python"],
            ["evaluation pipelines", "model testing", "reviewed datasets"],
        ),
        (
            "mixed multidisciplinary engineering",
            (
                "Integrated firmware, mechanical assemblies, and Python test "
                "automation with cross-functional teams."
            ),
            (
                "Integrated Python test automation, firmware, and mechanical "
                "assemblies with cross-functional teams."
            ),
            ["Python"],
            [
                "firmware",
                "mechanical integration",
                "test automation",
                "cross-functional collaboration",
            ],
        ),
    ],
)
def test_cross_domain_material_restructuring_preserves_reviewed_facts(
    domain: str,
    source: str,
    rewrite: str,
    technologies: list[str],
    capabilities: list[str],
) -> None:
    group = ApprovedEvidenceGroup(
        entry_id="entry",
        evidence_ids=["evidence"],
        source_texts=[source],
        technologies=technologies,
        capabilities=capabilities,
        max_rendered_lines=2,
    )
    service = HybridLlmServices(None, 0, 1, False, False, False)

    accepted, rejected = service._variant_records(
        [
            BulletRewrite(
                entry_id="entry",
                final_bullet_text=rewrite,
                source_evidence_ids=["evidence"],
                preserved_technologies=technologies,
                evidence_combined=False,
                confidence=0.9,
                claims=[
                    BulletRewriteClaim(
                        text=rewrite,
                        supporting_evidence_ids=["evidence"],
                    )
                ],
            )
        ],
        [group],
        provider="fake",
        model=f"fake-{domain}",
        posting=JobPosting(
            id=f"{domain}-posting",
            title=f"{domain} engineer",
            description=" ".join([*technologies, *capabilities]),
        ),
    )

    assert not rejected
    assert accepted
    assert accepted[0].validation_status is BulletValidationStatus.VALIDATED
    assert accepted[0].material_improvement is True
    assert accepted[0].source_evidence_ids == ["evidence"]
    assert accepted[0].factual_claims[0].supporting_evidence_ids == ["evidence"]


def test_malformed_typed_output_receives_exactly_one_repair() -> None:
    profile, posting = _single_entry_case()
    malformed = LanguageModelError(
        LanguageModelErrorKind.MALFORMED_RESPONSE,
        "Controlled malformed typed output.",
    )
    fake = FakeResumeLanguageModel(rewrite_bullets=[malformed, _single_entry_rewrite()])
    service = _service(fake)
    plan = service.create_plan(profile, posting, TemplateConstraints())

    resume = service.build_document(plan, profile, set())

    assert fake.calls["rewrite_bullets"] == 2
    assert service.telemetry.call_counts().provider_retries == 1
    repaired_request = fake.requests["rewrite_bullets"][1]
    assert isinstance(repaired_request, BulletRewriteRequest)
    assert repaired_request.correction_notes
    assert resume.hybrid_diagnostic is not None
    assert resume.hybrid_diagnostic.rewritten_bullet_count == 1
    assert "malformed" in (resume.hybrid_diagnostic.provider_retry_reason or "").casefold()


def test_second_malformed_typed_output_falls_back_without_a_third_call() -> None:
    profile, posting = _single_entry_case()
    malformed = LanguageModelError(
        LanguageModelErrorKind.MALFORMED_RESPONSE,
        "Controlled malformed typed output.",
    )
    fake = FakeResumeLanguageModel(rewrite_bullets=[malformed, malformed])
    service = _service(fake)
    plan = service.create_plan(profile, posting, TemplateConstraints())

    resume = service.build_document(plan, profile, set())

    assert fake.calls["rewrite_bullets"] == 2
    assert service.telemetry.call_counts().provider_retries == 1
    assert resume.hybrid_diagnostic is not None
    assert resume.hybrid_diagnostic.writer_execution_status is (
        WriterExecutionStatus.MALFORMED_WRITER_OUTPUT
    )
    assert "also failed" in (resume.hybrid_diagnostic.provider_retry_reason or "")
    assert resume.hybrid_diagnostic.fallback_bullet_count == 1


def test_empty_typed_batch_reports_no_material_improvement() -> None:
    profile, posting = _single_entry_case()
    fake = FakeResumeLanguageModel(
        rewrite_bullets=BulletRewriteResult(
            metadata=metadata(LlmOperation.REWRITE_BULLETS),
            output=BulletRewriteOutput(),
        )
    )
    service = _service(fake)
    plan = service.create_plan(profile, posting, TemplateConstraints())

    resume = service.build_document(plan, profile, set())

    assert resume.hybrid_diagnostic is not None
    assert resume.hybrid_diagnostic.writer_execution_status is (
        WriterExecutionStatus.NO_MATERIAL_IMPROVEMENT
    )
    assert resume.hybrid_diagnostic.rewritten_bullet_count == 0
    assert "no variants" in resume.hybrid_diagnostic.writing_reason.casefold()


def test_writer_cache_survives_page_budget_changes() -> None:
    profile, posting = _single_entry_case()
    fake = FakeResumeLanguageModel(rewrite_bullets=_single_entry_rewrite())
    service = _service(fake)
    first_plan = service.create_plan(
        profile,
        posting,
        TemplateConstraints(max_total_lines=42),
    )
    second_plan = service.create_plan(
        profile,
        posting,
        TemplateConstraints(max_total_lines=46),
    )

    first = service.build_document(first_plan, profile, set())
    second = service.build_document(second_plan, profile, set())

    assert fake.calls["rewrite_bullets"] == 1
    assert first.hybrid_diagnostic is not None
    assert second.hybrid_diagnostic is not None
    assert second.hybrid_diagnostic.provider_cache_hits == 1


def test_reviewed_evidence_change_invalidates_writer_cache() -> None:
    profile, posting = _single_entry_case()
    changed_profile = profile.model_copy(deep=True)
    changed_profile.evidence[0] = changed_profile.evidence[0].model_copy(
        update={
            "source_text": (
                "Developed STM32 firmware and validated SPI sensor communication "
                "through reviewed timing checks."
            ),
            "capabilities": [
                "firmware",
                "sensor validation",
                "reviewed timing checks",
            ],
        }
    )
    fake = FakeResumeLanguageModel(
        rewrite_bullets=[
            _single_entry_rewrite(),
            _single_entry_rewrite(),
        ]
    )
    service = _service(fake)
    first_plan = service.create_plan(profile, posting, TemplateConstraints())
    second_plan = service.create_plan(
        changed_profile,
        posting,
        TemplateConstraints(),
    )

    service.build_document(first_plan, profile, set())
    service.build_document(second_plan, changed_profile, set())

    assert fake.calls["rewrite_bullets"] == 2


def test_source_defeats_longer_rewrite_without_added_job_value() -> None:
    source = "Built Python APIs with PostgreSQL transactions."
    written = (
        "Built Python APIs with PostgreSQL transactions, integration testing, "
        "schema validation, production failure handling, controlled release evidence, "
        "deployment checks, and reviewed negative tests."
    )
    profile = MasterProfile(
        id="source-competition-profile",
        user_id="source-competition-user",
        display_name="Source Competition Candidate",
        experiences=[
            ResumeItem(
                id="backend-entry",
                title="Backend Developer",
                kind=EntityKind.EXPERIENCE,
            )
        ],
        evidence=[
            EvidenceItem(
                id="backend-evidence",
                entity_id="backend-entry",
                source_text=source,
                technologies=["Python", "PostgreSQL"],
                capabilities=[
                    "integration testing",
                    "schema validation",
                    "production failure handling",
                    "controlled release evidence",
                    "deployment checks",
                    "reviewed negative tests",
                ],
            )
        ],
    )
    posting = JobPosting(
        id="backend-posting",
        title="Backend Engineer",
        description="Required: Build Python APIs with PostgreSQL transactions.",
    )
    fake = FakeResumeLanguageModel(
        rewrite_bullets=BulletRewriteResult(
            metadata=metadata(LlmOperation.REWRITE_BULLETS),
            output=BulletRewriteOutput(
                bullets=[
                    BulletRewrite(
                        entry_id="backend-entry",
                        final_bullet_text=written,
                        source_evidence_ids=["backend-evidence"],
                        preserved_technologies=["Python", "PostgreSQL"],
                        evidence_combined=False,
                        confidence=0.95,
                        claims=[
                            BulletRewriteClaim(
                                text=written,
                                supporting_evidence_ids=["backend-evidence"],
                            )
                        ],
                    )
                ]
            ),
        )
    )
    service = _service(fake)
    plan = service.create_plan(profile, posting, TemplateConstraints())

    resume = service.build_document(plan, profile, set())

    assert resume.experience_bullets["backend-entry"][0].text == source
    assert resume.hybrid_diagnostic is not None
    assert resume.hybrid_diagnostic.rewritten_bullet_count == 0
    assert resume.hybrid_diagnostic.writer_execution_status is (
        WriterExecutionStatus.SOURCE_VARIANTS_SCORED_BETTER
    )
    variant = resume.hybrid_diagnostic.bullet_variants[0]
    assert variant.material_improvement is True
    assert variant.line_fit.expected_line_count > 1
    assert "line fit" in (variant.selection_reason or "")


def test_validated_alternative_variant_can_replace_initial_portfolio_entry() -> None:
    profile, posting = _writer_replacement_case()
    bounds = CompositionSearchBounds(
        maximum_selected_bullets=1,
        maximum_selected_entries=1,
        maximum_experience_entries=1,
        maximum_project_entries=0,
    )
    composer = DeterministicResumeComposer(ExactFixedPageFit(), bounds=bounds)
    optimizer = DeterministicResumeOptimizer()
    source_writer = EvidenceBoundResumeWriter()
    source_plan = optimizer.create_plan(profile, posting, TemplateConstraints())
    source_resume = source_writer.write(source_plan, profile, set())
    source_composed = composer.compose(
        source_resume,
        profile,
        posting,
        source_plan.constraints,
    )
    assert source_composed.composition_diagnostic is not None
    assert source_composed.composition_diagnostic.selected_experience_ids == ["strong-source"]

    written = "Built Python APIs and validated automated testing for production workflows."
    fake = FakeResumeLanguageModel(
        rewrite_bullets=BulletRewriteResult(
            metadata=metadata(LlmOperation.REWRITE_BULLETS),
            output=BulletRewriteOutput(
                bullets=[
                    BulletRewrite(
                        entry_id="writer-alternative",
                        final_bullet_text=written,
                        source_evidence_ids=[
                            "writer-alternative-evidence",
                            "writer-alternative-production-evidence",
                        ],
                        preserved_technologies=["Python"],
                        evidence_combined=True,
                        confidence=0.95,
                        claims=[
                            BulletRewriteClaim(
                                text=written,
                                supporting_evidence_ids=[
                                    "writer-alternative-evidence",
                                    "writer-alternative-production-evidence",
                                ],
                            )
                        ],
                    )
                ]
            ),
        )
    )
    service = TailorResumeService(
        optimizer,
        source_writer,
        hybrid_services=HybridLlmServices(fake, 0, 2, False, False, True),
        resume_composer=composer,
    )
    plan = service.create_plan(profile, posting, TemplateConstraints())

    final = service.build_document(plan, profile, set())

    assert final.hybrid_diagnostic is not None
    request = fake.requests["rewrite_bullets"][0]
    assert isinstance(request, BulletRewriteRequest)
    assert "writer-alternative" in {group.entry_id for group in request.groups}
    assert final.composition_diagnostic is not None
    assert final.composition_diagnostic.selected_experience_ids == ["writer-alternative"]
    assert final.experience_bullets["writer-alternative"][0].text == written
    assert final.hybrid_diagnostic.rewritten_bullet_count == 1


def test_real_profile_shortlist_keeps_exl_and_stush_as_bounded_alternatives() -> None:
    profile = MasterProfile.model_validate_json(
        (ROOT / "manual-test" / "profile.json").read_text(encoding="utf-8")
    )
    posting = build_job_posting(
        "controlled-real-profile-embedded-posting",
        "Embedded Systems Engineer",
        (ROOT / "manual-test" / "embedded-systems-engineer-posting.txt").read_text(
            encoding="utf-8"
        ),
    )
    fake = FakeResumeLanguageModel(
        rewrite_bullets=BulletRewriteResult(
            metadata=metadata(LlmOperation.REWRITE_BULLETS),
            output=BulletRewriteOutput(),
        )
    )
    service = _service(fake)
    plan = service.create_plan(profile, posting, TemplateConstraints())

    resume = service.build_document(plan, profile, set())

    request = fake.requests["rewrite_bullets"][0]
    assert isinstance(request, BulletRewriteRequest)
    entry_ids = {group.entry_id for group in request.groups}
    assert {"experience-exl", "experience-stush"}.issubset(entry_ids)
    assert len(request.groups) <= 24
    assert max(Counter(group.entry_id for group in request.groups).values()) <= 4
    assert sum(
        group.relationship_tier is EvidenceRelationship.DIRECT for group in request.groups
    ) > sum(group.relationship_tier is EvidenceRelationship.ADJACENT for group in request.groups)
    assert resume.hybrid_diagnostic is not None
    shortlisted = {
        item.entry_id for item in resume.hybrid_diagnostic.writer_shortlist if item.selected
    }
    assert {"experience-exl", "experience-stush"}.issubset(shortlisted)
    assert all(not hasattr(group, "organization") for group in request.groups)


def _service(fake: FakeResumeLanguageModel) -> TailorResumeService:
    return TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
        hybrid_services=HybridLlmServices(fake, 0, 2, False, False, True),
        resume_composer=DeterministicResumeComposer(ExactFixedPageFit()),
    )


def _single_entry_case() -> tuple[MasterProfile, JobPosting]:
    profile = MasterProfile(
        id="writer-profile",
        user_id="writer-user",
        display_name="Writer Candidate",
        experiences=[
            ResumeItem(
                id="embedded-entry",
                title="Embedded Developer",
                kind=EntityKind.EXPERIENCE,
            )
        ],
        evidence=[
            EvidenceItem(
                id="embedded-evidence",
                entity_id="embedded-entry",
                source_text=("Developed STM32 firmware and validated SPI sensor communication."),
                technologies=["STM32", "SPI"],
                capabilities=["firmware", "sensor validation"],
            )
        ],
    )
    return (
        profile,
        JobPosting(
            id="embedded-posting",
            title="Embedded Firmware Developer",
            description="Develop STM32 firmware and validate SPI sensor communication.",
        ),
    )


def _single_entry_rewrite() -> BulletRewriteResult:
    written = "Built STM32 firmware for validated SPI sensor communication."
    return BulletRewriteResult(
        metadata=metadata(LlmOperation.REWRITE_BULLETS),
        output=BulletRewriteOutput(
            bullets=[
                BulletRewrite(
                    entry_id="embedded-entry",
                    final_bullet_text=written,
                    source_evidence_ids=["embedded-evidence"],
                    preserved_technologies=["STM32", "SPI"],
                    evidence_combined=False,
                    confidence=0.95,
                    claims=[
                        BulletRewriteClaim(
                            text=written,
                            supporting_evidence_ids=["embedded-evidence"],
                        )
                    ],
                )
            ]
        ),
    )


def _writer_replacement_case() -> tuple[MasterProfile, JobPosting]:
    profile = MasterProfile(
        id="writer-aware-profile",
        user_id="writer-aware-user",
        display_name="Portfolio Candidate",
        experiences=[
            ResumeItem(
                id="writer-alternative",
                title="Python Developer",
                kind=EntityKind.EXPERIENCE,
            ),
            ResumeItem(
                id="strong-source",
                title="Systems Engineer",
                kind=EntityKind.EXPERIENCE,
            ),
        ],
        evidence=[
            EvidenceItem(
                id="writer-alternative-evidence",
                entity_id="writer-alternative",
                source_text="Built Python APIs for backend services.",
                technologies=["Python"],
                capabilities=["APIs"],
            ),
            EvidenceItem(
                id="writer-alternative-production-evidence",
                entity_id="writer-alternative",
                source_text=("Validated automated testing for production workflows."),
                capabilities=["automated testing", "production workflows"],
            ),
            EvidenceItem(
                id="strong-source-evidence",
                entity_id="strong-source",
                source_text=(
                    "Designed API architecture, automated testing, and production workflows."
                ),
                capabilities=[
                    "API architecture",
                    "automated testing",
                    "production workflows",
                    "ownership",
                ],
            ),
        ],
    )
    posting = JobPosting(
        id="writer-aware-posting",
        title="Python Backend Engineer",
        description=(
            "Required: Python APIs. Important: automated testing and production workflows."
        ),
    )
    return profile, posting
