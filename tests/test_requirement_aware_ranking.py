from __future__ import annotations

from collections.abc import Iterable

import pytest

from resume_tailor.application.requirement_ranking import (
    assess_evidence_relationship,
    extract_posting_requirements,
)
from resume_tailor.application.resume_composition import (
    CompositionSearchBounds,
    DeterministicResumeComposer,
    _posting_context,
)
from resume_tailor.application.resume_features import extract_reviewed_text_features
from resume_tailor.domain.layout import PageUtilizationStatus
from resume_tailor.domain.models import (
    EntityKind,
    EvidenceItem,
    JobPosting,
    MasterProfile,
    ResumeItem,
    ResumeStrategy,
    StructuredResume,
    TemplateConstraints,
)
from resume_tailor.domain.requirement_ranking import (
    EvidenceRelationship,
    RequirementAuthority,
)
from resume_tailor.domain.resume_composition import PageFitEvaluation


class _FixedPageFit:
    def evaluate(
        self,
        resume: StructuredResume,
        *,
        attempt_exact: bool = True,
    ) -> PageFitEvaluation:
        bullet_count = sum(
            len(items)
            for section in (resume.experience_bullets, resume.project_bullets)
            for items in section.values()
        )
        utilization = min(0.94, 0.62 + bullet_count * 0.035)
        return PageFitEvaluation(
            status=PageUtilizationStatus.ACCEPTABLE_ONE_PAGE,
            page_count=1,
            exact=attempt_exact,
            provider="requirement-aware fixed page fit",
            utilization_ratio=utilization,
            fits_one_page=True,
        )


def _profile(
    *,
    experiences: Iterable[ResumeItem] = (),
    projects: Iterable[ResumeItem] = (),
    evidence: Iterable[EvidenceItem] = (),
    declared_skills: list[str] | None = None,
) -> MasterProfile:
    return MasterProfile(
        id="requirement-aware-profile",
        user_id="requirement-aware-user",
        display_name="Reviewed Candidate",
        experiences=list(experiences),
        projects=list(projects),
        evidence=list(evidence),
        declared_skills=declared_skills or [],
    )


def _baseline(profile: MasterProfile, posting: JobPosting) -> StructuredResume:
    return StructuredResume(
        profile_id=profile.id,
        profile_version=profile.version,
        posting_id=posting.id,
        template_id="managed-engineering-v1",
        display_name=profile.display_name,
        strategy=ResumeStrategy(
            role_family="controlled",
            primary_focus=posting.title,
            rationale="Controlled requirement-aware ranking test.",
        ),
    )


def _rank(
    profile: MasterProfile,
    posting: JobPosting,
) -> dict[str, object]:
    composer = DeterministicResumeComposer(_FixedPageFit())
    return {
        item.evidence_id: item
        for item in composer._all_bullet_candidates(
            profile,
            _posting_context(posting),
        )
    }


def test_required_context_has_more_authority_than_bonus_context() -> None:
    posting = JobPosting(
        id="authority-posting",
        title="Platform Engineer",
        description=(
            "Required qualifications:\nBuild Python APIs with PostgreSQL.\n"
            "Preferred qualifications:\nDashboard visualization is a bonus."
        ),
    )

    model = extract_posting_requirements(posting)
    required = next(item for item in model.requirements if "Python APIs" in item.text)
    bonus = next(item for item in model.requirements if "Dashboard" in item.text)

    assert required.authority is RequirementAuthority.CORE
    assert bonus.authority is RequirementAuthority.BONUS
    assert required.importance > bonus.importance


def test_direct_requirement_evidence_defeats_weaker_complementary_evidence() -> None:
    direct_entry = ResumeItem(
        id="direct-project",
        title="Payment API",
        kind=EntityKind.PROJECT,
    )
    complementary_entry = ResumeItem(
        id="bonus-experience",
        title="Reporting Assistant",
        kind=EntityKind.EXPERIENCE,
    )
    profile = _profile(
        experiences=[complementary_entry],
        projects=[direct_entry],
        evidence=[
            EvidenceItem(
                id="direct-api",
                entity_id=direct_entry.id,
                source_text="Built authenticated Python APIs backed by PostgreSQL.",
                technologies=["Python", "PostgreSQL"],
            ),
            EvidenceItem(
                id="bonus-dashboard",
                entity_id=complementary_entry.id,
                source_text="Prepared a dashboard visualization for monthly reporting.",
            ),
        ],
    )
    posting = JobPosting(
        id="direct-posting",
        title="Backend Engineer",
        description=(
            "Required qualifications:\nBuild Python APIs with PostgreSQL.\n"
            "Preferred qualifications:\nDashboard visualization is a bonus."
        ),
    )

    ranked = _rank(profile, posting)

    assert ranked["direct-api"].relationship is EvidenceRelationship.DIRECT
    assert (
        ranked["bonus-dashboard"].relationship
        is EvidenceRelationship.COMPLEMENTARY
    )
    assert ranked["direct-api"].score > ranked["bonus-dashboard"].score


def test_direct_evidence_defeats_unrelated_entry_regardless_of_employer_label() -> None:
    direct_entry = ResumeItem(
        id="direct-controls",
        title="Controls Developer",
        kind=EntityKind.EXPERIENCE,
        organization="Small Engineering Team",
    )
    unrelated_entry = ResumeItem(
        id="unrelated-brand",
        title="Operations Assistant",
        kind=EntityKind.EXPERIENCE,
        organization="Widely Recognized Enterprise",
    )
    profile = _profile(
        experiences=[unrelated_entry, direct_entry],
        evidence=[
            EvidenceItem(
                id="unrelated-notes",
                entity_id=unrelated_entry.id,
                source_text="Prepared weekly scheduling notes for office meetings.",
            ),
            EvidenceItem(
                id="direct-firmware",
                entity_id=direct_entry.id,
                source_text="Developed STM32 firmware and validated SPI peripheral timing.",
                technologies=["STM32", "SPI"],
                capabilities=["firmware", "peripheral validation"],
            ),
        ],
    )
    posting = JobPosting(
        id="embedded-controls-posting",
        title="Embedded Controls Engineer",
        description="Develop STM32 firmware and validate SPI peripheral timing.",
    )
    composer = DeterministicResumeComposer(_FixedPageFit())
    pool = composer._candidate_pool(profile, _posting_context(posting))

    assert [item.evidence_id for item in pool.ranked_bullets] == [
        "direct-firmware"
    ]
    assert any(
        item.evidence_id == "unrelated-notes"
        for item in pool.relevance_excluded_bullets
    )


def test_strong_adjacent_evidence_can_beat_shallow_literal_overlap() -> None:
    adjacent_entry = ResumeItem(
        id="manufacturing-entry",
        title="Manufacturing Process Engineer",
        kind=EntityKind.EXPERIENCE,
    )
    shallow_entry = ResumeItem(
        id="notes-entry",
        title="Administrative Assistant",
        kind=EntityKind.EXPERIENCE,
    )
    profile = _profile(
        experiences=[adjacent_entry, shallow_entry],
        evidence=[
            EvidenceItem(
                id="adjacent-validation",
                entity_id=adjacent_entry.id,
                source_text=(
                        "Tested inspection jigs through repeatable gauge studies and "
                        "documented measurement accuracy."
                    ),
                    capabilities=["gauge studies", "inspection planning"],
            ),
            EvidenceItem(
                id="shallow-literal",
                entity_id=shallow_entry.id,
                source_text="Mentioned manufacturing in weekly notes.",
            ),
        ],
    )
    posting = JobPosting(
        id="manufacturing-posting",
        title="Manufacturing Engineer",
        description="Validate production fixtures and dimensional tolerances.",
    )

    ranked = _rank(profile, posting)

    assert (
        ranked["adjacent-validation"].relationship
        is EvidenceRelationship.ADJACENT
    )
    assert ranked["shallow-literal"].relationship in {
        EvidenceRelationship.INCIDENTAL,
        EvidenceRelationship.REJECTED,
    }
    assert ranked["adjacent-validation"].score > ranked["shallow-literal"].score


def test_entry_admission_does_not_transfer_relevance_to_weak_internal_bullet() -> None:
    entry = ResumeItem(
        id="backend-entry",
        title="Backend Engineer",
        kind=EntityKind.EXPERIENCE,
        technologies=["Python", "PostgreSQL"],
    )
    profile = _profile(
        experiences=[entry],
        evidence=[
            EvidenceItem(
                id="backend-proof",
                entity_id=entry.id,
                source_text="Built Python APIs backed by PostgreSQL.",
            ),
            EvidenceItem(
                id="event-photos",
                entity_id=entry.id,
                source_text="Organized event photos for a social newsletter.",
            ),
        ],
    )
    posting = JobPosting(
        id="backend-posting",
        title="Backend Engineer",
        description="Required: Build Python APIs backed by PostgreSQL.",
    )

    ranked = _rank(profile, posting)

    assert ranked["backend-proof"].admitted is True
    assert ranked["event-photos"].admitted is False
    assert ranked["event-photos"].relationship is EvidenceRelationship.REJECTED


def test_single_broad_acronym_cannot_admit_unrelated_project() -> None:
    entry = ResumeItem(
        id="expense-project",
        title="Expense Dashboard",
        kind=EntityKind.PROJECT,
    )
    profile = _profile(
        projects=[entry],
        evidence=[
            EvidenceItem(
                id="ai-only",
                entity_id=entry.id,
                source_text="Added AI summaries to an expense dashboard.",
                technologies=["AI"],
            )
        ],
    )
    posting = JobPosting(
        id="ai-posting",
        title="Automation Engineer",
        description="Build Python automation. Optional AI exposure is helpful.",
    )

    candidate = _rank(profile, posting)["ai-only"]

    assert candidate.admitted is False
    token = next(
        item for item in candidate.short_token_contributions if item.token == "AI"
    )
    assert token.corroborated is False
    assert token.contribution == 0


def test_corroborated_acronym_and_specific_identifier_remain_matchable() -> None:
    posting = JobPosting(
        id="identifier-posting",
        title="Inference and Firmware Engineer",
        description=(
            "Required:\nDevelop AI inference pipelines with PyTorch.\n"
            "Validate SPI peripheral timing on STM32."
        ),
    )
    model = extract_posting_requirements(posting)
    empty = extract_reviewed_text_features("")
    ai_text = "Deployed AI inference pipelines with PyTorch."
    ai = assess_evidence_relationship(
        bullet_text=ai_text,
        bullet_features=extract_reviewed_text_features(ai_text),
        entry_features=empty,
        structured_values=["AI", "PyTorch"],
        requirements=model,
    )
    spi_text = "Validated SPI peripheral timing on STM32."
    spi = assess_evidence_relationship(
        bullet_text=spi_text,
        bullet_features=extract_reviewed_text_features(spi_text),
        entry_features=empty,
        structured_values=["SPI", "STM32"],
        requirements=model,
    )

    assert ai.relationship is EvidenceRelationship.DIRECT
    assert next(
        item for item in ai.short_token_contributions if item.token == "AI"
    ).corroborated
    assert spi.relationship is EvidenceRelationship.DIRECT
    assert any(
        item.token == "STM32" and item.corroborated
        for item in spi.short_token_contributions
    )


def test_direct_project_can_defeat_weaker_experience_and_keep_scope() -> None:
    experience = ResumeItem(
        id="dashboard-experience",
        title="Reporting Assistant",
        kind=EntityKind.EXPERIENCE,
    )
    project = ResumeItem(
        id="robot-project",
        title="Robot Controller",
        kind=EntityKind.PROJECT,
    )
    profile = _profile(
        experiences=[experience],
        projects=[project],
        evidence=[
            EvidenceItem(
                id="dashboard-bonus",
                entity_id=experience.id,
                source_text="Built a monitoring dashboard for weekly reports.",
            ),
            EvidenceItem(
                id="robot-control",
                entity_id=project.id,
                source_text="Implemented STM32 motor control firmware.",
                technologies=["STM32"],
            ),
            EvidenceItem(
                id="robot-bus",
                entity_id=project.id,
                source_text="Validated SPI sensor timing and fault handling.",
                technologies=["SPI"],
            ),
        ],
    )
    posting = JobPosting(
        id="robot-posting",
        title="Embedded Controls Engineer",
        description=(
            "Required:\nImplement STM32 motor control firmware and validate SPI "
            "sensor timing.\nPreferred: Monitoring dashboards are a bonus."
        ),
    )
    resume = DeterministicResumeComposer(
        _FixedPageFit(),
        bounds=CompositionSearchBounds(maximum_estimated_page_evaluations=48),
    ).compose(
        _baseline(profile, posting),
        profile,
        posting,
        TemplateConstraints(),
    )
    diagnostic = resume.composition_diagnostic

    assert diagnostic is not None
    assert diagnostic.selected_project_ids == [project.id]
    assert diagnostic.bullet_counts[project.id] == 2
    assert diagnostic.bullet_counts[project.id] > diagnostic.bullet_counts.get(
        experience.id,
        0,
    )


@pytest.mark.parametrize(
    ("title", "required", "direct", "bonus"),
    [
        (
            "Embedded Engineer",
            "Validate STM32 sensor firmware.",
            "Validated STM32 sensor firmware.",
            "Prepared a cloud dashboard.",
        ),
        (
            "Manufacturing Engineer",
            "Validate CNC inspection fixtures.",
            "Validated CNC inspection fixtures.",
            "Prepared a reporting dashboard.",
        ),
        (
            "Cloud Engineer",
            "Deploy Kubernetes services.",
            "Deployed Kubernetes services.",
            "Prepared a CAD drawing.",
        ),
        (
            "Security Engineer",
            "Investigate SIEM alerts.",
            "Investigated SIEM alerts.",
            "Prepared a data dashboard.",
        ),
        (
            "Machine Learning Engineer",
            "Deploy PyTorch inference pipelines.",
            "Deployed PyTorch inference pipelines.",
            "Prepared an API dashboard.",
        ),
        (
            "Systems Engineer",
            "Integrate sensors, wiring, and controls.",
            "Integrated sensors, wiring, and controls.",
            "Prepared a cloud report.",
        ),
    ],
)
def test_cross_domain_direct_evidence_beats_bonus_evidence(
    title: str,
    required: str,
    direct: str,
    bonus: str,
) -> None:
    direct_entry = ResumeItem(
        id="direct-entry",
        title=title,
        kind=EntityKind.PROJECT,
    )
    bonus_entry = ResumeItem(
        id="bonus-entry",
        title="General Assistant",
        kind=EntityKind.EXPERIENCE,
    )
    profile = _profile(
        experiences=[bonus_entry],
        projects=[direct_entry],
        evidence=[
            EvidenceItem(id="direct", entity_id=direct_entry.id, source_text=direct),
            EvidenceItem(id="bonus", entity_id=bonus_entry.id, source_text=bonus),
        ],
    )
    posting = JobPosting(
        id=f"{title}-posting",
        title=title,
        description=f"Required:\n{required}\nPreferred:\n{bonus} is a bonus.",
    )

    ranked = _rank(profile, posting)

    assert ranked["direct"].relationship is EvidenceRelationship.DIRECT
    assert ranked["direct"].score > ranked["bonus"].score


def test_flat_skill_rows_are_coherent_provenance_preserving_and_non_mutating() -> None:
    entry = ResumeItem(
        id="systems-entry",
        title="Embedded Systems Engineer",
        kind=EntityKind.EXPERIENCE,
    )
    declared = [
        "C++",
        "Python",
        "Reviewed unrelated item",
        "STM32",
        "GPIO",
        "UART",
        "I2C",
        "SPI",
        "ADC/DAC Configuration",
        "ROS 2",
        "OpenCV",
        "YOLOv8",
    ]
    profile = _profile(
        experiences=[entry],
        declared_skills=declared,
        evidence=[
            EvidenceItem(
                id="systems-proof",
                entity_id=entry.id,
                source_text=(
                    "Built STM32 firmware in C++ and Python, validated GPIO, UART, "
                    "I2C, SPI, and ADC/DAC, and integrated ROS 2 with OpenCV and YOLOv8."
                ),
            )
        ],
    )
    original = profile.model_dump(mode="json")
    posting = JobPosting(
        id="flat-skill-posting",
        title="Embedded Systems Engineer",
        description=(
                "Required: Build C++ and Python STM32 firmware using GPIO, UART, I2C, "
                "SPI, and ADC. Preferred: ROS 2 image processing."
        ),
    )
    resume = DeterministicResumeComposer(_FixedPageFit()).compose(
        _baseline(profile, posting),
        profile,
        posting,
        TemplateConstraints(),
    )
    diagnostic = resume.composition_diagnostic

    assert diagnostic is not None
    assert len(diagnostic.selected_skill_rows) >= 2
    assert all(
        label not in {
            "Primary Technical Skills",
            "Supporting Technical Skills",
            "Additional Reviewed Skills",
        }
        for label in diagnostic.selected_skill_category_labels
    )
    displayed = {
        value
        for row in diagnostic.selected_skill_rows
        for value in row.skill_values
    }
    assert displayed <= set(declared)
    assert "Reviewed unrelated item" not in displayed
    assert {
        "C++",
        "Python",
        "STM32",
        "UART",
        "I2C",
        "SPI",
        "ADC/DAC Configuration",
    } <= displayed
    assert all(row.grouping_reason for row in diagnostic.selected_skill_rows)
    assert all(row.estimated_available_width_points > 500 for row in diagnostic.selected_skill_rows)
    assert all(
        abs(
            row.estimated_used_width_points
            + row.estimated_remaining_width_points
            - row.estimated_available_width_points
        ) <= 0.02
        for row in diagnostic.selected_skill_rows
    )
    assert all(
        source.startswith("profile.declared_skills[")
        for row in diagnostic.selected_skill_rows
        for source in row.provenance
    )
    assert set(diagnostic.omitted_direct_skill_values) <= set(
        diagnostic.omitted_direct_skill_reasons
    )
    assert profile.model_dump(mode="json") == original
