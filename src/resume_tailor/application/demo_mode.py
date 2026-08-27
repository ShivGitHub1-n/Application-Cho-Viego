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

from resume_tailor.domain.application_strategy import (
    ApplicationStrategyPlan,
    EvidencePriorityTier,
    StrategyEntryPlan,
    StrategyEvidenceChoice,
)
from resume_tailor.domain.company_research import CompanyFactConfidence, CompanyResearchBundle
from resume_tailor.domain.cover_letter import (
    CoverLetterCanonicalMetadata,
    CoverLetterEvidenceKind,
    CoverLetterEvidenceRecord,
    CoverLetterEvidenceSelectionDiagnostic,
    CoverLetterLengthClass,
    CoverLetterParagraphPurpose,
    CoverLetterSentenceAuthority,
)
from resume_tailor.domain.llm_models import CoverLetterDraftOutput, CoverLetterDraftParagraph
from resume_tailor.domain.models import (
    ClaimCandidate,
    ClaimSupport,
    EntityKind,
    EvidenceItem,
    JobPosting,
    MasterProfile,
    TailoringPlan,
    TechnicalSkillCategory,
    TemplateConstraints,
)

DEMO_COMPANY = "Anduril Industries"
DEMO_ROLE = "2027 Electrical Engineer Intern"

_TELEBOTICS_SNIPPETS = (
    "Led the architecture of a retrofittable Club Car drive-by-wire system",
    "Authored ICDs and pin-level interface documentation defining 30+ control",
    "Designed an independent STM32 safety-supervision architecture with command validation",
)
_R_AND_D_SNIPPETS = (
    "Integrated GPIO, CAN, UART, and USB communication between NVIDIA Jetson Orin",
    "Supported STM32F4 peripherals in STM32CubeIDE, contributed C++ integration code",
    "Designed and integrated sensor architecture + wiring harnesses including RTK GPS",
    "Designed and installed a 48 V electrical architecture with ignition-controlled power",
)
_VISION_HAND_SNIPPETS = (
    "Designed and built a 3-DoF tendon-driven robotic hand with custom CAD",
    "Developed Arduino firmware to control 3 independent servos at 50 Hz",
    "Integrated mechanical, electrical, and software subsystems through a 115200-baud",
    "Built a Python/OpenCV pipeline using MediaPipe's 21-point hand tracking",
)

_SKILL_PRIORITIES: dict[str, tuple[str, ...]] = {
    "Programming & Scripting": ("Python", "C", "C++", "Bash", "GitHub"),
    "Embedded Systems": (
        "STM32",
        "Arduino",
        "NVIDIA Jetson Orin",
        "Linux",
        "Ubuntu",
        "GPIO",
        "PWM",
        "ADC/DAC",
        "UART",
        "I2C",
        "SPI",
        "USB",
        "CAN",
        "timers",
        "interrupts",
    ),
    "Robotics": (
        "ROS 2",
        "sensor integration",
        "Actuator-command design",
        "Command validation",
        "Heartbeat monitoring",
        "Watchdog supervision",
        "Safe-stop and fault handling",
        "Closed-loop actuator verification",
    ),
    "Wiring & Electrical Systems": (
        "Wiring Harness Design",
        "Crimping & Soldering",
        "Power Distribution",
        "Voltage Regulation",
        "Relays",
        "MOSFET switching",
        "H-bridges",
    ),
    "Mechanical Design & CAD": (
        "SolidWorks",
        "Fusion360",
        "GD&T",
        "DFM/DFA",
        "3D Print drawings",
        "Onyx 3D printing",
        "laser cutting",
    ),
    "Tools": ("Git", "GitHub"),
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

    Company and role remain dynamic presentation context in the generated
    letter; they are not activation gates while the explicit demo flag is on.
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
        narrative_thread_count=len({record.entity_id for record in records}),
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
    snippets = (*_TELEBOTICS_SNIPPETS, *_R_AND_D_SNIPPETS, *_VISION_HAND_SNIPPETS[:3])
    optional = _VISION_HAND_SNIPPETS[3]
    selected = [_find_evidence(profile, snippet) for snippet in snippets]
    try:
        selected.append(_find_evidence(profile, optional))
    except ValueError:
        pass
    return selected


def _find_evidence(profile: MasterProfile, snippet: str) -> EvidenceItem:
    expected = set(_tokens(snippet))
    matches = [
        item
        for item in profile.evidence
        if item.confirmed and expected <= set(_tokens(item.source_text))
    ]
    if len(matches) != 1:
        raise ValueError(f"Temporary demo evidence is missing or ambiguous: {snippet}")
    return matches[0]


def _demo_skills(profile: MasterProfile) -> list[TechnicalSkillCategory]:
    categories: list[TechnicalSkillCategory] = []
    for category in profile.technical_skills:
        desired = _SKILL_PRIORITIES.get(category.category)
        if not desired:
            continue
        skills = [
            skill
            for skill in category.skills
            if any(_skill_matches(skill.value, target) for target in desired)
        ]
        if skills:
            categories.append(
                category.model_copy(
                    update={"skills": skills, "values": [skill.value for skill in skills]}
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
    "build_demo_cover_letter_evidence",
    "build_demo_cover_letter_output",
    "build_demo_resume_plan",
    "demo_mode_enabled",
    "is_demo_application",
    "is_demo_details",
    "validate_demo_plan",
]
