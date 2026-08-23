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
            focus_terms = list(
                dict.fromkeys(
                    term
                    for record in records
                    for term in [*record.technologies, *record.outcomes]
                    if term.strip()
                )
            )
            focus = ", ".join(focus_terms[:4]) or self._short_text(
                records[0].writer_text or records[0].source_text,
                150,
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
                )
            )

        primary_focus = stories[0].focus
        thesis = self._short_text(
            f"Build the letter around how demonstrated work with {primary_focus} connects "
            f"to the role's need for {role_themes[0]}; use the remaining stories only to "
            "deepen that same through-line.",
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
                "Specific, technically literate, conversational, and self-possessed; "
                "prefer clear observations over corporate enthusiasm."
            ),
        )

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
            f"Use the actual {company} posting as the personalization authority: the "
            f"specific work that stands out is {role_themes[0]}. Do not add company praise."
        )

    @staticmethod
    def _short_text(value: str, limit: int) -> str:
        normalized = " ".join(value.split())
        if len(normalized) <= limit:
            return normalized.rstrip(".")
        return normalized[: limit - 1].rsplit(" ", 1)[0].rstrip(".,;:") + "…"


__all__ = ["CoverLetterNarrativePlanner"]
