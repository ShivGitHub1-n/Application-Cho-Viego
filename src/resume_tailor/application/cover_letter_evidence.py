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
_ASSERTED_TITLE = re.compile(
    r"\b(?:as|serving as|acting as|in (?:my|the) role as)\s+"
    r"(?P<title>(?:(?:chief|director|head|lead|manager|principal|senior|staff)\s+)?"
    r"(?:[A-Za-z0-9&+/-]+\s+){0,5}"
    r"(?:engineer|architect|designer|researcher|developer|manager))\b\s*[,;:-]?\s*",
    re.IGNORECASE,
)


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
        plan: TailoringPlan | None = None,
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
        candidates_by_entry: dict[str, list[RetrievedEvidence]] = {}
        for candidate in candidates:
            candidates_by_entry.setdefault(candidate.entry_id, []).append(candidate)
        for thread in candidates_by_entry.values():
            thread.sort(key=self._candidate_key)

        selected_threads: list[list[RetrievedEvidence]] = []
        used_requirements: set[str] = set()
        used_features: set[str] = set()
        while candidates_by_entry and len(selected_threads) < 3:
            ranked_threads = sorted(
                candidates_by_entry.values(),
                key=lambda thread: self._thread_key(
                    thread,
                    used_requirements=used_requirements,
                    used_features=used_features,
                ),
            )
            thread = ranked_threads[0]
            selected_threads.append(thread)
            candidates_by_entry.pop(thread[0].entry_id)
            used_requirements.update(self._thread_requirements(thread))
            used_features.update(feature for item in thread for feature in item.meaningful_overlap)

        selected: list[RetrievedEvidence] = []
        for thread in selected_threads:
            representative = thread[0]
            selected.append(representative)
            representative_requirements = self._item_requirements(representative)
            representative_features = set(representative.meaningful_overlap)
            supporting = sorted(
                thread[1:],
                key=lambda item: (
                    -len(self._item_requirements(item) - representative_requirements),
                    -len(set(item.meaningful_overlap) - representative_features),
                    *self._candidate_key(item),
                ),
            )
            if supporting and supporting[0].relationship in {
                EvidenceRelationship.DIRECT,
                EvidenceRelationship.ADJACENT,
            }:
                selected.append(supporting[0])

        records: list[CoverLetterEvidenceRecord] = []
        for retrieved in selected:
            source = evidence_by_id[retrieved.evidence_id]
            entry = entries[source.entity_id]
            writer_text, excluded_titles = self._writer_safe_text(
                source.source_text,
                entry.title,
            )
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
                    writer_text=writer_text,
                    excluded_title_claims=excluded_titles,
                    technologies=list(source.technologies),
                    outcomes=list(source.outcomes),
                    provenance=list(retrieved.provenance),
                    matched_requirements=list(retrieved.matched_requirements),
                    retrieval_rank=retrieved.rank,
                    selected_in_final_resume=source.id in resume_evidence_ids,
                    selection_reason=self._selection_reason(
                        source.id in resume_evidence_ids,
                        retrieved.matched_requirements,
                        relationship=retrieved.relationship,
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
    def _item_requirements(item: RetrievedEvidence) -> set[str]:
        return {
            *item.direct_requirement_ids,
            *item.adjacent_requirement_ids,
            *item.complementary_requirement_ids,
        }

    @classmethod
    def _thread_requirements(cls, thread: list[RetrievedEvidence]) -> set[str]:
        return {requirement for item in thread for requirement in cls._item_requirements(item)}

    @staticmethod
    def _candidate_key(item: RetrievedEvidence) -> tuple[object, ...]:
        return (
            _RELATIONSHIP_PRIORITY[item.relationship],
            -len(item.direct_requirement_ids),
            -len(item.meaningful_overlap),
            -item.contextual_relevance,
            -item.total_score,
            item.rank,
            item.evidence_id,
        )

    @classmethod
    def _thread_key(
        cls,
        thread: list[RetrievedEvidence],
        *,
        used_requirements: set[str],
        used_features: set[str],
    ) -> tuple[object, ...]:
        requirements = cls._thread_requirements(thread)
        features = {feature for item in thread for feature in item.meaningful_overlap}
        direct_requirements = {
            requirement
            for item in thread
            for requirement in item.direct_requirement_ids
        }
        best = thread[0]
        has_prior_thread = bool(used_requirements or used_features)
        return (
            _RELATIONSHIP_PRIORITY[best.relationship],
            -len(direct_requirements - used_requirements) if has_prior_thread else 0,
            -len(requirements - used_requirements) if has_prior_thread else 0,
            -len(features - used_features) if has_prior_thread else 0,
            -best.total_score,
            -best.contextual_relevance,
            -len(direct_requirements),
            -len(features),
            -sum(item.total_score for item in thread[:2]),
            best.rank,
            best.entry_id,
        )

    @staticmethod
    def _final_resume_evidence_ids(
        final_resume: StructuredResume | None,
        plan: TailoringPlan | None,
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
        if plan is None:
            return set()
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
    def _writer_safe_text(source_text: str, authoritative_title: str) -> tuple[str, list[str]]:
        """Remove conflicting self-title phrases only from writer-facing prose."""

        excluded: list[str] = []
        canonical = " ".join(authoritative_title.casefold().split())

        def replace(match: re.Match[str]) -> str:
            asserted = " ".join(match.group("title").casefold().split())
            if asserted == canonical:
                return match.group(0)
            excluded.append(match.group("title").strip())
            return ""

        safe = _ASSERTED_TITLE.sub(replace, source_text)
        if excluded:
            clauses = [
                clause.strip(" ,;:-")
                for clause in re.split(r"[,;]", safe)
                if clause.strip(" ,;:-")
            ]
            technical_clauses = [
                clause
                for clause in clauses
                if not re.search(
                    r"\b(?:led|managed|oversaw|supervised)\b|"
                    r"\breview(?:ed|ing)\s+(?:subordinate|junior|team)\b",
                    clause,
                    re.IGNORECASE,
                )
            ]
            if technical_clauses:
                safe = ", ".join(technical_clauses)
        safe = re.sub(r"\s+", " ", safe).strip(" ,;:-")
        if not safe:
            safe = authoritative_title
        return safe, list(dict.fromkeys(excluded))

    @staticmethod
    def _selection_reason(
        selected_in_resume: bool,
        requirements: list[str],
        *,
        relationship: EvidenceRelationship,
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
            return (
                f"{relationship.value.title()} reviewed evidence consistent with the final "
                "resume narrative." + context
            )
        return (
            f"{relationship.value.title()} reviewed evidence omitted from the one-page resume "
            "that adds a distinct thread."
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
