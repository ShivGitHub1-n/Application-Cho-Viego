from __future__ import annotations

import re
from hashlib import sha256

from resume_tailor.application.resume_retrieval import InProcessResumeEvidenceRetriever
from resume_tailor.domain.cover_letter import (
    CoverLetterEvidenceKind,
    CoverLetterEvidenceRecord,
    CoverLetterEvidenceSelectionDiagnostic,
)
from resume_tailor.domain.hybrid_resume import RetrievedEvidence
from resume_tailor.domain.models import JobPosting, MasterProfile, StructuredResume, TailoringPlan
from resume_tailor.domain.requirement_ranking import EvidenceRelationship

_RELATIONSHIP_PRIORITY = {
    EvidenceRelationship.DIRECT: 0,
    EvidenceRelationship.ADJACENT: 1,
    EvidenceRelationship.COMPLEMENTARY: 2,
    EvidenceRelationship.INCIDENTAL: 3,
    EvidenceRelationship.REJECTED: 4,
}


class CoverLetterEvidencePortfolio:
    def __init__(
        self,
        retriever: InProcessResumeEvidenceRetriever | None = None,
    ) -> None:
        self._retriever = retriever or InProcessResumeEvidenceRetriever()

    def select(
        self,
        profile: MasterProfile,
        posting: JobPosting,
        plan: TailoringPlan,
        *,
        final_resume: StructuredResume | None = None,
        explicit_motivation: str | None = None,
    ) -> tuple[list[CoverLetterEvidenceRecord], CoverLetterEvidenceSelectionDiagnostic]:
        retrieval = self._retriever.retrieve(profile, posting)
        entries = {item.id: item for item in [*profile.experiences, *profile.projects]}
        evidence_by_id = {item.id: item for item in profile.evidence if item.confirmed}
        resume_evidence_ids = self._final_resume_evidence_ids(final_resume, plan)
        candidates = [
            item
            for item in retrieval.admitted
            if item.evidence_id in evidence_by_id and item.entry_id in entries
        ]
        sparse_fallback = False
        if not candidates:
            candidates = [
                item
                for item in retrieval.rejected
                if item.evidence_id in evidence_by_id and item.entry_id in entries
            ][:3]
            sparse_fallback = bool(candidates)
        selected: list[RetrievedEvidence] = []

        if candidates:
            selected.append(
                min(
                    candidates,
                    key=lambda item: (
                        _RELATIONSHIP_PRIORITY[item.relationship],
                        item.entry_kind != "experience",
                        item.evidence_id not in resume_evidence_ids,
                        item.rank,
                    ),
                )
            )

        while len(selected) < min(3, len(candidates)):
            used_ids = {item.evidence_id for item in selected}
            used_entries = {item.entry_id for item in selected}
            used_requirements = {
                requirement
                for item in selected
                for requirement in [
                    *item.direct_requirement_ids,
                    *item.adjacent_requirement_ids,
                    *item.complementary_requirement_ids,
                ]
            }
            remaining = [item for item in candidates if item.evidence_id not in used_ids]
            if not remaining:
                break
            used_features = {feature for item in selected for feature in item.normalized_features}
            second_experience_available = (
                len(selected) == 1
                and selected[0].entry_kind == "experience"
                and any(
                    item.entry_kind == "experience"
                    and item.entry_id not in used_entries
                    and item.relationship
                    in {EvidenceRelationship.DIRECT, EvidenceRelationship.ADJACENT}
                    for item in remaining
                )
            )
            remaining.sort(
                key=lambda item: (
                    (
                        item.entry_id in used_entries
                        or item.relationship
                        not in {
                            EvidenceRelationship.DIRECT,
                            EvidenceRelationship.ADJACENT,
                        }
                    ),
                    second_experience_available and item.entry_kind != "experience",
                    _RELATIONSHIP_PRIORITY[item.relationship],
                    (
                        len(selected) >= 2
                        and not any(chosen.entry_kind == "project" for chosen in selected)
                        and item.entry_kind != "project"
                    ),
                    not bool(
                        set(
                            [
                                *item.direct_requirement_ids,
                                *item.adjacent_requirement_ids,
                                *item.complementary_requirement_ids,
                            ]
                        )
                        - used_requirements
                    ),
                    len(set(item.normalized_features) & used_features),
                    item.evidence_id in resume_evidence_ids,
                    item.rank,
                )
            )
            selected.append(remaining[0])

        for thread in list(selected):
            if len(selected) >= 6:
                break
            used_ids = {item.evidence_id for item in selected}
            used_features = {feature for item in selected for feature in item.normalized_features}
            supporting = [
                item
                for item in candidates
                if item.evidence_id not in used_ids
                and item.entry_id == thread.entry_id
                and item.relationship
                in {EvidenceRelationship.DIRECT, EvidenceRelationship.ADJACENT}
            ]
            if not supporting:
                continue
            supporting.sort(
                key=lambda item: (
                    len(set(item.normalized_features) & used_features),
                    _RELATIONSHIP_PRIORITY[item.relationship],
                    item.rank,
                )
            )
            selected.append(supporting[0])

        records: list[CoverLetterEvidenceRecord] = []
        for retrieved in selected:
            source = evidence_by_id[retrieved.evidence_id]
            entry = entries[source.entity_id]
            kind = (
                CoverLetterEvidenceKind.EXPERIENCE
                if entry.kind.value == "experience"
                else CoverLetterEvidenceKind.PROJECT
            )
            records.append(
                CoverLetterEvidenceRecord(
                    id=source.id,
                    kind=kind,
                    entity_id=source.entity_id,
                    entry_title=entry.title,
                    source_text=source.source_text,
                    technologies=list(source.technologies),
                    outcomes=list(source.outcomes),
                    provenance=list(retrieved.provenance),
                    matched_requirements=list(retrieved.matched_requirements),
                    retrieval_rank=retrieved.rank,
                    selected_in_final_resume=source.id in resume_evidence_ids,
                    selection_reason=self._selection_reason(
                        source.id in resume_evidence_ids,
                        retrieved.matched_requirements,
                        sparse_fallback=sparse_fallback,
                    ),
                )
            )

        if len(records) < 2:
            education = self._education_record(profile, posting)
            if education is not None:
                records.append(education)
        if len(records) < 2:
            skill = self._skill_record(profile, posting)
            if skill is not None:
                records.append(skill)
        if explicit_motivation and explicit_motivation.strip():
            motivation = " ".join(explicit_motivation.split())
            records.append(
                CoverLetterEvidenceRecord(
                    id=f"motivation:{sha256(motivation.encode()).hexdigest()[:16]}",
                    kind=CoverLetterEvidenceKind.USER_MOTIVATION,
                    source_text=motivation,
                    provenance=["explicit_user_motivation"],
                    selection_reason=(
                        "Explicit user-provided motivation is authoritative for personal "
                        "preference."
                    ),
                )
            )
        records = records[:7]
        selected_ids = [record.id for record in records]
        omitted_resume = sorted(resume_evidence_ids - set(selected_ids))
        used_omitted = [
            record.id
            for record in records
            if record.kind in {CoverLetterEvidenceKind.EXPERIENCE, CoverLetterEvidenceKind.PROJECT}
            and not record.selected_in_final_resume
        ]
        diagnostic = CoverLetterEvidenceSelectionDiagnostic(
            selected_evidence_ids=selected_ids,
            omitted_resume_evidence_ids=omitted_resume,
            used_evidence_omitted_from_resume_ids=used_omitted,
            considered_evidence_count=len(candidates),
            narrative_thread_count=min(
                3,
                len(
                    {
                        record.entity_id or record.id
                        for record in records
                        if record.kind is not CoverLetterEvidenceKind.USER_MOTIVATION
                    }
                ),
            ),
            reasons=[record.selection_reason for record in records],
        )
        return records, diagnostic

    @staticmethod
    def _final_resume_evidence_ids(
        final_resume: StructuredResume | None,
        plan: TailoringPlan,
    ) -> set[str]:
        if final_resume is not None:
            return {
                evidence_id
                for bullets in [
                    *final_resume.experience_bullets.values(),
                    *final_resume.project_bullets.values(),
                ]
                for bullet in bullets
                for evidence_id in bullet.evidence_ids
            }
        if plan.composition_selection is not None:
            return set(plan.composition_selection.selected_evidence_ids)
        selected_claim_ids = set(plan.selected_claim_ids)
        return {
            evidence_id
            for candidate in plan.claim_candidates
            if candidate.id in selected_claim_ids
            for evidence_id in candidate.evidence_ids
        }

    @staticmethod
    def _selection_reason(
        selected_in_resume: bool,
        requirements: list[str],
        *,
        sparse_fallback: bool,
    ) -> str:
        if sparse_fallback:
            return (
                "Reviewed adjacent evidence retained because no stronger direct match was "
                "available; the limitation remains visible in the narrative portfolio."
            )
        rendered_requirements = [item.strip().rstrip(".") for item in requirements[:3]]
        context = (
            f" It connects to: {', '.join(rendered_requirements)}." if rendered_requirements else ""
        )
        if selected_in_resume:
            return "Strong reviewed evidence consistent with the final resume narrative." + context
        return (
            "Strong reviewed evidence omitted from the one-page resume that adds a distinct thread."
            + context
        )

    @staticmethod
    def _education_record(
        profile: MasterProfile,
        posting: JobPosting,
    ) -> CoverLetterEvidenceRecord | None:
        if not profile.education:
            return None
        posting_text = posting.description.casefold()
        if not any(term in posting_text for term in ("degree", "student", "university", "college")):
            return None
        education = profile.education[0]
        components = [education.program, education.school]
        if education.minor_or_specialization:
            components.append(education.minor_or_specialization)
        text = " at ".join(components[:2])
        if len(components) > 2:
            text += f", with {components[2]}"
        identifier = sha256(text.encode()).hexdigest()[:16]
        return CoverLetterEvidenceRecord(
            id=f"education:{identifier}",
            kind=CoverLetterEvidenceKind.EDUCATION,
            source_text=text,
            provenance=["profile.education[0]"],
            selection_reason=(
                "Canonical reviewed education supports an explicit posting requirement."
            ),
        )

    @staticmethod
    def _skill_record(
        profile: MasterProfile,
        posting: JobPosting,
    ) -> CoverLetterEvidenceRecord | None:
        posting_tokens = set(re.findall(r"[a-z0-9+#.-]+", posting.description.casefold()))
        matches = [
            skill.value
            for category in profile.technical_skills
            for skill in category.skills
            if skill.value.casefold() in posting.description.casefold()
            or set(re.findall(r"[a-z0-9+#.-]+", skill.value.casefold())) <= posting_tokens
        ]
        if not matches:
            return None
        text = ", ".join(dict.fromkeys(matches[:4]))
        return CoverLetterEvidenceRecord(
            id=f"skills:{sha256(text.encode()).hexdigest()[:16]}",
            kind=CoverLetterEvidenceKind.SKILL,
            source_text=text,
            technologies=list(dict.fromkeys(matches[:4])),
            provenance=["profile.technical_skills"],
            selection_reason="Reviewed skill evidence directly matches the posting.",
        )


__all__ = ["CoverLetterEvidencePortfolio"]
