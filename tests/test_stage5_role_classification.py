from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError
from streamlit.testing.v1 import AppTest

import resume_tailor.infrastructure.dependencies as dependencies
from resume_tailor.application.role_classification import (
    HybridRoleClassifier,
    HybridRoleOpportunityAnalyzer,
    RoleClassificationCacheIdentity,
)
from resume_tailor.application.services import TailorResumeService
from resume_tailor.domain.llm_models import (
    LanguageModelError,
    LanguageModelErrorKind,
    LlmOperation,
    ModelCallMetadata,
    RoleClassificationOutput,
    RoleClassificationRequest,
    RoleClassificationResult,
    RoleEvidenceQuote,
)
from resume_tailor.domain.models import (
    EntityKind,
    EvidenceItem,
    JobPosting,
    MasterProfile,
    ResumeItem,
    RoleClassificationCacheBehavior,
    RoleClassificationFallbackReason,
    RoleClassificationSource,
    RoleClassificationValidationStatus,
    RoleFamily,
    TemplateConstraints,
)
from resume_tailor.frontend.role_classification_view import (
    build_role_classification_diagnostic_view,
)
from resume_tailor.infrastructure.config import Settings
from resume_tailor.infrastructure.llm_cache import InMemoryLlmCache
from resume_tailor.infrastructure.optimization import (
    DeterministicResumeOptimizer,
    EvidenceBoundResumeWriter,
)
from resume_tailor.infrastructure.profile_repository import SQLiteMasterProfileRepository
from resume_tailor.ports.interfaces import RoleClassificationCacheError


class RecordingRoleModel:
    def __init__(
        self,
        result: RoleClassificationResult | LanguageModelError,
    ) -> None:
        self.result = result
        self.call_count = 0

    def classify_role(
        self,
        request: RoleClassificationRequest,
    ) -> RoleClassificationResult:
        self.call_count += 1
        if isinstance(self.result, LanguageModelError):
            raise self.result
        return self.result.model_copy(deep=True)


class RecordingCache(InMemoryLlmCache):
    def __init__(self) -> None:
        super().__init__(ttl_seconds=900)
        self.get_calls = 0
        self.set_calls = 0
        self.model_identities: list[str] = []

    def key_for(self, operation: str, model: str, payload: BaseModel) -> str:
        self.model_identities.append(model)
        return super().key_for(operation, model, payload)

    def get(self, key: str, result_type: type):  # type: ignore[no-untyped-def]
        self.get_calls += 1
        return super().get(key, result_type)

    def set(self, key: str, value: object) -> None:
        self.set_calls += 1
        super().set(key, value)  # type: ignore[arg-type]


class ReadFailingCache(RecordingCache):
    def get(self, key: str, result_type: type):  # type: ignore[no-untyped-def]
        self.get_calls += 1
        raise RoleClassificationCacheError("secret cache read internals")


class WriteFailingCache(RecordingCache):
    def set(self, key: str, value: object) -> None:
        self.set_calls += 1
        raise RoleClassificationCacheError("secret cache write internals")


class UnexpectedFailingCache(RecordingCache):
    def get(self, key: str, result_type: type):  # type: ignore[no-untyped-def]
        raise RuntimeError("programming defect")


def _profile() -> MasterProfile:
    return MasterProfile(
        id="stage5-profile",
        user_id="stage5-user",
        display_name="Stage Five Candidate",
        experiences=[
            ResumeItem(
                id="firmware-entry",
                title="Firmware Intern",
                kind=EntityKind.EXPERIENCE,
            ),
            ResumeItem(
                id="software-entry",
                title="Software Intern",
                kind=EntityKind.EXPERIENCE,
            ),
            ResumeItem(
                id="ai-entry",
                title="AI Project",
                kind=EntityKind.PROJECT,
            ),
        ],
        declared_skills=["STM32", "Python", "ETL"],
        evidence=[
            EvidenceItem(
                id="firmware-evidence",
                entity_id="firmware-entry",
                source_text="Developed STM32 firmware and validated SPI hardware interfaces.",
                technologies=["STM32", "SPI"],
            ),
            EvidenceItem(
                id="software-evidence",
                entity_id="software-entry",
                source_text="Built Python ETL API automation for analytics data.",
                technologies=["Python", "ETL"],
            ),
            EvidenceItem(
                id="ai-evidence",
                entity_id="ai-entry",
                source_text="Implemented a PyTorch transformer model.",
                technologies=["PyTorch"],
            ),
        ],
    )


def _posting() -> JobPosting:
    return JobPosting(
        id="stage5-posting",
        title="Embedded Firmware and Data Engineer",
        description=(
            "Develop STM32 firmware and SPI hardware interfaces while building "
            "Python ETL API automation."
        ),
    )


def _semantic_output(**overrides: object) -> RoleClassificationOutput:
    values: dict[str, object] = {
        "is_engineering_role": True,
        "primary_family": RoleFamily.SOFTWARE_DATA_ENGINEERING,
        "secondary_families": [RoleFamily.AI_ML_MULTIMODAL],
        "owned_responsibilities": ["semantic responsibility advisory only"],
        "managed_subjects": ["semantic managed subject advisory only"],
        "tools_and_skills": ["Kubernetes-advisory-only"],
        "contextual_mentions": ["semantic context advisory only"],
        "evidence_quotes": [
            RoleEvidenceQuote(
                quote="Python ETL API automation",
                category="responsibility",
            )
        ],
        "confidence": 0.9,
    }
    values.update(overrides)
    return RoleClassificationOutput(**values)


def _model_result(output: RoleClassificationOutput) -> RoleClassificationResult:
    return RoleClassificationResult(
        metadata=ModelCallMetadata(
            provider="gemini",
            model="gemini-test-model",
            operation=LlmOperation.CLASSIFY_ROLE,
            latency_ms=4,
        ),
        output=output,
    )


def _hybrid_service(
    model: RecordingRoleModel | None,
    *,
    cache: InMemoryLlmCache | None = None,
    minimum_confidence: float = 0.7,
) -> TailorResumeService:
    classifier = HybridRoleClassifier(
        model,
        enabled=True,
        cache=cache,
        cache_identity=(
            RoleClassificationCacheIdentity("gemini", "gemini-test-model")
            if cache is not None
            else None
        ),
        safe_cache_failures=True,
    )
    optimizer = DeterministicResumeOptimizer(
        opportunity_analyzer=HybridRoleOpportunityAnalyzer(
            classifier,
            minimum_confidence=minimum_confidence,
        )
    )
    return TailorResumeService(optimizer, EvidenceBoundResumeWriter())


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "gemini_api_key": "test-key",
        "gemini_model": "gemini-test-model",
        "llm_enable_role_classification": True,
        "llm_enable_opportunity_analysis": False,
        "llm_enable_composition": False,
        "llm_enable_bullet_rewrite": False,
        "llm_enable_shortening": False,
        "llm_enable_cover_letter": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_default_configuration_disables_semantic_role_classification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LLM_ENABLE_ROLE_CLASSIFICATION", raising=False)
    settings = Settings(_env_file=None)

    assert settings.llm_enable_role_classification is False
    assert settings.llm_role_classification_minimum_confidence == 0.7


def test_disabled_wiring_preserves_the_deterministic_plan_and_constructs_no_gemini(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructor_calls = 0

    def fail_if_constructed(*args: object, **kwargs: object) -> object:
        nonlocal constructor_calls
        constructor_calls += 1
        raise AssertionError("Gemini must not be constructed")

    monkeypatch.setattr(
        dependencies,
        "GeminiResumeLanguageModel",
        fail_if_constructed,
    )
    settings = _settings(
        llm_enable_role_classification=False,
        gemini_api_key=None,
        gemini_model=None,
    )
    expected = DeterministicResumeOptimizer().create_plan(
        _profile(),
        _posting(),
        TemplateConstraints(),
    )

    actual = dependencies.create_tailor_service(settings).create_plan(
        _profile(),
        _posting(),
        TemplateConstraints(),
    )

    assert actual == expected
    assert constructor_calls == 0
    assert actual.report.role.diagnostic is not None
    assert actual.report.role.diagnostic.semantic_enabled is False
    assert (
        actual.report.role.diagnostic.fallback_reason is RoleClassificationFallbackReason.DISABLED
    )


def test_enabled_valid_semantic_output_selects_gemini_once_and_preserves_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = RecordingRoleModel(_model_result(_semantic_output()))
    cache = RecordingCache()
    monkeypatch.setattr(dependencies, "_create_language_model", lambda settings: model)
    deterministic_plan = DeterministicResumeOptimizer().create_plan(
        _profile(),
        _posting(),
        TemplateConstraints(),
    )

    plan = dependencies.create_tailor_service(
        _settings(),
        role_classification_cache=cache,
    ).create_plan(_profile(), _posting(), TemplateConstraints())

    diagnostic = plan.report.role.diagnostic
    assert diagnostic is not None
    assert model.call_count == 1
    assert plan.report.role.role_family == RoleFamily.SOFTWARE_DATA_ENGINEERING
    assert plan.strategy is not None
    assert plan.strategy.role_family == RoleFamily.SOFTWARE_DATA_ENGINEERING
    assert plan.report.role.confidence == deterministic_plan.report.role.confidence
    assert plan.report.role.signals == deterministic_plan.report.role.signals
    assert diagnostic.selected_source is RoleClassificationSource.GEMINI
    assert diagnostic.resolved_primary_family is RoleFamily.SOFTWARE_DATA_ENGINEERING
    assert diagnostic.deterministic_primary_family is RoleFamily.EMBEDDED_FIRMWARE
    assert diagnostic.semantic_primary_family is RoleFamily.SOFTWARE_DATA_ENGINEERING
    assert diagnostic.validation_status is RoleClassificationValidationStatus.VALID
    assert diagnostic.cache_behavior is RoleClassificationCacheBehavior.STORED
    assert cache.model_identities == ["gemini:gemini-test-model"]


def test_low_confidence_output_resolves_deterministically() -> None:
    model = RecordingRoleModel(_model_result(_semantic_output(confidence=0.69)))

    plan = _hybrid_service(model, minimum_confidence=0.7).create_plan(
        _profile(),
        _posting(),
        TemplateConstraints(),
    )

    diagnostic = plan.report.role.diagnostic
    assert diagnostic is not None
    assert plan.report.role.role_family == RoleFamily.EMBEDDED_FIRMWARE
    assert diagnostic.selected_source is RoleClassificationSource.DETERMINISTIC
    assert diagnostic.fallback_reason is RoleClassificationFallbackReason.LOW_CONFIDENCE
    assert diagnostic.confidence == 0.69
    assert model.call_count == 1


def test_structurally_invalid_output_resolves_deterministically() -> None:
    model = RecordingRoleModel(_model_result(_semantic_output(primary_family=None)))

    plan = _hybrid_service(model).create_plan(
        _profile(),
        _posting(),
        TemplateConstraints(),
    )

    diagnostic = plan.report.role.diagnostic
    assert diagnostic is not None
    assert plan.report.role.role_family == RoleFamily.EMBEDDED_FIRMWARE
    assert diagnostic.validation_status is RoleClassificationValidationStatus.INVALID
    assert diagnostic.fallback_reason is RoleClassificationFallbackReason.INVALID_OUTPUT
    assert diagnostic.confidence is None
    assert model.call_count == 1


def test_provider_error_resolves_deterministically_without_exception_details() -> None:
    secret = "provider failure with secret-token-value"
    model = RecordingRoleModel(
        LanguageModelError(LanguageModelErrorKind.NETWORK, secret, retryable=True)
    )

    plan = _hybrid_service(model).create_plan(
        _profile(),
        _posting(),
        TemplateConstraints(),
    )

    diagnostic = plan.report.role.diagnostic
    assert diagnostic is not None
    assert plan.report.role.role_family == RoleFamily.EMBEDDED_FIRMWARE
    assert diagnostic.fallback_reason is RoleClassificationFallbackReason.PROVIDER_ERROR
    assert secret not in plan.model_dump_json()
    assert model.call_count == 1


def test_missing_model_resolves_deterministically_without_cache_access() -> None:
    cache = RecordingCache()

    plan = _hybrid_service(None, cache=cache).create_plan(
        _profile(),
        _posting(),
        TemplateConstraints(),
    )

    diagnostic = plan.report.role.diagnostic
    assert diagnostic is not None
    assert plan.report.role.role_family == RoleFamily.EMBEDDED_FIRMWARE
    assert diagnostic.fallback_reason is RoleClassificationFallbackReason.MODEL_UNAVAILABLE
    assert diagnostic.cache_behavior is RoleClassificationCacheBehavior.NOT_USED
    assert cache.get_calls == 0
    assert cache.set_calls == 0


def test_enabled_production_wiring_with_missing_model_is_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    settings = _settings(
        gemini_api_key=None,
        gemini_model=None,
    )

    plan = dependencies.create_tailor_service(settings).create_plan(
        _profile(),
        _posting(),
        TemplateConstraints(),
    )

    diagnostic = plan.report.role.diagnostic
    assert diagnostic is not None
    assert plan.report.role.role_family == RoleFamily.EMBEDDED_FIRMWARE
    assert diagnostic.semantic_enabled is True
    assert diagnostic.selected_source is RoleClassificationSource.DETERMINISTIC
    assert diagnostic.fallback_reason is RoleClassificationFallbackReason.MODEL_UNAVAILABLE


def test_cache_hit_reuses_validated_output_without_another_gemini_call() -> None:
    cache = RecordingCache()
    model = RecordingRoleModel(_model_result(_semantic_output()))
    service = _hybrid_service(model, cache=cache)

    first = service.create_plan(_profile(), _posting(), TemplateConstraints())
    second = service.create_plan(_profile(), _posting(), TemplateConstraints())

    assert first.report.role.diagnostic is not None
    assert second.report.role.diagnostic is not None
    assert first.report.role.diagnostic.cache_behavior is RoleClassificationCacheBehavior.STORED
    assert second.report.role.diagnostic.cache_behavior is RoleClassificationCacheBehavior.HIT
    assert model.call_count == 1


def test_cache_read_failure_builds_deterministic_resume_and_never_calls_gemini() -> None:
    cache = ReadFailingCache()
    model = RecordingRoleModel(_model_result(_semantic_output()))
    service = _hybrid_service(model, cache=cache)
    profile = _profile()

    plan = service.create_plan(profile, _posting(), TemplateConstraints())
    resume = service.build_document(plan, profile, set())

    diagnostic = plan.report.role.diagnostic
    assert diagnostic is not None
    assert resume.strategy.role_family == RoleFamily.EMBEDDED_FIRMWARE
    assert diagnostic.fallback_reason is RoleClassificationFallbackReason.CACHE_READ_ERROR
    assert diagnostic.cache_behavior is RoleClassificationCacheBehavior.READ_ERROR
    assert model.call_count == 0
    assert cache.set_calls == 0
    assert "secret cache read internals" not in plan.model_dump_json()


def test_cache_write_failure_does_not_crash_or_retry_within_an_operation() -> None:
    cache = WriteFailingCache()
    model = RecordingRoleModel(_model_result(_semantic_output()))
    service = _hybrid_service(model, cache=cache)
    profile = _profile()

    plan = service.create_plan(profile, _posting(), TemplateConstraints())

    diagnostic = plan.report.role.diagnostic
    assert diagnostic is not None
    assert plan.strategy is not None
    assert diagnostic.selected_source is RoleClassificationSource.GEMINI
    assert diagnostic.cache_behavior is RoleClassificationCacheBehavior.WRITE_ERROR
    assert model.call_count == 1
    assert cache.set_calls == 1
    assert "secret cache write internals" not in plan.model_dump_json()

    resume = service.build_document(plan, profile, set())

    assert resume.strategy.role_family == RoleFamily.SOFTWARE_DATA_ENGINEERING
    assert model.call_count == 2
    assert cache.set_calls == 2


def test_safe_cache_policy_does_not_swallow_untyped_programming_errors() -> None:
    service = _hybrid_service(
        RecordingRoleModel(_model_result(_semantic_output())),
        cache=UnexpectedFailingCache(),
    )

    with pytest.raises(RuntimeError, match="programming defect"):
        service.create_plan(_profile(), _posting(), TemplateConstraints())


@pytest.mark.parametrize(
    "confidence",
    [-0.1, 1.1, float("nan"), float("inf"), float("-inf")],
)
def test_invalid_confidence_configuration_fails_safely(confidence: float) -> None:
    with pytest.raises(ValidationError) as error:
        _settings(llm_role_classification_minimum_confidence=confidence)
    assert "test-key" not in str(error.value)


def test_semantic_advisory_fields_never_become_candidate_authority() -> None:
    profile = _profile()
    profile_before = deepcopy(profile.model_dump())
    model = RecordingRoleModel(_model_result(_semantic_output()))

    plan = _hybrid_service(model).create_plan(
        profile,
        _posting(),
        TemplateConstraints(),
    )

    serialized = plan.model_dump_json()
    for advisory_value in (
        "semantic responsibility advisory only",
        "semantic managed subject advisory only",
        "Kubernetes-advisory-only",
        "semantic context advisory only",
    ):
        assert advisory_value not in serialized
    assert profile.model_dump() == profile_before
    assert all(candidate.evidence_ids for candidate in plan.claim_candidates)
    assert all(
        candidate.id in {item.id for item in profile.evidence}
        or candidate.id.startswith("combined:")
        for candidate in plan.claim_candidates
    )


def test_semantic_secondary_families_do_not_broaden_optimization_authority() -> None:
    model = RecordingRoleModel(_model_result(_semantic_output()))

    plan = _hybrid_service(model).create_plan(
        _profile(),
        _posting(),
        TemplateConstraints(),
    )

    signal_ids = {signal.id for signal in plan.report.role.signals}
    assert RoleFamily.AI_ML_MULTIMODAL not in plan.report.role.secondary_role_families
    assert "deep-learning-research" not in signal_ids
    assert "ai-evidence" not in plan.selected_claim_ids
    assert RoleFamily.EMBEDDED_FIRMWARE in plan.report.role.secondary_role_families


def test_semantic_primary_without_deterministic_family_support_falls_back() -> None:
    output = _semantic_output(
        primary_family=RoleFamily.AI_ML_MULTIMODAL,
        secondary_families=[],
    )
    model = RecordingRoleModel(_model_result(output))

    plan = _hybrid_service(model).create_plan(
        _profile(),
        _posting(),
        TemplateConstraints(),
    )

    diagnostic = plan.report.role.diagnostic
    assert diagnostic is not None
    assert plan.report.role.role_family == RoleFamily.EMBEDDED_FIRMWARE
    assert diagnostic.selected_source is RoleClassificationSource.DETERMINISTIC
    assert (
        diagnostic.fallback_reason is RoleClassificationFallbackReason.SEMANTIC_FAMILY_UNSUPPORTED
    )


def test_job_discovery_dependency_construction_never_invokes_hybrid_classifier(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail_if_called(*args: object, **kwargs: object) -> object:
        raise AssertionError("Job Discovery must not invoke HybridRoleClassifier")

    monkeypatch.setattr(HybridRoleClassifier, "classify", fail_if_called)
    settings = Settings(
        _env_file=None,
        app_data_directory=tmp_path,
        job_discovery_enabled=False,
    )

    bundle = dependencies.create_job_discovery_services(settings)

    bundle.close_resources()


def test_application_initializes_without_gemini_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    service = dependencies.create_tailor_service(
        Settings(
            _env_file=None,
            gemini_api_key=None,
            gemini_model=None,
        )
    )

    plan = service.create_plan(_profile(), _posting(), TemplateConstraints())
    assert plan.report.role.role_family == RoleFamily.EMBEDDED_FIRMWARE
    assert plan.report.role.diagnostic is not None
    assert plan.report.role.diagnostic.semantic_enabled is False


def test_streamlit_diagnostic_view_represents_gemini_selection() -> None:
    plan = _hybrid_service(
        RecordingRoleModel(_model_result(_semantic_output())),
        cache=RecordingCache(),
    ).create_plan(_profile(), _posting(), TemplateConstraints())

    view = build_role_classification_diagnostic_view(plan.report.role)

    assert view.semantic_enabled is True
    assert view.selected_source == "Gemini"
    assert view.resolved_role_family == "Software Data Engineering"
    assert view.confidence == 0.9
    assert view.cached_reuse is False
    assert view.fallback_reason is None


def test_streamlit_diagnostic_view_represents_sanitized_fallback() -> None:
    secret = "secret provider diagnostic"
    plan = _hybrid_service(
        RecordingRoleModel(LanguageModelError(LanguageModelErrorKind.UNAVAILABLE, secret))
    ).create_plan(_profile(), _posting(), TemplateConstraints())

    view = build_role_classification_diagnostic_view(plan.report.role)

    assert view.semantic_enabled is True
    assert view.selected_source == "Deterministic"
    assert view.resolved_role_family == "Embedded Firmware"
    assert "unavailable" in (view.fallback_reason or "").casefold()
    assert secret not in view.model_dump_json()


def test_streamlit_diagnostic_view_represents_disabled_mode() -> None:
    plan = DeterministicResumeOptimizer().create_plan(
        _profile(),
        _posting(),
        TemplateConstraints(),
    )

    view = build_role_classification_diagnostic_view(plan.report.role)

    assert view.semantic_enabled is False
    assert view.selected_source == "Deterministic"
    assert view.resolved_role_family == "Embedded Firmware"
    assert "disabled" in (view.fallback_reason or "").casefold()
    assert view.confidence is None
    assert view.cached_reuse is None


def test_streamlit_tailoring_shows_compact_enabled_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model = RecordingRoleModel(_model_result(_semantic_output()))
    service = _hybrid_service(model, cache=RecordingCache())
    repository = SQLiteMasterProfileRepository(tmp_path / "stage5-streamlit.sqlite3")
    monkeypatch.setattr(dependencies, "create_tailor_service", lambda: service)
    monkeypatch.setattr(dependencies, "create_profile_repository", lambda: repository)

    app_path = Path(__file__).parents[1] / "src" / "resume_tailor" / "frontend" / "app.py"
    app = AppTest.from_file(str(app_path)).run()
    app.radio(key="navigation_selection").set_value("Profile").run()
    app.text_input(key="profile_id_input").input(_profile().id).run()
    app.text_area(key="profile_editor_raw_json").input(
        json.dumps(_profile().model_dump(mode="json"))
    )
    next(
        button for button in app.button if button.label == "Validate and save raw JSON"
    ).click().run()
    app.radio(key="navigation_selection").set_value("Tailor Resume").run()
    app.text_area(key="job_description_input").input(_posting().description)
    app.text_input(key="job_title_input").input(_posting().title)
    next(
        button for button in app.button if button.label == "Recommend resume strategy"
    ).click().run()

    markdown_values = [element.value for element in app.markdown]
    caption_values = [element.value for element in app.caption]
    assert "**Role classification**" in markdown_values
    assert "Selected source: Gemini" in caption_values
    assert "Validated Gemini confidence: 90%" in caption_values
    assert "Cached result reused: No" in caption_values
    assert model.call_count == 1

    next(
        button for button in app.button if button.label == "Recommend resume strategy"
    ).click().run()

    caption_values = [element.value for element in app.caption]
    assert "Cached result reused: Yes" in caption_values
    assert model.call_count == 1
