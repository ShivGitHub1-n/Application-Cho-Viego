import json
from pathlib import Path

from resume_tailor.application.services import TailorResumeService
from resume_tailor.domain.models import (
    ClaimCandidate,
    ClaimComposition,
    ClaimSupport,
    EntityKind,
    EvidenceItem,
    JobPosting,
    MasterProfile,
    ProfileFitStatus,
    ResumeItem,
    RoleFamily,
    TemplateConstraints,
)
from resume_tailor.infrastructure.optimization import DeterministicResumeOptimizer, EvidenceBoundResumeWriter


def _profile() -> MasterProfile:
    return MasterProfile(
        id="profile-1",
        user_id="user-1",
        display_name="Avery Engineer",
        experiences=[
            ResumeItem(id="experience-1", title="Firmware Intern", kind=EntityKind.EXPERIENCE),
            ResumeItem(id="experience-2", title="Software Volunteer", kind=EntityKind.EXPERIENCE),
        ],
        projects=[ResumeItem(id="project-1", title="Web Portfolio", kind=EntityKind.PROJECT)],
        coursework=["Embedded Systems", "Digital Logic"],
        evidence=[
            EvidenceItem(
                id="evidence-1",
                entity_id="experience-1",
                source_text="Developed STM32 firmware and validated SPI sensor communication during hardware debugging.",
                technologies=["STM32", "C", "SPI"],
                capabilities=["embedded debugging", "hardware integration"],
            ),
            EvidenceItem(
                id="evidence-2",
                entity_id="experience-2",
                source_text="Built a small internal scheduling dashboard for volunteers.",
                technologies=["Python"],
            ),
            EvidenceItem(
                id="evidence-3",
                entity_id="project-1",
                source_text="Created a personal portfolio website.",
                technologies=["JavaScript"],
            ),
        ],
    )


def _posting() -> JobPosting:
    return JobPosting(
        id="posting-1",
        title="Embedded Firmware Intern",
        description="Develop and test embedded firmware for STM32 microcontrollers and SPI-connected sensors.",
    )


def _fixture(name: str) -> dict[str, object]:
    path = Path(__file__).parent / "fixtures" / name
    return json.loads(path.read_text(encoding="utf-8"))


def test_optimizer_prioritizes_relevant_evidence_with_entry_cost() -> None:
    plan = DeterministicResumeOptimizer().create_plan(
        _profile(),
        _posting(),
        TemplateConstraints(max_total_lines=5, max_experience_lines=4, max_project_lines=3),
    )

    assert plan.strategy is not None
    assert plan.strategy.primary_focus == "embedded firmware development"
    assert "evidence-1" in plan.selected_claim_ids
    assert "project-1" not in plan.selected_entity_ids
    assert any(decision.action == "removed" and decision.entity_id == "project-1" for decision in plan.report.decisions)


def test_optimizer_returns_insufficient_fit_only_when_direct_evidence_is_missing() -> None:
    profile = MasterProfile(
        id="profile-mismatch",
        user_id="user-1",
        display_name="Avery Engineer",
        experiences=[ResumeItem(id="experience-circuit", title="Circuit Assistant", kind=EntityKind.EXPERIENCE)],
        evidence=[
            EvidenceItem(
                id="evidence-circuit",
                entity_id="experience-circuit",
                source_text="Assembled a comparator circuit on a breadboard.",
                technologies=["Comparator"],
            )
        ],
    )
    posting = JobPosting(id="posting-data", title="Data Engineering Intern", description="Build Python ETL pipelines.")

    plan = DeterministicResumeOptimizer().create_plan(profile, posting, TemplateConstraints())

    assert plan.report.role.supported is True
    assert plan.report.profile_fit is not None
    assert plan.report.profile_fit.status == ProfileFitStatus.INSUFFICIENT
    assert plan.strategy is None


def test_huawei_posting_is_accepted_with_limited_profile_fit() -> None:
    profile = MasterProfile.model_validate(_fixture("huawei_profile.json"))
    posting = JobPosting.model_validate(_fixture("huawei_autonomous_research_posting.json"))

    plan = DeterministicResumeOptimizer().create_plan(profile, posting, TemplateConstraints())

    assert plan.strategy is not None
    assert plan.report.role.role_family == RoleFamily.AI_ML_MULTIMODAL.value
    assert plan.report.profile_fit is not None
    assert plan.report.profile_fit.status == ProfileFitStatus.LIMITED
    assert "evidence-perception" in plan.selected_claim_ids
    assert {"PyTorch", "Jupyter"}.issubset(plan.selected_skills)
    assert all("PyTorch" not in claim.text and "Jupyter" not in claim.text for claim in plan.claim_candidates)
    assert "deep learning and transformer research" in plan.report.profile_fit.material_gaps
    assert "vision-language or vision-language-action models" in plan.report.profile_fit.material_gaps


def test_entry_overhead_prefers_coherent_exl_package_over_marginal_telebotics_entry() -> None:
    profile = MasterProfile(
        id="profile-entry-cost",
        user_id="user-1",
        display_name="Candidate",
        experiences=[
            ResumeItem(id="telebotics", title="Telebotics", kind=EntityKind.EXPERIENCE),
            ResumeItem(id="exl", title="EXL", kind=EntityKind.EXPERIENCE),
        ],
        evidence=[
            EvidenceItem(
                id="telebotics-1",
                entity_id="telebotics",
                source_text="Supported an autonomous driving integration prototype.",
                capabilities=["autonomous systems"],
            ),
            EvidenceItem(
                id="exl-1",
                entity_id="exl",
                source_text="Developed multi-agent AI workflows for enterprise generative AI systems.",
                capabilities=["multi-agent systems"],
            ),
            EvidenceItem(
                id="exl-2",
                entity_id="exl",
                source_text="Implemented compliance auditing and AI governance evaluation controls.",
                capabilities=["AI governance"],
            ),
        ],
    )
    posting = JobPosting(
        id="posting-entry-cost",
        title="Multimodal AI Research Intern",
        description="Work on multimodal reasoning, autonomous driving, multi-agent AI, and compliance auditing.",
    )

    plan = DeterministicResumeOptimizer().create_plan(
        profile,
        posting,
        TemplateConstraints(max_total_lines=4, max_experience_lines=4, max_project_lines=1),
    )

    assert plan.selected_entity_ids == ["exl"]
    assert set(plan.selected_claim_ids) == {"exl-1", "exl-2"}
    assert "telebotics" not in plan.selected_entity_ids


def test_one_bullet_entry_is_selected_when_it_uniquely_covers_a_role_signal() -> None:
    profile = MasterProfile(
        id="profile-unique",
        user_id="user-1",
        display_name="Candidate",
        experiences=[ResumeItem(id="perception", title="Perception Intern", kind=EntityKind.EXPERIENCE)],
        evidence=[
            EvidenceItem(
                id="lidar-evidence",
                entity_id="perception",
                source_text="Integrated LiDAR sensors for environmental perception.",
                technologies=["LiDAR"],
                capabilities=["computer vision"],
            )
        ],
    )
    posting = JobPosting(id="posting-perception", title="Perception Intern", description="Develop LiDAR perception systems.")

    plan = DeterministicResumeOptimizer().create_plan(profile, posting, TemplateConstraints(max_total_lines=3))

    assert plan.selected_entity_ids == ["perception"]
    assert plan.selected_claim_ids == ["lidar-evidence"]


def test_combined_candidate_keeps_same_entry_evidence_and_original_text() -> None:
    first_text = "Built ROS 2 teleoperation controls."
    second_text = "Tested ROS 2 safety override controls."
    profile = MasterProfile(
        id="profile-combine",
        user_id="user-1",
        display_name="Candidate",
        experiences=[ResumeItem(id="autonomy", title="Autonomy Intern", kind=EntityKind.EXPERIENCE)],
        evidence=[
            EvidenceItem(
                id="combine-1",
                entity_id="autonomy",
                source_text=first_text,
                technologies=["ROS 2"],
                capabilities=["teleoperation"],
            ),
            EvidenceItem(
                id="combine-2",
                entity_id="autonomy",
                source_text=second_text,
                technologies=["ROS 2"],
                capabilities=["teleoperation"],
            ),
        ],
    )
    posting = JobPosting(id="posting-combine", title="Autonomy Intern", description="Build ROS 2 teleoperation systems.")

    plan = DeterministicResumeOptimizer().create_plan(profile, posting, TemplateConstraints(max_total_lines=3))

    combined = next(candidate for candidate in plan.claim_candidates if candidate.composition == ClaimComposition.COMBINED)
    assert combined.evidence_ids == ["combine-1", "combine-2"]
    assert first_text in combined.text
    assert second_text in combined.text
    assert combined.max_rendered_lines == 2


def test_writer_excludes_unapproved_inferred_claims() -> None:
    profile = _profile()
    service = TailorResumeService(DeterministicResumeOptimizer(), EvidenceBoundResumeWriter())
    plan = service.create_plan(profile, _posting(), TemplateConstraints(max_total_lines=5, max_experience_lines=4))
    inferred = ClaimCandidate(
        id="inference-1",
        entity_id="experience-1",
        text="Applied embedded IDE workflows.",
        evidence_ids=["evidence-1"],
        support=ClaimSupport.STRONG_INFERENCE_PENDING_REVIEW,
        estimated_lines=1,
    )
    plan = plan.model_copy(update={"claim_candidates": [*plan.claim_candidates, inferred]})

    writer = EvidenceBoundResumeWriter()
    unapproved = writer.write(plan, profile, set())
    approved = writer.write(plan, profile, {"inference-1"})

    assert "inference-1" in unapproved.review_required_claim_ids
    assert all(
        bullet.id != "inference-1"
        for bullets in unapproved.experience_bullets.values()
        for bullet in bullets
    )
    assert any(
        bullet.id == "inference-1"
        for bullets in approved.experience_bullets.values()
        for bullet in bullets
    )
