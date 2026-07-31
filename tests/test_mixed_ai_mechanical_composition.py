from __future__ import annotations

from resume_tailor.application.resume_composition import (
    CompositionSearchBounds,
    DeterministicResumeComposer,
)
from resume_tailor.domain.layout import PageUtilizationStatus
from resume_tailor.domain.models import (
    JobPosting,
    MasterProfile,
    ResumeStrategy,
    StructuredResume,
    TemplateConstraints,
)
from resume_tailor.domain.resume_composition import PageFitEvaluation


class _OnePageBulletBudget:
    def __init__(self, maximum_bullets: int = 8) -> None:
        self.maximum_bullets = maximum_bullets

    def evaluate(
        self,
        resume: StructuredResume,
        *,
        attempt_exact: bool = True,
    ) -> PageFitEvaluation:
        bullet_count = sum(
            len(bullets)
            for section in (resume.experience_bullets, resume.project_bullets)
            for bullets in section.values()
        )
        utilization = min(1.2, 0.44 + (bullet_count * 0.07))
        fits = bullet_count <= self.maximum_bullets
        return PageFitEvaluation(
            status=(
                PageUtilizationStatus.ACCEPTABLE_ONE_PAGE
                if fits
                else PageUtilizationStatus.OVERFLOW
            ),
            page_count=1 if fits else 2,
            exact=attempt_exact,
            provider="synthetic exact one-page bullet budget",
            utilization_ratio=utilization,
            fits_one_page=fits,
        )

    def evaluate_batch(self, resumes: list[StructuredResume]) -> list[PageFitEvaluation]:
        return [self.evaluate(resume) for resume in resumes]


def _profile() -> MasterProfile:
    return MasterProfile.model_validate(
        {
            "id": "mixed-engineering-profile",
            "user_id": "synthetic-user",
            "display_name": "Jordan Candidate",
            "experiences": [
                {
                    "id": "vehicle-controls",
                    "title": "Vehicle Controls Developer",
                    "kind": "experience",
                },
                {"id": "ai-security", "title": "AI Security Researcher", "kind": "experience"},
                {
                    "id": "finance-governance",
                    "title": "AI Governance Analyst",
                    "kind": "experience",
                },
                {"id": "sales-reporting", "title": "Sales Data Analyst", "kind": "experience"},
            ],
            "projects": [
                {
                    "id": "robotic-assembly",
                    "title": "Robotic Assembly Design and AI Prototype",
                    "kind": "project",
                    "technologies": ["Python", "MATLAB", "CAD", "CAM"],
                    "capabilities": [
                        "kinematic analysis",
                        "mechanical assembly design",
                        "design for manufacturing",
                        "systems engineering",
                    ],
                }
            ],
            "technical_skills": [
                {
                    "id": "numerical-tools",
                    "category": "Programming & Numerical Prototyping",
                    "values": ["Python", "MATLAB", "USB)"],
                },
                {
                    "id": "mechanical-design",
                    "category": "Mechanical Design & Manufacturing",
                    "values": [
                        "CAD",
                        "CAM",
                        "Mechanical Assembly Design",
                        "Kinematics",
                        "DFM/DFA",
                        "Fabrication",
                    ],
                },
                {
                    "id": "ai-systems",
                    "category": "AI, Simulation & Systems",
                    "values": [
                        "Machine Learning Prototyping",
                        "Simulation",
                        "Systems Engineering",
                    ],
                },
                {
                    "id": "business-reporting",
                    "category": "Business Reporting",
                    "values": ["Power BI", "Sales Reporting"],
                },
            ],
            "evidence": [
                {
                    "id": "assembly-cad",
                    "entity_id": "robotic-assembly",
                    "source_text": (
                        "Designed CAD mechanical assemblies and CAM-ready component interfaces."
                    ),
                    "technologies": ["CAD", "CAM"],
                    "capabilities": ["mechanical assembly design"],
                },
                {
                    "id": "assembly-kinematics",
                    "entity_id": "robotic-assembly",
                    "source_text": (
                        "Performed MATLAB kinematic analysis for a multi-axis robotic assembly."
                    ),
                    "technologies": ["MATLAB"],
                    "capabilities": ["kinematic analysis", "robotics"],
                },
                {
                    "id": "assembly-manufacturing",
                    "entity_id": "robotic-assembly",
                    "source_text": (
                        "Applied DFM/DFA trade-offs and fabricated prototype components "
                        "for assembly testing."
                    ),
                    "technologies": ["DFM/DFA"],
                    "capabilities": ["fabrication", "design for manufacturing"],
                },
                {
                    "id": "assembly-ai",
                    "entity_id": "robotic-assembly",
                    "source_text": (
                        "Built a Python machine-learning prototype to evaluate mechanical "
                        "design alternatives."
                    ),
                    "technologies": ["Python", "Machine Learning"],
                    "capabilities": ["AI prototyping", "mechanical design"],
                },
                {
                    "id": "assembly-systems",
                    "entity_id": "robotic-assembly",
                    "source_text": (
                        "Evaluated systems trade-offs across mechanisms, sensing, controls, "
                        "and manufacturability."
                    ),
                    "capabilities": ["systems engineering", "simulation"],
                },
                {
                    "id": "assembly-research",
                    "entity_id": "robotic-assembly",
                    "source_text": (
                        "Coordinated cross-functional research and iterative prototype development."
                    ),
                    "capabilities": ["prototype development"],
                },
                {
                    "id": "controls-throttle",
                    "entity_id": "vehicle-controls",
                    "source_text": "Implemented throttle and braking controls for a test vehicle.",
                },
                {
                    "id": "controls-teleoperation",
                    "entity_id": "vehicle-controls",
                    "source_text": "Validated teleoperation commands and remote control testing.",
                },
                {
                    "id": "security-evaluation",
                    "entity_id": "ai-security",
                    "source_text": "Evaluated AI security risks and model attack scenarios.",
                },
                {
                    "id": "security-report",
                    "entity_id": "ai-security",
                    "source_text": "Reported security findings to software stakeholders.",
                },
                {
                    "id": "governance-policy",
                    "entity_id": "finance-governance",
                    "source_text": (
                        "Developed financial AI governance policy and compliance reporting."
                    ),
                },
                {
                    "id": "governance-controls",
                    "entity_id": "finance-governance",
                    "source_text": "Tested governance controls for enterprise model reviews.",
                },
                {
                    "id": "sales-etl",
                    "entity_id": "sales-reporting",
                    "source_text": "Built Python ETL pipelines for sales reporting.",
                    "technologies": ["Python"],
                },
                {
                    "id": "sales-dashboard",
                    "entity_id": "sales-reporting",
                    "source_text": "Created Power BI dashboards for quarterly sales analysis.",
                    "technologies": ["Power BI"],
                },
            ],
        }
    )


def _posting() -> JobPosting:
    return JobPosting(
        id="mixed-ai-mechanical-posting",
        title="AI and Mechanical Systems Engineer",
        description=(
            "Apply AI and machine learning to mechanical design research.\n"
            "Design CAD and CAM mechanical assemblies.\n"
            "Perform kinematic analysis for robotic mechanisms.\n"
            "Develop manufacturing plans using DFM/DFA and fabrication methods.\n"
            "Prototype design algorithms in Python and MATLAB.\n"
            "Evaluate simulation results and systems engineering trade-offs.\n"
            "Collaborate across research, design, and prototype development."
        ),
    )


def _compose() -> StructuredResume:
    profile = _profile()
    posting = _posting()
    baseline = StructuredResume(
        profile_id=profile.id,
        profile_version=profile.version,
        posting_id=posting.id,
        template_id="managed-engineering-v1",
        display_name=profile.display_name,
        strategy=ResumeStrategy(
            role_family="mixed_ai_mechanical",
            primary_focus=posting.title,
            rationale="Synthetic mixed-role regression.",
        ),
    )
    return DeterministicResumeComposer(
        _OnePageBulletBudget(),
        bounds=CompositionSearchBounds(
            maximum_selected_bullets=8,
            maximum_selected_entries=4,
            maximum_experience_entries=3,
            maximum_project_entries=1,
            maximum_bullets_per_entry=6,
        ),
    ).compose(baseline, profile, posting, TemplateConstraints())


def test_mixed_ai_mechanical_portfolio_concentrates_on_direct_project_evidence() -> None:
    resume = _compose()
    selected_project = resume.project_bullets.get("robotic-assembly", [])
    selected_ids = {
        bullet.id
        for section in (resume.experience_bullets, resume.project_bullets)
        for bullets in section.values()
        for bullet in bullets
    }

    assert len(selected_project) >= 4
    assert {
        "assembly-cad",
        "assembly-kinematics",
        "assembly-manufacturing",
        "assembly-ai",
        "assembly-systems",
    } <= selected_ids
    assert not selected_ids & {
        "security-evaluation",
        "governance-policy",
        "governance-controls",
        "sales-etl",
        "sales-dashboard",
    }


def test_mixed_ai_mechanical_selection_and_skills_are_coherent_and_deterministic() -> None:
    first = _compose()
    second = _compose()
    first_diagnostic = first.composition_diagnostic
    second_diagnostic = second.composition_diagnostic
    assert first_diagnostic is not None
    assert second_diagnostic is not None

    assert first_diagnostic.selected_bullet_ids == second_diagnostic.selected_bullet_ids
    assert first_diagnostic.selected_skill_category_ids == (
        second_diagnostic.selected_skill_category_ids
    )
    selected_skills = set(first.selected_skills)
    assert {"Python", "MATLAB", "CAD", "CAM", "Kinematics", "DFM/DFA"} <= selected_skills
    assert not selected_skills & {"Power BI", "Sales Reporting", "USB)"}
    assert all(value.count("(") == value.count(")") for value in selected_skills)
