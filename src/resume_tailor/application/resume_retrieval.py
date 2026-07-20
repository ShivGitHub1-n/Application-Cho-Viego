from __future__ import annotations

from hashlib import sha256

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


class InProcessResumeEvidenceRetriever:
    """Retrieve complete-profile reviewed evidence behind a replaceable typed seam."""

    def retrieve(
        self,
        profile: MasterProfile,
        posting: JobPosting,
    ) -> EvidenceRetrievalResult:
        posting_features = extract_reviewed_text_features(f"{posting.title}\n{posting.description}")
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
                            entry.title,
                            entry.subtitle or "",
                            *entry.technologies,
                            *entry.capabilities,
                        ]
                    )
                )
                match = match_reviewed_features(evidence_features, posting_features)
                intrinsic = _intrinsic_strength(evidence_features, evidence)
                complementary = _complementary_value(
                    evidence_features.responsibility_signals,
                    posting_features.responsibility_signals,
                    intrinsic,
                )
                admitted_adjacent = (
                    not match.generic_only
                    and complementary >= 6.0
                    and evidence_features.technical_specificity >= 0.22
                )
                if match.admitted:
                    status = RetrievalAdmissionStatus.ADMITTED_DIRECT
                    reason = match.reason
                elif admitted_adjacent:
                    status = RetrievalAdmissionStatus.ADMITTED_ADJACENT
                    reason = (
                        "Admitted as strong, specific reviewed evidence with a credible "
                        "shared technical responsibility; no role-family rule was used."
                    )
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
                    match.relevance_score + intrinsic + complementary,
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
                            contextual_relevance=match.relevance_score,
                            intrinsic_evidence_strength=intrinsic,
                            complementary_value=complementary,
                            total_score=total,
                            normalized_features=list(evidence_features.specific_phrases[:24]),
                            meaningful_overlap=list(match.meaningful_overlap),
                            matched_requirements=[
                                *match.matched_requirements,
                                *match.responsibility_overlap,
                            ],
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
        }
        return EvidenceRetrievalResult(
            profile_fingerprint=_fingerprint(profile.model_dump_json()),
            posting_fingerprint=_fingerprint(posting.model_dump_json()),
            complete_profile_evidence_count=len(profile.evidence),
            reviewed_evidence_count=sum(item.confirmed for item in profile.evidence),
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
