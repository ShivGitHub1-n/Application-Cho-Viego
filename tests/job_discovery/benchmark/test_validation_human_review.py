# ruff: noqa: E501

from __future__ import annotations

import json
import re
import tempfile
from collections import defaultdict
from pathlib import Path

from tests.job_discovery.benchmark.loader import load_development_cases

ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "job_discovery" / "benchmark"


def test_case_006_source_wording_is_grammatical_without_structural_drift() -> None:
    cases = json.loads((ROOT / "calibration.json").read_text(encoding="utf-8"))
    case = next(item for item in cases if item["case_id"] == "calibration-006")
    assert ". and requires Canadian work authorization" not in case["posting"]["description"]
    assert "The Toronto position has a hybrid schedule with regular office presence and requires Canadian work authorization; no sponsorship is available." in case["posting"]["description"]
    assert case["posting"]["location"] == "Toronto, ON"
    assert case["posting"]["work_arrangement"] == "hybrid"
    assert case["posting"]["employment_type"] == "full_time"
    assert case["expected_eligibility"] == "eligible"
    assert case["proposed_grade"] == "weak"


def test_stage_b_approval_record_is_explicit_and_calibration_is_not_validation() -> None:
    approval = json.loads((ROOT / "approval.json").read_text(encoding="utf-8"))
    assert approval["benchmark_status"] == "partially_approved"
    assert approval["calibration"]["approved"] is True
    assert approval["calibration"]["approval_status"] == "approved"
    assert approval["calibration"]["approved_at"] == "2026-07-23"
    assert approval["calibration"]["reviewer_authority"] == "project owner"
    assert approval["calibration"]["decision"] == "approved as proposed"
    assert approval["calibration"]["labels_frozen"] is True
    assert len(approval["calibration"]["approved_checksum"]) == 64
    assert approval["validation"]["approved"] is True
    assert approval["validation"]["approval_status"] == "approved"
    assert approval["validation"]["proposal_status"] == "proposed"
    assert approval["validation"]["labels_frozen"] is True
    assert approval["validation"]["approved_on"] == "2026-07-23"
    assert approval["validation"]["reviewer_authority"] == "project_owner"
    assert approval["validation"]["decision"] == "approved_as_proposed"
    assert approval["validation"]["reviewer_decision"] == ""
    assert approval["validation"]["reviewer_notes"] == ""
    assert approval["locked"]["approved"] is False
    assert approval["locked"]["approval_status"] == "unapproved"
    assert approval["locked"]["sealed"] is True


def test_validation_explanation_corrections_preserve_authoritative_pair_direction() -> None:
    cases = {case.case_id: case for case in load_development_cases() if case.split == "validation"}
    pair = next(pair for pair in cases["validation-070"].comparable_pair_annotations if pair.other_case_id == "validation-064")
    assert pair.relationship == "preferred_to_other"
    assert pair.rationale == (
        "Dawn Quarry is preferred because its direct backend core and limited event-replay depth gap support a Good grade, "
        "while Northline has two material required stretches in production Kubernetes operations and model-endpoint rollout support."
    )
    assert "Dawn Quarry is preferred" in pair.rationale
    assert "Northline is preferred" not in pair.rationale
    assert cases["validation-070"].proposed_grade == "good"
    assert cases["validation-064"].proposed_grade == "weak"


def test_validation_064_rationale_names_both_material_required_stretches() -> None:
    case = next(case for case in load_development_cases() if case.case_id == "validation-064")
    assert case.rationale == (
        "This is Weak because customer-facing service monitoring and incident investigation are demonstrated, while production "
        "Kubernetes cluster operations, sustained on-call ownership, and production model-endpoint rollout, rollback, and "
        "post-release support remain two material required stretches; eligibility is confirmed."
    )
    assert "Kubernetes cluster operations" in case.rationale
    assert "sustained on-call ownership" in case.rationale
    assert "model-endpoint rollout, rollback, and post-release support" in case.rationale


def test_overall_benchmark_is_not_approved_when_only_calibration_is_approved() -> None:
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["approval_status"] == "partially_approved"
    assert manifest["proposal_status"] == "partially_approved"
    assert manifest["approved"] is False


def test_validation_approval_is_explicit_and_split_specific() -> None:
    approval = json.loads((ROOT / "approval.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    validation = approval["validation"]
    assert validation["approved"] is True
    assert validation["approval_status"] == "approved"
    assert validation["labels_frozen"] is True
    assert validation["approved_on"] == "2026-07-23"
    assert validation["reviewer_authority"] == "project_owner"
    assert validation["decision"] == "approved_as_proposed"
    assert len(validation["approved_checksum"]) == 64
    assert len(validation["semantic_decision_digest"]) == 64
    assert manifest["approval"]["validation_approval_status"] == "approved"
    assert manifest["approval"]["validation_labels_frozen"] is True


def test_approved_validation_loader_preserves_proposed_values_and_verifies_checksums() -> None:
    from tests.job_discovery.benchmark.approval import load_approved_validation

    cases = load_approved_validation()
    raw = json.loads((ROOT / "validation.json").read_text(encoding="utf-8"))
    by_id = {item["case_id"]: item for item in raw}
    assert len(cases) == 20
    assert [case.case_id for case in cases] == [f"validation-{number:03d}" for number in range(61, 81)]
    assert all(case.approval_status == "approved" for case in cases)
    assert all(case.stage == "B" for case in cases)
    assert all(by_id[case.case_id]["proposed_grade"] == case.proposed_grade for case in cases)
    assert all(by_id[case.case_id]["expected_eligibility"] == case.expected_eligibility for case in cases)


def test_approved_validation_baselines_exclude_locked_cases_and_metrics() -> None:
    from tests.job_discovery.benchmark.report import generate_pilot_artifacts

    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory)
        generate_pilot_artifacts(output / "review.html", output / "review.csv", output / "baseline.json", "validation-group-01")
        payload = json.loads((output / "baseline.json").read_text(encoding="utf-8"))
    assert all(not row["case_id"].startswith("locked-") for row in payload["predictions"])
    assert payload["locked_split"] == "not touched or evaluated"


def test_validation_approved_checksum_rejects_semantic_mutation_but_ignores_presentation() -> None:
    from tests.job_discovery.benchmark.approval import approved_validation_checksum

    cases = [json.loads(json.dumps(item)) for item in json.loads((ROOT / "validation.json").read_text(encoding="utf-8"))]
    baseline = approved_validation_checksum(cases)
    cases[0]["reviewer_notes"] = "presentation-only note"
    assert approved_validation_checksum(cases) == baseline
    cases[0]["proposed_grade"] = "weak"
    assert approved_validation_checksum(cases) != baseline


def test_validation_semantic_digest_excludes_only_authorized_explanation_edits() -> None:
    from tests.job_discovery.benchmark.approval import validation_semantic_decision_digest

    cases = [json.loads(json.dumps(item)) for item in json.loads((ROOT / "validation.json").read_text(encoding="utf-8"))]
    baseline = validation_semantic_decision_digest(cases)
    case064 = next(item for item in cases if item["case_id"] == "validation-064")
    case064["rationale"] = "Authorized explanation wording."
    case070 = next(item for item in cases if item["case_id"] == "validation-070")
    pair = next(item for item in case070["comparable_pair_annotations"] if item["other_case_id"] == "validation-064")
    pair["rationale"] = "Authorized pair explanation wording."
    assert validation_semantic_decision_digest(cases) == baseline
    cases[0]["proposed_grade"] = "weak"
    assert validation_semantic_decision_digest(cases) != baseline


def test_calibration_loader_uses_explicit_calibration_approval_not_overall_flag() -> None:
    from tests.job_discovery.benchmark.approval import load_approved_calibration

    assert len(load_approved_calibration()) == 60


def test_validation_fixture_has_exact_new_membership_and_coverage() -> None:
    cases = [case for case in load_development_cases() if case.split == "validation"]
    assert [case.case_id for case in cases] == [f"validation-{number:03d}" for number in range(61, 81)]
    groups: dict[str, list[object]] = defaultdict(list)
    for case in cases:
        groups[case.ranking_group].append(case)
    assert sorted(groups) == ["validation-group-01", "validation-group-02"]
    assert all(len(group) == 10 for group in groups.values())
    for group in groups.values():
        assert {case.proposed_grade for case in group} == {"excellent", "good", "weak", "dont_match"}
        assert {case.expected_eligibility for case in group} == {"eligible", "unknown", "ineligible"}
        assert any("keyword_trap" in case.review_tags for case in group)
        assert any(case.expected_eligibility == "unknown" and case.proposed_provisional for case in group)


def test_validation_sources_are_independently_authored_and_review_ready() -> None:
    cases = [case for case in load_development_cases() if case.split == "validation"]
    sentences: list[str] = []
    for case in cases:
        description = case.posting.description
        assert 120 <= len(description.split()) <= 300
        assert not re.search(r"validation-(?:group-)?\d+|\b(?:benchmark|candidate|profile|grade|fit|review|apply-worthy)\b", description, re.I)
        sentences.extend(re.split(r"(?<=[.!?])\s+", description))
    normalized = [" ".join(sentence.casefold().split()) for sentence in sentences if sentence.strip()]
    assert len(normalized) == len(set(normalized))
    assert all(".;" not in sentence and "  " not in sentence for sentence in sentences)


def test_validation_sources_contain_no_candidate_evaluator_comparisons() -> None:
    banned = re.compile(
        r"(?:the profile|profile evidence|reviewed kubernetes|existing bench work demonstrates|"
        r"coursework supplies|does not establish|available profile evidence|candidate-specific)",
        re.I,
    )
    for case in load_development_cases():
        if case.split == "validation":
            assert not banned.search(case.posting.description), case.case_id


def test_validation_location_and_sponsorship_authority_is_explicit() -> None:
    cases = {case.case_id: case for case in load_development_cases() if case.split == "validation"}
    for case in cases.values():
        location_fact = next(fact for fact in case.posting.posting_facts if fact.kind == "location")
        assert location_fact.statement
        if case.case_id in {"validation-062", "validation-064"}:
            assert case.posting.location == "Canada"
            assert "within Canada" in case.posting.description
            assert "within Canada" in location_fact.statement
        elif case.posting.work_arrangement == "remote" and case.posting.location != "Remote geography unstated":
            assert case.posting.location.split(",")[0] in case.posting.description
        if case.posting.posting_sponsorship_available is True:
            assert re.search(r"sponsorship (?:is )?available|can sponsor|will sponsor|offer(?:s|ing)? sponsorship|provide(?:s)? sponsorship|makes sponsorship available", case.posting.description, re.I)
            assert re.search(r"sponsorship (?:is )?available|can sponsor|will sponsor|offer(?:s|ing)? sponsorship|provide(?:s)? sponsorship|makes sponsorship available", case.posting.posting_facts[[fact.kind for fact in case.posting.posting_facts].index("authorization")].statement, re.I)
        elif case.posting.posting_sponsorship_available is False:
            assert re.search(r"sponsorship is (?:not available|unavailable)|cannot sponsor|does not sponsor|no sponsorship", case.posting.description, re.I)
        else:
            assert re.search(r"unstated|unresolved|not stated", case.posting.description, re.I)


def test_explicit_source_qualifications_have_structured_authority() -> None:
    cases = {case.case_id: case for case in load_development_cases() if case.split == "validation"}
    expected = {
        "validation-061": {"java-maintenance"},
        "validation-062": {"python-automation"},
        "validation-063": {"incident-investigation"},
        "validation-067": {"release-quality", "model-serving"},
    }
    for case_id, fact_slugs in expected.items():
        case = cases[case_id]
        facts = {fact.fact_id.rsplit(":", 1)[-1] for fact in case.posting.posting_facts}
        requirement_ids = {
            (item.requirement_id if hasattr(item, "requirement_id") else item.qualification_id).rsplit(":", 1)[-1]
            for item in [*case.critical_requirements, *case.required_qualifications, *case.preferred_qualifications]
        }
        assert fact_slugs <= facts
        assert fact_slugs <= requirement_ids
    assert "graduate degree" not in cases["validation-065"].posting.description.casefold()
    assert "five years" not in cases["validation-066"].posting.description.casefold()


def test_unknown_credentials_cannot_authorize_a_hard_license_conflict() -> None:
    cases = {case.case_id: case for case in load_development_cases() if case.split == "validation"}
    assert cases["validation-069"].profile.professional_license_status == "confirmed_none"
    reason = cases["validation-069"].proposed_eligibility_reasons[0]
    assert reason.code == "hard_license_conflict"
    assert reason.profile_fact == "profile:val-profile-01:professional-license-status"
    assert "profile:val-profile-01:education" not in reason.evidence_references


def test_positive_reasons_are_pure_and_case_specific() -> None:
    forbidden = re.compile(r"peripheral|does not|cannot|conflict|gap|missing|eligib", re.I)
    cases = {case.case_id: case for case in load_development_cases() if case.split == "validation"}
    for case in cases.values():
        for reason in case.proposed_positive_reasons:
            assert not forbidden.search(reason.statement), (case.case_id, reason.statement)
    expected = {
        "validation-065": ("profile:val-profile-01:e6", "posting:validation-065:preferred_qualification:ai"),
        "validation-066": ("profile:val-profile-01:e1", "profile:val-profile-01:e2", "posting:validation-066:preferred_qualification:sql"),
        "validation-067": ("profile:val-profile-01:e1", "profile:val-profile-01:e2", "profile:val-profile-01:e4", "profile:val-profile-01:e5"),
        "validation-068": ("profile:val-profile-01:e1", "profile:val-profile-01:e4", "posting:validation-068:preferred_qualification:platform"),
        "validation-069": ("profile:val-profile-01:e2", "profile:val-profile-01:e3", "posting:validation-069:preferred_qualification:data"),
        "validation-075": ("profile:val-profile-02:e2", "posting:validation-075:preferred_qualification:ros"),
        "validation-076": ("profile:val-profile-02:e1", "profile:val-profile-02:e2", "profile:val-profile-02:e3", "posting:validation-076:preferred_qualification:bringup"),
        "validation-077": ("profile:val-profile-02:e1", "profile:val-profile-02:e4", "profile:val-profile-02:e5", "profile:val-profile-02:e6", "posting:validation-077:critical_requirement:verification-core", "posting:validation-077:responsibility:secure-verification"),
        "validation-078": ("profile:val-profile-02:e2", "profile:val-profile-02:e4", "profile:val-profile-02:e5", "posting:validation-078:preferred_qualification:integration"),
        "validation-079": ("profile:val-profile-02:e1", "profile:val-profile-02:e3", "profile:val-profile-02:e4", "posting:validation-079:preferred_qualification:embedded"),
    }
    for case_id, refs in expected.items():
        actual = set(reference for reason in cases[case_id].proposed_positive_reasons for reference in reason.evidence_references)
        assert set(refs) <= actual, case_id


def test_validation_boundary_repairs_are_grounded() -> None:
    cases = {case.case_id: case for case in load_development_cases() if case.split == "validation"}
    case070 = cases["validation-070"]
    assert (case070.proposed_grade, case070.expected_eligibility, case070.proposed_provisional, case070.normal_feed_visible, case070.apply_worthy, case070.human_ranking_tier) == ("good", "unknown", True, True, True, "tier_2")
    gap070 = next(gap for gap in case070.important_gaps if gap.code == "insufficient_replay_depth")
    assert "profile:val-profile-01:e3" in gap070.evidence_references
    assert "posting:validation-070:required_qualification:replay" in gap070.evidence_references
    gap064 = next(gap for gap in cases["validation-064"].important_gaps if gap.code == "insufficient_ml_platform_depth")
    assert set(gap064.evidence_references) == {"profile:val-profile-01:e6", "posting:validation-064:required_qualification:ml-platform"}
    gap076 = next(gap for gap in cases["validation-076"].important_gaps if gap.code == "insufficient_electrical_design")
    assert set(gap076.evidence_references) == {
        "profile:val-profile-02:e8",
        "posting:validation-076:critical_requirement:design-core",
        "posting:validation-076:required_qualification:hardware",
    }
    assert all("coursework" not in item.evidence_kind for item in cases["validation-064"].profile.evidence_items if item.evidence_id in gap064.evidence_references)


def test_validation_group_01_pair_order_follows_new_good_boundary() -> None:
    cases = {case.case_id: case for case in load_development_cases() if case.split == "validation"}
    expected = {
        "validation-061": {"validation-062", "validation-063", "validation-064", "validation-070"},
        "validation-062": {"validation-063", "validation-064", "validation-070"},
        "validation-063": {"validation-064", "validation-070"},
        "validation-070": {"validation-064"},
    }
    for case_id, others in expected.items():
        annotations = {item.other_case_id for item in cases[case_id].comparable_pair_annotations}
        assert others <= annotations


def test_validation_pair_annotations_cover_visible_cases() -> None:
    cases = [case for case in load_development_cases() if case.split == "validation"]
    for group in {case.ranking_group for case in cases}:
        group_cases = [case for case in cases if case.ranking_group == group]
        visible = [case for case in group_cases if case.normal_feed_visible]
        pairs = {
            tuple(sorted((case.case_id, pair.other_case_id)))
            for case in visible
            for pair in case.comparable_pair_annotations
            if pair.other_case_id in {item.case_id for item in visible}
        }
        assert len(pairs) == len(visible) * (len(visible) - 1) // 2


def test_validation_manifest_records_exact_proposed_ids() -> None:
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["splits"]["validation"]["proposed_case_ids"] == [
        f"validation-{number:03d}" for number in range(61, 81)
    ]
    assert manifest["splits"]["validation"]["case_count"] == 20


def test_all_development_source_metadata_and_atomic_authority_agree() -> None:
    iso = re.compile(r"\b20\d{2}-\d{2}-\d{2}\b")
    for case in load_development_cases():
        description_dates = iso.findall(case.posting.description)
        date_facts = [fact for fact in case.posting.posting_facts if fact.kind == "posting_date"]
        employment_facts = [fact for fact in case.posting.posting_facts if fact.kind == "employment_type"]
        level_facts = [fact for fact in case.posting.posting_facts if fact.kind == "level"]
        assert len(employment_facts) == 1
        assert "full-time" in case.posting.description.casefold()
        assert len(level_facts) == 1
        if case.posting.posted_date is None:
            assert description_dates == []
            assert len(date_facts) == 1
            assert re.search(r"missing|unstated|not stated|does not state", date_facts[0].statement, re.I)
            if case.posting.posting_level == "unknown":
                assert re.search(r"unknown|unstated|not stated", case.posting.description, re.I)
        else:
            assert description_dates == [case.posting.posted_date]
            assert len(date_facts) == 1
            assert case.posting.posted_date in date_facts[0].statement
            assert case.posting.posted_date <= case.source.retrieved_at[:10]
        if case.posting.posting_level != "unknown":
            assert case.posting.posting_level in case.posting.description.casefold()


def test_validation_reviewer_fields_are_blank_and_decisions_remain_proposed() -> None:
    validation = [case for case in load_development_cases() if case.split == "validation"]
    assert all(case.stage == "A" and case.proposal_status == "proposed" for case in validation)
    assert all(case.approval_status == "unapproved" for case in validation)
    assert all(case.reviewer_decision == "" and case.reviewer_notes == "" for case in validation)


def test_validation_references_resolve_and_requirement_fact_ids_match() -> None:
    for case in load_development_cases():
        facts = {fact.fact_id for fact in case.posting.posting_facts}
        profile = {item.evidence_id for item in case.profile.evidence_items}
        profile.update({
            f"profile:{case.profile.profile_ref}:experience-years",
            f"profile:{case.profile.profile_ref}:education",
            f"profile:{case.profile.profile_ref}:professional-license-status",
            f"profile:{case.profile.profile_ref}:clearance-status",
        })
        profile.update({
            f"preferences:{case.profile.profile_ref}:work_authorization",
            f"preferences:{case.profile.profile_ref}:target_level",
        })
        for requirement in [*case.critical_requirements, *case.required_qualifications, *case.preferred_qualifications]:
            assert requirement.fact_id == requirement.requirement_id if hasattr(requirement, "requirement_id") else requirement.fact_id == requirement.qualification_id
            assert requirement.fact_id in facts
        for reason in [*case.proposed_positive_reasons, *case.proposed_material_gap_reasons, *case.proposed_reasons]:
            assert len(reason.evidence_references) == len(set(reason.evidence_references))
            assert set(reason.evidence_references) <= facts | profile


def test_validation_baselines_expose_typed_ranks_and_approved_frozen_status(tmp_path: Path) -> None:
    from tests.job_discovery.benchmark.report import generate_pilot_artifacts

    for group in ("validation-group-01", "validation-group-02"):
        output = tmp_path / group
        generate_pilot_artifacts(output.with_suffix(".html"), output.with_suffix(".csv"), output.with_suffix(".json"), group)
        payload = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
        assert payload["status"] == "approved"
        assert payload["approval_status"] == "approved"
        assert payload["normal_feed_pair_count"] == 10
        assert all(isinstance(row["typed_sort_key"], list) and row["current_rank"] for row in payload["predictions"])


def test_all_development_posting_sentences_are_unique_across_splits() -> None:
    sentences: dict[str, str] = {}
    for case in load_development_cases():
        for sentence in re.split(r"(?<=[.!?])\s+", case.posting.description):
            normalized = " ".join(sentence.casefold().split())
            if normalized:
                assert normalized not in sentences, (case.case_id, sentences[normalized])
                sentences[normalized] = case.case_id
