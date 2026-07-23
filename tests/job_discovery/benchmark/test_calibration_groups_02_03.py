from __future__ import annotations

import csv
import json
import re
import tempfile
from pathlib import Path

from tests.job_discovery.benchmark.loader import load_calibration_group, load_development_cases
from tests.job_discovery.benchmark.metrics import (
    critical_gap_fact_ids,
    proposed_reference_structural_validity,
)
from tests.job_discovery.benchmark.report import generate_pilot_artifacts


def _groups() -> dict[str, list]:
    cases = load_development_cases()
    return {
        group: [case for case in cases if case.ranking_group == group]
        for group in ("calibration-group-02", "calibration-group-03")
    }


def test_groups_02_and_03_are_independent_realistic_ten_case_groups() -> None:
    groups = _groups()
    assert all(len(cases) == 10 for cases in groups.values())
    assert len({case.profile.profile_ref for cases in groups.values() for case in cases}) == 2
    profiles = [cases[0].profile for cases in groups.values()]
    assert profiles[0].evidence_items != profiles[1].evidence_items
    descriptions = [case.posting.description for cases in groups.values() for case in cases]
    assert all(120 <= len(description.split()) <= 300 for description in descriptions)
    assert all(
        len(
            sentences := [
                sentence.strip()
                for sentence in re.split(r"(?<=[.!?])\s+", description)
                if sentence.strip()
            ]
        )
        == len(set(sentences))
        for description in descriptions
    )
    assert not any(
        re.search(
            r"\b(benchmark|proposal|grade|fit|apply[- ]worthiness|"
            r"the candidate|profile evidence)\b",
            description,
            re.I,
        )
        for description in descriptions
    )


def test_groups_02_and_03_have_atomic_structural_coverage() -> None:
    for cases in _groups().values():
        validity = proposed_reference_structural_validity(cases)
        assert validity["qualification_coverage"]["coverage_rate"] == 1.0
        assert validity["validity_rate"] == 1.0
        for case in cases:
            facts = {fact.fact_id for fact in case.posting.posting_facts}
            records = [
                *case.critical_requirements,
                *case.required_qualifications,
                *case.preferred_qualifications,
            ]
            assert len(facts) == len(case.posting.posting_facts)
            assert all(
                record.fact_id
                == (
                    record.requirement_id
                    if hasattr(record, "requirement_id")
                    else record.qualification_id
                )
                and record.fact_id in facts
                for record in records
            )
            assert len(case.review_tags) == len(set(case.review_tags))
            assert len(case.provisional_reason_codes) == len(set(case.provisional_reason_codes))
            assert case.proposed_reasons == [
                *case.proposed_positive_reasons,
                *case.proposed_material_gap_reasons,
            ]


def test_groups_02_and_03_have_visible_only_pairs_and_numeric_ranking_inputs() -> None:
    for cases in _groups().values():
        visible = {case.case_id for case in cases if case.normal_feed_visible}
        pairs = {
            tuple(sorted((case.case_id, pair.other_case_id)))
            for case in cases
            for pair in case.comparable_pair_annotations
        }
        assert pairs
        assert all(left in visible and right in visible for left, right in pairs)
        assert not any(left not in visible and right not in visible for left, right in pairs)
        assert all(not case.apply_worthy for case in cases if not case.normal_feed_visible)


def test_group_specific_boundaries_and_evidence_authority() -> None:
    groups = _groups()
    data = {case.case_id: case for case in groups["calibration-group-02"]}
    ml = {case.case_id: case for case in groups["calibration-group-03"]}
    assert data["calibration-014"].proposed_grade == "weak"
    assert any(
        "streaming" in reason.statement.casefold()
        for reason in data["calibration-014"].proposed_material_gap_reasons
    )
    assert data["calibration-017"].expected_eligibility == "ineligible"
    assert data["calibration-018"].expected_eligibility == "ineligible"
    assert ml["calibration-024"].proposed_grade == "dont_match"
    assert ml["calibration-025"].expected_eligibility == "eligible"
    assert ml["calibration-026"].proposed_provisional is True
    assert critical_gap_fact_ids(data["calibration-014"]) == []
    assert critical_gap_fact_ids(ml["calibration-024"])


def test_source_postings_are_employer_facts_and_company_names_are_consistent() -> None:
    cases = [case for values in _groups().values() for case in values]
    sentences = []
    forbidden = re.compile(
        r"\b(profile|reviewed profile|candidate|confirmed target|profile evidence|"
        r"fit|adjacent fit|normal feed|apply[- ]worthiness|proposed eligibility|"
        r"proposed grade)\b",
        re.I,
    )
    for case in cases:
        posting_sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", case.posting.description)
            if sentence.strip()
        ]
        assert not forbidden.search(case.posting.description), case.case_id
        sentences.extend(posting_sentences)
    assert len(sentences) == len(set(sentences))
    assert (
        next(case for case in cases if case.case_id == "calibration-011").posting.company
        == "Northstar Freight"
    )
    assert (
        "Northstar Freight"
        in next(case for case in cases if case.case_id == "calibration-011").posting.description
    )


def test_unknown_eligibility_does_not_force_dont_match_or_hidden_visibility() -> None:
    cases = {case.case_id: case for values in _groups().values() for case in values}
    for case_id in ("calibration-019", "calibration-026"):
        case = cases[case_id]
        assert case.expected_eligibility == "unknown"
        assert case.proposed_provisional is True
        assert case.normal_feed_visible is True
        assert case.proposed_grade != "dont_match"
        assert case.proposed_positive_reasons


def test_degree_conflicts_are_hard_eligibility_conflicts() -> None:
    cases = {case.case_id: case for values in _groups().values() for case in values}
    for case_id, fact_id in (
        ("calibration-024", "posting:calibration-024:critical:phd"),
        ("calibration-030", "posting:calibration-030:critical:doctorate"),
    ):
        case = cases[case_id]
        assert case.expected_eligibility == "ineligible"
        assert case.proposed_grade == "dont_match"
        assert not case.normal_feed_visible and not case.apply_worthy
        assert fact_id in case.proposed_eligibility_reasons[0].evidence_references
        assert (
            "profile:cal-profile-ml-03:education"
            in case.proposed_eligibility_reasons[0].evidence_references
        )


def test_duration_and_scope_authority_is_not_inflated() -> None:
    cases = {case.case_id: case for values in _groups().values() for case in values}
    five_year = next(
        item
        for item in cases["calibration-020"].critical_requirements
        if item.fact_id.endswith(":five-years")
    )
    assert five_year.evidence_references == []
    assert (
        "profile:cal-profile-data-02:experience-years"
        in cases["calibration-020"].proposed_material_gap_reasons[0].evidence_references
    )
    software_years = next(
        item
        for item in cases["calibration-027"].critical_requirements
        if item.fact_id.endswith(":software-years")
    )
    assert not software_years.evidence_references
    model_years = next(
        item
        for item in cases["calibration-013"].critical_requirements
        if item.fact_id.endswith(":model-years")
    )
    assert "profile:cal-profile-data-02:experience-years" in model_years.evidence_references
    assert "profile:data-eng-02:modeling" in model_years.evidence_references


def test_audited_gap_references_use_their_own_authorities() -> None:
    cases = {case.case_id: case for values in _groups().values() for case in values}
    expected = {
        "calibration-012": [
            "profile:data-eng-02:cloud-review",
            "posting:calibration-012:required:cloud-platform",
        ],
        "calibration-014": [
            "profile:data-eng-02:streaming-coursework",
            "posting:calibration-014:required:kafka-production",
            "posting:calibration-014:required:streaming-operations",
        ],
        "calibration-022": [
            "posting:calibration-022:preferred:robotics",
            "posting:calibration-022:preferred:edge-inference",
        ],
        "calibration-023": [
            "posting:calibration-023:preferred:kubernetes",
            "posting:calibration-023:preferred:tensorflow-serving",
            "posting:calibration-023:preferred:cloud-deployment",
            "profile:ml-eng-03:tensorflow-review",
        ],
        "calibration-025": [
            "posting:calibration-025:preferred:robotics-sensors",
            "posting:calibration-025:preferred:ros",
            "posting:calibration-025:preferred:realtime",
        ],
    }
    for case_id, references in expected.items():
        actual = set(
            ref
            for reason in cases[case_id].proposed_material_gap_reasons
            for ref in reason.evidence_references
        )
        assert set(references) <= actual


def test_eligibility_reasons_match_status_and_conflict_authority() -> None:
    cases = {case.case_id: case for values in _groups().values() for case in values}
    hard_codes = {"hard_authorization_conflict", "hard_level_conflict", "hard_degree_conflict"}
    for case in cases.values():
        reasons = case.proposed_eligibility_reasons
        assert reasons
        codes = {reason.code for reason in reasons}
        if case.expected_eligibility == "eligible":
            assert not codes & hard_codes
        if case.expected_eligibility == "unknown":
            assert any(code == "eligibility_unknown" for code in codes)
        for reason in reasons:
            refs = set(reason.evidence_references)
            if reason.code == "hard_authorization_conflict":
                assert any(":location:" in ref for ref in refs)
                assert any(":authorization:" in ref for ref in refs)
                assert "authorization" in reason.statement.casefold()
            if reason.code == "hard_level_conflict":
                assert any(":level:" in ref for ref in refs)
                assert any(":target_level" in ref for ref in refs)
                assert "staff" in reason.statement.casefold()
            if reason.code == "hard_degree_conflict":
                assert any(":critical:phd" in ref or ":critical:doctorate" in ref for ref in refs)
                assert any(ref.endswith(":education") for ref in refs)


def test_pair_directions_follow_grade_tier_and_eligibility() -> None:
    cases = {case.case_id: case for values in _groups().values() for case in values}
    grade_rank = {"excellent": 3, "good": 2, "weak": 1, "dont_match": 0}
    tier_rank = {"tier_1": 3, "tier_2": 2, "tier_3": 1, "not_ranked": 0}
    eligibility_rank = {"eligible": 1, "unknown": 0, "ineligible": -1}
    audited = {
        ("calibration-011", "calibration-013"),
        ("calibration-012", "calibration-019"),
        ("calibration-014", "calibration-019"),
        ("calibration-015", "calibration-019"),
        ("calibration-022", "calibration-023"),
    }
    for case in cases.values():
        for pair in case.comparable_pair_annotations:
            other = cases[pair.other_case_id]
            left = (
                grade_rank[case.proposed_grade],
                tier_rank[case.human_ranking_tier],
                eligibility_rank[case.expected_eligibility],
            )
            right = (
                grade_rank[other.proposed_grade],
                tier_rank[other.human_ranking_tier],
                eligibility_rank[other.expected_eligibility],
            )
            if left == right:
                assert pair.rationale
            else:
                preferred = case if left > right else other
                assert pair.relationship == (
                    "preferred_to_other" if preferred is case else "less_preferred_than_other"
                )
            if tuple(sorted((case.case_id, other.case_id))) in audited:
                assert case.case_id in pair.rationale
                assert other.case_id in pair.rationale


def test_positive_reasons_have_complete_audited_reference_sets() -> None:
    cases = {case.case_id: case for values in _groups().values() for case in values}
    expected = {
        "calibration-013": {
            "profile:data-eng-02:modeling",
            "posting:calibration-013:responsibility:models",
            "profile:data-eng-02:stakeholders",
            "posting:calibration-013:responsibility:stakeholders",
        },
        "calibration-015": {
            "profile:data-eng-02:pipelines",
            "profile:data-eng-02:modeling",
            "profile:data-eng-02:quality",
            "posting:calibration-015:critical:sql-python",
            "posting:calibration-015:responsibility:ingestion",
            "posting:calibration-015:responsibility:validation",
        },
        "calibration-021": {
            "profile:ml-eng-03:training",
            "profile:ml-eng-03:vision-data",
            "profile:ml-eng-03:software",
            "posting:calibration-021:responsibility:training",
            "posting:calibration-021:responsibility:datasets",
            "posting:calibration-021:responsibility:handoff",
        },
        "calibration-022": {
            "profile:ml-eng-03:vision-data",
            "profile:ml-eng-03:training",
            "profile:ml-eng-03:software",
            "posting:calibration-022:critical:python",
            "posting:calibration-022:responsibility:datasets",
            "posting:calibration-022:responsibility:metrics",
        },
        "calibration-023": {
            "profile:ml-eng-03:serving",
            "profile:ml-eng-03:software",
            "profile:ml-eng-03:monitoring",
            "posting:calibration-023:responsibility:packaging",
            "posting:calibration-023:responsibility:interfaces",
            "posting:calibration-023:responsibility:dashboards",
        },
        "calibration-025": {
            "profile:ml-eng-03:vision-data",
            "profile:ml-eng-03:training",
            "profile:ml-eng-03:software",
            "posting:calibration-025:critical:python",
            "posting:calibration-025:responsibility:datasets",
            "posting:calibration-025:responsibility:evaluation",
        },
    }
    for case_id, references in expected.items():
        actual = {
            ref
            for reason in cases[case_id].proposed_positive_reasons
            for ref in reason.evidence_references
        }
        assert actual == references


def test_specialized_duration_requires_duration_and_scope_evidence() -> None:
    for cases in _groups().values():
        for case in cases:
            profile_refs = {
                ref
                for requirement in [*case.critical_requirements, *case.required_qualifications]
                if "year" in requirement.text.casefold()
                for ref in requirement.evidence_references
            }
            for requirement in [*case.critical_requirements, *case.required_qualifications]:
                if "year" not in requirement.text.casefold():
                    continue
                if not requirement.evidence_references:
                    continue
                assert any(ref.endswith(":experience-years") for ref in profile_refs)
                assert len(profile_refs) >= 2


def test_special_evidence_mappings_use_authoritative_evidence() -> None:
    cases = {case.case_id: case for values in _groups().values() for case in values}
    assert "profile:ml-eng-03:research-project" in {
        ref
        for qualification in cases["calibration-030"].preferred_qualifications
        for ref in qualification.evidence_references
    }
    assert "profile:ml-eng-03:serving" in {
        ref
        for qualification in cases["calibration-027"].required_qualifications
        for ref in qualification.evidence_references
    } | {
        ref
        for reason in cases["calibration-027"].proposed_reasons
        for ref in reason.evidence_references
    }
    assert "profile:ml-eng-03:software" in {
        ref
        for reason in cases["calibration-026"].proposed_positive_reasons
        for ref in reason.evidence_references
    }
    tensorflow_gap = next(
        reason
        for reason in cases["calibration-023"].proposed_material_gap_reasons
        if "tensorflow" in reason.statement.casefold()
    )
    assert "reviewed-only" in tensorflow_gap.statement.casefold()


def test_unknown_posting_metadata_matches_atomic_facts_and_reports() -> None:
    cases = {
        case.case_id: case
        for group in ("calibration-group-02", "calibration-group-03")
        for case in load_calibration_group(group)
    }
    for case_id in ("calibration-019", "calibration-026"):
        case = cases[case_id]
        level_facts = [fact for fact in case.posting.posting_facts if fact.kind == "level"]
        authorization_facts = [
            fact for fact in case.posting.posting_facts if fact.kind == "authorization"
        ]
        assert any(
            marker in fact.statement.casefold()
            for fact in level_facts
            for marker in ("unstated", "unresolved", "unknown", "does not state")
        )
        assert case.posting.posting_level == "unknown"
        assert any(
            marker in fact.statement.casefold()
            for fact in authorization_facts
            for marker in ("unresolved", "not stated", "does not state")
        )
        assert case.posting.posting_sponsorship_available is None

    no_sponsorship = next(
        case
        for case in cases.values()
        if any(
            "no sponsorship" in fact.statement.casefold()
            for fact in case.posting.posting_facts
            if fact.kind == "authorization"
        )
    )
    assert no_sponsorship.posting.posting_sponsorship_available is False

    with tempfile.TemporaryDirectory() as directory:
        for group, case_id in (
            ("calibration-group-02", "calibration-019"),
            ("calibration-group-03", "calibration-026"),
        ):
            output = Path(directory) / group
            generate_pilot_artifacts(
                output / "review.html",
                output / "review.csv",
                output / "baseline.json",
                group,
            )
            payload = json.loads((output / "baseline.json").read_text(encoding="utf-8"))
            with (output / "review.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            by_id = {row["case_id"]: row for row in rows}
            prediction_by_id = {item["case_id"]: item for item in payload["predictions"]}
            assert by_id[case_id]["posting_level"] == "unknown"
            assert by_id[case_id]["posting_sponsorship_available"] == ""
            assert prediction_by_id[case_id]["posting_level"] == "unknown"
            assert prediction_by_id[case_id]["posting_sponsorship_available"] is None


def test_audited_reason_reference_sets_are_exact() -> None:
    cases = {
        case.case_id: case
        for group in ("calibration-group-02", "calibration-group-03")
        for case in load_calibration_group(group)
    }
    expected = {
        ("calibration-012", "positive_0", "positive"): {
            "profile:data-eng-02:pipelines",
            "profile:data-eng-02:modeling",
            "posting:calibration-012:responsibility:batch",
            "posting:calibration-012:responsibility:warehouse",
            "posting:calibration-012:responsibility:contracts",
        },
        ("calibration-014", "positive_0", "positive"): {
            "profile:data-eng-02:pipelines",
            "posting:calibration-014:required:python",
            "posting:calibration-014:responsibility:topics",
            "posting:calibration-014:responsibility:streaming",
        },
        ("calibration-018", "gap_0", "gap"): {
            "preferences:cal-profile-data-02:target_level",
            "profile:cal-profile-data-02:experience-years",
            "posting:calibration-018:critical:eight-years",
            "posting:calibration-018:required:staff-authority",
            "posting:calibration-018:required:architecture-standards",
        },
        ("calibration-019", "data_engineering_match", "positive"): {
            "profile:data-eng-02:pipelines",
            "profile:data-eng-02:modeling",
            "profile:data-eng-02:stakeholders",
            "posting:calibration-019:responsibility:ingestion",
            "posting:calibration-019:responsibility:tables",
            "posting:calibration-019:responsibility:dashboards",
        },
        ("calibration-022", "gap_0", "gap"): {
            "posting:calibration-022:preferred:robotics",
            "posting:calibration-022:preferred:edge-inference",
        },
        ("calibration-024", "gap_0", "gap"): {
            "profile:ml-eng-03:research-project",
            "posting:calibration-024:critical:phd",
            "posting:calibration-024:critical:publications",
            "posting:calibration-024:required:research-leadership",
        },
        ("calibration-025", "gap_0", "gap"): {
            "posting:calibration-025:preferred:robotics-sensors",
            "posting:calibration-025:preferred:ros",
            "posting:calibration-025:preferred:realtime",
        },
        ("calibration-026", "analytical_transfer", "positive"): {
            "profile:ml-eng-03:software",
            "profile:ml-eng-03:monitoring",
            "posting:calibration-026:responsibility:experiments",
            "posting:calibration-026:required:written",
        },
        ("calibration-026", "analytics_questions_gap", "gap"): {
            "profile:ml-eng-03:monitoring",
            "posting:calibration-026:required:analytics-questions",
            "posting:calibration-026:responsibility:questions",
        },
        ("calibration-029", "gap_0", "gap"): {
            "preferences:cal-profile-ml-03:target_level",
            "profile:cal-profile-ml-03:experience-years",
            "posting:calibration-029:critical:eight-years",
            "posting:calibration-029:required:staff-influence",
            "posting:calibration-029:required:architecture-leadership",
        },
    }
    for (case_id, code, kind), references in expected.items():
        case = cases[case_id]
        reasons = (
            case.proposed_positive_reasons
            if kind == "positive"
            else case.proposed_material_gap_reasons
        )
        reason = next(reason for reason in reasons if reason.code == code)
        assert set(reason.evidence_references) == references
        assert len(reason.evidence_references) == len(references)


def test_case_026_analytics_question_requirement_is_not_matched() -> None:
    case = next(
        case
        for case in load_calibration_group("calibration-group-03")
        if case.case_id == "calibration-026"
    )
    requirement = next(
        item
        for item in case.required_qualifications
        if item.qualification_id.endswith(":analytics-questions")
    )
    assert requirement.evidence_references == []


def test_final_wording_matches_audited_reference_authority() -> None:
    cases = {
        case.case_id: case
        for group in ("calibration-group-02", "calibration-group-03")
        for case in load_calibration_group(group)
    }
    case_019 = cases["calibration-019"]
    gap_019 = case_019.proposed_material_gap_reasons[0]
    assert all(
        phrase in gap_019.statement.casefold()
        for phrase in ("country", "sponsorship", "posting date", "role level")
    )
    assert "data-quality" not in case_019.rationale.casefold()
    assert all(
        phrase in case_019.rationale.casefold()
        for phrase in ("ingestion", "sql-table", "research-dashboard")
    )

    rationale_026 = cases["calibration-026"].rationale.casefold()
    assert "documented technical communication" in rationale_026
    assert "cross-functional experiment review" in rationale_026
    assert "analytical-question" not in rationale_026
    assert "data-product responsibilities overlap" not in rationale_026
    assert "product-question translation" in rationale_026
    assert "data-product familiarity" in rationale_026

    assert cases["calibration-014"].proposed_positive_reasons[0].statement == (
        "Demonstrated Python batch-pipeline work provides limited transfer to Kafka "
        "topic validation and streaming-alert responsibilities."
    )
    for case_id, posting_terms in {
        "calibration-015": ("batch", "sql", "data-quality"),
        "calibration-022": ("visual datasets", "python", "evaluation"),
        "calibration-025": ("computer-vision datasets", "python", "evaluation"),
    }.items():
        statement = cases[case_id].proposed_positive_reasons[0].statement.casefold()
        assert all(term in statement for term in posting_terms)
