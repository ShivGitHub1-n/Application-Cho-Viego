# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path

from tests.job_discovery.benchmark.loader import load_calibration_group

ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "job_discovery" / "benchmark"
GROUPS = ("calibration-group-04", "calibration-group-05", "calibration-group-06")
ALL_GROUPS = tuple(f"calibration-group-{index:02d}" for index in range(1, 7))
FIRST_TEN_DIGEST = "5d46a8dfce69469899259e08553eddf0509500868c6dd9767d3b5254a2ca4078"
FIRST_THIRTY_DIGEST = "82d1bfb168904443dd2cd0ad9deaf6fa6f22755186f44b0145768d4dc58779ce"
PROTECTED_FIRST_THIRTY_DIGEST = "674ef292067a0492581a7c1e90497acd763fde015a7aa89ca7893aea07da7221"
EVALUATOR_WORDS = re.compile(
    r"\b(?:benchmark|candidate|profile|apply[- ]worthy|normal feed|"
    r"human review|proposed grade|proposal|evaluator|ranking tier)\b",
    re.IGNORECASE,
)


def _groups() -> dict[str, list]:
    return {group: load_calibration_group(group) for group in GROUPS}


def _all_calibration_groups() -> dict[str, list]:
    return {group: load_calibration_group(group) for group in ALL_GROUPS}


def _sentences(text: str) -> list[str]:
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text) if sentence.strip()]


def _posting_refs(case) -> set[str]:
    return {fact.fact_id for fact in case.posting.posting_facts}


def _profile_refs(case) -> set[str]:
    refs = {item.evidence_id for item in case.profile.evidence_items}
    refs.update(
        {
            f"profile:{case.profile.profile_ref}:experience-years",
            f"profile:{case.profile.profile_ref}:education",
            f"profile:{case.profile.profile_ref}:professional-license-status",
            f"profile:{case.profile.profile_ref}:clearance-status",
        }
    )
    refs.update(
        {
            f"preferences:{case.profile.profile_ref}:work_authorization",
            f"preferences:{case.profile.profile_ref}:target_level",
        }
    )
    return refs


def _all_refs(case) -> set[str]:
    return _posting_refs(case) | _profile_refs(case)


def _record_id(record) -> str:
    return record.requirement_id if hasattr(record, "requirement_id") else record.qualification_id


def _records(case):
    return [*case.critical_requirements, *case.required_qualifications, *case.preferred_qualifications]


def test_first_thirty_canonical_digest_is_current() -> None:
    rows = json.loads((ROOT / "calibration.json").read_text(encoding="utf-8"))
    first_thirty = sorted(rows[:30], key=lambda item: item["case_id"])
    canonical = json.dumps(first_thirty, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == FIRST_THIRTY_DIGEST


def test_first_ten_canonical_digest_is_current() -> None:
    rows = json.loads((ROOT / "calibration.json").read_text(encoding="utf-8"))
    first_ten = sorted(rows[:10], key=lambda item: item["case_id"])
    canonical = json.dumps(first_ten, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == FIRST_TEN_DIGEST


def test_groups_04_06_have_independent_profile_evidence_authority() -> None:
    groups = _all_calibration_groups()
    profiles = [groups[group][0].profile for group in ALL_GROUPS]
    assert len({profile.profile_ref for profile in profiles}) == 6
    payloads = [json.dumps([item.model_dump() for item in profile.evidence_items], sort_keys=True) for profile in profiles]
    assert len(set(payloads)) == 6
    for group in GROUPS:
        assert groups[group][0].profile.evidence_items != groups["calibration-group-01"][0].profile.evidence_items
        assert groups[group][0].profile.evidence_items != groups["calibration-group-02"][0].profile.evidence_items
        assert groups[group][0].profile.evidence_items != groups["calibration-group-03"][0].profile.evidence_items


def test_groups_04_06_postings_are_independent_employer_advertisements() -> None:
    cases = [case for group in _groups().values() for case in group]
    sentences = [sentence.casefold() for case in cases for sentence in _sentences(case.posting.description)]
    old_sentences = [
        sentence.casefold()
        for group in ("calibration-group-01", "calibration-group-02", "calibration-group-03")
        for case in _all_calibration_groups()[group]
        for sentence in _sentences(case.posting.description)
    ]
    profile_sentences = [
        sentence.casefold()
        for group in _all_calibration_groups().values()
        for sentence in _sentences(group[0].profile.summary)
    ]
    assert all(120 <= len(case.posting.description.split()) <= 300 for case in cases)
    assert len(sentences) == len(set(sentences))
    assert set(sentences).isdisjoint(old_sentences)
    assert not any(EVALUATOR_WORDS.search(case.posting.description) for case in cases)
    for case in cases:
        posting_words = set(re.findall(r"[a-z]+", case.posting.description.casefold()))
        for profile_sentence in profile_sentences:
            profile_words = profile_sentence.split()
            assert " ".join(profile_words[:8]) not in case.posting.description.casefold()
        assert posting_words


def test_group_review_artifacts_have_ten_rows_and_blank_reviewer_fields(tmp_path: Path) -> None:
    from tests.job_discovery.benchmark.report import generate_pilot_artifacts

    for group in GROUPS:
        output = tmp_path / group
        generate_pilot_artifacts(output.with_suffix(".html"), output.with_suffix(".csv"), output.with_suffix(".json"), group)
        import csv

        with output.with_suffix(".csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        assert len(rows) == 10
        assert {row["ranking_group"] for row in rows} == {group}
        assert all(
            row[field] == ""
            for row in rows
            for field in ("reviewer_decision", "reviewer_grade", "reviewer_eligibility", "reviewer_provisional", "reviewer_notes")
        )
        payload = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
        assert payload["case_count"] == 10
        assert payload["locked_split"] == "not touched or evaluated"
        assert "locked-" not in output.with_suffix(".json").read_text(encoding="utf-8")


def test_profile_level_license_and_clearance_facts_are_visible_in_review_csv(tmp_path: Path) -> None:
    import csv

    from tests.job_discovery.benchmark.report import generate_pilot_artifacts

    for group, case_id, expected_ref in (
        ("calibration-group-05", "calibration-048", "profile:cal-profile-05:clearance-status"),
        ("calibration-group-06", "calibration-058", "profile:cal-profile-06:professional-license-status"),
    ):
        output = tmp_path / group
        generate_pilot_artifacts(output.with_suffix(".html"), output.with_suffix(".csv"), output.with_suffix(".json"), group)
        rows = {row["case_id"]: row for row in csv.DictReader(output.with_suffix(".csv").open(encoding="utf-8", newline=""))}
        assert expected_ref in rows[case_id]["profile_level_facts"]


def test_groups_04_06_atomic_facts_and_references_are_complete() -> None:
    for case in [case for group in _all_calibration_groups().values() for case in group]:
        fact_ids = [fact.fact_id for fact in case.posting.posting_facts]
        assert len(fact_ids) == len(set(fact_ids))
        assert all(item.fact_id == _record_id(item) for item in _records(case))
        assert all(item.fact_id in set(fact_ids) for item in _records(case))
        for reason in [
            *case.proposed_eligibility_reasons,
            *case.proposed_reasons,
            *case.important_gaps,
            *case.proposed_positive_reasons,
            *case.proposed_material_gap_reasons,
        ]:
            assert len(reason.evidence_references) == len(set(reason.evidence_references))
            assert set(reason.evidence_references) <= _all_refs(case)
        assert len(case.review_tags) == len(set(case.review_tags))
        assert len(case.provisional_reason_codes) == len(set(case.provisional_reason_codes))
        assert case.proposed_reasons == [
            *case.proposed_positive_reasons,
            *case.proposed_material_gap_reasons,
        ]
    for group in GROUPS:
        for case in _groups()[group]:
            assert all(fact.fact_id.startswith(f"posting:{case.case_id}:") for fact in case.posting.posting_facts)
            responsibility_facts = {fact.statement for fact in case.posting.posting_facts if fact.kind == "responsibility"}
            assert set(case.posting.responsibilities) <= responsibility_facts


def test_group_metadata_matches_atomic_facts_and_unknowns_remain_independent() -> None:
    for group in GROUPS:
        for case in _groups()[group]:
            facts = case.posting.posting_facts
            level_facts = [fact for fact in facts if fact.kind == "level"]
            authorization_facts = [fact for fact in facts if fact.kind == "authorization"]
            date_facts = [fact for fact in facts if fact.kind == "posting_date"]
            assert level_facts and authorization_facts and date_facts
            if case.posting.posting_level == "unknown":
                assert any(word in fact.statement.casefold() for fact in level_facts for word in ("unknown", "unstated", "not specified", "unresolved"))
            if case.posting.posting_sponsorship_available is None:
                assert any(word in fact.statement.casefold() for fact in authorization_facts for word in ("unknown", "not stated", "unresolved"))
            if case.posting.posted_date is None:
                assert any(word in fact.statement.casefold() for fact in date_facts for word in ("unknown", "not stated", "missing"))
            if case.expected_eligibility == "unknown":
                assert case.normal_feed_visible
                assert case.proposed_grade != "dont_match"
                assert case.proposed_provisional


def test_critical_and_required_qualifications_are_matched_or_grounded_gaps() -> None:
    for group in GROUPS:
        for case in _groups()[group]:
            gap_refs = {
                ref
                for reason in case.proposed_material_gap_reasons
                for ref in reason.evidence_references
            }
            gap_reasons = case.proposed_material_gap_reasons
            for qualification in [*case.critical_requirements, *case.required_qualifications]:
                if qualification.evidence_references:
                    if _record_id(qualification) in gap_refs:
                        assert any(
                            reason.code == "insufficient_evidence"
                            and _record_id(qualification) in reason.evidence_references
                            and set(qualification.evidence_references) <= set(reason.evidence_references)
                            for reason in gap_reasons
                        )
                else:
                    assert _record_id(qualification) in gap_refs
            for qualification in [*case.critical_requirements, *case.required_qualifications]:
                if "year" in qualification.text.casefold() and qualification.evidence_references:
                    assert any(ref.endswith(":experience-years") for ref in qualification.evidence_references)
                    assert len(qualification.evidence_references) >= 2


def test_production_qualification_matches_use_demonstrated_evidence_only() -> None:
    for group in GROUPS:
        for case in _groups()[group]:
            evidence = {item.evidence_id: item for item in case.profile.evidence_items}
            for qualification in [*case.critical_requirements, *case.required_qualifications]:
                for reference in qualification.evidence_references:
                    if reference in evidence:
                        assert evidence[reference].evidence_kind in {"demonstrated", "transferable_demonstrated"}
                        assert evidence[reference].demonstrated
    case = next(case for group in GROUPS for case in _groups()[group] if case.case_id == "calibration-036")
    assert any("does not require sponsorship" in reason.statement for reason in case.proposed_eligibility_reasons)
    assert case.profile.requires_sponsorship is False


def test_group_04_robotics_boundaries_are_explicit() -> None:
    cases = {case.case_id: case for case in _groups()["calibration-group-04"]}
    profile = cases["calibration-031"].profile
    assert any("ROS 2" in item.statement or "ROS2" in item.statement for item in profile.evidence_items)
    assert any("coordinate" in item.statement.casefold() or "frame" in item.statement.casefold() for item in profile.evidence_items)
    assert cases["calibration-031"].proposed_grade in {"good", "excellent"}
    assert cases["calibration-035"].proposed_grade == "dont_match"
    assert "keyword_trap" in cases["calibration-035"].review_tags
    assert cases["calibration-036"].expected_eligibility == "ineligible"
    assert "hard_authorization_conflict" in {reason.code for reason in cases["calibration-036"].proposed_eligibility_reasons}
    assert cases["calibration-037"].proposed_grade == "dont_match"
    assert "hard_level_conflict" in {reason.code for reason in cases["calibration-037"].proposed_eligibility_reasons}
    assert cases["calibration-040"].expected_eligibility == "unknown"
    assert cases["calibration-040"].proposed_provisional


def test_group_05_embedded_boundaries_are_explicit() -> None:
    cases = {case.case_id: case for case in _groups()["calibration-group-05"]}
    profile = cases["calibration-041"].profile
    assert any("C firmware" in item.statement or "C++" in item.statement for item in profile.evidence_items)
    assert any(protocol in item.statement for item in profile.evidence_items for protocol in ("SPI", "I2C", "UART", "CAN"))
    assert any("hardware-in-the-loop" in item.statement.casefold() for item in profile.evidence_items)
    assert cases["calibration-045"].proposed_grade == "excellent"
    assert cases["calibration-046"].proposed_grade == "dont_match"
    assert "hardware_design_gap" in cases["calibration-046"].review_tags
    assert cases["calibration-048"].expected_eligibility == "ineligible"
    assert "hard_authorization_conflict" in {reason.code for reason in cases["calibration-048"].proposed_eligibility_reasons}
    assert cases["calibration-049"].proposed_grade == "dont_match"
    assert "level_mismatch" in cases["calibration-049"].review_tags
    assert cases["calibration-050"].proposed_grade in {"weak", "good"}
    assert cases["calibration-050"].expected_eligibility == "unknown"


def test_group_06_integration_controls_and_verification_boundaries_are_explicit() -> None:
    cases = {case.case_id: case for case in _groups()["calibration-group-06"]}
    profile = cases["calibration-051"].profile
    assert any("requirements" in item.statement.casefold() for item in profile.evidence_items)
    assert any("root cause" in item.statement.casefold() or "defect" in item.statement.casefold() for item in profile.evidence_items)
    assert any("Python" in item.statement or "MATLAB" in item.statement for item in profile.evidence_items)
    assert cases["calibration-055"].proposed_grade == "dont_match"
    assert cases["calibration-056"].proposed_grade == "dont_match"
    assert "keyword_trap" in cases["calibration-056"].review_tags
    assert cases["calibration-058"].expected_eligibility == "ineligible"
    assert "hard_license_conflict" in {reason.code for reason in cases["calibration-058"].proposed_eligibility_reasons}
    assert cases["calibration-059"].proposed_grade == "dont_match"
    assert "level_mismatch" in cases["calibration-059"].review_tags
    assert cases["calibration-060"].expected_eligibility == "unknown"


def test_pairwise_comparisons_cover_visible_cases_and_respect_typed_order() -> None:
    grade_rank = {"excellent": 3, "good": 2, "weak": 1, "dont_match": 0}
    tier_rank = {"tier_1": 3, "tier_2": 2, "tier_3": 1, "not_ranked": 0}
    eligibility_rank = {"eligible": 1, "unknown": 0, "ineligible": -1}
    for group, cases in _all_calibration_groups().items():
        by_id = {case.case_id: case for case in cases}
        visible = {case.case_id for case in cases if case.normal_feed_visible}
        pairs = {}
        for case in cases:
            for pair in case.comparable_pair_annotations:
                other = by_id[pair.other_case_id]
                key = tuple(sorted((case.case_id, other.case_id)))
                pairs[key] = (case, other, pair)
                assert case.case_id in visible and other.case_id in visible
        assert set(pairs) == {
            tuple(sorted((left.case_id, right.case_id)))
            for index, left in enumerate(cases)
            for right in cases[index + 1 :]
            if left.case_id in visible and right.case_id in visible
        }, group
        for left, right, pair in pairs.values():
            left_key = (grade_rank[left.proposed_grade], tier_rank[left.human_ranking_tier], eligibility_rank[left.expected_eligibility])
            right_key = (grade_rank[right.proposed_grade], tier_rank[right.human_ranking_tier], eligibility_rank[right.expected_eligibility])
            if left_key == right_key:
                if group in GROUPS:
                    assert left.case_id in pair.rationale and right.case_id in pair.rationale
                    assert any(
                        word in pair.rationale.casefold()
                        for word in ("responsibility", "ownership", "owns", "scope", "direct", "lifecycle", "integration")
                    )
                continue
            preferred = left if left_key > right_key else right
            assert pair.relationship == ("preferred_to_other" if preferred is left else "less_preferred_than_other")
        assert all(not case.apply_worthy for case in cases if not case.normal_feed_visible)


def _first_sentence_skeleton(case) -> str:
    sentence = _sentences(case.posting.description)[0].casefold()
    for value in (case.posting.company, case.posting.title, case.posting.location):
        sentence = sentence.replace(value.casefold(), "<field>")
    sentence = sentence.replace(case.posting.company.casefold(), "<field>")
    sentence = re.sub(r"\b(?:calibration|group)[- ]?\d+\b", "<generated>", sentence)
    sentence = re.sub(r"\b\d{3}\b", "<generated>", sentence)
    return re.sub(r"\s+", " ", sentence).strip()


def test_source_descriptions_have_no_generated_identifiers_or_template_authority() -> None:
    banned = (
        "this 031 opportunity", "this 048", "named 06-055", "delivery stream",
        "immediate priority is", "close to the hardware",
        "focused engineering program around", ".;", "not stated site",
    )
    cases = [case for group in _groups().values() for case in group]
    assert all(not re.search(r"\b(?:calibration|group)[- ]?0[456][- ]?\d{2}\b", case.posting.description, re.I) for case in cases)
    assert all(not re.search(r"\b0[456]-\d{3}\b", case.posting.description) for case in cases)
    assert all(not any(phrase in case.posting.description.casefold() for phrase in banned) for case in cases)
    assert all(not re.search(r"\bthe next [a-z -]+ release\b", case.posting.description.casefold()) for case in cases)
    assert all(not re.search(r"\bturn [a-z -]+ plans into reliable releases\b", case.posting.description.casefold()) for case in cases)
    assert all("group group" not in case.posting.description.casefold() for case in cases)
    assert len({_first_sentence_skeleton(case) for case in cases}) == len(cases)


def test_known_posting_dates_do_not_exceed_retrieval_dates() -> None:
    from datetime import datetime

    for case in [case for group in _all_calibration_groups().values() for case in group]:
        if case.posting.posted_date is not None:
            assert datetime.fromisoformat(case.posting.posted_date) <= datetime.fromisoformat(case.source.retrieved_at.replace("Z", "+00:00")).replace(tzinfo=None)


def test_grade_authority_matches_material_gap_shape() -> None:
    for case in [case for group in _groups().values() for case in group]:
        gap_codes = {reason.code for reason in case.proposed_material_gap_reasons}
        if case.proposed_grade == "excellent":
            assert not gap_codes, case.case_id
        if case.proposed_grade == "good":
            assert gap_codes, case.case_id
            assert any(code not in {"preferred_gap", "preferred_insufficiency"} for code in gap_codes), case.case_id
        if case.proposed_grade == "weak":
            assert all(qualification.evidence_references for qualification in case.critical_requirements), case.case_id
        for qualification in case.critical_requirements:
            if not qualification.evidence_references:
                assert case.proposed_grade == "dont_match", case.case_id


def test_existing_evidence_is_not_described_as_absent() -> None:
    cases = {case.case_id: case for case in [case for group in _groups().values() for case in group]}
    linux = next(item for item in cases["calibration-040"].required_qualifications if "Linux" in item.text)
    assert linux.evidence_references == ["profile:cal-profile-04:e4"]
    python = next(item for item in cases["calibration-050"].required_qualifications if "Python" in item.text)
    assert python.evidence_references == ["profile:cal-profile-05:e5"]
    python_gap = next(reason for reason in cases["calibration-050"].proposed_material_gap_reasons if reason.code == "insufficient_evidence")
    assert _record_id(python) in python_gap.evidence_references
    assert "profile:cal-profile-05:e5" in python_gap.evidence_references
    bench = next(item for item in cases["calibration-060"].required_qualifications if "control" in item.text.casefold())
    assert {"profile:cal-profile-06:e3", "profile:cal-profile-06:e4"} <= set(bench.evidence_references)


def test_eligibility_constraints_are_not_technical_requirements() -> None:
    for case_id in ("calibration-036", "calibration-048"):
        case = next(case for group in _groups().values() for case in group if case.case_id == case_id)
        for qualification in [*case.critical_requirements, *case.required_qualifications, *case.preferred_qualifications]:
            assert not re.search(r"authorization|citizenship|sponsor|clearance", qualification.text, re.I)


def test_license_and_clearance_conflicts_require_explicit_candidate_facts() -> None:
    cases = {case.case_id: case for case in [case for group in _groups().values() for case in group]}
    authorization = cases["calibration-048"]
    authorization_reasons = {reason.code: reason for reason in authorization.proposed_eligibility_reasons}
    assert "hard_authorization_conflict" in authorization_reasons
    assert set(authorization_reasons["hard_authorization_conflict"].evidence_references) == {
        "posting:calibration-048:location:work-location",
        "posting:calibration-048:authorization:authorization-policy",
        "preferences:cal-profile-05:work_authorization",
    }
    license_case = cases["calibration-058"]
    license_reasons = {reason.code: reason for reason in license_case.proposed_eligibility_reasons}
    assert "hard_license_conflict" in license_reasons
    assert "profile:cal-profile-06:professional-license-status" in license_reasons["hard_license_conflict"].evidence_references


def test_unknown_eligibility_reasons_reference_only_the_unresolved_authority_facts() -> None:
    for case_id in ("calibration-040", "calibration-050", "calibration-060"):
        case = next(case for group in _groups().values() for case in group if case.case_id == case_id)
        reason = next(reason for reason in case.proposed_eligibility_reasons if reason.code == "eligibility_unknown")
        expected = {
            f"posting:{case_id}:location:work-location",
            f"posting:{case_id}:authorization:authorization-policy",
            f"posting:{case_id}:posting_date:posting-date",
            f"posting:{case_id}:level:posting-level",
            f"preferences:{case.profile.profile_ref}:work_authorization",
            f"preferences:{case.profile.profile_ref}:target_level",
        }
        assert set(reason.evidence_references) == expected
        assert not any(ref.endswith(":education") for ref in reason.evidence_references)


def test_level_conflict_reasons_ground_exact_scope_and_candidate_authority() -> None:
    for case_id in ("calibration-037", "calibration-039", "calibration-049", "calibration-059"):
        case = next(case for group in _groups().values() for case in group if case.case_id == case_id)
        reason = next(reason for reason in case.proposed_eligibility_reasons if reason.code == "hard_level_conflict")
        refs = set(reason.evidence_references)
        assert f"posting:{case_id}:level:posting-level" in refs
        assert f"preferences:{case.profile.profile_ref}:target_level" in refs
        assert f"profile:{case.profile.profile_ref}:experience-years" in refs
        scope_refs = {
            _record_id(item)
            for item in [*case.critical_requirements, *case.required_qualifications]
            if re.search(r"staff|director|principal|portfolio|executive|organization|multi-team", item.text, re.I)
        }
        assert scope_refs & refs, case_id
        assert any(scope_ref in gap.evidence_references for scope_ref in scope_refs for gap in case.proposed_material_gap_reasons)


def test_positive_reasons_and_rationales_are_case_specific_and_grounded() -> None:
    forbidden_reason = "responsibilities align with reviewed"
    forbidden_rationale = "assessed independently from the"
    trap_forbidden = {
        "calibration-035": ("sql warehouse", "batch pipeline"),
        "calibration-036": ("controls validation ownership",),
        "calibration-037": ("staff influence",),
        "calibration-039": ("organization building",),
        "calibration-046": ("schematic", "compliance ownership"),
        "calibration-047": ("web-service", "cloud-observability"),
        "calibration-049": ("organizational mentoring",),
        "calibration-056": ("mechanical cad", "prototype-design ownership"),
        "calibration-057": ("program-roadmap", "vendor-management"),
        "calibration-059": ("people leadership",),
    }
    for case in [case for group in _groups().values() for case in group]:
        assert case.proposed_positive_reasons
        assert all(forbidden_reason not in reason.statement.casefold() for reason in case.proposed_positive_reasons)
        assert forbidden_rationale not in case.rationale.casefold()
        assert all(set(reason.evidence_references) & _posting_refs(case) for reason in case.proposed_positive_reasons)
        assert all(set(reason.evidence_references) & _profile_refs(case) for reason in case.proposed_positive_reasons)
        for phrase in trap_forbidden.get(case.case_id, ()):
            assert phrase not in " ".join(reason.statement for reason in case.proposed_positive_reasons).casefold()
        assert case.case_id in case.rationale


def test_source_date_structured_date_and_atomic_date_fact_are_identical() -> None:
    from datetime import date

    for case in [case for group in _groups().values() for case in group]:
        date_facts = [fact for fact in case.posting.posting_facts if fact.kind == "posting_date"]
        assert len(date_facts) == 1
        explicit_dates = re.findall(r"\b2026-\d{2}-\d{2}\b", case.posting.description)
        if case.posting.posted_date is None:
            assert explicit_dates == []
            assert re.search(r"unknown|missing|not stated|omitted", date_facts[0].statement, re.I)
            continue
        assert len(explicit_dates) == 1
        fact_dates = re.findall(r"\b2026-\d{2}-\d{2}\b", date_facts[0].statement)
        assert fact_dates == [case.posting.posted_date]
        assert explicit_dates == [case.posting.posted_date]
        assert date.fromisoformat(case.posting.posted_date) <= date.fromisoformat(case.source.retrieved_at[:10])


def test_known_structured_levels_are_represented_in_source_text() -> None:
    for case in [case for group in _groups().values() for case in group]:
        if case.posting.posting_level == "unknown":
            assert re.search(r"unknown|unstated|not stated|omitted", case.posting.description, re.I)
        else:
            assert re.search(rf"\b{re.escape(case.posting.posting_level)}(?:-level)?\b", case.posting.description, re.I)


def test_source_critical_qualifications_have_structured_critical_requirements() -> None:
    for case in [case for group in _groups().values() for case in group]:
        critical_requirements = {item.text.casefold(): item for item in case.critical_requirements}
        source_critical = re.search(r"\bcritical\b", case.posting.description, re.I)
        if not source_critical:
            continue
        assert critical_requirements
        for item in case.critical_requirements:
            assert item.requirement_id == item.fact_id
            assert item.fact_id in _posting_refs(case)
            assert item.text.casefold() in case.posting.description.casefold() or len(
                set(re.findall(r"[a-z0-9]+", item.text.casefold()))
                & set(re.findall(r"[a-z0-9]+", case.posting.description.casefold()))
            ) >= 2
    case = next(case for group in _groups().values() for case in group if case.case_id == "calibration-036")
    requirement = next(item for item in case.critical_requirements if "simulation" in item.text.casefold())
    assert requirement.requirement_id == "posting:calibration-036:critical_requirement:simulation-safety"
    assert requirement.evidence_references == ["profile:cal-profile-04:e5"]


def test_audited_peripheral_positive_reasons_have_exact_authority() -> None:
    expected = {
        "calibration-035": {"profile:cal-profile-04:e4", "posting:calibration-035:preferred_qualification:robotics-data"},
        "calibration-036": {"profile:cal-profile-04:e5", "posting:calibration-036:critical_requirement:simulation-safety"},
        "calibration-039": {"profile:cal-profile-04:e1", "posting:calibration-039:preferred_qualification:ros2"},
        "calibration-046": {"profile:cal-profile-05:e3", "posting:calibration-046:preferred_qualification:firmware"},
        "calibration-047": {"profile:cal-profile-05:e5", "posting:calibration-047:preferred_qualification:embedded-devices"},
        "calibration-049": {"profile:cal-profile-05:e1", "posting:calibration-049:preferred_qualification:c-drivers"},
        "calibration-057": {"profile:cal-profile-06:e5", "posting:calibration-057:preferred_qualification:hardware-context"},
        "calibration-059": {"profile:cal-profile-06:e4", "posting:calibration-059:preferred_qualification:hil"},
    }
    cases = {case.case_id: case for case in [case for group in _groups().values() for case in group]}
    for case_id, references in expected.items():
        reasons = cases[case_id].proposed_positive_reasons
        assert len(reasons) == 1
        assert set(reasons[0].evidence_references) == references
        assert re.search(r"peripheral|overlap|does not overcome|not overcome", reasons[0].statement, re.I)
    forbidden = {
        "calibration-035": ("batch", "sql"),
        "calibration-036": ("oscilloscope", "servo", "actuator-release"),
        "calibration-039": ("portfolio", "executive"),
        "calibration-046": ("supplier", "schematic", "compliance"),
        "calibration-047": ("web", "cloud"),
        "calibration-049": ("architecture", "mentoring"),
        "calibration-057": ("executive", "vendor", "program-risk"),
        "calibration-059": ("executive", "people leadership", "principal"),
    }
    for case_id, words in forbidden.items():
        statement = " ".join(reason.statement for reason in cases[case_id].proposed_positive_reasons).casefold()
        assert not any(word in statement for word in words)


def test_credential_status_semantics_match_conflict_authority() -> None:
    cases = {case.case_id: case for case in [case for group in _groups().values() for case in group]}
    assert cases["calibration-048"].profile.clearance_status == "none_recorded"
    assert {reason.code for reason in cases["calibration-048"].proposed_eligibility_reasons} == {"hard_authorization_conflict"}
    assert all("clearance-status" not in reason.evidence_references for reason in cases["calibration-048"].proposed_eligibility_reasons)
    assert cases["calibration-058"].profile.professional_license_status == "confirmed_none"
    license_reason = cases["calibration-058"].proposed_eligibility_reasons[0]
    assert license_reason.code == "hard_license_conflict"
    assert "profile:cal-profile-06:professional-license-status" in license_reason.evidence_references
    for case in cases.values():
        for reason in case.proposed_eligibility_reasons:
            if reason.code == "hard_license_conflict":
                assert case.profile.professional_license_status == "confirmed_none"
            if reason.code == "hard_clearance_conflict":
                assert case.profile.clearance_status == "active"
        if case.profile.professional_license_status in {"unknown", "none_recorded"}:
            assert all(reason.code != "hard_license_conflict" for reason in case.proposed_eligibility_reasons)
        if case.profile.clearance_status in {"unknown", "none_recorded"}:
            assert all(reason.code != "hard_clearance_conflict" for reason in case.proposed_eligibility_reasons)


def test_case_040_rationale_uses_only_grounded_substantive_authority() -> None:
    case = next(case for group in _groups().values() for case in group if case.case_id == "calibration-040")
    rationale = case.rationale.casefold()
    assert all(term in rationale for term in ("c++", "ros 2", "sensor calibration", "linux", "mobile-robot"))
    assert "log replay" not in rationale


def test_group_pair_counts_are_15_10_10_with_35_total() -> None:
    counts = {}
    for group, cases in _groups().items():
        counts[group] = sum(len(case.comparable_pair_annotations) for case in cases)
    assert counts == {"calibration-group-04": 15, "calibration-group-05": 10, "calibration-group-06": 10}
    assert sum(counts.values()) == 35


def test_all_sixty_inherited_metadata_authorities_are_consistent() -> None:
    from datetime import datetime

    arrangement_terms = {"hybrid": "hybrid", "remote": "remote", "onsite": "onsite"}
    cases = [case for group in _all_calibration_groups().values() for case in group]
    for case in cases:
        description = case.posting.description
        date_facts = [fact for fact in case.posting.posting_facts if fact.kind == "posting_date"]
        assert len(date_facts) == 1, case.case_id
        explicit_dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", description)
        if case.posting.posted_date is None:
            assert explicit_dates == [], case.case_id
            assert re.search(r"missing|not stated|unstated|unknown|does not state", date_facts[0].statement, re.I), case.case_id
        else:
            assert explicit_dates == [case.posting.posted_date], case.case_id
            assert case.posting.posted_date in date_facts[0].statement, case.case_id
            retrieved = datetime.fromisoformat(case.source.retrieved_at.replace("Z", "+00:00"))
            assert datetime.fromisoformat(case.posting.posted_date).date() <= retrieved.date(), case.case_id

        employment_facts = [fact for fact in case.posting.posting_facts if fact.kind == "employment_type"]
        assert len(employment_facts) == 1, case.case_id
        assert employment_facts[0].statement == "The position is full-time employment."
        assert re.search(r"\bfull[- ]time\b", description, re.I), case.case_id

        level_facts = [fact for fact in case.posting.posting_facts if fact.kind == "level"]
        assert len(level_facts) == 1, case.case_id
        if case.posting.posting_level == "unknown":
            assert re.search(r"unknown|unstated|not stated|not specified", description, re.I), case.case_id
        else:
            assert re.search(rf"\b{re.escape(case.posting.posting_level)}(?:-level)?\b", description, re.I), case.case_id

        arrangement = arrangement_terms[case.posting.work_arrangement]
        assert re.search(rf"\b{arrangement}\b", description, re.I), case.case_id
        if int(case.case_id[-3:]) <= 30:
            location_facts = [fact for fact in case.posting.posting_facts if fact.kind == "location"]
            assert len(location_facts) == 1
            assert re.search(rf"\b{arrangement}\b", location_facts[0].statement, re.I), case.case_id

    sentences = [sentence.casefold() for case in cases for sentence in _sentences(case.posting.description)]
    assert len(sentences) == len(set(sentences))
    assert not any(EVALUATOR_WORDS.search(case.posting.description) for case in cases)
    assert all(not re.search(r"\b(?:calibration|group)[- ]?0[1-6][- ]?\d{2}\b|\b0[1-6]-\d{3}\b", case.posting.description, re.I) for case in cases)
    assert all(120 <= len(case.posting.description.split()) <= 300 for case in cases)


def test_targeted_inherited_work_arrangements_are_hybrid() -> None:
    cases = {case.case_id: case for group in _all_calibration_groups().values() for case in group}
    for case_id in ("calibration-006", "calibration-011", "calibration-016", "calibration-025"):
        case = cases[case_id]
        assert case.posting.work_arrangement == "hybrid"
        assert "hybrid" in case.posting.description.casefold()
        location_fact = next(fact for fact in case.posting.posting_facts if fact.kind == "location")
        assert "hybrid" in location_fact.statement.casefold()


def test_protected_first_thirty_semantic_projection_is_unchanged() -> None:
    rows = json.loads((ROOT / "calibration.json").read_text(encoding="utf-8"))
    projection = []
    for case in rows[:30]:
        item = deepcopy(case)
        item["posting"].pop("description", None)
        item["posting"].pop("posting_facts", None)
        item["posting"].pop("work_arrangement", None)
        projection.append(item)
    canonical = json.dumps(sorted(projection, key=lambda item: item["case_id"]), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == PROTECTED_FIRST_THIRTY_DIGEST


def test_all_six_calibration_groups_have_boundary_coverage() -> None:
    for group, cases in _all_calibration_groups().items():
        assert {case.proposed_grade for case in cases} >= {"excellent", "good", "weak", "dont_match"}, group
        assert {case.expected_eligibility for case in cases} >= {"eligible", "ineligible", "unknown"}, group


def test_final_boundary_case_decisions_are_explicit() -> None:
    expected = {
        "calibration-034": ("good", "eligible", False, True, True, "tier_2"),
        "calibration-040": ("weak", "unknown", True, True, True, "tier_3"),
        "calibration-042": ("good", "eligible", False, True, True, "tier_2"),
        "calibration-052": ("good", "eligible", False, True, True, "tier_2"),
        "calibration-060": ("weak", "unknown", True, True, True, "tier_3"),
    }
    cases = {case.case_id: case for group in _all_calibration_groups().values() for case in group}
    for case_id, (grade, eligibility, provisional, visible, apply_worthy, tier) in expected.items():
        case = cases[case_id]
        assert (case.proposed_grade, case.expected_eligibility, case.proposed_provisional, case.normal_feed_visible, case.apply_worthy, case.human_ranking_tier) == (
            grade,
            eligibility,
            provisional,
            visible,
            apply_worthy,
            tier,
        )


def test_new_boundary_gaps_use_existing_evidence_and_exact_required_facts() -> None:
    cases = {case.case_id: case for group in _all_calibration_groups().values() for case in group}
    expected = {
        "calibration-034": (
            "posting:calibration-034:required_qualification:runtime-performance",
            {"profile:cal-profile-04:e3", "profile:cal-profile-04:e4"},
        ),
        "calibration-040": (
            "posting:calibration-040:required_qualification:actuator-controls-integration",
            {"profile:cal-profile-04:e5", "profile:cal-profile-04:e7"},
        ),
        "calibration-042": (
            "posting:calibration-042:required_qualification:interrupt-dma-depth",
            {"profile:cal-profile-05:e1", "profile:cal-profile-05:e2"},
        ),
        "calibration-052": (
            "posting:calibration-052:required_qualification:design-control-depth",
            {"profile:cal-profile-06:e2", "profile:cal-profile-06:e5"},
        ),
        "calibration-060": (
            "posting:calibration-060:required_qualification:bench-commissioning",
            {"profile:cal-profile-06:e3", "profile:cal-profile-06:e4"},
        ),
    }
    for case_id, (qualification_id, evidence_refs) in expected.items():
        case = cases[case_id]
        qualification = next(item for item in case.required_qualifications if item.qualification_id == qualification_id)
        gap = next(reason for reason in case.proposed_material_gap_reasons if reason.code == "insufficient_evidence" and qualification_id in reason.evidence_references)
        assert qualification.evidence_references
        assert set(evidence_refs) <= set(qualification.evidence_references) | set(gap.evidence_references)
        assert qualification_id in gap.evidence_references
        assert set(evidence_refs) <= set(gap.evidence_references)
        assert any("production" in word or "ownership" in word or "depth" in word for word in gap.statement.casefold().split())
        for reference in evidence_refs:
            item = next(item for item in case.profile.evidence_items if item.evidence_id == reference)
            if reference == "profile:cal-profile-04:e7":
                assert case_id == "calibration-040"
                assert item.evidence_kind == "coursework"
            else:
                assert item.evidence_kind != "coursework"


def test_boundary_critical_cores_remain_matched_and_coursework_stays_non_production() -> None:
    cases = {case.case_id: case for group in _all_calibration_groups().values() for case in group}
    for case_id in ("calibration-034", "calibration-040", "calibration-042", "calibration-052", "calibration-060"):
        case = cases[case_id]
        gap_refs = {ref for reason in case.proposed_material_gap_reasons for ref in reason.evidence_references}
        assert all(item.evidence_references and item.requirement_id not in gap_refs for item in case.critical_requirements), case_id
    actuator = next(item for item in cases["calibration-040"].required_qualifications if "actuator" in item.text.casefold())
    assert "profile:cal-profile-04:e7" not in actuator.evidence_references
    assert next(item for item in cases["calibration-040"].profile.evidence_items if item.evidence_id.endswith(":e7")).evidence_kind == "coursework"


def test_case_048_rationale_separates_direct_technical_alignment_from_authorization() -> None:
    case = next(case for group in _all_calibration_groups().values() for case in group if case.case_id == "calibration-048")
    rationale = case.rationale.casefold()
    assert all(term in rationale for term in ("c peripheral drivers", "board diagnostics", "secure controller firmware", "can-connected device"))
    assert "hard_authorization_conflict" in {reason.code for reason in case.proposed_eligibility_reasons}
    assert "united states work authorization without sponsorship" in rationale
    assert "canada-only authorization" in rationale
    assert "peripheral technical context" not in rationale
