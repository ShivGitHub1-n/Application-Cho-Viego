from __future__ import annotations

import re
from collections import Counter

from tests.job_discovery.benchmark.loader import load_pilot_calibration_group_01
from tests.job_discovery.benchmark.metrics import proposed_reference_structural_validity


def test_pilot_group_has_ten_distinct_realistic_postings() -> None:
    cases = load_pilot_calibration_group_01()
    assert len(cases) == 10
    assert {case.ranking_group for case in cases} == {"calibration-group-01"}
    assert len({case.posting.title for case in cases}) == 10
    assert all(120 <= len(case.posting.description.split()) <= 300 for case in cases)
    assert all(2 <= len(case.posting.responsibilities) <= 6 for case in cases)
    assert all(case.posting.title in case.rationale for case in cases)
    for case in cases:
        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", case.posting.description)
            if sentence.strip()
        ]
        assert len(sentences) == len(set(sentences))
    assert not any(
        re.search(
            r"\b(the candidate(?:'s)?|profile|target|evidence|fit|grade|proposal|"
            r"career path|apply[- ]worthiness)\b",
            case.posting.description,
            re.I,
        )
        for case in cases
    )
    assert not any(
        re.search(
            r"\b(scenario|synthetic|marker|proposal|benchmark|human review)\b",
            case.posting.description,
            re.I,
        )
        for case in cases
    )


def test_pilot_postings_do_not_reuse_profile_sentences_or_boilerplate() -> None:
    cases = load_pilot_calibration_group_01()
    evidence_sentences = [item.statement for item in cases[0].profile.evidence_items]
    descriptions = [case.posting.description for case in cases]
    assert not any(
        any(sentence.lower() in description.lower() for description in descriptions)
        for sentence in evidence_sentences
    )
    sentence_counts = Counter(
        sentence.strip()
        for description in descriptions
        for sentence in re.split(r"(?<=[.!?])\s+", description)
        if sentence.strip()
    )
    assert max(sentence_counts.values()) <= 2
    assert all(
        "The team works with partner engineers" not in description
        and "practical ownership of the stated work" not in description
        and "Qualification:" not in description
        for description in descriptions
    )
    for statement in evidence_sentences:
        words = statement.casefold().split()
        assert not any(
            " ".join(words[index : index + 8]) in description.casefold()
            for description in descriptions
            for index in range(max(0, len(words) - 7))
        )


def test_pilot_labels_and_eligibility_are_grounded_individually() -> None:
    cases = load_pilot_calibration_group_01()
    assert sum(case.proposed_grade == "excellent" for case in cases) >= 1
    assert sum(case.proposed_grade == "good" for case in cases) >= 2
    assert sum(case.proposed_grade == "weak" for case in cases) >= 2
    assert sum(case.proposed_grade == "dont_match" for case in cases) >= 3
    assert any(case.expected_eligibility == "unknown" for case in cases)
    assert any(case.expected_eligibility == "ineligible" for case in cases)
    for case in cases:
        assert case.posting.title in case.rationale
        assert case.rationale
        assert not any(
            other.posting.title in case.rationale
            for other in cases
            if other.case_id != case.case_id
        )
        profile_ids = {item.evidence_id for item in case.profile.evidence_items}
        posting_ids = {
            item.requirement_id for item in case.critical_requirements
        } | {
            item.qualification_id
            for item in [*case.required_qualifications, *case.preferred_qualifications]
        }
        for reference in [
            reference
            for reason in [*case.proposed_positive_reasons, *case.proposed_material_gap_reasons]
            for reference in reason.evidence_references
        ]:
            known_ids = (
                profile_ids
                | posting_ids
                | {fact.fact_id for fact in case.posting.posting_facts}
                | {
                    f"preferences:{case.profile.profile_ref}:work_authorization",
                    f"preferences:{case.profile.profile_ref}:target_level",
                    f"profile:{case.profile.profile_ref}:experience-years",
                    f"profile:{case.profile.profile_ref}:education",
                }
            )
            assert reference in known_ids
        assert all(reason.evidence_references for reason in case.proposed_positive_reasons)
        assert all(reason.evidence_references for reason in case.proposed_material_gap_reasons)
        if case.expected_eligibility == "ineligible":
            assert case.proposed_grade == "dont_match"
            assert case.apply_worthy is False
            assert any(
                reason.posting_fact and reason.profile_fact
                for reason in case.proposed_eligibility_reasons
            )
        if case.proposed_grade == "excellent":
            assert case.scenario_category in {"software_engineering", "backend_engineering"}
            assert all(item.evidence_quality == "verified" for item in case.important_evidence)
            assert all(
                item.demonstrated
                for item in case.profile.evidence_items
                if item.evidence_id in {ref.reference for ref in case.important_evidence}
            )
        if case.proposed_grade == "weak":
            assert case.important_gaps
            assert any(
                any(
                    marker in reason.statement.casefold()
                    for marker in (
                        "rather than",
                        "gap",
                        "not demonstrated",
                        "reviewed",
                        "exceed",
                    )
                )
                for reason in case.important_gaps
            )


def test_pilot_has_at_least_fifteen_specific_non_tied_comparisons() -> None:
    cases = load_pilot_calibration_group_01()
    annotations = [
        (case.case_id, annotation.other_case_id, annotation.rationale)
        for case in cases
        for annotation in case.comparable_pair_annotations
    ]
    pairs = {tuple(sorted((left, right))) for left, right, _ in annotations}
    assert len(pairs) >= 15
    assert len({rationale for _, _, rationale in annotations}) >= 15
    assert all(len(rationale.split()) >= 6 for _, _, rationale in annotations)


def test_pilot_pair_directions_match_human_ranking_tiers() -> None:
    cases = load_pilot_calibration_group_01()
    by_id = {case.case_id: case for case in cases}
    rank = {"excellent": 0, "good": 1, "weak": 2, "dont_match": 3}
    for case in cases:
        for pair in case.comparable_pair_annotations:
            other = by_id[pair.other_case_id]
            if case.proposed_grade == other.proposed_grade:
                continue
            expected = (
                "preferred_to_other"
                if rank[case.proposed_grade] < rank[other.proposed_grade]
                else "less_preferred_than_other"
            )
            assert pair.relationship == expected


def test_pilot_has_atomic_posting_facts_and_unique_requirement_ids() -> None:
    cases = load_pilot_calibration_group_01()
    for case in cases:
        fact_ids = [fact.fact_id for fact in case.posting.posting_facts]
        requirement_ids = [
            item.requirement_id if hasattr(item, "requirement_id") else item.qualification_id
            for item in [
                *case.critical_requirements,
                *case.required_qualifications,
                *case.preferred_qualifications,
            ]
        ]
        assert fact_ids and len(fact_ids) == len(set(fact_ids))
        assert len(requirement_ids) == len(set(requirement_ids))
        assert all(fact.statement for fact in case.posting.posting_facts)
        assert case.posting.posting_level != "unknown"


def test_pilot_references_have_structural_validity() -> None:
    cases = load_pilot_calibration_group_01()
    validity = proposed_reference_structural_validity(cases)
    assert validity["positive_reasons"]["total"] > 0
    assert validity["positive_reasons"]["complete"] == validity["positive_reasons"]["total"]
    assert validity["positive_reasons"]["valid"] == validity["positive_reasons"]["total"]
    assert validity["gap_reasons"]["complete"] == validity["gap_reasons"]["total"]
    assert validity["gap_reasons"]["valid"] == validity["gap_reasons"]["total"]
    for case in cases:
        all_gap_refs = {
            ref
            for reason in case.proposed_material_gap_reasons
            for ref in reason.evidence_references
        }
        for requirement in [
            *case.critical_requirements,
            *case.required_qualifications,
        ]:
            requirement_id = (
                requirement.requirement_id
                if hasattr(requirement, "requirement_id")
                else requirement.qualification_id
            )
            assert requirement.evidence_references or requirement_id in all_gap_refs or any(
                fact.fact_id in all_gap_refs
                for fact in case.posting.posting_facts
                if requirement.text.casefold() in fact.statement.casefold()
            )


def test_pilot_reason_and_reference_collections_are_idempotent() -> None:
    for case in load_pilot_calibration_group_01():
        assert len(case.review_tags) == len(set(case.review_tags))
        assert len(case.provisional_reason_codes) == len(set(case.provisional_reason_codes))
        positive = case.proposed_positive_reasons
        gaps = case.proposed_material_gap_reasons
        reason_keys = [
            (reason.code, reason.statement, tuple(reason.evidence_references))
            for reason in [*positive, *gaps]
        ]
        assert len(reason_keys) == len(set(reason_keys))
        assert all(
            len(reason.evidence_references) == len(set(reason.evidence_references))
            for reason in [*positive, *gaps]
        )
        assert case.proposed_reasons == [*positive, *gaps]


def test_pilot_positive_reason_reference_sets_are_exact() -> None:
    cases = {case.case_id: case for case in load_pilot_calibration_group_01()}
    expected = {
        "calibration-004": {
            "python_api": {
                "profile:pilot-backend:python-api",
                "posting:calibration-004:critical:python",
                "posting:calibration-004:required:api-contracts",
            }
        },
        "calibration-006": {
            "incident_operations": {
                "profile:pilot-backend:operations",
                "posting:calibration-006:required:linux",
                "posting:calibration-006:required:containers",
                "posting:calibration-006:required:incident-response",
            }
        },
        "calibration-008": {
            "technical_overlap": {
                "profile:pilot-backend:python-api",
                "posting:calibration-008:critical:python",
                "profile:pilot-backend:postgres",
                "posting:calibration-008:required:postgresql",
            }
        },
        "calibration-009": {
            "preferred_technology": {
                "profile:pilot-backend:python-api",
                "posting:calibration-009:preferred:python",
                "profile:pilot-backend:postgres",
                "posting:calibration-009:preferred:postgresql",
            }
        },
        "calibration-010": {
            "transferable_overlap": {
                "profile:pilot-backend:python-api",
                "posting:calibration-010:preferred:python",
                "profile:pilot-backend:operations",
                "posting:calibration-010:preferred:docker",
            }
        },
    }
    for case_id, reasons in expected.items():
        by_code = {
            reason.code: set(reason.evidence_references)
            for reason in cases[case_id].proposed_positive_reasons
        }
        for code, references in reasons.items():
            assert by_code[code] == references


def test_pilot_insufficient_evidence_is_not_a_matched_qualification() -> None:
    cases = {case.case_id: case for case in load_pilot_calibration_group_01()}
    for case_id, requirement_id in (
        ("calibration-005", "posting:calibration-005:required:quality-years"),
        ("calibration-009", "posting:calibration-009:critical:eight-years"),
    ):
        case = cases[case_id]
        requirement = next(
            item
            for item in [*case.critical_requirements, *case.required_qualifications]
            if (item.requirement_id if hasattr(item, "requirement_id") else item.qualification_id)
            == requirement_id
        )
        assert requirement.evidence_references == []
        assert any(
            requirement_id in reason.evidence_references
            and any(reference.startswith("profile:") for reference in reason.evidence_references)
            for reason in case.proposed_material_gap_reasons
        )
    production_years = next(
        item for item in cases["calibration-006"].required_qualifications
        if item.qualification_id == "posting:calibration-006:required:production-years"
    )
    assert set(production_years.evidence_references) == {
        "profile:cal-profile-pilot-01:experience-years",
        "profile:pilot-backend:operations",
    }


def test_pilot_case_007_recognizes_peripheral_evidence() -> None:
    case = next(
        case
        for case in load_pilot_calibration_group_01()
        if case.case_id == "calibration-007"
    )
    assert case.evidence_assessment.quality != "absent"
    assert {
        "profile:pilot-backend:operations",
        "posting:calibration-007:required:written-communication",
        "profile:cal-profile-pilot-01:education",
        "posting:calibration-007:preferred:technical-degree",
    } <= {
        reference
        for reason in case.proposed_positive_reasons
        for reference in reason.evidence_references
    }
    assert "public-infrastructure" not in {
        reference
        for item in case.preferred_qualifications
        if item.qualification_id.endswith("public-infrastructure")
        for reference in item.evidence_references
    }


def test_pilot_preferred_matches_are_referenced_and_source_text_is_spaced() -> None:
    cases = {case.case_id: case for case in load_pilot_calibration_group_01()}
    expected = {
        "calibration-001": ("payment-accounting", {"profile:pilot-backend:postgres"}),
        "calibration-004": ("subscription-data", {"profile:pilot-backend:postgres"}),
        "calibration-008": ("docker", {"profile:pilot-backend:operations"}),
    }
    for case_id, (suffix, references) in expected.items():
        qualification = next(
            item for item in cases[case_id].preferred_qualifications
            if item.qualification_id.endswith(suffix)
        )
        assert set(qualification.evidence_references) == references
    assert "contracts.Required" not in cases["calibration-004"].posting.description
    assert not any(
        re.search(r"[,;:][A-Z]", case.posting.description)
        for case in cases.values()
    )


def test_pilot_boundary_cases_use_the_correct_atomic_facts() -> None:
    cases = {case.case_id: case for case in load_pilot_calibration_group_01()}
    case003 = cases["calibration-003"]
    assert any("cloud-platform" in fact.fact_id for fact in case003.posting.posting_facts)
    assert any(
        "cloud-platform" in ref
        for reason in case003.proposed_material_gap_reasons
        for ref in reason.evidence_references
    )
    case004 = cases["calibration-004"]
    assert any("event-driven" in fact.fact_id for fact in case004.posting.posting_facts)
    assert any(
        "event-driven" in ref
        for reason in case004.proposed_material_gap_reasons
        for ref in reason.evidence_references
    )
    case006 = cases["calibration-006"]
    assert any(
        "kubernetes" in fact.fact_id
        and fact.kind in {"critical_requirement", "required_qualification"}
        for fact in case006.posting.posting_facts
    )
    assert any(
        "kubernetes" in ref
        for reason in case006.proposed_material_gap_reasons
        for ref in reason.evidence_references
    )
    case008 = cases["calibration-008"]
    assert {
        "posting:calibration-008:eligibility:austin-onsite",
        "posting:calibration-008:eligibility:us-authorization",
        "posting:calibration-008:eligibility:no-sponsorship",
    } <= {fact.fact_id for fact in case008.posting.posting_facts}
    assert all(
        "python" not in ref
        for reason in case008.proposed_eligibility_reasons
        for ref in reason.evidence_references
    )
    case009 = cases["calibration-009"]
    assert case009.expected_eligibility == "ineligible"
    assert "ineligible" in case009.rationale.casefold()
    assert any("staff-level" in fact.statement.casefold() for fact in case009.posting.posting_facts)
    case010 = cases["calibration-010"]
    gap_refs = {
        ref
        for reason in case010.proposed_material_gap_reasons
        for ref in reason.evidence_references
    }
    assert {
        "posting:calibration-010:critical:go",
        "posting:calibration-010:critical:terraform",
        "posting:calibration-010:critical:kubernetes",
    } <= gap_refs


def test_pilot_requirements_use_their_atomic_posting_fact_ids() -> None:
    for case in load_pilot_calibration_group_01():
        facts = {fact.fact_id for fact in case.posting.posting_facts}
        for item in [
            *case.critical_requirements,
            *case.required_qualifications,
            *case.preferred_qualifications,
        ]:
            item_id = (
                item.requirement_id
                if hasattr(item, "requirement_id")
                else item.qualification_id
            )
            assert item_id in facts
            assert item.fact_id == item_id


def test_pilot_profile_level_facts_are_used_for_duration_and_education() -> None:
    cases = load_pilot_calibration_group_01()
    profile_ref = cases[0].profile.profile_ref
    reason_refs = {
        reference
        for case in cases
        for reason in [*case.proposed_positive_reasons, *case.proposed_material_gap_reasons]
        for reference in reason.evidence_references
    }
    assert f"profile:{profile_ref}:experience-years" in reason_refs
    assert f"profile:{profile_ref}:education" in reason_refs


def test_pilot_case_boundaries_use_correct_authority() -> None:
    cases = {case.case_id: case for case in load_pilot_calibration_group_01()}
    case003 = cases["calibration-003"]
    assert "required_noncritical_gap" in case003.review_tags
    assert "preferred gap" not in case003.rationale.casefold()
    case006 = cases["calibration-006"]
    assert any(
        fact.fact_id == "posting:calibration-006:required:kubernetes-incident-operation"
        and fact.kind == "required_qualification"
        for fact in case006.posting.posting_facts
    )
    assert not any(
        "critical" in fact.fact_id
        for fact in case006.posting.posting_facts
        if "kubernetes" in fact.fact_id
    )
    assert "mid/senior" in cases["calibration-009"].rationale.casefold()
    assert "staff-level organizational authority" in cases["calibration-009"].rationale.casefold()


def test_only_visible_cases_are_paired_and_excluded_cases_are_not_apply_worthy() -> None:
    cases = load_pilot_calibration_group_01()
    visible = [case for case in cases if case.normal_feed_visible]
    assert [case.case_id for case in visible] == [
        f"calibration-{index:03d}" for index in range(1, 7)
    ]
    pairs = {
        tuple(sorted((case.case_id, pair.other_case_id)))
        for case in cases
        for pair in case.comparable_pair_annotations
    }
    assert len(pairs) == 15
    assert all(left <= "calibration-006" and right <= "calibration-006" for left, right in pairs)
    assert all(not case.apply_worthy for case in cases if not case.normal_feed_visible)
