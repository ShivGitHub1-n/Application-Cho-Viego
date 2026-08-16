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
            provider="controlled final-allocation evaluator",
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
            "id": "synthetic-final-allocation-profile",
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
            role_family="synthetic_allocation_test",
            primary_focus=posting.title,
            rationale="Synthetic deterministic allocation fixture.",
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
            maximum_estimated_page_evaluations=100,
            maximum_exact_finalist_evaluations=12,
        ),
    ).compose(baseline, profile, posting, TemplateConstraints())


def _marginal_project_profile(*, extra_redundant_bullets: int = 0) -> MasterProfile:
    return _profile(
        experiences=[
            {
                "id": "robotics-role",
                "title": "Robotics Engineer",
                "kind": "experience",
            }
        ],
        projects=[
            {
                "id": "motor-project",
                "title": "Motor Driver Prototype",
                "kind": "project",
            }
        ],
        evidence=[
            {
                "id": "robot-control",
                "entity_id": "robotics-role",
                "source_text": "Built embedded motor controls for robotic actuation.",
            },
            {
                "id": "robot-test",
                "entity_id": "robotics-role",
                "source_text": (
                    "Validated robotic motor controls through hardware testing."
                ),
            },
            {
                "id": "robot-debug",
                "entity_id": "robotics-role",
                "source_text": (
                    "Debugged robotic motor control faults during prototype testing."
                ),
            },
            {
                "id": "robot-repeat",
                "entity_id": "robotics-role",
                "source_text": "Documented robotic motor control test results.",
            },
            *[
                {
                    "id": f"robot-redundant-{index}",
                    "entity_id": "robotics-role",
                    "source_text": (
                        "Documented robotic motor control test results."
                    ),
                }
                for index in range(extra_redundant_bullets)
            ],
            {
                "id": "project-circuit",
                "entity_id": "motor-project",
                "source_text": (
                    "Designed and soldered a motor-driver circuit with current-sensing "
                    "electronics."
                ),
            },
        ],
    )


def _marginal_project_posting() -> JobPosting:
    return JobPosting(
        id="synthetic-mechatronics-posting",
        title="Mechatronics Engineer",
        description=(
            "Build embedded motor controls for robotic actuation. Design motor-driver "
            "circuits and current-sensing electronics. Perform hardware testing and "
            "debugging."
        ),
    )


def test_redundant_fourth_experience_bullet_loses_to_direct_project_evidence() -> None:
    resume = _compose(
        _marginal_project_profile(),
        _marginal_project_posting(),
        maximum_selected_bullets=5,
    )
    diagnostic = resume.composition_diagnostic

    assert diagnostic is not None
    assert "project-circuit" in diagnostic.selected_bullet_ids
    assert "robot-repeat" not in diagnostic.selected_bullet_ids
    assert diagnostic.bullet_counts["robotics-role"] <= 3


def test_redundant_library_growth_does_not_increase_entry_allocation() -> None:
    posting = _marginal_project_posting()
    baseline = _compose(
        _marginal_project_profile(),
        posting,
        maximum_selected_bullets=5,
    )
    grown = _compose(
        _marginal_project_profile(extra_redundant_bullets=20),
        posting.model_copy(deep=True),
        maximum_selected_bullets=5,
    )

    assert baseline.composition_diagnostic is not None
    assert grown.composition_diagnostic is not None
    assert baseline.composition_diagnostic.selected_bullet_ids == (
        grown.composition_diagnostic.selected_bullet_ids
    )
    assert grown.composition_diagnostic.bullet_counts["robotics-role"] <= 3


def test_weak_redundant_project_does_not_displace_stronger_experience() -> None:
    profile = _profile(
        experiences=[
            {
                "id": "validation-role",
                "title": "Hardware Validation Engineer",
                "kind": "experience",
            }
        ],
        projects=[
            {"id": "notes-project", "title": "Test Notes", "kind": "project"}
        ],
        evidence=[
            {
                "id": "validation-plan",
                "entity_id": "validation-role",
                "source_text": "Created hardware validation plans for embedded boards.",
            },
            {
                "id": "validation-debug",
                "entity_id": "validation-role",
                "source_text": (
                    "Debugged embedded board failures using oscilloscope measurements."
                ),
            },
            {
                "id": "weak-notes",
                "entity_id": "notes-project",
                "source_text": "Documented general testing notes for a demonstration.",
            },
        ],
    )
    posting = JobPosting(
        id="hardware-validation-posting",
        title="Hardware Validation Engineer",
        description=(
            "Create hardware validation plans for embedded boards and debug failures "
            "using oscilloscope measurements."
        ),
    )

    resume = _compose(profile, posting, maximum_selected_bullets=2)

    assert resume.composition_diagnostic is not None
    assert set(resume.composition_diagnostic.selected_bullet_ids) == {
        "validation-plan",
        "validation-debug",
    }
    assert resume.composition_diagnostic.selected_project_ids == []


def _mixed_domain_profile() -> MasterProfile:
    return _profile(
        experiences=[
            {
                "id": "mechanical-role",
                "title": "Mechanical Prototype Engineer",
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
        ],
        projects=[
            {
                "id": "actuator-project",
                "title": "Electromechanical Actuator",
                "kind": "project",
            },
            {
                "id": "controller-project",
                "title": "Motor Controller",
                "kind": "project",
            },
        ],
        evidence=[
            {
                "id": "mechanical-cad",
                "entity_id": "mechanical-role",
                "source_text": "Designed CAD assemblies for machined prototype mechanisms.",
            },
            {
                "id": "mechanical-build",
                "entity_id": "mechanical-role",
                "source_text": (
                    "Built electromechanical prototypes with motors and mechanical "
                    "linkages."
                ),
            },
            {
                "id": "mechanical-test",
                "entity_id": "mechanical-role",
                "source_text": "Load-tested actuator mechanisms and debugged alignment faults.",
            },
            {
                "id": "embedded-board",
                "entity_id": "embedded-role",
                "source_text": (
                    "Integrated microcontrollers, sensors, and CAN interfaces on embedded "
                    "hardware boards."
                ),
            },
            {
                "id": "embedded-circuit",
                "entity_id": "embedded-role",
                "source_text": "Designed and soldered motor-driver protection circuits.",
            },
            {
                "id": "embedded-debug",
                "entity_id": "embedded-role",
                "source_text": (
                    "Troubleshot embedded board interfaces with an oscilloscope."
                ),
            },
            {
                "id": "digital-automation",
                "entity_id": "digital-role",
                "source_text": (
                    "Automated hardware tests with Python scripts."
                ),
            },
            {
                "id": "digital-telemetry",
                "entity_id": "digital-role",
                "source_text": "Developed Python telemetry services for test measurements.",
            },
            {
                "id": "digital-api",
                "entity_id": "digital-role",
                "source_text": "Implemented cloud APIs for digital reporting workflows.",
            },
            {
                "id": "digital-dashboard",
                "entity_id": "digital-role",
                "source_text": "Created dashboards for software service operations.",
            },
            {
                "id": "actuator-build",
                "entity_id": "actuator-project",
                "source_text": "Built and tuned a motor-driven actuation prototype.",
            },
            {
                "id": "actuator-cad",
                "entity_id": "actuator-project",
                "source_text": "Designed the actuator housing and linkage in CAD.",
            },
            {
                "id": "controller-electronics",
                "entity_id": "controller-project",
                "source_text": (
                    "Assembled motor-control electronics with current sensing."
                ),
            },
            {
                "id": "controller-validation",
                "entity_id": "controller-project",
                "source_text": (
                    "Debugged circuit faults and validated the controller on hardware."
                ),
            },
        ],
    )


def test_mixed_hardware_posting_allocates_by_marginal_domain_coverage() -> None:
    posting = JobPosting(
        id="mixed-hardware-posting",
        title="Mechatronics Prototyping Engineer",
        description=(
            "Build electromechanical prototypes and embedded hardware. Design CAD "
            "mechanical assemblies. Integrate motors and actuation. Design electronics "
            "and circuits. Integrate CAN interfaces on embedded hardware boards. Perform "
            "hardware testing and validation. Troubleshoot physical systems. Automated "
            "hardware tests with Python scripts."
        ),
    )

    resume = _compose(
        _mixed_domain_profile(),
        posting,
        maximum_selected_bullets=10,
    )
    diagnostic = resume.composition_diagnostic

    assert diagnostic is not None
    assert {"mechanical-role", "embedded-role"} <= set(
        diagnostic.selected_experience_ids
    )
    assert {"actuator-project", "controller-project"} & set(
        diagnostic.selected_project_ids
    )
    assert "digital-automation" in diagnostic.selected_bullet_ids
    assert not {"digital-api", "digital-dashboard"} & set(
        diagnostic.selected_bullet_ids
    )


def test_posting_priority_change_gives_digital_experience_substantial_space() -> None:
    posting = JobPosting(
        id="software-test-posting",
        title="Software Test Automation Engineer",
        description=(
            "Build Python test automation. Develop telemetry services. Implement cloud "
            "APIs. Create dashboards. Validate software service workflows."
        ),
    )

    resume = _compose(
        _mixed_domain_profile(),
        posting,
        maximum_selected_bullets=6,
    )
    diagnostic = resume.composition_diagnostic

    assert diagnostic is not None
    assert "digital-role" in diagnostic.selected_experience_ids
    assert diagnostic.bullet_counts["digital-role"] >= 3
    assert {"digital-telemetry", "digital-api", "digital-dashboard"} <= set(
        diagnostic.selected_bullet_ids
    )


def test_important_requirement_beats_comparable_minor_signal() -> None:
    profile = _profile(
        experiences=[],
        projects=[
            {"id": "circuit-project", "title": "Motor Circuit", "kind": "project"},
            {"id": "dashboard-project", "title": "Dashboard", "kind": "project"},
        ],
        evidence=[
            {
                "id": "important-circuit",
                "entity_id": "circuit-project",
                "source_text": "Designed and tested a motor-driver protection circuit.",
            },
            {
                "id": "minor-dashboard",
                "entity_id": "dashboard-project",
                "source_text": "Designed and tested a Python telemetry dashboard.",
            },
        ],
    )
    posting = JobPosting(
        id="importance-posting",
        title="Motor Controls Engineer",
        description=(
            "Design and test motor-driver protection circuits. Python telemetry "
            "dashboards are optional."
        ),
    )

    resume = _compose(profile, posting, maximum_selected_bullets=1)

    assert resume.composition_diagnostic is not None
    assert resume.composition_diagnostic.selected_bullet_ids == ["important-circuit"]


def test_unconfirmed_direct_candidate_cannot_enter_final_portfolio() -> None:
    profile = _marginal_project_profile().model_copy(deep=True)
    profile.evidence.append(
        profile.evidence[-1].model_copy(
            update={
                "id": "unconfirmed-perfect-match",
                "source_text": (
                    "Designed motor-driver circuits, current sensing, and embedded "
                    "hardware validation."
                ),
                "confirmed": False,
            }
        )
    )

    resume = _compose(
        profile,
        _marginal_project_posting(),
        maximum_selected_bullets=5,
    )

    assert resume.composition_diagnostic is not None
    assert "unconfirmed-perfect-match" not in (
        resume.composition_diagnostic.selected_bullet_ids
    )


def test_final_allocation_is_deterministic_for_equivalent_inputs() -> None:
    profile = _mixed_domain_profile()
    posting = JobPosting(
        id="deterministic-hardware-posting",
        title="Hardware Integration Engineer",
        description=(
            "Integrate embedded hardware, motor-driver circuits, CAD assemblies, "
            "actuation prototypes, hardware validation, and troubleshooting."
        ),
    )

    first = _compose(profile, posting, maximum_selected_bullets=9)
    second = _compose(
        profile.model_copy(deep=True),
        posting.model_copy(deep=True),
        maximum_selected_bullets=9,
    )

    assert first.composition_diagnostic is not None
    assert second.composition_diagnostic is not None
    assert first.composition_diagnostic.selected_bullet_ids == (
        second.composition_diagnostic.selected_bullet_ids
    )
    assert first.composition_diagnostic.selected_experience_ids == (
        second.composition_diagnostic.selected_experience_ids
    )
    assert first.composition_diagnostic.selected_project_ids == (
        second.composition_diagnostic.selected_project_ids
    )
