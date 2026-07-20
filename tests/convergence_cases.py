# Exact reviewed fixture bullets remain single literals for byte-fidelity assertions.
# ruff: noqa: E501

from __future__ import annotations

import json
from pathlib import Path

from resume_tailor.domain.models import (
    EducationRecord,
    EntityKind,
    EvidenceItem,
    GraduationStatus,
    JobPosting,
    MasterProfile,
    ResumeItem,
    TechnicalSkillCategory,
)


def software_cloud_case() -> tuple[MasterProfile, JobPosting]:
    experiences = [
        _entry(
            "backend-platform",
            "Backend Platform Developer",
            EntityKind.EXPERIENCE,
            "Digital Services Lab",
            "May 2023",
            "Present",
            "Toronto, ON",
        ),
        _entry(
            "cloud-reliability",
            "Cloud Reliability Engineer",
            EntityKind.EXPERIENCE,
            "Infrastructure Cooperative",
            "Jan. 2021",
            "Apr. 2023",
            "Toronto, ON",
        ),
        _entry(
            "application-security",
            "Application Security Co-op",
            EntityKind.EXPERIENCE,
            "Public Systems Centre",
            "2020",
            "2021",
            "Toronto, ON",
        ),
    ]
    projects = [
        _entry(
            "security-observability",
            "Security Observability Service",
            EntityKind.PROJECT,
            "Hackathon Project",
            "2024",
            "2025",
            "Toronto, ON",
        ),
        _entry(
            "distributed-events",
            "Distributed Event Platform",
            EntityKind.PROJECT,
            "Portfolio Project",
            "Sep. 2022",
            "Apr. 2023",
            "Toronto, ON",
        ),
    ]
    evidence = _evidence(
        "backend-platform",
        [
            "Built Python and .NET 8 APIs with PostgreSQL transactions, asynchronous workflows, schema validation, and documented failure handling for production services.",
            "Implemented Kafka event consumers with idempotent processing, retry controls, and traceable recovery behavior across distributed service boundaries.",
            "Validated API contracts through integration tests, negative test cases, and reviewed release evidence before production deployments.",
            "Profiled database and request paths, then improved backend throughput by 38% through reviewed batching and indexing changes.",
        ],
    )
    evidence += _evidence(
        "cloud-reliability",
        [
            "Built Kubernetes health monitoring, service-level dashboards, and alert routing for Docker workloads deployed across AWS environments.",
            "Created controlled recovery tests for timeouts, dependency failures, database interruptions, and service restarts with documented incident evidence.",
            "Validated CI/CD pipelines, PostgreSQL migrations, and Terraform plans through staging checks before production release approval.",
            "Automated Python analysis of application logs and deployment telemetry to support repeatable defect investigation and reliability reviews.",
        ],
    )
    evidence += _evidence(
        "application-security",
        [
            "Implemented OAuth 2.0 authorization checks and validated API access-control behavior through reviewed integration and negative test scenarios.",
            "Built SIEM event correlation workflows that linked security alerts to application logs while retaining analyst review for ambiguous findings.",
            "Validated container and dependency findings through reproducible Docker tests before coordinating remediation with backend and cloud engineers.",
            "Created threat scenarios for event-driven services and documented secure deployment controls, failure modes, and evidence-backed review decisions.",
        ],
    )
    evidence += _evidence(
        "security-observability",
        [
            "Built an OAuth 2.0 audit service that correlated API activity with SIEM findings and retained evidence links for each security decision.",
            "Implemented deterministic severity rules, structured findings, and review workflows without inventing unsupported incident outcomes.",
            "Tested malformed, duplicated, and delayed security events through repeatable automated tests and documented expected behavior.",
            "Built deployment health checks and dashboards for monitored Docker and Kubernetes services.",
        ],
    )
    evidence += _evidence(
        "distributed-events",
        [
            "Created Kafka event processing with idempotent consumers, PostgreSQL persistence, schema validation, and deterministic recovery behavior.",
            "Built Docker and Kubernetes manifests with CI/CD integration tests, AWS deployment checks, and repeatable rollback validation.",
            "Implemented distributed traces and structured logs that linked failed events to the responsible service and evidence record.",
            "Validated load, retry, and schema-evolution scenarios through automated Python tests before each controlled release.",
        ],
    )
    return (
        _profile(
            "software-cloud-convergence",
            experiences,
            projects,
            evidence,
            [
                _skills("Programming Languages", "Python", "C#", "SQL", "JavaScript"),
                _skills("Cloud & Platforms", "AWS", "Kubernetes", "Docker", "Terraform"),
                _skills("Data & Messaging", "PostgreSQL", "Kafka", "Schema validation"),
                _skills("Delivery & Security", "CI/CD", "OAuth 2.0", "SIEM", "Integration testing"),
            ],
            EducationRecord(
                school="Public Polytechnic University",
                program="Bachelor of Engineering in Software Systems",
                minor_or_specialization="Cybersecurity specialization",
                co_op_designation="Co-operative Education",
                start_date="Sep. 2018",
                graduation_date="Apr. 2023",
                graduation_status=GraduationStatus.COMPLETED,
                location="Toronto, ON",
                gpa="3.8/4.0",
                awards=["Applied Computing Scholarship"],
                relevant_coursework=[
                    "Distributed Systems",
                    "Cloud Computing",
                    "Secure Software Design",
                ],
            ),
        ),
        JobPosting(
            id="software-cloud-posting",
            title="Software and Cloud Platform Engineer",
            description=(
                "Build Python and .NET backend APIs using PostgreSQL and Kafka. Deploy "
                "Docker services to Kubernetes on AWS with Terraform and CI/CD. Improve "
                "distributed-system reliability, observability, security, testing, OAuth "
                "authorization, and production incident diagnosis."
            ),
        ),
    )


def mechanical_manufacturing_case() -> tuple[MasterProfile, JobPosting]:
    experiences = [
        _entry(
            "mechanical-design",
            "Mechanical Design Engineer",
            EntityKind.EXPERIENCE,
            "Applied Design Laboratory",
            "May 2023",
            "Present",
            "Toronto, ON",
        ),
        _entry(
            "manufacturing-coop",
            "Manufacturing Engineering Co-op",
            EntityKind.EXPERIENCE,
            "Advanced Production Centre",
            "Jan. 2022",
            "Aug. 2022",
            "Toronto, ON",
        ),
        _entry(
            "product-test",
            "Product Test Engineer",
            EntityKind.EXPERIENCE,
            "Mobility Systems Team",
            "2020",
            "2021",
            "Toronto, ON",
        ),
    ]
    projects = [
        _entry(
            "modular-fixture",
            "Modular Manufacturing Fixture",
            EntityKind.PROJECT,
            "Design Project",
            "2024",
            "2025",
            "Toronto, ON",
        ),
        _entry(
            "robot-chassis",
            "Autonomous Robot Chassis",
            EntityKind.PROJECT,
            "Capstone Project",
            "Sep. 2022",
            "Apr. 2023",
            "Toronto, ON",
        ),
    ]
    evidence = _evidence(
        "mechanical-design",
        [
            "Created load-bearing SolidWorks assemblies with GD&T drawings, tolerance-stack analysis, documented design decisions, and reviewed manufacturing constraints.",
            "Validated structural prototypes through static-load, fatigue, fit, and interface testing while documenting failure modes and corrective design changes.",
            "Led design-for-manufacturing reviews with machinists, electrical engineers, and controls engineers for integrated enclosures and serviceable assemblies.",
            "Released controlled drawing packages and bills of materials after verifying interfaces, fastener access, material choices, and supplier feedback.",
        ],
    )
    evidence += _evidence(
        "manufacturing-coop",
        [
            "Created CNC machining work instructions, GD&T inspection plans, and traceable measurement records for aluminum production components.",
            "Designed 3D-printed fixtures and soft jaws that supported repeatable part location, inspection access, and manufacturing trials.",
            "Investigated out-of-tolerance machined components using GD&T inspection records, then documented corrective actions with production and design engineers.",
            "Completed process capability studies for critical dimensions and presented measurement findings during manufacturing readiness reviews.",
        ],
    )
    evidence += _evidence(
        "product-test",
        [
            "Tested electromechanical assemblies using load cells, displacement sensors, laboratory equipment, and repeatable verification procedures.",
            "Debugged mechanical, wiring, sensor, and controls-interface faults across integrated prototype systems while preserving cross-discipline evidence.",
            "Built Python data-analysis scripts for reviewed load and displacement measurements without changing the mechanical validation authority.",
            "Documented requirement traceability, test exceptions, and corrective actions for design and manufacturing review teams.",
        ],
    )
    evidence += _evidence(
        "modular-fixture",
        [
            "Built a modular inspection fixture with datum controls, interchangeable locating features, and documented operator access requirements.",
            "Applied GD&T and tolerance analysis to verify repeatable part location across three manufactured component variants.",
            "Fabricated prototype fixture elements through CNC machining and 3D printing, then measured fit and repeatability during trials.",
            "Revised clamp geometry after ergonomic and measurement studies reduced average setup time by 24%.",
        ],
    )
    evidence += _evidence(
        "robot-chassis",
        [
            "Created a welded and machined robot chassis with SolidWorks assemblies, GD&T drawings, tolerance analysis, and integrated sensor mounts.",
            "Built CNC-machined and 3D-printed prototype brackets, then verified assembly fit, service access, and cable-routing interfaces.",
            "Tested wheel loads, enclosure mounts, and electromechanical interfaces through controlled bench and field test procedures.",
            "Coordinated mechanical, electrical, and controls interfaces through reviewed drawings, fit checks, and documented integration decisions.",
        ],
    )
    return (
        _profile(
            "mechanical-manufacturing-convergence",
            experiences,
            projects,
            evidence,
            [
                _skills("Mechanical Design", "SolidWorks", "GD&T", "Tolerance analysis"),
                _skills(
                    "Manufacturing", "CNC machining", "3D printing", "Design for manufacturing"
                ),
                _skills(
                    "Test & Measurement", "Load cells", "Inspection planning", "Process capability"
                ),
                _skills(
                    "Engineering Tools", "Python", "Data analysis", "Requirements traceability"
                ),
            ],
            EducationRecord(
                school="Public Polytechnic University",
                program="Bachelor of Engineering in Mechanical Engineering",
                minor_or_specialization="Manufacturing systems option",
                co_op_designation="Co-operative Education",
                start_date="Sep. 2018",
                graduation_date="Apr. 2023",
                graduation_status=GraduationStatus.COMPLETED,
                location="Toronto, ON",
                gpa="3.7/4.0",
                awards=["Manufacturing Design Award"],
                relevant_coursework=[
                    "Machine Design",
                    "Manufacturing Processes",
                    "Mechanical Testing",
                ],
            ),
        ),
        JobPosting(
            id="mechanical-manufacturing-posting",
            title="Mechanical Design and Manufacturing Engineer",
            description=(
                "Design SolidWorks assemblies and GD&T drawings, complete tolerance "
                "analysis, and support design for manufacturing. Build CNC-machined and "
                "3D-printed prototypes and fixtures. Plan inspection, validate mechanical "
                "and electromechanical systems, analyze test data, investigate failures, "
                "and coordinate manufacturing readiness with cross-functional teams."
            ),
        ),
    )


def rich_mixed_case() -> tuple[MasterProfile, JobPosting]:
    raw = json.loads(
        (Path(__file__).parent / "fixtures" / "resume_composition_cases.json").read_text(
            encoding="utf-8"
        )
    )
    return (
        MasterProfile.model_validate(raw["profile"]),
        JobPosting.model_validate(raw["postings"]["mixed"]),
    )


def _profile(
    profile_id: str,
    experiences: list[ResumeItem],
    projects: list[ResumeItem],
    evidence: list[EvidenceItem],
    skills: list[TechnicalSkillCategory],
    education: EducationRecord,
) -> MasterProfile:
    return MasterProfile(
        id=profile_id,
        user_id="synthetic-convergence-user",
        display_name="Jordan Candidate",
        contact={
            "email": "jordan@example.com",
            "phone": "555-0142",
            "location": "Toronto, ON",
            "links": ["linkedin.com/in/jordan-candidate"],
        },
        education=[education],
        experiences=experiences,
        projects=projects,
        technical_skills=skills,
        evidence=evidence,
    )


def _entry(
    entry_id: str,
    title: str,
    kind: EntityKind,
    organization: str,
    start_date: str,
    end_date: str,
    location: str,
) -> ResumeItem:
    return ResumeItem(
        id=entry_id,
        title=title,
        kind=kind,
        organization=organization,
        start_date=start_date,
        end_date=end_date,
        location=location,
    )


def _evidence(entry_id: str, bullets: list[str]) -> list[EvidenceItem]:
    return [
        EvidenceItem(
            id=f"{entry_id}-evidence-{index}",
            entity_id=entry_id,
            source_text=text,
            confirmed=True,
        )
        for index, text in enumerate(bullets, start=1)
    ]


def _skills(category: str, *values: str) -> TechnicalSkillCategory:
    return TechnicalSkillCategory(category=category, values=list(values))


__all__ = [
    "mechanical_manufacturing_case",
    "rich_mixed_case",
    "software_cloud_case",
]
