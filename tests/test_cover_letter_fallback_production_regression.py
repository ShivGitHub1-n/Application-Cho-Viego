from __future__ import annotations

from pathlib import Path

import pytest

from resume_tailor.application.company_research import BoundedCompanyResearchService
from resume_tailor.application.cover_letter import CoverLetterService
from resume_tailor.application.cover_letter_evidence import CoverLetterEvidencePortfolio
from resume_tailor.application.cover_letter_policy import (
    COVER_LETTER_WRITING_POLICY_VERSION,
)
from resume_tailor.application.cover_letter_validation import (
    CoverLetterValidator,
    DeterministicCoverLetterComposer,
)
from resume_tailor.application.services import TailorResumeService
from resume_tailor.domain.application_strategy import (
    ApplicationStrategyPlan,
    EvidencePriorityTier,
    StrategyEntryPlan,
    StrategyEvidenceChoice,
)
from resume_tailor.domain.company_research import (
    CompanyFactConfidence,
    CompanyResearchStatus,
)
from resume_tailor.domain.cover_letter import (
    CoverLetterEvidenceKind,
    CoverLetterEvidenceRecord,
    CoverLetterFallbackReason,
    CoverLetterParagraphPurpose,
    CoverLetterQualityGateStatus,
)
from resume_tailor.domain.llm_models import CoverLetterDraftResult, LlmOperation
from resume_tailor.domain.models import (
    EntityKind,
    EvidenceItem,
    JobPosting,
    MasterProfile,
    ResumeItem,
    TemplateConstraints,
)
from resume_tailor.frontend import cover_letter_view
from resume_tailor.infrastructure.optimization import (
    DeterministicResumeOptimizer,
    EvidenceBoundResumeWriter,
)
from tests.cover_letter_helpers import ControlledCoverLetterRenderer
from tests.fakes import FakeResumeLanguageModel, metadata

ROOT = Path(__file__).resolve().parents[1]


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


def test_titan_posting_only_fallback_survives_complete_service_validation() -> None:
    """Reproduce the live no-plan Streamlit fallback through the application facade."""

    profile = MasterProfile.model_validate_json(
        (ROOT / "tests" / "fixtures" / "world_star_tech_production_profile.json").read_text(
            encoding="utf-8"
        )
    )
    posting = JobPosting(
        id="titan-posting-only-service-regression",
        title="Mechatronics Engineer Intern - Hardware",
        company_name="TITAN Haptics",
        description=(
            ROOT / "tests" / "fixtures" / "titan_haptics_mechatronics_integration_engineer.txt"
        ).read_text(encoding="utf-8"),
    )

    class RecordingComposer(DeterministicCoverLetterComposer):
        first_output = None

        def variants(self, evidence, research, active_posting):
            outputs = super().variants(evidence, research, active_posting)
            self.first_output = outputs[0]
            return outputs

    preparation = CoverLetterService()
    research = preparation._research.research(
        preparation.default_research_request(posting)
    )
    evidence, _ = preparation._evidence.select(profile, posting, plan=None)
    invalid_provider_output = DeterministicCoverLetterComposer().variants(
        evidence,
        research,
        posting,
    )[0]
    provider_paragraphs = []
    for index, paragraph in enumerate(invalid_provider_output.paragraphs):
        provider_paragraphs.append(
            paragraph.model_copy(
                update={
                    "text": (
                        "TITAN Haptics operates an unsupported production fleet."
                        if index == 0
                        else paragraph.text
                    ),
                    "source_bound_sentences": [],
                }
            )
        )
    provider = FakeResumeLanguageModel(
        draft_cover_letter=CoverLetterDraftResult(
            metadata=metadata(LlmOperation.COVER_LETTER_DRAFT),
            output=invalid_provider_output.model_copy(
                update={"paragraphs": provider_paragraphs}
            ),
        )
    )
    composer = RecordingComposer()
    cover_letter_service = CoverLetterService(
        language_model=provider,
        renderer=ControlledCoverLetterRenderer([0.82, 0.84, 0.86, 0.88]),
        deterministic_composer=composer,
    )
    service = TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
        cover_letter_service=cover_letter_service,
    )

    artifact = service.generate_cover_letter_artifact(
        profile,
        posting,
        plan=None,
        research_request=service.default_cover_letter_research_request(posting),
    )

    assert composer.first_output is not None
    opening = composer.first_output.paragraphs[0]
    assert opening.source_bound_sentences
    connection = opening.source_bound_sentences[0]
    assert connection.candidate_evidence_ids
    assert len(connection.posting_fact_ids) == 1
    facts_by_id = {fact.id: fact for fact in artifact.company_research.facts}
    attached_fact = facts_by_id[connection.posting_fact_ids[0]]

    assert artifact.company_research.status is CompanyResearchStatus.POSTING_ONLY
    assert attached_fact.fact == "Integrate drivers, test real hardware, and iterate performance."
    assert "drivers" in connection.text.casefold()
    assert posting.company_name in connection.text
    assert posting.title in connection.text
    assert artifact.fingerprint_inputs.writing_policy_version == (
        COVER_LETTER_WRITING_POLICY_VERSION
    )
    assert artifact.call_counts.provider_calls == 1
    assert artifact.provider_diagnostic.fallback_reason is (
        CoverLetterFallbackReason.ALL_PARAGRAPHS_REJECTED
    )
    assert all(not diagnostic.rejection_codes for diagnostic in artifact.candidate_validations)


def test_maintenance_posting_fragment_remains_source_faithful_without_numeric_wordplay() -> None:
    normalized = DeterministicCoverLetterComposer._normalize_posting_fragment(
        "Maintain schematics, BOMs, integration guides, and test reports."
    )

    assert normalized.startswith("maintaining schematics")
    assert "maintenance" not in normalized


def _posting_only_opening_case() -> tuple[
    JobPosting,
    list[CoverLetterEvidenceRecord],
]:
    posting = JobPosting(
        id="posting-only-opening",
        title="Intern",
        company_name="Example Motion",
        description=(
            "The intern will debug integrated electromechanical prototypes under "
            "bench-test conditions. Maintain clear build records for prototype "
            "reliability."
        ),
    )
    source_texts = [
        (
            "Authored interface-control documents defining 30 signals for ADC, DAC, "
            "PWM, I2C, UART, and motor-driver interfaces."
        ),
        "Contributed C++ integration code for sensor input and prototype control outputs.",
        "Designed fused wiring harnesses with relays and labelled connectors.",
        "Validated actuator commands, feedback signals, and manual override behavior.",
    ]
    evidence = [
        CoverLetterEvidenceRecord(
            id=f"opening-evidence-{index}",
            kind=CoverLetterEvidenceKind.EXPERIENCE,
            entity_id="controls",
            entry_title="Controls Engineer",
            source_text=source_text,
            technologies=(
                ["ADC", "DAC", "PWM", "I2C", "UART"] if index == 0 else []
            ),
            outcomes=["30 signals"] if index == 0 else [],
            provenance=["synthetic-reviewed-profile"],
            retrieval_rank=index + 1,
            selection_reason="Validated strategy-compatible story evidence.",
        )
        for index, source_text in enumerate(source_texts)
    ]
    return posting, evidence


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


def test_fallback_uses_natural_source_bound_cadence_without_four_sentence_dump() -> None:
    profile = _profile()
    posting = _hardware_posting()
    plan = _strategy_plan(profile, posting, ["controls", "integration", "actuator"])
    evidence, _ = CoverLetterEvidencePortfolio().select(profile, posting, plan)
    research = BoundedCompanyResearchService().research(
        CoverLetterService.default_research_request(posting)
    )

    composer = DeterministicCoverLetterComposer()
    variants = composer.variants(evidence, research, posting)
    output = composer.source_bound_fallback(
        evidence,
        research,
        posting,
    )
    body = output.paragraphs[1:-1]
    lowered = " ".join(paragraph.text for paragraph in body).casefold()
    variant_evidence_counts = [
        len(
            {
                evidence_id
                for paragraph in variant.paragraphs
                for evidence_id in paragraph.candidate_evidence_ids
            }
        )
        for variant in variants
    ]

    assert len(variants) == 4
    assert variant_evidence_counts == sorted(set(variant_evidence_counts))
    assert all(len(paragraph.source_bound_sentences) <= 3 for paragraph in body)
    assert any(
        len(paragraph.candidate_evidence_ids) == 3
        and len(paragraph.source_bound_sentences) == 2
        for paragraph in body
    )
    assert any(
        len(paragraph.candidate_evidence_ids) == 4
        and len(paragraph.source_bound_sentences) == 3
        for paragraph in body
    )
    assert all(
        phrase not in lowered
        for phrase in (
            "i also",
            "the project also involved",
            "another part of that work",
            "that role also involved",
        )
    )


def test_opening_does_not_immediately_reopen_the_same_entry() -> None:
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
    entity_by_evidence = {item.id: item.entity_id for item in evidence}
    opening_entities = {
        entity_by_evidence[item] for item in output.paragraphs[0].candidate_evidence_ids
    }
    first_story_entities = {
        entity_by_evidence[item] for item in output.paragraphs[1].candidate_evidence_ids
    }
    body_evidence_ids = {
        item for paragraph in output.paragraphs[1:-1] for item in paragraph.candidate_evidence_ids
    }

    assert opening_entities.isdisjoint(first_story_entities)
    assert set(output.paragraphs[0].candidate_evidence_ids).isdisjoint(body_evidence_ids)


def test_old_resume_summary_cadence_is_a_typed_quality_failure() -> None:
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
    body = paragraphs[1]
    paragraphs[1] = body.model_copy(
        update={
            "text": (
                "In my Controls Engineer work, I contributed embedded firmware. "
                "I also implemented safety supervision. Another part of that work "
                "was designing control schematics. That role also involved testing "
                "actuator feedback."
            ),
            "source_bound_sentences": [],
        }
    )

    validated = CoverLetterValidator().validate_output(
        output.model_copy(update={"paragraphs": paragraphs}),
        evidence,
        research,
        posting,
    )

    assert any(
        gate.code in {"resume_summary_cadence", "overdense_resume_summary"}
        and gate.status is CoverLetterQualityGateStatus.FAILED
        for gate in validated.quality_gates
    )


def test_posting_only_opening_records_candidate_and_specific_posting_authority() -> None:
    posting, evidence = _posting_only_opening_case()
    research = BoundedCompanyResearchService().research(
        CoverLetterService.default_research_request(posting)
    )
    composer = DeterministicCoverLetterComposer()
    outputs = [
        *composer.variants(evidence, research, posting),
        composer.source_bound_fallback(evidence, research, posting),
    ]
    facts_by_id = {fact.id: fact for fact in research.facts}

    assert research.status is CompanyResearchStatus.POSTING_ONLY
    assert all(
        fact.confidence is CompanyFactConfidence.POSTING_AUTHORITY
        for fact in research.facts
    )
    assert len(outputs) == 5

    for output in outputs:
        opening = output.paragraphs[0]
        assert opening.purpose is CoverLetterParagraphPurpose.OPENING
        assert opening.candidate_evidence_ids == ["opening-evidence-0"]
        assert len(opening.company_research_ids) == 1
        posting_fact = facts_by_id[opening.company_research_ids[0]]
        assert posting_fact.confidence is CompanyFactConfidence.POSTING_AUTHORITY
        assert all(
            sentence.candidate_evidence_ids == ["opening-evidence-0"]
            and sentence.posting_fact_ids == opening.company_research_ids
            and not sentence.verified_company_fact_ids
            for sentence in opening.source_bound_sentences
        )
        metadata_terms = CoverLetterValidator._content_terms(
            f"{posting.company_name} {posting.title}"
        )
        substantive_posting_terms = (
            CoverLetterValidator._content_terms(posting_fact.fact)
            & CoverLetterValidator._content_terms(opening.text)
        ) - metadata_terms
        assert len(substantive_posting_terms) >= 2

        validated = CoverLetterValidator().validate_output(
            output,
            evidence,
            research,
            posting,
        )
        relevant_gates = {
            gate.gate: gate
            for gate in validated.quality_gates
            if gate.gate
            in {
                "candidate_grounding",
                "company_grounding",
                "interchangeability",
                "opening_quality",
            }
        }
        assert not [
            claim
            for claim in validated.rejected_claims
            if claim.paragraph_index == 0
        ]
        assert all(
            gate.status is CoverLetterQualityGateStatus.PASSED
            for gate in relevant_gates.values()
        )
        assert validated.paragraphs[0].purpose is CoverLetterParagraphPurpose.OPENING


def test_posting_only_opening_does_not_authorize_an_unsupported_company_claim() -> None:
    posting, evidence = _posting_only_opening_case()
    research = BoundedCompanyResearchService().research(
        CoverLetterService.default_research_request(posting)
    )
    output = DeterministicCoverLetterComposer().variants(evidence, research, posting)[0]
    paragraphs = list(output.paragraphs)
    opening = paragraphs[0]
    authorities = list(opening.source_bound_sentences)
    authorities[0] = authorities[0].model_copy(
        update={
            "text": (
                authorities[0].text.rstrip(".")
                + " Example Motion ships one million production devices annually."
            )
        }
    )
    paragraphs[0] = opening.model_copy(
        update={
            "text": " ".join(sentence.text for sentence in authorities),
            "source_bound_sentences": authorities,
        }
    )

    validated = CoverLetterValidator().validate_output(
        output.model_copy(update={"paragraphs": paragraphs}),
        evidence,
        research,
        posting,
    )

    opening_rejections = [
        code
        for claim in validated.rejected_claims
        if claim.paragraph_index == 0
        for code in claim.codes
    ]
    assert opening_rejections
    assert "company_fact_not_verified" in opening_rejections


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
        renderer=ControlledCoverLetterRenderer([0.62, 0.70, 0.86, 0.90], exact=True)
    )

    artifact = service.generate_artifact(profile, posting, plan)

    assert artifact.ready_for_review
    assert artifact.letter.job_title == "Mechatronics Engineer Intern - Hardware"
    assert artifact.page_fit.exact_pagination
    assert artifact.page_fit.estimated_utilization == 0.86
    assert max(
        len(paragraph.candidate_evidence_ids)
        for paragraph in artifact.letter.paragraphs[1:-1]
    ) <= 3
    assert artifact.call_counts.provider_calls == 0
    selected_ids = {
        evidence_id
        for paragraph in artifact.letter.paragraphs
        for evidence_id in paragraph.candidate_evidence_ids
    }
    assert set(artifact.page_fit.evidence_added_during_page_fit) == selected_ids - set(
        artifact.page_fit.candidates[0].evidence_ids
    )


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
