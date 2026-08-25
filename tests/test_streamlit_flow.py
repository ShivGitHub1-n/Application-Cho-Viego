import json
import sqlite3
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import resume_tailor.infrastructure.dependencies as dependencies
from resume_tailor.application import cover_letter_policy
from resume_tailor.application.cover_letter import CoverLetterService
from resume_tailor.application.generated_artifact import (
    ResumeGenerationConfiguration,
    content_fingerprint,
)
from resume_tailor.application.generation_diagnostics import GenerationTelemetry
from resume_tailor.application.job_intake import build_job_posting
from resume_tailor.application.llm_services import HybridLlmServices
from resume_tailor.application.resume_composition import DeterministicResumeComposer
from resume_tailor.application.services import TailorResumeService
from resume_tailor.application.workflow_state import (
    COVER_LETTER_ARTIFACT_KEY,
    get_active_posting,
    has_cover_letter_prerequisites,
    invalidate_posting_derived_workflow,
    invalidate_profile_derived_workflow,
    set_active_opportunity,
)
from resume_tailor.domain.hybrid_resume import (
    RESUME_WRITING_CONTRACT_VERSION,
    RESUME_WRITING_POLICY_VERSION,
)
from resume_tailor.domain.llm_models import (
    BulletRewrite,
    BulletRewriteOutput,
    BulletRewriteResult,
    ClaimConfidence,
    CompositionRecommendationOutput,
    CompositionRecommendationResult,
    LlmOperation,
)
from resume_tailor.domain.models import MasterProfile, TemplateConstraints
from resume_tailor.domain.resume_composition import RESUME_COMPOSITION_CONTRACT_VERSION
from resume_tailor.frontend.cover_letter_view import _artifact_after_build
from resume_tailor.infrastructure.artifact_rendering import TemplateV1ArtifactRenderer
from resume_tailor.infrastructure.composition_page_fit import TemplateV1PageFitEvaluator
from resume_tailor.infrastructure.config import Settings
from resume_tailor.infrastructure.optimization import (
    DeterministicResumeOptimizer,
    EvidenceBoundResumeWriter,
)
from resume_tailor.infrastructure.profile_repository import SQLiteMasterProfileRepository
from resume_tailor.infrastructure.template_v1 import TEMPLATE_V1_DOCX_SHA256, TEMPLATE_V1_ID
from tests.cover_letter_helpers import ControlledCoverLetterRenderer, cover_letter_case
from tests.fakes import FakeResumeLanguageModel, metadata
from tests.test_resume_composition import ParagraphLimitPageProvider


class _Strategy:
    pass


class _Plan:
    strategy = _Strategy()


def _generation_configuration() -> ResumeGenerationConfiguration:
    return ResumeGenerationConfiguration(
        template_identity=f"{TEMPLATE_V1_ID}:{TEMPLATE_V1_DOCX_SHA256}",
        composition_contract_version=RESUME_COMPOSITION_CONTRACT_VERSION,
        writing_policy_version=RESUME_WRITING_POLICY_VERSION,
        writing_contract_version=RESUME_WRITING_CONTRACT_VERSION,
        feature_flags={"bullet_rewrite": False},
        provider="gemini",
        model="controlled",
        provider_timeout_seconds=30,
        provider_retry_count=0,
    )


def _navigate(app: AppTest, route: str) -> AppTest:
    return app.button(key=f"pw-route-sidebar-{route}").click().run()


def _create_resume_strategy(app: AppTest, title: str, description: str) -> AppTest:
    _navigate(app, "resume_studio")
    app.pills(key="_resume_studio_stage_widget").set_value("Job context").run()
    app.text_input(key="_resume_studio_job_title_widget").input(title).run()
    app.text_area(key="_resume_studio_job_description_widget").input(description).run()
    return app.button(key="resume-create-strategy").click().run()


def _workflow_state() -> dict[str, object]:
    return {
        "profile": object(),
        "posting": type(
            "Posting", (), {"title": "Robotics Engineer", "company_name": "Example Robotics"}
        )(),
        "plan": _Plan(),
        "resume": "resume-artifact",
        "generated_content_reviewed": True,
        "cover_letter": "cover-letter-draft",
        COVER_LETTER_ARTIFACT_KEY: "immutable-cover-letter-artifact",
        "cover_letter_reviewed": True,
        "cover_letter_download": "download-state",
        "workflow_profile_fingerprint": "profile-v1",
        "workflow_posting_fingerprint": "posting-v1",
        "cover_letter_profile_fingerprint": "profile-v1",
        "cover_letter_posting_fingerprint": "posting-v1",
        "cover_letter_plan_fingerprint": "plan-v1",
        "cover_letter_evidence_fingerprint": "evidence-v1",
        "cover_letter_recipient_fingerprint": "recipient-v1",
    }


def test_streamlit_rebuilds_cached_service_when_provider_configuration_changes(
    monkeypatch,
    tmp_path,
) -> None:
    constructions = 0

    def create_service():
        nonlocal constructions
        constructions += 1
        return TailorResumeService(
            DeterministicResumeOptimizer(),
            EvidenceBoundResumeWriter(),
        )

    monkeypatch.setattr(dependencies, "create_tailor_service", create_service)
    monkeypatch.setattr(
        dependencies,
        "create_profile_repository",
        lambda: SQLiteMasterProfileRepository(tmp_path / "provider-config.sqlite3"),
    )
    app_path = Path(__file__).parents[1] / "src" / "resume_tailor" / "frontend" / "app.py"
    app = AppTest.from_file(str(app_path)).run()
    assert constructions == 1

    app.run()
    assert constructions == 1

    monkeypatch.setenv("LLM_ENABLE_COVER_LETTER", "false")
    app.run()
    assert constructions == 2

    monkeypatch.setattr(
        cover_letter_policy,
        "COVER_LETTER_WRITING_POLICY_VERSION",
        "cover-letter-writing-runtime-fingerprint-test",
    )
    app.run()
    assert constructions == 3


def test_initial_workflow_has_no_active_posting_and_cover_letter_is_guarded() -> None:
    state: dict[str, object] = {}

    assert get_active_posting(state) is None
    assert not has_cover_letter_prerequisites(state)


def test_active_posting_survives_rerun_without_original_local_variable() -> None:
    state = _workflow_state()

    assert get_active_posting(state).title == "Robotics Engineer"
    assert get_active_posting(state).company_name == "Example Robotics"


def test_legacy_rerun_recovers_normalized_posting_from_accepted_plan() -> None:
    profile, posting, plan = cover_letter_case()
    state: dict[str, object] = {"profile": profile, "plan": plan}

    recovered = get_active_posting(state)

    assert recovered is posting or recovered == posting
    assert state["posting"] == plan.posting
    assert state["workflow_posting_fingerprint"] == content_fingerprint(posting)
    assert has_cover_letter_prerequisites(state)


def test_active_opportunity_rejects_contradictory_strategy_posting() -> None:
    _profile, posting, plan = cover_letter_case()
    changed = posting.model_copy(update={"description": posting.description + " Changed."})

    with pytest.raises(ValueError, match="same opportunity"):
        set_active_opportunity({}, changed, plan)


def test_authoritative_posting_supplies_company_and_role_defaults() -> None:
    state = _workflow_state()
    posting = get_active_posting(state)

    assert posting.company_name == "Example Robotics"
    assert posting.title == "Robotics Engineer"


def test_job_description_invalidation_removes_all_posting_derived_state() -> None:
    state = _workflow_state()

    invalidate_posting_derived_workflow(state)

    assert get_active_posting(state) is None
    assert not has_cover_letter_prerequisites(state)
    assert "plan" not in state
    assert "resume" not in state
    assert "generated_content_reviewed" not in state
    assert "cover_letter" not in state
    assert COVER_LETTER_ARTIFACT_KEY not in state
    assert "cover_letter_reviewed" not in state
    assert "workflow_posting_fingerprint" not in state


def test_invalid_posting_cannot_leave_the_prior_posting_active() -> None:
    state = _workflow_state()

    invalidate_posting_derived_workflow(state)

    assert get_active_posting(state) is None
    assert not has_cover_letter_prerequisites(state)


def test_loading_same_profile_preserves_active_posting() -> None:
    state = _workflow_state()
    posting = state["posting"]

    invalidate_profile_derived_workflow(state)

    assert state["posting"] is posting
    assert get_active_posting(state) is posting


def test_changed_canonical_profile_invalidates_dependents_but_preserves_posting() -> None:
    state = _workflow_state()
    posting = state["posting"]

    invalidate_profile_derived_workflow(state)

    assert state["posting"] is posting
    assert "plan" not in state
    assert "resume" not in state
    assert "cover_letter" not in state
    assert COVER_LETTER_ARTIFACT_KEY not in state
    assert "generated_content_reviewed" not in state
    assert "cover_letter_reviewed" not in state


def test_missing_posting_is_a_cover_letter_guard_not_a_name_error() -> None:
    state = {"profile": object(), "plan": _Plan()}

    assert not has_cover_letter_prerequisites(state)


def test_resume_and_cover_letter_approval_states_are_separate() -> None:
    state = {"generated_content_reviewed": True, "cover_letter_reviewed": False}

    state["generated_content_reviewed"] = False

    assert state["generated_content_reviewed"] is False
    assert state["cover_letter_reviewed"] is False


def test_repeated_invalidation_is_safe_and_deterministic() -> None:
    state = _workflow_state()

    invalidate_posting_derived_workflow(state)
    first_result = dict(state)
    invalidate_posting_derived_workflow(state)

    assert state == first_result


def test_streamlit_cover_letter_uses_artifact_review_and_stored_byte_download(
    monkeypatch,
    tmp_path,
) -> None:
    profile, posting, plan = cover_letter_case()
    cover_service = CoverLetterService(renderer=ControlledCoverLetterRenderer([0.94]))
    service = TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
        cover_letter_service=cover_service,
    )
    monkeypatch.setattr(dependencies, "create_tailor_service", lambda: service)
    monkeypatch.setattr(
        dependencies,
        "create_profile_repository",
        lambda: SQLiteMasterProfileRepository(tmp_path / "cover-letter-ui.sqlite3"),
    )
    app_path = Path(__file__).parents[1] / "src" / "resume_tailor" / "frontend" / "app.py"
    app = AppTest.from_file(str(app_path)).run()
    app.session_state["profile"] = profile
    app.session_state["posting"] = posting
    app.session_state["plan"] = plan

    _navigate(app, "cover_letters")
    next(button for button in app.button if button.label == "Generate cover letter").click().run()

    artifact = app.session_state[COVER_LETTER_ARTIFACT_KEY]
    assert artifact.ready_for_review
    assert artifact.docx_bytes.startswith(b"PK\x03\x04")
    assert any(expander.label == "Evidence, sources, and diagnostics" for expander in app.expander)
    next(
        checkbox
        for checkbox in app.checkbox
        if checkbox.label.startswith("I reviewed the complete letter")
    ).check().run()
    next(button for button in app.button if button.label == "Approve cover letter").click().run()

    approved = app.session_state[COVER_LETTER_ARTIFACT_KEY]
    assert approved.review_state.value == "approved"
    assert any(button.label == "Download approved DOCX" for button in app.get("download_button"))


def test_failed_cover_letter_rebuild_preserves_prior_valid_artifact() -> None:
    profile, posting, plan = cover_letter_case()
    valid = CoverLetterService(renderer=ControlledCoverLetterRenderer([0.94])).generate_artifact(
        profile, posting, plan
    )
    failed = CoverLetterService(renderer=ControlledCoverLetterRenderer([0.50])).generate_artifact(
        profile, posting, plan
    )

    stored, committed = _artifact_after_build(valid, failed)

    assert failed.ready_for_review is False
    assert stored is valid
    assert committed is False


def test_streamlit_strategy_uses_reconciled_composition(monkeypatch, tmp_path) -> None:
    result = CompositionRecommendationResult(
        metadata=metadata(LlmOperation.RECOMMEND_COMPOSITION),
        output=CompositionRecommendationOutput(
            selected_entry_ids=["streamlit-entry"],
            selected_evidence_ids=["streamlit-evidence-2"],
            rationale="Use focused interface validation evidence.",
        ),
    )
    hybrid = HybridLlmServices(
        FakeResumeLanguageModel(recommend_composition=result),
        0,
        4,
        False,
        True,
        False,
    )
    service = TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
        hybrid_services=hybrid,
        artifact_renderer=TemplateV1ArtifactRenderer(),
        generation_configuration=_generation_configuration(),
    )
    monkeypatch.setattr(dependencies, "create_tailor_service", lambda: service)
    monkeypatch.setattr(
        dependencies,
        "create_profile_repository",
        lambda: SQLiteMasterProfileRepository(tmp_path / "streamlit-profile.sqlite3"),
    )
    profile = {
        "id": "streamlit-profile",
        "user_id": "streamlit-user",
        "display_name": "Candidate",
        "experiences": [
            {"id": "streamlit-entry", "title": "Firmware Intern", "kind": "experience"}
        ],
        "evidence": [
            {
                "id": "streamlit-evidence-1",
                "entity_id": "streamlit-entry",
                "source_text": "Developed STM32 embedded firmware.",
            },
            {
                "id": "streamlit-evidence-2",
                "entity_id": "streamlit-entry",
                "source_text": "Validated SPI hardware sensor interfaces.",
            },
        ],
    }
    app_path = Path(__file__).parents[1] / "src" / "resume_tailor" / "frontend" / "app.py"
    app = AppTest.from_file(str(app_path)).run()
    app.session_state["profile"] = MasterProfile.model_validate(profile)
    app.session_state["profile_id"] = "streamlit-profile"
    app.session_state["resume"] = "stale-generated-resume"
    app.session_state["generated_content_reviewed"] = True
    _create_resume_strategy(
        app,
        "Embedded Firmware Intern",
        "Develop STM32 firmware and validate SPI hardware interfaces.",
    )

    assert app.session_state["plan"].selected_claim_ids == ["streamlit-evidence-2"]
    assert "resume" not in app.session_state
    assert app.session_state["generated_content_reviewed"] is False

    app.button(key="resume-to-evidence").click().run()
    app.button(key="resume-build-document").click().run(timeout=10)

    assert app.session_state["resume"].experience_bullets["streamlit-entry"][0].text == (
        "Validated SPI hardware sensor interfaces."
    )
    assert app.session_state["generated_content_reviewed"] is False
    assert any("Résumé review canvas" in element.value for element in app.markdown)
    assert app.session_state["generated_resume_artifact"].docx_bytes


def test_streamlit_approved_wording_rebuild_resets_widget_state_and_reuses_artifact(
    monkeypatch, tmp_path
) -> None:
    from io import BytesIO

    from docx import Document

    from resume_tailor.application.generated_artifact import prepare_artifact_download
    from resume_tailor.frontend import app as frontend_app

    class _SessionState(dict[str, object]):
        widget_keys: set[str] = set()

        def __setitem__(self, key: str, value: object) -> None:
            if key in self.widget_keys:
                raise AssertionError(f"illegal widget mutation: {key}")
            super().__setitem__(key, value)

    class _Status:
        def __enter__(self) -> "_Status":
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

    rewrites = BulletRewriteResult(
        metadata=metadata(LlmOperation.REWRITE_BULLETS),
        output=BulletRewriteOutput(
            bullets=[
                BulletRewrite(
                    entry_id="streamlit-entry",
                    final_bullet_text="Built STM32 embedded firmware, testing sensor interfaces.",
                    source_evidence_ids=["streamlit-evidence-1"],
                    evidence_combined=False,
                    concise_alternative="Built STM32 embedded firmware, testing sensor interfaces.",
                    confidence=0.9,
                    support=ClaimConfidence.STRONGLY_IMPLIED,
                ),
                BulletRewrite(
                    entry_id="streamlit-entry",
                    final_bullet_text=(
                        "Validated hardware sensor interfaces through SPI hardware checks."
                    ),
                    source_evidence_ids=["streamlit-evidence-2"],
                    evidence_combined=False,
                    concise_alternative=(
                        "Validated hardware sensor interfaces through SPI hardware checks."
                    ),
                    confidence=0.9,
                    support=ClaimConfidence.STRONGLY_IMPLIED,
                ),
            ]
        ),
    )
    fake = FakeResumeLanguageModel(rewrite_bullets=rewrites)
    telemetry = GenerationTelemetry()
    service = TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
        hybrid_services=HybridLlmServices(fake, 0, 4, False, False, True),
        resume_composer=DeterministicResumeComposer(
            TemplateV1PageFitEvaluator(ParagraphLimitPageProvider(), telemetry=telemetry),
            telemetry=telemetry,
        ),
        artifact_renderer=TemplateV1ArtifactRenderer(),
        generation_configuration=_generation_configuration().model_copy(
            update={"feature_flags": {"bullet_rewrite": True}}
        ),
        telemetry=telemetry,
    )
    profile = MasterProfile.model_validate(
        {
            "id": "streamlit-profile",
            "user_id": "streamlit-user",
            "display_name": "Candidate",
            "experiences": [
                {"id": "streamlit-entry", "title": "Firmware Intern", "kind": "experience"}
            ],
            "evidence": [
                {
                    "id": "streamlit-evidence-1",
                    "entity_id": "streamlit-entry",
                    "source_text": (
                        "Developed STM32 embedded firmware and tested sensor interfaces."
                    ),
                    "technologies": ["STM32"],
                },
                {
                    "id": "streamlit-evidence-2",
                    "entity_id": "streamlit-entry",
                    "source_text": (
                        "Validated SPI hardware sensor interfaces through hardware checks."
                    ),
                    "technologies": ["SPI"],
                },
            ],
        }
    )
    posting = build_job_posting(
        "streamlit-posting",
        "Embedded Firmware Intern",
        "Develop STM32 firmware and validate SPI hardware sensor interfaces.",
    )
    service.start_generation()
    plan = service.create_plan(profile, posting, TemplateConstraints())
    state = _SessionState()
    monkeypatch.setattr(frontend_app, "st", _StreamlitStub(state))
    initial = frontend_app._build_and_store_resume_artifact(service, plan, profile, set())
    review_ids = {
        variant.variant_id
        for variant in initial.writing_diagnostic.bullet_variants
        if variant.validation_status.value == "review_required"
    }
    assert len(review_ids) == 2
    state["generated_content_reviewed"] = True
    state.widget_keys.add("generated_content_reviewed")
    rebuilt = frontend_app._build_and_store_resume_artifact(service, plan, profile, review_ids)
    assert fake.calls["rewrite_bullets"] == 1
    assert rebuilt.pagination_diagnostic.attempt_count <= 1
    rendered_text = "\n".join(
        paragraph.text for paragraph in Document(BytesIO(rebuilt.docx_bytes)).paragraphs
    )
    assert "Developed STM32 embedded firmware and tested sensor interfaces." in rendered_text
    assert "Validated SPI hardware sensor interfaces through hardware checks." in rendered_text
    assert "Built STM32 embedded firmware, testing sensor interfaces." not in rendered_text
    assert "Validated hardware sensor interfaces through SPI hardware checks." not in rendered_text
    state.widget_keys.clear()
    frontend_app._apply_pending_generated_content_review_reset()
    assert state["generated_content_reviewed"] is False
    download = prepare_artifact_download(rebuilt, clock=telemetry.clock)
    assert download.docx_bytes is rebuilt.docx_bytes
    assert not any(download.generation_call_counts.model_dump().values())
    assert fake.calls["rewrite_bullets"] == 1


def test_streamlit_uses_persisted_profile_with_pasted_job_description(
    monkeypatch, tmp_path
) -> None:
    database = tmp_path / "profiles.sqlite3"
    repository = SQLiteMasterProfileRepository(database)
    profile = MasterProfile(
        id="local-profile",
        user_id="local-user",
        display_name="Persisted Candidate",
        experiences=[{"id": "entry-1", "title": "Engineer", "kind": "experience"}],
        evidence=[{"id": "evidence-1", "entity_id": "entry-1", "source_text": "Built firmware."}],
    )
    repository.save(profile)
    monkeypatch.setattr(
        dependencies, "create_profile_repository", lambda: SQLiteMasterProfileRepository(database)
    )
    monkeypatch.setattr(
        dependencies,
        "create_tailor_service",
        lambda: TailorResumeService(DeterministicResumeOptimizer(), EvidenceBoundResumeWriter()),
    )

    app_path = Path(__file__).parents[1] / "src" / "resume_tailor" / "frontend" / "app.py"
    app = AppTest.from_file(str(app_path)).run()
    _create_resume_strategy(app, "Firmware Engineer", "Build firmware.\r\n\r\n- Test systems  ")

    assert app.session_state["profile"].id == "local-profile"
    assert app.session_state["posting"].description == "Build firmware.\n\n- Test systems"
    assert app.session_state["profile_load_status"] == "Loaded from persistent storage."


def test_profile_workflow_is_canonical_for_job_discovery_and_stale_selection(
    monkeypatch,
    tmp_path,
) -> None:
    database = tmp_path / "resume_tailor.sqlite3"
    repository = SQLiteMasterProfileRepository(database)
    create_services = dependencies.create_job_discovery_services
    discovery_settings = Settings(
        app_data_directory=tmp_path,
        job_discovery_enabled=False,
        job_discovery_source_registry_path=None,
    )
    monkeypatch.setenv("APPLICATION_VIEGO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JOB_DISCOVERY_ENABLED", "false")
    monkeypatch.setattr(
        dependencies,
        "create_profile_repository",
        lambda: SQLiteMasterProfileRepository(database),
    )
    monkeypatch.setattr(
        dependencies,
        "create_tailor_service",
        lambda: TailorResumeService(
            DeterministicResumeOptimizer(),
            EvidenceBoundResumeWriter(),
        ),
    )
    monkeypatch.setattr(
        dependencies,
        "create_job_discovery_services",
        lambda _settings, *, profile_repository=None: create_services(
            discovery_settings,
            legacy_repository_root=tmp_path / "no-legacy-repository",
            profile_repository=profile_repository,
        ),
    )
    profile = {
        "id": "workflow-profile",
        "user_id": "workflow-owner",
        "display_name": "Workflow Candidate",
        "experiences": [
            {
                "id": "workflow-experience",
                "title": "Firmware Engineer",
                "kind": "experience",
            }
        ],
        "evidence": [
            {
                "id": "workflow-evidence",
                "entity_id": "workflow-experience",
                "source_text": "Developed embedded firmware and validated interfaces.",
            }
        ],
    }
    repository.save(MasterProfile.model_validate(profile))
    app_path = Path(__file__).parents[1] / "src" / "resume_tailor" / "frontend" / "app.py"
    app = AppTest.from_file(str(app_path))
    app.session_state["profile_id"] = profile["id"]
    app.run()
    _navigate(app, "jobs")

    assert repository.get(profile["id"]) is not None
    assert app.session_state["profile_id"] == profile["id"]
    assert app.session_state["job_discovery_profile_id"] == profile["id"]
    app.pills(key="jobs-active-section").set_value("Preferences").run()
    app.button(key="jobs-suggest-preferences").click().run()

    assert app.session_state["jobs_preference_suggestion"].profile_id == profile["id"]
    assert app.session_state["jobs_preference_draft"].user_id == profile["user_id"]
    assert any(item.label == "Target titles" for item in app.text_area)
    app.button(key="jobs-confirm-preferences").click().run()

    assert not app.exception
    assert app.session_state["jobs_confirmed_preferences"].user_id == profile["user_id"]

    with sqlite3.connect(database) as connection:
        connection.execute(
            "DELETE FROM master_profiles WHERE profile_id = ?",
            (profile["id"],),
        )
        connection.commit()

    _navigate(app, "career_profile")
    _navigate(app, "jobs")

    assert not app.exception
    assert not any(item.key == "jobs-profile-selector" for item in app.selectbox)
    rendered = " ".join(
        [element.value for element in app.warning]
        + [element.value for element in app.info]
        + [element.value for element in app.subheader]
    )
    assert "A reviewed profile is required" in rendered


def test_streamlit_shows_collapsed_typed_composition_diagnostic(
    monkeypatch,
    tmp_path,
) -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "resume_composition_cases.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    profile = MasterProfile.model_validate(fixture["profile"]).model_copy(
        update={"id": "local-profile"}
    )
    posting = fixture["postings"]["firmware"]
    database = tmp_path / "composition-diagnostic.sqlite3"
    repository = SQLiteMasterProfileRepository(database)
    repository.save(profile)
    service = TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
        resume_composer=DeterministicResumeComposer(
            TemplateV1PageFitEvaluator(ParagraphLimitPageProvider())
        ),
        artifact_renderer=TemplateV1ArtifactRenderer(),
        generation_configuration=_generation_configuration(),
    )
    monkeypatch.setattr(
        dependencies,
        "create_profile_repository",
        lambda: SQLiteMasterProfileRepository(database),
    )
    monkeypatch.setattr(dependencies, "create_tailor_service", lambda: service)

    app_path = Path(__file__).parents[1] / "src" / "resume_tailor" / "frontend" / "app.py"
    app = AppTest.from_file(str(app_path)).run()
    _create_resume_strategy(app, posting["title"], posting["description"])
    app.button(key="resume-to-evidence").click().run()
    app.button(key="resume-build-document").click().run(timeout=10)

    diagnostic = app.session_state["resume"].composition_diagnostic
    assert diagnostic is not None
    assert diagnostic.selected_experience_ids
    assert diagnostic.termination_reason is not None
    artifact_fingerprint = app.session_state["generated_resume_artifact"].artifact_fingerprint

    _navigate(app, "jobs")

    assert (
        app.session_state["generated_resume_artifact"].artifact_fingerprint == artifact_fingerprint
    )

    _create_resume_strategy(
        app,
        posting["title"],
        posting["description"] + "\nChanged material requirement.",
    )

    assert "generated_resume_artifact" not in app.session_state
