from __future__ import annotations

from hashlib import sha256

from resume_tailor.application.requirement_ranking import (
    assess_evidence_relationship,
    extract_posting_requirements,
)
from resume_tailor.application.resume_features import (
    ReviewedTextFeatures,
    extract_reviewed_text_features,
    match_reviewed_features,
)
from resume_tailor.domain.hybrid_resume import (
    EvidenceRetrievalResult,
    RetrievalAdmissionStatus,
    RetrievedEvidence,
)
from resume_tailor.domain.models import EvidenceItem, JobPosting, MasterProfile
from resume_tailor.domain.requirement_ranking import EvidenceRelationship


class InProcessResumeEvidenceRetriever:
    """Retrieve complete-profile reviewed evidence behind a replaceable typed seam."""

    def retrieve(
        self,
        profile: MasterProfile,
        posting: JobPosting,
    ) -> EvidenceRetrievalResult:
        posting_features = extract_reviewed_text_features(f"{posting.title}\n{posting.description}")
        requirement_model = extract_posting_requirements(posting)
        entries = {item.id: item for item in [*profile.experiences, *profile.projects]}
        scored: list[tuple[int, RetrievedEvidence]] = []
        for source_order, evidence in enumerate(profile.evidence):
            entry = entries.get(evidence.entity_id)
            if not evidence.confirmed:
                status = RetrievalAdmissionStatus.REJECTED_UNREVIEWED
                reason = "Evidence is not reviewed and confirmed."
            elif entry is None:
                status = RetrievalAdmissionStatus.REJECTED_MISSING_METADATA
                reason = "Evidence does not retain a complete parent-entry reference."
            else:
                evidence_features = extract_reviewed_text_features(
                    " ".join(
                        [
                            evidence.source_text,
                            *evidence.technologies,
                            *evidence.capabilities,
                            *evidence.outcomes,
                        ]
                    )
                )
                entry_features = extract_reviewed_text_features(
                    " ".join(
                        [
                            entry.title,
                            entry.subtitle or "",
                            *entry.technologies,
                            *entry.capabilities,
                        ]
                    )
                )
                match = match_reviewed_features(evidence_features, posting_features)
                relationship = assess_evidence_relationship(
                    bullet_text=evidence.source_text,
                    bullet_features=evidence_features,
                    entry_features=entry_features,
                    structured_values=[
                        *evidence.technologies,
                        *evidence.capabilities,
                        *evidence.outcomes,
                    ],
                    requirements=requirement_model,
                )
                intrinsic = _intrinsic_strength(evidence_features, evidence)
                complementary = round(
                    min(
                        12.0,
                        (len(relationship.complementary_requirement_ids) * 4.0)
                        + (len(relationship.adjacent_requirement_ids) * 2.0),
                    ),
                    2,
                )
                if relationship.relationship is EvidenceRelationship.DIRECT:
                    status = RetrievalAdmissionStatus.ADMITTED_DIRECT
                    reason = relationship.reason
                elif relationship.relationship is EvidenceRelationship.ADJACENT:
                    status = RetrievalAdmissionStatus.ADMITTED_ADJACENT
                    reason = relationship.reason
                elif relationship.relationship is EvidenceRelationship.COMPLEMENTARY:
                    status = RetrievalAdmissionStatus.ADMITTED_COMPLEMENTARY
                    reason = relationship.reason
                elif relationship.relationship is EvidenceRelationship.INCIDENTAL:
                    status = RetrievalAdmissionStatus.REJECTED_INCIDENTAL
                    reason = relationship.reason
                elif match.generic_only:
                    status = RetrievalAdmissionStatus.REJECTED_GENERIC_ONLY
                    reason = match.reason
                else:
                    status = RetrievalAdmissionStatus.REJECTED_LOW_RELEVANCE
                    reason = (
                        "Reviewed evidence lacked specific direct or credibly adjacent "
                        "posting support."
                    )
                total = round(
                    relationship.contextual_relevance + intrinsic + complementary,
                    2,
                )
                scored.append(
                    (
                        source_order,
                        RetrievedEvidence(
                            evidence_id=evidence.id,
                            entry_id=evidence.entity_id,
                            entry_kind=entry.kind.value,
                            source_text=evidence.source_text,
                            rank=1,
                            contextual_relevance=relationship.contextual_relevance,
                            intrinsic_evidence_strength=intrinsic,
                            complementary_value=complementary,
                            total_score=total,
                            normalized_features=list(evidence_features.specific_phrases[:24]),
                            meaningful_overlap=list(relationship.meaningful_overlap),
                            matched_requirements=list(
                                relationship.matched_requirement_labels
                            ),
                            relationship=relationship.relationship,
                            direct_requirement_ids=list(
                                relationship.direct_requirement_ids
                            ),
                            adjacent_requirement_ids=list(
                                relationship.adjacent_requirement_ids
                            ),
                            complementary_requirement_ids=list(
                                relationship.complementary_requirement_ids
                            ),
                            incidental_requirement_ids=list(
                                relationship.incidental_requirement_ids
                            ),
                            short_token_contributions=list(
                                relationship.short_token_contributions
                            ),
                            admission_status=status,
                            admission_reason=reason,
                            provenance=[
                                f"profile.evidence[{evidence.id}]",
                                f"profile.{entry.kind.value}s[{entry.id}]",
                            ],
                        ),
                    )
                )
                continue
            scored.append(
                (
                    source_order,
                    RetrievedEvidence(
                        evidence_id=evidence.id,
                        entry_id=evidence.entity_id,
                        entry_kind=entry.kind.value if entry is not None else "unknown",
                        source_text=evidence.source_text,
                        rank=1,
                        contextual_relevance=0,
                        intrinsic_evidence_strength=0,
                        complementary_value=0,
                        total_score=0,
                        admission_status=status,
                        admission_reason=reason,
                        provenance=[f"profile.evidence[{evidence.id}]"],
                    ),
                )
            )
        scored.sort(
            key=lambda item: (
                -item[1].total_score,
                item[0],
                item[1].evidence_id,
            )
        )
        ranked = [
            item.model_copy(update={"rank": rank}) for rank, (_, item) in enumerate(scored, start=1)
        ]
        admitted_statuses = {
            RetrievalAdmissionStatus.ADMITTED_DIRECT,
            RetrievalAdmissionStatus.ADMITTED_ADJACENT,
            RetrievalAdmissionStatus.ADMITTED_COMPLEMENTARY,
        }
        return EvidenceRetrievalResult(
            profile_fingerprint=_fingerprint(profile.model_dump_json()),
            posting_fingerprint=_fingerprint(posting.model_dump_json()),
            complete_profile_evidence_count=len(profile.evidence),
            reviewed_evidence_count=sum(item.confirmed for item in profile.evidence),
            posting_requirements=list(requirement_model.requirements),
            admitted=[item for item in ranked if item.admission_status in admitted_statuses],
            rejected=[item for item in ranked if item.admission_status not in admitted_statuses],
        )


def _intrinsic_strength(
    features: ReviewedTextFeatures,
    evidence: EvidenceItem,
) -> float:
    outcome_depth = min(
        8.0,
        (len(features.outcome_signals) * 2.0) + (len(evidence.outcomes) * 2.0),
    )
    responsibility_depth = min(10.0, len(features.responsibility_signals) * 2.5)
    capability_depth = min(
        8.0,
        (len(evidence.capabilities) * 2.0) + (len(evidence.technologies) * 1.25),
    )
    return round(
        5.0
        + (features.technical_specificity * 20.0)
        + outcome_depth
        + responsibility_depth
        + capability_depth,
        2,
    )


def _complementary_value(
    evidence_responsibilities: tuple[str, ...],
    posting_responsibilities: tuple[str, ...],
    intrinsic_strength: float,
) -> float:
    shared = set(evidence_responsibilities) & set(posting_responsibilities)
    if not shared:
        return 0.0
    return round(min(12.0, (len(shared) * 3.0) + (intrinsic_strength * 0.12)), 2)


def _fingerprint(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


__all__ = ["InProcessResumeEvidenceRetriever"]
