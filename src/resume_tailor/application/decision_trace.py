from __future__ import annotations

from hashlib import sha256

from pydantic import BaseModel, ConfigDict, Field

from resume_tailor.application.generated_artifact import content_fingerprint
from resume_tailor.domain.generated_artifact import GeneratedResumeArtifact
from resume_tailor.domain.models import JobPosting, MasterProfile, TailoringPlan, TemplateConstraints
from resume_tailor.domain.requirement_ranking import EvidenceRelationship
from resume_tailor.domain.resume_composition import (
    CompositionCandidateDiagnostic,
    ExperiencePackageSelectionDiagnostic,
    PageFitPortfolioDiagnostic,
)


class EvidenceCandidateTrace(BaseModel):
    """Safe retrieval metadata that deliberately excludes reviewed source text."""

    evidence_id: str
    entry_id: str
    entry_kind: str
    rank: int = Field(ge=1)
    relationship: EvidenceRelationship
    contextual_relevance: float = Field(ge=0)
    intrinsic_evidence_strength: float = Field(ge=0)
    complementary_value: float = Field(ge=0)
    total_score: float
    admission_status: str
    requirement_ids: list[str] = Field(default_factory=list)


class ResumeCompositionConfigurationTrace(BaseModel):
    constraints: TemplateConstraints
    template_identity: str
    composition_contract_version: str
    writing_policy_version: str
    writing_contract_version: str
    feature_flags: dict[str, bool]
    provider: str
    model: str
    beam_width: int = Field(gt=0)
    maximum_estimated_page_evaluations: int = Field(gt=0)
    maximum_exact_finalist_evaluations: int = Field(gt=0)
    maximum_expansion_operations: int = Field(gt=0)
    maximum_selected_bullets: int = Field(gt=0)
    maximum_selected_entries: int = Field(gt=0)


class ResumeDecisionTrace(BaseModel):
    """Sanitized snapshot of already-computed production resume decisions."""

    model_config = ConfigDict(frozen=True)

    trace_version: str = "resume-production-decision-trace-v1"
    profile_source: str
    profile_id: str
    profile_version: int = Field(ge=1)
    profile_fingerprint: str
    posting_source: str
    posting_id: str
    posting_fingerprint: str
    plan_posting_fingerprint: str
    artifact_posting_fingerprint: str
    normalized_title: str
    normalized_company: str | None = None
    normalized_description_length: int = Field(ge=1)
    normalized_description_digest: str
    role_family: str
    role_classification_source: str | None = None
    requirement_ids: list[str] = Field(default_factory=list)
    normalized_requirement_terms: list[str] = Field(default_factory=list)
    relationship_counts: dict[str, int] = Field(default_factory=dict)
    retrieval_candidates: list[EvidenceCandidateTrace] = Field(default_factory=list)
    composition_candidates: list[CompositionCandidateDiagnostic] = Field(default_factory=list)
    experience_package_candidates: list[ExperiencePackageSelectionDiagnostic] = Field(
        default_factory=list
    )
    project_candidate_ids: list[str] = Field(default_factory=list)
    skill_candidate_ids: list[str] = Field(default_factory=list)
    configuration: ResumeCompositionConfigurationTrace
    page_fit_finalists: list[PageFitPortfolioDiagnostic] = Field(default_factory=list)
    selected_experience_ids: list[str] = Field(default_factory=list)
    selected_project_ids: list[str] = Field(default_factory=list)
    selected_bullet_ids: list[str] = Field(default_factory=list)
    selected_skill_category_ids: list[str] = Field(default_factory=list)
    bullet_counts: dict[str, int] = Field(default_factory=dict)
    provider_call_count: int = Field(ge=0)
    writer_status: str


def build_resume_decision_trace(
    artifact: GeneratedResumeArtifact,
    profile: MasterProfile,
    posting: JobPosting,
    plan: TailoringPlan,
    *,
    profile_source: str,
    posting_source: str,
) -> ResumeDecisionTrace:
    """Return safe decision metadata without recalculating ranking or page fit."""

    if plan.posting != posting or artifact.final_validated_plan != plan:
        raise ValueError("Resume decision trace inputs do not describe one accepted opportunity")
    profile_fingerprint = content_fingerprint(profile)
    posting_fingerprint = content_fingerprint(posting)
    if artifact.fingerprint_inputs.reviewed_profile_fingerprint != profile_fingerprint:
        raise ValueError("Resume decision trace profile does not match the generated artifact")
    if artifact.fingerprint_inputs.normalized_posting_fingerprint != posting_fingerprint:
        raise ValueError("Resume decision trace posting does not match the generated artifact")
    composition = artifact.composition_diagnostic
    if composition is None:
        raise ValueError("Resume decision trace requires composition diagnostics")

    hybrid = artifact.writing_diagnostic
    retrieval = hybrid.retrieval if hybrid is not None else None
    retrieved = [*(retrieval.admitted if retrieval else []), *(retrieval.rejected if retrieval else [])]
    relationship_counts = {
        relationship.value: sum(item.relationship is relationship for item in retrieved)
        for relationship in EvidenceRelationship
    }
    composition_candidates: dict[str, CompositionCandidateDiagnostic] = {}
    for candidate in [
        *composition.selected_candidates,
        *composition.excluded_high_ranking_candidates,
        *composition.unused_admissible_candidates,
        *composition.candidates_excluded_by_search_bounds,
        *composition.candidates_excluded_by_thresholds,
    ]:
        composition_candidates.setdefault(candidate.candidate_id, candidate)
    role_diagnostic = plan.report.role.diagnostic
    role_source = getattr(role_diagnostic, "source", None)
    return ResumeDecisionTrace(
        profile_source=profile_source,
        profile_id=profile.id,
        profile_version=profile.version,
        profile_fingerprint=profile_fingerprint,
        posting_source=posting_source,
        posting_id=posting.id,
        posting_fingerprint=posting_fingerprint,
        plan_posting_fingerprint=content_fingerprint(plan.posting),
        artifact_posting_fingerprint=(
            artifact.fingerprint_inputs.normalized_posting_fingerprint
        ),
        normalized_title=posting.title,
        normalized_company=posting.company_name,
        normalized_description_length=len(posting.description),
        normalized_description_digest=sha256(posting.description.encode("utf-8")).hexdigest(),
        role_family=plan.report.role.role_family,
        role_classification_source=(
            getattr(role_source, "value", str(role_source)) if role_source is not None else None
        ),
        requirement_ids=[item.id for item in composition.posting_requirements],
        normalized_requirement_terms=[
            item.normalized_text for item in composition.posting_requirements
        ],
        relationship_counts=relationship_counts,
        retrieval_candidates=[
            EvidenceCandidateTrace(
                evidence_id=item.evidence_id,
                entry_id=item.entry_id,
                entry_kind=item.entry_kind,
                rank=item.rank,
                relationship=item.relationship,
                contextual_relevance=item.contextual_relevance,
                intrinsic_evidence_strength=item.intrinsic_evidence_strength,
                complementary_value=item.complementary_value,
                total_score=item.total_score,
                admission_status=item.admission_status.value,
                requirement_ids=[
                    *item.direct_requirement_ids,
                    *item.adjacent_requirement_ids,
                    *item.complementary_requirement_ids,
                    *item.incidental_requirement_ids,
                ],
            )
            for item in retrieved
        ],
        composition_candidates=list(composition_candidates.values()),
        experience_package_candidates=composition.experience_package_selections,
        project_candidate_ids=sorted(
            {
                item.candidate_id
                for item in composition_candidates.values()
                if item.kind.value.startswith("project_")
            }
        ),
        skill_candidate_ids=sorted(
            {
                item.candidate_id
                for item in composition_candidates.values()
                if item.kind.value == "skill_category"
            }
        ),
        configuration=ResumeCompositionConfigurationTrace(
            constraints=plan.constraints,
            template_identity=artifact.fingerprint_inputs.template_identity,
            composition_contract_version=(
                artifact.fingerprint_inputs.composition_contract_version
            ),
            writing_policy_version=artifact.fingerprint_inputs.writing_policy_version,
            writing_contract_version=artifact.fingerprint_inputs.writing_contract_version,
            feature_flags=artifact.fingerprint_inputs.feature_flags,
            provider=artifact.fingerprint_inputs.provider,
            model=artifact.fingerprint_inputs.model,
            beam_width=composition.beam_width,
            maximum_estimated_page_evaluations=(
                composition.maximum_estimated_page_evaluations
            ),
            maximum_exact_finalist_evaluations=(
                composition.maximum_exact_finalist_evaluations
            ),
            maximum_expansion_operations=composition.maximum_expansion_operations,
            maximum_selected_bullets=composition.maximum_selected_bullets,
            maximum_selected_entries=composition.maximum_selected_entries,
        ),
        page_fit_finalists=composition.page_fit_finalists,
        selected_experience_ids=composition.selected_experience_ids,
        selected_project_ids=composition.selected_project_ids,
        selected_bullet_ids=composition.selected_bullet_ids,
        selected_skill_category_ids=composition.selected_skill_category_ids,
        bullet_counts=composition.bullet_counts,
        provider_call_count=artifact.provider_diagnostic.call_count,
        writer_status=artifact.provider_diagnostic.status,
    )


__all__ = [
    "EvidenceCandidateTrace",
    "ResumeCompositionConfigurationTrace",
    "ResumeDecisionTrace",
    "build_resume_decision_trace",
]
