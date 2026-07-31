from __future__ import annotations

import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from resume_tailor.domain.job_discovery.capabilities import ProfileCapabilityIndexBuilder
from resume_tailor.domain.job_discovery.location import parse_location
from resume_tailor.domain.job_discovery.models import (
    ProfileCapabilityIndex,
    WorkArrangement,
)
from resume_tailor.domain.job_discovery.requirements import (
    JOB_REQUIREMENT_TERM_CATALOG,
    RequirementExtractor,
)
from resume_tailor.domain.models import MasterProfile


def test_required_term_absent_from_profile_is_extracted_without_profile():
    signals = RequirementExtractor().extract(
        "Software Engineer",
        "Required CUDA and Python.",
        None,
        WorkArrangement.UNKNOWN,
    )

    assert "cuda" in signals.required_terms
    assert "python" in signals.required_terms

    with_empty_profile = RequirementExtractor().extract(
        "Software Engineer",
        "Required CUDA and Python.",
        None,
        WorkArrangement.UNKNOWN,
        profile_index=ProfileCapabilityIndex(terms={}),
    )
    assert with_empty_profile.material_gaps == [
        "No reviewed profile evidence or skill was found for required cuda.",
        "No reviewed profile evidence or skill was found for required python.",
    ]


def test_profile_expansion_is_additive_and_does_not_hide_catalog_terms():
    profile = MasterProfile(
        id="profile-1",
        user_id="user-1",
        display_name="Candidate",
        experiences=[
            {
                "id": "entry-1",
                "title": "ML Engineer",
                "kind": "experience",
                "technologies": ["JAX"],
            }
        ],
    )
    profile_index = ProfileCapabilityIndexBuilder().build(profile)

    signals = RequirementExtractor().extract(
        "ML Engineer",
        "Required JAX and Python.",
        None,
        WorkArrangement.UNKNOWN,
        profile_index=profile_index,
    )

    assert "jax" in signals.required_terms
    assert "python" in signals.required_terms
    assert "jax" not in RequirementExtractor().extract(
        "ML Engineer", "Required JAX and Python.", None, WorkArrangement.UNKNOWN
    ).required_terms


def test_required_preferred_and_unknown_importance_are_distinguished():
    signals = RequirementExtractor().extract(
        "Software Engineer",
        "Required Python. Docker is preferred. SQL experience is useful.",
        None,
        WorkArrangement.UNKNOWN,
    )

    assert signals.required_terms == ["python"]
    assert signals.preferred_terms == ["docker"]
    assert signals.unknown_terms == ["sql"]


def test_requirement_categories_cover_experience_education_authorization_arrangement_and_role():
    signals = RequirementExtractor().extract(
        "Senior Software Engineer",
        (
            "Must have 3+ years of experience and a bachelor's degree. "
            "Candidates must be authorized to work in Canada. "
            "This is a hybrid role."
        ),
        "Toronto, ON, Canada",
        WorkArrangement.UNKNOWN,
    )

    assert signals.experience_years == 3
    assert signals.degree_requirements
    assert signals.degree_equivalent_experience is False
    assert signals.authorization_language
    assert signals.work_arrangement is WorkArrangement.HYBRID
    assert signals.location is not None
    assert signals.location.country_code == "CA"
    assert signals.job_level.value == "senior"


def test_degree_equivalent_experience_alternative_is_retained() -> None:
    signals = RequirementExtractor().extract(
        "Software Engineer",
        "A bachelor's degree or equivalent experience is required.",
        None,
        WorkArrangement.UNKNOWN,
    )

    assert signals.degree_requirements == ["bachelor's degree"]
    assert signals.degree_equivalent_experience is True


def test_responsibilities_are_extracted_but_marketing_language_is_not_a_requirement():
    signals = RequirementExtractor().extract(
        "Software Engineer",
        (
            "We are an innovative, fast-growing company with a world-class culture. "
            "You will design and test Python services. Join us to make an impact."
        ),
        None,
        WorkArrangement.UNKNOWN,
    )

    assert signals.responsibilities == ["You will design and test Python services."]
    assert "python" in signals.unknown_terms
    assert "innovative" not in signals.required_terms


def test_incomplete_description_remains_deterministic_and_unknown():
    signals = RequirementExtractor().extract(
        "Backend Engineer",
        "",
        None,
        WorkArrangement.UNKNOWN,
    )

    assert signals.required_terms == []
    assert signals.preferred_terms == []
    assert signals.responsibilities == []
    assert signals.location is None


def test_catalog_is_authoritative_and_profile_independent():
    canonical_terms = {entry.canonical for entry in JOB_REQUIREMENT_TERM_CATALOG}

    assert {"python", "cuda", "docker", "ros2", "system design"} <= canonical_terms
    assert all(entry.canonical for entry in JOB_REQUIREMENT_TERM_CATALOG)
    assert all(entry.aliases for entry in JOB_REQUIREMENT_TERM_CATALOG)


@pytest.mark.parametrize(
    ("raw", "city", "region", "country"),
    [
        ("Toronto, ON, Canada", "toronto", "on", "CA"),
        ("Toronto, Ontario, Canada", "toronto", "on", "CA"),
        ("Austin, TX, United States", "austin", "tx", "US"),
        ("Ontario, Canada", None, "on", "CA"),
        ("Canada", None, None, "CA"),
    ],
)
def test_location_parser_supported_forms(raw, city, region, country):
    parsed = parse_location(raw)

    assert (parsed.city, parsed.region, parsed.country_code) == (city, region, country)
    assert parsed.parseable is True


def test_location_parser_leaves_unparseable_unknown():
    parsed = parse_location("Near a major metropolitan area")

    assert parsed.parseable is False
    assert parsed.country_code is None
    assert parsed.region is None
    assert parsed.city is None


def test_extraction_order_is_stable_across_calls_hash_seeds_and_inputs_are_unchanged():
    title = "Software Engineer"
    description = "Required Python and Docker. Preferred SQL."
    profile_index = ProfileCapabilityIndex(terms={})
    before = deepcopy((title, description, profile_index.model_dump(mode="python")))
    extractor = RequirementExtractor()

    first = extractor.extract(
        title, description, None, WorkArrangement.UNKNOWN, profile_index=profile_index
    )
    second = extractor.extract(
        title, description, None, WorkArrangement.UNKNOWN, profile_index=profile_index
    )

    assert first == second
    assert (title, description, profile_index.model_dump(mode="python")) == before

    script = (
        "import json; "
        "from resume_tailor.domain.job_discovery.models import WorkArrangement; "
        "from resume_tailor.domain.job_discovery.requirements import RequirementExtractor; "
        "print(RequirementExtractor().extract('Software Engineer', "
        "'Required Python and Docker. Preferred SQL.', None, "
        "WorkArrangement.UNKNOWN).model_dump_json())"
    )
    project_root = Path(__file__).resolve().parents[3]
    env = {**os.environ, "PYTHONPATH": str(project_root / "src")}
    outputs = []
    for seed in ("11", "22"):
        completed = subprocess.run(
            [sys.executable, "-c", script],
            check=True,
            capture_output=True,
            text=True,
            cwd=project_root,
            env={**env, "PYTHONHASHSEED": seed},
        )
        outputs.append(json.loads(completed.stdout))
    assert outputs[0] == outputs[1]
