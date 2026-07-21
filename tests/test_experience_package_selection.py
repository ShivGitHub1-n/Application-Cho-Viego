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
from resume_tailor.domain.resume_composition import (
    ExperienceSingleBulletExceptionReason,
    PageFitEvaluation,
)


class _OnePageEvaluator:
    def evaluate(
        self,
        resume: object,
        *,
        attempt_exact: bool = True,
    ) -> PageFitEvaluation:
        return PageFitEvaluation(
            status=PageUtilizationStatus.ACCEPTABLE_ONE_PAGE,
            page_count=1,
            exact=attempt_exact,
            provider="experience-package-test",
            utilization_ratio=0.91,
            fits_one_page=True,
        )


def _profile(
    experiences: list[dict[str, object]],
    evidence: list[dict[str, object]],
    *,
    projects: list[dict[str, object]] | None = None,
) -> MasterProfile:
    return MasterProfile.model_validate(
        {
            "id": "package-profile",
            "user_id": "package-user",
            "display_name": "Package Candidate",
            "experiences": experiences,
            "projects": projects or [],
            "evidence": evidence,
        }
    )


def _compose(
    profile: MasterProfile,
    posting: JobPosting,
    *,
    maximum_experiences: int = 1,
    maximum_projects: int = 0,
    maximum_bullets: int = 4,
) -> StructuredResume:
    baseline = StructuredResume(
        profile_id=profile.id,
        profile_version=profile.version,
        posting_id=posting.id,
        template_id="managed-engineering-v1",
        display_name=profile.display_name,
        contact_line="candidate@example.com",
        strategy=ResumeStrategy(
            role_family="package_test",
            primary_focus=posting.title,
            rationale="Controlled package-selection regression.",
        ),
    )
    return DeterministicResumeComposer(
        _OnePageEvaluator(),
        bounds=CompositionSearchBounds(
            maximum_selected_bullets=maximum_bullets,
            maximum_selected_entries=maximum_experiences + maximum_projects,
            maximum_experience_entries=maximum_experiences,
            maximum_project_entries=maximum_projects,
        ),
    ).compose(baseline, profile, posting, TemplateConstraints())


def _posting() -> JobPosting:
    return JobPosting(
        id="package-posting",
        title="Backend Systems Engineer",
        description=(
            "Required: Build Python APIs. Important: test production services and "
            "automate reliable deployment workflows."
        ),
    )


def test_marginal_single_bullet_experience_is_omitted_for_coherent_package() -> None:
    profile = _profile(
        [
            {"id": "coherent", "title": "Software Engineer", "kind": "experience"},
            {"id": "fragment", "title": "Assistant", "kind": "experience"},
        ],
        [
            {
                "id": "coherent-api",
                "entity_id": "coherent",
                "source_text": "Built Python APIs for backend services.",
                "technologies": ["Python"],
            },
            {
                "id": "coherent-test",
                "entity_id": "coherent",
                "source_text": "Tested production services through reliable deployment checks.",
            },
            {
                "id": "fragment-doc",
                "entity_id": "fragment",
                "source_text": "Supported Python APIs and production service tests.",
                "technologies": ["Python"],
            },
        ],
    )

    resume = _compose(profile, _posting())
    diagnostic = resume.composition_diagnostic

    assert diagnostic is not None
    assert diagnostic.selected_experience_ids == ["coherent"]
    fragment = next(
        item for item in diagnostic.experience_package_selections if item.entry_id == "fragment"
    )
    assert fragment.coherent_block_minimum_failed is True
    assert fragment.single_bullet_exception_reason is None


def test_strong_three_bullet_package_defeats_weaker_two_bullet_package() -> None:
    profile = _profile(
        [
            {"id": "strong", "title": "Systems Developer", "kind": "experience"},
            {"id": "shallow", "title": "Application Assistant", "kind": "experience"},
        ],
        [
            {
                "id": "strong-api",
                "entity_id": "strong",
                "source_text": "Built Python APIs for distributed backend services.",
                "technologies": ["Python"],
            },
            {
                "id": "strong-test",
                "entity_id": "strong",
                "source_text": "Automated production service tests for reliable releases.",
            },
            {
                "id": "strong-deploy",
                "entity_id": "strong",
                "source_text": "Designed deployment checks for service failure handling.",
            },
            {
                "id": "shallow-api",
                "entity_id": "shallow",
                "source_text": "Updated one Python API example.",
                "technologies": ["Python"],
            },
            {
                "id": "shallow-test",
                "entity_id": "shallow",
                "source_text": "Reviewed one service test document.",
            },
        ],
    )

    resume = _compose(profile, _posting(), maximum_bullets=3)
    diagnostic = resume.composition_diagnostic

    assert diagnostic is not None
    assert diagnostic.selected_experience_ids == ["strong"]
    assert diagnostic.bullet_counts["strong"] == 3


def test_single_bullet_exception_requires_typed_unique_direct_reason() -> None:
    profile = _profile(
        [{"id": "unique", "title": "API Developer", "kind": "experience"}],
        [
            {
                "id": "unique-api",
                "entity_id": "unique",
                "source_text": (
                    "Built Python APIs that processed 2,000 reviewed service requests."
                ),
                "technologies": ["Python"],
                "metrics": ["2,000"],
                "capabilities": ["API development", "service request processing"],
            }
        ],
    )

    resume = _compose(profile, _posting(), maximum_bullets=1)
    diagnostic = resume.composition_diagnostic

    assert diagnostic is not None
    package = diagnostic.experience_package_selections[0]
    assert package.selected_bullet_count == 1
    assert package.single_bullet_exception_reason is (
        ExperienceSingleBulletExceptionReason.UNIQUE_DIRECT_REQUIREMENT_COVERAGE
    )


def test_project_may_supply_one_distinct_supplemental_bullet() -> None:
    profile = _profile(
        [{"id": "experience", "title": "Backend Developer", "kind": "experience"}],
        [
            {
                "id": "experience-api",
                "entity_id": "experience",
                "source_text": "Built Python APIs for backend services.",
                "technologies": ["Python"],
            },
            {
                "id": "experience-test",
                "entity_id": "experience",
                "source_text": "Tested production services through automated checks.",
            },
            {
                "id": "project-deploy",
                "entity_id": "deployment-project",
                "source_text": "Designed reliable deployment failure checks for a service project.",
            },
        ],
        projects=[{"id": "deployment-project", "title": "Deployment Monitor", "kind": "project"}],
    )

    resume = _compose(
        profile,
        _posting(),
        maximum_projects=1,
        maximum_bullets=3,
    )
    diagnostic = resume.composition_diagnostic

    assert diagnostic is not None
    assert diagnostic.bullet_counts["experience"] == 2
    assert diagnostic.bullet_counts["deployment-project"] == 1


def test_employer_identity_does_not_change_package_selection() -> None:
    experiences = [
        {
            "id": "first",
            "title": "Backend Developer",
            "kind": "experience",
            "organization": "Globally Famous Corporation",
        },
        {
            "id": "second",
            "title": "Backend Developer",
            "kind": "experience",
            "organization": "Local Workshop",
        },
    ]
    evidence = [
        {
            "id": f"{entry}-api",
            "entity_id": entry,
            "source_text": "Built Python APIs for backend services.",
            "technologies": ["Python"],
        }
        for entry in ("first", "second")
    ] + [
        {
            "id": f"{entry}-test",
            "entity_id": entry,
            "source_text": "Tested backend services through automated checks.",
        }
        for entry in ("first", "second")
    ]
    first = _compose(_profile(experiences, evidence), _posting())
    swapped = [
        {**experiences[0], "organization": experiences[1]["organization"]},
        {**experiences[1], "organization": experiences[0]["organization"]},
    ]
    second = _compose(_profile(swapped, evidence), _posting())

    assert first.composition_diagnostic is not None
    assert second.composition_diagnostic is not None
    assert (
        first.composition_diagnostic.selected_experience_ids
        == second.composition_diagnostic.selected_experience_ids
    )
    first_scores = {
        item.entry_id: item.best_package_alternatives[0].total_score
        for item in first.composition_diagnostic.experience_package_selections
    }
    second_scores = {
        item.entry_id: item.best_package_alternatives[0].total_score
        for item in second.composition_diagnostic.experience_package_selections
    }
    assert first_scores == second_scores


def test_stronger_project_can_displace_weaker_professional_package_with_marginal_diagnostic() -> (
    None
):
    profile = _profile(
        [{"id": "support-entry", "title": "Technical Assistant", "kind": "experience"}],
        [
            {
                "id": "support-api",
                "entity_id": "support-entry",
                "source_text": "Reviewed one Python API example.",
                "technologies": ["Python"],
            },
            {
                "id": "support-doc",
                "entity_id": "support-entry",
                "source_text": "Tested backend services through one automated deployment check.",
            },
            {
                "id": "project-api",
                "entity_id": "service-project",
                "source_text": "Built Python APIs for production backend services.",
                "technologies": ["Python"],
            },
            {
                "id": "project-test",
                "entity_id": "service-project",
                "source_text": "Automated service tests and reliable deployment checks.",
            },
        ],
        projects=[{"id": "service-project", "title": "Service Platform", "kind": "project"}],
    )

    resume = _compose(
        profile,
        _posting(),
        maximum_projects=1,
        maximum_bullets=2,
    )
    diagnostic = resume.composition_diagnostic

    assert diagnostic is not None
    assert diagnostic.selected_project_ids == ["service-project"]
    comparison = next(
        item
        for item in diagnostic.portfolio_marginal_comparisons
        if item.selected_entry_id == "service-project"
    )
    assert comparison.strongest_omitted_entry_id == "support-entry"
    assert comparison.page_cost_difference is not None
    assert comparison.selected_reason


def test_stronger_professional_package_can_displace_weaker_project() -> None:
    profile = _profile(
        [{"id": "service-entry", "title": "Backend Developer", "kind": "experience"}],
        [
            {
                "id": "entry-api",
                "entity_id": "service-entry",
                "source_text": "Built Python APIs for production backend services.",
                "technologies": ["Python"],
            },
            {
                "id": "entry-test",
                "entity_id": "service-entry",
                "source_text": "Automated service tests and reliable deployment checks.",
            },
            {
                "id": "project-example",
                "entity_id": "example-project",
                "source_text": "Reviewed one Python API example.",
                "technologies": ["Python"],
            },
        ],
        projects=[{"id": "example-project", "title": "API Example", "kind": "project"}],
    )

    resume = _compose(
        profile,
        _posting(),
        maximum_projects=1,
        maximum_bullets=2,
    )

    assert resume.composition_diagnostic is not None
    assert resume.composition_diagnostic.selected_experience_ids == ["service-entry"]
    assert resume.composition_diagnostic.selected_project_ids == []


def test_reviewed_production_evidence_breaks_close_package_tie() -> None:
    profile = _profile(
        [
            {"id": "plain", "title": "Backend Developer", "kind": "experience"},
            {
                "id": "production",
                "title": "Backend Developer",
                "kind": "experience",
                "description": "Reviewed production deployment context.",
            },
        ],
        [
            {
                "id": f"{entry}-api",
                "entity_id": entry,
                "source_text": "Built Python APIs for backend services.",
                "technologies": ["Python"],
            }
            for entry in ("plain", "production")
        ]
        + [
            {
                "id": f"{entry}-test",
                "entity_id": entry,
                "source_text": "Tested backend services through automated checks.",
            }
            for entry in ("plain", "production")
        ],
    )

    resume = _compose(profile, _posting())
    diagnostic = resume.composition_diagnostic

    assert diagnostic is not None
    assert diagnostic.selected_experience_ids == ["production"]
    production = next(
        item for item in diagnostic.experience_package_selections if item.entry_id == "production"
    )
    assert production.best_package_alternatives[0].enterprise_production_contribution > 0


def test_duration_and_recency_are_bounded_and_do_not_defeat_direct_relevance() -> None:
    profile = _profile(
        [
            {
                "id": "older-direct",
                "title": "Backend Developer",
                "kind": "experience",
                "start_date": "2018",
                "end_date": "2020",
            },
            {
                "id": "recent-adjacent",
                "title": "Documentation Assistant",
                "kind": "experience",
                "start_date": "2025",
                "end_date": "Present",
            },
        ],
        [
            {
                "id": "older-api",
                "entity_id": "older-direct",
                "source_text": "Built Python APIs for backend services.",
                "technologies": ["Python"],
            },
            {
                "id": "older-test",
                "entity_id": "older-direct",
                "source_text": "Automated production tests for reliable deployments.",
            },
            {
                "id": "recent-doc",
                "entity_id": "recent-adjacent",
                "source_text": "Documented Python API examples for one service.",
                "technologies": ["Python"],
            },
            {
                "id": "recent-review",
                "entity_id": "recent-adjacent",
                "source_text": "Reviewed deployment documentation with developers.",
            },
        ],
    )

    resume = _compose(profile, _posting())
    diagnostic = resume.composition_diagnostic

    assert diagnostic is not None
    assert diagnostic.selected_experience_ids == ["older-direct"]
    contributions = [
        alternative.duration_recency_contribution
        for item in diagnostic.experience_package_selections
        for alternative in item.best_package_alternatives
    ]
    assert contributions
    assert all(0 <= contribution <= 6 for contribution in contributions)
