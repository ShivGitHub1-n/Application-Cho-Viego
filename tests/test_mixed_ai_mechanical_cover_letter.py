from __future__ import annotations

import re

from resume_tailor.application.company_research import BoundedCompanyResearchService
from resume_tailor.application.cover_letter import CoverLetterService
from resume_tailor.application.cover_letter_evidence import CoverLetterEvidencePortfolio
from resume_tailor.application.cover_letter_validation import (
    CoverLetterValidator,
    DeterministicCoverLetterComposer,
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
from resume_tailor.infrastructure.optimization import DeterministicResumeOptimizer


def _mixed_role_case():
    profile = MasterProfile(
        id="mixed-design-profile",
        user_id="synthetic-user",
        display_name="Alex Candidate",
        experiences=[
            ResumeItem(
                id="governance-entry",
                title="AI Risk Analyst",
                kind=EntityKind.EXPERIENCE,
            ),
            ResumeItem(
                id="reporting-entry",
                title="Reporting Analyst",
                kind=EntityKind.EXPERIENCE,
            ),
        ],
        projects=[
            ResumeItem(
                id="robotic-assembly-entry",
                title="Robotic Assembly Prototype",
                kind=EntityKind.PROJECT,
            ),
            ResumeItem(
                id="manufacturing-entry",
                title="Manufacturing Prototype",
                kind=EntityKind.PROJECT,
            ),
            ResumeItem(
                id="ai-design-entry",
                title="Mechanical AI Prototype",
                kind=EntityKind.PROJECT,
            ),
        ],
        evidence=[
            EvidenceItem(
                id="robotic-cad",
                entity_id="robotic-assembly-entry",
                source_text=(
                    "Designed CAD and CAM mechanical assemblies and modeled kinematics "
                    "for a robotic arm."
                ),
                technologies=["CAD", "CAM", "kinematics"],
                capabilities=["mechanical assembly design"],
            ),
            EvidenceItem(
                id="robotic-analysis",
                entity_id="robotic-assembly-entry",
                source_text=(
                    "Developed Python and MATLAB simulations for robotic motion and "
                    "systems trade-offs."
                ),
                technologies=["Python", "MATLAB"],
                capabilities=["simulation", "systems engineering"],
            ),
            EvidenceItem(
                id="manufacturing-dfm",
                entity_id="manufacturing-entry",
                source_text=(
                    "Built fabricated prototypes using DFM and DFA and documented "
                    "manufacturing trade-offs."
                ),
                technologies=["DFM", "DFA", "fabrication"],
                capabilities=["manufacturing"],
            ),
            EvidenceItem(
                id="manufacturing-fragment",
                entity_id="manufacturing-entry",
                source_text="Owned the complete BOM",
                technologies=["BOM"],
                capabilities=["manufacturing"],
            ),
            EvidenceItem(
                id="ai-prototype",
                entity_id="ai-design-entry",
                source_text=(
                    "Integrated machine learning into Python prototypes for mechanical "
                    "design simulation."
                ),
                technologies=["Python", "machine learning"],
                capabilities=["AI prototyping", "mechanical design"],
            ),
            EvidenceItem(
                id="unrelated-governance",
                entity_id="governance-entry",
                source_text=(
                    "Evaluated generative AI governance controls and security testing reports."
                ),
                technologies=["generative AI"],
                capabilities=["governance", "security testing"],
            ),
            EvidenceItem(
                id="unrelated-reporting",
                entity_id="reporting-entry",
                source_text="Built sales dashboards and managed procurement reporting costs.",
                technologies=["business intelligence"],
                capabilities=["reporting", "procurement"],
            ),
        ],
    )
    posting = JobPosting(
        id="mixed-design-posting",
        title="AI Mechanical Design Engineer",
        company_name="Northwind Design Lab",
        description=(
            "Develop AI and machine learning methods for CAD and CAM mechanical assembly "
            "design. Perform kinematic analysis, DFM and DFA, fabrication and manufacturing. "
            "Prototype in Python and MATLAB, run simulation and systems engineering trade-offs "
            "with research teams."
        ),
    )
    plan = DeterministicResumeOptimizer().create_plan(
        profile,
        posting,
        TemplateConstraints(max_experience_lines=8, max_project_lines=6),
    )
    research = BoundedCompanyResearchService().research(
        CoverLetterService.default_research_request(posting)
    )
    evidence, diagnostic = CoverLetterEvidencePortfolio().select(profile, posting, plan)
    output = DeterministicCoverLetterComposer().variants(evidence, research, posting)[-1]
    validated = CoverLetterValidator().validate_output(output, evidence, research, posting)
    return posting, research, evidence, diagnostic, output, validated


def test_mixed_ai_mechanical_narrative_prioritizes_direct_threads_deterministically() -> None:
    posting, research, evidence, diagnostic, output, validated = _mixed_role_case()
    selected_ids = set(diagnostic.selected_evidence_ids)
    text = " ".join(paragraph.text for paragraph in output.paragraphs)
    lowered = text.casefold()

    assert {
        "robotic-cad",
        "robotic-analysis",
        "manufacturing-dfm",
        "ai-prototype",
    } <= selected_ids
    assert {"unrelated-governance", "unrelated-reporting"}.isdisjoint(selected_ids)
    assert len(output.paragraphs) == 4
    assert 270 <= len(text.split()) <= 425
    assert posting.company_name in text
    assert "your organization" not in lowered
    assert all(
        term in lowered
        for term in (
            "cad",
            "cam",
            "kinematic",
            "dfm",
            "dfa",
            "python",
            "matlab",
            "machine learning",
            "manufactur",
        )
    )
    assert not any(
        phrase in lowered
        for phrase in (
            "i also worked with",
            "the work included",
            "another responsibility involved",
        )
    )
    assert not re.search(r"(?:^|[.!?]\s+)Owned the complete BOM", text)
    assert "Lead " not in text and "Senior " not in text
    assert "master's" not in lowered and "master degree" not in lowered
    assert not validated.rejected_claims
    assert not [
        gate
        for gate in validated.quality_gates
        if gate.status is CoverLetterQualityGateStatus.FAILED
    ]

    repeated = DeterministicCoverLetterComposer().variants(evidence, research, posting)[-1]
    assert repeated == output


def test_malformed_fragments_templates_and_known_company_placeholder_block_export() -> None:
    posting, research, evidence, _, output, _ = _mixed_role_case()
    paragraphs = list(output.paragraphs)
    paragraphs[0] = paragraphs[0].model_copy(
        update={
            "text": "I am applying for this role at your organization.",
            "source_bound_sentences": [],
        }
    )
    paragraphs[1] = paragraphs[1].model_copy(
        update={
            "text": (
                "Owned the complete BOM. I also worked with CAD. I also worked with Python. "
                "The position's emphasis on work on alongside cross functional teams was useful."
            ),
            "source_bound_sentences": [],
        }
    )
    malformed = output.model_copy(update={"paragraphs": paragraphs})

    validated = CoverLetterValidator().validate_output(
        malformed,
        evidence,
        research,
        posting,
    )
    integrity = next(
        gate for gate in validated.quality_gates if gate.gate == "narrative_integrity"
    )

    assert integrity.status is CoverLetterQualityGateStatus.FAILED
    assert "known_company_replaced_by_placeholder" in integrity.detail
    assert "malformed_posting_fragment" in integrity.detail
    assert "sentence_fragment" in integrity.detail
    assert "repetitive_narrative_template" in integrity.detail
    assert not CoverLetterService._required_content_gates_pass(validated.quality_gates)


def test_title_degree_and_unsupported_claims_remain_blocked_by_content_gates() -> None:
    posting, research, evidence, _, output, _ = _mixed_role_case()
    paragraphs = list(output.paragraphs)
    paragraphs[1] = paragraphs[1].model_copy(
        update={
            "text": (
                "As Lead Mechatronics Engineer, I directed an enterprise program after "
                "completing a Master's degree."
            ),
            "source_bound_sentences": [],
        }
    )
    unsafe = output.model_copy(update={"paragraphs": paragraphs})

    validated = CoverLetterValidator().validate_output(
        unsafe,
        evidence,
        research,
        posting,
    )
    integrity = next(
        gate for gate in validated.quality_gates if gate.gate == "narrative_integrity"
    )

    assert integrity.status is CoverLetterQualityGateStatus.FAILED
    assert "unsupported_title_change" in integrity.detail
    assert "unsupported_degree_qualification" in integrity.detail
    assert not CoverLetterService._required_content_gates_pass(validated.quality_gates)
