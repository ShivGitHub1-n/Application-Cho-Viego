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


class _ControlledPageFitEvaluator:
    def evaluate(
        self,
        resume: StructuredResume,
        *,
        attempt_exact: bool = True,
    ) -> PageFitEvaluation:
        return PageFitEvaluation(
            status=PageUtilizationStatus.ACCEPTABLE_ONE_PAGE,
            page_count=1,
            exact=attempt_exact,
            provider="controlled portfolio-coherence evaluator",
            utilization_ratio=0.82,
            fits_one_page=True,
        )


def _profile(
    *,
    experiences: list[dict[str, object]],
    projects: list[dict[str, object]],
    evidence: list[dict[str, object]],
) -> MasterProfile:
    return MasterProfile.model_validate(
        {
            "id": "synthetic-portfolio-coherence-profile",
            "user_id": "synthetic-user",
            "display_name": "Sample Candidate",
            "education": [
                {
                    "school": "Public Polytechnic",
                    "program": "Bachelor of Engineering",
                    "expected_graduation_date": "2027",
                }
            ],
            "experiences": experiences,
            "projects": projects,
            "evidence": evidence,
        }
    )


def _compose(
    profile: MasterProfile,
    posting: JobPosting,
    *,
    maximum_selected_bullets: int,
    maximum_selected_entries: int = 5,
) -> StructuredResume:
    baseline = StructuredResume(
        profile_id=profile.id,
        profile_version=profile.version,
        posting_id=posting.id,
        template_id="managed-engineering-v1",
        display_name=profile.display_name,
        strategy=ResumeStrategy(
            role_family="synthetic_portfolio_coherence",
            primary_focus=posting.title,
            rationale="Synthetic deterministic coherence fixture.",
        ),
        education=profile.education,
    )
    return DeterministicResumeComposer(
        _ControlledPageFitEvaluator(),
        bounds=CompositionSearchBounds(
            maximum_selected_bullets=maximum_selected_bullets,
            maximum_selected_entries=maximum_selected_entries,
            maximum_experience_entries=3,
            maximum_project_entries=3,
            maximum_estimated_page_evaluations=120,
            maximum_exact_finalist_evaluations=12,
        ),
    ).compose(baseline, profile, posting, TemplateConstraints())


def _entry_activation_profile() -> MasterProfile:
    return _profile(
        experiences=[
            {
                "id": "hardware-role",
                "title": "Electromechanical Engineer",
                "kind": "experience",
            }
        ],
        projects=[
            {
                "id": "software-project",
                "title": "Validation Documentation Portal",
                "kind": "project",
            }
        ],
        evidence=[
            {
                "id": "hardware-integration",
                "entity_id": "hardware-role",
                "source_text": (
                    "Integrated mechanical structures, motors, sensors, and embedded "
                    "control electronics in electromechanical prototypes."
                ),
            },
            {
                "id": "hardware-cad",
                "entity_id": "hardware-role",
                "source_text": (
                    "Designed tolerance-controlled mechanical assemblies and machined "
                    "prototype components in CAD."
                ),
            },
            {
                "id": "hardware-circuit",
                "entity_id": "hardware-role",
                "source_text": (
                    "Designed motor-driver protection circuits and debugged embedded "
                    "hardware interfaces with an oscilloscope."
                ),
            },
            {
                "id": "hardware-validation",
                "entity_id": "hardware-role",
                "source_text": (
                    "Load-tested electromechanical actuators and validated safety limits "
                    "across repeated hardware test cycles."
                ),
            },
            {
                "id": "software-documentation",
                "entity_id": "software-project",
                "source_text": (
                    "Automated validation documentation with Python for a software portal."
                ),
            },
        ],
    )


def _hardware_posting() -> JobPosting:
    return JobPosting(
        id="synthetic-hardware-coherence-posting",
        title="Mechatronics Engineer",
        description=(
            "Build electromechanical prototypes integrating mechanical structures, "
            "motors, sensors, and embedded control electronics. Design mechanical "
            "assemblies in CAD. Design and debug motor-driver circuits and embedded "
            "hardware interfaces. Perform load testing and hardware validation for "
            "electromechanical actuators. Engineering test documentation and Python "
            "automation are preferred."
        ),
    )


def test_strong_coherent_depth_beats_weak_one_bullet_entry_activation() -> None:
    resume = _compose(
        _entry_activation_profile(),
        _hardware_posting(),
        maximum_selected_bullets=4,
        maximum_selected_entries=2,
    )
    diagnostic = resume.composition_diagnostic

    assert diagnostic is not None
    assert diagnostic.selected_bullet_ids == [
        "hardware-integration",
        "hardware-cad",
        "hardware-circuit",
        "hardware-validation",
    ]
    assert diagnostic.bullet_counts == {"hardware-role": 4}
    assert diagnostic.selected_project_ids == []


def test_frontier_diagnostic_explains_entry_cost_and_rejected_alternative() -> None:
    resume = _compose(
        _entry_activation_profile(),
        _hardware_posting(),
        maximum_selected_bullets=4,
        maximum_selected_entries=2,
    )
    diagnostic = resume.composition_diagnostic

    assert diagnostic is not None
    comparison = next(
        item
        for item in diagnostic.portfolio_frontier_comparisons
        if item.rejected_candidate_id == "software-documentation"
    )
    assert comparison.selected_candidate_id in diagnostic.selected_bullet_ids
    assert comparison.selected_marginal_value > comparison.rejected_marginal_value
    assert comparison.selected_rendered_line_cost >= 1
    assert comparison.rejected_rendered_line_cost >= 3
    assert comparison.selected_entry_activation_line_cost == 0
    assert comparison.rejected_entry_activation_line_cost == 2
    assert comparison.selected_requirement_contribution
    assert comparison.comparison_reason


def _mixed_profile() -> MasterProfile:
    experiences = [
        {
            "id": "prototype-role",
            "title": "Electromechanical Prototype Engineer",
            "kind": "experience",
        },
        {
            "id": "embedded-role",
            "title": "Embedded Hardware Engineer",
            "kind": "experience",
        },
        {
            "id": "digital-role",
            "title": "Software Test Engineer",
            "kind": "experience",
        },
    ]
    projects = [
        {
            "id": "controller-project",
            "title": "Electromechanical Controller",
            "kind": "project",
        },
        {
            "id": "actuator-project",
            "title": "Mechanical Actuator",
            "kind": "project",
        },
        {
            "id": "web-project",
            "title": "Web Analytics Portal",
            "kind": "project",
        },
    ]
    evidence: list[dict[str, object]] = []

    def add(evidence_id: str, entry_id: str, text: str) -> None:
        evidence.append(
            {"id": evidence_id, "entity_id": entry_id, "source_text": text}
        )

    add(
        "prototype-integration",
        "prototype-role",
        "Integrated motors, sensors, mechanical structures, and embedded electronics.",
    )
    add(
        "prototype-cad",
        "prototype-role",
        "Designed machined prototype mechanisms and tolerance-controlled CAD assemblies.",
    )
    add(
        "prototype-actuation",
        "prototype-role",
        "Built motor-driven actuation with gearboxes, linkages, and safety limits.",
    )
    add(
        "prototype-validation",
        "prototype-role",
        "Load-tested electromechanical prototypes and debugged alignment faults.",
    )
    add(
        "embedded-board",
        "embedded-role",
        "Integrated microcontrollers, CAN interfaces, sensors, and power electronics.",
    )
    add(
        "embedded-circuit",
        "embedded-role",
        "Designed and soldered motor-driver protection and current-sensing circuits.",
    )
    add(
        "embedded-test",
        "embedded-role",
        "Performed oscilloscope-based hardware validation on embedded boards.",
    )
    add(
        "embedded-debug",
        "embedded-role",
        "Troubleshot intermittent embedded interfaces and documented root causes.",
    )
    add(
        "digital-automation",
        "digital-role",
        "Automated software tests with Python for a digital reporting workflow.",
    )
    add(
        "digital-api",
        "digital-role",
        "Implemented cloud APIs for software service workflows.",
    )
    add(
        "digital-dashboard",
        "digital-role",
        "Built operational dashboards for software service monitoring.",
    )
    add(
        "controller-build",
        "controller-project",
        "Built an electromechanical controller with motors and embedded electronics.",
    )
    add(
        "controller-test",
        "controller-project",
        "Validated motor-control circuits and debugged electrical faults on the bench.",
    )
    add(
        "controller-doc",
        "controller-project",
        "Documented controller test procedures and hardware validation results.",
    )
    add(
        "actuator-cad",
        "actuator-project",
        "Designed a mechanical actuator housing and linkage in CAD.",
    )
    add(
        "actuator-build",
        "actuator-project",
        "Machined and assembled an actuator prototype with motors and safety stops.",
    )
    add(
        "actuator-test",
        "actuator-project",
        "Load-tested the actuator and debugged alignment and backlash issues.",
    )
    add(
        "web-automation",
        "web-project",
        "Automated web application tests with Python.",
    )
    add(
        "web-dashboard",
        "web-project",
        "Built a web analytics dashboard for service metrics.",
    )
    return _profile(experiences=experiences, projects=projects, evidence=evidence)


def test_mixed_hardware_portfolio_uses_coherent_aligned_entry_packages() -> None:
    resume = _compose(
        _mixed_profile(),
        JobPosting(
            id="synthetic-mixed-hardware-posting",
            title="Mechatronics Prototyping Engineer",
            description=(
                "Build electromechanical prototypes and embedded hardware. Design CAD "
                "mechanical assemblies. Integrate motors and actuation. Design circuits "
                "and electronics. Perform hardware testing and validation. Troubleshoot "
                "and debug physical systems. Document engineering test results."
            ),
        ),
        maximum_selected_bullets=13,
        maximum_selected_entries=5,
    )
    diagnostic = resume.composition_diagnostic

    assert diagnostic is not None
    assert diagnostic.bullet_counts["prototype-role"] >= 3
    assert diagnostic.bullet_counts["embedded-role"] >= 3
    assert diagnostic.bullet_counts["controller-project"] >= 2
    assert diagnostic.bullet_counts["actuator-project"] >= 2
    assert diagnostic.bullet_counts.get("digital-role", 0) <= 1
    assert "web-project" not in diagnostic.selected_project_ids


def test_software_priority_reverses_entry_allocation_without_type_preference() -> None:
    resume = _compose(
        _mixed_profile(),
        JobPosting(
            id="synthetic-software-priority-posting",
            title="Software Test Automation Engineer",
            description=(
                "Build Python test automation for software services. Implement cloud "
                "APIs and digital reporting workflows. Build operational dashboards. "
                "Validate and debug web applications."
            ),
        ),
        maximum_selected_bullets=8,
        maximum_selected_entries=4,
    )
    diagnostic = resume.composition_diagnostic

    assert diagnostic is not None
    assert diagnostic.bullet_counts["digital-role"] >= 3
    assert "digital-role" in diagnostic.selected_experience_ids
    assert (
        "web-project" in diagnostic.selected_project_ids
        or "web-automation" in diagnostic.selected_bullet_ids
    )
