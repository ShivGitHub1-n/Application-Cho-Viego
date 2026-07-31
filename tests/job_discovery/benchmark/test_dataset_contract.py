# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.job_discovery.benchmark.loader import (
    LockedBenchmarkAccessError,
    load_development_cases,
    load_locked_cases,
    locked_proposal_metadata,
)

ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "job_discovery" / "benchmark"
META_WORDS = re.compile(r"\b(?:scenario|synthetic|marker|proposal|benchmark|human review)\b", re.I)
FACT_STOP_WORDS = {"a", "an", "and", "are", "be", "for", "from", "in", "is", "of", "on", "or", "the", "to", "this", "with", "that", "its", "does", "not"}
EXPECTED = {"calibration": 60, "validation": 20}
ROLE_FAMILIES = {
    "software_engineering", "backend_engineering", "data_engineering", "machine_learning",
    "computer_vision", "robotics", "autonomous_systems", "embedded_systems", "firmware",
    "hardware_systems_integration", "controls", "mechatronics", "testing", "verification", "mixed_family",
}


def _dev():
    return load_development_cases()


def _refs(case):
    profile = {item.evidence_id: item for item in case.profile.evidence_items}
    posting = {item.requirement_id: item for item in case.critical_requirements}
    posting.update({item.qualification_id: item for item in case.required_qualifications})
    posting.update({item.qualification_id: item for item in case.preferred_qualifications})
    posting.update({fact.fact_id: fact for fact in case.posting.posting_facts})
    posting.update({f"posting:resp:{case.case_id}:primary": object()})
    posting.update({f"preferences:{case.profile.profile_ref}:work_authorization": object()})
    posting.update({f"preferences:{case.profile.profile_ref}:target_level": object()})
    profile.update({
        f"profile:{case.profile.profile_ref}:experience-years": SimpleNamespace(
            evidence_quality="verified",
            statement=f"The reviewed profile records {case.profile.experience_years:g} years of experience.",
        )
    })
    profile.update({
        f"profile:{case.profile.profile_ref}:education": SimpleNamespace(
            evidence_quality="verified",
            statement=case.profile.education_summary,
        )
    })
    profile.update({
        f"profile:{case.profile.profile_ref}:professional-license-status": SimpleNamespace(
            evidence_quality="verified",
            statement=f"Professional-license status: {case.profile.professional_license_status}.",
        ),
        f"profile:{case.profile.profile_ref}:clearance-status": SimpleNamespace(
            evidence_quality="verified",
            statement=f"Clearance status: {case.profile.clearance_status}.",
        ),
    })
    return profile, posting


def test_exact_counts_and_ten_independent_tailored_groups() -> None:
    cases = _dev()
    assert Counter(case.split for case in cases) == EXPECTED
    groups = defaultdict(list)
    for case in cases:
        groups[case.ranking_group].append(case)
    assert len(groups) == 8
    assert Counter(case.split for case in cases if case.ranking_group.startswith("calibration")) == {"calibration": 60}
    assert Counter(case.split for case in cases if case.ranking_group.startswith("validation")) == {"validation": 20}
    assert sorted(map(len, groups.values())) == [10] * 8
    assert all(len({case.profile.profile_ref for case in group}) == 1 for group in groups.values())
    assert len({case.profile.profile_ref for case in cases}) == 8
    assert all(len({case.preferences.model_dump_json() for case in group}) == 1 for group in groups.values())
    source_text = " ".join(case.posting.description.casefold() for case in cases)
    assert all(level in source_text for level in ("mid-level", "senior", "director", "principal"))


def test_manifest_and_locked_proposal_metadata_are_stable_without_locked_deserialization() -> None:
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["approval_status"] == "partially_approved"
    assert manifest["approved"] is False
    assert manifest["approval"]["calibration_approval_status"] == "approved"
    assert manifest["approval"]["validation_approval_status"] == "approved"
    meta = locked_proposal_metadata()
    assert meta["case_count"] == 20
    assert meta["sha256"] == meta["bytes_sha256"]
    assert len(meta["proposed_case_ids"]) == 20


def test_locked_loading_requires_marker_and_explicit_authorization() -> None:
    with pytest.raises(LockedBenchmarkAccessError):
        load_locked_cases(authorized=False)
    with pytest.raises(LockedBenchmarkAccessError):
        load_locked_cases(authorized=True)


def test_profile_identity_and_evidence_payloads_do_not_cross_development_splits() -> None:
    cases = _dev()
    by_split = {split: [case for case in cases if case.split == split] for split in EXPECTED}
    refs = {split: {case.profile.profile_ref for case in rows} for split, rows in by_split.items()}
    assert refs["calibration"].isdisjoint(refs["validation"])
    payloads = {
        split: {json.dumps([item.model_dump() for item in case.profile.evidence_items], sort_keys=True, separators=(",", ":")) for case in rows}
        for split, rows in by_split.items()
    }
    assert payloads["calibration"].isdisjoint(payloads["validation"])


def test_postings_are_realistic_and_have_no_fixture_meta_language_or_duplicates() -> None:
    cases = _dev()
    assert not any(META_WORDS.search(value) for case in cases for value in (case.posting.title, case.posting.company, case.posting.description))
    normalized = [" ".join(f"{case.posting.title} {case.posting.description}".casefold().split()) for case in cases]
    assert len(normalized) == len(set(normalized))
    tokens = [set(re.findall(r"[a-z]+", text)) for text in normalized]
    for left in range(len(tokens)):
        for right in range(left):
            similarity = len(tokens[left] & tokens[right]) / len(tokens[left] | tokens[right])
            assert similarity < 0.9, (cases[left].case_id, cases[right].case_id, similarity)


def test_role_family_grade_and_hard_case_coverage() -> None:
    cases = _dev()
    assert {case.scenario_category for case in cases} >= ROLE_FAMILIES - {"firmware"}
    assert {case.proposed_grade for case in cases} == {"excellent", "good", "weak", "dont_match"}
    tags = {tag for case in cases for tag in case.review_tags}
    assert {"keyword_trap", "sector_trap", "work_authorization", "level_mismatch", "critical_gap"} <= tags
    assert sum(case.expected_eligibility == "ineligible" for case in cases) >= 4
    assert sum(case.expected_eligibility == "unknown" for case in cases) >= 4
    assert sum(case.proposed_grade == "weak" for case in cases) >= 8


def test_evidence_and_gap_semantic_consistency() -> None:
    for case in _dev():
        profile, posting = _refs(case)
        for reason in [*case.proposed_eligibility_reasons, *case.proposed_reasons, *case.important_gaps]:
            assert reason.evidence_references
            assert all(ref in profile or ref in posting for ref in reason.evidence_references)
        for item in case.important_evidence:
            assert item.reference in profile
            assert item.evidence_quality == profile[item.reference].evidence_quality
        for reason in case.important_gaps:
            if "no demonstrated evidence" in reason.statement:
                assert not any(ref in profile for ref in reason.evidence_references)
            if "only as reviewed skill" in reason.statement:
                assert any(profile[ref].evidence_kind == "reviewed_skill" for ref in reason.evidence_references if ref in profile)
        for reason in case.proposed_positive_reasons:
            assert any(ref in profile for ref in reason.evidence_references)
            assert any(ref in posting for ref in reason.evidence_references)
        for requirement in case.critical_requirements:
            requirement_terms = {
                token
                for token in re.findall(r"[a-z0-9]+", requirement.text.casefold())
                if token not in FACT_STOP_WORDS and len(token) > 2
            }
            description_terms = set(re.findall(r"[a-z0-9]+", case.posting.description.casefold()))
            assert not requirement_terms or len(requirement_terms & description_terms) >= max(1, len(requirement_terms) // 3)
        for reason in case.proposed_eligibility_reasons:
            assert any(ref.startswith("posting:") for ref in reason.evidence_references)
            assert any(ref.startswith(("preferences:", "profile:")) for ref in reason.evidence_references)


def test_proposed_rubric_invariants_and_provisional_independence() -> None:
    for case in _dev():
        tags = set(case.review_tags)
        hard = case.expected_eligibility == "ineligible"
        if case.proposed_grade == "excellent":
            assert not hard and not any(reason.code == "critical_gap" for reason in case.proposed_material_gap_reasons)
            assert all(item.evidence_quality == "verified" for item in case.important_evidence)
            assert all(item.evidence_kind not in {"reviewed_skill", "coursework"} for item in case.profile.evidence_items if item.evidence_id in {ref.reference for ref in case.important_evidence})
            assert case.important_evidence
            assert any(requirement.evidence_references for requirement in case.critical_requirements)
        if case.proposed_grade == "good":
            assert not hard and case.proposed_positive_reasons
        if case.proposed_grade == "weak":
            assert case.proposed_material_gap_reasons
        if case.proposed_grade == "dont_match":
            assert hard or case.proposed_material_gap_reasons or "keyword_trap" in tags or "sector_trap" in tags
            assert not case.apply_worthy
        assert "stage_a_human_review_pending" not in case.provisional_reason_codes
        if case.proposed_provisional:
            assert case.provisional_reason_codes
            assert any(code in {"incomplete_description", "unresolved_authorization", "missing_date", "uncertain_level", "remote_ambiguity"} for code in case.provisional_reason_codes)
        else:
            assert not case.provisional_reason_codes
        if case.expected_eligibility == "ineligible":
            assert not case.apply_worthy
        assert case.human_ranking_tier == {"excellent": "tier_1", "good": "tier_2", "weak": "tier_3", "dont_match": "not_ranked"}[case.proposed_grade]


def test_each_group_has_explicit_non_tied_pairs_and_coherent_apply_worthy_labels() -> None:
    groups = defaultdict(list)
    for case in _dev():
        groups[case.ranking_group].append(case)
    for group, cases in groups.items():
        pair_keys = set()
        for case in cases:
            assert case.apply_worthy or case.human_ranking_tier == "not_ranked" or case.proposed_grade == "weak"
            for pair in case.comparable_pair_annotations:
                assert pair.other_case_id in {item.case_id for item in cases}
                key = tuple(sorted((case.case_id, pair.other_case_id)))
                pair_keys.add(key)
                assert pair.rationale
        visible_count = sum(case.normal_feed_visible for case in cases)
        if group in {"calibration-group-01", "calibration-group-02", "calibration-group-03"}:
            assert len(pair_keys) == visible_count * (visible_count - 1) // 2, group
        else:
            assert len(pair_keys) >= 10, group


def test_proposal_references_are_complete_and_split_membership_is_immutable() -> None:
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    for split, expected in EXPECTED.items():
        raw = (ROOT / f"{split}.json").read_bytes()
        assert hashlib.sha256(raw).hexdigest() == manifest["splits"][split]["sha256"]
        assert manifest["splits"][split]["case_count"] == expected
        assert all(case.review_required and case.approval_status == "unapproved" for case in _dev() if case.split == split)
