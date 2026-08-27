"""Temporary, explicitly gated demo fixtures.

TEMPORARY DEMO OVERRIDE — remove after demo recording.

This module is intentionally narrow: it activates only when ``VIEGO_DEMO_MODE``
is truthy.  While enabled, the active posting is used only for its visible
role/company context; the canonical profile remains the only factual source
and this module selects known reviewed atoms for the recording path.
"""

from __future__ import annotations

import math
import os
import re

from resume_tailor.application.generated_artifact import content_fingerprint
from resume_tailor.domain.application_strategy import (
    ApplicationStrategyPlan,
    EvidencePriorityTier,
    StrategyEntryPlan,
    StrategyEvidenceChoice,
)
from resume_tailor.domain.company_research import CompanyFactConfidence, CompanyResearchBundle
from resume_tailor.domain.cover_letter import (
    CoverLetter,
    CoverLetterCanonicalMetadata,
    CoverLetterEvidenceKind,
    CoverLetterEvidenceRecord,
    CoverLetterEvidenceSelectionDiagnostic,
    CoverLetterLayoutProfile,
    CoverLetterLengthClass,
    CoverLetterParagraph,
    CoverLetterParagraphPurpose,
    CoverLetterRecipient,
    CoverLetterSentenceAuthority,
    CoverLetterValidationStatus,
)
from resume_tailor.domain.llm_models import CoverLetterDraftOutput, CoverLetterDraftParagraph
from resume_tailor.domain.models import (
    ClaimCandidate,
    ClaimSupport,
    EntityKind,
    EvidenceItem,
    JobPosting,
    MasterProfile,
    ResumeItem,
    StructuredBullet,
    StructuredResume,
    TailoringPlan,
    TechnicalSkillCategory,
    TemplateConstraints,
)
from resume_tailor.domain.resume_metadata import validate_structured_resume_metadata

DEMO_COMPANY = "Anduril Industries"
DEMO_ROLE = "2027 Electrical Engineer Intern"

_DEMO_RESUME_SPECS: tuple[tuple[str, str, str], ...] = (
    (
        "telebotics-mechatronics-engineer",
        "Led the architecture of a retrofittable Club Car drive-by-wire system",
        "Led the architecture of a retrofittable Club Car drive-by-wire system, defining "
        "MCOR throttle interception, EPS steering control, linear-actuator primary braking, "
        "hydraulic emergency braking, and Jetson–STM32 control interfaces.",
    ),
    (
        "telebotics-mechatronics-engineer",
        "MCOR's 0–4.65 V command and battery-voltage foot signal",
        "Designed a throttle-control interface around the Club Car MCOR’s 0–4.65 V command "
        "and battery-voltage foot signal using relay-based manual fallback, STM32 DAC output, "
        "op-amp scaling, MOSFET control, and watchdog supervision.",
    ),
    (
        "telebotics-mechatronics-engineer",
        "dual-path braking architecture using a linear actuator and pulley linkage",
        "Designed a dual-path braking architecture using a linear actuator and pulley linkage "
        "for primary braking plus an independent electric-over-hydraulic disc-brake concept "
        "with pressure feedback for emergency stopping.",
    ),
    (
        "telebotics-mechatronics-engineer",
        "ICDs and pin-level interface documentation defining 30+ control",
        "Authored ICDs and pin-level interface documentation for 30+ control, feedback, and "
        "safety signals across ADC, DAC, PWM, GPIO, I2C, UART, watchdog, relay, encoder, and "
        "motor-driver interfaces.",
    ),
    (
        "telebotics-mechatronics-engineer",
        "independent STM32 safety-supervision architecture",
        "Designed an independent STM32 safety-supervision architecture with command validation, "
        "heartbeat and watchdog monitoring, manual override, E-stop handling, fault detection, "
        "and controlled safe-stop behavior.",
    ),
    (
        "lassonde-rd-hardware-engineer",
        "GPIO, CAN, UART, and USB communication between NVIDIA Jetson Orin",
        "Integrated GPIO, CAN, UART, and USB communication between NVIDIA Jetson Orin, STM32F4, "
        "and peripheral electronics, enabling edge AI inference, motor control, and <150 ms "
        "emergency-stop response.",
    ),
    (
        "lassonde-rd-hardware-engineer",
        "STM32F4 peripherals in STM32CubeIDE",
        "Supported STM32F4 peripherals in STM32CubeIDE and contributed C++ integration code for "
        "sensor I/O, serial communication, GPIO, and prototype control outputs.",
    ),
    (
        "lassonde-rd-hardware-engineer",
        "sensor architecture + wiring harnesses including RTK GPS",
        "Designed and integrated sensor architecture and wiring harnesses for RTK GPS, IMU, "
        "ultrasonic, LiDAR, and camera arrays, enabling 360° environmental perception with "
        "<2 cm localization error.",
    ),
    (
        "lassonde-rd-hardware-engineer",
        "48 V electrical architecture with ignition-controlled power",
        "Designed and installed a 48 V electrical architecture with ignition-controlled power, "
        "staged DC-DC conversion, fused distribution, grounding, and protected branches to "
        "improve voltage stability, EMF noise, and camera streaming by 50%.",
    ),
    (
        "robotic-hand",
        "3-DoF tendon-driven robotic hand with custom CAD",
        "Designed and built a 3-DoF tendon-driven robotic hand with custom CAD, 3D-printed "
        "components, and MG90S servos supporting pinch, tripod, and cylindrical grasp "
        "configurations.",
    ),
    (
        "robotic-hand",
        "Arduino firmware to control 3 independent servos at 50 Hz",
        "Developed Arduino firmware to control three independent servos at 50 Hz, implementing "
        "calibration, motion smoothing, and configurable travel limits for repeatable finger "
        "actuation.",
    ),
    (
        "robotic-hand",
        "Python/OpenCV pipeline using MediaPipe's 21-point hand tracking",
        "Built a Python/OpenCV pipeline using MediaPipe’s 21-point hand tracking, translating "
        "real-time gestures into robotic motion at ~30 FPS with <200 ms response time.",
    ),
    (
        "robotic-hand",
        "115200-baud serial protocol",
        "Integrated mechanical, electrical, and software subsystems through a 115200-baud "
        "serial protocol, achieving >99.5% command reliability during continuous operation.",
    ),
    (
        "sodium-silicate",
        "conceptual design specifications for Rayonier Advanced Materials",
        "Developed three conceptual design specifications for Rayonier Advanced Materials to "
        "address excessive sodium silicate buildup in bleaching-process holding tanks.",
    ),
    (
        "sodium-silicate",
        "ultrasonic, guided-wave radar, pH, IR thermopile",
        "Evaluated and modeled ultrasonic, guided-wave radar, pH, IR thermopile, and pressure "
        "sensing concepts in SolidWorks across three proposed system designs.",
    ),
    (
        "sodium-silicate",
        "Python Measure of Success simulator",
        "Developed a Python Measure of Success simulator using temperature–solubility equations "
        "and humidity factors to generate multi-scenario precipitation curves with NumPy and "
        "Matplotlib and support design selection.",
    ),
    (
        "robotic-arm",
        "complete multi-DOF kinematic structure in SolidWorks",
        "Designed the complete multi-DOF kinematic structure in SolidWorks, including linkage "
        "configurations, housings, and mounting geometry.",
    ),
    (
        "robotic-arm",
        "custom actuator assemblies with integrated harmonic drives",
        "Modeled custom actuator assemblies with integrated harmonic drives, specifying "
        "torque-speed requirements, encoder resolution, and gear ratios for <0.1° positioning "
        "accuracy and minimal backlash.",
    ),
)

_DEMO_ENTRY_TITLES = {
    "telebotics-mechatronics-engineer": "Mechatronics Engineer",
    "lassonde-rd-hardware-engineer": "R&D Hardware Engineer",
    "robotic-hand": "Vision Controlled Robotic Hand",
    "sodium-silicate": "Preventing Sodium Silicate Crystal Build-up in Holding Tanks",
    "robotic-arm": "Long Reach Robotic Arm Manipulator",
}

_DEMO_COVER_LETTER_PARAGRAPHS: tuple[str, ...] = (
    (
        "I am applying for the 2027 Electrical Engineer Intern position because the role "
        "lines up closely with the kind of engineering work I enjoy most: building physical "
        "systems where electronics, embedded software, controls, and mechanical design all "
        "have to work together. I am currently studying Mechanical Engineering at the "
        "University of Toronto with a minor in Robotics & Mechatronics, and much of my "
        "experience has involved taking ideas from early design decisions through hands-on "
        "integration and testing."
    ),
    (
        "At the Lassonde School of Engineering at York University, I worked on the hardware "
        "integration of an autonomous teleoperation platform. I connected an NVIDIA Jetson "
        "Orin, STM32F4, and peripheral electronics over GPIO, CAN, UART, and USB, while also "
        "helping integrate sensors including LiDAR, cameras, RTK GPS, IMUs, and ultrasonic "
        "sensors. I designed and installed parts of the vehicle’s 48 V electrical architecture, "
        "including DC-DC conversion, fused distribution, grounding, and protected power "
        "branches. That experience taught me how quickly an electrical problem can become a "
        "software, mechanical, or systems problem, and how important it is to understand the "
        "whole system rather than only one component."
    ),
    (
        "I worked on similar problems at Telebotics while developing a retrofittable "
        "drive-by-wire system for a Club Car. My work covered throttle, steering, braking, "
        "Jetson-to-STM32 interfaces, and the safety logic around those systems. I created "
        "interface documentation for more than 30 control, feedback, and safety signals and "
        "designed STM32-based supervision using command validation, heartbeat monitoring, "
        "watchdogs, manual override, E-stop handling, and controlled safe-stop behavior. I "
        "especially enjoyed the process of turning system requirements into concrete electrical "
        "and control interfaces that could be built and tested."
    ),
    (
        "Outside of work, I have continued building systems that cross engineering disciplines. "
        "I designed a tendon-driven robotic hand, wrote Arduino firmware for its servo control, "
        "and built a Python/OpenCV hand-tracking pipeline that translated real-time gestures "
        "into motion. I also designed a long-reach robotic arm in SolidWorks and worked on an "
        "industrial design project that used sensor concepts, mechanical design, and Python "
        "simulation to evaluate ways of reducing sodium silicate buildup in processing "
        "equipment. These projects have given me experience moving between software, "
        "electronics, controls, and mechanical design depending on what the problem requires."
    ),
    (
        "What draws me to Anduril is the chance to work in exactly that kind of environment. "
        "The role involves building electronics into functional prototypes, working across "
        "electrical and software boundaries, developing embedded systems, and collaborating "
        "closely with mechanical, firmware, software, and test engineers. I would be excited "
        "to bring my hands-on experience with embedded systems, electrical integration, "
        "robotics, and mechanical design to that team while continuing to learn from engineers "
        "working on complex real-world systems."
    ),
    (
        "Thank you for your time and consideration. I would welcome the opportunity to discuss "
        "how my background could contribute to Anduril’s engineering team."
    ),
)

_DEMO_SKILL_GROUPS: dict[str, tuple[str, ...]] = {
    "Programming": ("Python", "C", "C++", "MATLAB"),
    "Embedded Systems": (
        "STM32",
        "Arduino",
        "NVIDIA Jetson Orin",
        "GPIO",
        "PWM",
        "ADC/DAC",
        "Serial Communication",
        "CAN",
    ),
    "Robotics & Controls": (
        "ROS 2",
        "OpenCV",
        "sensor integration",
        "Actuator-command design",
        "Command validation",
        "Watchdog supervision",
        "Safe-stop and fault handling",
    ),
    "Mechanical Design": (
        "SolidWorks",
        "Fusion360",
        "GD&T",
        "DFM/DFA",
        "Onyx 3D printing",
    ),
    "Electrical": (
        "Wiring Harness Design",
        "Crimping & Soldering",
        "Power Distribution",
        "Voltage Regulation",
        "Relays",
        "MOSFET switching",
        "H-bridges",
    ),
    "Tools": ("Git", "GitHub", "Linux"),
}


def demo_mode_enabled() -> bool:
    return os.getenv("VIEGO_DEMO_MODE", "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }


def is_demo_application(posting: JobPosting) -> bool:
    """Return whether the temporary fixture is active for the current posting.

    ``posting`` is intentionally accepted as part of the application boundary,
    but demo mode is an explicit operator opt-in rather than an identity match.
    This keeps the fixture usable when a live Streamlit posting has normalized
    or incomplete company/title fields while leaving the normal path untouched.
    """
    del posting
    return demo_mode_enabled()


def is_demo_details(company: str | None, role: str) -> bool:
    """Return whether the temporary deterministic cover-letter path is active.

    Company and role are not activation gates while the explicit flag is on;
    final fixture validation still fails closed unless the recorded Anduril
    application is the active application.
    """
    del company, role
    return demo_mode_enabled()


def build_demo_resume_plan(
    profile: MasterProfile,
    posting: JobPosting,
    constraints: TemplateConstraints,
    base_plan: TailoringPlan,
) -> TailoringPlan:
    if not is_demo_application(posting):
        return base_plan
    selected = _resolve_demo_evidence(profile)
    selected_ids = [item.id for item in selected]
    selected_entity_ids = list(dict.fromkeys(item.entity_id for item in selected))
    claims = [
        ClaimCandidate(
            id=item.id,
            entity_id=item.entity_id,
            text=item.source_text,
            evidence_ids=[item.id],
            support=ClaimSupport.DIRECT,
            estimated_lines=max(1, math.ceil(len(item.source_text) / 90)),
            required_terms=[*item.technologies, *item.outcomes],
            max_rendered_lines=constraints.max_combined_bullet_lines,
        )
        for item in selected
    ]
    entries = {item.id: item for item in [*profile.experiences, *profile.projects]}
    strategy = ApplicationStrategyPlan(
        application_thesis=(
            "Electrical and embedded systems candidate spanning physical integration, "
            "control safety, and hands-on robotic prototyping."
        ),
        selected_entries=[
            StrategyEntryPlan(
                entry_id=entry_id,
                reason="Temporary Anduril demo portfolio fixture using reviewed evidence.",
                desired_depth=len([item for item in selected if item.entity_id == entry_id]),
                evidence=[
                    StrategyEvidenceChoice(
                        evidence_id=item.id,
                        priority=EvidencePriorityTier.CRITICAL
                        if item.entity_id == selected_entity_ids[0]
                        else EvidencePriorityTier.HIGH,
                    )
                    for item in selected
                    if item.entity_id == entry_id
                ],
            )
            for entry_id in selected_entity_ids
        ],
        global_evidence_priority=selected_ids,
    )
    filtered_skills = _demo_skills(profile)
    selected_entries = [entries[item_id] for item_id in selected_entity_ids]
    selected_experiences = [item for item in selected_entries if item.kind is EntityKind.EXPERIENCE]
    selected_projects = [item for item in selected_entries if item.kind is EntityKind.PROJECT]
    return base_plan.model_copy(
        update={
            "constraints": constraints,
            "strategy": base_plan.strategy,
            "selected_entity_ids": selected_entity_ids,
            "selected_claim_ids": selected_ids,
            "claim_candidates": claims,
            "education": profile.education,
            "technical_skills": filtered_skills,
            "selected_skill_categories": [],
            "ranked_skill_categories": [],
            "skill_composition_selection": None,
            "selected_experiences": selected_experiences,
            "selected_projects": selected_projects,
            "selected_skills": [skill for category in filtered_skills for skill in category.values],
            "selected_coursework": base_plan.selected_coursework,
            "estimated_lines": sum(claim.estimated_lines for claim in claims),
            "composition_selection": None,
            "application_strategy": strategy,
            "demonstrated_skills": [],
        }
    )


def validate_demo_plan(plan: TailoringPlan, profile: MasterProfile) -> None:
    if not is_demo_application(plan.posting):
        return
    expected = _resolve_demo_evidence(profile)
    expected_ids = {item.id for item in expected}
    actual_ids = set(plan.selected_claim_ids)
    expected_entity_ids = list(dict.fromkeys(item.entity_id for item in expected))
    if (
        actual_ids != expected_ids
        or len(plan.claim_candidates) != len(expected)
        or plan.selected_entity_ids != expected_entity_ids
        or {item.id for item in [*plan.selected_experiences, *plan.selected_projects]}
        != set(expected_entity_ids)
        or plan.application_strategy is None
        or plan.application_strategy.selected_entry_ids != expected_entity_ids
    ):
        raise ValueError("The temporary demo plan does not match canonical reviewed evidence")
    evidence_by_id = {item.id: item for item in profile.evidence}
    for candidate in plan.claim_candidates:
        source = evidence_by_id.get(candidate.id)
        if source is None or not source.confirmed or candidate.evidence_ids != [candidate.id]:
            raise ValueError("The temporary demo plan contains invalid or unconfirmed evidence")
        if candidate.text != source.source_text or candidate.entity_id != source.entity_id:
            raise ValueError("The temporary demo plan changed canonical evidence")


def build_demo_structured_resume(
    profile: MasterProfile,
    posting: JobPosting,
    plan: TailoringPlan,
    baseline: StructuredResume,
) -> StructuredResume:
    """Freeze the requested demo portfolio at the final structured-document boundary."""

    if not is_demo_application(posting):
        return baseline
    resolved = _resolve_demo_evidence_with_text(profile)
    entries = {item.id: item for item in [*profile.experiences, *profile.projects]}
    ordered_entry_ids = list(dict.fromkeys(entry_id for entry_id, _, _ in resolved))
    selected_entries = [_canonical_demo_entry(entries, entry_id) for entry_id in ordered_entry_ids]
    bullets_by_entry: dict[str, list[StructuredBullet]] = {}
    for entry_id, evidence, text in resolved:
        bullets_by_entry.setdefault(entry_id, []).append(
            StructuredBullet(
                id=f"demo-final:{evidence.id}",
                text=text,
                evidence_ids=[evidence.id],
                support=ClaimSupport.DIRECT,
            )
        )
    experiences = [
        item.model_copy(deep=True)
        for item in selected_entries
        if item.kind is EntityKind.EXPERIENCE
    ]
    projects = [
        item.model_copy(deep=True)
        for item in selected_entries
        if item.kind is EntityKind.PROJECT
    ]
    experience_ids = {item.id for item in experiences}
    project_ids = {item.id for item in projects}
    skills = _demo_skills(profile)
    result = baseline.model_copy(
        deep=True,
        update={
            "posting_id": posting.id,
            "application_strategy": plan.application_strategy,
            "entity_titles": {item.id: item.title for item in selected_entries},
            "education": [item.model_copy(deep=True) for item in profile.education],
            "technical_skills": skills,
            "experiences": experiences,
            "projects": projects,
            "experience_bullets": {
                entry_id: bullets_by_entry[entry_id] for entry_id in ordered_entry_ids
                if entry_id in experience_ids
            },
            "project_bullets": {
                entry_id: bullets_by_entry[entry_id] for entry_id in ordered_entry_ids
                if entry_id in project_ids
            },
            "selected_skills": [
                skill.value
                for category in skills
                for skill in category.skills
            ],
            "review_required_claim_ids": [],
            "review_pending_bullets": [],
            "review_pending_skills": [],
            "demonstrated_skills": [],
            "composition_diagnostic": None,
            "hybrid_diagnostic": None,
        },
    )
    validate_demo_structured_resume(profile, result)
    return result


def validate_demo_structured_resume(profile: MasterProfile, resume: StructuredResume) -> None:
    """Fail closed if the final demo document drifts from canonical reviewed authority."""

    validate_structured_resume_metadata(resume)
    expected = _resolve_demo_evidence_with_text(profile)
    expected_ids = [entry_id for entry_id, _, _ in expected]
    expected_counts = {
        entry_id: expected_ids.count(entry_id) for entry_id in dict.fromkeys(expected_ids)
    }
    actual_entries = [*resume.experiences, *resume.projects]
    if [item.id for item in actual_entries] != list(dict.fromkeys(expected_ids)):
        raise ValueError("The final demo résumé portfolio does not match the fixed fixture")
    for item in actual_entries:
        expected_title = _DEMO_ENTRY_TITLES[item.id]
        if item.title != expected_title:
            raise ValueError("The final demo résumé changed canonical entry metadata")
        bullets = (
            resume.experience_bullets.get(item.id, [])
            if item.kind is EntityKind.EXPERIENCE
            else resume.project_bullets.get(item.id, [])
        )
        if len(bullets) != expected_counts[item.id]:
            raise ValueError("The final demo résumé bullet count drifted from the fixture")
    actual = [
        (item.id, bullet.evidence_ids, bullet.text)
        for item in actual_entries
        for bullet in (
            resume.experience_bullets.get(item.id, [])
            if item.kind is EntityKind.EXPERIENCE
            else resume.project_bullets.get(item.id, [])
        )
    ]
    expected_rows = [
        (entry_id, [evidence.id], text) for entry_id, evidence, text in expected
    ]
    if actual != expected_rows:
        raise ValueError("The final demo résumé wording or provenance changed")


def build_demo_cover_letter(
    profile: MasterProfile,
    posting: JobPosting,
    plan: TailoringPlan | None,
    *,
    date_text: str,
    posting_fact_ids: list[str],
    layout_profile: CoverLetterLayoutProfile,
) -> CoverLetter:
    """Build the exact user-approved deterministic letter for the recording."""

    if not is_demo_application(posting):
        raise ValueError("Demo cover letter requested outside temporary demo mode")
    evidence_by_entry: dict[str, list[str]] = {}
    for entry_id, evidence, _ in _resolve_demo_evidence_with_text(profile):
        evidence_by_entry.setdefault(entry_id, []).append(evidence.id)
    paragraph_evidence = (
        [],
        evidence_by_entry["lassonde-rd-hardware-engineer"],
        evidence_by_entry["telebotics-mechatronics-engineer"],
        [
            *evidence_by_entry["robotic-hand"],
            *evidence_by_entry["robotic-arm"],
            *evidence_by_entry["sodium-silicate"],
        ],
        [],
        [],
    )
    purposes = (
        CoverLetterParagraphPurpose.OPENING,
        CoverLetterParagraphPurpose.EXPERIENCE_CONNECTION,
        CoverLetterParagraphPurpose.CONTRIBUTION,
        CoverLetterParagraphPurpose.ROLE_FIT,
        CoverLetterParagraphPurpose.ROLE_FIT,
        CoverLetterParagraphPurpose.CLOSING,
    )
    paragraphs = [
        CoverLetterParagraph(
            id=f"demo-exact-paragraph-{index + 1}",
            purpose=purpose,
            text=text,
            candidate_evidence_ids=list(paragraph_evidence[index]),
            company_research_ids=(
                posting_fact_ids if index in {0, 4, 5} else []
            ),
            narrative_thread_id=f"demo-exact-thread-{index + 1}",
            length_class=CoverLetterLengthClass.DEVELOPED,
            claims=[],
            validation_status=CoverLetterValidationStatus.SUPPORTED,
            deterministic_fallback=False,
        )
        for index, (purpose, text) in enumerate(
            zip(purposes, _DEMO_COVER_LETTER_PARAGRAPHS, strict=True)
        )
    ]
    letter = CoverLetter(
        profile_id=profile.id,
        profile_version=profile.version,
        posting_id=posting.id,
        plan_fingerprint=(content_fingerprint(plan) if plan is not None else None),
        candidate_name=profile.display_name,
        contact=profile.contact,
        date_text=date_text,
        job_title=DEMO_ROLE,
        company_name=DEMO_COMPANY,
        recipient=CoverLetterRecipient(company=DEMO_COMPANY),
        salutation="Dear Anduril Hiring Team,",
        paragraphs=paragraphs,
        signoff="Sincerely,",
        signoff_name=profile.display_name,
        layout_profile=layout_profile,
    )
    validate_demo_cover_letter(profile, posting, letter)
    return letter


def validate_demo_cover_letter(
    profile: MasterProfile,
    posting: JobPosting,
    letter: CoverLetter,
) -> None:
    """Validate the exact approved text against canonical profile and posting authority."""

    _resolve_demo_evidence_with_text(profile)
    education_supported = any(
        item.school == "University of Toronto"
        and "Mechanical Engineering" in item.program
        and item.minor_or_specialization == "Robotics & Mechatronics"
        for item in profile.education
    )
    if not education_supported:
        raise ValueError("The demo cover letter education claim is not canonical")
    if profile.display_name != "Shiv Arora":
        raise ValueError("The demo cover letter signatory does not match the reviewed profile")
    if posting.company_name != DEMO_COMPANY or posting.title != DEMO_ROLE:
        raise ValueError("The demo cover letter requires the recorded Anduril application")
    if letter.salutation != "Dear Anduril Hiring Team," or (
        letter.job_title != DEMO_ROLE or letter.company_name != DEMO_COMPANY
    ):
        raise ValueError("The demo cover letter company or role identity changed")
    if tuple(item.text for item in letter.paragraphs) != _DEMO_COVER_LETTER_PARAGRAPHS:
        raise ValueError("The demo cover letter wording changed")
    forbidden = (
        "u.s. person",
        "work authorization",
        "altium",
        "oscilloscope",
        "device tree",
        "bootloader",
        "pcie",
    )
    complete_text = " ".join(item.text for item in letter.paragraphs).casefold()
    if any(term in complete_text for term in forbidden):
        raise ValueError("The demo cover letter contains a prohibited unsupported claim")


def build_demo_cover_letter_evidence(
    profile: MasterProfile,
    posting: JobPosting,
    *,
    final_resume_evidence_ids: set[str] | None = None,
) -> tuple[list[CoverLetterEvidenceRecord], CoverLetterEvidenceSelectionDiagnostic]:
    if not is_demo_application(posting):
        raise ValueError("Demo evidence requested for a non-demo application")
    selected = _resolve_demo_evidence(profile)
    entries = {item.id: item for item in [*profile.experiences, *profile.projects]}
    resume_ids = final_resume_evidence_ids or set()
    records = [
        CoverLetterEvidenceRecord(
            id=item.id,
            kind=(
                CoverLetterEvidenceKind.EXPERIENCE
                if entries[item.entity_id].kind is EntityKind.EXPERIENCE
                else CoverLetterEvidenceKind.PROJECT
            ),
            entity_id=item.entity_id,
            entry_title=entries[item.entity_id].title,
            source_text=item.source_text,
            technologies=list(item.technologies),
            outcomes=list(item.outcomes),
            provenance=[f"profile.evidence[{item.id}]"],
            retrieval_rank=index + 1,
            selected_in_final_resume=item.id in resume_ids or not resume_ids,
            selection_reason="Temporary demo fixture selected from canonical reviewed evidence.",
        )
        for index, item in enumerate(selected)
    ]
    return records, CoverLetterEvidenceSelectionDiagnostic(
        selected_evidence_ids=[record.id for record in records],
        considered_evidence_count=len(profile.evidence),
        # The exact letter uses York, Telebotics, and one combined project thread.
        narrative_thread_count=min(3, len({record.entity_id for record in records})),
        reasons=[record.selection_reason for record in records],
    )


def build_demo_cover_letter_output(
    evidence: list[CoverLetterEvidenceRecord],
    research: CompanyResearchBundle,
    posting: JobPosting,
) -> CoverLetterDraftOutput:
    """Build the bounded Anduril demo letter from exact reviewed source sentences."""

    by_entry: dict[str, list[CoverLetterEvidenceRecord]] = {}
    for record in evidence:
        if record.entity_id:
            by_entry.setdefault(record.entity_id, []).append(record)
    telebotics = next((items for key, items in by_entry.items() if "telebotics" in key), [])
    hardware = next((items for key, items in by_entry.items() if "lassonde" in key), [])
    hand = next((items for key, items in by_entry.items() if key == "robotic-hand"), [])
    posting_facts = [
        fact
        for fact in research.facts
        if fact.confidence is CompanyFactConfidence.POSTING_AUTHORITY
    ]
    posting_fact = next(
        (fact for fact in posting_facts if "electrical hardware" in fact.fact.casefold()),
        posting_facts[0],
    )
    opening_record = telebotics[0]
    company = f" at {posting.company_name}" if posting.company_name else ""
    posting_focus = ", ".join(
        term
        for term in ("electrical hardware", "embedded firmware", "system integration")
        if term in posting_fact.fact.casefold()
    ) or "electrical hardware and functional prototypes"
    opening = _demo_paragraph(
        CoverLetterParagraphPurpose.OPENING,
        [
            (
                _source_sentence(opening_record, "At Telebotics, "),
                [opening_record.id],
                [],
                [],
            ),
            (
                f"That is why the {posting.title} role{company} interests me: the work spans "
                f"{posting_focus}, and taking electronics to a functional prototype.",
                [],
                [fact.id for fact in posting_facts],
                [
                    CoverLetterCanonicalMetadata.COMPANY_NAME,
                    CoverLetterCanonicalMetadata.ROLE_TITLE,
                ],
            ),
        ],
        "thread-opening",
    )
    paragraphs = [
        opening,
        _demo_story(
            CoverLetterParagraphPurpose.EXPERIENCE_CONNECTION,
            hardware,
            "At Lassonde School of Engineering, ",
            "thread-r-and-d",
        ),
        _demo_story(
            CoverLetterParagraphPurpose.CONTRIBUTION,
            telebotics[1:],
            "At Telebotics, ",
            "thread-telebotics",
        ),
        _demo_story(
            CoverLetterParagraphPurpose.ROLE_FIT,
            hand,
            "On the Vision Controlled Robotic Hand project, ",
            "thread-vision-hand",
        ),
        _demo_paragraph(
            CoverLetterParagraphPurpose.CLOSING,
            [
                (
                    f"I would be glad to bring that experience to the {posting.title} role"
                    f"{company}.",
                    [],
                    [],
                    [
                        CoverLetterCanonicalMetadata.COMPANY_NAME,
                        CoverLetterCanonicalMetadata.ROLE_TITLE,
                    ],
                )
            ],
            "thread-closing",
        ),
    ]
    return CoverLetterDraftOutput(paragraphs=paragraphs)


def _demo_story(
    purpose: CoverLetterParagraphPurpose,
    records: list[CoverLetterEvidenceRecord],
    prefix: str,
    thread_id: str,
) -> CoverLetterDraftParagraph:
    selected = records[:4]
    sentences: list[tuple[str, list[str], list[str], list[CoverLetterCanonicalMetadata]]] = []
    if selected:
        sentences.append((_source_sentence(selected[0], prefix), [selected[0].id], [], []))
    for record in selected[1:2]:
        sentences.append((_source_sentence(record, ""), [record.id], [], []))
    if len(selected) >= 4:
        left, right = selected[2:4]
        left_text = _source_action(left)
        right_text = _source_action(right)
        sentences.append(
            (
                f"I {left_text}, and I {right_text}.",
                [left.id, right.id],
                [],
                [],
            )
        )
    elif len(selected) == 3:
        record = selected[2]
        sentences.append((_source_sentence(record, ""), [record.id], [], []))
    return _demo_paragraph(purpose, sentences, thread_id)


def _source_action(record: EvidenceItem | CoverLetterEvidenceRecord) -> str:
    text = record.source_text.strip().rstrip(".")
    return text[:1].casefold() + text[1:]


def _source_sentence(record: EvidenceItem | CoverLetterEvidenceRecord, prefix: str) -> str:
    return f"{prefix}I {_source_action(record)}."


def _demo_paragraph(
    purpose: CoverLetterParagraphPurpose,
    sentence_specs: list[tuple[str, list[str], list[str], list[CoverLetterCanonicalMetadata]]],
    thread_id: str,
) -> CoverLetterDraftParagraph:
    authorities = [
        CoverLetterSentenceAuthority(
            text=text,
            candidate_evidence_ids=evidence_ids,
            posting_fact_ids=posting_ids,
            canonical_metadata=metadata,
        )
        for text, evidence_ids, posting_ids, metadata in sentence_specs
    ]
    return CoverLetterDraftParagraph(
        purpose=purpose,
        text=" ".join(authority.text for authority in authorities),
        candidate_evidence_ids=list(
            dict.fromkeys(
                evidence_id
                for authority in authorities
                for evidence_id in authority.candidate_evidence_ids
            )
        ),
        company_research_ids=list(
            dict.fromkeys(
                research_id
                for authority in authorities
                for research_id in authority.posting_fact_ids
            )
        ),
        narrative_thread_id=thread_id,
        length_class=CoverLetterLengthClass.DEVELOPED,
        source_bound_sentences=authorities,
    )


def _resolve_demo_evidence(profile: MasterProfile) -> list[EvidenceItem]:
    return [evidence for _, evidence, _ in _resolve_demo_evidence_with_text(profile)]


def _resolve_demo_evidence_with_text(
    profile: MasterProfile,
) -> list[tuple[str, EvidenceItem, str]]:
    resolved: list[tuple[str, EvidenceItem, str]] = []
    seen: set[str] = set()
    for entry_id, snippet, text in _DEMO_RESUME_SPECS:
        evidence = _find_evidence(profile, snippet, entry_id=entry_id)
        if evidence.id in seen:
            raise ValueError("Temporary demo evidence cannot be reused across bullets")
        seen.add(evidence.id)
        resolved.append((entry_id, evidence, text))
    return resolved


def _find_evidence(
    profile: MasterProfile,
    snippet: str,
    *,
    entry_id: str | None = None,
) -> EvidenceItem:
    expected = set(_tokens(snippet))
    matches = [
        item
        for item in profile.evidence
        if item.confirmed
        and (entry_id is None or item.entity_id == entry_id)
        and expected <= set(_tokens(item.source_text))
    ]
    if len(matches) != 1:
        raise ValueError(f"Temporary demo evidence is missing or ambiguous: {snippet}")
    return matches[0]


def _canonical_demo_entry(entries: dict[str, ResumeItem], entry_id: str) -> ResumeItem:
    entry = entries.get(entry_id)
    if entry is None or entry.title != _DEMO_ENTRY_TITLES[entry_id]:
        raise ValueError("Temporary demo entry metadata is unavailable or changed")
    if entry_id == "telebotics-mechatronics-engineer" and entry.organization != "Telebotics":
        raise ValueError("Temporary demo employer metadata is unavailable or changed")
    if entry_id == "lassonde-rd-hardware-engineer" and (
        entry.organization is None
        or "lassonde school of engineering" not in entry.organization.casefold()
    ):
        raise ValueError("Temporary demo organization metadata is unavailable or changed")
    return entry


def _demo_skills(profile: MasterProfile) -> list[TechnicalSkillCategory]:
    reviewed = [
        (category, skill)
        for category in profile.technical_skills
        for skill in category.skills
    ]
    categories: list[TechnicalSkillCategory] = []
    used: set[str] = set()
    for label, desired in _DEMO_SKILL_GROUPS.items():
        skills = []
        for target in desired:
            match = next(
                (
                    skill
                    for _, skill in reviewed
                    if skill.value.casefold() not in used
                    and _skill_matches(skill.value, target)
                ),
                None,
            )
            if match is not None:
                used.add(match.value.casefold())
                skills.append(match.model_copy(deep=True))
        if skills:
            categories.append(
                TechnicalSkillCategory(
                    id=f"demo-{re.sub(r'[^a-z0-9]+', '-', label.casefold()).strip('-')}",
                    category=label,
                    skills=skills,
                    values=[skill.value for skill in skills],
                    source_reference="reviewed-career-profile",
                )
            )
    return categories


def _skill_matches(value: str, target: str) -> bool:
    value_tokens = set(_tokens(value))
    target_tokens = set(_tokens(target))
    return value_tokens == target_tokens or target_tokens <= value_tokens


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.casefold())


__all__ = [
    "DEMO_COMPANY",
    "DEMO_ROLE",
    "build_demo_cover_letter",
    "build_demo_cover_letter_evidence",
    "build_demo_cover_letter_output",
    "build_demo_resume_plan",
    "build_demo_structured_resume",
    "demo_mode_enabled",
    "is_demo_application",
    "is_demo_details",
    "validate_demo_plan",
    "validate_demo_cover_letter",
    "validate_demo_structured_resume",
]
