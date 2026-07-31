# ruff: noqa: E402, E501

from __future__ import annotations

import argparse
import csv
import html
import json
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

_SOURCE_ROOT = Path(__file__).resolve().parents[3] / "src"
if str(_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SOURCE_ROOT))

from resume_tailor.domain.job_discovery.capabilities import ProfileCapabilityIndexBuilder
from resume_tailor.domain.job_discovery.deduplication import JobDeduplicator
from resume_tailor.domain.job_discovery.eligibility import EligibilityEvaluator
from resume_tailor.domain.job_discovery.models import (
    ConnectorType,
    JobLevel,
    JobSearchPreferences,
    ProfileCapabilityIndex,
    SourceJobRecord,
    SupportedJobSource,
    VerificationConfidence,
    VerificationStatus,
    WorkArrangement,
    WorkArrangementPreferenceMode,
)
from resume_tailor.domain.job_discovery.normalization import (
    normalize_job_record,
    normalize_job_term,
)
from resume_tailor.domain.job_discovery.scoring import (
    DeterministicExplanationBuilder,
    ScoringPolicy,
    recommendation_sort_key,
    score_label,
)
from resume_tailor.domain.models import (
    ContactInfo,
    EducationRecord,
    EntityKind,
    EvidenceItem,
    MasterProfile,
    ResumeItem,
    ReviewedTechnicalSkill,
    RoleFamily,
    TechnicalSkillCategory,
)
from tests.job_discovery.benchmark.approval import (
    load_approved_calibration,
    load_approved_validation,
)
from tests.job_discovery.benchmark.loader import load_development_cases
from tests.job_discovery.benchmark.metrics import (
    CurrentPrediction,
    MetricCase,
    calculate_quality_metrics,
    canonical_json,
    critical_gap_fact_ids,
    current_explanation_heuristic_traceability,
    proposed_reference_structural_validity,
)
from tests.job_discovery.benchmark.models import BenchmarkCase

AS_OF = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
STAGE_A_NOTICE = (
    "PRELIMINARY | PROPOSED LABELS | NOT APPROVED GROUND TRUTH | "
    "LOCKED SPLIT NOT EVALUATED | User review required before Stage B"
)
CALIBRATION_APPROVED_NOTICE = (
    "APPROVED CALIBRATION | LABELS FROZEN | APPROVED 2026-07-23 BY PROJECT OWNER | "
    "FIT GROUND TRUTH, NOT HIRING PROBABILITY | VALIDATION REMAINS PROPOSED | LOCKED SPLIT NOT EVALUATED"
)
VALIDATION_PROPOSAL_NOTICE = (
    "VALIDATION PROPOSAL | PROPOSED LABELS | NOT APPROVED GROUND TRUTH | "
    "HUMAN REVIEW REQUIRED | LOCKED SPLIT NOT EVALUATED"
)
VALIDATION_APPROVED_NOTICE = (
    "APPROVED VALIDATION | LABELS FROZEN | APPROVED 2026-07-23 BY PROJECT OWNER | "
    "FIT GROUND TRUTH, NOT HIRING PROBABILITY | LOCKED SPLIT NOT EVALUATED"
)
_ROLE_FAMILY_MAP = {
    "software_engineering": RoleFamily.SOFTWARE_DATA_ENGINEERING,
    "backend_engineering": RoleFamily.SOFTWARE_DATA_ENGINEERING,
    "data_engineering": RoleFamily.SOFTWARE_DATA_ENGINEERING,
    "machine_learning": RoleFamily.AI_ML_MULTIMODAL,
    "computer_vision": RoleFamily.COMPUTER_VISION_PERCEPTION,
    "robotics": RoleFamily.ROBOTICS_MECHATRONICS,
    "autonomous_systems": RoleFamily.AUTONOMOUS_SYSTEMS,
    "embedded_systems": RoleFamily.EMBEDDED_FIRMWARE,
    "firmware": RoleFamily.EMBEDDED_FIRMWARE,
    "hardware_systems_integration": RoleFamily.ROBOTICS_MECHATRONICS,
    "controls": RoleFamily.ROBOTICS_MECHATRONICS,
    "mechatronics": RoleFamily.ROBOTICS_MECHATRONICS,
    "testing": RoleFamily.SOFTWARE_DATA_ENGINEERING,
    "verification": RoleFamily.SOFTWARE_DATA_ENGINEERING,
    "mixed_family": RoleFamily.SOFTWARE_DATA_ENGINEERING,
}
_PROVIDER_SURROGATES = {"synthetic_ats": ConnectorType.GREENHOUSE}


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def benchmark_profile_to_master_profile(profile: object) -> MasterProfile:
    """Translate benchmark evidence into the same authority production uses."""

    evidence_items: list[EvidenceItem] = []
    resume_items: list[ResumeItem] = []
    reviewed_skills: list[ReviewedTechnicalSkill] = []
    coursework: list[str] = []
    for item in profile.evidence_items:
        if item.evidence_kind in {"demonstrated", "transferable_demonstrated"}:
            parent_id = f"resume:{item.evidence_id}"
            evidence_items.append(
                EvidenceItem(
                    id=item.evidence_id,
                    entity_id=parent_id,
                    source_text=item.statement,
                    source_reference=item.provenance,
                    capabilities=item.capabilities,
                    technologies=item.technologies,
                    confirmed=item.demonstrated,
                )
            )
            resume_items.append(
                ResumeItem(
                    id=parent_id,
                    title="Reviewed engineering work",
                    kind=EntityKind.EXPERIENCE,
                    description=item.statement,
                    bullets=[item.statement],
                    technologies=item.technologies,
                    capabilities=item.capabilities,
                )
            )
        elif item.evidence_kind == "reviewed_skill":
                reviewed_skills.extend(
                    ReviewedTechnicalSkill(
                        id=f"{item.evidence_id}:{normalize_job_term(technology)}",
                    value=technology,
                    source_reference=item.provenance,
                )
                for technology in item.technologies or item.capabilities
            )
        elif item.evidence_kind == "coursework":
            coursework.extend(item.technologies or item.capabilities)
    technical_skills = (
        [
            TechnicalSkillCategory(
                id="reviewed:benchmark",
                category="reviewed-only skills",
                skills=reviewed_skills,
            )
        ]
        if reviewed_skills
        else []
    )
    return MasterProfile(
        id=profile.profile_ref,
        user_id=profile.profile_ref,
        display_name="Deidentified benchmark profile",
        contact=ContactInfo(location=profile.current_location),
        education=[
            EducationRecord(
                school="Deidentified Canadian University",
                program=profile.education_summary,
                relevant_coursework=coursework,
            )
        ],
        experiences=resume_items,
        declared_skills=profile.skills,
        technical_skills=technical_skills,
        coursework=coursework,
        evidence=evidence_items,
    )


def _current_inputs(
    case: BenchmarkCase,
) -> tuple[object, JobSearchPreferences, ProfileCapabilityIndex, MasterProfile]:
    posting = case.posting
    provider = case.source.provider.casefold()
    if provider == "lever":
        connector_type = ConnectorType.LEVER
    elif provider == "greenhouse":
        connector_type = ConnectorType.GREENHOUSE
    elif provider in _PROVIDER_SURROGATES:
        connector_type = _PROVIDER_SURROGATES[provider]
    else:
        raise ValueError(f"Unsupported benchmark provider: {case.source.provider}")
    source = SupportedJobSource(
        source_id=case.source.source_id,
        connector_type=connector_type,
        company_name=posting.company,
        board_token=case.source.source_id,
        enabled=True,
        official_base_url="https://jobs.example.test",
    )
    record = SourceJobRecord(
        external_job_id=case.source.external_job_id,
        title=posting.title,
        company_name=posting.company,
        description=posting.description,
        official_url=case.source.source_url,
        location_raw=posting.location,
        work_arrangement=WorkArrangement(posting.work_arrangement),
        posted_at=_parse_datetime(posting.posted_date),
        source_payload={"provider_position": case.source.provider_position},
    )
    job = normalize_job_record(record, source, fetched_at=AS_OF).model_copy(
        update={
            "verification_status": VerificationStatus(
                "verified_active"
                if case.source.verification_status == "verified_active"
                else "verified_status_unknown"
            ),
            "verification_confidence": (
                VerificationConfidence.HIGH
                if case.source.verification_status == "verified_active"
                else VerificationConfidence.LOW
            ),
        }
    )
    if not case.preferences.role_families:
        raise ValueError("Benchmark preferences require at least one role family")
    try:
        role_families = [_ROLE_FAMILY_MAP[value] for value in case.preferences.role_families]
    except KeyError as error:
        raise ValueError(f"Unsupported benchmark role family: {error.args[0]}") from error
    levels = [
        JobLevel(value) if value in {item.value for item in JobLevel} else JobLevel.UNKNOWN
        for value in case.preferences.target_levels
    ]
    locations = []
    if case.preferences.locations:
        from resume_tailor.domain.job_discovery.location import parse_location

        locations = [parse_location(value) for value in case.preferences.locations]
    arrangements = [
        WorkArrangement(value)
        for value in case.preferences.work_arrangements
        if value in {item.value for item in WorkArrangement}
    ]
    preferences = JobSearchPreferences(
        user_id="synthetic-benchmark-user",
        profile_id=case.profile.profile_ref,
        version=1,
        role_family_priority=role_families,
        target_titles=case.preferences.target_titles,
        related_title_variants=[],
        technical_themes=case.profile.skills,
        career_interests=case.preferences.selected_exploration_sectors,
        job_levels=levels,
        locations=locations,
        work_arrangement=arrangements[0] if arrangements else WorkArrangement.UNKNOWN,
        work_arrangement_mode=WorkArrangementPreferenceMode.PREFERRED,
        preferred_companies=case.preferences.preferred_companies,
        work_authorization_constraints=(
            ["Canada work authorization"]
            if case.preferences.work_authorization_status == "confirmed"
            else ["No sponsorship"]
            if case.preferences.work_authorization_status == "conflict"
            else []
        ),
        max_posting_age_days=30,
        created_at=AS_OF,
    )
    master_profile = benchmark_profile_to_master_profile(case.profile)
    profile_index = ProfileCapabilityIndexBuilder().build(master_profile)
    return job, preferences, profile_index, master_profile


class AdapterFailureError(RuntimeError):
    """A current-policy adapter failure is not a prediction and stops the baseline."""


def current_prediction(case: BenchmarkCase) -> CurrentPrediction:
    job, preferences, profile_index, master_profile = _current_inputs(case)
    eligibility = EligibilityEvaluator().assess(job, preferences, as_of=AS_OF, profile=master_profile)
    score = ScoringPolicy().score(job, preferences, profile_index, as_of=AS_OF)
    reasons, gaps = DeterministicExplanationBuilder(preferences).reasons_and_gaps(
        job, job.requirements, profile_index
    )
    explanation_terms = {
        normalize_job_term(term)
        for term in [*job.requirements.required_terms, *job.requirements.preferred_terms]
    }
    trace_terms = {
        *explanation_terms,
        *(normalize_job_term(term) for term in [*job.requirements.degree_requirements, *job.requirements.graduation_requirements]),
        *profile_index.terms,
        normalize_job_term(job.company_name),
        normalize_job_term(job.requirements.job_level.value),
        normalize_job_term(job.role_family.value if job.role_family else ""),
    }
    def explanation_is_traceable(text: str) -> bool:
        normalized = normalize_job_term(text)
        if any(term and term in normalized for term in trace_terms):
            return True
        if "selected role family" in normalized:
            return bool(job.role_family and preferences.role_family_priority)
        if "selected job level" in normalized:
            return bool(job.requirements.job_level.value != "unknown")
        if "company is on your preferred company list" in normalized:
            return normalize_job_term(job.company_name) in {
                normalize_job_term(value) for value in preferences.preferred_companies
            }
        return False

    explanation_traceable = bool(reasons or gaps) and all(
        explanation_is_traceable(text) for text in [*reasons, *gaps]
    )
    component_names = (
        "demonstrated_technical_evidence",
        "required_coverage",
        "role_alignment",
        "level_alignment",
        "education_coursework",
        "preferred_skill_alignment",
        "recency_completeness",
    )
    ranking_key = recommendation_sort_key(job, score, preferences)
    if eligibility.status.value == "ineligible":
        label = "dont_match"
        legacy_grade = "dont_match"
    elif score.label.value == "provisional":
        label = "provisional"
        legacy_grade = {
            "strong": "excellent",
            "good": "good",
            "stretch": "weak",
        }[score_label(score.total).value]
    else:
        label = {"strong": "strong", "good": "good", "stretch": "stretch"}[score.label.value]
        legacy_grade = None
    categories: list[str] = []
    if eligibility.status.value != case.expected_eligibility:
        categories.append("eligibility_disagreement")
    comparison_grade = legacy_grade or {"strong": "excellent", "good": "good", "stretch": "weak", "dont_match": "dont_match"}[label]
    if comparison_grade != case.proposed_grade:
        categories.append("grade_disagreement")
    for tag, category in (("keyword_trap", "keyword_overlap"), ("misleading_title", "title_responsibility_disagreement"), ("level_mismatch", "level_mismatch"), ("incomplete_description", "incomplete_posting")):
        if tag in case.review_tags:
            categories.append(category)
    return CurrentPrediction(
        case_id=case.case_id,
        current_label=label,
        current_eligibility=eligibility.status.value,
        provisional=score.provisional,
        legacy_substantive_grade=legacy_grade,
        score=score.total,
        score_components={name: float(getattr(score, name)) for name in component_names},
        failure_categories=sorted(set(categories)),
        current_explanation_traceable=explanation_traceable,
        current_explanation_reasons=reasons,
        current_explanation_gaps=gaps,
        ranking_key=ranking_key,
    )


def _rank_prediction_ids(
    predictions: dict[str, CurrentPrediction],
) -> list[str]:
    return [
        case_id
        for case_id, _ in sorted(
            predictions.items(), key=lambda item: item[1].ranking_key
        )
    ]


def _prediction_map(cases: Iterable[BenchmarkCase]) -> dict[str, CurrentPrediction]:
    case_list = list(cases)
    try:
        predictions = {case.case_id: current_prediction(case) for case in case_list}
    except Exception as error:
        raise AdapterFailureError(
            f"Current-policy adapter failed for benchmark case: {type(error).__name__}"
        ) from error
    groups: dict[str, list[BenchmarkCase]] = {}
    for case in case_list:
        if case.ranking_group:
            groups.setdefault(case.ranking_group, []).append(case)
    for group_cases in groups.values():
        ranked_ids = _rank_prediction_ids(
            {case.case_id: predictions[case.case_id] for case in group_cases}
        )
        for rank, case_id in enumerate(ranked_ids, start=1):
            case = next(item for item in group_cases if item.case_id == case_id)
            predictions[case.case_id] = predictions[case.case_id].model_copy(
                update={"rank": rank}
            )
    return predictions


def _provider_order_diagnostics(cases: list[BenchmarkCase]) -> list[dict[str, object]]:
    results = []
    for case in cases:
        if "provider_order" not in case.review_tags:
            continue
        first = case.model_copy(deep=True)
        second = case.model_copy(deep=True)
        first.source.provider_position = 1
        second.source.provider_position = 99
        first_job, _, _, _ = _current_inputs(first)
        second_job, _, _, _ = _current_inputs(second)
        def canonical(job: object) -> tuple[object, ...]:
            return (
                job.normalized_company_name,
                job.normalized_title,
                job.description,
                tuple(item.term for item in job.requirements.requirements),
                job.role_family.value if job.role_family else None,
            )
        results.append({"case_id": case.case_id, "equivalent_canonical_output": canonical(first_job) == canonical(second_job)})
    return results


def _duplicate_identity_diagnostics(cases: list[BenchmarkCase]) -> list[dict[str, object]]:
    results = []
    for case in cases:
        if "duplicate_identity" not in case.review_tags:
            continue
        job, _, _, _ = _current_inputs(case)
        alias = job.model_copy(update={"official_url": job.official_url + "?source=alias"})
        resolved = JobDeduplicator().resolve([job, alias])
        results.append({"case_id": case.case_id, "duplicate_count": resolved.duplicate_count, "canonical_count": len(resolved.jobs)})
    return results


def _comparison_grade(prediction: CurrentPrediction) -> str:
    if prediction.current_label == "provisional":
        return prediction.legacy_substantive_grade or "weak"
    return {
        "strong": "excellent",
        "good": "good",
        "stretch": "weak",
        "dont_match": "dont_match",
    }[prediction.current_label]


def select_review_cases(
    cases: list[BenchmarkCase], predictions: dict[str, CurrentPrediction]
) -> list[str]:
    mandatory: list[BenchmarkCase] = []
    disagreement_representatives: dict[str, BenchmarkCase] = {}
    for case in cases:
        prediction = predictions[case.case_id]
        disagreement = (
            _comparison_grade(prediction) != case.proposed_grade
            or prediction.current_eligibility != case.expected_eligibility
        )
        if disagreement:
            disagreement_representatives.setdefault(
                f"{_comparison_grade(prediction)}->{case.proposed_grade}:{prediction.current_eligibility}->{case.expected_eligibility}", case
            )
        if (
            case.proposed_grade == "excellent"
            or case.proposal_confidence == "low"
            or case.expected_eligibility == "unknown"
            or case.expected_eligibility == "ineligible"
            or "keyword_trap" in case.review_tags
            or "sector_trap" in case.review_tags
            or "misleading_title" in case.review_tags
        ):
            mandatory.append(case)
    selected = {case.case_id for case in mandatory}
    for case in sorted(disagreement_representatives.values(), key=lambda item: item.case_id):
        if len(selected) >= 45:
            break
        selected.add(case.case_id)
    remaining = [case for case in cases if case.case_id not in selected]
    def review_sort_key(case: BenchmarkCase) -> tuple[str, ...]:
        return (
            case.split,
            case.proposed_grade,
            case.preferences.role_families[0]
            if case.preferences.role_families
            else "unknown",
            case.preferences.target_levels[0]
            if case.preferences.target_levels
            else "unknown",
            case.evidence_assessment.quality,
            case.case_id,
        )

    for case in sorted(remaining, key=review_sort_key):
        if len(selected) >= 40:
            break
        selected.add(case.case_id)
    return [
        case.case_id
        for case in sorted(cases, key=lambda item: item.case_id)
        if case.case_id in selected
    ]


def select_review_appendix(
    cases: list[BenchmarkCase], predictions: dict[str, CurrentPrediction], primary_ids: list[str]
) -> list[str]:
    primary = set(primary_ids)
    return [
        case.case_id
        for case in sorted(cases, key=lambda item: item.case_id)
        if case.case_id not in primary
        and (_comparison_grade(predictions[case.case_id]) != case.proposed_grade
             or predictions[case.case_id].current_eligibility != case.expected_eligibility)
    ]


def _list(items: Iterable[object]) -> str:
    return "<ul>" + "".join(f"<li>{html.escape(str(item))}</li>" for item in items) + "</ul>"


def _review_html(cases: list[BenchmarkCase], predictions: dict[str, CurrentPrediction]) -> str:
    selected_ids = select_review_cases(cases, predictions)
    appendix_ids = select_review_appendix(cases, predictions, selected_ids)
    by_id = {case.case_id: case for case in cases}
    cards: list[str] = []
    for case_id in selected_ids:
        case = by_id[case_id]
        prediction = predictions[case_id]
        disagreement = (
            f"Current comparison {_comparison_grade(prediction)} / {prediction.current_eligibility}; "
            f"proposal {case.proposed_grade} / {case.expected_eligibility}."
        )
        cards.append(
            "<article class='case'>"
            f"<h2>{html.escape(case.case_id)} <small>{html.escape(case.split)}</small></h2>"
            f"<p><b>Scenario:</b> {html.escape(case.scenario_id)} · {html.escape(case.scenario_category)}</p>"
            f"<p><b>Profile:</b> {html.escape(case.profile.summary)}</p>"
            f"<p><b>Posting:</b> {html.escape(case.posting.title)} · {html.escape(case.posting.company)} · "
            f"{html.escape(case.posting.location)} · {html.escape(case.preferences.target_levels[0])}</p>"
            f"<p>{html.escape(case.posting.description)}</p>"
            f"<h3>Critical requirements</h3>{_list(item.text for item in case.critical_requirements)}"
            f"<p><b>Proposed eligibility:</b> {html.escape(case.expected_eligibility)}; "
            f"{_list(reason.statement for reason in case.proposed_eligibility_reasons)}</p>"
            f"<p><b>Proposed grade:</b> {html.escape(case.proposed_grade)} · "
            f"<b>Provisional:</b> {case.proposed_provisional}</p>"
            f"<p><b>Matching evidence:</b> {_list(item.statement for item in case.important_evidence)}</p>"
            f"<p><b>Important gaps:</b> {_list(item.statement for item in case.important_gaps)}</p>"
            f"<p><b>Rationale:</b> {html.escape(case.rationale)}</p>"
            f"<p><b>Confidence:</b> {html.escape(case.proposal_confidence)} · "
            f"<b>Review tags:</b> {html.escape(', '.join(case.review_tags))}</p>"
            f"<p><b>Current production:</b> score={prediction.score!r}, label={html.escape(prediction.current_label)}; "
            f"{html.escape(disagreement)}</p>"
            "<label>Reviewer decision <input value=''></label>"
            "<label>Reviewer notes <textarea></textarea></label>"
            "</article>"
        )
    appendix = "<h1>Complete disagreement appendix</h1>" + "".join(
        f"<p>{html.escape(case_id)}: current {html.escape(_comparison_grade(predictions[case_id]))} / "
        f"{html.escape(predictions[case_id].current_eligibility)} versus proposed "
        f"{html.escape(next(case.proposed_grade for case in cases if case.case_id == case_id))}</p>"
        for case_id in appendix_ids
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>Jobs benchmark review</title>"
        "<style>body{font-family:system-ui;max-width:1100px;margin:auto}.case{border:1px solid #aaa;"
        "padding:1rem;margin:1rem 0}small{font-weight:normal}label{display:block;margin:.5rem 0}"
        "textarea{display:block;width:100%;height:3rem}</style></head><body>"
        f"<h1>Jobs benchmark human review</h1><p><b>{STAGE_A_NOTICE}</b></p>"
        f"<p>Review queue: {len(selected_ids)} proposed cases. Corrections are blank and no labels are approved.</p>"
        + f"<h2>Primary queue ({len(selected_ids)} cases)</h2>"
        + "".join(cards)
        + appendix
        + "</body></html>"
    )


def generate_review_artifact(output: Path) -> list[str]:
    cases = load_development_cases()
    predictions = _prediction_map(cases)
    selected = select_review_cases(cases, predictions)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_review_html(cases, predictions), encoding="utf-8")
    _write_review_csv(output.with_suffix(".csv"), cases, predictions, selected)
    return selected


def _write_review_csv(path: Path, cases: list[BenchmarkCase], predictions: dict[str, CurrentPrediction], selected: list[str]) -> None:
    import csv

    appendix = select_review_appendix(cases, predictions, selected)
    by_id = {case.case_id: case for case in cases}
    fields = ["case_id", "split", "scenario", "profile_summary", "title", "company", "location", "proposed_grade", "proposed_eligibility", "proposed_provisional", "current_score", "current_label", "rationale", "reviewer_decision", "reviewer_grade", "reviewer_eligibility", "reviewer_provisional", "reviewer_notes"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for case_id in [*selected, *appendix]:
            case = by_id[case_id]
            prediction = predictions[case_id]
            writer.writerow({"case_id": case.case_id, "split": case.split, "scenario": case.scenario_id, "profile_summary": case.profile.summary, "title": case.posting.title, "company": case.posting.company, "location": case.posting.location, "proposed_grade": case.proposed_grade, "proposed_eligibility": case.expected_eligibility, "proposed_provisional": case.proposed_provisional, "current_score": prediction.score, "current_label": prediction.current_label, "rationale": case.rationale, "reviewer_decision": "", "reviewer_grade": "", "reviewer_eligibility": "", "reviewer_provisional": "", "reviewer_notes": ""})


def _baseline_payload(
    cases: list[BenchmarkCase], predictions: dict[str, CurrentPrediction]
) -> dict[str, object]:
    metric_cases = [MetricCase.from_benchmark(case) for case in cases]
    pairs = []
    seen_pairs: set[tuple[str, str]] = set()
    from tests.job_discovery.benchmark.metrics import RankingPair
    for case in cases:
        for annotation in case.comparable_pair_annotations:
            preferred, other = (case.case_id, annotation.other_case_id) if annotation.relationship == "preferred_to_other" else (annotation.other_case_id, case.case_id)
            key = tuple(sorted((preferred, other)))
            if key not in seen_pairs:
                seen_pairs.add(key)
                pairs.append(RankingPair(scenario_id=case.scenario_id, preferred_case_id=preferred, other_case_id=other))
    metrics_by_split = {}
    for split in ("calibration", "validation"):
        split_cases = [case for case in cases if case.split == split]
        split_ids = {case.case_id for case in split_cases}
        split_metric_cases = [item for item in metric_cases if item.case_id in split_ids]
        split_pairs = [pair for pair in pairs if pair.preferred_case_id in split_ids]
        metrics_by_split[split] = calculate_quality_metrics(
            split_metric_cases, predictions, split_pairs
        )
    prediction_rows = [
        {
            "case_id": case.case_id,
            "split": case.split,
            "proposed_grade": case.proposed_grade,
            "proposed_eligibility": case.expected_eligibility,
            "current_score": predictions[case.case_id].score,
            "current_label": predictions[case.case_id].current_label,
            "current_comparison_grade": _comparison_grade(predictions[case.case_id]),
            "current_eligibility": predictions[case.case_id].current_eligibility,
            "provisional": predictions[case.case_id].provisional,
            "score_components": predictions[case.case_id].score_components,
            "current_explanation_reasons": predictions[case.case_id].current_explanation_reasons,
            "current_explanation_gaps": predictions[case.case_id].current_explanation_gaps,
            "current_explanation_traceable": predictions[case.case_id].current_explanation_traceable,
            "failure_categories": predictions[case.case_id].failure_categories,
        }
        for case in sorted(cases, key=lambda item: item.case_id)
    ]
    return {
        "status": "preliminary",
        "labels": "proposed labels; not approved ground truth",
        "locked_split": "not evaluated",
        "review_gate": "user review required before Stage B",
        "splits": sorted({case.split for case in cases}),
        "case_count": len(cases),
        "predictions": prediction_rows,
        "metrics": calculate_quality_metrics(metric_cases, predictions, pairs),
        "metrics_by_split": metrics_by_split,
        "proposed_reference_structural_validity": proposed_reference_structural_validity(cases),
        "current_explanation_heuristic_traceability": current_explanation_heuristic_traceability(predictions),
        "adapter_failures": 0,
        "ranking_mode": "scorer_only_diagnostic_using_production_recommendation_sort_key",
        "components_invoked": ["normalize_job_record", "RequirementExtractor", "role classification", "EligibilityEvaluator", "ScoringPolicy", "DeterministicExplanationBuilder"],
        "provider_order_diagnostics": _provider_order_diagnostics(cases),
        "duplicate_identity_diagnostics": _duplicate_identity_diagnostics(cases),
    }


def _baseline_html(payload: dict[str, object]) -> str:
    rows = payload["predictions"]
    table = "".join(
        "<tr>"
        + "".join(
            f"<td>{html.escape(str(row[key]))}</td>"
            for key in (
                "case_id",
                "split",
                "proposed_grade",
                "current_score",
                "current_label",
                "current_comparison_grade",
        "current_eligibility",
            )
        )
        + "</tr>"
        for row in rows
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>Current jobs baseline</title>"
        "<style>body{font-family:system-ui;max-width:1200px;margin:auto}table{border-collapse:collapse}"
        "td,th{border:1px solid #aaa;padding:.3rem}</style></head><body>"
        f"<h1>Preliminary current-production comparison</h1><p><b>{STAGE_A_NOTICE}</b></p>"
        "<table><thead><tr><th>Case</th><th>Split</th><th>Proposed grade</th><th>Score</th>"
        "<th>Current label</th><th>Comparison grade</th><th>Current eligibility</th></tr></thead>"
        f"<tbody>{table}</tbody></table></body></html>"
    )


def generate_current_baseline(output: Path, splits: list[str]) -> None:
    if set(splits) - {"calibration", "validation"}:
        raise ValueError(
            "Locked split is not accepted by the current preliminary baseline; only calibration and validation are allowed"
        )
    cases = [case for case in load_development_cases() if case.split in splits]
    predictions = _prediction_map(cases)
    payload = _baseline_payload(cases, predictions)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_baseline_html(payload), encoding="utf-8")
    output.with_suffix(".json").write_text(canonical_json(payload) + "\n", encoding="utf-8")


def _pilot_payload(
    cases: list[BenchmarkCase],
    predictions: dict[str, CurrentPrediction],
    ranking_group: str,
) -> dict[str, object]:
    from tests.job_discovery.benchmark.metrics import (
        MetricCase,
        RankingPair,
        pairwise_ranking_accuracy,
    )

    visible_ids = {case.case_id for case in cases if case.normal_feed_visible}
    pairs: list[RankingPair] = []
    seen_pairs: set[tuple[str, str]] = set()
    for case in cases:
        if not case.normal_feed_visible:
            continue
        for annotation in case.comparable_pair_annotations:
            if annotation.other_case_id not in visible_ids:
                continue
            preferred, other = (
                (case.case_id, annotation.other_case_id)
                if annotation.relationship == "preferred_to_other"
                else (annotation.other_case_id, case.case_id)
            )
            key = tuple(sorted((preferred, other)))
            if key not in seen_pairs:
                seen_pairs.add(key)
                pairs.append(
                    RankingPair(
                        scenario_id=case.scenario_id,
                        preferred_case_id=preferred,
                        other_case_id=other,
                    )
                )
    visible_metric_cases = [
        MetricCase.from_benchmark(case)
        for case in cases
        if case.normal_feed_visible
    ]
    is_calibration = ranking_group.startswith("calibration-")
    is_approved = is_calibration or ranking_group.startswith("validation-")
    return {
        "status": "approved" if is_approved else "proposed",
        "scope": ranking_group,
        "not_complete_benchmark": True,
        "approval_status": "approved" if is_approved else "unapproved",
        "labels": "approved calibration ground truth" if is_calibration else "approved validation ground truth",
        "locked_split": "not touched or evaluated",
        "review_gate": "user review required before Stage B",
        "case_count": len(cases),
        "components_invoked": [
            "normalize_job_record",
            "RequirementExtractor",
            "role classification",
            "ProfileCapabilityIndexBuilder",
            "EligibilityEvaluator",
            "ScoringPolicy",
            "DeterministicExplanationBuilder",
            "recommendation_sort_key",
        ],
        "ranking_mode": "scorer_only_diagnostic_using_production_recommendation_sort_key",
        "normal_feed_pair_count": len(pairs),
        "metrics": calculate_quality_metrics(
            [MetricCase.from_benchmark(case) for case in cases],
            predictions,
            pairs,
        ),
        "normal_feed_visibility_accuracy": sum(
            case.normal_feed_visible
            == (
                predictions[case.case_id].current_eligibility != "ineligible"
                and predictions[case.case_id].current_label != "dont_match"
            )
            for case in cases
        ) / len(cases),
        "pairwise_ranking_diagnostic": pairwise_ranking_accuracy(
            visible_metric_cases, predictions, pairs
        ),
        "proposed_reference_structural_validity": proposed_reference_structural_validity(cases),
        "current_explanation_heuristic_traceability": current_explanation_heuristic_traceability(predictions),
        "predictions": [
            {
                "case_id": case.case_id,
                "split": case.split,
                "title": case.posting.title,
                "candidate_target_levels": case.preferences.target_levels,
                "posting_level": case.posting.posting_level,
                "posting_sponsorship_available": case.posting.posting_sponsorship_available,
                "normal_feed_visible": case.normal_feed_visible,
                "current_rank": predictions[case.case_id].rank,
                "current_predicted_grade": _comparison_grade(predictions[case.case_id]),
                "typed_sort_key": list(predictions[case.case_id].ranking_key),
                "posting_facts": [fact.model_dump() for fact in case.posting.posting_facts],
                "critical_gap_fact_ids": critical_gap_fact_ids(case),
                "proposed_grade": case.proposed_grade,
                "proposed_eligibility": case.expected_eligibility,
                "current_score": predictions[case.case_id].score,
                "current_label": predictions[case.case_id].current_label,
                "current_comparison_grade": _comparison_grade(predictions[case.case_id]),
                "current_eligibility": predictions[case.case_id].current_eligibility,
                "provisional": predictions[case.case_id].provisional,
                "score_components": predictions[case.case_id].score_components,
                "current_explanation_reasons": predictions[case.case_id].current_explanation_reasons,
                "current_explanation_gaps": predictions[case.case_id].current_explanation_gaps,
                "current_explanation_traceable": predictions[case.case_id].current_explanation_traceable,
                "failure_categories": predictions[case.case_id].failure_categories,
            }
            for case in cases
        ],
    }


def _pilot_fact_display(case: BenchmarkCase, kind: str | None = None) -> list[str]:
    return [
        f"{fact.fact_id} [{fact.kind}]: {fact.statement}"
        for fact in case.posting.posting_facts
        if kind is None or fact.kind == kind
    ]


def _pilot_profile_fact_display(case: BenchmarkCase) -> list[str]:
    return [
        f"profile:{case.profile.profile_ref}:experience-years: {case.profile.experience_years:g} years",
        f"profile:{case.profile.profile_ref}:education: {case.profile.education_summary}",
        f"profile:{case.profile.profile_ref}:professional-license-status: {case.profile.professional_license_status}",
        f"profile:{case.profile.profile_ref}:clearance-status: {case.profile.clearance_status}",
    ]


def _pilot_requirement_display(items: Iterable[object]) -> list[str]:
    return [
        f"{item.requirement_id if hasattr(item, 'requirement_id') else item.qualification_id}: "
        f"{item.text} (refs: {', '.join(item.evidence_references) or 'none'})"
        for item in items
    ]


def _pilot_gap_display(case: BenchmarkCase) -> list[str]:
    return [
        f"{item.code}: {item.statement} (refs: {', '.join(item.evidence_references)})"
        for item in case.important_gaps
    ]


def _pilot_html(cases: list[BenchmarkCase], predictions: dict[str, CurrentPrediction], ranking_group: str) -> str:
    is_calibration = ranking_group.startswith("calibration-")
    notice = CALIBRATION_APPROVED_NOTICE if is_calibration else VALIDATION_APPROVED_NOTICE
    cards: list[str] = []
    for case in cases:
        prediction = predictions[case.case_id]
        pairs = "<ul>" + "".join(
            f"<li>{html.escape(pair.other_case_id)} — {html.escape(pair.relationship)}: {html.escape(pair.rationale)}</li>"
            for pair in case.comparable_pair_annotations
        ) + "</ul>"
        cards.append(
            "<article class='case'>"
            f"<h2>{html.escape(case.case_id)} — {html.escape(case.posting.title)}</h2>"
            f"<p><b>Split/group:</b> {html.escape(case.split)} / {html.escape(case.ranking_group or '')} · "
            f"<b>Company:</b> {html.escape(case.posting.company)} · <b>Location:</b> {html.escape(case.posting.location)} · "
            f"<b>Candidate target levels:</b> {html.escape(', '.join(case.preferences.target_levels))} · "
            f"<b>Posting level:</b> {html.escape(case.posting.posting_level)} · "
            f"<b>Posting sponsorship available:</b> {case.posting.posting_sponsorship_available} · "
            f"<b>Normal-feed visible:</b> {case.normal_feed_visible} · "
            f"<b>Current numeric rank:</b> {prediction.rank}</p>"
            f"<p><b>Profile:</b> {html.escape(case.profile.summary)}; {case.profile.experience_years:g} years; "
            f"{html.escape(case.profile.current_location)}; authorized in {html.escape(', '.join(case.profile.authorized_work_locations))}; "
            f"sponsorship required: {case.profile.requires_sponsorship}</p>"
            f"<h3>Profile-level facts</h3>{_list(_pilot_profile_fact_display(case))}"
            f"<p><b>Posting summary:</b> {html.escape(case.posting.description)}</p>"
            f"<h3>Posting facts</h3>{_list(_pilot_fact_display(case))}"
            f"<h3>Critical requirements</h3>{_list(_pilot_requirement_display(case.critical_requirements))}"
            f"<h3>Required qualifications</h3>{_list(_pilot_requirement_display(case.required_qualifications))}"
            f"<h3>Preferred qualifications</h3>{_list(_pilot_requirement_display(case.preferred_qualifications))}"
            f"<p><b>Proposed eligibility:</b> {html.escape(case.expected_eligibility)}; {_list(reason.statement for reason in case.proposed_eligibility_reasons)}</p>"
            f"<p><b>Proposed grade:</b> {html.escape(case.proposed_grade)} · <b>Provisional:</b> {case.proposed_provisional} ({html.escape(', '.join(case.provisional_reason_codes) or 'none')})</p>"
            f"<p><b>Proposed evidence references:</b> {_list(f'{item.reference}: {item.statement}' for item in case.important_evidence)}</p>"
            f"<p><b>Critical-gap authority:</b> {_list(critical_gap_fact_ids(case))}</p>"
            f"<p><b>Proposed gap references:</b> {_list(_pilot_gap_display(case))}</p>"
            f"<p><b>Rationale:</b> {html.escape(case.rationale)}</p>"
            f"<p><b>Current production diagnostic:</b> score={prediction.score!r}; label={html.escape(prediction.current_label)}; "
            f"components={html.escape(json.dumps(prediction.score_components, sort_keys=True))}; "
            f"explanation traceable={prediction.current_explanation_traceable}</p>"
            f"<h3>Pairwise comparison annotations</h3>{pairs}"
            "<div class='review'><label>Reviewer decision <input name='reviewer_decision' value=''></label>"
            "<label>Reviewer grade <input name='reviewer_grade' value=''></label>"
            "<label>Reviewer eligibility <input name='reviewer_eligibility' value=''></label>"
            "<label>Reviewer provisional <input name='reviewer_provisional' value=''></label>"
            "<label>Reviewer notes <textarea name='reviewer_notes'></textarea></label></div>"
            "</article>"
        )
    return (
        f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(ranking_group)} pilot review</title>"
        "<style>body{font-family:system-ui;max-width:1180px;margin:auto}.case{border:1px solid #aaa;padding:1rem;margin:1rem 0}"
        "label{display:block;margin:.4rem 0}textarea{display:block;width:100%;height:3rem}</style></head><body>"
        f"<h1>{html.escape(ranking_group)} pilot review</h1>"
        f"<p><b>{html.escape(notice)}</b></p><p>This artifact contains exactly ten cases from {html.escape(ranking_group)}. It is not the complete benchmark and must not be used as a hiring-probability claim.</p>"
        f"<h2>Ten-case pilot queue</h2>{''.join(cards)}</body></html>"
    )


def generate_pilot_artifacts(html_output: Path, csv_output: Path, json_output: Path, ranking_group: str = "calibration-group-01") -> None:
    if ranking_group.startswith("calibration-"):
        cases = [case for case in load_approved_calibration() if case.ranking_group == ranking_group]
    else:
        cases = [case for case in load_approved_validation() if case.ranking_group == ranking_group]
    if len(cases) != 10:
        raise ValueError(f"{ranking_group} must contain exactly ten approved cases")
    predictions = _prediction_map(cases)
    payload = _pilot_payload(cases, predictions, ranking_group)
    html_output.parent.mkdir(parents=True, exist_ok=True)
    csv_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.parent.mkdir(parents=True, exist_ok=True)
    html_output.write_text(_pilot_html(cases, predictions, ranking_group), encoding="utf-8")
    # Both development groups are now frozen; the historical CSV reviewer fields remain blank.
    if not ranking_group.startswith("calibration-"):
        ranking_group = f"calibration-{ranking_group}"
    fields = [
        "case_id", "split", "ranking_group", "scenario_category", "profile_ref", "profile_summary", "experience_years", "current_location", "target_role_families", "candidate_target_levels", "posting_level", "posting_sponsorship_available", "authorized_work_locations", "requires_sponsorship", "profile_level_facts", "title", "company", "location", "work_arrangement", "normal_feed_visible", "current_rank", "posting_facts", "critical_gap_fact_ids", "critical_requirements", "required_qualifications", "preferred_qualifications", "eligibility", "eligibility_reasons", "grade", "provisional", "provisional_reason_codes", "evidence", "gaps", "rationale", "proposal_confidence", "apply_worthy", "human_ranking_tier", "pairwise_rationale_summary", "current_score", "current_label", "score_components", "current_eligibility", "current_explanation_heuristic_traceability", "reviewer_decision", "reviewer_grade", "reviewer_eligibility", "reviewer_provisional", "reviewer_notes",
        "approval_status",
    ]
    with csv_output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for case in cases:
            prediction = predictions[case.case_id]
            writer.writerow({
                "case_id": case.case_id, "split": case.split, "ranking_group": case.ranking_group, "scenario_category": case.scenario_category, "profile_ref": case.profile.profile_ref, "profile_summary": case.profile.summary, "experience_years": case.profile.experience_years, "current_location": case.profile.current_location, "target_role_families": "; ".join(case.preferences.role_families), "candidate_target_levels": "; ".join(case.preferences.target_levels), "posting_level": case.posting.posting_level, "posting_sponsorship_available": case.posting.posting_sponsorship_available, "authorized_work_locations": "; ".join(case.profile.authorized_work_locations), "requires_sponsorship": case.profile.requires_sponsorship, "profile_level_facts": " | ".join(_pilot_profile_fact_display(case)), "title": case.posting.title, "company": case.posting.company, "location": case.posting.location, "work_arrangement": case.posting.work_arrangement, "normal_feed_visible": case.normal_feed_visible, "current_rank": prediction.rank, "posting_facts": " | ".join(_pilot_fact_display(case)), "critical_gap_fact_ids": "; ".join(critical_gap_fact_ids(case)), "critical_requirements": " | ".join(_pilot_requirement_display(case.critical_requirements)), "required_qualifications": " | ".join(_pilot_requirement_display(case.required_qualifications)), "preferred_qualifications": " | ".join(_pilot_requirement_display(case.preferred_qualifications)), "eligibility": case.expected_eligibility, "eligibility_reasons": " | ".join(reason.statement for reason in case.proposed_eligibility_reasons), "grade": case.proposed_grade, "provisional": case.proposed_provisional, "provisional_reason_codes": "; ".join(case.provisional_reason_codes), "evidence": " | ".join(f"{item.reference}: {item.statement}" for item in case.important_evidence), "gaps": " | ".join(_pilot_gap_display(case)), "rationale": case.rationale, "proposal_confidence": case.proposal_confidence, "apply_worthy": case.apply_worthy, "human_ranking_tier": case.human_ranking_tier, "pairwise_rationale_summary": " | ".join(f"{pair.other_case_id}: {pair.rationale}" for pair in case.comparable_pair_annotations), "current_score": prediction.score, "current_label": prediction.current_label, "score_components": json.dumps(prediction.score_components, sort_keys=True), "current_eligibility": prediction.current_eligibility, "current_explanation_heuristic_traceability": prediction.current_explanation_traceable, "reviewer_decision": "", "reviewer_grade": "", "reviewer_eligibility": "", "reviewer_provisional": "", "reviewer_notes": "", "approval_status": "approved" if ranking_group.startswith("calibration-") else "unapproved",
            })
    json_output.write_text(canonical_json(payload) + "\n", encoding="utf-8")


def generate_validation_review_index(output: Path) -> None:
    """Write a concise index for the frozen validation groups."""

    output.parent.mkdir(parents=True, exist_ok=True)
    links = "".join(
        f"<li><a href='validation-group-{group}-review.html'>Validation group {group}</a> · "
        f"<a href='validation-group-{group}-review.csv'>CSV</a> · "
        f"<a href='validation-group-{group}-baseline.json'>current baseline JSON</a></li>"
        for group in ("01", "02")
    )
    output.write_text(
        "<!doctype html><html><head><meta charset='utf-8'><title>Validation review index</title>"
        "<style>body{font-family:system-ui;max-width:900px;margin:auto}li{margin:.7rem 0}</style>"
        "</head><body><h1>Validation human-review candidate</h1>"
        f"<p><b>{html.escape(VALIDATION_APPROVED_NOTICE)}</b></p>"
        "<p>Twenty validation cases are approved and frozen as development fit ground truth. No locked cases or locked metrics are included.</p>"
        f"<ul>{links}</ul><p>Historical reviewer-input fields remain blank; split approval is recorded in approval.json.</p>"
        "</body></html>",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("review", "current-baseline", "pilot"), required=True)
    parser.add_argument("--splits", nargs="+", default=["calibration", "validation"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--csv-output", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--group", default="calibration-group-01")
    args = parser.parse_args()
    if args.mode == "review":
        generate_review_artifact(args.output)
    elif args.mode == "current-baseline":
        generate_current_baseline(args.output, args.splits)
    else:
        if args.csv_output is None or args.json_output is None:
            parser.error("pilot mode requires --csv-output and --json-output")
        generate_pilot_artifacts(args.output, args.csv_output, args.json_output, args.group)


if __name__ == "__main__":
    main()
