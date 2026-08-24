from __future__ import annotations

import pytest

from resume_tailor.application.company_research import BoundedCompanyResearchService
from resume_tailor.application.cover_letter import CoverLetterService
from resume_tailor.application.cover_letter_evidence import CoverLetterEvidencePortfolio
from resume_tailor.application.cover_letter_validation import (
    CoverLetterValidator,
    DeterministicCoverLetterComposer,
)
from resume_tailor.domain.cover_letter import (
    CoverLetterEvidenceKind,
    CoverLetterEvidenceRecord,
    CoverLetterParagraphPurpose,
    CoverLetterQualityGateStatus,
    CoverLetterValidationStatus,
)
from resume_tailor.domain.llm_models import CoverLetterDraftOutput
from resume_tailor.domain.models import JobPosting
from tests.cover_letter_helpers import cover_letter_case, rich_cover_letter_case


def _grounded_case():
    profile, posting, plan = cover_letter_case()
    evidence, _ = CoverLetterEvidencePortfolio().select(profile, posting, plan)
    research = BoundedCompanyResearchService().research(
        CoverLetterService.default_research_request(posting)
    )
    output = DeterministicCoverLetterComposer().variants(evidence, research, posting)[0]
    return posting, evidence, research, output


def _replace_paragraph_text(
    output: CoverLetterDraftOutput,
    index: int,
    text: str,
) -> CoverLetterDraftOutput:
    paragraphs = list(output.paragraphs)
    paragraphs[index] = paragraphs[index].model_copy(
        update={"text": text, "source_bound_sentences": []}
    )
    return output.model_copy(update={"paragraphs": paragraphs})


@pytest.mark.parametrize(
    ("text", "expected_code"),
    [
        (
            "I built STM32 firmware and tested SPI sensor communication at 99 FPS.",
            "changed_number_or_metric",
        ),
        (
            "I built STM32 firmware with an unsupported CUDA implementation.",
            "unsupported_technology_or_entity",
        ),
        (
            "I led the firmware organization and architected its production platform.",
            "ownership_expansion",
        ),
        (
            "I deployed the prototype globally in production for millions of users.",
            "unsupported_production_claim",
        ),
        (
            "Since childhood, I have always dreamed of building these robots.",
            "unsupported_personal_motivation",
        ),
    ],
)
def test_candidate_claim_failures_are_rejected_locally(
    text: str,
    expected_code: str,
) -> None:
    posting, evidence, research, output = _grounded_case()
    changed = _replace_paragraph_text(output, 1, text)

    result = CoverLetterValidator().validate_output(changed, evidence, research, posting)

    codes = {code for claim in result.rejected_claims for code in claim.codes}
    assert expected_code in codes
    assert len(result.paragraphs) == len(output.paragraphs) - 1


def test_third_person_candidate_claim_is_not_allowed_to_bypass_grounding() -> None:
    posting, evidence, research, output = _grounded_case()
    changed = _replace_paragraph_text(
        output,
        1,
        "The firmware system ran an unsupported CUDA implementation at 99 FPS.",
    )

    result = CoverLetterValidator().validate_output(changed, evidence, research, posting)

    codes = {code for claim in result.rejected_claims for code in claim.codes}
    assert "unsupported_technology_or_entity" in codes
    assert "changed_number_or_metric" in codes


def test_unsupported_company_technology_is_rejected() -> None:
    posting, evidence, research, output = _grounded_case()
    changed = _replace_paragraph_text(
        output,
        0,
        (
            "Example Robotics uses ROS 2 and NVIDIA CUDA in a global production fleet. "
            "I have worked with STM32 and SPI."
        ),
    )

    result = CoverLetterValidator().validate_output(changed, evidence, research, posting)

    assert any("company_fact_not_verified" in claim.codes for claim in result.rejected_claims)


def test_invalid_paragraph_does_not_destroy_valid_siblings() -> None:
    posting, evidence, research, output = _grounded_case()
    changed = _replace_paragraph_text(output, 1, "I achieved an unsupported 900 percent result.")

    result = CoverLetterValidator().validate_output(changed, evidence, research, posting)

    assert result.rejected_claims
    assert {paragraph.purpose for paragraph in result.paragraphs} == {
        paragraph.purpose for paragraph in output.paragraphs[2:]
    } | {CoverLetterParagraphPurpose.OPENING}


def test_deterministic_letter_passes_interchangeability_and_generic_language_gates() -> None:
    posting, evidence, research, output = _grounded_case()

    result = CoverLetterValidator().validate_output(output, evidence, research, posting)
    gates = {gate.gate: gate for gate in result.quality_gates}

    assert gates["interchangeability"].status is CoverLetterQualityGateStatus.PASSED
    assert gates["generic_language"].status is CoverLetterQualityGateStatus.PASSED
    assert gates["company_grounding"].status is CoverLetterQualityGateStatus.PASSED
    assert gates["resume_complement"].status is CoverLetterQualityGateStatus.PASSED


def test_deterministic_company_connection_uses_grounded_source_detail_without_copying() -> None:
    posting = JobPosting(
        id="generic-integration-posting",
        title="Integration Engineer",
        company_name="Example Systems",
        description=(
            "Architect and build end-to-end hardware prototypes for sensor integration "
            "and enclosure testing."
        ),
    )
    evidence = [
        CoverLetterEvidenceRecord(
            id="multidisciplinary-pcb-evidence",
            kind=CoverLetterEvidenceKind.EXPERIENCE,
            source_text=(
                "Collaborated with a multidisciplinary team to design PCB assemblies "
                "and document connector test results."
            ),
            technologies=["hardware prototypes"],
            selection_reason="Reviewed direct integration evidence.",
        ),
        CoverLetterEvidenceRecord(
            id="sensor-enclosure-evidence",
            kind=CoverLetterEvidenceKind.PROJECT,
            source_text=(
                "Integrated sensor hardware and tested enclosure interfaces under "
                "defined laboratory constraints."
            ),
            technologies=["sensor integration"],
            selection_reason="Reviewed complementary integration evidence.",
        ),
    ]
    research = BoundedCompanyResearchService().research(
        CoverLetterService.default_research_request(posting)
    )
    output = DeterministicCoverLetterComposer().variants(evidence, research, posting)[0]

    result = CoverLetterValidator().validate_output(output, evidence, research, posting)
    gates = {gate.gate: gate for gate in result.quality_gates}
    combined = " ".join(paragraph.text for paragraph in result.paragraphs).casefold()

    assert not result.rejected_claims
    assert gates["company_grounding"].status is CoverLetterQualityGateStatus.PASSED
    assert gates["interchangeability"].status is CoverLetterQualityGateStatus.PASSED
    assert gates["resume_complement"].status is CoverLetterQualityGateStatus.PASSED
    assert not any("copied_posting_language" in claim.codes for claim in result.rejected_claims)
    # The deterministic emergency path is intentionally source-faithful: its
    # quality comes from selecting and ordering concrete reviewed facts, not
    # from manufacturing a paraphrased bridge. Each fact should still appear
    # only once in the narrative.
    assert combined.count(evidence[0].source_text.casefold().rstrip(".")) == 1
    assert "same technical problem" not in combined
    assert "separate constraint joined" not in combined


def test_invalid_synthetic_candidate_exposes_all_live_rejection_codes() -> None:
    description = (
        "Architect modular actuator interfaces and integrate sensor feedback through "
        "embedded controllers while troubleshooting prototype hardware under test."
    )
    profile, posting, plan = cover_letter_case(
        company="Nova Motion",
        title="Hardware Integration Engineer",
        description=description,
    )
    evidence, _ = CoverLetterEvidencePortfolio().select(profile, posting, plan)
    research = BoundedCompanyResearchService().research(
        CoverLetterService.default_research_request(posting)
    )
    output = DeterministicCoverLetterComposer().variants(evidence, research, posting)[1]
    invalid = _replace_paragraph_text(
        output,
        0,
        (f"{description} Nova Motion offers this role. My background is relevant."),
    )
    invalid = _replace_paragraph_text(
        invalid,
        -1,
        "I would welcome a conversation about this opportunity.",
    )

    result = CoverLetterValidator().validate_output(invalid, evidence, research, posting)
    failed_gate_codes = {
        gate.code
        for gate in result.quality_gates
        if gate.status is CoverLetterQualityGateStatus.FAILED
    }
    rejected_codes = {code for claim in result.rejected_claims for code in claim.codes}

    assert {
        "candidate_claims_supported",
        "company_connection_verified",
        "interchangeable_company_connection",
    } <= failed_gate_codes
    assert "copied_posting_language" in rejected_codes


def test_keyword_only_company_reference_remains_interchangeable() -> None:
    posting, evidence, research, output = _grounded_case()
    keyword_only = _replace_paragraph_text(
        output,
        0,
        (
            "Example Robotics and the Embedded Firmware Intern role mention STM32, SPI, "
            "sensors, and hardware test systems. I use STM32 and SPI."
        ),
    )
    paragraphs = list(keyword_only.paragraphs)
    paragraphs[1] = paragraphs[1].model_copy(
        update={"text": "I built STM32 firmware.", "company_research_ids": []}
    )
    paragraphs[2] = paragraphs[2].model_copy(
        update={"text": "I tested SPI sensor communication.", "company_research_ids": []}
    )
    paragraphs[-1] = paragraphs[-1].model_copy(
        update={
            "text": "Thank you for your consideration.",
            "candidate_evidence_ids": [],
            "company_research_ids": [],
        }
    )
    keyword_only = keyword_only.model_copy(update={"paragraphs": paragraphs})

    result = CoverLetterValidator().validate_output(keyword_only, evidence, research, posting)
    gates = {gate.gate: gate for gate in result.quality_gates}

    assert gates["company_grounding"].status is CoverLetterQualityGateStatus.FAILED
    assert gates["interchangeability"].status is CoverLetterQualityGateStatus.FAILED


def test_long_posting_copy_is_rejected_but_grounded_paraphrase_passes() -> None:
    posting, evidence, research, output = _grounded_case()
    copied = _replace_paragraph_text(
        output,
        0,
        (f"{posting.description} My reviewed firmware work connects to these responsibilities."),
    )

    copied_result = CoverLetterValidator().validate_output(copied, evidence, research, posting)
    paraphrased_result = CoverLetterValidator().validate_output(output, evidence, research, posting)

    copied_claim = next(
        claim
        for claim in copied_result.rejected_claims
        if "copied_posting_language" in claim.codes
    )
    assert copied_claim.paragraph_index == 0
    assert copied_claim.sentence_index == 0
    assert copied_claim.text == posting.description
    assert not any(
        "copied_posting_language" in claim.codes for claim in paraphrased_result.rejected_claims
    )


def test_canonical_senior_posting_title_is_not_an_experience_promotion() -> None:
    profile, posting, plan = cover_letter_case(
        title="Senior Embedded Firmware Engineer",
    )
    evidence, _ = CoverLetterEvidencePortfolio().select(profile, posting, plan)
    research = BoundedCompanyResearchService().research(
        CoverLetterService.default_research_request(posting)
    )
    output = DeterministicCoverLetterComposer().variants(evidence, research, posting)[0]

    result = CoverLetterValidator().validate_output(output, evidence, research, posting)
    integrity = next(gate for gate in result.quality_gates if gate.gate == "narrative_integrity")

    assert integrity.status is CoverLetterQualityGateStatus.PASSED
    assert "unsupported_title_change" not in integrity.detail


def test_canonical_senior_posting_title_cannot_be_claimed_as_experience() -> None:
    profile, posting, plan = cover_letter_case(
        title="Senior Embedded Firmware Engineer",
    )
    evidence, _ = CoverLetterEvidencePortfolio().select(profile, posting, plan)
    research = BoundedCompanyResearchService().research(
        CoverLetterService.default_research_request(posting)
    )
    output = DeterministicCoverLetterComposer().variants(evidence, research, posting)[0]
    unsafe = _replace_paragraph_text(
        output,
        1,
        "As Senior Embedded Firmware Engineer, I built STM32 firmware and tested SPI.",
    )

    result = CoverLetterValidator().validate_output(unsafe, evidence, research, posting)
    integrity = next(gate for gate in result.quality_gates if gate.gate == "narrative_integrity")

    assert integrity.status is CoverLetterQualityGateStatus.FAILED
    assert "unsupported_title_change" in integrity.detail


def test_formulaic_opening_and_closing_are_rejected() -> None:
    posting, evidence, research, output = _grounded_case()
    opening = _replace_paragraph_text(
        output,
        0,
        "I am thrilled to apply for this exciting opportunity at Example Robotics.",
    )
    closing = _replace_paragraph_text(
        output,
        -1,
        "I look forward to the opportunity to make a meaningful impact.",
    )

    opening_result = CoverLetterValidator().validate_output(opening, evidence, research, posting)
    closing_result = CoverLetterValidator().validate_output(closing, evidence, research, posting)

    assert any("formulaic_opening" in claim.codes for claim in opening_result.rejected_claims)
    assert any("formulaic_closing" in claim.codes for claim in closing_result.rejected_claims)


@pytest.mark.parametrize(
    ("text", "expected_code"),
    [
        (
            "I worked across embedded hardware tasks, mechanical, and electrical.",
            "malformed_parallel_list",
        ),
        (
            "SolidWorks mounts and enclosures comes from my integration work.",
            "compound_subject_verb_disagreement",
        ),
        (
            "What interested me was the work behind the intern position.",
            "awkward_posting_frame",
        ),
    ],
)
def test_live_shaped_awkward_grammar_is_rejected(
    text: str,
    expected_code: str,
) -> None:
    posting, evidence, research, output = _grounded_case()
    changed = _replace_paragraph_text(output, 1, text)

    result = CoverLetterValidator().validate_output(changed, evidence, research, posting)

    assert expected_code in {
        code for claim in result.rejected_claims for code in claim.codes
    }


def test_repeated_abstract_thesis_is_detected_across_paragraphs() -> None:
    posting, evidence, research, output = _grounded_case()
    validated = CoverLetterValidator().validate_output(output, evidence, research, posting)
    repeated = [
        paragraph.model_copy(
            update={
                "text": (
                    f"{paragraph.text} Implementation decisions stayed tied to observable "
                    "test behavior in the system."
                )
            }
        )
        for paragraph in validated.paragraphs
    ]

    assert "repeated_narrative_thesis" in (
        CoverLetterValidator._paragraph_progression_codes(repeated)
    )


def test_repeated_vague_hardware_referents_fail_specificity_review() -> None:
    posting, evidence, research, output = _grounded_case()
    validated = CoverLetterValidator().validate_output(output, evidence, research, posting)
    vague = list(validated.paragraphs)
    for index in range(1, len(vague) - 1):
        vague[index] = vague[index].model_copy(
            update={"text": "The hardware made the system useful. That work mattered."}
        )

    codes = CoverLetterValidator._technical_specificity_codes(vague, evidence)

    assert "vague_technical_story" in codes
    assert "repeated_vague_technical_abstraction" in codes


def test_company_and_candidate_provenance_are_preserved_per_paragraph() -> None:
    posting, evidence, research, output = _grounded_case()

    result = CoverLetterValidator().validate_output(output, evidence, research, posting)

    assert all(
        paragraph.candidate_evidence_ids
        for paragraph in result.paragraphs
        if paragraph.purpose
        not in {CoverLetterParagraphPurpose.OPENING, CoverLetterParagraphPurpose.CLOSING}
    )
    assert result.paragraphs[0].company_research_ids
    assert result.paragraphs[-1].company_research_ids
    source_ids = {fact.id for fact in research.facts}
    assert {
        item for paragraph in result.paragraphs for item in paragraph.company_research_ids
    } <= source_ids


@pytest.mark.parametrize(
    "role_family",
    [
        "Embedded systems",
        "Robotics",
        "Firmware",
        "Mechanical engineering",
        "Manufacturing",
        "Backend engineering",
        "Cloud infrastructure",
        "Cybersecurity",
        "Data engineering",
        "AI/ML",
        "Mixed engineering",
        "Adjacent technical engineering",
    ],
)
def test_evidence_portfolio_is_bounded_across_role_families(role_family: str) -> None:
    profile, posting, plan = cover_letter_case(
        title=f"{role_family} Intern",
        description=(
            f"Support {role_family} systems through implementation, testing, data, "
            "and engineering documentation."
        ),
    )

    evidence, diagnostic = CoverLetterEvidencePortfolio().select(profile, posting, plan)

    assert 1 <= len(evidence) <= 6
    assert diagnostic.narrative_thread_count <= 3
    assert set(diagnostic.selected_evidence_ids) == {item.id for item in evidence}


def test_sparse_early_career_profile_uses_available_reviewed_evidence_only() -> None:
    profile, posting, plan = cover_letter_case()
    profile = profile.model_copy(update={"evidence": [profile.evidence[0]]})
    plan = plan.model_copy(update={"profile_version": profile.version})

    evidence, diagnostic = CoverLetterEvidencePortfolio().select(profile, posting, plan)

    assert {item.id for item in evidence} <= {"firmware-evidence"}
    assert diagnostic.considered_evidence_count >= 1


def test_rich_deterministic_letter_is_natural_distinct_and_grounded() -> None:
    profile, posting, plan = rich_cover_letter_case()
    evidence, diagnostic = CoverLetterEvidencePortfolio().select(profile, posting, plan)
    research = BoundedCompanyResearchService().research(
        CoverLetterService.default_research_request(posting)
    )

    output = DeterministicCoverLetterComposer().variants(evidence, research, posting)[-1]
    result = CoverLetterValidator().validate_output(output, evidence, research, posting)
    text = " ".join(paragraph.text for paragraph in result.paragraphs)
    lowered = text.casefold()
    body = result.paragraphs[1:-1]

    assert posting.company_name in text
    assert "the employer" not in lowered
    assert "includes work on act as" not in lowered
    assert "work on working with" not in lowered
    assert all(
        phrase not in lowered
        for phrase in (
            "reviewed evidence",
            "reviewed experience",
            "those records",
            "another reviewed example",
            "without changing the facts or scope",
            "implementation evidence",
        )
    )
    # Sparse source-bound candidates must not be padded with deterministic
    # pseudo-creative prose merely to reach a target length. Exact page-fit
    # validation decides whether this candidate can become an artifact.
    assert 120 <= len(text.split()) <= 425
    assert 4 <= len(result.paragraphs) <= 5
    assert max(len(paragraph.text.split()) for paragraph in result.paragraphs) <= 135
    assert 2 <= diagnostic.narrative_thread_count <= 3
    distinct_threads = []
    for item in evidence:
        if item.entity_id not in {thread.entity_id for thread in distinct_threads}:
            distinct_threads.append(item)
    assert {item.kind for item in distinct_threads} == {
        CoverLetterEvidenceKind.EXPERIENCE,
        CoverLetterEvidenceKind.PROJECT,
    }
    assert len({item for paragraph in body for item in paragraph.candidate_evidence_ids}) == sum(
        len(paragraph.candidate_evidence_ids) for paragraph in body
    )
    assert (
        len([paragraph for paragraph in body if paragraph.candidate_evidence_ids])
        == diagnostic.narrative_thread_count
    )
    assert "STM32" in text
    assert "sensor" in lowered
    assert "actuator" in lowered
    assert "worked directly with the hardware" not in lowered
    assert "same technical problem" not in lowered
    assert "separate constraint joined" not in lowered
    assert not result.rejected_claims
    assert all(
        claim.status is CoverLetterValidationStatus.SUPPORTED
        for paragraph in result.paragraphs
        for claim in paragraph.claims
    )
    assert not [
        gate for gate in result.quality_gates if gate.status is CoverLetterQualityGateStatus.FAILED
    ]


def test_sparse_evidence_remains_concise_without_internal_language() -> None:
    profile, posting, plan = cover_letter_case()
    profile = profile.model_copy(update={"evidence": profile.evidence[:2]})
    evidence, _ = CoverLetterEvidencePortfolio().select(profile, posting, plan)
    research = BoundedCompanyResearchService().research(
        CoverLetterService.default_research_request(posting)
    )

    output = DeterministicCoverLetterComposer().variants(evidence, research, posting)[0]
    result = CoverLetterValidator().validate_output(output, evidence, research, posting)
    text = " ".join(paragraph.text for paragraph in result.paragraphs)

    assert len(text.split()) < 350
    assert "reviewed" not in text.casefold()
    assert not result.rejected_claims


def test_internal_application_language_is_rejected_as_employer_facing_prose() -> None:
    posting, evidence, research, output = _grounded_case()
    invalid = _replace_paragraph_text(
        output,
        1,
        (
            "My reviewed experience is implementation evidence that connects those records "
            "without changing the facts or scope."
        ),
    )

    result = CoverLetterValidator().validate_output(invalid, evidence, research, posting)

    assert any("internal_application_language" in claim.codes for claim in result.rejected_claims)


def test_manual_bad_letter_shape_is_rejected_with_synthetic_content() -> None:
    posting, evidence, research, output = _grounded_case()
    paragraphs = list(output.paragraphs)
    paragraphs[0] = paragraphs[0].model_copy(
        update={
            "text": (
                "The Embedded Firmware Intern role at the employer includes work on Act as "
                "the primary technical liaison."
            )
        }
    )
    paragraphs[1] = paragraphs[1].model_copy(
        update={
            "text": (
                "My reviewed experience uses STM32 firmware. Those records connect STM32 "
                "firmware to STM32 firmware."
            )
        }
    )
    if len(paragraphs) > 2:
        paragraphs[2] = paragraphs[2].model_copy(
            update={
                "text": (
                    "Another reviewed example repeats STM32 firmware and implementation evidence."
                ),
                "candidate_evidence_ids": list(paragraphs[1].candidate_evidence_ids),
            }
        )
    paragraphs[-1] = paragraphs[-1].model_copy(update={"text": "Thank you."})

    result = CoverLetterValidator().validate_output(
        output.model_copy(update={"paragraphs": paragraphs}),
        evidence,
        research,
        posting,
    )
    rejection_codes = {code for claim in result.rejected_claims for code in claim.codes}

    assert "available_company_name_replaced_by_placeholder" in rejection_codes
    assert "ungrammatical_posting_fragment" in rejection_codes
    assert "internal_application_language" in rejection_codes
    assert "incomplete_closing" in rejection_codes


def test_reusing_one_evidence_mechanism_across_body_paragraphs_is_rejected() -> None:
    posting, evidence, research, output = _grounded_case()
    paragraphs = list(output.paragraphs)
    paragraphs[2] = paragraphs[1].model_copy(
        update={
            "purpose": CoverLetterParagraphPurpose.CONTRIBUTION,
            "narrative_thread_id": "duplicated-mechanism",
        }
    )

    result = CoverLetterValidator().validate_output(
        output.model_copy(update={"paragraphs": paragraphs}),
        evidence,
        research,
        posting,
    )

    assert any(
        gate.code == "repetitive_paragraph_structure"
        and gate.status is CoverLetterQualityGateStatus.FAILED
        for gate in result.quality_gates
    )


def test_likely_title_spelling_inconsistency_warns_without_rewriting() -> None:
    posting, evidence, research, output = _grounded_case()
    evidence[0] = evidence[0].model_copy(update={"entry_title": "Principle Hardware Engineer"})

    result = CoverLetterValidator().validate_output(output, evidence, research, posting)
    gate = next(item for item in result.quality_gates if item.gate == "profile_title_consistency")

    assert gate.status is CoverLetterQualityGateStatus.REVIEW_REQUIRED
    assert gate.code == "possible_title_spelling_inconsistency"
    assert evidence[0].entry_title == "Principle Hardware Engineer"
