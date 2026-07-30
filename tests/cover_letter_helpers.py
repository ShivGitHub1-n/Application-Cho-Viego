from __future__ import annotations

from pathlib import Path

from resume_tailor.application.company_research import BoundedCompanyResearchService
from resume_tailor.application.cover_letter import CoverLetterService
from resume_tailor.application.cover_letter_evidence import CoverLetterEvidencePortfolio
from resume_tailor.application.cover_letter_validation import DeterministicCoverLetterComposer
from resume_tailor.domain.cover_letter import CoverLetterRecipient
from resume_tailor.domain.llm_models import (
    CoverLetterDraftResult,
    LlmOperation,
    ModelCallMetadata,
)
from resume_tailor.domain.models import (
    EntityKind,
    EvidenceItem,
    JobPosting,
    MasterProfile,
    ResumeItem,
    TailoringPlan,
    TemplateConstraints,
)
from resume_tailor.infrastructure.cover_letter_rendering import CoverLetterRenderResult
from resume_tailor.infrastructure.optimization import DeterministicResumeOptimizer
from resume_tailor.infrastructure.rendering import PageCountMeasurement


def cover_letter_case(
    *,
    title: str = "Embedded Firmware Intern",
    description: str | None = None,
    company: str = "Example Robotics",
) -> tuple[MasterProfile, JobPosting, TailoringPlan]:
    profile = MasterProfile(
        id="cover-profile",
        user_id="user",
        display_name="Candidate Name",
        contact={
            "location": "Toronto, ON",
            "email": "candidate@example.com",
            "phone": "+1 416 555 0100",
            "links": ["https://github.com/candidate"],
        },
        experiences=[
            ResumeItem(id="firmware-entry", title="Firmware Intern", kind=EntityKind.EXPERIENCE),
            ResumeItem(
                id="test-entry", title="Test Engineering Assistant", kind=EntityKind.EXPERIENCE
            ),
            ResumeItem(id="data-entry", title="Software Project", kind=EntityKind.PROJECT),
        ],
        evidence=[
            EvidenceItem(
                id="firmware-evidence",
                entity_id="firmware-entry",
                source_text=("Built STM32 firmware and tested SPI sensor communication at 30 FPS."),
                technologies=["STM32", "SPI"],
                outcomes=["30 FPS"],
            ),
            EvidenceItem(
                id="test-evidence",
                entity_id="test-entry",
                source_text=(
                    "Designed a Python hardware test fixture that recorded repeatable "
                    "sensor failures across 40 test cycles."
                ),
                technologies=["Python", "hardware test fixture"],
                outcomes=["40 test cycles"],
            ),
            EvidenceItem(
                id="data-evidence",
                entity_id="data-entry",
                source_text=(
                    "Implemented a containerized data API with PostgreSQL and measured "
                    "request latency during integration tests."
                ),
                technologies=["PostgreSQL", "containers"],
                outcomes=["measured request latency"],
            ),
        ],
    )
    posting = JobPosting(
        id="cover-posting",
        title=title,
        company_name=company,
        description=description
        or (
            "Build STM32 firmware, test SPI sensors, and develop hardware test systems "
            "for autonomous robots."
        ),
        source_url="https://example.com/jobs/embedded-firmware-intern",
    )
    plan = DeterministicResumeOptimizer().create_plan(
        profile,
        posting,
        TemplateConstraints(max_experience_lines=8, max_project_lines=4),
    )
    return profile, posting, plan


def rich_cover_letter_case() -> tuple[MasterProfile, JobPosting, TailoringPlan]:
    profile = MasterProfile(
        id="rich-cover-profile",
        user_id="synthetic-user",
        display_name="Jordan Candidate",
        contact={
            "location": "Hamilton, ON",
            "email": "jordan@example.com",
            "phone": "+1 905 555 0100",
            "links": [
                "https://github.com/jordan-candidate",
                "https://portfolio.example.net/jordan",
            ],
        },
        experiences=[
            ResumeItem(
                id="systems-entry",
                title="Hardware Systems Engineer",
                kind=EntityKind.EXPERIENCE,
            ),
            ResumeItem(
                id="sensor-entry",
                title="Sensor Integration Engineer",
                kind=EntityKind.EXPERIENCE,
            ),
            ResumeItem(
                id="airflow-entry",
                title="Airflow Safety Controller",
                kind=EntityKind.PROJECT,
            ),
        ],
        evidence=[
            EvidenceItem(
                id="systems-architecture",
                entity_id="systems-entry",
                source_text=(
                    "Designed actuator controller architecture with STM32 microcontrollers, "
                    "CAN interfaces, and motor drivers for prototype positioning hardware."
                ),
                technologies=["STM32", "CAN interfaces", "motor drivers"],
                outcomes=["prototype positioning hardware"],
            ),
            EvidenceItem(
                id="systems-integration",
                entity_id="systems-entry",
                source_text=(
                    "Built wiring harnesses, selected connectors, documented interface-control "
                    "requirements, and troubleshot electrical integration faults during bench "
                    "testing."
                ),
                technologies=[
                    "wiring harnesses",
                    "connectors",
                    "interface-control requirements",
                ],
                outcomes=["electrical integration fault isolation"],
            ),
            EvidenceItem(
                id="sensor-architecture",
                entity_id="sensor-entry",
                source_text=(
                    "Developed sensor architecture linking encoders, current sensors, and GPIO "
                    "interfaces to embedded firmware for closed-loop test rigs."
                ),
                technologies=[
                    "encoders",
                    "current sensors",
                    "GPIO interfaces",
                    "embedded firmware",
                ],
                outcomes=["closed-loop test rigs"],
            ),
            EvidenceItem(
                id="sensor-testing",
                entity_id="sensor-entry",
                source_text=(
                    "Created schematics and test procedures, verified signal timing across "
                    "embedded interfaces, and documented repeatable troubleshooting results."
                ),
                technologies=["schematics", "test procedures", "embedded interfaces"],
                outcomes=["repeatable troubleshooting results"],
            ),
            EvidenceItem(
                id="airflow-control",
                entity_id="airflow-entry",
                source_text=(
                    "Built a ventilation controller using gas sensors, comparator circuitry, "
                    "a timer, and a motor driver to trigger physical airflow."
                ),
                technologies=[
                    "gas sensors",
                    "comparator circuitry",
                    "timer",
                    "motor driver",
                ],
                outcomes=["triggered physical airflow"],
            ),
            EvidenceItem(
                id="airflow-prototype",
                entity_id="airflow-entry",
                source_text=(
                    "Assembled the circuit on a breadboard, integrated the fan and power stage, "
                    "and tested sensor thresholds while troubleshooting the physical prototype."
                ),
                technologies=["breadboard", "fan", "power stage", "sensor thresholds"],
                outcomes=["tested physical prototype"],
            ),
        ],
    )
    posting = JobPosting(
        id="rich-cover-posting",
        title="Hardware Integration Engineer",
        company_name="Northstar Controls",
        description=(
            "Act as the primary technical liaison, working with manufacturing partners to "
            "define requirements and troubleshoot integration issues. Design sensor interfaces "
            "and wiring harnesses. Integrate microcontrollers with actuator drivers. Build "
            "hardware prototypes and execute validation testing."
        ),
        source_url="https://northstar.example/jobs/hardware-integration",
    )
    plan = DeterministicResumeOptimizer().create_plan(
        profile,
        posting,
        TemplateConstraints(max_experience_lines=8, max_project_lines=4),
    )
    return profile, posting, plan


class ControlledCoverLetterRenderer:
    def __init__(
        self,
        utilizations: list[float] | None = None,
        *,
        page_counts: list[int] | None = None,
        exact: bool = True,
        blank_indices: set[int] | None = None,
    ) -> None:
        self.utilizations = utilizations or [0.93]
        self.page_counts = page_counts or [1]
        self.exact = exact
        self.blank_indices = blank_indices or set()
        self.pagination_attempt_count = 0
        self.render_calls = 0
        self.rendered_letters: list[object] = []

    def render_candidates(
        self,
        letters: list[object],
        output_directory: Path,
    ) -> list[CoverLetterRenderResult]:
        self.pagination_attempt_count += 1
        self.render_calls += len(letters)
        self.rendered_letters.extend(letters)
        results: list[CoverLetterRenderResult] = []
        for index, _letter in enumerate(letters):
            path = Path(output_directory) / f"controlled-cover-letter-{index}.docx"
            payload = b"PK\x03\x04stored-cover-letter-" + str(index).encode()
            path.write_bytes(payload)
            utilization = self.utilizations[min(index, len(self.utilizations) - 1)]
            page_count = self.page_counts[min(index, len(self.page_counts) - 1)]
            results.append(
                CoverLetterRenderResult(
                    docx_path=path,
                    docx_bytes=payload,
                    measurement=PageCountMeasurement(
                        page_count=page_count,
                        provider="controlled exact provider" if self.exact else "estimate",
                        confidence="exact" if self.exact else "estimated",
                        exact=self.exact,
                    ),
                    estimated_utilization=utilization,
                    estimated_remaining_lines=max(0, round((1 - utilization) * 52)),
                    pagination_failure=(None if self.exact else "Word pagination unavailable"),
                    blank_trailing_page=index in self.blank_indices,
                )
            )
        return results


def provider_result(
    profile: MasterProfile,
    posting: JobPosting,
    plan: TailoringPlan,
) -> CoverLetterDraftResult:
    research = BoundedCompanyResearchService().research(
        CoverLetterService.default_research_request(posting)
    )
    evidence, _ = CoverLetterEvidencePortfolio().select(profile, posting, plan)
    output = DeterministicCoverLetterComposer().variants(evidence, research, posting)[-1]
    return CoverLetterDraftResult(
        metadata=ModelCallMetadata(
            provider="fake",
            model="fake-model",
            operation=LlmOperation.COVER_LETTER_DRAFT,
            latency_ms=1,
        ),
        output=output,
    )


def recipient(posting: JobPosting) -> CoverLetterRecipient:
    return CoverLetterRecipient(company=posting.company_name)


__all__ = [
    "ControlledCoverLetterRenderer",
    "cover_letter_case",
    "provider_result",
    "recipient",
    "rich_cover_letter_case",
]
