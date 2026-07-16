from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

from resume_tailor.domain.job_discovery.models import (
    ProfileCapabilityEvidence,
    ProfileCapabilityIndex,
)
from resume_tailor.domain.models import MasterProfile, ResumeItem

_EXPLICIT_ALIASES = {
    "js": "javascript",
    "ts": "typescript",
    "cpp": "c++",
    "c plus plus": "c++",
    "csharp": "c#",
    "c sharp": "c#",
    "postgres": "postgresql",
    "k8s": "kubernetes",
    "ros 2": "ros2",
    "ml": "machine learning",
    "ai": "artificial intelligence",
}


def normalize_capability_term(value: str) -> str:
    """Return the stable, case-insensitive key used by capability indexes."""

    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    normalized = normalized.replace("ros2", "ros 2")
    normalized = re.sub(r"[^\w+#]+", " ", normalized, flags=re.UNICODE)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return _EXPLICIT_ALIASES.get(normalized, normalized)


def _source_text(item: ResumeItem) -> str:
    parts = [item.title]
    if item.description:
        parts.append(item.description)
    return " — ".join(part.strip() for part in parts if part.strip())


class ProfileCapabilityIndexBuilder:
    """Build a deterministic, provenance-preserving index from one profile."""

    def build(self, profile: MasterProfile) -> ProfileCapabilityIndex:
        indexed: defaultdict[str, list[ProfileCapabilityEvidence]] = defaultdict(list)

        def add(
            term: str,
            *,
            source_type: str,
            source_id: str,
            source_text: str,
            demonstrated: bool,
        ) -> None:
            normalized = normalize_capability_term(term)
            if not normalized:
                return
            indexed[normalized].append(
                ProfileCapabilityEvidence(
                    source_type=source_type,  # type: ignore[arg-type]
                    source_id=source_id,
                    source_text=source_text,
                    demonstrated=demonstrated,
                )
            )

        for evidence in profile.evidence:
            if not evidence.confirmed:
                continue
            for term in [*evidence.capabilities, *evidence.technologies]:
                add(
                    term,
                    source_type="confirmed_evidence",
                    source_id=evidence.id,
                    source_text=evidence.source_text,
                    demonstrated=True,
                )

        for item in [*profile.experiences, *profile.projects]:
            for term in [*item.capabilities, *item.technologies]:
                add(
                    term,
                    source_type="resume_item",
                    source_id=item.id,
                    source_text=_source_text(item),
                    demonstrated=True,
                )
            add(
                item.title,
                source_type="title",
                source_id=item.id,
                source_text=item.title,
                demonstrated=False,
            )

        for category in profile.technical_skills:
            for skill in category.skills:
                add(
                    skill.value,
                    source_type="reviewed_skill",
                    source_id=skill.id or f"{category.id}:{skill.value}",
                    source_text=f"{category.category}: {skill.value}",
                    demonstrated=False,
                )

        for course in profile.coursework:
            add(
                course,
                source_type="coursework",
                source_id=f"coursework:{normalize_capability_term(course)}",
                source_text=course,
                demonstrated=False,
            )

        for education_index, education in enumerate(profile.education):
            add(
                education.program,
                source_type="education",
                source_id=f"education:{education_index}",
                source_text=education.program,
                demonstrated=False,
            )
            for course in education.relevant_coursework:
                add(
                    course,
                    source_type="coursework",
                    source_id=f"education:{education_index}:coursework:{normalize_capability_term(course)}",
                    source_text=course,
                    demonstrated=False,
                )

        source_priority = {
            "confirmed_evidence": 0,
            "resume_item": 1,
            "reviewed_skill": 2,
            "coursework": 3,
            "education": 4,
            "title": 5,
        }
        ordered_terms = {}
        for term in sorted(indexed):
            unique: dict[tuple[str, str, str, bool], ProfileCapabilityEvidence] = {}
            for indexed_evidence in indexed[term]:
                key = (
                    indexed_evidence.source_type,
                    indexed_evidence.source_id,
                    indexed_evidence.source_text,
                    indexed_evidence.demonstrated,
                )
                unique[key] = indexed_evidence
            ordered_terms[term] = sorted(
                unique.values(),
                key=lambda evidence: (
                    source_priority[evidence.source_type],
                    evidence.source_id,
                    evidence.source_text.casefold(),
                    evidence.source_text,
                ),
            )
        return ProfileCapabilityIndex(terms=ordered_terms)


def build_profile_capability_index(profile: MasterProfile) -> ProfileCapabilityIndex:
    return ProfileCapabilityIndexBuilder().build(profile)
