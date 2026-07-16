from __future__ import annotations

from dataclasses import dataclass
import re

from resume_tailor.domain.models import (
    Decision,
    JobPosting,
    MasterProfile,
    RankedSkill,
    RankedSkillCategory,
    RoleClassification,
    SkillSelectionStatus,
    TechnicalSkillCategory,
)


_ALIASES = (
    frozenset({"js", "javascript"}),
    frozenset({"ts", "typescript"}),
    frozenset({"cpp", "c++"}),
    frozenset({"csharp", "c#"}),
    frozenset({"postgres", "postgresql"}),
    frozenset({"k8s", "kubernetes"}),
    frozenset({"ros2", "ros 2"}),
    frozenset({"ml", "machine learning"}),
    frozenset({"ai", "artificial intelligence"}),
)

_CONTEXT_STOPWORDS = frozenset(
    {
        "and",
        "the",
        "with",
        "for",
        "systems",
        "system",
        "engineering",
        "development",
        "design",
        "software",
        "hardware",
    }
)


@dataclass(frozen=True)
class SkillPlanResult:
    selected: list[RankedSkillCategory]
    ranked: list[RankedSkillCategory]
    selected_profile_categories: list[TechnicalSkillCategory]
    flattened_selected_values: list[str]
    decisions: list[Decision]


class DeterministicSkillSelector:
    """Scores only reviewed categorized skills against opportunity language."""

    _skill_threshold = 24.0

    def select(
        self,
        profile: MasterProfile,
        posting: JobPosting,
        role: RoleClassification,
        max_selected_categories: int,
    ) -> SkillPlanResult:
        posting_text = _normalize(f"{posting.title} {posting.description}")
        posting_tokens = _tokens(posting_text)
        ranked: list[RankedSkillCategory] = []
        for category_order, category in enumerate(profile.technical_skills):
            scored_skills: list[RankedSkill] = []
            for skill_order, skill in enumerate(category.skills):
                score, signals, reason = self._skill_score(
                    skill.value, posting_text, posting_tokens, role
                )
                scored_skills.append(
                    RankedSkill(
                        id=skill.id or "",
                        value=skill.value,
                        relevance_score=score,
                        status=(
                            SkillSelectionStatus.ALTERNATE
                            if score >= self._skill_threshold
                            else SkillSelectionStatus.EXCLUDED_UNRELATED
                        ),
                        original_order=skill_order,
                        selection_reason=reason,
                        supporting_job_signals=signals,
                        provenance=skill.source_reference
                        or f"reviewed_profile:{category.id}/{skill.id}",
                    )
                )
            relevant = [
                skill for skill in scored_skills if skill.relevance_score >= self._skill_threshold
            ]
            coverage = {signal for skill in relevant for signal in skill.supporting_job_signals}
            best = max((skill.relevance_score for skill in scored_skills), default=0.0)
            mean_relevant = (
                sum(skill.relevance_score for skill in relevant) / len(relevant) if relevant else 0.0
            )
            density = len(relevant) / len(scored_skills)
            label_score = self._label_score(category.category, posting_text, posting_tokens)
            category_score = round(
                (best * 0.45)
                + (mean_relevant * 0.25)
                + (min(len(coverage), 3) * 6)
                + (density * 18)
                + (label_score * 0.12),
                2,
            )
            ranked.append(
                RankedSkillCategory(
                    id=category.id or "",
                    label=category.category,
                    relevance_score=category_score,
                    status=(
                        SkillSelectionStatus.ALTERNATE
                        if relevant
                        else SkillSelectionStatus.EXCLUDED_UNRELATED
                    ),
                    original_order=category_order,
                    selection_reason=(
                        f"{len(relevant)} of {len(scored_skills)} reviewed skills matched "
                        f"{len(coverage)} job signals."
                        if relevant
                        else "No reviewed skill in this category matched the opportunity strongly enough."
                    ),
                    supporting_job_signals=sorted(coverage),
                    skills=sorted(
                        scored_skills,
                        key=lambda item: (-item.relevance_score, item.original_order, item.id),
                    ),
                    provenance=category.source_reference or f"reviewed_profile:{category.id}",
                )
            )
        ranked.sort(key=lambda item: (-item.relevance_score, item.original_order, item.id))
        covered_signals: set[str] = set()
        for index, category in enumerate(ranked):
            signals = set(category.supporting_job_signals)
            overlap = signals & covered_signals
            redundancy_penalty = (
                round((len(overlap) / len(signals)) * 12, 2) if signals else 0.0
            )
            if redundancy_penalty:
                adjusted_score = max(0.0, round(category.relevance_score - redundancy_penalty, 2))
                category = category.model_copy(
                    update={
                        "relevance_score": adjusted_score,
                        "status": (
                            SkillSelectionStatus.EXCLUDED_REDUNDANT
                            if adjusted_score < self._skill_threshold
                            else category.status
                        ),
                        "selection_reason": (
                            f"{category.selection_reason} Redundancy penalty {redundancy_penalty} "
                            "for already-covered job signals."
                        ),
                    }
                )
                ranked[index] = category
            if category.status != SkillSelectionStatus.EXCLUDED_UNRELATED:
                covered_signals.update(signals)
        ranked.sort(key=lambda item: (-item.relevance_score, item.original_order, item.id))
        eligible = [item for item in ranked if item.status == SkillSelectionStatus.ALTERNATE]
        selected_ids = {item.id for item in eligible[:max_selected_categories]}
        selected: list[RankedSkillCategory] = []
        for category_index, category in enumerate(ranked):
            is_selected = category.id in selected_ids
            selected_skills: list[RankedSkill] = []
            skill_order = 0
            updated_skills: list[RankedSkill] = []
            for skill in category.skills:
                skill_selected = is_selected and skill.relevance_score >= self._skill_threshold
                updated = skill.model_copy(
                    update={
                        "status": (
                            SkillSelectionStatus.SELECTED
                            if skill_selected
                            else skill.status
                        ),
                        "selected_order": skill_order if skill_selected else None,
                    }
                )
                updated_skills.append(updated)
                if skill_selected:
                    selected_skills.append(updated)
                    skill_order += 1
            updated_category = category.model_copy(
                update={
                    "status": (
                        SkillSelectionStatus.SELECTED if is_selected else category.status
                    ),
                    "selected_order": len(selected) if is_selected else None,
                    "skills": updated_skills,
                }
            )
            if is_selected:
                selected.append(
                    updated_category.model_copy(update={"skills": selected_skills})
                )
            ranked[category_index] = updated_category
        originals = {category.id: category for category in profile.technical_skills}
        selected_profile_categories = [
            originals[category.id].model_copy(
                update={
                    "values": [skill.value for skill in category.skills],
                    "skills": [
                        skill
                        for selected_skill in category.skills
                        for skill in originals[category.id].skills
                        if skill.id == selected_skill.id
                    ],
                }
            )
            for category in selected
        ]
        decisions = [
            *[
                Decision(
                    action=decision.action,
                    entity_id=decision.source_category_id,
                    reason=decision.reason,
                    constraint=f"retained in {decision.retained_category_id}",
                )
                for decision in profile.skill_normalization_decisions
            ],
            *self._decisions(ranked),
        ]
        return SkillPlanResult(
            selected=selected,
            ranked=ranked,
            selected_profile_categories=selected_profile_categories,
            flattened_selected_values=[
                skill.value for category in selected for skill in category.skills
            ],
            decisions=decisions,
        )

    def _skill_score(
        self,
        value: str,
        posting_text: str,
        posting_tokens: set[str],
        role: RoleClassification,
    ) -> tuple[float, list[str], str]:
        normalized = _normalize(value)
        aliases = _alias_variants(normalized)
        exact = any(_contains_phrase(posting_text, alias) for alias in aliases)
        skill_tokens = set().union(*(_tokens(alias) for alias in aliases))
        overlap = len(skill_tokens & posting_tokens) / max(1, len(skill_tokens))
        semantic_overlap = len(
            _semantic_concepts(normalized) & _semantic_concepts(posting_text)
        )
        signals = sorted(
            signal.id
            for signal in role.signals
            if any(
                _contains_phrase(normalized, _normalize(keyword))
                or _contains_phrase(_normalize(keyword), normalized)
                or bool(skill_tokens & _tokens(_normalize(keyword)))
                for keyword in signal.keywords
            )
        )
        score = min(
            100.0,
            (100 if exact else 0)
            + (overlap * 55)
            + (min(2, len(signals)) * 18)
            + (min(3, semantic_overlap) * 25),
        )
        score = round(score, 2)
        if exact:
            reason = "Exact or normalized-alias match in the job posting."
        elif signals:
            reason = "Related to recognized job signals through normalized terminology."
        elif overlap:
            reason = "Weak contextual term overlap with the job posting."
        else:
            reason = "No meaningful match in the job posting or recognized signals."
        return score, signals, reason

    @staticmethod
    def _label_score(label: str, posting_text: str, posting_tokens: set[str]) -> float:
        normalized = _normalize(label)
        if _contains_phrase(posting_text, normalized):
            return 100.0
        tokens = _tokens(normalized)
        return round((len(tokens & posting_tokens) / max(1, len(tokens))) * 60, 2)

    @staticmethod
    def _decisions(categories: list[RankedSkillCategory]) -> list[Decision]:
        decisions: list[Decision] = []
        for category in categories:
            selected_values = [
                skill.value for skill in category.skills if skill.status == SkillSelectionStatus.SELECTED
            ]
            decisions.append(
                Decision(
                    action=(
                        "skill_category_selected"
                        if category.status == SkillSelectionStatus.SELECTED
                        else "skill_category_alternate"
                        if category.status == SkillSelectionStatus.ALTERNATE
                        else "skill_category_excluded_redundant"
                        if category.status == SkillSelectionStatus.EXCLUDED_REDUNDANT
                        else "skill_category_excluded_unrelated"
                    ),
                    entity_id=category.id,
                    reason=f"{category.selection_reason} Selected skills: {selected_values!r}.",
                    constraint="deterministic categorized-skill relevance",
                )
            )
            for skill in category.skills:
                decisions.append(
                    Decision(
                        action=(
                            "skill_selected"
                            if skill.status == SkillSelectionStatus.SELECTED
                            else "skill_ranked_alternate"
                            if skill.status == SkillSelectionStatus.ALTERNATE
                            else "skill_excluded_redundant"
                            if skill.status == SkillSelectionStatus.EXCLUDED_REDUNDANT
                            else "skill_excluded_unrelated"
                        ),
                        entity_id=skill.id,
                        reason=(
                            f"{skill.selection_reason} Supporting job signals: "
                            f"{skill.supporting_job_signals!r}."
                        ),
                        constraint=f"reviewed category {category.id}",
                    )
                )
        return decisions


def _normalize(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9+#.]+", value.casefold()))


def _tokens(value: str) -> set[str]:
    return set(value.split()) - _CONTEXT_STOPWORDS


def _contains_phrase(text: str, phrase: str) -> bool:
    return bool(phrase) and f" {phrase} " in f" {text} "


def _alias_variants(value: str) -> set[str]:
    variants = {value}
    for group in _ALIASES:
        if value in group:
            variants.update(group)
    return variants


def _semantic_concepts(value: str) -> set[str]:
    tokens = set(re.findall(r"[a-z0-9+#.]+", value.casefold()))
    groups = {
        "integration": {"integration", "interface", "interfaces", "assembly"},
        "design": {"design", "cad", "prototype", "fabrication", "fixture", "mount", "tooling", "mechanical", "mechatronics"},
        "control": {"control", "controller", "automation", "robot", "robotics", "actuator", "embedded", "firmware"},
        "perception": {"camera", "vision", "perception", "sensor", "sensors", "lidar", "detection"},
        "verification": {"test", "testing", "validation", "verify", "debug", "debugging"},
        "software": {"software", "python", "c", "c++", "api", "backend", "pipeline", "data", "algorithm"},
        "delivery": {"deploy", "deployment", "production", "release", "monitoring"},
    }
    return {name for name, members in groups.items() if tokens & members}
