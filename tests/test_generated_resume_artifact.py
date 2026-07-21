from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO

from docx import Document

from resume_tailor.application.generated_artifact import (
    ResumeGenerationConfiguration,
    prepare_artifact_download,
)
from resume_tailor.application.generation_diagnostics import GenerationTelemetry
from resume_tailor.application.llm_services import HybridLlmServices
from resume_tailor.application.resume_composition import DeterministicResumeComposer
from resume_tailor.application.services import TailorResumeService
from resume_tailor.application.workflow_state import (
    invalidate_posting_derived_workflow,
    invalidate_profile_derived_workflow,
)
from resume_tailor.domain.generated_artifact import GeneratedResumeArtifact, GenerationStage
from resume_tailor.domain.hybrid_resume import (
    RESUME_WRITING_CONTRACT_VERSION,
    RESUME_WRITING_POLICY_VERSION,
)
from resume_tailor.domain.llm_models import (
    BulletRewrite,
    BulletRewriteOutput,
    BulletRewriteResult,
    LlmOperation,
)
from resume_tailor.domain.models import JobPosting, MasterProfile, TemplateConstraints
from resume_tailor.domain.resume_composition import RESUME_COMPOSITION_CONTRACT_VERSION
from resume_tailor.infrastructure.artifact_rendering import TemplateV1ArtifactRenderer
from resume_tailor.infrastructure.composition_page_fit import TemplateV1PageFitEvaluator
from resume_tailor.infrastructure.optimization import (
    DeterministicResumeOptimizer,
    EvidenceBoundResumeWriter,
)
from resume_tailor.infrastructure.rendering import PageCountMeasurement
from resume_tailor.infrastructure.template_v1 import TEMPLATE_V1_DOCX_SHA256, TEMPLATE_V1_ID
from tests.fakes import FakeResumeLanguageModel, metadata


class _FakeArtifactRenderer:
    def __init__(self, payload: bytes = b"PK\x03\x04controlled-docx") -> None:
        self.payload = payload
        self.calls = 0

    def render_docx_bytes(self, resume: object) -> bytes:
        self.calls += 1
        return self.payload


class _FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class _BatchPageProvider:
    def __init__(self) -> None:
        self.batch_calls = 0
        self.single_calls = 0

    def measure(self, docx_path: object) -> PageCountMeasurement:
        self.single_calls += 1
        raise AssertionError("Finalists must use the bounded batch pagination path")

    def measure_many(self, docx_paths: list[object]) -> list[PageCountMeasurement]:
        self.batch_calls += 1
        return [
            PageCountMeasurement(
                page_count=1,
                provider="controlled batch exact provider",
                confidence="exact",
                exact=True,
            )
            for _path in docx_paths
        ]


def _profile() -> MasterProfile:
    return MasterProfile.model_validate(
        {
            "id": "artifact-profile",
            "user_id": "artifact-user",
            "display_name": "Artifact Candidate",
            "experiences": [
                {
                    "id": "firmware-entry",
                    "title": "Firmware Developer",
                    "kind": "experience",
                }
            ],
            "evidence": [
                {
                    "id": "firmware-evidence",
                    "entity_id": "firmware-entry",
                    "source_text": "Built and validated embedded firmware.",
                }
            ],
        }
    )


def _posting(description: str = "Build and validate embedded firmware.") -> JobPosting:
    return JobPosting(
        id="artifact-posting",
        title="Firmware Developer",
        description=description,
    )


def _configuration(
    *,
    template_identity: str | None = None,
    writing_policy_version: str = RESUME_WRITING_POLICY_VERSION,
    provider: str = "gemini",
    model: str = "controlled-model",
) -> ResumeGenerationConfiguration:
    return ResumeGenerationConfiguration(
        template_identity=(template_identity or f"{TEMPLATE_V1_ID}:{TEMPLATE_V1_DOCX_SHA256}"),
        composition_contract_version=RESUME_COMPOSITION_CONTRACT_VERSION,
        writing_policy_version=writing_policy_version,
        writing_contract_version=RESUME_WRITING_CONTRACT_VERSION,
        feature_flags={"bullet_rewrite": False},
        provider=provider,
        model=model,
        provider_timeout_seconds=30,
        provider_retry_count=2,
    )


def _service(
    renderer: _FakeArtifactRenderer,
    *,
    configuration: ResumeGenerationConfiguration | None = None,
    telemetry: GenerationTelemetry | None = None,
) -> TailorResumeService:
    return TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
        artifact_renderer=renderer,
        generation_configuration=configuration or _configuration(),
        telemetry=telemetry,
    )


def _artifact() -> tuple[GeneratedResumeArtifact, _FakeArtifactRenderer, TailorResumeService]:
    renderer = _FakeArtifactRenderer()
    service = _service(renderer)
    profile = _profile()
    posting = _posting()
    service.start_generation()
    plan = service.create_plan(profile, posting, TemplateConstraints())
    artifact = service.build_generated_artifact(
        plan,
        profile,
        set(),
        now=lambda: datetime(2026, 7, 19, tzinfo=UTC),
    )
    return artifact, renderer, service


def test_completed_build_stores_final_docx_bytes_and_reuses_identical_artifact() -> None:
    artifact, renderer, service = _artifact()

    reused = service.build_generated_artifact(
        artifact.final_validated_plan,
        _profile(),
        set(),
        existing_artifact=artifact,
    )

    assert artifact.docx_bytes == renderer.payload
    assert reused is artifact
    assert renderer.calls == 1


def test_download_returns_exact_stored_bytes_and_runs_zero_generation_calls() -> None:
    artifact, renderer, service = _artifact()
    before = artifact.call_counts.model_copy(deep=True)

    download = prepare_artifact_download(artifact, clock=service.telemetry.clock)

    assert download.docx_bytes is artifact.docx_bytes
    assert download.docx_bytes == renderer.payload
    assert download.generation_call_counts.model_dump() == {
        "profile_loads": 0,
        "posting_normalizations": 0,
        "evidence_retrievals": 0,
        "deterministic_plans": 0,
        "semantic_plans": 0,
        "provider_calls": 0,
        "provider_retries": 0,
        "claim_validations": 0,
        "composition_searches": 0,
        "docx_renders": 0,
        "pagination_attempts": 0,
    }
    assert artifact.call_counts == before
    assert renderer.calls == 1


def test_unrelated_rerun_retains_completed_artifact() -> None:
    artifact, _renderer, _service = _artifact()
    state: dict[str, object] = {
        "generated_resume_artifact": artifact,
        "unrelated_navigation_value": "Profile",
    }

    state["unrelated_navigation_value"] = "Settings / Diagnostics"

    assert state["generated_resume_artifact"] is artifact


def test_posting_and_profile_changes_invalidate_completed_artifact_state() -> None:
    artifact, _renderer, _service = _artifact()
    posting_state: dict[str, object] = {
        "posting": artifact.final_validated_plan.posting,
        "generated_resume_artifact": artifact,
    }
    profile_state: dict[str, object] = {
        "generated_resume_artifact": artifact,
    }

    invalidate_posting_derived_workflow(posting_state)
    invalidate_profile_derived_workflow(profile_state)

    assert "generated_resume_artifact" not in posting_state
    assert "generated_resume_artifact" not in profile_state


def test_artifact_fingerprint_invalidates_every_material_identity_input() -> None:
    profile = _profile()
    plan_service = _service(_FakeArtifactRenderer())
    plan = plan_service.create_plan(profile, _posting(), TemplateConstraints())
    baseline = plan_service.expected_artifact_fingerprint(plan, profile, set())
    changed_profile = profile.model_copy(update={"display_name": "Changed Candidate"})
    changed_posting = plan.posting.model_copy(
        update={"description": "Build safety-critical embedded controls."}
    )
    changed_plan = plan.model_copy(update={"posting": changed_posting})

    assert plan_service.expected_artifact_fingerprint(plan, changed_profile, set()) != baseline
    assert plan_service.expected_artifact_fingerprint(changed_plan, profile, set()) != baseline
    assert (
        _service(
            _FakeArtifactRenderer(),
            configuration=_configuration(writing_policy_version="changed-writing-policy"),
        ).expected_artifact_fingerprint(plan, profile, set())
        != baseline
    )
    assert (
        _service(
            _FakeArtifactRenderer(),
            configuration=_configuration(provider="gemini", model="changed-model"),
        ).expected_artifact_fingerprint(plan, profile, set())
        != baseline
    )
    assert (
        _service(
            _FakeArtifactRenderer(),
            configuration=_configuration(template_identity="template-v1:changed"),
        ).expected_artifact_fingerprint(plan, profile, set())
        != baseline
    )


def test_stage_timings_are_typed_and_include_every_production_stage() -> None:
    artifact, _renderer, _service = _artifact()

    assert {timing.stage for timing in artifact.stage_timings} == set(GenerationStage)
    assert all(timing.elapsed_seconds >= 0 for timing in artifact.stage_timings)


def test_fake_clock_exposes_exact_stage_and_download_timings() -> None:
    clock = _FakeClock()
    telemetry = GenerationTelemetry(clock)

    with telemetry.measure(GenerationStage.EVIDENCE_RETRIEVAL):
        clock.advance(1.25)
    artifact, _renderer, _service = _artifact()
    clock.advance(0.5)
    download = prepare_artifact_download(artifact, clock=clock)

    assert telemetry.elapsed(GenerationStage.EVIDENCE_RETRIEVAL) == 1.25
    assert download.preparation_timing.elapsed_seconds == 0


def test_one_build_uses_one_pagination_batch_and_download_never_repeats_it() -> None:
    telemetry = GenerationTelemetry()
    provider = _BatchPageProvider()
    renderer = _FakeArtifactRenderer()
    service = TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
        resume_composer=DeterministicResumeComposer(
            TemplateV1PageFitEvaluator(provider, telemetry=telemetry),
            telemetry=telemetry,
        ),
        artifact_renderer=renderer,
        generation_configuration=_configuration(),
        telemetry=telemetry,
    )
    profile = _profile()
    plan = service.create_plan(profile, _posting(), TemplateConstraints())

    artifact = service.build_generated_artifact(plan, profile, set())
    batch_calls_after_build = provider.batch_calls
    download = prepare_artifact_download(artifact, clock=telemetry.clock)

    assert provider.batch_calls == 1
    assert provider.single_calls == 0
    assert artifact.call_counts.pagination_attempts == 1
    assert artifact.pagination_diagnostic.attempt_count == 1
    assert download.generation_call_counts.pagination_attempts == 0
    assert provider.batch_calls == batch_calls_after_build


def test_approved_wording_rebuild_owns_fresh_pagination_and_reuses_writer_cache() -> None:
    profile = MasterProfile.model_validate(
        {
            "id": "approved-profile",
            "user_id": "approved-user",
            "display_name": "Approved Candidate",
            "experiences": [
                {"id": "controls-entry", "title": "Controls Developer", "kind": "experience"}
            ],
            "evidence": [
                {
                    "id": "control-evidence",
                    "entity_id": "controls-entry",
                    "source_text": "Developed STM32 motor controls using SPI feedback.",
                    "technologies": ["STM32", "SPI"],
                    "capabilities": ["motor controls"],
                },
                {
                    "id": "test-evidence",
                    "entity_id": "controls-entry",
                    "source_text": "Validated STM32 control timing at 30 Hz.",
                    "technologies": ["STM32"],
                    "outcomes": ["30 Hz"],
                },
            ],
        }
    )
    posting = JobPosting(
        id="approved-posting",
        title="Embedded Controls Developer",
        description="Build STM32 motor controls and validate SPI timing.",
    )
    rewrites = [
        BulletRewrite(
            entry_id="controls-entry",
            final_bullet_text="Built STM32 motor controls with SPI feedback.",
            source_evidence_ids=["control-evidence"],
            preserved_technologies=["STM32", "SPI"],
            evidence_combined=False,
            support="strongly_implied",
            confidence=0.9,
        ),
        BulletRewrite(
            entry_id="controls-entry",
            final_bullet_text="Validated STM32 control timing at 30 Hz.",
            source_evidence_ids=["test-evidence"],
            preserved_technologies=["STM32"],
            preserved_metrics=["30 Hz"],
            evidence_combined=False,
            support="strongly_implied",
            confidence=0.9,
        ),
    ]
    fake = FakeResumeLanguageModel(
        rewrite_bullets=BulletRewriteResult(
            metadata=metadata(LlmOperation.REWRITE_BULLETS),
            output=BulletRewriteOutput(bullets=rewrites),
        )
    )
    telemetry = GenerationTelemetry()
    page_provider = _BatchPageProvider()
    renderer = TemplateV1ArtifactRenderer()
    hybrid = HybridLlmServices(fake, 0, 4, False, False, True)
    service = TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
        hybrid_services=hybrid,
        resume_composer=DeterministicResumeComposer(
            TemplateV1PageFitEvaluator(page_provider, telemetry=telemetry),
            telemetry=telemetry,
        ),
        artifact_renderer=renderer,
        generation_configuration=_configuration().model_copy(
            update={"feature_flags": {"bullet_rewrite": True}}
        ),
        telemetry=telemetry,
    )
    service.start_generation()
    plan = service.create_plan(profile, posting, TemplateConstraints())
    initial = service.build_generated_artifact(plan, profile, set())
    review_ids = {
        variant.variant_id
        for variant in initial.writing_diagnostic.bullet_variants
        if variant.validation_status.value == "review_required"
    }
    assert len(review_ids) == 2

    rebuilt = service.build_generated_artifact(
        plan,
        profile,
        review_ids,
        existing_artifact=initial,
    )
    download = prepare_artifact_download(rebuilt, clock=telemetry.clock)

    assert fake.calls["rewrite_bullets"] == 1
    assert rebuilt.pagination_diagnostic.attempt_count <= 1
    assert rebuilt.call_counts.pagination_attempts <= 1
    rebuilt_docx = Document(BytesIO(rebuilt.docx_bytes))
    rendered_text = "\n".join(paragraph.text for paragraph in rebuilt_docx.paragraphs)
    assert "Built STM32 motor controls with SPI feedback." in rendered_text
    assert "Validated STM32 control timing at 30 Hz." in rendered_text
    assert download.docx_bytes is rebuilt.docx_bytes
    assert not any(download.generation_call_counts.model_dump().values())
