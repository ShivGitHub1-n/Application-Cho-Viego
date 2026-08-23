from __future__ import annotations

import json
from pathlib import Path

import pytest

from resume_tailor.application.company_research import BoundedCompanyResearchService
from resume_tailor.application.cover_letter import CoverLetterService
from resume_tailor.application.cover_letter_evidence import CoverLetterEvidencePortfolio
from resume_tailor.application.cover_letter_page_fit import CoverLetterPageFitter
from resume_tailor.application.cover_letter_validation import (
    CoverLetterValidator,
    DeterministicCoverLetterComposer,
)
from resume_tailor.domain.cover_letter import (
    CoverLetter,
    CoverLetterLengthClass,
    CoverLetterPageFitStatus,
    CoverLetterParagraphPurpose,
)
from resume_tailor.domain.llm_models import CoverLetterDraftOutput, CoverLetterDraftParagraph
from resume_tailor.domain.models import JobPosting, MasterProfile, TemplateConstraints
from resume_tailor.infrastructure.cover_letter_rendering import CoverLetterRenderer
from resume_tailor.infrastructure.optimization import DeterministicResumeOptimizer
from resume_tailor.infrastructure.rendering import PageCountVerificationError
from tests.cover_letter_helpers import ControlledCoverLetterRenderer, cover_letter_case

ROOT = Path(__file__).resolve().parents[1]
PROFILE_FIXTURE = ROOT / "tests" / "fixtures" / "world_star_tech_production_profile.json"
POSTING_FIXTURE = ROOT / "tests" / "fixtures" / "huawei_autonomous_research_posting.json"

REJECTED_HUAWEI_PARAGRAPHS = (
    "The Huawei posting connects the Autonomous Driving and Multimodal AI Researcher role "
    "to work in autonomous driving, scene understanding, multimodal reasoning, and deep "
    "learning. That has a practical connection to my work with a retrofittable drive-by-wire "
    "actuation system for an autonomous golf cart.",
    "My Principle Hardware Engineer work involved leading the design and technical architecture "
    "of a retrofittable drive-by-wire actuation system for an autonomous golf cart, integrating "
    "electronic steering, throttle, and braking through 3 linear actuators and embedded control "
    "interfaces. That is a direct connection to the posting's work in autonomous driving.",
    "My R&D Hardware Engineer work involved integrating the hardware architecture of a level 1 "
    "autonomous teleoperation last-mile delivery solution for low-speed vehicles (LSVs) using "
    "ROS 2, enabling real-time remote control, safety override, and operator-to-vehicle round-trip "
    "latency <200 ms over 5G modem. It is a second concrete connection to the posting's work in "
    "autonomous driving.",
    "My Crest – AI-Powered Expense Intelligence Platform work involved building an AI-powered "
    "financial management platform that analyzed 4,000+ transactions using natural language "
    "queries, enabling users to explore spending patterns, budgets, and expense data through an "
    "interactive dashboard. The domain is different from the posting's autonomous driving work. "
    "What I can carry from it is experience with an AI-powered financial management platform that "
    "analyzed 4,000+ transactions using natural language queries.",
    "I can contribute now through experience spanning a retrofittable drive-by-wire actuation "
    "system for an autonomous golf cart, a level 1 autonomous teleoperation last-mile delivery "
    "solution for low-speed vehicles (LSVs), and an AI-powered financial management platform that "
    "analyzed 4,000+ transactions using natural language queries. The Autonomous Driving and "
    "Multimodal AI Researcher role is a logical next step because its emphasis on autonomous "
    "driving, scene understanding, multimodal reasoning, and deep learning continues the technical "
    "direction of that work.",
)


def _production_case():
    profile = MasterProfile.model_validate(json.loads(PROFILE_FIXTURE.read_text(encoding="utf-8")))
    posting = JobPosting.model_validate(
        json.loads(POSTING_FIXTURE.read_text(encoding="utf-8"))
    ).model_copy(
        update={
            "company_name": "Huawei",
            "source_url": "https://example.invalid/huawei-autonomous-research",
        }
    )
    plan = DeterministicResumeOptimizer().create_plan(
        profile,
        posting,
        TemplateConstraints(max_experience_lines=8, max_project_lines=4),
    )
    research = BoundedCompanyResearchService().research(
        CoverLetterService.default_research_request(posting)
    )
    evidence, _ = CoverLetterEvidencePortfolio().select(profile, posting, plan)
    return profile, posting, plan, research, evidence


def _rejected_huawei_output(evidence_ids: list[str], fact_id: str) -> CoverLetterDraftOutput:
    purposes = [
        CoverLetterParagraphPurpose.OPENING,
        CoverLetterParagraphPurpose.EXPERIENCE_CONNECTION,
        CoverLetterParagraphPurpose.CONTRIBUTION,
        CoverLetterParagraphPurpose.CONTRIBUTION,
        CoverLetterParagraphPurpose.CLOSING,
    ]
    paragraph_evidence = [
        evidence_ids[:1],
        evidence_ids[:1],
        evidence_ids[1:2],
        evidence_ids[2:3],
        evidence_ids[:3],
    ]
    return CoverLetterDraftOutput(
        paragraphs=[
            CoverLetterDraftParagraph(
                purpose=purpose,
                text=text,
                candidate_evidence_ids=used,
                company_research_ids=[fact_id],
                narrative_thread_id=f"rejected-thread-{index}",
                length_class=CoverLetterLengthClass.STANDARD,
            )
            for index, (purpose, text, used) in enumerate(
                zip(purposes, REJECTED_HUAWEI_PARAGRAPHS, paragraph_evidence, strict=True)
            )
        ]
    )


def _failed_codes(result) -> set[str]:
    return {gate.code for gate in result.quality_gates if gate.status.value == "failed"}


class _UnavailablePagination:
    def measure(self, path: Path):
        del path
        raise PageCountVerificationError("Offline regression uses occupancy estimation")

    def measure_many(self, paths: list[Path]):
        del paths
        raise PageCountVerificationError("Offline regression uses occupancy estimation")


def test_malformed_huawei_draft_is_a_rejected_regression_fixture() -> None:
    profile, posting, plan, research, evidence = _production_case()
    output = _rejected_huawei_output(
        [item.id for item in evidence],
        str(research.facts[0].id),
    )

    validated = CoverLetterValidator().validate_output(output, evidence, research, posting)

    assert {
        "resume_paraphrase",
        "repetitive_paragraph_structure",
        "mechanical_posting_reference",
        "interchangeable_company_connection",
        "enumerative_closing",
        "insufficient_narrative_development",
    } <= _failed_codes(validated)
    assert not CoverLetterService._required_content_gates_pass(validated.quality_gates)


@pytest.mark.parametrize(
    "expected_code",
    [
        "resume_paraphrase",
        "repetitive_paragraph_structure",
        "mechanical_posting_reference",
        "enumerative_closing",
        "insufficient_narrative_development",
    ],
)
def test_rejected_huawei_structure_has_each_typed_quality_reason(
    expected_code: str,
) -> None:
    _, posting, _, research, evidence = _production_case()
    output = _rejected_huawei_output(
        [item.id for item in evidence],
        str(research.facts[0].id),
    )

    validated = CoverLetterValidator().validate_output(output, evidence, research, posting)

    assert expected_code in _failed_codes(validated)


def test_company_name_without_substantive_connection_is_interchangeable() -> None:
    _, posting, _, research, evidence = _production_case()
    output = DeterministicCoverLetterComposer().variants(evidence, research, posting)[1]
    paragraphs = list(output.paragraphs)
    paragraphs[0] = paragraphs[0].model_copy(
        update={
            "text": (
                "Huawei offers this engineering role. I have worked on drive-by-wire actuation "
                "and ROS 2."
            )
        }
    )

    validated = CoverLetterValidator().validate_output(
        output.model_copy(update={"paragraphs": paragraphs}),
        evidence,
        research,
        posting,
    )

    assert "interchangeable_company_connection" in _failed_codes(validated)


def test_deterministic_variants_synthesize_threads_without_provider_or_research_calls() -> None:
    _, posting, _, research, evidence = _production_case()
    composer = DeterministicCoverLetterComposer()

    outputs = composer.variants(evidence, research, posting)

    assert [output.paragraphs[0].length_class for output in outputs] == [
        CoverLetterLengthClass.CONCISE,
        CoverLetterLengthClass.STANDARD,
        CoverLetterLengthClass.DEVELOPED,
    ]
    assert all(len(output.paragraphs) == 4 for output in outputs)
    evidence_strategies = [
        tuple(
            dict.fromkeys(
                evidence_id
                for paragraph in output.paragraphs[1:-1]
                for evidence_id in paragraph.candidate_evidence_ids
            )
        )
        for output in outputs
    ]
    assert len(set(evidence_strategies)) == len(evidence_strategies)
    assert len(evidence_strategies[0]) < len(evidence_strategies[-1])
    assert not hasattr(composer, "language_model")
    assert not hasattr(composer, "company_research")


def test_production_variants_are_grounded_and_keep_crest_explicitly_adjacent() -> None:
    _, posting, _, research, evidence = _production_case()
    outputs = DeterministicCoverLetterComposer().variants(evidence, research, posting)

    for output in outputs:
        validated = CoverLetterValidator().validate_output(output, evidence, research, posting)
        assert not validated.rejected_claims
        assert not _failed_codes(validated)

    developed_text = " ".join(paragraph.text for paragraph in outputs[-1].paragraphs)
    assert "i do not claim direct" not in developed_text.casefold()
    assert "the useful bridge is" in developed_text.casefold()
    assert "financial" in developed_text.casefold()


def test_senior_target_title_and_concise_posting_facts_produce_an_artifact() -> None:
    profile, posting, plan = cover_letter_case(
        title="Senior Embedded Firmware Engineer",
        company="Northwind Robotics",
        description=(
            "Develop embedded firmware for STM32 sensor controllers. Validate SPI "
            "communication and build automated hardware test systems for autonomous mobile "
            "robots. Work with electrical engineers to diagnose interface failures and "
            "improve controller reliability."
        ),
    )
    service = CoverLetterService(
        renderer=ControlledCoverLetterRenderer([0.87, 0.90, 0.92]),
    )

    artifact = service.generate_artifact(
        profile,
        posting,
        plan,
        date_text="August 16, 2026",
    )

    failed = {
        gate.code
        for gate in artifact.quality_gates
        if gate.status.value == "failed"
    }
    text = " ".join(paragraph.text for paragraph in artifact.letter.paragraphs)
    accepted = [
        candidate
        for candidate in artifact.candidate_validations
        if candidate.rendering_attempted
    ]
    assert artifact.ready_for_review
    assert accepted
    assert not failed
    assert "Northwind Robotics" in text
    assert "Senior Embedded Firmware Engineer" in text
    assert "Firmware Intern" in text
    assert "Test Engineering Assistant" in text
    assert all("unsupported_title_change" not in item.rejection_codes for item in accepted)
    assert all("copied_posting_language" not in item.rejection_codes for item in accepted)


def test_substantive_developed_variant_improves_density_and_reaches_preferred_band(
    tmp_path: Path,
) -> None:
    profile, posting, plan, research, evidence = _production_case()
    outputs = DeterministicCoverLetterComposer().variants(evidence, research, posting)
    validator = CoverLetterValidator()
    letters = []
    for output in outputs:
        validated = validator.validate_output(output, evidence, research, posting)
        letters.append(
            CoverLetter(
                profile_id=profile.id,
                profile_version=profile.version,
                posting_id=posting.id,
                plan_fingerprint="production-plan",
                candidate_name=profile.display_name,
                contact=profile.contact,
                date_text="July 21, 2026",
                job_title=posting.title,
                company_name=posting.company_name,
                recipient={"company": posting.company_name},
                salutation="Dear Hiring Manager,",
                paragraphs=validated.paragraphs,
                signoff_name=profile.display_name,
            )
        )
    renderer = ControlledCoverLetterRenderer([0.78, 0.87, 0.94], exact=False)

    fitted = CoverLetterPageFitter(renderer).fit(letters, tmp_path)

    assert fitted.letter.paragraphs[0].length_class is CoverLetterLengthClass.STANDARD
    assert fitted.diagnostic.estimated_utilization == 0.87
    assert fitted.diagnostic.preferred_density_reachable
    assert fitted.diagnostic.status is CoverLetterPageFitStatus.PAGINATION_UNVERIFIED
    assert fitted.diagnostic.candidates[0].estimated_utilization < (
        fitted.diagnostic.candidates[-1].estimated_utilization
    )
    assert renderer.pagination_attempt_count == 1


def test_real_offline_candidate_respects_concise_narrative_policy() -> None:
    profile, posting, plan, _, _ = _production_case()
    service = CoverLetterService(
        renderer=CoverLetterRenderer(page_count_provider=_UnavailablePagination())
    )

    artifact = service.generate_artifact(
        profile,
        posting,
        plan,
        date_text="July 21, 2026",
    )

    narrative_words = sum(len(paragraph.text.split()) for paragraph in artifact.letter.paragraphs)
    assert 300 <= narrative_words <= 425
    assert (
        artifact.letter.layout_profile.preferred_utilization_floor
        <= artifact.page_fit.estimated_utilization
        <= artifact.letter.layout_profile.preferred_utilization_ceiling
    )
    assert artifact.page_fit.estimated_remaining_lines > 0
    assert artifact.page_fit.preferred_density_reachable
    assert artifact.page_fit.underfill_or_overflow == "balanced_one_page"
    assert artifact.page_fit.status is CoverLetterPageFitStatus.PAGINATION_UNVERIFIED
    assert artifact.call_counts.provider_calls == 0
    assert artifact.call_counts.research_network_requests == 0
    assert artifact.call_counts.pagination_attempts == 1


def test_formulaic_filler_cannot_make_a_variant_eligible_for_page_fit() -> None:
    _, posting, _, research, evidence = _production_case()
    output = DeterministicCoverLetterComposer().variants(evidence, research, posting)[-1]
    paragraphs = list(output.paragraphs)
    paragraphs[-1] = paragraphs[-1].model_copy(
        update={
            "text": (
                f"{paragraphs[-1].text} I am passionate about driving innovation and making a "
                "meaningful impact."
            )
        }
    )

    validated = CoverLetterValidator().validate_output(
        output.model_copy(update={"paragraphs": paragraphs}),
        evidence,
        research,
        posting,
    )

    gates = {gate.gate: gate for gate in validated.quality_gates}
    assert gates["generic_language"].status.value == "failed"
