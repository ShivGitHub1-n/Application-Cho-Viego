from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from docx import Document
from streamlit.testing.v1 import AppTest

import resume_tailor.infrastructure.dependencies as dependencies
from resume_tailor.application.generated_artifact import (
    ResumeGenerationConfiguration,
    prepare_artifact_download,
)
from resume_tailor.application.generation_diagnostics import GenerationTelemetry
from resume_tailor.application.job_intake import build_job_posting
from resume_tailor.application.llm_services import HybridLlmServices
from resume_tailor.application.resume_composition import DeterministicResumeComposer
from resume_tailor.application.services import TailorResumeService
from resume_tailor.application.workflow_state import (
    GENERATED_RESUME_ARTIFACT_VERSION_KEY,
    GENERATED_RESUME_GENERATED_APPROVALS_KEY,
    GENERATED_RESUME_REBUILD_IN_PROGRESS_KEY,
    GENERATED_RESUME_REBUILD_REQUIRED_KEY,
    GENERATED_RESUME_REVIEW_STATE_KEY,
    GENERATED_RESUME_WORDING_DIRTY_KEY,
    GeneratedResumeReviewState,
)
from resume_tailor.domain.hybrid_resume import (
    RESUME_WRITING_CONTRACT_VERSION,
    RESUME_WRITING_POLICY_VERSION,
    BulletValidationStatus,
    WriterExecutionStatus,
)
from resume_tailor.domain.models import MasterProfile, TemplateConstraints
from resume_tailor.domain.requirement_ranking import RequirementAuthority
from resume_tailor.domain.resume_composition import RESUME_COMPOSITION_CONTRACT_VERSION
from resume_tailor.infrastructure.artifact_rendering import TemplateV1ArtifactRenderer
from resume_tailor.infrastructure.composition_page_fit import TemplateV1PageFitEvaluator
from resume_tailor.infrastructure.gemini_adapter import GeminiResumeLanguageModel
from resume_tailor.infrastructure.llm_cache import InMemoryLlmCache
from resume_tailor.infrastructure.optimization import (
    DeterministicResumeOptimizer,
    EvidenceBoundResumeWriter,
)
from resume_tailor.infrastructure.profile_repository import SQLiteMasterProfileRepository
from resume_tailor.infrastructure.rendering import PageCountVerificationError
from resume_tailor.infrastructure.template_v1 import (
    TEMPLATE_V1_DOCX_SHA256,
    TEMPLATE_V1_ID,
)

ROOT = Path(__file__).resolve().parents[1]
PROFILE_FIXTURE = ROOT / "tests" / "fixtures" / "world_star_tech_production_profile.json"
POSTING_FIXTURE = (
    ROOT / "tests" / "fixtures" / "world_star_tech_embedded_systems_engineer.txt"
)
RESPONSE_FIXTURE = ROOT / "tests" / "fixtures" / "captured_gemini_writer_response.json"


class _SdkCandidate:
    finish_reason = "STOP"
    finish_message = "Completed"


class _SdkResponse:
    def __init__(self, parsed: object) -> None:
        self.parsed = parsed
        self.text = None
        self.candidates = [_SdkCandidate()]
        self.usage_metadata = None


class _SdkModels:
    def __init__(self, parsed: object) -> None:
        self.parsed = parsed
        self.calls = 0

    def generate_content(self, **_kwargs: object) -> _SdkResponse:
        self.calls += 1
        return _SdkResponse(self.parsed)


class _FailingExactPageProvider:
    def measure(self, docx_path: Path) -> object:
        raise PageCountVerificationError(
            f"Controlled exact pagination failure for {docx_path.name}"
        )


class _SessionState(dict[str, object]):
    widget_keys: set[str] = set()

    def __setitem__(self, key: str, value: object) -> None:
        if key in self.widget_keys:
            raise AssertionError(f"illegal widget mutation: {key}")
        super().__setitem__(key, value)


class _Status:
    def __enter__(self) -> _Status:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def update(self, **_kwargs: object) -> None:
        return None

    def write(self, _value: object) -> None:
        return None


class _StreamlitStub:
    def __init__(self, state: _SessionState) -> None:
        self.session_state = state

    def status(self, *_args: object, **_kwargs: object) -> _Status:
        return _Status()


def _captured_writer() -> tuple[GeminiResumeLanguageModel, _SdkModels]:
    models = _SdkModels(json.loads(RESPONSE_FIXTURE.read_text(encoding="utf-8")))

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
    adapter._model = "captured-gemini-response"
    adapter._temperature = 0.1
    adapter._max_output_tokens = 4_096
    adapter._bullet_rewrite_max_output_tokens = 4_096
    adapter._profile_extraction_max_output_tokens = 4_096
    adapter._cache = InMemoryLlmCache(60)
    adapter._telemetry = GenerationTelemetry()
    return adapter, models


def _production_case() -> tuple[
    TailorResumeService,
    MasterProfile,
    object,
    _SdkModels,
]:
    profile = MasterProfile.model_validate_json(PROFILE_FIXTURE.read_text(encoding="utf-8"))
    posting = build_job_posting(
        "world-star-tech-embedded-systems-engineer",
        "Embedded Systems Engineer",
        POSTING_FIXTURE.read_text(encoding="utf-8"),
    )
    adapter, models = _captured_writer()
    telemetry = GenerationTelemetry()
    service = TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
        hybrid_services=HybridLlmServices(adapter, 0, 2, False, False, True),
        resume_composer=DeterministicResumeComposer(
            TemplateV1PageFitEvaluator(
                _FailingExactPageProvider(),
                telemetry=telemetry,
            ),
            telemetry=telemetry,
        ),
        artifact_renderer=TemplateV1ArtifactRenderer(),
        generation_configuration=ResumeGenerationConfiguration(
            template_identity=f"{TEMPLATE_V1_ID}:{TEMPLATE_V1_DOCX_SHA256}",
            composition_contract_version=RESUME_COMPOSITION_CONTRACT_VERSION,
            writing_policy_version=RESUME_WRITING_POLICY_VERSION,
            writing_contract_version=RESUME_WRITING_CONTRACT_VERSION,
            feature_flags={"bullet_rewrite": True},
            provider="gemini",
            model="captured-gemini-response",
            provider_timeout_seconds=30,
            provider_retry_count=0,
        ),
        telemetry=telemetry,
    )
    return service, profile, posting, models


def test_captured_production_streamlit_route_selects_density_and_truthful_coverage(
    monkeypatch,
) -> None:
    from resume_tailor.frontend import app as frontend_app

    service, profile, posting, models = _production_case()
    service.start_generation()
    plan = service.create_plan(profile, posting, TemplateConstraints())
    state = _SessionState()
    monkeypatch.setattr(frontend_app, "st", _StreamlitStub(state))

    artifact = frontend_app._build_and_store_resume_artifact(
        service,
        plan,
        profile,
        set(),
    )
    diagnostic = artifact.composition_diagnostic
    writing = artifact.writing_diagnostic

    assert models.calls == 1
    assert artifact.provider_diagnostic.call_count == 1
    assert artifact.provider_diagnostic.retry_count == 0
    assert diagnostic is not None
    assert diagnostic.final_utilization_ratio >= 0.90
    assert diagnostic.final_utilization_ratio <= 0.95
    assert writing.writer_execution_status is WriterExecutionStatus.SOURCE_VARIANTS_SCORED_BETTER
    assert all(not variant.selected for variant in writing.bullet_variants)
    assert all(
        count >= 2
        for entry_id, count in diagnostic.bullet_counts.items()
        if entry_id.startswith("exp-")
    )
    assert "Mechanical Design & CAD" in diagnostic.selected_skill_category_labels
    assert "proj-robotic-arm" in diagnostic.selected_project_ids
    assert "proj-ventilation" in diagnostic.selected_project_ids
    assert all(
        "Employer identity was not scored" in item.final_reason
        for item in diagnostic.experience_package_selections
    )

    coverage_texts = [item.text for item in diagnostic.requirement_coverage]
    assert "Embedded Systems Engineer" not in coverage_texts
    assert all(
        item.authority is not RequirementAuthority.INCIDENTAL
        for item in diagnostic.requirement_coverage
    )
    assert not any(
        phrase in text.casefold()
        for text in coverage_texts
        for phrase in (
            "company overview",
            "markham",
            "basketball",
            "compensation",
            "health",
            "dynamic, ambitious team",
        )
    )
    gui_coverage = [
        item
        for item in diagnostic.requirement_coverage
        if "gui" in item.text.casefold() or "graphical user interface" in item.text.casefold()
    ]
    assert len(gui_coverage) == 2
    assert all(not item.fully_covered for item in gui_coverage)
    assert all(
        not component.supporting_evidence_ids
        for item in gui_coverage
        for component in item.component_matches
        if component.normalized_component == "gui"
    )
    degree = next(
        item
        for item in diagnostic.requirement_coverage
        if "degree in engineering" in item.text.casefold()
    )
    assert degree.fully_covered is True
    assert degree.satisfied_by_profile_sections == ["education"]
    assert degree.supporting_evidence_ids == []
    assert all(item.component_matches for item in diagnostic.requirement_coverage)

    assert len(diagnostic.candidates_excluded_by_search_bounds) == 2
    assert all(
        item.entry_id
        and item.package_bullet_count
        and item.relevance_score
        and item.page_cost
        and item.pruning_bound
        and item.would_improve_density is not None
        for item in diagnostic.candidates_excluded_by_search_bounds
    )


def test_captured_approved_wording_rebuild_and_download_make_no_generation_calls(
    monkeypatch,
) -> None:
    from resume_tailor.frontend import app as frontend_app

    service, profile, posting, models = _production_case()
    service.start_generation()
    plan = service.create_plan(profile, posting, TemplateConstraints())
    state = _SessionState()
    monkeypatch.setattr(frontend_app, "st", _StreamlitStub(state))
    initial = frontend_app._build_and_store_resume_artifact(
        service,
        plan,
        profile,
        set(),
    )
    review_variants = [
        variant
        for variant in initial.writing_diagnostic.bullet_variants
        if variant.validation_status is BulletValidationStatus.REVIEW_REQUIRED
    ]
    assert len(review_variants) == 2

    state["generated_content_reviewed"] = True
    state.widget_keys.add("generated_content_reviewed")
    rebuilt = frontend_app._build_and_store_resume_artifact(
        service,
        plan,
        profile,
        {variant.variant_id for variant in review_variants},
    )

    assert models.calls == 1
    assert rebuilt.provider_diagnostic.call_count == 0
    assert rebuilt.pagination_diagnostic.attempt_count <= 1
    rendered_text = "\n".join(
        paragraph.text
        for paragraph in Document(BytesIO(rebuilt.docx_bytes)).paragraphs
    )
    assert all(variant.rewritten_text in rendered_text for variant in review_variants)

    state.widget_keys.clear()
    frontend_app._apply_pending_generated_content_review_reset()
    assert state["generated_content_reviewed"] is False
    state["generated_content_reviewed"] = True

    download = prepare_artifact_download(rebuilt, clock=service.telemetry.clock)
    assert download.docx_bytes is rebuilt.docx_bytes
    assert not any(download.generation_call_counts.model_dump().values())


def test_actual_streamlit_rebuild_state_machine_keeps_approved_snapshot(
    monkeypatch, tmp_path
) -> None:
    profile = MasterProfile.model_validate_json(PROFILE_FIXTURE.read_text(encoding="utf-8"))
    repository = SQLiteMasterProfileRepository(tmp_path / "production-profile.sqlite3")
    repository.save(profile)
    service, _profile, _posting, models = _production_case()
    monkeypatch.setattr(dependencies, "create_profile_repository", lambda: repository)
    monkeypatch.setattr(dependencies, "create_tailor_service", lambda: service)

    app_path = ROOT / "src" / "resume_tailor" / "frontend" / "app.py"
    app = AppTest.from_file(str(app_path))
    app.session_state["profile_id"] = profile.id
    app.run()
    app.radio(key="navigation_selection").set_value("Tailor Resume").run()
    app.text_input(key="job_title_input").input("Embedded Systems Engineer")
    app.text_area(key="job_description_input").input(
        POSTING_FIXTURE.read_text(encoding="utf-8")
    )
    next(
        button for button in app.button if button.label == "Recommend resume strategy"
    ).click().run()
    next(button for button in app.button if button.label == "Build reviewed resume").click().run(
        timeout=30
    )

    assert app.session_state[GENERATED_RESUME_REVIEW_STATE_KEY] == (
        GeneratedResumeReviewState.GENERATED_AWAITING_REVIEW
    )
    assert next(
        button for button in app.download_button if button.label == "Download DOCX"
    ).disabled
    pending = [
        item
        for item in app.checkbox
        if item.key and item.key.startswith("approve-generated-")
    ]
    assert len(pending) >= 2
    for item in pending[:2]:
        app.checkbox(key=item.key).set_value(True).run()

    assert app.session_state[GENERATED_RESUME_REBUILD_REQUIRED_KEY] is True
    assert app.session_state[GENERATED_RESUME_WORDING_DIRTY_KEY] is True
    assert any(button.label == "Rebuild with approved wording" for button in app.button)
    initial_fingerprint = app.session_state["generated_resume_artifact"].artifact_fingerprint
    initial_version = app.session_state[GENERATED_RESUME_ARTIFACT_VERSION_KEY]

    next(
        button for button in app.button if button.label == "Rebuild with approved wording"
    ).click().run(
        timeout=30
    )

    rebuilt = app.session_state["generated_resume_artifact"]
    assert models.calls == 1
    assert rebuilt.artifact_fingerprint != initial_fingerprint
    assert app.session_state[GENERATED_RESUME_ARTIFACT_VERSION_KEY] == initial_version + 1
    assert app.session_state[GENERATED_RESUME_REVIEW_STATE_KEY] == (
        GeneratedResumeReviewState.REBUILT_AWAITING_REVIEW
    )
    assert app.session_state[GENERATED_RESUME_REBUILD_REQUIRED_KEY] is False
    assert app.session_state[GENERATED_RESUME_WORDING_DIRTY_KEY] is False
    assert not any(button.label == "Rebuild with approved wording" for button in app.button)
    assert any(
        "Approved wording rebuilt successfully" in element.value for element in app.success
    )
    assert app.session_state["generated_content_reviewed"] is False
    assert any(item.key == "generated_content_reviewed" for item in app.checkbox)
    assert next(
        button for button in app.download_button if button.label == "Download DOCX"
    ).disabled

    app.checkbox(key="generated_content_reviewed").set_value(True).run()
    assert app.session_state[GENERATED_RESUME_REVIEW_STATE_KEY] == (
        GeneratedResumeReviewState.REBUILT_APPROVED
    )
    download_button = next(
        button for button in app.download_button if button.label == "Download DOCX"
    )
    assert download_button.disabled is False
    downloaded = prepare_artifact_download(rebuilt, clock=service.telemetry.clock)
    assert downloaded.docx_bytes == rebuilt.docx_bytes
    download_button.click().run()
    assert app.session_state[GENERATED_RESUME_REVIEW_STATE_KEY] == (
        GeneratedResumeReviewState.DOWNLOADED
    )

    app.run()
    assert app.session_state[GENERATED_RESUME_REVIEW_STATE_KEY] == (
        GeneratedResumeReviewState.DOWNLOADED
    )
    assert not any(button.label == "Rebuild with approved wording" for button in app.button)
    assert next(
        button for button in app.download_button if button.label == "Download DOCX"
    ).disabled is False
    assert app.session_state[GENERATED_RESUME_GENERATED_APPROVALS_KEY]
    assert models.calls == 1


def test_failed_rebuild_preserves_last_valid_frontend_artifact(monkeypatch) -> None:
    from resume_tailor.frontend import app as frontend_app

    service, profile, posting, models = _production_case()
    service.start_generation()
    plan = service.create_plan(profile, posting, TemplateConstraints())
    state = _SessionState()
    monkeypatch.setattr(frontend_app, "st", _StreamlitStub(state))
    initial = frontend_app._build_and_store_resume_artifact(service, plan, profile, set())
    original_bytes = initial.docx_bytes
    state[GENERATED_RESUME_GENERATED_APPROVALS_KEY] = {
        variant.variant_id
        for variant in initial.writing_diagnostic.bullet_variants
        if variant.validation_status is BulletValidationStatus.REVIEW_REQUIRED
    }

    class FailingRebuildService:
        telemetry = service.telemetry

        def build_generated_artifact(self, *_args: object, **_kwargs: object) -> object:
            raise ValueError("controlled rebuild failure")

    try:
        frontend_app._rebuild_and_store_resume_artifact(
            FailingRebuildService(),
            plan,
            profile,
            set(state[GENERATED_RESUME_GENERATED_APPROVALS_KEY]),
        )
    except ValueError as error:
        assert str(error) == "controlled rebuild failure"
    else:
        raise AssertionError("the controlled rebuild should fail")

    assert state["generated_resume_artifact"] is initial
    assert initial.docx_bytes == original_bytes
    assert state[GENERATED_RESUME_REVIEW_STATE_KEY] == (
        GeneratedResumeReviewState.WORDING_CHANGED_REBUILD_REQUIRED
    )
    assert state[GENERATED_RESUME_REBUILD_REQUIRED_KEY] is True
    assert state[GENERATED_RESUME_WORDING_DIRTY_KEY] is True
    assert state[GENERATED_RESUME_REBUILD_IN_PROGRESS_KEY] is False
    assert "controlled rebuild failure" in state["generated_resume_rebuild_error"]
    assert models.calls == 1
