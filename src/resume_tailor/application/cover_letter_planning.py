from __future__ import annotations

from collections import defaultdict

from resume_tailor.domain.company_research import CompanyFactConfidence, CompanyResearchBundle
from resume_tailor.domain.cover_letter import (
    CoverLetterEvidenceRecord,
    CoverLetterNarrativePlan,
    CoverLetterNarrativeStory,
)
from resume_tailor.domain.models import JobPosting


class CoverLetterNarrativePlanner:
    """Turn ranked letter evidence into an ordered persuasive-writing brief."""

    def create(
        self,
        posting: JobPosting,
        evidence: list[CoverLetterEvidenceRecord],
        research: CompanyResearchBundle,
    ) -> CoverLetterNarrativePlan:
        role_themes = self._role_themes(evidence, posting)
        grouped: dict[str, list[CoverLetterEvidenceRecord]] = defaultdict(list)
        for record in evidence:
            grouped[record.entity_id or record.id].append(record)

        stories: list[CoverLetterNarrativeStory] = []
        for index, records in enumerate(grouped.values()):
            if index >= 3:
                break
            concrete_details = list(
                dict.fromkeys(
                    term
                    for record in records
                    for term in [*record.technologies, *record.outcomes]
                    if term.strip()
                )
            )
            source_focus = records[0].writer_text or records[0].source_text
            focus = self._short_text(
                "Develop the engineering problem, choice, or constraint demonstrated by: "
                f"{source_focus}",
                240,
            )
            matched = list(
                dict.fromkeys(
                    requirement
                    for record in records
                    for requirement in record.matched_requirements
                    if requirement.strip()
                )
            )
            role_connection = "; ".join(matched[:2]) or role_themes[0]
            stories.append(
                CoverLetterNarrativeStory(
                    thread_id=f"story-{index + 1}",
                    entry_id=records[0].entity_id,
                    authoritative_title=records[0].entry_title,
                    evidence_ids=[record.id for record in records[:3]],
                    focus=focus,
                    role_connection=role_connection,
                    concrete_details=concrete_details[:6],
                    narrative_function=self._narrative_function(index),
                )
            )

        thesis = self._short_text(
            "Choose one specific engineering point of view from the intersection of the "
            f"role's work on {role_themes[0]} and the reviewed stories. Let concrete choices "
            "and constraints reveal that point of view. Do not repeat it as every paragraph's "
            "lesson.",
            490,
        )
        hook = self._company_role_hook(posting, research, role_themes)
        titles = {
            record.entity_id: record.entry_title
            for record in evidence
            if record.entity_id and record.entry_title
        }
        prohibited = list(
            dict.fromkeys(
                claim
                for record in evidence
                for claim in record.excluded_title_claims
            )
        )
        return CoverLetterNarrativePlan(
            thesis=thesis,
            company_role_hook=hook,
            role_themes=role_themes,
            stories=stories,
            authoritative_entry_titles=titles,
            prohibited_title_claims=prohibited,
            tone=(
                "Specific, technically literate, conversational, and self-possessed. Vary "
                "sentence length, prefer normal English, and allow restrained personality "
                "to come from what the candidate notices about the work."
            ),
            opening_direction=(
                "Begin with an original technical observation or tension that the first "
                "story can prove. Do not begin with application intent, what stood out, or a "
                "list of posting responsibilities."
            ),
            closing_direction=(
                "Land one concise forward-looking thought earned by the preceding stories. "
                "Do not restate the thesis, inventory skills, or use a stock discussion request."
            ),
        )

    @staticmethod
    def _narrative_function(index: int) -> str:
        return (
            (
                "Establish the candidate's main technical point of view through one concrete "
                "system, problem, or engineering decision."
            ),
            (
                "Add a different dimension of the candidate through a distinct implementation, "
                "integration, diagnostic, or design constraint; do not repeat the first lesson."
            ),
            (
                "Use only if it changes the reader's picture of the candidate. Add a genuinely "
                "different context or scale instead of a third version of the same takeaway."
            ),
        )[min(index, 2)]

    @staticmethod
    def _role_themes(
        evidence: list[CoverLetterEvidenceRecord],
        posting: JobPosting,
    ) -> list[str]:
        themes = list(
            dict.fromkeys(
                requirement.strip().rstrip(".")
                for record in evidence
                for requirement in record.matched_requirements
                if requirement.strip()
            )
        )
        if not themes:
            themes = [posting.title]
        return [CoverLetterNarrativePlanner._short_text(theme, 180) for theme in themes[:4]]

    @classmethod
    def _company_role_hook(
        cls,
        posting: JobPosting,
        research: CompanyResearchBundle,
        role_themes: list[str],
    ) -> str:
        verified = next(
            (
                fact.supported_claim
                for fact in research.facts
                if fact.confidence
                in {CompanyFactConfidence.VERIFIED, CompanyFactConfidence.USER_AUTHORITY}
            ),
            None,
        )
        if verified:
            return cls._short_text(verified, 420)
        company = posting.company_name or "the employer"
        return (
            f"Use the actual {company} posting as the only employer authority. Ground the "
            f"connection in the work on {role_themes[0]}, but do not quote or paraphrase this "
            "brief and do not add company praise."
        )

    @staticmethod
    def _short_text(value: str, limit: int) -> str:
        normalized = " ".join(value.split())
        if len(normalized) <= limit:
            return normalized.rstrip(".")
        return normalized[: limit - 1].rsplit(" ", 1)[0].rstrip(".,;:") + "…"


__all__ = ["CoverLetterNarrativePlanner"]
