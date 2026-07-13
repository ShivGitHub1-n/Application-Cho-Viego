import pytest

from resume_tailor.application.llm_services import HybridLlmServices
from resume_tailor.application.plan_validation import (
    DeterministicPlanIntegrityValidator,
    PlanIntegrityError,
)
from resume_tailor.application.skill_selection import DeterministicSkillSelector
from resume_tailor.application.skill_composition import (
    DeterministicSkillCompositionReconciler,
    SkillCompositionReconciliationError,
)
from resume_tailor.domain.llm_models import (
    LanguageModelError,
    LanguageModelErrorKind,
    LlmOperation,
    ProposedSkill,
    ProposedSkillCategory,
    SkillCompositionOutput,
    SkillCompositionResult,
)
from resume_tailor.domain.models import (
    EducationRecord,
    EntityKind,
    EvidenceItem,
    JobPosting,
    MasterProfile,
    ResumeItem,
    ReviewedTechnicalSkill,
    RoleClassification,
    RoleFamily,
    RoleSignal,
    SkillSelectionStatus,
    TechnicalSkillCategory,
    TemplateConstraints,
)
from resume_tailor.infrastructure.optimization import (
    DeterministicResumeOptimizer,
    EvidenceBoundResumeWriter,
)
from tests.fakes import FakeResumeLanguageModel, metadata


def _inputs() -> tuple[MasterProfile, JobPosting]:
    profile = MasterProfile(
        id="skills-profile",
        user_id="skills-user",
        display_name="Candidate",
        education=[
            EducationRecord(
                school="Reviewed University",
                program="Reviewed Program",
                expected_graduation_date="2027",
            )
        ],
        technical_skills=[
            TechnicalSkillCategory(
                category="Languages & Frameworks",
                values=["Python", "FastAPI", "Unrelated Legacy Tool"],
            ),
            TechnicalSkillCategory(
                category="Delivery Systems",
                values=["Docker", "Kubernetes", "Unrelated Process"],
            ),
            TechnicalSkillCategory(
                category="Physical Prototyping",
                values=["Sheet Metal", "Manual Milling"],
            ),
            TechnicalSkillCategory(
                category="Future Unseen Category Label",
                values=["PostgreSQL", "Python"],
            ),
        ],
        experiences=[
            ResumeItem(
                id="backend-role",
                title="Backend Developer",
                kind=EntityKind.EXPERIENCE,
                organization="Reviewed Employer",
            )
        ],
        projects=[
            ResumeItem(id="api-project", title="API Project", kind=EntityKind.PROJECT)
        ],
        evidence=[
            EvidenceItem(
                id="backend-evidence",
                entity_id="backend-role",
                source_text="Built Python FastAPI backend services with Docker.",
                technologies=["Python", "FastAPI", "Docker"],
            ),
            EvidenceItem(
                id="project-evidence",
                entity_id="api-project",
                source_text="Built a PostgreSQL API data service.",
                technologies=["PostgreSQL", "API"],
            ),
        ],
    )
    posting = JobPosting(
        id="skills-posting",
        title="Backend Software Engineer",
        description=(
            "Build Python and FastAPI backend APIs. Required: Docker and PostgreSQL. "
            "Preferred: Kubernetes deployment experience."
        ),
    )
    return profile, posting


def _plan(max_skill_lines: int = 3):
    profile, posting = _inputs()
    optimizer = DeterministicResumeOptimizer()
    plan = optimizer.create_plan(
        profile,
        posting,
        TemplateConstraints(
            max_total_lines=30,
            max_experience_lines=15,
            max_project_lines=10,
            max_skill_lines=max_skill_lines,
        ),
    )
    return profile, posting, optimizer, plan


def _proposal(plan, *, category_ids=None, skills_by_category=None):
    ranked = {category.id: category for category in plan.ranked_skill_categories}
    category_ids = category_ids or [category.id for category in plan.selected_skill_categories]
    categories = []
    for category_id in category_ids:
        category = ranked[category_id]
        skill_ids = (skills_by_category or {}).get(
            category_id,
            [
                skill.id
                for skill in category.skills
                if skill.status != SkillSelectionStatus.EXCLUDED_UNRELATED
            ],
        )
        categories.append(
            ProposedSkillCategory(
                category_id=category.id,
                label=category.label,
                skills=[
                    ProposedSkill(
                        skill_id=skill_id,
                        value=next(skill.value for skill in category.skills if skill.id == skill_id),
                    )
                    for skill_id in skill_ids
                ],
            )
        )
    return SkillCompositionOutput(categories=categories, rationale="Prefer focused backend skills.")


def test_arbitrary_categories_normalize_with_stable_ids_and_exact_values() -> None:
    first, _ = _inputs()
    second, _ = _inputs()

    assert [category.id for category in first.technical_skills] == [
        category.id for category in second.technical_skills
    ]
    assert [
        skill.id for category in first.technical_skills for skill in category.skills
    ] == [skill.id for category in second.technical_skills for skill in category.skills]
    assert [category.category for category in first.technical_skills] == [
        "Languages & Frameworks",
        "Delivery Systems",
        "Physical Prototyping",
        "Future Unseen Category Label",
    ]
    assert first.technical_skills[0].values == [
        "Python",
        "FastAPI",
        "Unrelated Legacy Tool",
    ]
    mapped = MasterProfile(
        id="mapped",
        user_id="mapped",
        display_name="Mapped",
        technical_skills={"Never-Before-Seen Group": ["Novel Tool"]},
    )
    assert mapped.technical_skills[0].category == "Never-Before-Seen Group"
    assert mapped.technical_skills[0].values == ["Novel Tool"]
    supplied = MasterProfile(
        id="supplied",
        user_id="supplied",
        display_name="Supplied",
        technical_skills=[
            TechnicalSkillCategory(
                id="reviewed-category-id",
                category="Reviewed Label",
                skills=[ReviewedTechnicalSkill(id="reviewed-skill-id", value="Reviewed Value")],
            )
        ],
    )
    assert supplied.technical_skills[0].id == "reviewed-category-id"
    assert supplied.technical_skills[0].skills[0].id == "reviewed-skill-id"


def test_duplicates_are_removed_from_later_category_without_moving_the_skill() -> None:
    profile, _ = _inputs()
    assert "Python" in profile.technical_skills[0].values
    assert "Python" not in profile.technical_skills[-1].values
    decision = profile.skill_normalization_decisions[0]
    assert decision.action == "removed_duplicate"
    assert decision.retained_category_id == profile.technical_skills[0].id


def test_relevance_scores_categories_and_skills_without_selecting_weak_neighbors() -> None:
    _, _, _, plan = _plan()
    categories = {category.label: category for category in plan.ranked_skill_categories}
    languages = categories["Languages & Frameworks"]
    physical = categories["Physical Prototyping"]
    assert languages.relevance_score > physical.relevance_score
    scores = {skill.value: skill.relevance_score for skill in languages.skills}
    assert scores["Python"] > scores["Unrelated Legacy Tool"]
    selected_values = {
        skill.value for category in plan.selected_skill_categories for skill in category.skills
    }
    assert "Python" in selected_values
    assert "Unrelated Legacy Tool" not in selected_values
    assert categories["Delivery Systems"].relevance_score > categories["Physical Prototyping"].relevance_score
    assert (
        categories["Languages & Frameworks"].relevance_score
        > categories["Future Unseen Category Label"].relevance_score
    )


def test_general_alias_normalization_scores_reviewed_value_without_rewriting_it() -> None:
    profile = MasterProfile(
        id="alias",
        user_id="alias",
        display_name="Alias",
        technical_skills=[TechnicalSkillCategory(category="Web Tools", values=["JavaScript"])],
    )
    role = RoleClassification(
        role_family=RoleFamily.SOFTWARE_DATA_ENGINEERING,
        confidence=1,
        supported=True,
        signals=[
            RoleSignal(
                id="web",
                label="web development",
                keywords=["javascript"],
                weight=1,
                family=RoleFamily.SOFTWARE_DATA_ENGINEERING,
            )
        ],
    )
    result = DeterministicSkillSelector().select(
        profile,
        JobPosting(id="alias-posting", title="JS Engineer", description="Build JS services."),
        role,
        1,
    )
    skill = result.selected[0].skills[0]
    assert skill.value == "JavaScript"
    assert skill.relevance_score == 100


def test_ranked_alternates_remain_grouped_and_authoritative_plan_is_not_flattened() -> None:
    profile, _, _, plan = _plan(max_skill_lines=1)
    assert len(plan.selected_skill_categories) == 1
    assert any(
        category.status == SkillSelectionStatus.ALTERNATE
        for category in plan.ranked_skill_categories
    )
    assert {category.original_order for category in plan.ranked_skill_categories} == {0, 1, 2, 3}
    assert [category.selected_order for category in plan.selected_skill_categories] == [0]
    source_categories = {
        skill.id: category.id
        for category in profile.technical_skills
        for skill in category.skills
    }
    assert all(
        source_categories[skill.id] == category.id
        for category in plan.ranked_skill_categories
        for skill in category.skills
    )
    assert plan.technical_skills
    assert all(category.skills for category in plan.technical_skills)
    assert plan.selected_skills == [
        skill.value for category in plan.selected_skill_categories for skill in category.skills
    ]


def test_structured_resume_receives_categories_and_derived_legacy_flat_values() -> None:
    profile, _, _, plan = _plan()
    resume = EvidenceBoundResumeWriter().write(plan, profile, set())
    assert resume.technical_skills == plan.technical_skills
    assert resume.education == profile.education
    assert resume.selected_skills == [
        skill.value for category in plan.selected_skill_categories for skill in category.skills
    ]


def test_valid_skill_composition_reorders_and_narrows_without_touching_entries() -> None:
    profile, _, _, plan = _plan()
    original_entities = plan.selected_entity_ids
    original_claims = plan.selected_claim_ids
    original_education = plan.education
    reversed_ids = [category.id for category in reversed(plan.selected_skill_categories)]
    first = next(category for category in plan.ranked_skill_categories if category.id == reversed_ids[0])
    one_skill = next(
        skill.id for skill in first.skills if skill.status != SkillSelectionStatus.EXCLUDED_UNRELATED
    )
    output = _proposal(
        plan,
        category_ids=reversed_ids,
        skills_by_category={reversed_ids[0]: [one_skill]},
    )

    reconciled = DeterministicSkillCompositionReconciler().reconcile(plan, profile, output)

    assert [category.id for category in reconciled.selected_skill_categories] == reversed_ids
    assert [skill.id for skill in reconciled.selected_skill_categories[0].skills] == [one_skill]
    assert reconciled.selected_entity_ids == original_entities
    assert reconciled.selected_claim_ids == original_claims
    assert reconciled.education == original_education


def test_typed_model_skill_composition_is_applied_through_hybrid_service() -> None:
    profile, posting, _, plan = _plan()
    output = _proposal(
        plan,
        category_ids=[plan.selected_skill_categories[-1].id],
    )
    fake = FakeResumeLanguageModel(
        recommend_skill_composition=SkillCompositionResult(
            metadata=metadata(LlmOperation.RECOMMEND_SKILL_COMPOSITION),
            output=output,
        )
    )
    hybrid = HybridLlmServices(fake, 0, 1, False, True, False)

    enriched = hybrid.enrich_plan(plan, profile, posting)

    assert [category.id for category in enriched.selected_skill_categories] == [
        plan.selected_skill_categories[-1].id
    ]
    assert enriched.skill_composition_selection is not None


@pytest.mark.parametrize(
    "mutation",
    ["category", "skill", "label", "value", "move", "duplicate", "duplicate_category"],
)
def test_invalid_skill_composition_is_rejected(mutation: str) -> None:
    profile, _, _, plan = _plan()
    output = _proposal(plan)
    categories = list(output.categories)
    first = categories[0]
    if mutation == "category":
        categories[0] = first.model_copy(update={"category_id": "invented-category"})
    elif mutation == "skill":
        categories[0] = first.model_copy(
            update={"skills": [ProposedSkill(skill_id="invented-skill", value="Invented")]}
        )
    elif mutation == "label":
        categories[0] = first.model_copy(update={"label": "Renamed Category"})
    elif mutation == "value":
        categories[0] = first.model_copy(
            update={"skills": [first.skills[0].model_copy(update={"value": "Renamed Skill"})]}
        )
    elif mutation == "move":
        other = categories[1]
        categories[0] = first.model_copy(update={"skills": [other.skills[0]]})
    elif mutation == "duplicate":
        categories[0] = first.model_copy(update={"skills": [first.skills[0], first.skills[0]]})
    else:
        categories.append(first)
    invalid = output.model_copy(update={"categories": categories})

    with pytest.raises(SkillCompositionReconciliationError):
        DeterministicSkillCompositionReconciler().reconcile(plan, profile, invalid)


def test_integrity_validator_replays_skill_composition_and_rejects_metadata_mutation() -> None:
    profile, _, optimizer, plan = _plan()
    reconciled = DeterministicSkillCompositionReconciler().reconcile(
        plan, profile, _proposal(plan)
    )
    DeterministicPlanIntegrityValidator(optimizer).validate(reconciled, profile)

    category = reconciled.ranked_skill_categories[0]
    mutated = reconciled.model_copy(
        update={
            "ranked_skill_categories": [
                category.model_copy(update={"relevance_score": category.relevance_score + 1}),
                *reconciled.ranked_skill_categories[1:],
            ]
        }
    )
    with pytest.raises(PlanIntegrityError, match="ranked_skill_categories"):
        DeterministicPlanIntegrityValidator(optimizer).validate(mutated, profile)


@pytest.mark.parametrize(
    "response",
    [
        LanguageModelError(LanguageModelErrorKind.UNAVAILABLE, "unavailable"),
        SkillCompositionResult(
            metadata=metadata(LlmOperation.RECOMMEND_SKILL_COMPOSITION),
            output=SkillCompositionOutput(
                categories=[
                    ProposedSkillCategory(
                        category_id="invented",
                        label="Invented",
                        skills=[ProposedSkill(skill_id="invented", value="Invented")],
                    )
                ],
                rationale="Invalid proposal.",
            ),
        ),
    ],
)
def test_provider_or_grounding_failure_preserves_deterministic_categories(response) -> None:
    profile, posting, _, plan = _plan()
    fake = FakeResumeLanguageModel(recommend_skill_composition=response)
    enriched = HybridLlmServices(fake, 0, 1, False, True, False).enrich_plan(
        plan, profile, posting
    )

    assert enriched.selected_skill_categories == plan.selected_skill_categories
    assert enriched.ranked_skill_categories == plan.ranked_skill_categories
    assert enriched.technical_skills == plan.technical_skills
    assert any(
        decision.action == "gemini_skill_fallback"
        for decision in enriched.report.decisions
    )


def test_malformed_categories_fail_cleanly() -> None:
    with pytest.raises(ValueError, match="non-empty label"):
        MasterProfile(
            id="bad",
            user_id="bad",
            display_name="Bad",
            technical_skills=[TechnicalSkillCategory(category=" ", values=["Python"])],
        )
    with pytest.raises(ValueError, match="empty skill"):
        MasterProfile(
            id="bad-skill",
            user_id="bad",
            display_name="Bad",
            technical_skills=[TechnicalSkillCategory(category="Any Label", values=[" "])],
        )
