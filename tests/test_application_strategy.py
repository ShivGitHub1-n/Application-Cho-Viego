from __future__ import annotations

from collections.abc import Iterable

import pytest

from resume_tailor.application.llm_prompts import task_prompt
from resume_tailor.application.llm_services import HybridLlmServices
from resume_tailor.application.resume_composition import (
    DeterministicResumeComposer,
    ExactPaginationRequiredError,
)
from resume_tailor.application.services import TailorResumeService
from resume_tailor.domain.application_strategy import (
    APPLICATION_STRATEGY_CONTRACT_VERSION,
    APPLICATION_STRATEGY_RESERVE_MAXIMUM_ACTIONS,
    EvidencePriorityTier,
    SourceWordingAssessment,
    StrategyExpansionOrigin,
    StrategyValidationIssueCode,
)
from resume_tailor.domain.hybrid_resume import HybridPlanningStatus
from resume_tailor.domain.layout import PageUtilizationStatus
from resume_tailor.domain.llm_models import (
    ApplicationStrategyOutput,
    ApplicationStrategyResult,
    BulletRewriteOutput,
    BulletRewriteResult,
    LanguageModelError,
    LanguageModelErrorKind,
    LlmOperation,
    ProposedLowPriorityEntry,
    ProposedStrategyEntry,
    ProposedStrategyEvidence,
    ProposedStrategyExpansionAction,
    ProposedStrategyRolePriority,
)
from resume_tailor.domain.models import (
    EntityKind,
    EvidenceItem,
    JobPosting,
    MasterProfile,
    ResumeItem,
    TemplateConstraints,
)
from resume_tailor.domain.resume_composition import (
    STRATEGY_UTILIZATION_ACCEPTABLE_FLOOR,
    STRATEGY_UTILIZATION_PREFERRED_CEILING,
    STRATEGY_UTILIZATION_PREFERRED_FLOOR,
    TEMPLATE_V1_SEVERE_UNDERFILL_FLOOR,
    PageFitEvaluation,
)
from resume_tailor.infrastructure.optimization import (
    DeterministicResumeOptimizer,
    EvidenceBoundResumeWriter,
)
from tests.fakes import FakeResumeLanguageModel, metadata


class ControlledPageFit:
    def __init__(self, maximum_bullets: int = 24) -> None:
        self.maximum_bullets = maximum_bullets

    def evaluate(self, resume: object, *, attempt_exact: bool = True) -> PageFitEvaluation:
        bullet_count = sum(
            len(items)
            for section in (resume.experience_bullets, resume.project_bullets)
            for items in section.values()
        )
        fits = bullet_count <= self.maximum_bullets
        return PageFitEvaluation(
            status=(
                PageUtilizationStatus.ACCEPTABLE_ONE_PAGE
                if fits
                else PageUtilizationStatus.OVERFLOW
            ),
            page_count=1 if fits else 2,
            exact=attempt_exact,
            provider="controlled exact paginator",
            utilization_ratio=min(1.15, 0.50 + bullet_count * 0.07),
            fits_one_page=fits,
        )


class UnverifiedPageFit(ControlledPageFit):
    def evaluate(self, resume: object, *, attempt_exact: bool = True) -> PageFitEvaluation:
        result = super().evaluate(resume, attempt_exact=attempt_exact)
        if not attempt_exact:
            return result
        return result.model_copy(
            update={
                "exact": False,
                "page_count": None,
                "provider": "unavailable exact paginator",
                "verification_failure": "Controlled paginator unavailable.",
            }
        )


class UnderfillExpansionPageFit:
    def __init__(self, *, exact_overflow_above: int | None = None) -> None:
        self.exact_overflow_above = exact_overflow_above
        self.observed: list[tuple[int, bool, float, int]] = []

    @staticmethod
    def _bullet_count(resume: object) -> int:
        return sum(
            len(items)
            for section in (resume.experience_bullets, resume.project_bullets)
            for items in section.values()
        )

    def evaluate(self, resume: object, *, attempt_exact: bool = True) -> PageFitEvaluation:
        bullet_count = self._bullet_count(resume)
        utilization = min(0.96, 0.23 + (0.044 * bullet_count))
        overflow = bool(
            attempt_exact
            and self.exact_overflow_above is not None
            and bullet_count > self.exact_overflow_above
        )
        self.observed.append((bullet_count, attempt_exact, utilization, 2 if overflow else 1))
        return PageFitEvaluation(
            status=(
                PageUtilizationStatus.OVERFLOW
                if overflow
                else PageUtilizationStatus.SEVERE_UNDERFILL
                if utilization < 0.75
                else PageUtilizationStatus.UNDERFILLED
                if utilization < 0.84
                else PageUtilizationStatus.ACCEPTABLE_ONE_PAGE
            ),
            page_count=2 if overflow else 1,
            exact=attempt_exact,
            provider="controlled rendered-DOCX geometry and exact paginator",
            utilization_ratio=utilization,
            fits_one_page=not overflow,
        )

    def evaluate_batch(self, resumes: list[object]) -> list[PageFitEvaluation]:
        return [self.evaluate(resume, attempt_exact=True) for resume in resumes]


class OneStepAlternativePageFit(UnderfillExpansionPageFit):
    def __init__(self, core_bullets: int = 11) -> None:
        super().__init__()
        self.core_bullets = core_bullets

    def evaluate(self, resume: object, *, attempt_exact: bool = True) -> PageFitEvaluation:
        bullet_count = self._bullet_count(resume)
        utilization = 0.69 if bullet_count <= self.core_bullets else 0.86
        self.observed.append((bullet_count, attempt_exact, utilization, 1))
        return PageFitEvaluation(
            status=(
                PageUtilizationStatus.SEVERE_UNDERFILL
                if bullet_count <= self.core_bullets
                else PageUtilizationStatus.ACCEPTABLE_ONE_PAGE
            ),
            page_count=1,
            exact=attempt_exact,
            provider="controlled rendered-DOCX geometry and exact paginator",
            utilization_ratio=utilization,
            fits_one_page=True,
        )


class LiveUnderfillReservePageFit(UnderfillExpansionPageFit):
    def __init__(self) -> None:
        super().__init__()
        self.evaluations: list[tuple[frozenset[str], bool, float, int]] = []

    @staticmethod
    def _evidence_ids(resume: object) -> frozenset[str]:
        return frozenset(
            evidence_id
            for section in (resume.experience_bullets, resume.project_bullets)
            for bullets in section.values()
            for bullet in bullets
            for evidence_id in bullet.evidence_ids
        )

    def evaluate(self, resume: object, *, attempt_exact: bool = True) -> PageFitEvaluation:
        evidence_ids = self._evidence_ids(resume)
        preferred_but_overflowing = "mech-feedback" in evidence_ids
        later_new_entry_fits = {
            "arm-cad",
            "arm-test",
            "arm-transmission",
        }.issubset(evidence_ids)
        later_same_entry_fits = "mech-cad" in evidence_ids
        utilization = (
            0.90
            if preferred_but_overflowing
            else 0.89
            if later_new_entry_fits
            else 0.85
            if later_same_entry_fits
            else 0.69
        )
        overflow = attempt_exact and preferred_but_overflowing
        page_count = 2 if overflow else 1
        self.evaluations.append((evidence_ids, attempt_exact, utilization, page_count))
        return PageFitEvaluation(
            status=(
                PageUtilizationStatus.OVERFLOW
                if overflow
                else PageUtilizationStatus.SEVERE_UNDERFILL
                if utilization < 0.75
                else PageUtilizationStatus.UNDERFILLED
                if utilization < 0.84
                else PageUtilizationStatus.ACCEPTABLE_ONE_PAGE
            ),
            page_count=page_count,
            exact=attempt_exact,
            provider="controlled live-shaped exact paginator",
            utilization_ratio=utilization,
            fits_one_page=not overflow,
        )


class DeepReserveCoveragePageFit(UnderfillExpansionPageFit):
    def __init__(self, core_bullets: int = 8) -> None:
        super().__init__()
        self.core_bullets = core_bullets

    def evaluate(self, resume: object, *, attempt_exact: bool = True) -> PageFitEvaluation:
        bullet_count = self._bullet_count(resume)
        utilization = min(0.94, 0.67 + (0.045 * max(0, bullet_count - self.core_bullets)))
        self.observed.append((bullet_count, attempt_exact, utilization, 1))
        return PageFitEvaluation(
            status=(
                PageUtilizationStatus.SEVERE_UNDERFILL
                if utilization < 0.75
                else PageUtilizationStatus.UNDERFILLED
                if utilization < 0.84
                else PageUtilizationStatus.ACCEPTABLE_ONE_PAGE
            ),
            page_count=1,
            exact=attempt_exact,
            provider="controlled deep-reserve exact paginator",
            utilization_ratio=utilization,
            fits_one_page=True,
        )


def _entry(entry_id: str, title: str, kind: EntityKind) -> ResumeItem:
    return ResumeItem(
        id=entry_id,
        title=title,
        kind=kind,
        organization="Sanitized Engineering Group",
        start_date="2023",
        end_date="Present",
    )


def _evidence(
    entry_id: str,
    item_id: str,
    text: str,
    technologies: Iterable[str],
) -> EvidenceItem:
    return EvidenceItem(
        id=item_id,
        entity_id=entry_id,
        source_text=text,
        technologies=list(technologies),
        capabilities=["reviewed technical delivery"],
    )


def _mixed_profile(*, add_large_library: bool = False) -> MasterProfile:
    experiences = [
        _entry("mech", "Mechatronics Engineer", EntityKind.EXPERIENCE),
        _entry("rd", "R&D Hardware Engineer", EntityKind.EXPERIENCE),
        _entry("digital", "Digital Engineering Intern", EntityKind.EXPERIENCE),
        _entry("software", "Software Engineering Intern", EntityKind.EXPERIENCE),
    ]
    projects = [
        _entry("hand", "Electromechanical Hand", EntityKind.PROJECT),
        _entry("arm", "Long-Reach Actuator", EntityKind.PROJECT),
        _entry("resume-tool", "Resume Workflow Tool", EntityKind.PROJECT),
    ]
    evidence = [
        _evidence(
            "mech",
            "mech-control",
            "Implemented STM32 motor control with PWM and encoder feedback.",
            ["STM32", "PWM"],
        ),
        _evidence(
            "mech",
            "mech-interfaces",
            "Defined ADC, DAC, I2C, UART, and motor-driver electrical interfaces.",
            ["ADC", "DAC", "I2C", "UART"],
        ),
        _evidence(
            "mech",
            "mech-safety",
            "Bench-tested interlocks and debugged electromechanical safety faults.",
            ["interlocks"],
        ),
        _evidence(
            "mech",
            "mech-cad",
            "Designed SolidWorks fixtures for repeatable actuator assembly and test.",
            ["SolidWorks"],
        ),
        _evidence(
            "mech",
            "mech-feedback",
            "Tuned encoder feedback and current limits during actuator bench validation.",
            ["encoders", "current sensing"],
        ),
        _evidence(
            "mech",
            "mech-repeat",
            "Implemented STM32 motor control with PWM and encoder feedback.",
            ["STM32", "PWM"],
        ),
        _evidence(
            "rd",
            "rd-wiring",
            "Integrated sensors, wiring, and embedded controllers on a physical prototype.",
            ["sensors"],
        ),
        _evidence(
            "rd",
            "rd-test",
            "Built a hardware test fixture and documented bring-up findings.",
            ["test fixture"],
        ),
        _evidence(
            "rd",
            "rd-power",
            "Prototyped regulated power distribution and protected sensor interfaces.",
            ["power distribution", "sensors"],
        ),
        _evidence(
            "rd",
            "rd-validation",
            "Recorded repeatable electrical and mechanical validation results across builds.",
            ["validation"],
        ),
        _evidence(
            "digital",
            "digital-ai",
            "Evaluated retrieval quality for an AI engineering knowledge system.",
            ["Python", "AI"],
        ),
        _evidence(
            "digital",
            "digital-docs",
            "Automated documentation checks in a Python data pipeline.",
            ["Python"],
        ),
        _evidence(
            "software",
            "software-api",
            "Implemented typed Python APIs and database migrations.",
            ["Python", "SQL"],
        ),
        _evidence(
            "software",
            "software-tests",
            "Added integration tests and CI validation for a web service.",
            ["CI"],
        ),
        _evidence(
            "software",
            "software-observability",
            "Added structured telemetry and failure diagnostics to a production Python service.",
            ["Python", "telemetry"],
        ),
        _evidence(
            "hand",
            "hand-build",
            "Assembled a motorized robotic hand with embedded sensing.",
            ["motors", "sensors"],
        ),
        _evidence(
            "hand",
            "hand-vision",
            "Connected a vision model to gesture commands for the robotic hand.",
            ["computer vision"],
        ),
        _evidence(
            "hand",
            "hand-control",
            "Validated closed-loop finger motion using motor-current and position feedback.",
            ["feedback control"],
        ),
        _evidence(
            "arm",
            "arm-cad",
            "Designed and 3D-printed actuator mounts for a long-reach mechanism.",
            ["CAD", "3D printing"],
        ),
        _evidence(
            "arm",
            "arm-test",
            "Validated actuator fit, range, and mechanical alignment on the bench.",
            ["actuator"],
        ),
        _evidence(
            "arm",
            "arm-transmission",
            "Built and tested a compact mechanical transmission for the long-reach actuator.",
            ["mechanical transmission", "actuator"],
        ),
        _evidence(
            "resume-tool",
            "resume-rag",
            "Built a retrieval pipeline for evidence-backed resume suggestions.",
            ["Python", "RAG"],
        ),
        _evidence(
            "resume-tool",
            "resume-ui",
            "Implemented a typed review workflow and export service.",
            ["Python"],
        ),
    ]
    if add_large_library:
        evidence.extend(
            _evidence(
                "digital",
                f"digital-duplicate-{index}",
                f"Documented routine analytics pipeline check number {index}.",
                ["Python"],
            )
            for index in range(12)
        )
    return MasterProfile(
        id="strategy-profile",
        user_id="strategy-user",
        display_name="Jordan Candidate",
        experiences=experiences,
        projects=projects,
        evidence=evidence,
    )


def _deep_hardware_profile() -> MasterProfile:
    profile = _mixed_profile()
    return profile.model_copy(
        update={
            "evidence": [
                *profile.evidence,
                _evidence(
                    "mech",
                    "mech-power",
                    "Validated protected power distribution during motor-load testing.",
                    ["power distribution", "motor load"],
                ),
                _evidence(
                    "mech",
                    "mech-thermal",
                    "Tested thermal protection and fault recovery on the actuator controller.",
                    ["thermal protection", "actuator controller"],
                ),
                _evidence(
                    "hand",
                    "hand-sensing",
                    "Integrated position sensors and embedded signal conditioning for the hand.",
                    ["position sensors", "signal conditioning"],
                ),
            ]
        }
    )


def _hardware_posting() -> JobPosting:
    return JobPosting(
        id="hardware-role",
        title="Mechatronics Hardware Intern",
        description=(
            "Design, assemble, test, and debug electromechanical prototypes. Bring up "
            "motor-control hardware, embedded interfaces, CAD fixtures, wiring, and sensors."
        ),
    )


def _software_posting() -> JobPosting:
    return JobPosting(
        id="software-role",
        title="Software and AI Engineering Intern",
        description=(
            "Build typed Python services, retrieval systems, databases, CI tests, and AI "
            "evaluation tooling for a production software platform."
        ),
    )


def _selection(
    entry_id: str,
    evidence_ids: list[str],
    priority: EvidencePriorityTier,
    *,
    reason: str | None = None,
) -> ProposedStrategyEntry:
    return ProposedStrategyEntry(
        entry_id=entry_id,
        reason=reason or f"The reviewed {entry_id} work supports the application thesis.",
        desired_depth=len(evidence_ids),
        selected_evidence=[
            ProposedStrategyEvidence(
                evidence_id=evidence_id,
                priority=priority,
                source_wording=SourceWordingAssessment.STRONG,
            )
            for evidence_id in evidence_ids
        ],
    )


def _hardware_core_entries(
    *,
    mechatronics_alternatives: list[str] | None = None,
) -> list[ProposedStrategyEntry]:
    entries = [
        _selection(
            "mech",
            ["mech-control", "mech-interfaces", "mech-safety", "mech-cad"],
            EvidencePriorityTier.CRITICAL,
        ),
        _selection(
            "rd",
            ["rd-wiring", "rd-test", "rd-power", "rd-validation"],
            EvidencePriorityTier.HIGH,
        ),
        _selection(
            "hand",
            ["hand-build", "hand-vision", "hand-control"],
            EvidencePriorityTier.MEDIUM,
        ),
    ]
    alternatives = mechatronics_alternatives or []
    if alternatives:
        entries[0] = entries[0].model_copy(
            update={
                "alternative_evidence": [
                    ProposedStrategyEvidence(
                        evidence_id=evidence_id,
                        priority=EvidencePriorityTier.HIGH,
                        source_wording=SourceWordingAssessment.STRONG,
                    )
                    for evidence_id in alternatives
                ]
            }
        )
    return entries


def _strategy_result(
    selected_entries: list[ProposedStrategyEntry],
    *,
    thesis: str,
    low_priority: list[str] | None = None,
    expansion_reserve: list[ProposedStrategyExpansionAction] | None = None,
) -> ApplicationStrategyResult:
    return ApplicationStrategyResult(
        metadata=metadata(LlmOperation.APPLICATION_STRATEGY),
        output=ApplicationStrategyOutput(
            application_thesis=thesis,
            role_priorities=[
                ProposedStrategyRolePriority(theme="Deliver the role's material technical work")
            ],
            selected_entries=selected_entries,
            expansion_reserve=expansion_reserve or [],
            low_priority_entries=[
                ProposedLowPriorityEntry(
                    entry_id=entry_id,
                    reason="Contributes less distinct evidence to this application.",
                )
                for entry_id in (low_priority or [])
            ],
            global_evidence_priority=[
                item.evidence_id for entry in selected_entries for item in entry.selected_evidence
            ],
        ),
    )


def _service(
    fake: FakeResumeLanguageModel | None,
    *,
    writing: bool = False,
    maximum_bullets: int = 24,
    page_fit: object | None = None,
) -> TailorResumeService:
    return TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
        hybrid_services=HybridLlmServices(
            fake,
            0,
            2,
            False,
            False,
            writing,
            enable_application_strategy=True,
        ),
        resume_composer=DeterministicResumeComposer(
            page_fit or ControlledPageFit(maximum_bullets=maximum_bullets)
        ),
    )


def _selected_entry_ids(resume: object) -> set[str]:
    return {*resume.experience_bullets, *resume.project_bullets}


def test_hardware_strategy_owns_the_final_portfolio_and_receives_complete_bank() -> None:
    profile = _mixed_profile(add_large_library=True)
    result = _strategy_result(
        [
            _selection(
                "mech",
                ["mech-control", "mech-interfaces", "mech-safety"],
                EvidencePriorityTier.CRITICAL,
            ),
            _selection("rd", ["rd-wiring", "rd-test"], EvidencePriorityTier.HIGH),
            _selection("arm", ["arm-cad", "arm-test"], EvidencePriorityTier.HIGH),
        ],
        thesis=(
            "A multidisciplinary builder strongest at embedded, electrical, and "
            "mechanical integration."
        ),
        low_priority=["digital", "software", "resume-tool"],
    )
    fake = FakeResumeLanguageModel(recommend_application_strategy=result)
    service = _service(fake)

    plan = service.create_plan(profile, _hardware_posting(), TemplateConstraints())
    resume = service.build_document(plan, profile, set())

    request = fake.requests["recommend_application_strategy"][0]
    assert sum(len(entry.evidence) for entry in request.entries) == len(profile.evidence)
    assert plan.application_strategy is not None
    assert _selected_entry_ids(resume) == {"mech", "rd", "arm"}
    assert "digital" not in resume.experience_bullets
    assert "resume-tool" not in resume.project_bullets
    assert fake.calls["recommend_application_strategy"] == 1
    assert resume.hybrid_diagnostic is not None
    assert resume.hybrid_diagnostic.planning_status is HybridPlanningStatus.STRATEGY_APPLIED


def test_software_reverse_and_multidisciplinary_strategies_are_symmetric() -> None:
    profile = _mixed_profile()
    software_result = _strategy_result(
        [
            _selection("digital", ["digital-ai", "digital-docs"], EvidencePriorityTier.CRITICAL),
            _selection("software", ["software-api", "software-tests"], EvidencePriorityTier.HIGH),
            _selection("resume-tool", ["resume-rag", "resume-ui"], EvidencePriorityTier.HIGH),
        ],
        thesis=(
            "A software candidate grounded in typed services, retrieval, evaluation, and delivery."
        ),
        low_priority=["mech", "rd", "hand", "arm"],
    )
    software_fake = FakeResumeLanguageModel(recommend_application_strategy=software_result)
    software_service = _service(software_fake)
    software_plan = software_service.create_plan(
        profile,
        _software_posting(),
        TemplateConstraints(),
    )
    software_resume = software_service.build_document(software_plan, profile, set())
    assert _selected_entry_ids(software_resume) == {"digital", "software", "resume-tool"}

    mixed_result = _strategy_result(
        [
            _selection("mech", ["mech-control", "mech-interfaces"], EvidencePriorityTier.CRITICAL),
            _selection("digital", ["digital-ai", "digital-docs"], EvidencePriorityTier.HIGH),
            _selection("hand", ["hand-build"], EvidencePriorityTier.MEDIUM),
        ],
        thesis="A physical-systems engineer who can connect embedded hardware with AI tooling.",
    )
    mixed_fake = FakeResumeLanguageModel(recommend_application_strategy=mixed_result)
    mixed_service = _service(mixed_fake)
    mixed_posting = JobPosting(
        id="mixed-role",
        title="Robotics Systems Intern",
        description=(
            "Integrate motors and embedded control with perception software and AI evaluation."
        ),
    )
    mixed_plan = mixed_service.create_plan(profile, mixed_posting, TemplateConstraints())
    mixed_resume = mixed_service.build_document(mixed_plan, profile, set())
    assert _selected_entry_ids(mixed_resume) == {"mech", "digital", "hand"}


def test_strategy_validation_preserves_valid_remainder_and_title_integrity() -> None:
    source_profile = _mixed_profile()
    profile = source_profile.model_copy(
        update={
            "evidence": [
                item.model_copy(
                    update={
                        "source_text": (
                            "Implemented STM32 motor control as Lead Mechatronics Engineer "
                            "for an electromechanical platform."
                        )
                    }
                )
                if item.id == "mech-control"
                else item
                for item in source_profile.evidence
            ]
        }
    )
    result = _strategy_result(
        [
            _selection(
                "mech",
                ["missing-evidence", "mech-control", "mech-interfaces"],
                EvidencePriorityTier.CRITICAL,
                reason="Use the Lead Mechatronics Engineer work as the senior anchor.",
            ),
            _selection("rd", ["software-api", "rd-wiring", "rd-test"], EvidencePriorityTier.HIGH),
        ],
        thesis="Use reviewed multidisciplinary evidence without changing title authority.",
    )
    fake = FakeResumeLanguageModel(recommend_application_strategy=result)
    service = _service(fake)

    plan = service.create_plan(profile, _hardware_posting(), TemplateConstraints())

    assert plan.application_strategy is not None
    assert plan.application_strategy.selected_evidence_ids == [
        "mech-control",
        "mech-interfaces",
        "rd-wiring",
        "rd-test",
    ]
    assert plan.application_strategy.selected_entries[0].reason == (
        "Selected from reviewed evidence for this application."
    )
    codes = {item.code for item in plan.application_strategy.validation_issues}
    assert StrategyValidationIssueCode.UNKNOWN_EVIDENCE in codes
    assert StrategyValidationIssueCode.WRONG_ENTRY in codes
    assert StrategyValidationIssueCode.TITLE_INTEGRITY in codes
    resume = service.build_document(plan, profile, set())
    rendered_text = " ".join(bullet.text for bullet in resume.experience_bullets["mech"])
    assert "Lead Mechatronics Engineer" not in rendered_text
    assert "STM32 motor control" in rendered_text


def test_page_fit_removes_optional_strategy_evidence_before_high_or_critical() -> None:
    profile = _mixed_profile()
    result = _strategy_result(
        [
            _selection("mech", ["mech-control", "mech-interfaces"], EvidencePriorityTier.CRITICAL),
            _selection("rd", ["rd-wiring", "rd-test"], EvidencePriorityTier.HIGH),
            _selection("arm", ["arm-cad", "arm-test"], EvidencePriorityTier.OPTIONAL),
        ],
        thesis="Preserve the strongest integration evidence before optional supporting projects.",
    )
    fake = FakeResumeLanguageModel(recommend_application_strategy=result)
    service = _service(fake, maximum_bullets=4)

    plan = service.create_plan(profile, _hardware_posting(), TemplateConstraints())
    resume = service.build_document(plan, profile, set())

    assert _selected_entry_ids(resume) == {"mech", "rd"}
    assert "arm" not in resume.project_bullets
    assert resume.composition_diagnostic is not None
    assert resume.composition_diagnostic.verification_status.value == "exact"


def test_core_rollback_trims_depth_before_eliminating_a_selected_entry() -> None:
    profile = _mixed_profile()
    result = _strategy_result(
        [
            _selection(
                "mech",
                ["mech-control", "mech-interfaces", "mech-safety"],
                EvidencePriorityTier.OPTIONAL,
            ),
            _selection(
                "rd",
                ["rd-wiring", "rd-test", "rd-power"],
                EvidencePriorityTier.HIGH,
            ),
            _selection(
                "hand",
                ["hand-build", "hand-control"],
                EvidencePriorityTier.HIGH,
            ),
        ],
        thesis="Preserve every strategist-selected application-story entry before extra depth.",
    )
    fake = FakeResumeLanguageModel(recommend_application_strategy=result)
    service = _service(fake, maximum_bullets=5)

    plan = service.create_plan(profile, _hardware_posting(), TemplateConstraints())
    resume = service.build_document(plan, profile, set())

    assert _selected_entry_ids(resume) == {"mech", "rd", "hand"}
    assert len(resume.experience_bullets["mech"]) == 2
    assert len(resume.experience_bullets["rd"]) == 2
    assert len(resume.project_bullets["hand"]) == 1


def test_dominated_new_entry_reserve_gets_one_bounded_strategy_repair() -> None:
    profile = _deep_hardware_profile()
    weak_first_pass = _strategy_result(
        [
            _selection(
                "rd",
                ["rd-wiring", "rd-test", "rd-power", "rd-validation"],
                EvidencePriorityTier.CRITICAL,
            ),
            _selection(
                "hand",
                ["hand-build", "hand-vision", "hand-control"],
                EvidencePriorityTier.HIGH,
            ),
        ],
        thesis="Use a physical-system core, then fill from a broad transferable bench.",
        expansion_reserve=[
            ProposedStrategyExpansionAction(
                entry_id="digital",
                evidence_ids=["digital-ai", "digital-docs"],
                priority=EvidencePriorityTier.HIGH,
                marginal_value_reason="Adds generic automation and documentation support.",
                minimum_coherent_depth=2,
            ),
            ProposedStrategyExpansionAction(
                entry_id="resume-tool",
                evidence_ids=["resume-rag", "resume-ui"],
                priority=EvidencePriorityTier.MEDIUM,
                marginal_value_reason="Adds a generic software workflow.",
            ),
            ProposedStrategyExpansionAction(
                entry_id="arm",
                evidence_ids=["arm-cad", "arm-test", "arm-transmission"],
                priority=EvidencePriorityTier.MEDIUM,
                marginal_value_reason="Adds a coherent actuator-design project.",
                minimum_coherent_depth=2,
            ),
        ],
    )
    repaired = _strategy_result(
        _hardware_core_entries(),
        thesis="Center direct mechatronics, hardware integration, and physical-system proof.",
        expansion_reserve=[
            ProposedStrategyExpansionAction(
                entry_id="arm",
                evidence_ids=["arm-cad", "arm-test", "arm-transmission"],
                priority=EvidencePriorityTier.MEDIUM,
                marginal_value_reason="Adds a coherent actuator-design project.",
                minimum_coherent_depth=2,
            )
        ],
        low_priority=["digital", "software", "resume-tool"],
    )
    fake = FakeResumeLanguageModel(
        recommend_application_strategy=[weak_first_pass, repaired]
    )
    service = _service(fake, page_fit=UnderfillExpansionPageFit())

    plan = service.create_plan(profile, _hardware_posting(), TemplateConstraints())
    resume = service.build_document(plan, profile, set())

    assert fake.calls["recommend_application_strategy"] == 2
    repair_request = fake.requests["recommend_application_strategy"][1]
    assert repair_request.correction_notes
    assert all("mech" in note for note in repair_request.correction_notes)
    assert any("digital" in note for note in repair_request.correction_notes)
    assert "mech" in resume.experience_bullets
    assert "digital" not in resume.experience_bullets
    assert "resume-tool" not in resume.project_bullets


def test_underfill_uses_material_core_depth_and_rejects_weak_positive_fill() -> None:
    profile = _mixed_profile()
    result = _strategy_result(
        _hardware_core_entries(),
        thesis="Center the reviewed multidisciplinary physical-system portfolio.",
        expansion_reserve=[
            ProposedStrategyExpansionAction(
                entry_id="digital",
                evidence_ids=["digital-ai", "digital-docs"],
                priority=EvidencePriorityTier.HIGH,
                marginal_value_reason="Adds generic automation and documentation support.",
                minimum_coherent_depth=2,
            ),
            ProposedStrategyExpansionAction(
                entry_id="arm",
                evidence_ids=["arm-cad", "arm-test", "arm-transmission"],
                priority=EvidencePriorityTier.MEDIUM,
                marginal_value_reason="Adds distinct actuator and mechanical validation proof.",
                minimum_coherent_depth=2,
            ),
        ],
        low_priority=["software", "resume-tool"],
    )
    fake = FakeResumeLanguageModel(recommend_application_strategy=result)
    service = _service(fake, page_fit=UnderfillExpansionPageFit())

    plan = service.create_plan(profile, _hardware_posting(), TemplateConstraints())
    resume = service.build_document(plan, profile, set())

    assert plan.application_strategy is not None
    assert any(
        action.origin is StrategyExpansionOrigin.CORE_ENTRY_DEPTH
        for action in plan.application_strategy.expansion_reserve
    )
    assert "digital" not in resume.experience_bullets
    assert "arm" in resume.project_bullets
    assert resume.composition_diagnostic is not None
    assert any(
        "material marginal portfolio-value floor" in item.reason
        for item in resume.composition_diagnostic.page_fill_iterations
    )


def test_severe_underfill_consumes_existing_same_entry_alternative() -> None:
    profile = _mixed_profile()
    result = _strategy_result(
        _hardware_core_entries(mechatronics_alternatives=["mech-feedback"]),
        thesis="Center the reviewed multidisciplinary physical-system portfolio.",
        low_priority=["digital", "software", "resume-tool", "arm"],
    )
    page_fit = OneStepAlternativePageFit()
    fake = FakeResumeLanguageModel(recommend_application_strategy=result)
    service = _service(fake, page_fit=page_fit)

    plan = service.create_plan(profile, _hardware_posting(), TemplateConstraints())
    resume = service.build_document(plan, profile, set())

    assert plan.application_strategy is not None
    assert plan.application_strategy.selected_evidence_ids == [
        "mech-control",
        "mech-interfaces",
        "mech-safety",
        "mech-cad",
        "rd-wiring",
        "rd-test",
        "rd-power",
        "rd-validation",
        "hand-build",
        "hand-vision",
        "hand-control",
    ]
    assert plan.application_strategy.reserve_evidence_ids == [
        "mech-feedback",
        "mech-repeat",
    ]
    assert plan.application_strategy.expansion_reserve[-1].origin is (
        StrategyExpansionOrigin.CORE_ENTRY_DEPTH
    )
    assert any(
        count == 11 and utilization == 0.69
        for count, _, utilization, _ in page_fit.observed
    )
    assert resume.composition_diagnostic is not None
    assert "mech-feedback" in resume.composition_diagnostic.selected_bullet_ids
    assert resume.composition_diagnostic.final_utilization_ratio == 0.86
    assert resume.composition_diagnostic.page_count == 1
    assert resume.composition_diagnostic.verification_status.value == "exact"
    assert "digital" not in resume.experience_bullets
    assert "resume-tool" not in resume.project_bullets


def test_ranked_reserve_prefers_distinct_portfolio_value_and_can_open_project() -> None:
    profile = _mixed_profile()
    reserve = [
        ProposedStrategyExpansionAction(
            entry_id="arm",
            evidence_ids=["arm-cad", "arm-test", "arm-transmission"],
            priority=EvidencePriorityTier.HIGH,
            marginal_value_reason=(
                "Adds distinct actuator, CAD, transmission, and mechanical validation proof."
            ),
            minimum_coherent_depth=2,
        )
    ]
    result = _strategy_result(
        _hardware_core_entries(
            mechatronics_alternatives=["mech-repeat", "mech-feedback"]
        ),
        thesis="Center the reviewed multidisciplinary physical-system portfolio.",
        expansion_reserve=reserve,
        low_priority=["digital", "software", "resume-tool"],
    )
    page_fit = UnderfillExpansionPageFit()
    fake = FakeResumeLanguageModel(recommend_application_strategy=result)
    service = _service(fake, page_fit=page_fit)

    plan = service.create_plan(profile, _hardware_posting(), TemplateConstraints())
    resume = service.build_document(plan, profile, set())

    assert plan.application_strategy is not None
    assert plan.application_strategy.expansion_reserve[-1].requires_entry_heading is True
    assert plan.application_strategy.expansion_reserve[-1].minimum_coherent_depth == 2
    assert resume.composition_diagnostic is not None
    assert resume.composition_diagnostic.final_utilization_ratio == pytest.approx(0.89)
    assert resume.composition_diagnostic.bullet_counts == {
        "mech": 5,
        "rd": 4,
        "hand": 3,
        "arm": 3,
    }
    assert "arm" in resume.project_bullets
    assert len(resume.project_bullets["arm"]) == 3
    assert "mech-feedback" in resume.composition_diagnostic.selected_bullet_ids
    assert "mech-repeat" not in resume.composition_diagnostic.selected_bullet_ids
    assert "digital" not in resume.experience_bullets
    assert "software" not in resume.experience_bullets
    assert "resume-tool" not in resume.project_bullets


def test_live_69_percent_core_tries_exact_fitting_sibling_after_first_reserve_overflows() -> None:
    profile = _mixed_profile()
    core = [
        _selection(
            "mech",
            ["mech-control", "mech-interfaces"],
            EvidencePriorityTier.CRITICAL,
        ),
        _selection(
            "rd",
            ["rd-wiring", "rd-test", "rd-power", "rd-validation"],
            EvidencePriorityTier.HIGH,
        ),
        _selection(
            "hand",
            ["hand-build", "hand-control"],
            EvidencePriorityTier.MEDIUM,
        ),
    ]
    reserve = [
        ProposedStrategyExpansionAction(
            entry_id="mech",
            evidence_ids=["mech-feedback"],
            priority=EvidencePriorityTier.HIGH,
            marginal_value_reason="Adds distinct actuator feedback validation.",
        ),
        ProposedStrategyExpansionAction(
            entry_id="mech",
            evidence_ids=["mech-cad"],
            priority=EvidencePriorityTier.MEDIUM,
            marginal_value_reason="Adds distinct fixture design evidence.",
        ),
        ProposedStrategyExpansionAction(
            entry_id="arm",
            evidence_ids=["arm-cad", "arm-test", "arm-transmission"],
            priority=EvidencePriorityTier.MEDIUM,
            marginal_value_reason="Adds a coherent actuator and mechanical-design project.",
            minimum_coherent_depth=2,
        ),
    ]
    page_fit = LiveUnderfillReservePageFit()
    fake = FakeResumeLanguageModel(
        recommend_application_strategy=_strategy_result(
            core,
            thesis="Center the reviewed multidisciplinary physical-system portfolio.",
            expansion_reserve=reserve,
            low_priority=["digital", "software", "resume-tool"],
        )
    )
    service = _service(fake, page_fit=page_fit)

    plan = service.create_plan(profile, _hardware_posting(), TemplateConstraints())
    resume = service.build_document(plan, profile, set())

    assert resume.composition_diagnostic is not None
    diagnostic = resume.composition_diagnostic
    prompt = task_prompt(
        LlmOperation.APPLICATION_STRATEGY,
        fake.requests["recommend_application_strategy"][0],
    )
    assert "Reserve count is not a quality target" in prompt
    assert "Never shrink the core" in prompt
    assert STRATEGY_UTILIZATION_PREFERRED_FLOOR == 0.88
    assert STRATEGY_UTILIZATION_PREFERRED_CEILING == 0.93
    assert STRATEGY_UTILIZATION_ACCEPTABLE_FLOOR == 0.84
    assert TEMPLATE_V1_SEVERE_UNDERFILL_FLOOR == 0.75
    assert diagnostic.final_utilization_ratio == 0.89
    assert diagnostic.page_count == 1
    assert diagnostic.verification_status.value == "exact"
    assert "mech-feedback" not in diagnostic.selected_bullet_ids
    assert {"arm-cad", "arm-test", "arm-transmission"} <= set(
        diagnostic.selected_bullet_ids
    )
    assert "digital" not in resume.experience_bullets
    assert "software" not in resume.experience_bullets
    assert "resume-tool" not in resume.project_bullets
    assert any(
        exact and page_count == 2 and "mech-feedback" in evidence_ids
        for evidence_ids, exact, _utilization, page_count in page_fit.evaluations
    )
    assert any(
        exact
        and page_count == 1
        and "mech-cad" in evidence_ids
        for evidence_ids, exact, _utilization, page_count in page_fit.evaluations
    )
    assert any(
        exact
        and page_count == 1
        and {"arm-cad", "arm-test", "arm-transmission"}.issubset(evidence_ids)
        for evidence_ids, exact, _utilization, page_count in page_fit.evaluations
    )
    assert fake.calls["recommend_application_strategy"] == 1
    assert fake.calls["rewrite_bullets"] == 0
    assert diagnostic.estimated_page_evaluations < diagnostic.maximum_estimated_page_evaluations
    assert diagnostic.exact_page_evaluations <= diagnostic.maximum_exact_finalist_evaluations
    assert any(
        item.candidate_id.startswith("strategy-exact:")
        and ":reserve-1" in item.candidate_id
        and item.overflow
        and "overflowed" in item.reason
        for item in diagnostic.page_fill_iterations
    )
    assert any(
        item.candidate_id.startswith("strategy-exact:")
        and ":reserve-3" in item.candidate_id
        and item.accepted
        for item in diagnostic.page_fill_iterations
    )


def test_deep_hardware_strategy_exposes_bounded_reserve_and_fills_existing_page_frontier() -> None:
    profile = _deep_hardware_profile()
    core = [
        _selection(
            "mech",
            ["mech-control", "mech-interfaces"],
            EvidencePriorityTier.CRITICAL,
        ),
        _selection(
            "rd",
            ["rd-wiring", "rd-test", "rd-power", "rd-validation"],
            EvidencePriorityTier.HIGH,
        ),
        _selection(
            "hand",
            ["hand-build", "hand-control"],
            EvidencePriorityTier.HIGH,
        ),
    ]
    reserve = [
        ProposedStrategyExpansionAction(
            entry_id="mech",
            evidence_ids=["mech-safety"],
            priority=EvidencePriorityTier.HIGH,
            marginal_value_reason="Adds distinct physical safety validation.",
        ),
        ProposedStrategyExpansionAction(
            entry_id="mech",
            evidence_ids=["mech-cad"],
            priority=EvidencePriorityTier.HIGH,
            marginal_value_reason="Adds distinct fixture-design evidence.",
        ),
        ProposedStrategyExpansionAction(
            entry_id="mech",
            evidence_ids=["mech-feedback"],
            priority=EvidencePriorityTier.HIGH,
            marginal_value_reason="Adds distinct feedback and current-limit validation.",
        ),
        ProposedStrategyExpansionAction(
            entry_id="mech",
            evidence_ids=["mech-power"],
            priority=EvidencePriorityTier.HIGH,
            marginal_value_reason="Adds distinct protected power evidence.",
        ),
        ProposedStrategyExpansionAction(
            entry_id="hand",
            evidence_ids=["hand-vision"],
            priority=EvidencePriorityTier.MEDIUM,
            marginal_value_reason="Adds a supported system-input dimension.",
        ),
        ProposedStrategyExpansionAction(
            entry_id="hand",
            evidence_ids=["hand-sensing"],
            priority=EvidencePriorityTier.MEDIUM,
            marginal_value_reason="Adds distinct sensing and signal-conditioning evidence.",
        ),
        ProposedStrategyExpansionAction(
            entry_id="arm",
            evidence_ids=["arm-cad", "arm-test"],
            priority=EvidencePriorityTier.MEDIUM,
            marginal_value_reason="Adds a coherent actuator-design and bench-test project.",
            minimum_coherent_depth=2,
        ),
        ProposedStrategyExpansionAction(
            entry_id="arm",
            evidence_ids=["arm-transmission"],
            priority=EvidencePriorityTier.MEDIUM,
            marginal_value_reason="Adds distinct mechanical-transmission evidence.",
        ),
    ]
    page_fit = DeepReserveCoveragePageFit()
    fake = FakeResumeLanguageModel(
        recommend_application_strategy=_strategy_result(
            core,
            thesis="Center the reviewed multidisciplinary physical-system portfolio.",
            expansion_reserve=reserve,
            low_priority=["digital", "software", "resume-tool"],
        )
    )
    service = _service(fake, page_fit=page_fit)

    plan = service.create_plan(profile, _hardware_posting(), TemplateConstraints())
    resume = service.build_document(plan, profile, set())

    assert plan.application_strategy is not None
    assert plan.application_strategy.contract_version == APPLICATION_STRATEGY_CONTRACT_VERSION
    assert len(plan.application_strategy.expansion_reserve) == 10
    assert sum(
        action.origin is StrategyExpansionOrigin.CORE_ENTRY_DEPTH
        for action in plan.application_strategy.expansion_reserve
    ) == 2
    request = fake.requests["recommend_application_strategy"][0]
    assert request.constraints.maximum_expansion_reserve_actions == (
        APPLICATION_STRATEGY_RESERVE_MAXIMUM_ACTIONS
    )
    assert resume.composition_diagnostic is not None
    diagnostic = resume.composition_diagnostic
    assert 0.88 <= diagnostic.final_utilization_ratio <= 0.93
    assert diagnostic.page_count == 1
    assert diagnostic.verification_status.value == "exact"
    assert "mech-repeat" not in diagnostic.selected_bullet_ids
    assert "digital" not in resume.experience_bullets
    assert "software" not in resume.experience_bullets
    assert "resume-tool" not in resume.project_bullets
    assert fake.calls["recommend_application_strategy"] == 1
    assert fake.calls["rewrite_bullets"] == 0
    assert max(item[2] for item in page_fit.observed) >= 0.88


def test_new_professional_reserve_entry_requires_coherent_depth() -> None:
    profile = _mixed_profile()
    result = _strategy_result(
        _hardware_core_entries(),
        thesis="Center the reviewed multidisciplinary physical-system portfolio.",
        expansion_reserve=[
            ProposedStrategyExpansionAction(
                entry_id="digital",
                evidence_ids=["digital-ai"],
                priority=EvidencePriorityTier.OPTIONAL,
                marginal_value_reason="One isolated supporting item.",
                minimum_coherent_depth=1,
            )
        ],
    )
    fake = FakeResumeLanguageModel(recommend_application_strategy=result)
    service = _service(fake)

    plan = service.create_plan(profile, _hardware_posting(), TemplateConstraints())

    assert plan.application_strategy is not None
    assert all(
        action.entry_id != "digital"
        for action in plan.application_strategy.expansion_reserve
    )
    assert StrategyValidationIssueCode.STRUCTURAL_LIMIT in {
        item.code for item in plan.application_strategy.validation_issues
    }


def test_exact_two_page_expansion_is_rejected_for_verified_core() -> None:
    profile = _mixed_profile()
    result = _strategy_result(
        _hardware_core_entries(mechatronics_alternatives=["mech-feedback"]),
        thesis="Center the reviewed multidisciplinary physical-system portfolio.",
    )
    page_fit = OneStepAlternativePageFit()

    def exact_batch(resumes: list[object]) -> list[PageFitEvaluation]:
        evaluations: list[PageFitEvaluation] = []
        for resume in resumes:
            count = page_fit._bullet_count(resume)
            evaluations.append(
                PageFitEvaluation(
                    status=(
                        PageUtilizationStatus.OVERFLOW
                        if count > 11
                        else PageUtilizationStatus.SEVERE_UNDERFILL
                    ),
                    page_count=2 if count > 11 else 1,
                    exact=True,
                    provider="controlled exact paginator",
                    utilization_ratio=0.84 if count > 11 else 0.67,
                    fits_one_page=count <= 11,
                )
            )
        return evaluations

    page_fit.evaluate_batch = exact_batch  # type: ignore[method-assign]
    fake = FakeResumeLanguageModel(recommend_application_strategy=result)
    service = _service(fake, page_fit=page_fit)

    plan = service.create_plan(profile, _hardware_posting(), TemplateConstraints())
    resume = service.build_document(plan, profile, set())

    assert resume.composition_diagnostic is not None
    assert "mech-feedback" not in resume.composition_diagnostic.selected_bullet_ids
    assert resume.composition_diagnostic.page_count == 1
    assert resume.composition_diagnostic.verification_status.value == "exact"
    assert resume.composition_diagnostic.additional_evidence_unavailable is True
    assert "every validated reserve action was consumed or rejected" in (
        resume.composition_diagnostic.reason
    )
    assert any(
        item.candidate_id.startswith("strategy-exact:")
        and ":reserve-1" in item.candidate_id
        and item.overflow
        and "overflowed" in item.reason
        for item in resume.composition_diagnostic.page_fill_iterations
    )


def test_underfilled_software_strategy_expands_only_with_software_reserve() -> None:
    profile = _mixed_profile()
    software_entries = [
        _selection("digital", ["digital-ai", "digital-docs"], EvidencePriorityTier.CRITICAL),
        _selection("software", ["software-api", "software-tests"], EvidencePriorityTier.HIGH),
        _selection("resume-tool", ["resume-rag", "resume-ui"], EvidencePriorityTier.HIGH),
    ]
    result = _strategy_result(
        software_entries,
        thesis="Center the reviewed software delivery and AI evaluation portfolio.",
        expansion_reserve=[
            ProposedStrategyExpansionAction(
                entry_id="software",
                evidence_ids=["software-observability"],
                priority=EvidencePriorityTier.HIGH,
                marginal_value_reason="Adds distinct production telemetry and diagnostics proof.",
                minimum_coherent_depth=1,
            )
        ],
        low_priority=["mech", "rd", "hand", "arm"],
    )
    page_fit = OneStepAlternativePageFit(core_bullets=6)
    fake = FakeResumeLanguageModel(recommend_application_strategy=result)
    service = _service(fake, page_fit=page_fit)

    plan = service.create_plan(profile, _software_posting(), TemplateConstraints())
    resume = service.build_document(plan, profile, set())

    request = fake.requests["recommend_application_strategy"][0]
    assert request.constraints.maximum_expansion_reserve_actions == 8
    assert _selected_entry_ids(resume) == {"digital", "software", "resume-tool"}
    assert resume.composition_diagnostic is not None
    assert "software-observability" in resume.composition_diagnostic.selected_bullet_ids
    assert resume.composition_diagnostic.final_utilization_ratio == 0.86


def test_writer_receives_only_strategy_evidence_and_total_calls_are_bounded() -> None:
    profile = _mixed_profile()
    result = _strategy_result(
        [_selection("mech", ["mech-control", "mech-interfaces"], EvidencePriorityTier.CRITICAL)],
        thesis="Center the reviewed embedded and interface work.",
    )
    writer = BulletRewriteResult(
        metadata=metadata(LlmOperation.REWRITE_BULLETS),
        output=BulletRewriteOutput(),
    )
    fake = FakeResumeLanguageModel(
        recommend_application_strategy=result,
        rewrite_bullets=writer,
    )
    service = _service(fake, writing=True)

    plan = service.create_plan(profile, _hardware_posting(), TemplateConstraints())
    resume = service.build_document(plan, profile, set())

    request = fake.requests["rewrite_bullets"][0]
    assert {item.evidence_ids[0] for item in request.groups} == {
        "mech-control",
        "mech-interfaces",
    }
    assert fake.calls["recommend_application_strategy"] == 1
    assert fake.calls["rewrite_bullets"] == 1
    assert resume.hybrid_diagnostic is not None
    assert resume.hybrid_diagnostic.provider_call_count == 2


def test_strategist_and_writer_share_one_malformed_repair_budget() -> None:
    profile = _mixed_profile()
    strategy = _strategy_result(
        [_selection("mech", ["mech-control", "mech-interfaces"], EvidencePriorityTier.CRITICAL)],
        thesis="Center the reviewed embedded and interface work.",
    )
    malformed = LanguageModelError(
        LanguageModelErrorKind.MALFORMED_RESPONSE,
        "controlled malformed typed response",
    )
    fake = FakeResumeLanguageModel(
        recommend_application_strategy=[malformed, strategy],
        rewrite_bullets=[
            malformed,
            BulletRewriteResult(
                metadata=metadata(LlmOperation.REWRITE_BULLETS),
                output=BulletRewriteOutput(),
            ),
        ],
    )
    service = TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
        hybrid_services=HybridLlmServices(
            fake,
            1,
            2,
            False,
            False,
            True,
            enable_application_strategy=True,
        ),
        resume_composer=DeterministicResumeComposer(ControlledPageFit()),
    )

    plan = service.create_plan(profile, _hardware_posting(), TemplateConstraints())
    resume = service.build_document(plan, profile, set())

    assert plan.application_strategy is not None
    assert fake.calls["recommend_application_strategy"] == 2
    assert fake.calls["rewrite_bullets"] == 1
    assert resume.hybrid_diagnostic is not None
    assert resume.hybrid_diagnostic.provider_call_count == 3
    assert resume.hybrid_diagnostic.deterministic_fallback_used is True


def test_provider_unavailable_retains_existing_deterministic_fallback() -> None:
    profile = _mixed_profile()
    service = _service(None)

    plan = service.create_plan(profile, _hardware_posting(), TemplateConstraints())
    resume = service.build_document(plan, profile, set())

    assert plan.application_strategy is None
    assert resume.application_strategy is None
    assert resume.experience_bullets or resume.project_bullets
    assert resume.hybrid_diagnostic is not None
    assert "Deterministic fallback" in resume.hybrid_diagnostic.planning_reason


def test_strategy_page_fit_fails_closed_without_exact_pagination() -> None:
    profile = _mixed_profile()
    result = _strategy_result(
        [
            _selection(
                "mech",
                ["mech-control", "mech-interfaces"],
                EvidencePriorityTier.CRITICAL,
            )
        ],
        thesis="Center the reviewed embedded and interface work.",
    )
    fake = FakeResumeLanguageModel(recommend_application_strategy=result)
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
            enable_application_strategy=True,
        ),
        resume_composer=DeterministicResumeComposer(UnverifiedPageFit()),
    )
    plan = service.create_plan(profile, _hardware_posting(), TemplateConstraints())

    with pytest.raises(ExactPaginationRequiredError, match="Exact one-page pagination"):
        service.build_document(plan, profile, set())
