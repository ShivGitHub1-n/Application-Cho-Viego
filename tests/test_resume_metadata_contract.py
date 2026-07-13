from resume_tailor.application.composition import DeterministicCompositionReconciler
from resume_tailor.domain.models import (
    CompositionSelection,
    EducationRecord,
    EntityKind,
    EvidenceItem,
    JobPosting,
    MasterProfile,
    ResumeItem,
    TechnicalSkillCategory,
    TemplateConstraints,
)
from resume_tailor.infrastructure.optimization import (
    DeterministicResumeOptimizer,
    EvidenceBoundResumeWriter,
)


def _profile() -> MasterProfile:
    return MasterProfile(
        id="metadata-profile",
        user_id="metadata-user",
        display_name="Avery Engineer",
        education=[
            EducationRecord(
                school="University of Waterloo",
                program="BASc, Mechatronics Engineering",
                start_date="Sep 2022",
                expected_graduation_date="Apr 2027",
                location="Waterloo, ON",
                gpa="3.9/4.0",
                awards=["President's Scholarship"],
                relevant_coursework=["Embedded Systems", "Control Systems"],
            )
        ],
        technical_skills=[
            TechnicalSkillCategory(category="Languages", values=["C", "Python"]),
            TechnicalSkillCategory(category="Hardware", values=["STM32", "SPI"]),
        ],
        experiences=[
            ResumeItem(
                id="firmware",
                title="Firmware Intern",
                kind=EntityKind.EXPERIENCE,
                organization="Acme Robotics",
                start_date="May 2025",
                end_date="Aug 2025",
                location="Toronto, ON",
                subtitle="Embedded Systems",
                technology_label="C, STM32",
            )
        ],
        projects=[
            ResumeItem(
                id="rover",
                title="Autonomous Rover",
                kind=EntityKind.PROJECT,
                start_date="Jan 2025",
                end_date="Apr 2025",
                technology_label="Python, ROS 2",
            )
        ],
        evidence=[
            EvidenceItem(
                id="firmware-1",
                entity_id="firmware",
                source_text="Developed STM32 firmware for SPI sensors.",
                technologies=["STM32", "SPI"],
            ),
            EvidenceItem(
                id="firmware-2",
                entity_id="firmware",
                source_text="Validated embedded firmware on hardware.",
                technologies=["firmware"],
            ),
            EvidenceItem(
                id="rover-1",
                entity_id="rover",
                source_text="Built autonomous rover software using Python and ROS 2.",
                technologies=["Python", "ROS 2"],
            ),
        ],
    )


def test_complete_baseline_and_selected_entry_metadata_survive_to_structured_resume() -> None:
    profile = _profile()
    plan = DeterministicResumeOptimizer().create_plan(
        profile,
        JobPosting(
            id="posting",
            title="Embedded Firmware Engineer",
            description="Develop STM32 SPI firmware and Python ROS autonomous systems.",
        ),
        TemplateConstraints(max_total_lines=30, max_experience_lines=15, max_project_lines=15),
    )
    resume = EvidenceBoundResumeWriter().write(plan, profile, set())

    assert resume.education == profile.education
    assert resume.education[0].awards == ["President's Scholarship"]
    assert resume.education[0].relevant_coursework == ["Embedded Systems", "Control Systems"]
    assert resume.technical_skills == plan.technical_skills
    assert [category.category for category in resume.technical_skills] == [
        category.category for category in plan.technical_skills
    ]
    assert [category.values for category in resume.technical_skills] == [
        category.values for category in plan.technical_skills
    ]
    plan_skills_by_label = {
        category.category: category for category in plan.technical_skills
    }
    resume_skills_by_label = {
        category.category: category for category in resume.technical_skills
    }
    for label in ("Hardware", "Languages"):
        if label in plan_skills_by_label:
            assert resume_skills_by_label[label] == plan_skills_by_label[label]
    assert resume.experiences[0].organization == "Acme Robotics"
    assert resume.experiences[0].location == "Toronto, ON"
    assert (resume.experiences[0].start_date, resume.experiences[0].end_date) == (
        "May 2025",
        "Aug 2025",
    )
    assert resume.experiences[0].subtitle == "Embedded Systems"
    assert resume.projects[0].title == "Autonomous Rover"
    assert resume.projects[0].technology_label == "Python, ROS 2"
    assert resume.projects[0].end_date == "Apr 2025"


def test_composition_changes_bullets_without_deleting_entry_or_baseline_metadata() -> None:
    profile = _profile()
    optimizer = DeterministicResumeOptimizer()
    plan = optimizer.create_plan(
        profile,
        JobPosting(
            id="posting",
            title="Embedded Firmware Engineer",
            description="Develop and validate STM32 SPI embedded firmware.",
        ),
        TemplateConstraints(max_total_lines=20, max_experience_lines=15),
    )
    reconciled = DeterministicCompositionReconciler().reconcile(
        plan,
        profile,
        CompositionSelection(
            selected_entry_ids=["firmware"],
            selected_evidence_ids=["firmware-2"],
            rationale="Use the validation bullet.",
        ),
    )
    resume = EvidenceBoundResumeWriter().write(reconciled, profile, set())

    assert reconciled.selected_claim_ids == ["firmware-2"]
    assert [bullet.id for bullet in resume.experience_bullets["firmware"]] == ["firmware-2"]
    assert resume.experiences == [profile.experiences[0]]
    assert resume.education == profile.education
    assert resume.technical_skills == reconciled.technical_skills
