from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from zipfile import ZipFile

from docx import Document
from lxml import etree

from resume_tailor.application.generated_artifact import (
    ResumeGenerationConfiguration,
    prepare_artifact_download,
)
from resume_tailor.application.generation_diagnostics import GenerationTelemetry
from resume_tailor.application.llm_services import HybridLlmServices
from resume_tailor.application.resume_composition import (
    CompositionSearchBounds,
    DeterministicResumeComposer,
)
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
from resume_tailor.domain.layout import PageUtilizationStatus
from resume_tailor.domain.llm_models import (
    BulletRewrite,
    BulletRewriteClaim,
    BulletRewriteOutput,
    BulletRewriteResult,
    LlmOperation,
)
from resume_tailor.domain.models import (
    ContactInfo,
    EntityKind,
    EvidenceItem,
    JobPosting,
    MasterProfile,
    ResumeItem,
    TemplateConstraints,
)
from resume_tailor.domain.resume_composition import (
    RESUME_COMPOSITION_CONTRACT_VERSION,
    PageFitEvaluation,
)
from resume_tailor.infrastructure.artifact_rendering import TemplateV1ArtifactRenderer
from resume_tailor.infrastructure.composition_page_fit import TemplateV1PageFitEvaluator
from resume_tailor.infrastructure.optimization import (
    DeterministicResumeOptimizer,
    EvidenceBoundResumeWriter,
)
from resume_tailor.infrastructure.profile_repository import SQLiteMasterProfileRepository
from resume_tailor.infrastructure.rendering import PageCountMeasurement
from resume_tailor.infrastructure.template_v1 import TEMPLATE_V1_DOCX_SHA256, TEMPLATE_V1_ID
from resume_tailor.ports.interfaces import ResumeArtifactRenderer
from tests.fakes import FakeResumeLanguageModel, metadata


class _FakeArtifactRenderer:
    def __init__(self, payload: bytes = b"PK\x03\x04controlled-docx") -> None:
        self.payload = payload
        self.calls = 0
        self.rendered_resume: object | None = None

    def render_docx_bytes(self, resume: object) -> bytes:
        self.calls += 1
        self.rendered_resume = resume
        return self.payload


class _ExactFixedPageFit:
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


class _ContentDensityPageFit:
    """Controlled exact page budget that still reacts to portfolio content."""

    def evaluate(
        self,
        resume: object,
        *,
        attempt_exact: bool = True,
    ) -> PageFitEvaluation:
        assert hasattr(resume, "experience_bullets")
        structured = resume
        bullet_count = sum(
            len(items)
            for section in (
                structured.experience_bullets,
                structured.project_bullets,
            )
            for items in section.values()
        )
        entry_count = len(structured.experiences) + len(structured.projects)
        utilization = 0.57 + (bullet_count * 0.035) + (entry_count * 0.012)
        fits = utilization <= 0.95
        return PageFitEvaluation(
            status=(
                PageUtilizationStatus.ACCEPTABLE_ONE_PAGE
                if fits
                else PageUtilizationStatus.OVERFLOW
            ),
            page_count=1 if fits else 2,
            exact=attempt_exact,
            provider="controlled content-density exact page fit",
            utilization_ratio=utilization,
            fits_one_page=fits,
        )


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
    renderer: ResumeArtifactRenderer,
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


def test_generated_word_order_cannot_create_portfolio_relevance() -> None:
    """Exercise the same writer, composer, artifact, and renderer path as Resume Studio."""

    posting = JobPosting(
        id="synthetic-mechatronics-posting",
        title="Mechatronics Engineer Intern",
        description=(
            "Core responsibilities:\n"
            "Debug embedded motor controls over CAN bus.\n"
            "Tune PID loop controls for actuator motion.\n"
            "Preferred qualifications:\n"
            "Create data reports for inventory workflows."
        ),
    )
    profile = MasterProfile(
        id="synthetic-portfolio-profile",
        user_id="synthetic-portfolio-user",
        display_name="Synthetic Candidate",
        experiences=[
            ResumeItem(
                id="mechatronics-entry",
                title="Mechatronics Intern",
                kind=EntityKind.EXPERIENCE,
            ),
            ResumeItem(
                id="digital-entry",
                title="Digital Engineering Intern",
                kind=EntityKind.EXPERIENCE,
            ),
        ],
        evidence=[
            EvidenceItem(
                id="motor-controls-evidence",
                entity_id="mechatronics-entry",
                source_text="Integrated motors with embedded controllers.",
            ),
            EvidenceItem(
                id="actuator-tuning-evidence",
                entity_id="mechatronics-entry",
                source_text="Validated actuator response with PID tuning.",
            ),
            EvidenceItem(
                id="digital-can-report",
                entity_id="digital-entry",
                source_text=(
                    "Automated data reports for inventory workflows and tracked CAN "
                    "logs with bus diagnostics."
                ),
            ),
            EvidenceItem(
                id="digital-pid-report",
                entity_id="digital-entry",
                source_text=(
                    "Automated data reports for inventory workflows, tracking PID "
                    "records and loop metrics."
                ),
            ),
        ],
    )
    generated_can = "Automated CAN bus diagnostics reports for inventory workflows."
    generated_pid = "Automated PID loop metrics reports for inventory workflows."
    rewrites = [
        BulletRewrite(
            entry_id="digital-entry",
            final_bullet_text=text,
            source_evidence_ids=[evidence_id],
            evidence_combined=False,
            confidence=0.95,
            claims=[
                BulletRewriteClaim(
                    text=text,
                    supporting_evidence_ids=[evidence_id],
                )
            ],
        )
        for evidence_id, text in (
            ("digital-can-report", generated_can),
            ("digital-pid-report", generated_pid),
        )
    ]
    fake = FakeResumeLanguageModel(
        rewrite_bullets=BulletRewriteResult(
            metadata=metadata(LlmOperation.REWRITE_BULLETS),
            output=BulletRewriteOutput(bullets=rewrites),
        )
    )
    renderer = _FakeArtifactRenderer()
    configuration = _configuration().model_copy(
        update={"feature_flags": {"bullet_rewrite": True}}
    )
    service = TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
        hybrid_services=HybridLlmServices(fake, 0, 2, False, False, True),
        resume_composer=DeterministicResumeComposer(
            _ExactFixedPageFit(),
            bounds=CompositionSearchBounds(
                maximum_selected_bullets=2,
                maximum_selected_entries=1,
                maximum_experience_entries=1,
                maximum_project_entries=0,
            ),
        ),
        artifact_renderer=renderer,
        generation_configuration=configuration,
    )
    service.start_generation()
    plan = service.create_plan(profile, posting, TemplateConstraints())

    artifact = service.build_generated_artifact(plan, profile, set())

    request = fake.requests["rewrite_bullets"][0]
    assert {group.entry_id for group in request.groups} == {
        "mechatronics-entry",
        "digital-entry",
    }
    assert artifact.writing_diagnostic is not None
    assert all(
        variant.validation_status.value == "validated"
        and variant.material_improvement
        for variant in artifact.writing_diagnostic.bullet_variants
    )
    assert artifact.composition_diagnostic is not None
    assert artifact.composition_diagnostic.selected_experience_ids == [
        "mechatronics-entry"
    ]
    assert set(artifact.final_resume.experience_bullets) == {"mechatronics-entry"}
    assert generated_can not in {
        bullet.text
        for bullets in artifact.final_resume.experience_bullets.values()
        for bullet in bullets
    }
    assert generated_pid not in {
        bullet.text
        for bullets in artifact.final_resume.experience_bullets.values()
        for bullet in bullets
    }
    assert not artifact.selected_bullet_variants
    assert renderer.rendered_resume is artifact.final_resume


def _mixed_domain_profile() -> MasterProfile:
    entries = [
        ResumeItem(id="motion-lab", title="Mechatronics Engineer", kind="experience"),
        ResumeItem(id="electronics-lab", title="Hardware Engineer", kind="experience"),
        ResumeItem(id="digital-lab", title="Digital Engineering Intern", kind="experience"),
        ResumeItem(id="robot-hand", title="Robotic Hand", kind="project"),
        ResumeItem(id="motor-fixture", title="Motor Test Fixture", kind="project"),
        ResumeItem(id="pcb-controller", title="Embedded Controller", kind="project"),
        ResumeItem(id="resume-app", title="Document Automation App", kind="project"),
    ]
    evidence_by_entry = {
        "motion-lab": [
            "Designed electromechanical prototypes with brushless motors and actuators.",
            "Created SolidWorks CAD assemblies and 3D-printed alignment fixtures.",
            "Debugged embedded C motor controls on physical hardware.",
            "Integrated wiring harnesses, encoders, and motor drivers.",
            "Documented hardware validation results and interface requirements.",
            "Tested the actuator assembly against mechanical requirements.",
            "Repeated actuator assembly tests against the same mechanical requirements.",
            "Recorded the same actuator test status for a second design review.",
        ],
        "electronics-lab": [
            "Built and soldered STM32 controller boards with motor-driver circuits.",
            "Debugged PCB power faults with an oscilloscope and multimeter.",
            "Assembled bench fixtures for electronics validation.",
            "Executed reliability tests on embedded hardware.",
            "Documented schematics, BOM revisions, and root-cause findings.",
        ],
        "digital-lab": [
            "Built Python AI document-classification pipelines and REST APIs.",
            "Automated cloud deployments and software regression tests.",
            "Debugged production data services and improved API latency by 30%.",
            "Created model-evaluation dashboards and technical documentation.",
        ],
        "robot-hand": [
            "Designed a cable-driven robotic hand with servo actuators.",
            "Built 3D-printed linkages and integrated embedded sensor feedback.",
            "Validated grasp motion and documented mechanical revisions.",
        ],
        "motor-fixture": [
            "Built a 3D-printed motor fixture with encoder alignment features.",
            "Soldered motor-driver wiring and measured current on the bench.",
            "Troubleshot vibration and revised the CAD assembly.",
        ],
        "pcb-controller": [
            "Designed and assembled a PCB for embedded actuator control.",
            "Validated sensor inputs and debugged power faults on the bench.",
            "Documented schematic and connector interfaces.",
        ],
        "resume-app": [
            "Built a Python AI document application with REST APIs.",
            "Automated document validation and cloud deployment.",
            "Evaluated ranking models and debugged production software workflows.",
        ],
    }
    evidence = [
        EvidenceItem(
            id=f"{entry_id}-proof-{index}",
            entity_id=entry_id,
            source_text=text,
        )
        for entry_id, texts in evidence_by_entry.items()
        for index, text in enumerate(texts, start=1)
    ]
    return MasterProfile(
        id="mixed-domain-profile",
        user_id="mixed-domain-user",
        display_name="Synthetic Candidate",
        experiences=[item for item in entries if item.kind is EntityKind.EXPERIENCE],
        projects=[item for item in entries if item.kind is EntityKind.PROJECT],
        evidence=evidence,
    )


def _deep_mixed_domain_profile() -> MasterProfile:
    payload = _mixed_domain_profile().model_dump(mode="python")
    entries = {
        item["id"]: item
        for item in [*payload["experiences"], *payload["projects"]]
    }
    entries["digital-lab"].update(
        {
            "technologies": ["Python", "automation", "testing"],
            "capabilities": ["documentation", "validation"],
        }
    )
    entries["resume-app"].update(
        {
            "technologies": ["Python", "automation"],
            "capabilities": ["documentation", "validation", "testing"],
        }
    )
    payload["evidence"].extend(
        [
            {
                "id": "motion-lab-proof-9",
                "entity_id": "motion-lab",
                "source_text": (
                    "Defined 30+ signals across ADC, DAC, PWM, I2C, UART, and "
                    "motor-driver interfaces in a controlled interface record."
                ),
            },
            {
                "id": "motion-lab-proof-10",
                "entity_id": "motion-lab",
                "source_text": (
                    "Verified connector pinouts, wiring continuity, and sensor channels "
                    "before integrated actuator testing."
                ),
            },
            {
                "id": "motion-lab-proof-11",
                "entity_id": "motion-lab",
                "source_text": (
                    "Inspected prototype electronics, reworked solder joints, and "
                    "documented corrective actions from bench debugging."
                ),
            },
        ]
    )
    return MasterProfile.model_validate(payload)


def _mixed_domain_artifact(
    posting: JobPosting,
    profile: MasterProfile | None = None,
) -> GeneratedResumeArtifact:
    resolved_profile = profile or _mixed_domain_profile()
    renderer = _FakeArtifactRenderer()
    service = TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
        resume_composer=DeterministicResumeComposer(_ContentDensityPageFit()),
        artifact_renderer=renderer,
        generation_configuration=_configuration(),
    )
    service.start_generation()
    plan = service.create_plan(resolved_profile, posting, TemplateConstraints())
    artifact = service.build_generated_artifact(plan, resolved_profile, set())
    assert renderer.rendered_resume is artifact.final_resume
    return artifact


def test_production_artifact_path_reverses_mixed_portfolio_by_posting_domain() -> None:
    hardware = _mixed_domain_artifact(
        JobPosting(
            id="mixed-hardware-posting",
            title="Mechatronics Engineer Intern",
            description=(
                "Build electromechanical prototypes with motors and actuators. Design "
                "embedded electronics and PCBs. Create mechanical CAD and 3D-printed "
                "fixtures. Prototype robotic mechanisms with servo feedback. Solder "
                "assemblies, perform bench hardware testing and "
                "validation, troubleshoot faults, and maintain engineering documentation."
            ),
        )
    )
    software = _mixed_domain_artifact(
        JobPosting(
            id="mixed-software-posting",
            title="Software AI Engineer Intern",
            description=(
                "Build Python AI applications and REST APIs. Deploy cloud data pipelines "
                "and automation workflows. Create software regression tests, debug "
                "production services, evaluate models, build dashboards, and maintain "
                "technical documentation."
            ),
        )
    )

    hardware_diagnostic = hardware.composition_diagnostic
    software_diagnostic = software.composition_diagnostic
    assert hardware_diagnostic is not None
    assert software_diagnostic is not None
    assert "motion-lab" in hardware_diagnostic.selected_experience_ids
    assert len(
        {"robot-hand", "motor-fixture", "pcb-controller"}
        & set(hardware_diagnostic.selected_project_ids)
    ) >= 2
    assert "digital-lab" not in hardware_diagnostic.selected_experience_ids
    assert "resume-app" not in hardware_diagnostic.selected_project_ids
    assert hardware_diagnostic.bullet_counts["motion-lab"] >= 3
    assert all(
        hardware_diagnostic.bullet_counts[entry_id] >= 2
        for entry_id in hardware_diagnostic.selected_project_ids
    )

    assert "digital-lab" in software_diagnostic.selected_experience_ids
    assert "resume-app" in software_diagnostic.selected_project_ids
    assert software_diagnostic.bullet_counts["digital-lab"] >= 3
    assert software_diagnostic.bullet_counts["resume-app"] >= 2
    assert software_diagnostic.bullet_counts.get("electronics-lab", 0) == 0
    assert hardware.pagination_diagnostic.status == "exact"
    assert software.pagination_diagnostic.status == "exact"


def test_production_artifact_rejects_context_neutral_entry_metadata_broadcast() -> None:
    artifact = _mixed_domain_artifact(
        JobPosting(
            id="deep-hardware-allocation-posting",
            title="Mechatronics Engineer Intern - Hardware",
            description=(
                "Design, assemble, test, and debug electromechanical prototypes using "
                "motors, PCBs, fixtures, and development hardware. Perform PCB bring-up, "
                "inspection, soldering, rework, and bench debugging. Create CAD fixtures "
                "and 3D-printed parts for fit and assembly. Test embedded hardware and "
                "troubleshoot mechanical, electrical, and embedded systems. Build test "
                "setups, execute reliability validation, and document engineering results. "
                "Use Python for hardware control, telemetry, automation, and logging."
            ),
        ),
        _deep_mixed_domain_profile(),
    )
    diagnostic = artifact.composition_diagnostic
    retrieval = artifact.writing_diagnostic.retrieval

    assert diagnostic is not None
    assert retrieval is not None
    assert "motion-lab" in diagnostic.selected_experience_ids
    assert diagnostic.bullet_counts["motion-lab"] >= 3
    assert "digital-lab" not in diagnostic.selected_experience_ids
    assert "resume-app" not in diagnostic.selected_project_ids
    cross_domain = [
        item
        for item in [*retrieval.admitted, *retrieval.rejected]
        if item.entry_id in {"digital-lab", "resume-app"}
    ]
    assert cross_domain
    assert all(not item.direct_requirement_ids for item in cross_domain)
    assert all(len(item.adjacent_requirement_ids) <= 1 for item in cross_domain)
    assert max(item.contextual_relevance for item in cross_domain) < 10.0


def test_production_portfolio_is_invariant_to_redundant_entry_volume() -> None:
    posting = JobPosting(
        id="redundant-volume-hardware-posting",
        title="Mechatronics Engineer Intern",
        description=(
            "Build electromechanical motor prototypes, create mechanical CAD and "
            "3D-printed fixtures, assemble PCBs, solder wiring, and debug embedded "
            "hardware through bench validation."
        ),
    )
    profile = _mixed_domain_profile()
    duplicate_source = next(
        item.source_text
        for item in profile.evidence
        if item.id == "motion-lab-proof-6"
    )
    grown = profile.model_copy(
        update={
            "evidence": [
                *profile.evidence,
                *[
                    EvidenceItem(
                        id=f"redundant-motion-proof-{index}",
                        entity_id="motion-lab",
                        source_text=duplicate_source,
                    )
                    for index in range(16)
                ],
            ]
        }
    )

    baseline = _mixed_domain_artifact(posting, profile).composition_diagnostic
    expanded = _mixed_domain_artifact(posting, grown).composition_diagnostic

    assert baseline is not None
    assert expanded is not None
    assert expanded.selected_experience_ids == baseline.selected_experience_ids
    assert expanded.selected_project_ids == baseline.selected_project_ids
    assert expanded.selected_bullet_ids == baseline.selected_bullet_ids


def test_production_artifact_path_compacts_legacy_profile_contact_links(
    tmp_path,
) -> None:
    profile = _profile().model_copy(
        update={
            "contact": ContactInfo(
                email="candidate@example.test",
                phone="555-0100",
                location="Example City, ZZ",
                links=[
                    "https://www.linkedin.com/in/example-candidate",
                    "https://github.com/example-candidate",
                    "https://portfolio.example.test/work%20samples",
                ],
            )
        }
    )
    repository = SQLiteMasterProfileRepository(tmp_path / "legacy-profile.sqlite3")
    repository.save(profile)
    loaded = repository.get(profile.id)
    assert loaded is not None
    assert loaded.contact.hyperlinks == []

    service = _service(TemplateV1ArtifactRenderer())
    service.start_generation()
    plan = service.create_plan(loaded, _posting(), TemplateConstraints())
    artifact = service.build_generated_artifact(plan, loaded, set())

    with ZipFile(BytesIO(artifact.docx_bytes)) as package:
        root = etree.fromstring(package.read("word/document.xml"))
        relationships = package.read("word/_rels/document.xml.rels").decode()
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    contact = root.xpath("//w:body/w:p", namespaces=namespace)[1]
    visible = "".join(contact.xpath(".//w:t/text()", namespaces=namespace))
    hyperlink_text = contact.xpath("./w:hyperlink//w:t/text()", namespaces=namespace)

    assert visible == (
        "Email | 555-0100 | Example City, ZZ | LinkedIn | GitHub | Portfolio"
    )
    assert hyperlink_text == ["Email", "LinkedIn", "GitHub", "Portfolio"]
    assert "candidate@example.test" not in visible
    assert "https://" not in visible
    assert "%20" not in visible
    assert "mailto:candidate@example.test" in relationships
    assert "https://www.linkedin.com/in/example-candidate" in relationships
    assert "https://github.com/example-candidate" in relationships
    assert "https://portfolio.example.test/work%20samples" in relationships


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


def test_approval_makes_rewrite_eligible_but_does_not_force_it_over_source() -> None:
    profile = MasterProfile.model_validate(
        {
            "id": "approval-competition-profile",
            "user_id": "approval-competition-user",
            "display_name": "Synthetic Candidate",
            "experiences": [
                {
                    "id": "controls-entry",
                    "title": "Controls Developer",
                    "kind": "experience",
                }
            ],
            "evidence": [
                {
                    "id": "control-evidence",
                    "entity_id": "controls-entry",
                    "source_text": (
                        "Responsible for validating STM32 motor controls using SPI "
                        "feedback at 30 Hz."
                    ),
                    "technologies": ["STM32", "SPI"],
                    "outcomes": ["30 Hz"],
                },
                {
                    "id": "fault-evidence",
                    "entity_id": "controls-entry",
                    "source_text": "Debugged embedded motor-control timing faults.",
                },
            ],
        }
    )
    posting = JobPosting(
        id="approval-competition-posting",
        title="Embedded Controls Developer",
        description="Validate STM32 motor controls with SPI feedback and debug timing faults.",
    )
    shortened = "Validated STM32 controls at 30 Hz."
    fake = FakeResumeLanguageModel(
        rewrite_bullets=BulletRewriteResult(
            metadata=metadata(LlmOperation.REWRITE_BULLETS),
            output=BulletRewriteOutput(
                bullets=[
                    BulletRewrite(
                        entry_id="controls-entry",
                        final_bullet_text=shortened,
                        source_evidence_ids=["control-evidence"],
                        preserved_technologies=["STM32"],
                        preserved_metrics=["30 Hz"],
                        evidence_combined=False,
                        support="strongly_implied",
                        confidence=0.9,
                    )
                ]
            ),
        )
    )
    service = TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
        hybrid_services=HybridLlmServices(fake, 0, 4, False, False, True),
        resume_composer=DeterministicResumeComposer(_ExactFixedPageFit()),
        artifact_renderer=_FakeArtifactRenderer(),
        generation_configuration=_configuration().model_copy(
            update={"feature_flags": {"bullet_rewrite": True}}
        ),
    )
    service.start_generation()
    plan = service.create_plan(profile, posting, TemplateConstraints())
    initial = service.build_generated_artifact(plan, profile, set())
    review_id = next(
        item.variant_id
        for item in initial.writing_diagnostic.bullet_variants
        if item.validation_status.value == "review_required"
    )

    rebuilt = service.build_generated_artifact(
        plan,
        profile,
        {review_id},
        existing_artifact=initial,
    )
    rendered_text = {
        bullet.text
        for bullets in rebuilt.final_resume.experience_bullets.values()
        for bullet in bullets
    }

    assert shortened not in rendered_text
    assert (
        "Responsible for validating STM32 motor controls using SPI feedback at 30 Hz."
        in rendered_text
    )
    assert not rebuilt.selected_bullet_variants
