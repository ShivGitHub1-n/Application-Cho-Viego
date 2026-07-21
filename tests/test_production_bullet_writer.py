from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from resume_tailor.application.generation_diagnostics import GenerationTelemetry
from resume_tailor.application.job_intake import build_job_posting
from resume_tailor.application.llm_services import HybridLlmServices
from resume_tailor.application.resume_composition import (
    CompositionSearchBounds,
    DeterministicResumeComposer,
    _rewrite_substance_adjustment,
)
from resume_tailor.application.resume_features import TemplateV1BulletLineEstimator
from resume_tailor.application.services import TailorResumeService
from resume_tailor.domain.generated_artifact import GenerationStage, StageStatus
from resume_tailor.domain.hybrid_resume import (
    BulletValidationStatus,
    GroundingFailureCode,
    ProviderRewriteMappingOutcome,
    ProviderRewriteMappingStatus,
    WriterExecutionStatus,
    WriterPipelineFailureCode,
    WriterPipelineIssue,
    WriterPipelineStage,
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
from resume_tailor.infrastructure.gemini_adapter import GeminiResumeLanguageModel
from resume_tailor.infrastructure.llm_cache import InMemoryLlmCache
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


def test_rewrite_that_removes_supported_tool_and_mechanism_is_penalized() -> None:
    source = (
        "Modeled actuator assemblies in SolidWorks with harmonic drives, torque-speed "
        "profiles, encoder resolution, and gear ratios for under 0.1-degree positioning "
        "with minimal backlash."
    )
    evidence = EvidenceItem(
        id="actuator-evidence",
        entity_id="actuator-project",
        source_text=source,
        technologies=["SolidWorks"],
        capabilities=["harmonic drives", "torque-speed profiles", "minimal backlash"],
        outcomes=["under 0.1-degree positioning"],
    )
    rewrite = "Designed actuator gearing for under 0.1-degree positioning."
    estimator = TemplateV1BulletLineEstimator()

    preserved, removed, adjustment = _rewrite_substance_adjustment(
        [evidence],
        rewrite,
        source_line_fit=estimator.estimate(source),
        rewrite_line_fit=estimator.estimate(rewrite),
        material_improvement=True,
    )

    assert "SolidWorks" in removed
    assert "torque-speed profiles" in removed
    assert "minimal backlash" in removed
    assert any("0.1" in term for term in preserved)
    assert adjustment < 0


def test_rewrite_preserving_supported_tool_method_and_result_can_gain_quality_value() -> None:
    source = (
        "Modeled actuator assemblies in SolidWorks using torque-speed profiles for "
        "under 0.1-degree positioning."
    )
    rewrite = (
        "Modeled actuator assemblies in SolidWorks, applying torque-speed profiles "
        "to achieve under 0.1-degree positioning."
    )
    evidence = EvidenceItem(
        id="actuator-evidence",
        entity_id="actuator-project",
        source_text=source,
        technologies=["SolidWorks"],
        capabilities=["torque-speed profiles"],
        outcomes=["under 0.1-degree positioning"],
    )
    estimator = TemplateV1BulletLineEstimator()

    _preserved, removed, adjustment = _rewrite_substance_adjustment(
        [evidence],
        rewrite,
        source_line_fit=estimator.estimate(source),
        rewrite_line_fit=estimator.estimate(rewrite),
        material_improvement=True,
    )

    assert removed == ()
    assert adjustment > 0


class _SdkCandidate:
    finish_reason = "STOP"
    finish_message = "Completed"


class _SdkResponse:
    def __init__(self, *, parsed: object = None, text: str | None = None) -> None:
        self.parsed = parsed
        self.text = text
        self.candidates = [_SdkCandidate()]
        self.usage_metadata = None


class _SdkModels:
    def __init__(self, responses: list[_SdkResponse]) -> None:
        self.responses = responses
        self.calls = 0

    def generate_content(self, **kwargs: object) -> _SdkResponse:
        response = self.responses[self.calls]
        self.calls += 1
        return response


def _sdk_writer(
    responses: list[_SdkResponse],
) -> tuple[GeminiResumeLanguageModel, _SdkModels]:
    models = _SdkModels(responses)

    class Client:
        pass

    class Types:
        @staticmethod
        def GenerateContentConfig(**kwargs: object) -> dict[str, object]:
            return kwargs

    client = Client()
    client.models = models
    adapter = object.__new__(GeminiResumeLanguageModel)
    adapter._client = client
    adapter._types = Types()
    adapter._model = "fake-gemini-model"
    adapter._temperature = 0.1
    adapter._max_output_tokens = 1000
    adapter._bullet_rewrite_max_output_tokens = 1000
    adapter._profile_extraction_max_output_tokens = 1000
    adapter._cache = InMemoryLlmCache(60)
    adapter._telemetry = GenerationTelemetry()
    return adapter, models


def _sdk_rewrite_payload() -> dict[str, object]:
    written = "Built STM32 firmware for validated SPI sensor communication."
    return {
        "rewrites": [
            {
                "source_evidence_ids": ["embedded-evidence"],
                "rewritten_text": written,
                "length_class": "standard",
            }
        ]
    }


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

    accepted, rejected, _diagnostics = service._variant_records(
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


def test_strict_inequality_is_not_weakened_to_within() -> None:
    source = (
        "Modeled custom actuator assemblies in SolidWorks, specifying torque-speed "
        "profiles and gear ratios for under 0.1-degree positioning accuracy."
    )
    rewrite = (
        "Modeled custom actuator assemblies in SolidWorks, specifying torque-speed "
        "profiles and gear ratios to achieve positioning accuracy within 0.1 degrees."
    )
    group = ApprovedEvidenceGroup(
        entry_id="project-entry",
        evidence_ids=["project-evidence"],
        source_texts=[source],
        technologies=["SolidWorks"],
        capabilities=["actuator design", "positioning accuracy"],
        metrics=["under 0.1-degree positioning accuracy"],
        max_rendered_lines=2,
    )
    service = HybridLlmServices(None, 0, 1, False, False, False)

    accepted, rejected, diagnostics = service._variant_records(
        [
            BulletRewrite(
                entry_id="project-entry",
                final_bullet_text=rewrite,
                source_evidence_ids=["project-evidence"],
                preserved_technologies=["SolidWorks"],
                preserved_metrics=[],
                evidence_combined=False,
                confidence=0.9,
                claims=[
                    BulletRewriteClaim(
                        text=rewrite,
                        supporting_evidence_ids=["project-evidence"],
                    )
                ],
            )
        ],
        [group],
        provider="fake",
        model="fake",
        posting=JobPosting(
            id="posting",
            title="Mechanical Engineer",
            description="Design actuator assemblies in SolidWorks.",
        ),
    )

    assert not accepted
    assert rejected[0].validation_status is BulletValidationStatus.REJECTED
    assert any(
        "inequality" in reason
        for reason in diagnostics[0].validator_rejection_details
    )


@pytest.mark.parametrize(
    ("source", "rewrite"),
    [
        (
            "Extracted and normalized sales data from 3 major distributor systems.",
            "Extracted and normalized sales data from three major distributor systems.",
        ),
        (
            "Detected traffic objects with >90% accuracy at 30 FPS.",
            "Detected traffic objects with over 90 percent accuracy at 30 FPS.",
        ),
        (
            "Achieved <2 cm localization error using reviewed sensor arrays.",
            "Achieved under 2 cm localization error using reviewed sensor arrays.",
        ),
    ],
)
def test_safe_numeric_wording_equivalents_are_not_review_gated(
    source: str,
    rewrite: str,
) -> None:
    group = ApprovedEvidenceGroup(
        entry_id="numeric-entry",
        evidence_ids=["numeric-evidence"],
        source_texts=[source],
        max_rendered_lines=2,
    )
    service = HybridLlmServices(None, 0, 1, False, False, False)

    accepted, rejected, diagnostics = service._variant_records(
        [
            BulletRewrite(
                entry_id="numeric-entry",
                final_bullet_text=rewrite,
                source_evidence_ids=["numeric-evidence"],
                evidence_combined=False,
                confidence=0.9,
                claims=[
                    BulletRewriteClaim(
                        text=rewrite,
                        supporting_evidence_ids=["numeric-evidence"],
                    )
                ],
            )
        ],
        [group],
        provider="fake",
        model="fake",
        posting=JobPosting(
            id="numeric-posting",
            title="Engineer",
            description="Validate reviewed engineering metrics.",
        ),
    )

    assert not rejected
    assert accepted[0].validation_status is BulletValidationStatus.VALIDATED
    assert diagnostics[0].normalized_unsupported_terms == []


def test_conservative_semantic_normalization_is_not_review_gated() -> None:
    source = (
        "Normalized reviewed records across business units by defining supported interfaces."
    )
    rewrite = (
        "Normalize reviewed records cross-unit by including the same supported interfaces."
    )
    group = ApprovedEvidenceGroup(
        entry_id="backend-entry",
        evidence_ids=["backend-evidence"],
        source_texts=[source],
        capabilities=["record normalization", "interface definition"],
        max_rendered_lines=2,
    )
    service = HybridLlmServices(None, 0, 1, False, False, False)

    accepted, rejected, diagnostics = service._variant_records(
        [
            BulletRewrite(
                entry_id="backend-entry",
                final_bullet_text=rewrite,
                source_evidence_ids=["backend-evidence"],
                evidence_combined=False,
                confidence=0.9,
                claims=[
                    BulletRewriteClaim(
                        text=rewrite,
                        supporting_evidence_ids=["backend-evidence"],
                    )
                ],
            )
        ],
        [group],
        provider="fake",
        model="fake",
        posting=JobPosting(
            id="backend-posting",
            title="Backend Engineer",
            description="Normalize records and define interfaces.",
        ),
    )

    assert not rejected
    assert accepted[0].validation_status is BulletValidationStatus.VALIDATED
    assert diagnostics[0].normalized_unsupported_terms == []


def test_technical_plural_scope_change_remains_review_gated() -> None:
    source = "Integrated one microprocessor with an embedded microcontroller."
    rewrite = "Integrated microprocessors with embedded microcontrollers."
    group = ApprovedEvidenceGroup(
        entry_id="embedded-entry",
        evidence_ids=["embedded-evidence"],
        source_texts=[source],
        capabilities=["processor integration"],
        max_rendered_lines=2,
    )
    service = HybridLlmServices(None, 0, 1, False, False, False)

    accepted, rejected, diagnostics = service._variant_records(
        [
            BulletRewrite(
                entry_id="embedded-entry",
                final_bullet_text=rewrite,
                source_evidence_ids=["embedded-evidence"],
                evidence_combined=False,
                confidence=0.9,
                claims=[
                    BulletRewriteClaim(
                        text=rewrite,
                        supporting_evidence_ids=["embedded-evidence"],
                    )
                ],
            )
        ],
        [group],
        provider="fake",
        model="fake",
        posting=JobPosting(
            id="posting",
            title="Embedded Engineer",
            description="Integrate embedded processors.",
        ),
    )

    assert not rejected
    assert accepted[0].validation_status is BulletValidationStatus.REVIEW_REQUIRED
    assert "microcontrollers" in diagnostics[0].normalized_unsupported_terms
    assert "microprocessors" in diagnostics[0].singular_plural_scope_comparison


def test_malformed_typed_output_receives_exactly_one_repair() -> None:
    profile, posting = _single_entry_case()
    malformed = LanguageModelError(
        LanguageModelErrorKind.MALFORMED_RESPONSE,
        "Controlled malformed typed output.",
        diagnostic=WriterPipelineIssue(
            code=WriterPipelineFailureCode.MALFORMED_JSON,
            stage=WriterPipelineStage.JSON_PARSING,
            text_present=True,
        ),
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


def test_fake_gemini_response_reaches_parsing_grounding_and_final_competition() -> None:
    profile, posting = _single_entry_case()
    adapter, sdk = _sdk_writer([_SdkResponse(parsed=_sdk_rewrite_payload())])
    service = _service(adapter)
    plan = service.create_plan(profile, posting, TemplateConstraints())

    resume = service.build_document(plan, profile, set())

    assert sdk.calls == 1
    assert resume.hybrid_diagnostic is not None
    assert resume.hybrid_diagnostic.rewritten_bullet_count == 1
    assert resume.hybrid_diagnostic.writer_pipeline_issue is None
    assert resume.hybrid_diagnostic.provider_request_shape is not None
    assert resume.hybrid_diagnostic.provider_request_shape.schema_property_count == 4
    assert resume.hybrid_diagnostic.provider_request_shape.schema_inlined_ref_count == 0
    adapter_timings = {item.stage: item for item in adapter._telemetry.timings()}
    service_timings = {item.stage: item for item in service.telemetry.timings()}
    assert (
        adapter_timings[GenerationStage.PROVIDER_RESPONSE_PARSING].status
        is StageStatus.COMPLETED
    )
    assert service_timings[GenerationStage.CLAIM_VALIDATION].status is StageStatus.COMPLETED


def test_malformed_fake_gemini_json_uses_one_repair_then_reaches_validation() -> None:
    profile, posting = _single_entry_case()
    adapter, sdk = _sdk_writer(
        [
            _SdkResponse(text='{"rewrites":['),
            _SdkResponse(parsed=_sdk_rewrite_payload()),
        ]
    )
    service = _service(adapter)
    plan = service.create_plan(profile, posting, TemplateConstraints())

    resume = service.build_document(plan, profile, set())

    assert sdk.calls == 2
    assert service.telemetry.call_counts().provider_retries == 1
    assert resume.hybrid_diagnostic is not None
    assert resume.hybrid_diagnostic.rewritten_bullet_count == 1
    assert resume.hybrid_diagnostic.writer_pipeline_issue is None


def test_second_malformed_typed_output_falls_back_without_a_third_call() -> None:
    profile, posting = _single_entry_case()
    malformed = LanguageModelError(
        LanguageModelErrorKind.MALFORMED_RESPONSE,
        "Controlled malformed typed output.",
        diagnostic=WriterPipelineIssue(
            code=WriterPipelineFailureCode.MALFORMED_JSON,
            stage=WriterPipelineStage.JSON_PARSING,
            text_present=True,
        ),
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
    assert resume.hybrid_diagnostic.fallback_bullet_count == 2


@pytest.mark.parametrize(
    ("kind", "issue", "expected_status"),
    [
        (
            LanguageModelErrorKind.SAFETY_BLOCKED,
            WriterPipelineIssue(
                code=WriterPipelineFailureCode.SAFETY_BLOCKED_RESPONSE,
                stage=WriterPipelineStage.RESPONSE_EXTRACTION,
                finish_reason="SAFETY",
                candidate_count=1,
                text_present=False,
            ),
            WriterExecutionStatus.PROVIDER_SAFETY_BLOCKED,
        ),
        (
            LanguageModelErrorKind.EMPTY_RESPONSE,
            WriterPipelineIssue(
                code=WriterPipelineFailureCode.EMPTY_PROVIDER_RESPONSE,
                stage=WriterPipelineStage.RESPONSE_EXTRACTION,
                candidate_count=0,
                text_present=False,
            ),
            WriterExecutionStatus.PROVIDER_EMPTY_RESPONSE,
        ),
    ],
)
def test_non_malformed_provider_responses_do_not_trigger_repair(
    kind: LanguageModelErrorKind,
    issue: WriterPipelineIssue,
    expected_status: WriterExecutionStatus,
) -> None:
    profile, posting = _single_entry_case()
    fake = FakeResumeLanguageModel(
        rewrite_bullets=LanguageModelError(
            kind,
            "Controlled provider response failure.",
            diagnostic=issue,
        )
    )
    service = _service(fake)
    plan = service.create_plan(profile, posting, TemplateConstraints())

    resume = service.build_document(plan, profile, set())

    assert fake.calls["rewrite_bullets"] == 1
    assert service.telemetry.call_counts().provider_retries == 0
    assert resume.hybrid_diagnostic is not None
    assert resume.hybrid_diagnostic.writer_execution_status is expected_status
    assert resume.hybrid_diagnostic.writer_pipeline_issue == issue


def test_unsupported_claim_reaches_grounding_validation_not_provider_failure() -> None:
    profile, posting = _single_entry_case()
    unsupported = (
        "Built STM32 firmware on AWS and validated SPI sensor communication "
        "with a 40% latency reduction."
    )
    fake = FakeResumeLanguageModel(
        rewrite_bullets=BulletRewriteResult(
            metadata=metadata(LlmOperation.REWRITE_BULLETS),
            output=BulletRewriteOutput(
                bullets=[
                    BulletRewrite(
                        entry_id="embedded-entry",
                        final_bullet_text=unsupported,
                        source_evidence_ids=["embedded-evidence"],
                        preserved_technologies=["STM32", "SPI", "AWS"],
                        preserved_metrics=["40%"],
                        evidence_combined=False,
                        confidence=0.95,
                        claims=[
                            BulletRewriteClaim(
                                text=unsupported,
                                supporting_evidence_ids=["embedded-evidence"],
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

    assert fake.calls["rewrite_bullets"] == 1
    assert service.telemetry.call_counts().provider_retries == 0
    assert service.telemetry.call_counts().claim_validations >= 1
    assert resume.hybrid_diagnostic is not None
    assert resume.hybrid_diagnostic.writer_execution_status is (
        WriterExecutionStatus.ALL_GENERATED_VARIANTS_REJECTED
    )
    issue = resume.hybrid_diagnostic.writer_pipeline_issue
    assert issue is not None
    assert issue.code is WriterPipelineFailureCode.CLAIM_GROUNDING_REJECTION
    assert issue.stage is WriterPipelineStage.CLAIM_VALIDATION
    assert "provider" not in resume.hybrid_diagnostic.writing_reason.casefold()


def test_invalid_provider_mapping_does_not_discard_valid_sibling() -> None:
    profile, posting = _single_entry_case()
    valid = _single_entry_rewrite().output.bullets[0]
    fake = FakeResumeLanguageModel(
        rewrite_bullets=BulletRewriteResult(
            metadata=metadata(LlmOperation.REWRITE_BULLETS),
            output=BulletRewriteOutput(bullets=[valid]),
            mapping_outcomes=[
                ProviderRewriteMappingOutcome(
                        rewrite_index=0,
                        evidence_ids=["unknown-evidence"],
                        rewritten_text="Built an unauthorized cloud deployment.",
                        mapping_status=(
                            ProviderRewriteMappingStatus.REJECTED_UNKNOWN_EVIDENCE
                        ),
                        failure_codes=[GroundingFailureCode.UNKNOWN_EVIDENCE],
                        failure_details=[
                            "provider rewrite 0 references unknown evidence IDs"
                        ],
                ),
                ProviderRewriteMappingOutcome(
                        rewrite_index=1,
                        evidence_ids=["embedded-evidence"],
                        rewritten_text=valid.final_bullet_text,
                        mapping_status=ProviderRewriteMappingStatus.MAPPED,
                        entry_id="embedded-entry",
                        mapped_bullet_index=0,
                ),
            ],
        )
    )
    service = _service(fake)
    plan = service.create_plan(profile, posting, TemplateConstraints())

    resume = service.build_document(plan, profile, set())

    assert resume.hybrid_diagnostic is not None
    diagnostic = resume.hybrid_diagnostic
    assert diagnostic.bullet_variants
    assert diagnostic.writer_execution_status is (
        WriterExecutionStatus.WRITER_PARTIALLY_SUCCEEDED
    )
    assert [item.provider_contract_mapping_result for item in diagnostic.rewrite_diagnostics] == [
        ProviderRewriteMappingStatus.REJECTED_UNKNOWN_EVIDENCE,
        ProviderRewriteMappingStatus.MAPPED,
    ]
    assert "valid_sibling_retained" in diagnostic.rewrite_diagnostics[0].batch_effect
    assert "continued_to_variant_competition" in diagnostic.rewrite_diagnostics[1].batch_effect


def test_zero_mappable_rewrites_uses_complete_source_fallback() -> None:
    profile, posting = _single_entry_case()
    fake = FakeResumeLanguageModel(
        rewrite_bullets=BulletRewriteResult(
            metadata=metadata(LlmOperation.REWRITE_BULLETS),
            output=BulletRewriteOutput(),
            mapping_outcomes=[
                ProviderRewriteMappingOutcome(
                        rewrite_index=0,
                        evidence_ids=["unknown-evidence"],
                        rewritten_text="Built an unauthorized cloud deployment.",
                        mapping_status=(
                            ProviderRewriteMappingStatus.REJECTED_UNKNOWN_EVIDENCE
                        ),
                        failure_codes=[GroundingFailureCode.UNKNOWN_EVIDENCE],
                        failure_details=[
                            "provider rewrite 0 references unknown evidence IDs"
                        ],
                )
            ],
        )
    )
    service = _service(fake)
    plan = service.create_plan(profile, posting, TemplateConstraints())

    resume = service.build_document(plan, profile, set())

    assert resume.hybrid_diagnostic is not None
    diagnostic = resume.hybrid_diagnostic
    assert diagnostic.writer_execution_status is (
        WriterExecutionStatus.ALL_GENERATED_VARIANTS_REJECTED
    )
    assert diagnostic.rewritten_bullet_count == 0
    assert diagnostic.deterministic_fallback_used is True
    assert diagnostic.rewrite_diagnostics[0].batch_effect == (
        "batch_source_fallback_no_usable_validated_rewrites"
    )


def test_writer_diagnostics_do_not_include_environment_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "diagnostic-secret-must-not-appear"
    monkeypatch.setenv("GEMINI_API_KEY", secret)
    profile, posting = _single_entry_case()
    service = _service(FakeResumeLanguageModel(rewrite_bullets=_single_entry_rewrite()))
    plan = service.create_plan(profile, posting, TemplateConstraints())

    resume = service.build_document(plan, profile, set())

    assert resume.hybrid_diagnostic is not None
    assert secret not in resume.hybrid_diagnostic.model_dump_json()


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
    assert resume.hybrid_diagnostic.writer_pipeline_issue is not None
    assert (
        resume.hybrid_diagnostic.writer_pipeline_issue.code
        is WriterPipelineFailureCode.NO_MATERIAL_IMPROVEMENT
    )


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
            ),
            EvidenceItem(
                id="backend-validation-evidence",
                entity_id="backend-entry",
                source_text=(
                    "Validated PostgreSQL transaction behavior through Python integration tests."
                ),
                technologies=["Python", "PostgreSQL"],
                capabilities=["integration testing", "transaction validation"],
            ),
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

    assert source in {
        bullet.text for bullet in resume.experience_bullets["backend-entry"]
    }
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
        maximum_selected_bullets=2,
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

    written = "Built Python services that exposed APIs with reviewed governance controls."
    testing_written = "Evaluated production workflow behavior with automated tests."
    fake = FakeResumeLanguageModel(
        rewrite_bullets=BulletRewriteResult(
            metadata=metadata(LlmOperation.REWRITE_BULLETS),
            output=BulletRewriteOutput(
                bullets=[
                    BulletRewrite(
                        entry_id="writer-alternative",
                        final_bullet_text=written,
                        source_evidence_ids=["writer-alternative-evidence"],
                        preserved_technologies=["Python"],
                        evidence_combined=False,
                        confidence=0.95,
                        claims=[
                            BulletRewriteClaim(
                                text=written,
                                supporting_evidence_ids=["writer-alternative-evidence"],
                            )
                        ],
                    ),
                    BulletRewrite(
                        entry_id="writer-alternative",
                        final_bullet_text=testing_written,
                        source_evidence_ids=["writer-alternative-production-evidence"],
                        evidence_combined=False,
                        confidence=0.95,
                        claims=[
                            BulletRewriteClaim(
                                text=testing_written,
                                supporting_evidence_ids=[
                                    "writer-alternative-production-evidence"
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
    assert any(
        item.selected_entry_id == "writer-alternative"
        and item.choice_changed_after_validated_writing
        for item in final.composition_diagnostic.portfolio_marginal_comparisons
    )
    assert {bullet.text for bullet in final.experience_bullets["writer-alternative"]} == {
        written,
        "Validated automated testing for production workflows.",
    }
    assert final.hybrid_diagnostic.rewritten_bullet_count == 1


def test_weak_rewrite_does_not_force_alternative_experience_package() -> None:
    profile, posting = _writer_replacement_case()
    source = next(
        item.source_text
        for item in profile.evidence
        if item.id == "writer-alternative-evidence"
    )
    cosmetic = source.replace("Built", "Developed", 1)
    fake = FakeResumeLanguageModel(
        rewrite_bullets=BulletRewriteResult(
            metadata=metadata(LlmOperation.REWRITE_BULLETS),
            output=BulletRewriteOutput(
                bullets=[
                    BulletRewrite(
                        entry_id="writer-alternative",
                        final_bullet_text=cosmetic,
                        source_evidence_ids=["writer-alternative-evidence"],
                        preserved_technologies=["Python"],
                        evidence_combined=False,
                        confidence=0.95,
                        claims=[
                            BulletRewriteClaim(
                                text=cosmetic,
                                supporting_evidence_ids=["writer-alternative-evidence"],
                            )
                        ],
                    )
                ]
            ),
        )
    )
    composer = DeterministicResumeComposer(
        ExactFixedPageFit(),
        bounds=CompositionSearchBounds(
            maximum_selected_bullets=2,
            maximum_selected_entries=1,
            maximum_experience_entries=1,
            maximum_project_entries=0,
        ),
    )
    service = TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
        hybrid_services=HybridLlmServices(fake, 0, 2, False, False, True),
        resume_composer=composer,
    )

    final = service.build_document(
        service.create_plan(profile, posting, TemplateConstraints()),
        profile,
        set(),
    )

    assert final.composition_diagnostic is not None
    assert final.composition_diagnostic.selected_experience_ids == ["strong-source"]
    assert final.hybrid_diagnostic is not None
    assert final.hybrid_diagnostic.rewritten_bullet_count == 0


def test_real_profile_shortlist_is_bounded_and_does_not_transmit_employer_identity() -> None:
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
    assert len({entry_id for entry_id in entry_ids if entry_id.startswith("experience-")}) >= 2
    assert len(request.groups) <= 24
    assert max(Counter(group.entry_id for group in request.groups).values()) <= 4
    direct_count = sum(
        group.relationship_tier is EvidenceRelationship.DIRECT for group in request.groups
    )
    adjacent_count = sum(
        group.relationship_tier is EvidenceRelationship.ADJACENT for group in request.groups
    )
    assert direct_count > 0
    assert direct_count + adjacent_count >= len(request.groups) // 2
    assert resume.hybrid_diagnostic is not None
    shortlisted = [
        item for item in resume.hybrid_diagnostic.writer_shortlist if item.selected
    ]
    assert len({item.entry_id for item in shortlisted}) >= 2
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
            ),
            EvidenceItem(
                id="embedded-test-evidence",
                entity_id="embedded-entry",
                source_text="Debugged STM32 timing faults with reviewed SPI traces.",
                technologies=["STM32", "SPI"],
                capabilities=["firmware debugging", "timing validation"],
            ),
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
                source_text=(
                    "Built services in Python that exposed APIs and implemented reviewed "
                    "governance controls."
                ),
                technologies=["Python"],
                capabilities=["API", "APIs", "governance controls"],
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
                    "Designed API architecture for backend services."
                ),
                capabilities=[
                    "API architecture",
                    "backend services",
                    "ownership",
                ],
            ),
            EvidenceItem(
                id="strong-source-release-evidence",
                entity_id="strong-source",
                source_text="Reviewed test evidence for backend service releases.",
                capabilities=["testing", "release evidence"],
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
