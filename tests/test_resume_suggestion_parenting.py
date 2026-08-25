from resume_tailor.application.llm_services import HybridLlmServices
from resume_tailor.domain.hybrid_resume import (
    BulletLengthClass,
    BulletValidationStatus,
    BulletVariantRecord,
    ClaimValidationStatus,
    GroundedClaim,
)
from resume_tailor.domain.models import (
    EntityKind,
    EvidenceItem,
    MasterProfile,
    ResumeItem,
    ResumeStrategy,
    StructuredResume,
)
from resume_tailor.domain.requirement_ranking import EvidenceRelationship
from resume_tailor.domain.resume_composition import (
    BulletLineFitDiagnostic,
    LineFitVerificationStatus,
)


def _variant(entry_id: str, evidence_id: str) -> BulletVariantRecord:
    text = "Built a reviewed automation controller for repeatable testing."
    return BulletVariantRecord(
        variant_id="approved-omitted-suggestion",
        entry_id=entry_id,
        source_evidence_ids=[evidence_id],
        original_reviewed_text=["Built an automation challenge project."],
        rewritten_text=text,
        factual_claims=[
            GroundedClaim(
                text=text,
                supporting_evidence_ids=[evidence_id],
                validation_status=ClaimValidationStatus.REVIEW_REQUIRED,
                reason="Supported inference awaiting review.",
            )
        ],
        relationship_tier=EvidenceRelationship.DIRECT,
        intended_length_class=BulletLengthClass.STANDARD_ONE_TO_TWO_LINES,
        provider="fixture",
        model="fixture",
        validation_status=BulletValidationStatus.REVIEW_REQUIRED,
        line_fit=BulletLineFitDiagnostic(
            verification_status=LineFitVerificationStatus.ESTIMATED,
            expected_line_count=1,
            expected_final_line_word_count=7,
            expected_final_line_width_ratio=0.7,
            total_vertical_line_cost=1,
            awkward_wrap_risk=False,
            three_line_risk=False,
            future_rewrite_recommended=False,
        ),
        material_improvement=True,
    )


def test_approved_omitted_suggestion_adds_only_its_canonical_parent() -> None:
    experience = ResumeItem(
        id="experience-one", title="Embedded Intern", kind=EntityKind.EXPERIENCE
    )
    omitted_project = ResumeItem(
        id="project-two", title="Automation Challenge", kind=EntityKind.PROJECT
    )
    profile = MasterProfile(
        id="profile",
        user_id="user",
        display_name="Candidate",
        experiences=[experience],
        projects=[omitted_project],
        evidence=[
            EvidenceItem(
                id="evidence-project-two",
                entity_id="project-two",
                source_text="Built an automation challenge project.",
            )
        ],
    )
    resume = StructuredResume(
        profile_id=profile.id,
        profile_version=profile.version,
        posting_id="posting",
        template_id="managed-engineering-v1",
        display_name=profile.display_name,
        strategy=ResumeStrategy(
            role_family="general",
            primary_focus="Automation",
            rationale="Use reviewed automation evidence.",
        ),
        experiences=[experience],
        entity_titles={experience.id: experience.title},
    )
    variant = _variant("project-two", "evidence-project-two")

    updated = HybridLlmServices._apply_variants(
        resume,
        [variant],
        {variant.variant_id},
        profile,
    )

    assert [item.id for item in updated.projects] == ["project-two"]
    assert updated.entity_titles["project-two"] == "Automation Challenge"
    assert updated.project_bullets["project-two"][0].id == variant.variant_id
    assert "project-two" not in updated.experience_bullets
    assert updated.review_pending_bullets == []
    assert updated.review_required_claim_ids == []


def test_approved_suggestion_cannot_cross_attach_to_another_parent() -> None:
    project = ResumeItem(id="project-two", title="Automation", kind=EntityKind.PROJECT)
    profile = MasterProfile(
        id="profile",
        user_id="user",
        display_name="Candidate",
        projects=[project],
        evidence=[
            EvidenceItem(
                id="owned-evidence",
                entity_id="project-two",
                source_text="Built a reviewed automation project.",
            )
        ],
    )
    resume = StructuredResume(
        profile_id=profile.id,
        profile_version=profile.version,
        posting_id="posting",
        template_id="managed-engineering-v1",
        display_name=profile.display_name,
        strategy=ResumeStrategy(
            role_family="general",
            primary_focus="Automation",
            rationale="Use reviewed evidence.",
        ),
    )
    mismatched = _variant("project-two", "not-owned-evidence")

    updated = HybridLlmServices._apply_variants(
        resume,
        [mismatched],
        {mismatched.variant_id},
        profile,
    )

    assert updated.projects == []
    assert updated.project_bullets == {}
