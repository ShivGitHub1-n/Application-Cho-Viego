from __future__ import annotations

import pytest

from resume_tailor.application.company_research import BoundedCompanyResearchService
from resume_tailor.application.cover_letter import CoverLetterService
from resume_tailor.application.cover_letter_evidence import CoverLetterEvidencePortfolio
from resume_tailor.application.cover_letter_validation import (
    CoverLetterValidator,
    DeterministicCoverLetterComposer,
)
from resume_tailor.domain.application_strategy import (
    ApplicationStrategyPlan,
    EvidencePriorityTier,
    StrategyEntryPlan,
    StrategyEvidenceChoice,
)
from resume_tailor.domain.cover_letter import CoverLetterQualityGateStatus
from resume_tailor.domain.models import (
    EntityKind,
    EvidenceItem,
    JobPosting,
    MasterProfile,
    ResumeItem,
    TemplateConstraints,
)
from resume_tailor.frontend import cover_letter_view
from resume_tailor.infrastructure.optimization import DeterministicResumeOptimizer
from tests.cover_letter_helpers import ControlledCoverLetterRenderer


def _profile() -> MasterProfile:
    entries = [
        ResumeItem(id="controls", title="Controls Engineer", kind=EntityKind.EXPERIENCE),
        ResumeItem(id="integration", title="Integration Engineer", kind=EntityKind.EXPERIENCE),
        ResumeItem(id="actuator", title="Actuator Hand", kind=EntityKind.PROJECT),
        ResumeItem(id="digital", title="Digital Engineering Intern", kind=EntityKind.EXPERIENCE),
        ResumeItem(id="software", title="Software Evaluation Project", kind=EntityKind.PROJECT),
    ]
    evidence = [
        EvidenceItem(
            id="control-firmware",
            entity_id="controls",
            source_text=(
                "Contributed embedded C++ firmware in STM32CubeIDE for STM32F4 sensor I/O, "
                "serial communication, GPIO, and prototype control outputs."
            ),
            technologies=["C++", "STM32CubeIDE", "STM32F4", "GPIO"],
        ),
        EvidenceItem(
            id="control-safety",
            entity_id="controls",
            source_text=(
                "Implemented STM32 safety supervision with manual override, fault-state "
                "outputs, and actuator command interlocks."
            ),
            technologies=["STM32", "manual override", "actuator interlocks"],
        ),
        EvidenceItem(
            id="control-schematics",
            entity_id="controls",
            source_text=(
                "Contributed electrical and embedded control schematics for steering, "
                "braking, signal routing, power distribution, and feedback sensing."
            ),
            technologies=["control schematics", "power distribution", "feedback sensing"],
        ),
        EvidenceItem(
            id="control-validation",
            entity_id="controls",
            source_text=(
                "Tested actuator commands, feedback signals, manual overrides, and fault "
                "behavior on the assembled electromechanical prototype."
            ),
            technologies=["actuator feedback", "fault testing"],
        ),
        EvidenceItem(
            id="integration-cad",
            entity_id="integration",
            source_text=(
                "Designed SolidWorks mounts and enclosures for sensors, controllers, and "
                "supporting electronics using caliper measurements, GD&T, and DFM/DFA."
            ),
            technologies=["SolidWorks", "GD&T", "DFM/DFA"],
        ),
        EvidenceItem(
            id="integration-fabrication",
            entity_id="integration",
            source_text=(
                "Fabricated and fit-checked Onyx 3D-printed brackets and laser-cut acrylic "
                "panels for the physical prototype."
            ),
            technologies=["Onyx 3D printing", "laser-cut acrylic"],
        ),
        EvidenceItem(
            id="integration-wiring",
            entity_id="integration",
            source_text=(
                "Built vehicle wiring harnesses with fused power distribution, relays, "
                "MOSFET switching, labelled connectors, and documented pin assignments."
            ),
            technologies=["wiring harnesses", "relays", "MOSFET switching"],
        ),
        EvidenceItem(
            id="integration-debug",
            entity_id="integration",
            source_text=(
                "Integrated CAN, UART, USB, and GPIO interfaces between an embedded computer, "
                "STM32F4 controller, motor drivers, and peripheral electronics."
            ),
            technologies=["CAN", "UART", "USB", "GPIO", "STM32F4"],
        ),
        EvidenceItem(
            id="actuator-firmware",
            entity_id="actuator",
            source_text=(
                "Developed Arduino firmware for three independent servos at 50 Hz with "
                "calibration, motion smoothing, and configurable travel limits."
            ),
            technologies=["Arduino firmware", "servos"],
            outcomes=["50 Hz"],
        ),
        EvidenceItem(
            id="actuator-feedback",
            entity_id="actuator",
            source_text=(
                "Integrated flex-sensor feedback with PWM actuator commands and verified "
                "repeatable finger motion across bench tests."
            ),
            technologies=["flex sensors", "PWM", "actuator commands"],
        ),
        EvidenceItem(
            id="actuator-mechanical",
            entity_id="actuator",
            source_text=(
                "Designed and assembled 3D-printed linkages, servo mounts, and cable routing "
                "for repeatable electromechanical actuation."
            ),
            technologies=["3D-printed linkages", "servo mounts"],
        ),
        EvidenceItem(
            id="actuator-test",
            entity_id="actuator",
            source_text=(
                "Diagnosed mechanical binding, adjusted travel limits, and retested the "
                "assembled hand until each actuator moved reliably."
            ),
            technologies=["travel limits", "actuator testing"],
        ),
        EvidenceItem(
            id="digital-security",
            entity_id="digital",
            source_text=(
                "Built a Python adversarial AI evaluation pipeline across seven security "
                "categories with checkpointed findings and retrieved context."
            ),
            technologies=["Python", "AI evaluation"],
        ),
        EvidenceItem(
            id="digital-reporting",
            entity_id="digital",
            source_text=(
                "Created Power BI dashboards and Jupyter analyses for evaluation reporting."
            ),
            technologies=["Power BI", "Jupyter"],
        ),
        EvidenceItem(
            id="software-retrieval",
            entity_id="software",
            source_text=(
                "Developed a typed Python retrieval service with automated tests and model "
                "quality diagnostics."
            ),
            technologies=["Python", "retrieval", "automated tests"],
        ),
        EvidenceItem(
            id="software-observability",
            entity_id="software",
            source_text=(
                "Deployed containerized inference services with structured logging and "
                "latency monitoring."
            ),
            technologies=["containers", "inference services", "structured logging"],
        ),
    ]
    return MasterProfile(
        id="fallback-regression-profile",
        user_id="synthetic-user",
        display_name="Taylor Candidate",
        contact={"email": "taylor@example.com"},
        experiences=[entry for entry in entries if entry.kind is EntityKind.EXPERIENCE],
        projects=[entry for entry in entries if entry.kind is EntityKind.PROJECT],
        evidence=evidence,
    )


def _hardware_posting() -> JobPosting:
    return JobPosting(
        id="hardware-fallback-posting",
        title="Mechatronics Engineer Intern - Hardware",
        company_name="Example Motion Labs",
        description=(
            "Build, assemble, test, debug, and validate electromechanical prototypes. "
            "Develop embedded C/C++ test code for microcontrollers, motors, and feedback. "
            "Create CAD fixtures and 3D-printed parts, route wiring, inspect interfaces, "
            "and troubleshoot mechanical and electrical hardware on the bench."
        ),
    )


def _strategy_plan(profile: MasterProfile, posting: JobPosting, entries: list[str]):
    plan = DeterministicResumeOptimizer().create_plan(
        profile,
        posting,
        TemplateConstraints(),
    )
    evidence_by_entry = {
        entry_id: next(item.id for item in profile.evidence if item.entity_id == entry_id)
        for entry_id in entries
    }
    strategy = ApplicationStrategyPlan(
        application_thesis="Build and validate integrated systems through concrete evidence.",
        selected_entries=[
            StrategyEntryPlan(
                entry_id=entry_id,
                reason="This entry is a validated core application story.",
                desired_depth=4,
                evidence=[
                    StrategyEvidenceChoice(
                        evidence_id=evidence_by_entry[entry_id],
                        priority=EvidencePriorityTier.HIGH,
                    )
                ],
            )
            for entry_id in entries
        ],
        global_evidence_priority=list(evidence_by_entry.values()),
    )
    return plan.model_copy(update={"application_strategy": strategy})


def test_hardware_fallback_stays_inside_strategy_entries_and_uses_concrete_depth() -> None:
    profile = _profile()
    posting = _hardware_posting()
    plan = _strategy_plan(profile, posting, ["controls", "integration", "actuator"])

    evidence, diagnostic = CoverLetterEvidencePortfolio().select(profile, posting, plan)
    research = BoundedCompanyResearchService().research(
        CoverLetterService.default_research_request(posting)
    )
    output = DeterministicCoverLetterComposer().source_bound_fallback(
        evidence,
        research,
        posting,
    )
    validated = CoverLetterValidator().validate_output(
        output,
        evidence,
        research,
        posting,
    )
    text = " ".join(paragraph.text for paragraph in output.paragraphs).casefold()

    assert {item.entity_id for item in evidence} == {"controls", "integration", "actuator"}
    assert len(evidence) >= 10
    assert diagnostic.narrative_thread_count == 3
    assert "digital engineering intern" not in text
    assert "adversarial ai" not in text
    assert "i worked directly with the hardware" not in text
    assert "same technical problem" not in text
    assert "a separate constraint joined" not in text
    assert not validated.rejected_claims
    assert not [
        gate
        for gate in validated.quality_gates
        if gate.status is CoverLetterQualityGateStatus.FAILED
    ]


def test_hardware_fallback_without_resume_generation_does_not_open_digital_for_variety() -> None:
    profile = _profile()
    posting = _hardware_posting()

    evidence, _ = CoverLetterEvidencePortfolio().select(profile, posting, plan=None)

    assert "digital" not in {item.entity_id for item in evidence}
    assert "software" not in {item.entity_id for item in evidence}


def test_developed_fallback_reaches_page_fit_with_full_supplied_title() -> None:
    profile = _profile()
    posting = _hardware_posting()
    plan = _strategy_plan(profile, posting, ["controls", "integration", "actuator"])
    service = CoverLetterService(
        renderer=ControlledCoverLetterRenderer([0.62, 0.70, 0.86], exact=True)
    )

    artifact = service.generate_artifact(profile, posting, plan)

    assert artifact.ready_for_review
    assert artifact.letter.job_title == "Mechatronics Engineer Intern - Hardware"
    assert artifact.page_fit.exact_pagination
    assert artifact.page_fit.estimated_utilization == 0.86
    assert artifact.call_counts.provider_calls == 0
    assert set(artifact.page_fit.evidence_added_during_page_fit) == {
        item.id for item in artifact.evidence_records
    } - set(artifact.page_fit.candidates[0].evidence_ids)


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("I worked directly with the hardware.", "vague_direct_technical_referent"),
        (
            "The work brought STM32 interfaces and communication architecture into the "
            "same technical problem.",
            "synthetic_bridge_prose",
        ),
        (
            "A separate constraint joined SolidWorks mounts and GPIO in the same "
            "implementation.",
            "synthetic_bridge_prose",
        ),
        (
            "I worked directly with hands-on engineering work in my Digital Engineering "
            "Intern work.",
            "duplicated_work_frame",
        ),
    ],
)
def test_live_malformed_fallback_shapes_are_rejected(text: str, code: str) -> None:
    profile = _profile()
    posting = _hardware_posting()
    plan = _strategy_plan(profile, posting, ["controls", "integration", "actuator"])
    evidence, _ = CoverLetterEvidencePortfolio().select(profile, posting, plan)
    research = BoundedCompanyResearchService().research(
        CoverLetterService.default_research_request(posting)
    )
    output = DeterministicCoverLetterComposer().source_bound_fallback(
        evidence,
        research,
        posting,
    )
    paragraphs = list(output.paragraphs)
    paragraphs[1] = paragraphs[1].model_copy(
        update={"text": text, "source_bound_sentences": []}
    )

    validated = CoverLetterValidator().validate_output(
        output.model_copy(update={"paragraphs": paragraphs}),
        evidence,
        research,
        posting,
    )

    assert any(code in claim.codes for claim in validated.rejected_claims)


def test_software_strategy_boundary_is_symmetric() -> None:
    profile = _profile()
    posting = JobPosting(
        id="software-fallback-posting",
        title="AI Infrastructure Engineer",
        company_name="Example Compute Labs",
        description=(
            "Build Python retrieval and inference services with typed APIs, model evaluation, "
            "container deployment, structured logging, and latency monitoring."
        ),
    )
    plan = _strategy_plan(profile, posting, ["digital", "software"])

    evidence, _ = CoverLetterEvidencePortfolio().select(profile, posting, plan)

    assert {item.entity_id for item in evidence} == {"digital", "software"}
    assert not ({"controls", "integration", "actuator"} & {item.entity_id for item in evidence})


def test_failed_diagnostic_download_message_does_not_promise_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = _profile()
    posting = _hardware_posting()
    plan = _strategy_plan(profile, posting, ["controls", "integration", "actuator"])
    artifact = CoverLetterService(
        renderer=ControlledCoverLetterRenderer([0.70, 0.70, 0.70], exact=True)
    ).generate_artifact(profile, posting, plan)
    captions: list[str] = []

    class _Streamlit:
        @staticmethod
        def caption(value: str) -> None:
            captions.append(value)

    class _Service:
        @staticmethod
        def prepare_cover_letter_download(*_args, **_kwargs):
            raise AssertionError("A failed diagnostic must not prepare a download")

    monkeypatch.setattr(cover_letter_view, "st", _Streamlit())

    cover_letter_view._render_download(_Service(), artifact, True)

    assert captions == ["No download is available for this diagnostic candidate."]
