from __future__ import annotations

import os
import subprocess
import sys
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest

from resume_tailor.domain.job_discovery.models import (
    ConnectorType,
    JobLevel,
    JobRequirementSignals,
    JobSearchPreferences,
    MatchLabel,
    ProfileCapabilityEvidence,
    ProfileCapabilityIndex,
    SourceJobRecord,
    SupportedJobSource,
    WorkArrangement,
)
from resume_tailor.domain.job_discovery.normalization import normalize_job_record
from resume_tailor.domain.job_discovery.requirements import RequirementExtractor
from resume_tailor.domain.job_discovery.scoring import (
    DeterministicExplanationBuilder,
    ScoringPolicy,
    recommendation_sort_key,
    score_label,
)
from resume_tailor.domain.models import RoleFamily

NOW = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


def _preferences(**overrides: object) -> JobSearchPreferences:
    values: dict[str, object] = {
        "user_id": "user-1",
        "profile_id": "profile-1",
        "version": 1,
        "role_family_priority": [RoleFamily.SOFTWARE_DATA_ENGINEERING],
        "target_titles": ["Software Engineer"],
        "related_title_variants": [],
        "technical_themes": ["python", "data engineering"],
        "career_interests": ["software and data engineering"],
        "job_levels": [],
        "locations": [],
        "work_arrangement": WorkArrangement.UNKNOWN,
        "preferred_companies": ["Acme Robotics"],
        "max_posting_age_days": 30,
        "created_at": NOW,
    }
    values.update(overrides)
    return JobSearchPreferences(**values)


def _job(
    description: str = (
        "Required Python, Docker, and robotics. Preferred SQL. "
        "You will perform sensor integration. Bachelor's degree."
    )
):
    source = SupportedJobSource(
        source_id="acme-board",
        connector_type=ConnectorType.GREENHOUSE,
        company_name="Acme Robotics",
        board_token="acme",
        enabled=True,
        official_base_url="https://boards.greenhouse.io",
    )
    return normalize_job_record(
        SourceJobRecord(
            external_job_id="1",
            title="Entry Level Software Engineer",
            company_name="Acme Robotics",
            description=description,
            official_url="https://boards.greenhouse.io/acme/jobs/1",
            location_raw="Toronto, ON, Canada",
            work_arrangement=WorkArrangement.REMOTE,
            posted_at=datetime(2026, 7, 10, tzinfo=UTC),
            source_updated_at=None,
            application_deadline=None,
            source_payload={},
        ),
        source,
        fetched_at=NOW,
    )


def _index(*, demonstrated: bool = True) -> ProfileCapabilityIndex:
    evidence = {
        term: [
            ProfileCapabilityEvidence(
                source_type="confirmed_evidence" if demonstrated else "reviewed_skill",
                source_id=f"source-{term}",
                source_text="Software Engineer",
                demonstrated=demonstrated,
            )
        ]
        for term in (
            "python",
            "docker",
            "robotics",
            "sql",
            "hardware",
            "sensor integration",
            "bachelor",
        )
    }
    return ProfileCapabilityIndex(terms=evidence)


def test_perfect_fit_uses_the_exact_100_point_budget() -> None:
    result = ScoringPolicy().score(
        _job(), _preferences(job_levels=[JobLevel.ENTRY]), _index(), as_of=NOW
    )

    assert result.demonstrated_technical_evidence == 30
    assert result.required_coverage == 20
    assert result.role_alignment == 0
    assert result.level_alignment == 10
    assert result.education_coursework == 10
    assert result.preferred_skill_alignment == 5
    assert result.transferable_evidence == 15
    assert result.recency_completeness == 0
    assert result.total == 100
    assert result.label is MatchLabel.STRONG
    assert 0 <= result.total <= 100
    robotics_requirement = next(
        item for item in _job().requirements.requirements if item.term == "robotics"
    )
    assert robotics_requirement.category.value == "role"
    assert robotics_requirement.importance.value == "required"


def test_contextual_required_capability_is_weighted_but_not_demonstrated() -> None:
    contextual = _index(demonstrated=False)
    result = ScoringPolicy().score(_job(), _preferences(), contextual, as_of=NOW)

    assert result.demonstrated_technical_evidence == 0
    assert result.required_coverage == 0


def test_empty_profile_does_not_receive_full_points_for_absent_evidence() -> None:
    result = ScoringPolicy().score(
        _job("Build systems."),
        _preferences(),
        ProfileCapabilityIndex(terms={}),
        as_of=NOW,
    )

    assert result.total < 55
    assert result.label is MatchLabel.STRETCH


def test_missing_requirements_are_gaps_and_do_not_create_positive_reasons() -> None:
    job = _job("Required CUDA and Python. You will design Python systems.")
    index = ProfileCapabilityIndex(terms={"python": _index().terms["python"]})

    reasons, gaps = DeterministicExplanationBuilder().reasons_and_gaps(
        job, job.requirements, index
    )

    assert "No reviewed profile evidence or skill was found for required cuda." in gaps
    assert not any("cuda" in reason for reason in reasons)


def test_demonstrated_responsibility_reason_uses_confirmed_capability() -> None:
    job = _job("You will design Python systems.")
    index = ProfileCapabilityIndex(terms={"python": _index().terms["python"]})

    reasons, _ = DeterministicExplanationBuilder().reasons_and_gaps(
        job, job.requirements, index
    )

    assert "Confirmed experience demonstrates python for this role." in reasons


def test_reason_and_gap_ordering_is_exact_and_context_is_not_overstated() -> None:
    job = _job("Required Python and CUDA. Preferred Docker.")
    index = ProfileCapabilityIndex(
        terms={
            "python": [
                ProfileCapabilityEvidence(
                    source_type="confirmed_evidence",
                    source_id="e-1",
                    source_text="Software Engineer",
                    demonstrated=True,
                )
            ],
            "docker": [
                ProfileCapabilityEvidence(
                    source_type="coursework",
                    source_id="course-1",
                    source_text="Docker",
                    demonstrated=False,
                )
            ],
            "cuda": [
                ProfileCapabilityEvidence(
                    source_type="reviewed_skill",
                    source_id="skill-1",
                    source_text="CUDA",
                    demonstrated=False,
                )
            ],
        }
    )

    reasons, gaps = DeterministicExplanationBuilder().reasons_and_gaps(
        job, job.requirements, index
    )

    assert reasons[0].startswith("Demonstrated python in ")
    assert all("CUDA" not in reason for reason in reasons)
    assert gaps == [
        "Reviewed profile mentions cuda, but no confirmed evidence item demonstrates it.",
        "Preferred docker is not present in reviewed profile evidence or skills.",
    ]


def test_preference_derived_reasons_require_matching_preference_facts() -> None:
    job = _job()
    preferences = _preferences(job_levels=[JobLevel.ENTRY])
    reasons, _ = DeterministicExplanationBuilder(preferences).reasons_and_gaps(
        job, job.requirements, _index()
    )

    assert not any(reason.startswith("Selected role family ") for reason in reasons)
    assert any(reason.startswith("Level compatibility was admitted") for reason in reasons)
    assert "Reviewed education or coursework matches bachelor's degree." in reasons
    assert not any("preferred-company" in reason for reason in reasons)


def test_preferred_company_is_a_deterministic_tie_break_not_a_score_component() -> None:
    preferred = _job()
    other = preferred.model_copy(
        update={
            "company_name": "Other Robotics",
            "normalized_company_name": "other robotics",
            "id": "job-other",
        }
    )
    preferences = _preferences()
    score = ScoringPolicy().score(preferred, preferences, _index(), as_of=NOW)

    assert recommendation_sort_key(preferred, score, preferences) < recommendation_sort_key(
        other, score, preferences
    )


@pytest.mark.parametrize(
    ("score", "label"),
    [
        (100.0, MatchLabel.STRONG),
        (85.0, MatchLabel.STRONG),
        (84.99, MatchLabel.GOOD),
        (70.0, MatchLabel.GOOD),
        (69.99, MatchLabel.STRETCH),
        (55.0, MatchLabel.STRETCH),
        (54.99, MatchLabel.STRETCH),
    ],
)
def test_match_label_boundaries(score: float, label: MatchLabel) -> None:
    assert score_label(score) is label


def test_missing_description_is_provisional_and_capped() -> None:
    result = ScoringPolicy().score(_job(""), _preferences(), _index(), as_of=NOW)

    assert result.provisional is True
    assert result.total <= 54
    assert result.label is MatchLabel.PROVISIONAL


def test_material_gaps_are_limited_to_three() -> None:
    job = _job().model_copy(
        update={
            "requirements": JobRequirementSignals(
                required_terms=["cuda", "go", "rust", "kubernetes"],
            )
        }
    )

    _, gaps = DeterministicExplanationBuilder().reasons_and_gaps(
        job, job.requirements, ProfileCapabilityIndex(terms={})
    )

    assert len(gaps) == 3


def test_scoring_is_pure_and_hash_seed_deterministic() -> None:
    job = _job()
    preferences = _preferences()
    index = _index()
    before = (deepcopy(job.model_dump(mode="python")), deepcopy(index.model_dump(mode="python")))

    first = ScoringPolicy().score(job, preferences, index, as_of=NOW)
    second = ScoringPolicy().score(job, preferences, index, as_of=NOW)

    assert first == second
    assert job.model_dump(mode="python") == before[0]
    assert index.model_dump(mode="python") == before[1]

    script = (
        "from resume_tailor.domain.job_discovery.scoring import score_label; "
        "print(score_label(84.99).value)"
    )
    root = Path(__file__).resolve().parents[3]
    env = {**os.environ, "PYTHONPATH": str(root / "src")}
    outputs = [
        subprocess.run(
            [sys.executable, "-c", script],
            check=True,
            capture_output=True,
            text=True,
            cwd=root,
            env={**env, "PYTHONHASHSEED": seed},
        ).stdout
        for seed in ("1", "2")
    ]
    assert outputs[0] == outputs[1]


def _synthetic_job(description: str, *, company: str = "Synthetic Labs"):
    return normalize_job_record(
        SourceJobRecord(
            external_job_id="synthetic",
            title="Controls Software Engineer",
            company_name=company,
            description=description,
            official_url="https://boards.greenhouse.io/synthetic/jobs/1",
            location_raw="Toronto, ON, Canada",
            work_arrangement=WorkArrangement.REMOTE,
            posted_at=datetime(2026, 7, 10, tzinfo=UTC),
            source_updated_at=None,
            application_deadline=None,
            source_payload={},
        ),
        SupportedJobSource(
            source_id="synthetic-board",
            connector_type=ConnectorType.GREENHOUSE,
            company_name=company,
            board_token="synthetic",
            enabled=True,
            official_base_url="https://boards.greenhouse.io",
        ),
        fetched_at=NOW,
    )


def _synthetic_index(*terms: str) -> ProfileCapabilityIndex:
    evidence = ProfileCapabilityEvidence(
        source_type="confirmed_evidence",
        source_id="rich-robotics-project",
        source_text="Robotics integration project",
        demonstrated=True,
    )
    return ProfileCapabilityIndex(terms={term: [evidence] for term in terms})


def test_relevant_occupational_responsibilities_outrank_generic_management() -> None:
    relevant = _synthetic_job(
        "Required robotics, Python, and ROS2. You will perform sensor integration "
        "and validate controls. Required bachelor's degree."
    )
    unrelated = _synthetic_job(
        "Manage change control, configuration governance, and documentation "
        "administration. Required bachelor's degree."
    )
    index = _synthetic_index("robotics", "python", "ros2", "sensor integration")

    relevant_score = ScoringPolicy().score(relevant, _preferences(), index, as_of=NOW)
    unrelated_score = ScoringPolicy().score(unrelated, _preferences(), index, as_of=NOW)

    assert relevant_score.total > unrelated_score.total
    assert relevant_score.occupational_gating_factor > unrelated_score.occupational_gating_factor
    assert unrelated_score.total < 10


def test_degree_text_cannot_rescue_an_unrelated_posting() -> None:
    with_degree = _synthetic_job(
        "Manage change control and configuration governance. Required bachelor's degree."
    )
    without_degree = _synthetic_job(
        "Manage change control and configuration governance."
    )
    index = _synthetic_index("robotics", "python")

    first = ScoringPolicy().score(with_degree, _preferences(), index, as_of=NOW)
    second = ScoringPolicy().score(without_degree, _preferences(), index, as_of=NOW)

    assert first.occupational_gating_factor == second.occupational_gating_factor == 0
    assert first.total == second.total == 0
    assert first.generic_points_suppressed > 0


def test_one_evidence_item_can_support_distinct_requirements_without_saturating_score() -> None:
    job = _synthetic_job(
        "Required robotics. You will perform sensor integration and validate controls. "
        "Required Python and ROS2. Preferred testing. Required bachelor's degree."
    )
    score = ScoringPolicy().score(
        job,
        _preferences(job_levels=[JobLevel.ENTRY]),
        _synthetic_index("robotics", "sensor integration", "python", "ros2", "testing"),
        as_of=NOW,
    )

    pairs = [
        allocation
        for allocation in score.evidence_allocation
        if "rich-robotics-project" in allocation.evidence_ids
    ]
    requirement_ids = {
        (allocation.category.value, allocation.term, allocation.importance.value)
        for allocation in pairs
    }
    assert len(requirement_ids) >= 2
    assert score.total < 100


def test_same_evidence_requirement_pair_is_not_credited_twice() -> None:
    job = _synthetic_job("Required robotics. You will perform robotics integration.")
    score = ScoringPolicy().score(job, _preferences(), _synthetic_index("robotics"), as_of=NOW)

    pair_ids = [
        (allocation.category.value, allocation.term, allocation.importance.value)
        for allocation in score.evidence_allocation
    ]
    assert len(pair_ids) == len(set(pair_ids))


def test_exact_duplicate_requirements_are_scored_once() -> None:
    job = _synthetic_job("Required robotics. Required robotics.")
    score = ScoringPolicy().score(job, _preferences(), _synthetic_index("robotics"), as_of=NOW)

    robotics_allocations = [
        allocation
        for allocation in score.evidence_allocation
        if allocation.term == "robotics"
    ]
    assert len(robotics_allocations) == 1
    assert score.required_coverage == 20


def test_role_family_classification_alone_contributes_zero_fit() -> None:
    job = _synthetic_job("Robotics systems use Python and ROS2.")
    score = ScoringPolicy().score(job, _preferences(), ProfileCapabilityIndex(terms={}), as_of=NOW)

    assert job.role_family is not None
    assert score.occupational_gating_factor == 0
    assert score.total == 0


def test_unknown_profile_terms_are_not_technology_evidence() -> None:
    job = _synthetic_job("Required quantum widget. Required bachelor's degree.")
    index = _synthetic_index("quantum widget")

    extracted = RequirementExtractor(index).extract(
        job.title,
        job.description,
        job.location.raw,
        job.work_arrangement,
    )
    requirement = next(item for item in extracted.requirements if item.term == "quantum widget")
    score = ScoringPolicy().score(
        job.model_copy(update={"requirements": extracted}),
        _preferences(),
        index,
        as_of=NOW,
    )

    assert requirement.category.value == "other"
    assert score.demonstrated_technical_evidence == 0
    assert score.required_coverage == 0


def test_recommendation_only_factors_do_not_change_profile_fit() -> None:
    job = _synthetic_job("Required Python and robotics.")
    index = _synthetic_index("python", "robotics")
    first = ScoringPolicy().score(
        job,
        _preferences(
            work_arrangement=WorkArrangement.REMOTE,
            preferred_companies=["Company A"],
        ),
        index,
        as_of=NOW,
    )
    second = ScoringPolicy().score(
        job,
        _preferences(
            work_arrangement=WorkArrangement.ONSITE,
            preferred_companies=["Company B"],
        ),
        index,
        as_of=datetime(2028, 1, 1, tzinfo=UTC),
    )

    assert first == second
    assert first.recency_completeness == 0
    assert "company preferences" in first.recommendation_only_factors_excluded


def test_missing_posting_details_are_provisional_not_fit_points() -> None:
    complete = _synthetic_job("Required Python and robotics.")
    incomplete = _synthetic_job("").model_copy(update={"completeness": ["missing_description"]})
    index = _synthetic_index("python", "robotics")

    complete_score = ScoringPolicy().score(complete, _preferences(), index, as_of=NOW)
    incomplete_score = ScoringPolicy().score(incomplete, _preferences(), index, as_of=NOW)

    assert complete_score.provisional is False
    assert incomplete_score.provisional is True
    assert incomplete_score.total == 0


def test_sentence_order_and_company_name_do_not_change_fit() -> None:
    first = _synthetic_job(
        "Required Python and robotics. You will perform sensor integration.",
        company="Company A",
    )
    second = _synthetic_job(
        "You will perform sensor integration. Required robotics and Python.",
        company="Company B",
    )
    index = _synthetic_index("python", "robotics", "sensor integration")

    assert ScoringPolicy().score(first, _preferences(), index, as_of=NOW) == ScoringPolicy().score(
        second, _preferences(), index, as_of=NOW
    )
