from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, replace
from hashlib import sha256
from typing import cast

from resume_tailor.application.generation_diagnostics import GenerationTelemetry
from resume_tailor.application.requirement_ranking import (
    assess_evidence_relationship,
    extract_posting_requirements,
    requirement_component_supported,
)
from resume_tailor.application.resume_features import (
    FeatureMatch,
    ReviewedTextFeatures,
    TemplateV1BulletLineEstimator,
    TemplateV1SkillRowWidthEstimator,
    extract_reviewed_text_features,
    match_reviewed_features,
    normalize_reviewed_text,
)
from resume_tailor.domain.generated_artifact import GenerationStage
from resume_tailor.domain.hybrid_resume import (
    BulletValidationStatus,
    BulletVariantRecord,
)
from resume_tailor.domain.models import (
    ClaimSupport,
    EntityKind,
    EvidenceItem,
    JobPosting,
    MasterProfile,
    ResumeItem,
    ReviewedTechnicalSkill,
    StructuredBullet,
    StructuredResume,
    TechnicalSkillCategory,
    TemplateConstraints,
)
from resume_tailor.domain.requirement_ranking import (
    DirectCandidateTradeoffDiagnostic,
    EvidenceRelationship,
    EvidenceRelationshipAssessment,
    PostingRequirementModel,
    RequirementAuthority,
    RequirementComponentMatch,
    RequirementCoverageDiagnostic,
    ShortTokenContribution,
)
from resume_tailor.domain.resume_composition import (
    TEMPLATE_V1_ACCEPTABLE_DENSITY_CEILING,
    TEMPLATE_V1_DENSITY_INVESTIGATION_FLOOR,
    TEMPLATE_V1_IDEAL_DENSITY,
    TEMPLATE_V1_PREFERRED_DENSITY_CEILING,
    TEMPLATE_V1_PREFERRED_DENSITY_FLOOR,
    TEMPLATE_V1_UTILIZATION_TARGET_CEILING,
    TEMPLATE_V1_UTILIZATION_TARGET_FLOOR,
    BulletLineFitDiagnostic,
    CandidateExclusionCategory,
    CompositionCandidateDiagnostic,
    CompositionCandidateKind,
    CompositionOutcome,
    CompositionTerminationReason,
    CompositionUnderfillReason,
    EntryBulletSelectionDiagnostic,
    ExperiencePackageAlternativeDiagnostic,
    ExperiencePackageSelectionDiagnostic,
    ExperienceSingleBulletExceptionReason,
    PageFillIterationDiagnostic,
    PageFitEvaluation,
    PageVerificationStatus,
    PortfolioMarginalComparisonDiagnostic,
    PreferredDensityStatus,
    ProjectRepresentationDiagnostic,
    ProjectRepresentationStatus,
    ResumeCompositionDiagnostic,
    SkillRowSelectionDiagnostic,
)
from resume_tailor.ports.interfaces import ResumePageFitEvaluator

_YEAR_PATTERN = re.compile(r"(?:19|20)\d{2}")
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "intern",
        "is",
        "engineer",
        "engineering",
        "of",
        "on",
        "or",
        "our",
        "experience",
        "role",
        "that",
        "the",
        "their",
        "this",
        "to",
        "we",
        "will",
        "with",
        "you",
        "your",
    }
)
_LOW_INFORMATION_TOKENS = frozenset(
    {
        "assisted",
        "helped",
        "responsible",
        "supported",
        "tasks",
        "various",
        "worked",
    }
)
_ENTERPRISE_PRODUCTION_SIGNALS = frozenset(
    {
        "compliance",
        "deployed",
        "deployment",
        "enterprise",
        "production",
        "regulated",
        "reliability",
        "scale",
        "scaled",
    }
)


@dataclass(frozen=True)
class CompositionSearchBounds:
    beam_width: int = 6
    maximum_estimated_page_evaluations: int = 128
    maximum_exact_finalist_evaluations: int = 12
    maximum_expansion_operations: int = 1_600
    maximum_ranked_bullets: int = 48
    maximum_expansions_per_state: int = 6
    maximum_selected_bullets: int = 24
    maximum_selected_entries: int = 7
    maximum_experience_entries: int = 4
    maximum_project_entries: int = 3
    maximum_bullets_per_entry: int | None = None
    target_finalist_count: int = 8


@dataclass(frozen=True)
class _PostingContext:
    normalized_text: str
    tokens: frozenset[str]
    title_tokens: frozenset[str]
    weighted_segments: tuple[tuple[str, float], ...]
    features: ReviewedTextFeatures
    requirements: PostingRequirementModel


@dataclass(frozen=True)
class _BulletCandidate:
    evidence_id: str
    source_evidence_ids: tuple[str, ...]
    entry_id: str
    entry_kind: EntityKind
    text: str
    score: float
    contextual_relevance: float
    intrinsic_evidence_strength: float
    estimated_lines: int
    line_fit: BulletLineFitDiagnostic
    coverage_keys: tuple[str, ...]
    coverage_labels: tuple[str, ...]
    normalized_features: tuple[str, ...]
    meaningful_overlap: tuple[str, ...]
    generic_only_rejected: bool
    admitted: bool
    admission_reason: str
    relationship: EvidenceRelationship
    direct_requirement_ids: tuple[str, ...]
    adjacent_requirement_ids: tuple[str, ...]
    complementary_requirement_ids: tuple[str, ...]
    incidental_requirement_ids: tuple[str, ...]
    short_token_contributions: tuple[ShortTokenContribution, ...]
    provenance: tuple[str, ...]
    entry_order: int
    evidence_order: int
    writing_variant: BulletVariantRecord | None = None
    preserved_supported_terms: tuple[str, ...] = ()
    removed_supported_terms: tuple[str, ...] = ()
    writing_adjustment: float = 0.0
    source_alternative_score: float = 0.0


@dataclass(frozen=True)
class _ExperiencePackage:
    package_id: str
    entry_id: str
    bullet_ids: tuple[str, ...]
    source_evidence_ids: tuple[str, ...]
    package_relevance: float
    intrinsic_strength: float
    writing_quality: float
    duration_recency_contribution: float
    enterprise_production_contribution: float
    enterprise_production_evidence: tuple[str, ...]
    distinct_coverage: tuple[str, ...]
    page_cost: float
    redundancy_penalty: float
    total_score: float
    single_bullet_exception_reason: ExperienceSingleBulletExceptionReason | None = None


@dataclass(frozen=True)
class _SkillCandidate:
    category_id: str
    label: str
    category: TechnicalSkillCategory
    score: float
    coverage_keys: tuple[str, ...]
    coverage_labels: tuple[str, ...]
    normalized_features: tuple[str, ...]
    meaningful_overlap: tuple[str, ...]
    supported_skill_ids: tuple[str, ...]
    declared_only_skill_ids: tuple[str, ...]
    construction_reason: str
    provenance: tuple[str, ...]
    source_category_ids: tuple[str, ...]
    one_skill_exception_reason: str | None
    grouping_reason: str
    relationship: EvidenceRelationship
    original_order: int
    estimated_available_width_points: float
    estimated_used_width_points: float
    estimated_remaining_width_points: float
    estimated_used_width_ratio: float
    compatible_omitted_skill_values: tuple[str, ...]
    underfill_exception_reason: str | None


@dataclass(frozen=True)
class _State:
    bullet_ids: frozenset[str]
    skill_category_ids: frozenset[str]

    @property
    def key(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        return tuple(sorted(self.bullet_ids)), tuple(sorted(self.skill_category_ids))


@dataclass(frozen=True)
class _EvaluatedState:
    state: _State
    resume: StructuredResume
    evaluation: PageFitEvaluation
    quality: float
    coverage_count: int
    three_line_bullet_count: int
    substantive_project_count: int


@dataclass(frozen=True)
class _Expansion:
    candidate_id: str
    source_id: str
    kind: CompositionCandidateKind
    state: _State
    marginal_score: float
    redundancy_penalty: float
    preference_bonus: float
    line_cost: float


@dataclass(frozen=True)
class _CandidatePool:
    ranked_bullets: list[_BulletCandidate]
    relevance_excluded_bullets: list[_BulletCandidate]
    redundancy_excluded_bullets: list[_BulletCandidate]
    ranking_bound_excluded_bullets: list[_BulletCandidate]


class DeterministicResumeComposer:
    """Compose reviewed profile atoms through bounded Template V1 page-fit search."""

    _minimum_bullet_score = 12.0
    _minimum_skill_score = 12.0
    _minimum_marginal_score = 7.0
    _near_duplicate_threshold = 0.72
    _maximum_skills_per_display_row = 8

    def __init__(
        self,
        page_fit_evaluator: ResumePageFitEvaluator,
        *,
        bounds: CompositionSearchBounds | None = None,
        line_estimator: TemplateV1BulletLineEstimator | None = None,
        skill_row_estimator: TemplateV1SkillRowWidthEstimator | None = None,
        telemetry: GenerationTelemetry | None = None,
    ) -> None:
        self._page_fit_evaluator = page_fit_evaluator
        self._bounds = bounds or CompositionSearchBounds()
        self._line_estimator = line_estimator or TemplateV1BulletLineEstimator()
        self._skill_row_estimator = skill_row_estimator or TemplateV1SkillRowWidthEstimator()
        self._telemetry = telemetry or GenerationTelemetry()

    def compose(
        self,
        baseline: StructuredResume,
        profile: MasterProfile,
        posting: JobPosting,
        constraints: TemplateConstraints,
        *,
        attempt_exact_final: bool = True,
    ) -> StructuredResume:
        self._telemetry.increment("composition_searches")
        with self._telemetry.measure(GenerationStage.COMPOSITION_CANDIDATE_CONSTRUCTION):
            context = _posting_context(posting)
            available_variants = _available_variants(baseline)
            advisory_evidence_ids = (
                set() if available_variants else _baseline_evidence_ids(baseline)
            )
            if available_variants:
                with self._telemetry.measure(GenerationStage.WRITER_VARIANT_SELECTION):
                    candidate_pool = self._candidate_pool(
                        profile,
                        context,
                        available_variants,
                        advisory_evidence_ids,
                    )
            else:
                candidate_pool = self._candidate_pool(
                    profile,
                    context,
                    available_variants,
                    advisory_evidence_ids,
                )
            bullets = candidate_pool.ranked_bullets
            experience_packages = self._experience_packages(profile, bullets)
            skills = self._rank_skills(profile, context, bullets)
        search_started = self._telemetry.clock()
        bullet_by_id = {candidate.evidence_id: candidate for candidate in bullets}
        skill_by_id = {candidate.category_id: candidate for candidate in skills}
        iterations: list[PageFillIterationDiagnostic] = []
        overflow_sources: dict[str, float] = {}
        redundancy_by_source: dict[str, float] = {}
        bound_excluded_sources = {
            candidate.evidence_id for candidate in candidate_pool.ranking_bound_excluded_bullets
        }
        bound_exclusion_reasons = {
            candidate.evidence_id: (
                f"maximum_ranked_bullets={self._bounds.maximum_ranked_bullets}"
            )
            for candidate in candidate_pool.ranking_bound_excluded_bullets
        }
        evaluated_candidate_sources: set[str] = set()
        verification_failure: str | None = None
        estimated_evaluations = 0
        exact_evaluations = 0
        expansion_operations = 0
        best_estimated_utilization = 0.0
        best_exact_utilization: float | None = None
        completion_reserve = min(
            64,
            max(24, self._bounds.maximum_estimated_page_evaluations // 2),
        )
        exploration_evaluation_limit = max(
            1,
            self._bounds.maximum_estimated_page_evaluations - completion_reserve,
        )

        def evaluate_state(
            state: _State,
            candidate_id: str,
            source_id: str,
            *,
            attempt_exact: bool,
            evaluation_override: PageFitEvaluation | None = None,
        ) -> _EvaluatedState:
            nonlocal best_estimated_utilization
            nonlocal best_exact_utilization
            nonlocal estimated_evaluations
            nonlocal exact_evaluations
            nonlocal verification_failure
            resume = self._resume_for_state(
                baseline,
                profile,
                state,
                bullet_by_id,
                skill_by_id,
            )
            evaluation = evaluation_override or self._page_fit_evaluator.evaluate(
                resume,
                attempt_exact=attempt_exact,
            )
            if attempt_exact:
                exact_evaluations += 1
            else:
                estimated_evaluations += 1
            verification_failure = verification_failure or evaluation.verification_failure
            overflow = not evaluation.fits_one_page
            if overflow:
                overflow_sources[source_id] = max(
                    overflow_sources.get(source_id, 0),
                    evaluation.utilization_ratio,
                )
            elif evaluation.exact:
                best_exact_utilization = max(
                    best_exact_utilization or 0.0,
                    evaluation.utilization_ratio,
                )
            else:
                best_estimated_utilization = max(
                    best_estimated_utilization,
                    evaluation.utilization_ratio,
                )
            iteration_number = estimated_evaluations + exact_evaluations
            iterations.append(
                PageFillIterationDiagnostic(
                    iteration=iteration_number,
                    candidate_id=candidate_id,
                    accepted=evaluation.fits_one_page,
                    overflow=overflow,
                    utilization_ratio=evaluation.utilization_ratio,
                    exact_page_verification=evaluation.exact,
                    reason=(
                        "Retained as an estimated one-page search state."
                        if evaluation.fits_one_page and not attempt_exact
                        else "Accepted after authoritative exact one-page pagination."
                        if evaluation.fits_one_page and evaluation.exact
                        else "Exact pagination was unavailable; retained the typed estimate."
                        if evaluation.fits_one_page
                        else "Rolled back because the rendered candidate exceeded one page."
                    ),
                )
            )
            coverage = self._state_coverage(state, bullet_by_id, skill_by_id)
            return _EvaluatedState(
                state=state,
                resume=resume,
                evaluation=evaluation,
                quality=self._state_quality(
                    state,
                    profile,
                    bullet_by_id,
                    skill_by_id,
                ),
                coverage_count=len(coverage),
                three_line_bullet_count=sum(
                    bullet_by_id[evidence_id].line_fit.three_line_risk
                    for evidence_id in state.bullet_ids
                ),
                substantive_project_count=sum(
                    count >= 2
                    for count in Counter(
                        bullet_by_id[evidence_id].entry_id
                        for evidence_id in state.bullet_ids
                        if bullet_by_id[evidence_id].entry_kind is EntityKind.PROJECT
                    ).values()
                ),
            )

        seed_states: list[tuple[_State, str]] = []
        if bullets:
            seed_bullets = list(bullets[: self._bounds.beam_width])
            for requirement in context.requirements.requirements:
                if requirement.authority not in {
                    RequirementAuthority.CORE,
                    RequirementAuthority.IMPORTANT,
                }:
                    continue
                requirement_bullet = next(
                    (
                        candidate
                        for candidate in bullets
                        if requirement.id in candidate.direct_requirement_ids
                    ),
                    None,
                )
                if requirement_bullet is None:
                    continue
                if requirement_bullet not in seed_bullets:
                    seed_bullets.append(requirement_bullet)
            seeded_project_entries: set[str] = set()
            for project_bullet in bullets:
                if project_bullet.entry_kind is not EntityKind.PROJECT:
                    continue
                if project_bullet.entry_id in seeded_project_entries:
                    continue
                seeded_project_entries.add(project_bullet.entry_id)
                if project_bullet not in seed_bullets:
                    seed_bullets.append(project_bullet)
            seed_bullet_groups: list[tuple[frozenset[str], str]] = []
            seen_seed_groups: set[frozenset[str]] = set()
            for bullet in seed_bullets:
                groups = (
                    [
                        (frozenset(package.bullet_ids), package.package_id)
                        for package in experience_packages.get(bullet.entry_id, [])[:2]
                    ]
                    if bullet.entry_kind is EntityKind.EXPERIENCE
                    else [(frozenset({bullet.evidence_id}), bullet.evidence_id)]
                )
                for bullet_ids, source_id in groups:
                    if bullet_ids in seen_seed_groups:
                        continue
                    seen_seed_groups.add(bullet_ids)
                    seed_bullet_groups.append((bullet_ids, source_id))
            for bullet_ids, source_id in seed_bullet_groups:
                supported_skills = [
                    candidate.category_id
                    for candidate in skills
                    if any(
                        _contains_phrase(
                            _normalize(
                                " ".join(bullet_by_id[item].text for item in bullet_ids)
                            ),
                            _normalize(skill.value),
                        )
                        for skill in candidate.category.skills
                    )
                ]
                credible_skill_ids = [
                    item.category_id
                    for item in skills
                    if item.relationship
                    in {
                        EvidenceRelationship.DIRECT,
                        EvidenceRelationship.ADJACENT,
                        EvidenceRelationship.COMPLEMENTARY,
                    }
                    or item.category_id in supported_skills
                    or item.supported_skill_ids
                ][: min(3, constraints.max_skill_lines)]
                seed_skill_counts = list(dict.fromkeys([len(credible_skill_ids), 0]))
                for skill_count in seed_skill_counts:
                    skill_ids = frozenset(credible_skill_ids[:skill_count])
                    state = _State(bullet_ids, skill_ids)
                    if self._within_planning_bounds(
                        state,
                        profile,
                        bullet_by_id,
                        constraints,
                    ):
                        seed_states.append((state, source_id))
        else:
            seed_states.append((_State(frozenset(), frozenset()), "mandatory-base"))

        evaluated_states: list[_EvaluatedState] = []
        visited: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
        for state, source_id in seed_states:
            if estimated_evaluations >= exploration_evaluation_limit:
                break
            if state.key in visited:
                continue
            visited.add(state.key)
            evaluated_candidate_sources.add(source_id)
            evaluated = evaluate_state(
                state,
                f"base-entry:{source_id}",
                source_id,
                attempt_exact=False,
            )
            if evaluated.evaluation.fits_one_page:
                evaluated_states.append(evaluated)

        if not evaluated_states:
            fallback = evaluate_state(
                _State(frozenset(), frozenset()),
                "mandatory-base",
                "mandatory-base",
                attempt_exact=False,
            )
            evaluated_states.append(fallback)

        frontier = self._search_states(evaluated_states)
        project_seed_by_entry: dict[str, _EvaluatedState] = {}
        requirement_seed_by_id: dict[str, _EvaluatedState] = {}
        for item in evaluated_states:
            selected_candidates = [
                bullet_by_id[evidence_id] for evidence_id in item.state.bullet_ids
            ]
            for requirement_id in {
                requirement_id
                for candidate in selected_candidates
                for requirement_id in candidate.direct_requirement_ids
            }:
                previous = requirement_seed_by_id.get(requirement_id)
                if previous is None or item.quality > previous.quality:
                    requirement_seed_by_id[requirement_id] = item
            project_entry_ids = {
                bullet_by_id[evidence_id].entry_id
                for evidence_id in item.state.bullet_ids
                if bullet_by_id[evidence_id].entry_kind is EntityKind.PROJECT
            }
            for entry_id in project_entry_ids:
                previous = project_seed_by_entry.get(entry_id)
                if previous is None or item.quality > previous.quality:
                    project_seed_by_entry[entry_id] = item
        reserved_project_frontier = sorted(
            project_seed_by_entry.values(),
            key=lambda item: (-item.quality, item.state.key),
        )[: self._bounds.maximum_project_entries]
        reserved_requirement_frontier = [
            requirement_seed_by_id[requirement.id]
            for requirement in context.requirements.requirements
            if requirement.id in requirement_seed_by_id
            and requirement.authority in {RequirementAuthority.CORE, RequirementAuthority.IMPORTANT}
        ]
        reserved_frontier: list[_EvaluatedState] = []
        reserved_state_keys: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
        for item in [
            *reserved_requirement_frontier,
            *reserved_project_frontier,
        ]:
            if item.state.key in reserved_state_keys:
                continue
            reserved_state_keys.add(item.state.key)
            reserved_frontier.append(item)
        frontier = [
            *reserved_frontier,
            *[item for item in frontier if item not in reserved_frontier],
        ][: self._bounds.beam_width]
        all_fitting = list(evaluated_states)
        expanded: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
        termination_reason = (
            CompositionTerminationReason.NO_RELEVANT_EVIDENCE
            if not bullets
            else CompositionTerminationReason.FRONTIER_EXHAUSTED
        )
        while bullets and frontier:
            target_states = [
                item
                for item in all_fitting
                if self._in_automatic_completion_band(
                    item.evaluation.utilization_ratio
                )
            ]
            target_has_substantive_project = any(
                self._state_has_substantive_project(item.state, bullet_by_id)
                for item in target_states
            )
            if len(target_states) >= self._bounds.target_finalist_count and (
                not self._credible_project_ids(bullets) or target_has_substantive_project
            ):
                termination_reason = CompositionTerminationReason.TARGET_FINALISTS_FOUND
                break
            if estimated_evaluations >= exploration_evaluation_limit:
                termination_reason = CompositionTerminationReason.ESTIMATED_EVALUATION_LIMIT
                break
            if expansion_operations >= self._bounds.maximum_expansion_operations:
                termination_reason = CompositionTerminationReason.EXPANSION_OPERATION_LIMIT
                break
            current = frontier.pop(0)
            if current.state.key in expanded:
                continue
            expanded.add(current.state.key)
            options = self._expansions(
                current.state,
                profile,
                bullets,
                experience_packages,
                skills,
                bullet_by_id,
                skill_by_id,
                constraints,
                redundancy_by_source,
            )
            remaining_operation_budget = (
                self._bounds.maximum_expansion_operations - expansion_operations
            )
            if len(options) > remaining_operation_budget:
                bound_excluded_sources.update(
                    item.source_id for item in options[remaining_operation_budget:]
                )
                for bounded_option in options[remaining_operation_budget:]:
                    bound_exclusion_reasons.setdefault(
                        bounded_option.source_id,
                        f"maximum_expansion_operations={self._bounds.maximum_expansion_operations}",
                    )
                options = options[:remaining_operation_budget]
                termination_reason = CompositionTerminationReason.EXPANSION_OPERATION_LIMIT
            expansion_operations += len(options)
            if len(options) > self._bounds.maximum_expansions_per_state:
                bound_excluded_sources.update(
                    item.source_id for item in options[self._bounds.maximum_expansions_per_state :]
                )
                for bounded_option in options[self._bounds.maximum_expansions_per_state :]:
                    bound_exclusion_reasons.setdefault(
                        bounded_option.source_id,
                        "maximum_expansions_per_state="
                        f"{self._bounds.maximum_expansions_per_state}",
                    )
                options = options[: self._bounds.maximum_expansions_per_state]
            next_states: list[_EvaluatedState] = []
            for option_index, expansion in enumerate(options):
                if estimated_evaluations >= exploration_evaluation_limit:
                    bound_excluded_sources.update(item.source_id for item in options[option_index:])
                    for bounded_option in options[option_index:]:
                        bound_exclusion_reasons.setdefault(
                            bounded_option.source_id,
                            f"exploration_evaluation_limit={exploration_evaluation_limit}",
                        )
                    termination_reason = CompositionTerminationReason.ESTIMATED_EVALUATION_LIMIT
                    break
                if expansion.state.key in visited:
                    continue
                visited.add(expansion.state.key)
                evaluated_candidate_sources.add(expansion.source_id)
                evaluated = evaluate_state(
                    expansion.state,
                    expansion.candidate_id,
                    expansion.source_id,
                    attempt_exact=False,
                )
                if evaluated.evaluation.fits_one_page:
                    next_states.append(evaluated)
                    all_fitting.append(evaluated)
            frontier = self._search_states([*frontier, *next_states])
            if termination_reason in {
                CompositionTerminationReason.ESTIMATED_EVALUATION_LIMIT,
                CompositionTerminationReason.EXPANSION_OPERATION_LIMIT,
            }:
                break

        # Reserve a bounded second stage for progressive completion. The beam
        # compares alternatives well, but a large profile can otherwise spend
        # the whole evaluation budget exploring shallow siblings and turn a
        # computation bound into an accidental content-count limit.
        completion_current = self._best_states(
            all_fitting,
            limit=len(all_fitting),
        )[0]
        if termination_reason is CompositionTerminationReason.ESTIMATED_EVALUATION_LIMIT:
            termination_reason = CompositionTerminationReason.FRONTIER_EXHAUSTED
        completion_processed_sources: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
        while (
            bullets
            and estimated_evaluations < self._bounds.maximum_estimated_page_evaluations
            and expansion_operations < self._bounds.maximum_expansion_operations
        ):
            preferred_states = [
                item
                for item in all_fitting
                if self._in_automatic_completion_band(
                    item.evaluation.utilization_ratio
                )
            ]
            substantive_preferred_states = [
                item
                for item in preferred_states
                if self._state_has_substantive_project(item.state, bullet_by_id)
            ]
            if preferred_states and (
                not self._credible_project_ids(bullets) or substantive_preferred_states
            ):
                completion_current = self._best_states(
                    substantive_preferred_states or preferred_states,
                    limit=len(substantive_preferred_states or preferred_states),
                )[0]
                break
            completion_options: list[_Expansion] = []
            completion_sources = [
                completion_current,
                *sorted(
                    all_fitting,
                    key=lambda item: (
                        -item.evaluation.utilization_ratio,
                        -item.coverage_count,
                        -item.quality,
                        -len(item.state.bullet_ids),
                        item.state.key,
                    ),
                ),
            ]
            checked_completion_states: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
            for completion_source in completion_sources:
                if (
                    completion_source.state.key in checked_completion_states
                    or completion_source.state.key in completion_processed_sources
                ):
                    continue
                checked_completion_states.add(completion_source.state.key)
                completion_processed_sources.add(completion_source.state.key)
                traversable_options = self._expansions(
                    completion_source.state,
                    profile,
                    bullets,
                    experience_packages,
                    skills,
                    bullet_by_id,
                    skill_by_id,
                    constraints,
                    redundancy_by_source,
                )
                if traversable_options:
                    completion_current = completion_source
                    completion_options = traversable_options
                    break
            if not completion_options:
                break
            remaining_operation_budget = (
                self._bounds.maximum_expansion_operations - expansion_operations
            )
            bounded_completion_options: list[_Expansion] = []
            novel_operation_count = 0
            for option in completion_options:
                is_novel = option.state.key not in visited
                if is_novel and novel_operation_count >= remaining_operation_budget:
                    bound_excluded_sources.add(option.source_id)
                    bound_exclusion_reasons.setdefault(
                        option.source_id,
                        f"maximum_expansion_operations={self._bounds.maximum_expansion_operations}",
                    )
                    continue
                bounded_completion_options.append(option)
                if is_novel:
                    novel_operation_count += 1
            completion_options = bounded_completion_options
            expansion_operations += novel_operation_count
            if len(completion_options) > self._bounds.maximum_expansions_per_state:
                bound_excluded_sources.update(
                    item.source_id
                    for item in completion_options[self._bounds.maximum_expansions_per_state :]
                )
                for bounded_option in completion_options[
                    self._bounds.maximum_expansions_per_state :
                ]:
                    bound_exclusion_reasons.setdefault(
                        bounded_option.source_id,
                        "maximum_expansions_per_state="
                        f"{self._bounds.maximum_expansions_per_state}",
                    )
                completion_options = completion_options[: self._bounds.maximum_expansions_per_state]
            completion_fitting: list[_EvaluatedState] = []
            for option_index, expansion in enumerate(completion_options):
                previously_evaluated = next(
                    (item for item in all_fitting if item.state.key == expansion.state.key),
                    None,
                )
                if previously_evaluated is not None:
                    completion_fitting.append(previously_evaluated)
                    break
                if estimated_evaluations >= self._bounds.maximum_estimated_page_evaluations:
                    bound_excluded_sources.update(
                        item.source_id for item in completion_options[option_index:]
                    )
                    for bounded_option in completion_options[option_index:]:
                        bound_exclusion_reasons.setdefault(
                            bounded_option.source_id,
                            "maximum_estimated_page_evaluations="
                            f"{self._bounds.maximum_estimated_page_evaluations}",
                        )
                    termination_reason = CompositionTerminationReason.ESTIMATED_EVALUATION_LIMIT
                    break
                visited.add(expansion.state.key)
                evaluated_candidate_sources.add(expansion.source_id)
                evaluated = evaluate_state(
                    expansion.state,
                    f"completion:{expansion.candidate_id}",
                    expansion.source_id,
                    attempt_exact=False,
                )
                if evaluated.evaluation.fits_one_page:
                    completion_fitting.append(evaluated)
                    all_fitting.append(evaluated)
                    # The beam stage already compared shallow alternatives. This
                    # completion lane deliberately spends one successful render
                    # per content step so the reserved budget can deepen a strong
                    # coherent plan. Overflow still falls through to the next
                    # bounded option and is rolled back normally.
                    break
            if not completion_fitting:
                break
            completion_current = self._best_states(
                completion_fitting,
                limit=len(completion_fitting),
            )[0]
        if self._in_automatic_completion_band(
            completion_current.evaluation.utilization_ratio
        ):
            termination_reason = CompositionTerminationReason.TARGET_FINALISTS_FOUND
        elif estimated_evaluations >= self._bounds.maximum_estimated_page_evaluations:
            termination_reason = CompositionTerminationReason.ESTIMATED_EVALUATION_LIMIT

        ordered_fitting = self._best_states(all_fitting, limit=len(all_fitting))
        target_finalists = [
            item
            for item in ordered_fitting
            if self._in_automatic_completion_band(
                item.evaluation.utilization_ratio
            )
        ]
        underfilled_finalists = [item for item in ordered_fitting if item not in target_finalists]
        preferred_target_count = min(
            len(target_finalists),
            max(1, self._bounds.maximum_exact_finalist_evaluations // 4),
        )
        finalists = target_finalists[:preferred_target_count]
        substantive_project_states = [
            item
            for item in ordered_fitting
            if any(
                count >= 2
                for count in Counter(
                    bullet_by_id[evidence_id].entry_id
                    for evidence_id in item.state.bullet_ids
                    if bullet_by_id[evidence_id].entry_kind is EntityKind.PROJECT
                ).values()
            )
        ]
        if substantive_project_states:
            for density_target in (0.90, 0.82, 0.74):
                substantive_project_finalist = min(
                    substantive_project_states,
                    key=lambda item: (
                        abs(item.evaluation.utilization_ratio - density_target),
                        -item.quality,
                        item.state.key,
                    ),
                )
                if substantive_project_finalist not in finalists:
                    finalists.append(substantive_project_finalist)
        # Exact pagination can place the fit boundary below the estimator's
        # preferred band. Preserve deterministic density diversity so deep
        # completion states do not crowd every lower-density rollback candidate
        # out of the bounded authoritative finalist set.
        for density_target in (
            0.95,
            0.92,
            0.90,
            0.87,
            0.84,
            0.80,
            0.75,
            0.70,
            0.65,
            0.60,
            0.55,
            0.50,
        ):
            if len(finalists) >= self._bounds.maximum_exact_finalist_evaluations:
                break
            closest = min(
                ordered_fitting,
                key=lambda item: (
                    abs(item.evaluation.utilization_ratio - density_target),
                    -item.quality,
                    item.state.key,
                ),
            )
            if closest not in finalists:
                finalists.append(closest)
        remaining_slots = self._bounds.maximum_exact_finalist_evaluations - len(finalists)
        if underfilled_finalists and remaining_slots:
            denominator = max(1, remaining_slots - 1)
            last_index = len(underfilled_finalists) - 1
            for slot in range(remaining_slots):
                index = round(slot * last_index / denominator)
                underfilled_candidate = underfilled_finalists[index]
                if underfilled_candidate not in finalists:
                    finalists.append(underfilled_candidate)
        for item in ordered_fitting:
            if len(finalists) >= self._bounds.maximum_exact_finalist_evaluations:
                break
            if item not in finalists:
                finalists.append(item)
        sparsest_fitting = min(
            ordered_fitting,
            key=lambda item: (
                item.evaluation.utilization_ratio,
                len(item.state.bullet_ids),
                len(item.state.skill_category_ids),
                item.state.key,
            ),
        )
        if sparsest_fitting not in finalists:
            if len(finalists) >= self._bounds.maximum_exact_finalist_evaluations:
                finalists[-1] = sparsest_fitting
            else:
                finalists.append(sparsest_fitting)

        final = ordered_fitting[0]
        exact_provider_available = attempt_exact_final
        exact_one_page_found = False
        last_exact_candidate: _EvaluatedState | None = None
        exact_fitting_candidates: list[_EvaluatedState] = []
        if attempt_exact_final:
            batch_method = getattr(self._page_fit_evaluator, "evaluate_batch", None)
            batch_evaluations = (
                batch_method(
                    [
                        self._resume_for_state(
                            baseline,
                            profile,
                            finalist.state,
                            bullet_by_id,
                            skill_by_id,
                        )
                        for finalist in finalists
                    ]
                )
                if callable(batch_method)
                else [None] * len(finalists)
            )
            for finalist_index, (finalist, batch_evaluation) in enumerate(
                zip(finalists, batch_evaluations, strict=True),
                start=1,
            ):
                exact_candidate = evaluate_state(
                    finalist.state,
                    f"exact-finalist:{finalist_index}",
                    f"exact-finalist:{finalist_index}",
                    attempt_exact=True,
                    evaluation_override=cast(
                        PageFitEvaluation | None,
                        batch_evaluation,
                    ),
                )
                if not exact_candidate.evaluation.exact:
                    exact_provider_available = False
                    break
                last_exact_candidate = exact_candidate
                if (
                    exact_candidate.evaluation.fits_one_page
                    and exact_candidate.evaluation.page_count == 1
                ):
                    exact_one_page_found = True
                    exact_fitting_candidates.append(exact_candidate)
        if exact_fitting_candidates:
            final = self._best_states(
                exact_fitting_candidates,
                limit=len(exact_fitting_candidates),
            )[0]
        elif not exact_provider_available:
            # When Word/LibreOffice is unavailable, keep the strongest
            # deterministic one-page finalist in the preferred density band
            # instead of retaining a sparse state chosen only by the exact
            # verification lane.  The estimate remains explicitly marked as
            # unverified; it never relaxes overflow or grounding rules.
            estimated_preferred = [
                item
                for item in ordered_fitting
                if self._in_preferred_density_band(item.evaluation.utilization_ratio)
                or (
                    item.evaluation.utilization_ratio
                    >= TEMPLATE_V1_PREFERRED_DENSITY_FLOOR
                    and item.evaluation.utilization_ratio
                    <= TEMPLATE_V1_ACCEPTABLE_DENSITY_CEILING
                )
            ]
            if estimated_preferred:
                final = self._best_states(
                    estimated_preferred,
                    limit=len(estimated_preferred),
                )[0]
        if exact_provider_available and not exact_one_page_found:
            termination_reason = CompositionTerminationReason.ALL_ADMISSIBLE_CANDIDATES_OVERFLOWED
            if last_exact_candidate is not None:
                final = last_exact_candidate

        final_content_bound_sources: set[str] = set()
        for candidate in bullets:
            if candidate.evidence_id in final.state.bullet_ids:
                continue
            penalty, duplicate = self._redundancy_penalty(
                candidate,
                final.state,
                bullet_by_id,
            )
            selected_entries = {bullet_by_id[item].entry_id for item in final.state.bullet_ids}
            if (
                candidate.entry_kind is EntityKind.EXPERIENCE
                and candidate.entry_id not in selected_entries
            ):
                continue
            opening_penalty = 6.0 if candidate.entry_id not in selected_entries else 0.0
            if (
                not duplicate
                and candidate.score - penalty - opening_penalty >= self._minimum_marginal_score
                and not self._within_planning_bounds(
                    _State(
                        final.state.bullet_ids | {candidate.evidence_id},
                        final.state.skill_category_ids,
                    ),
                    profile,
                    bullet_by_id,
                    constraints,
                )
            ):
                final_content_bound_sources.add(candidate.evidence_id)
                bound_exclusion_reasons[candidate.evidence_id] = (
                    self._planning_bound_reason(
                        _State(
                            final.state.bullet_ids | {candidate.evidence_id},
                            final.state.skill_category_ids,
                        ),
                        profile,
                        bullet_by_id,
                        constraints,
                    )
                )
        final_admissible_sources = {
            expansion.source_id
            for expansion in self._expansions(
                final.state,
                profile,
                bullets,
                experience_packages,
                skills,
                bullet_by_id,
                skill_by_id,
                constraints,
                redundancy_by_source,
            )
        }
        final_bound_excluded_sources = (
            (bound_excluded_sources - evaluated_candidate_sources) & final_admissible_sources
        ) | final_content_bound_sources
        additional_evidence_unavailable = (
            not self._has_admissible_expansion(
                final.state,
                profile,
                bullets,
                experience_packages,
                skills,
                bullet_by_id,
                skill_by_id,
                constraints,
                redundancy_by_source,
            )
            and not candidate_pool.ranking_bound_excluded_bullets
            and not (final_bound_excluded_sources)
        )
        outcome, reason = self._outcome(final, additional_evidence_unavailable)
        diagnostic = self._diagnostic(
            final,
            profile,
            context,
            candidate_pool,
            bullets,
            experience_packages,
            skills,
            iterations,
            overflow_sources,
            redundancy_by_source,
            verification_failure,
            termination_reason=termination_reason,
            bound_excluded_sources=final_bound_excluded_sources,
            bound_exclusion_reasons={
                source_id: bound_exclusion_reasons[source_id]
                for source_id in final_bound_excluded_sources
                if source_id in bound_exclusion_reasons
            },
            best_estimated_utilization=best_estimated_utilization,
            best_exact_utilization=best_exact_utilization,
            estimated_evaluations=estimated_evaluations,
            exact_evaluations=exact_evaluations,
            expansion_operations=expansion_operations,
            constraints=constraints,
            additional_evidence_unavailable=additional_evidence_unavailable,
            outcome=outcome,
            reason=reason,
            baseline_selected_entry_ids=(
                {
                    *baseline.composition_diagnostic.selected_experience_ids,
                    *baseline.composition_diagnostic.selected_project_ids,
                }
                if available_variants and baseline.composition_diagnostic is not None
                else None
            ),
        )
        result = final.resume.model_copy(update={"composition_diagnostic": diagnostic})
        self._telemetry.record(
            GenerationStage.PORTFOLIO_PAGE_FIT_SEARCH,
            self._telemetry.clock() - search_started,
        )
        return result

    def _candidate_pool(
        self,
        profile: MasterProfile,
        context: _PostingContext,
        variants: dict[str, list[BulletVariantRecord]] | None = None,
        advisory_evidence_ids: set[str] | None = None,
    ) -> _CandidatePool:
        candidates = self._all_bullet_candidates(
            profile,
            context,
            variants or {},
            advisory_evidence_ids or set(),
        )
        preliminary_relevant = [
            candidate
            for candidate in candidates
            if candidate.admitted
            if candidate.score >= self._minimum_bullet_score and candidate.coverage_keys
        ]
        relevant: list[_BulletCandidate] = []
        redundancy_excluded: list[_BulletCandidate] = []
        for candidate in preliminary_relevant:
            stronger_duplicate = next(
                (
                    retained
                    for retained in relevant
                    if retained.entry_id == candidate.entry_id
                    and _near_duplicate(retained.text, candidate.text)
                    >= self._near_duplicate_threshold
                ),
                None,
            )
            if stronger_duplicate is not None:
                redundancy_excluded.append(candidate)
                continue
            relevant.append(candidate)
        relevance_excluded = [
            candidate for candidate in candidates if candidate not in preliminary_relevant
        ]
        return _CandidatePool(
            ranked_bullets=relevant[: self._bounds.maximum_ranked_bullets],
            relevance_excluded_bullets=relevance_excluded,
            redundancy_excluded_bullets=redundancy_excluded,
            ranking_bound_excluded_bullets=relevant[self._bounds.maximum_ranked_bullets :],
        )

    def _rank_bullets(
        self,
        profile: MasterProfile,
        context: _PostingContext,
    ) -> list[_BulletCandidate]:
        return self._candidate_pool(profile, context).ranked_bullets

    def _all_bullet_candidates(
        self,
        profile: MasterProfile,
        context: _PostingContext,
        variants: dict[str, list[BulletVariantRecord]] | None = None,
        advisory_evidence_ids: set[str] | None = None,
    ) -> list[_BulletCandidate]:
        entries = [*profile.experiences, *profile.projects]
        entry_by_id = {entry.id: entry for entry in entries}
        entry_order = {entry.id: index for index, entry in enumerate(entries)}
        latest_year = max(
            (
                year
                for entry in entries
                for value in (entry.start_date, entry.end_date)
                for year in _years(value)
            ),
            default=0,
        )
        resolved_variants = variants or {}
        evidence_by_id = {item.id: item for item in profile.evidence if item.confirmed}
        resolved_advisory_ids = advisory_evidence_ids or set()
        preferred_candidates: dict[str, _BulletCandidate] = {}
        for evidence_order, evidence in enumerate(profile.evidence):
            entry = entry_by_id.get(evidence.entity_id)
            if not evidence.confirmed or entry is None:
                continue
            options = [
                self._bullet_candidate(
                    evidence,
                    entry,
                    context,
                    latest_year,
                    entry_order[entry.id],
                    evidence_order,
                    writing_variant=None,
                    advisory=evidence.id in resolved_advisory_ids,
                    evidence_by_id=evidence_by_id,
                ),
                *[
                    self._bullet_candidate(
                        evidence,
                        entry,
                        context,
                        latest_year,
                        entry_order[entry.id],
                        evidence_order,
                        writing_variant=variant,
                        advisory=evidence.id in resolved_advisory_ids,
                        evidence_by_id=evidence_by_id,
                    )
                    for variant in resolved_variants.get(evidence.id, [])
                ],
            ]
            explicitly_approved = [
                candidate
                for candidate in options[1:]
                if candidate.writing_variant is not None
                and candidate.writing_variant.selection_reason
                == "Explicitly approved by the user for this rebuilt artifact."
            ]
            preferred = max(
                explicitly_approved or options,
                key=_source_versus_rewrite_key,
            )
            if explicitly_approved:
                source = options[0]
                # User approval governs wording, while the reviewed source
                # remains the authority for relevance and requirement
                # attribution. This prevents a harmless paraphrase from
                # disappearing merely because its surface tokens score below
                # the source it faithfully represents.
                preferred = replace(
                    preferred,
                    score=max(preferred.score, source.score),
                    contextual_relevance=source.contextual_relevance,
                    intrinsic_evidence_strength=source.intrinsic_evidence_strength,
                    coverage_keys=source.coverage_keys,
                    coverage_labels=source.coverage_labels,
                    meaningful_overlap=source.meaningful_overlap,
                    generic_only_rejected=source.generic_only_rejected,
                    admitted=source.admitted,
                    admission_reason=source.admission_reason,
                    relationship=source.relationship,
                    direct_requirement_ids=source.direct_requirement_ids,
                    adjacent_requirement_ids=source.adjacent_requirement_ids,
                    complementary_requirement_ids=source.complementary_requirement_ids,
                    incidental_requirement_ids=source.incidental_requirement_ids,
                    short_token_contributions=source.short_token_contributions,
                )
            preferred_candidates[evidence.id] = replace(
                preferred,
                source_alternative_score=options[0].score,
            )
        consumed_secondary_evidence_ids = {
            evidence_id
            for candidate in preferred_candidates.values()
            if candidate.writing_variant is not None
            for evidence_id in candidate.source_evidence_ids[1:]
        }
        candidates: list[_BulletCandidate] = []
        for evidence in profile.evidence:
            if evidence.id in consumed_secondary_evidence_ids:
                continue
            candidate = preferred_candidates.get(evidence.id)
            if candidate is None:
                continue
            candidates.append(candidate)
        candidates.sort(
            key=lambda item: (
                -item.score,
                item.entry_order,
                item.evidence_order,
                item.evidence_id,
            )
        )
        return candidates

    def _experience_packages(
        self,
        profile: MasterProfile,
        bullets: list[_BulletCandidate],
    ) -> dict[str, list[_ExperiencePackage]]:
        """Build a bounded set of coherent source/rewrite packages per experience."""

        entry_by_id = {entry.id: entry for entry in profile.experiences}
        latest_year = max(
            (
                year
                for entry in profile.experiences
                for value in (entry.start_date, entry.end_date)
                for year in _years(value)
            ),
            default=0,
        )
        bullets_by_entry: dict[str, list[_BulletCandidate]] = {}
        for bullet in bullets:
            if bullet.entry_kind is EntityKind.EXPERIENCE:
                bullets_by_entry.setdefault(bullet.entry_id, []).append(bullet)
        packages_by_entry: dict[str, list[_ExperiencePackage]] = {}
        for entry_id, entry_bullets in bullets_by_entry.items():
            entry = entry_by_id.get(entry_id)
            if entry is None:
                continue
            alternatives: dict[tuple[str, ...], _ExperiencePackage] = {}
            if len(entry_bullets) == 1:
                reason = self._single_bullet_exception_reason(
                    entry_bullets[0],
                    {item.evidence_id: item for item in bullets},
                )
                if reason is not None:
                    package = self._score_experience_package(
                        entry,
                        entry_bullets,
                        latest_year,
                        single_bullet_exception_reason=reason,
                    )
                    alternatives[package.bullet_ids] = package
            else:
                pool = entry_bullets[:6]
                for anchor in pool[:3]:
                    selected = [anchor]
                    remaining = [item for item in pool if item.evidence_id != anchor.evidence_id]
                    while remaining and len(selected) < 4:
                        ranked_remaining = sorted(
                            remaining,
                            key=lambda candidate: (
                                -self._package_companion_value(candidate, selected),
                                candidate.evidence_order,
                                candidate.evidence_id,
                            ),
                        )
                        companion = ranked_remaining[0]
                        if self._package_companion_value(companion, selected) < (
                            self._minimum_marginal_score
                        ):
                            break
                        selected.append(companion)
                        remaining.remove(companion)
                        if len(selected) >= 2:
                            package = self._score_experience_package(
                                entry,
                                selected,
                                latest_year,
                            )
                            alternatives.setdefault(package.bullet_ids, package)
            ordered = sorted(
                alternatives.values(),
                key=lambda package: (
                    -package.total_score,
                    -len(package.bullet_ids),
                    package.bullet_ids,
                ),
            )
            if ordered:
                packages_by_entry[entry_id] = ordered[:6]
        return packages_by_entry

    def _package_companion_value(
        self,
        candidate: _BulletCandidate,
        selected: list[_BulletCandidate],
    ) -> float:
        selected_coverage = {key for item in selected for key in item.coverage_keys}
        selected_features = {feature for item in selected for feature in item.normalized_features}
        distinct_coverage = len(set(candidate.coverage_keys) - selected_coverage)
        distinct_features = len(set(candidate.normalized_features) - selected_features)
        similarity = max(
            (_near_duplicate(candidate.text, item.text) for item in selected),
            default=0.0,
        )
        return (
            candidate.score
            + (distinct_coverage * 8.0)
            + (min(4, distinct_features) * 2.0)
            - (candidate.score * similarity * 0.55)
        )

    def _score_experience_package(
        self,
        entry: ResumeItem,
        bullets: list[_BulletCandidate],
        latest_year: int,
        *,
        single_bullet_exception_reason: ExperienceSingleBulletExceptionReason | None = None,
    ) -> _ExperiencePackage:
        ordered = sorted(bullets, key=lambda item: (item.evidence_order, item.evidence_id))
        coverage = sorted({key for item in ordered for key in item.coverage_keys})
        redundancy_penalty = 0.0
        for index, candidate in enumerate(ordered):
            for other in ordered[index + 1 :]:
                similarity = _near_duplicate(candidate.text, other.text)
                repeated = len(set(candidate.coverage_keys) & set(other.coverage_keys))
                redundancy_penalty += (
                    min(candidate.score, other.score) * similarity * 0.18
                ) + (repeated * 2.0)
        reviewed_context = " ".join(
            [
                entry.title,
                entry.subtitle or "",
                entry.description or "",
                *entry.technologies,
                *entry.capabilities,
                *[item.text for item in ordered],
            ]
        ).casefold()
        enterprise_evidence = tuple(
            sorted(
                signal
                for signal in _ENTERPRISE_PRODUCTION_SIGNALS
                if re.search(rf"\b{re.escape(signal)}\b", reviewed_context)
            )
        )
        enterprise_contribution = min(3.0, len(enterprise_evidence) * 0.75)
        duration_recency = min(
            6.0,
            _duration_score(entry, latest_year) + _recency_score(entry, latest_year),
        )
        seniority_contribution = _reviewed_seniority_score(entry.title)
        writing_quality = sum(
            max(0.0, item.writing_adjustment)
            for item in ordered
            if item.writing_variant is not None
        )
        page_cost = 2.0 + sum(item.line_fit.total_vertical_line_cost for item in ordered)
        depth_bonus = 5.0 if len(ordered) == 3 else 3.0 if len(ordered) >= 4 else 0.0
        ranked_bullet_scores = sorted((item.score for item in ordered), reverse=True)
        weighted_bullet_score = sum(
            score * weight
            for score, weight in zip(
                ranked_bullet_scores,
                (1.0, 0.75, 0.35, 0.15),
                strict=False,
            )
        )
        total_score = (
            weighted_bullet_score
            + (len(coverage) * 5.0)
            + writing_quality
            + duration_recency
            + enterprise_contribution
            + seniority_contribution
            + depth_bonus
            - redundancy_penalty
            - (page_cost * 0.4)
            - (8.0 if single_bullet_exception_reason is not None else 0.0)
        )
        bullet_ids = tuple(item.evidence_id for item in ordered)
        return _ExperiencePackage(
            package_id=f"experience-package:{entry.id}:{'-'.join(bullet_ids)}",
            entry_id=entry.id,
            bullet_ids=bullet_ids,
            source_evidence_ids=tuple(
                dict.fromkeys(
                    source_id for item in ordered for source_id in item.source_evidence_ids
                )
            ),
            package_relevance=round(sum(item.contextual_relevance for item in ordered), 2),
            intrinsic_strength=round(
                sum(item.intrinsic_evidence_strength for item in ordered)
                + seniority_contribution,
                2,
            ),
            writing_quality=round(writing_quality, 2),
            duration_recency_contribution=round(duration_recency, 2),
            enterprise_production_contribution=round(enterprise_contribution, 2),
            enterprise_production_evidence=enterprise_evidence,
            distinct_coverage=tuple(coverage),
            page_cost=round(page_cost, 2),
            redundancy_penalty=round(redundancy_penalty, 2),
            total_score=round(total_score, 2),
            single_bullet_exception_reason=single_bullet_exception_reason,
        )

    def _bullet_candidate(
        self,
        evidence: EvidenceItem,
        entry: ResumeItem,
        context: _PostingContext,
        latest_year: int,
        entry_order: int,
        evidence_order: int,
        *,
        writing_variant: BulletVariantRecord | None,
        advisory: bool,
        evidence_by_id: dict[str, EvidenceItem],
    ) -> _BulletCandidate:
        candidate_text = (
            writing_variant.rewritten_text if writing_variant is not None else evidence.source_text
        )
        line_fit = (
            writing_variant.line_fit
            if writing_variant is not None
            else self._line_estimator.estimate(candidate_text)
        )
        supporting_evidence = (
            [
                evidence_by_id[evidence_id]
                for evidence_id in writing_variant.source_evidence_ids
                if evidence_id in evidence_by_id
                and evidence_by_id[evidence_id].entity_id == evidence.entity_id
            ]
            if writing_variant is not None
            else [evidence]
        )
        supporting_structured_values = [
            value
            for item in supporting_evidence
            for value in [*item.technologies, *item.capabilities, *item.outcomes]
        ]
        (
            score,
            contextual_relevance,
            intrinsic_evidence_strength,
            coverage_keys,
            coverage_labels,
            normalized_features,
            meaningful_overlap,
            generic_only,
            admitted,
            admission_reason,
            relationship,
            direct_requirement_ids,
            adjacent_requirement_ids,
            complementary_requirement_ids,
            incidental_requirement_ids,
            short_token_contributions,
        ) = _evidence_score(
            evidence,
            entry,
            context,
            latest_year,
            line_fit,
            candidate_text=candidate_text,
            structured_values_override=(
                supporting_structured_values if writing_variant is not None else None
            ),
        )
        if advisory:
            score = round(score + 6.0, 2)
        preserved_terms: tuple[str, ...] = ()
        removed_terms: tuple[str, ...] = ()
        writing_adjustment = 0.0
        if writing_variant is not None:
            preserved_terms, removed_terms, writing_adjustment = _rewrite_substance_adjustment(
                supporting_evidence,
                candidate_text,
                source_line_fit=self._line_estimator.estimate(
                    " ".join(item.source_text for item in supporting_evidence)
                ),
                rewrite_line_fit=line_fit,
                material_improvement=writing_variant.material_improvement,
            )
            score = round(score + writing_adjustment, 2)
        return _BulletCandidate(
            evidence_id=evidence.id,
            source_evidence_ids=(
                tuple(writing_variant.source_evidence_ids)
                if writing_variant is not None
                else (evidence.id,)
            ),
            entry_id=evidence.entity_id,
            entry_kind=entry.kind,
            text=candidate_text,
            score=score,
            contextual_relevance=contextual_relevance,
            intrinsic_evidence_strength=intrinsic_evidence_strength,
            estimated_lines=line_fit.expected_line_count,
            line_fit=line_fit,
            coverage_keys=tuple(coverage_keys),
            coverage_labels=tuple(coverage_labels),
            normalized_features=tuple(normalized_features),
            meaningful_overlap=tuple(meaningful_overlap),
            generic_only_rejected=generic_only,
            admitted=admitted,
            admission_reason=admission_reason,
            relationship=relationship,
            direct_requirement_ids=tuple(direct_requirement_ids),
            adjacent_requirement_ids=tuple(adjacent_requirement_ids),
            complementary_requirement_ids=tuple(complementary_requirement_ids),
            incidental_requirement_ids=tuple(incidental_requirement_ids),
            short_token_contributions=tuple(short_token_contributions),
            provenance=(
                f"profile.evidence[{evidence.id}]",
                f"profile.{entry.kind.value}s[{entry.id}]",
                *(
                    (f"validated_writer_variant[{writing_variant.variant_id}]",)
                    if writing_variant is not None
                    else ()
                ),
            ),
            entry_order=entry_order,
            evidence_order=evidence_order,
            writing_variant=writing_variant,
            preserved_supported_terms=preserved_terms,
            removed_supported_terms=removed_terms,
            writing_adjustment=writing_adjustment,
        )

    def _rank_skills(
        self,
        profile: MasterProfile,
        context: _PostingContext,
        bullets: list[_BulletCandidate],
    ) -> list[_SkillCandidate]:
        confirmed_evidence_text = _normalize(
            " ".join(evidence.source_text for evidence in profile.evidence if evidence.confirmed)
        )
        relevant_evidence_text = _normalize(" ".join(candidate.text for candidate in bullets))
        source_categories = profile.technical_skills or _display_categories_from_declared_skills(
            profile,
            context,
            confirmed_evidence_text=confirmed_evidence_text,
            relevant_evidence_text=relevant_evidence_text,
        )
        ranked: list[_SkillCandidate] = []
        seen_normalized_skills: set[str] = set()
        for original_order, category in enumerate(source_categories):
            is_display_regrouped = bool(
                category.source_reference
                and category.source_reference.startswith("display_regrouping:")
            )
            category_match = match_reviewed_features(
                extract_reviewed_text_features(category.category),
                context.features,
            )
            category_match_is_primary = _match_has_primary_posting_context(
                category_match,
                context,
            )
            category_assessment = assess_evidence_relationship(
                bullet_text=category.category,
                bullet_features=extract_reviewed_text_features(category.category),
                entry_features=extract_reviewed_text_features(""),
                structured_values=[category.category],
                requirements=context.requirements,
                reviewed_skill=True,
            )
            category_relevant_support_ratio = (
                sum(
                    _contains_phrase(relevant_evidence_text, _normalize(skill.value))
                    for skill in category.skills
                )
                / len(category.skills)
                if category.skills
                else 0.0
            )
            scored: list[
                tuple[
                    ReviewedTechnicalSkill,
                    float,
                    bool,
                    bool,
                    FeatureMatch,
                    ReviewedTextFeatures,
                    EvidenceRelationshipAssessment,
                ]
            ] = []
            for skill in category.skills:
                normalized = _normalize(skill.value)
                if not normalized or normalized in seen_normalized_skills:
                    continue
                features = extract_reviewed_text_features(skill.value)
                match = match_reviewed_features(features, context.features)
                assessment = assess_evidence_relationship(
                    bullet_text=skill.value,
                    bullet_features=features,
                    entry_features=extract_reviewed_text_features(category.category),
                    structured_values=[skill.value],
                    requirements=context.requirements,
                    reviewed_skill=True,
                )
                supported = _contains_phrase(confirmed_evidence_text, normalized)
                supported_by_relevant_evidence = _contains_phrase(
                    relevant_evidence_text,
                    normalized,
                )
                relationship_base = {
                    EvidenceRelationship.DIRECT: 80.0,
                    EvidenceRelationship.ADJACENT: 52.0,
                    EvidenceRelationship.COMPLEMENTARY: 28.0,
                    EvidenceRelationship.INCIDENTAL: 0.0,
                    EvidenceRelationship.REJECTED: 0.0,
                }[assessment.relationship]
                if (
                    assessment.relationship is EvidenceRelationship.REJECTED
                    and supported_by_relevant_evidence
                    and category_relevant_support_ratio >= 0.5
                ):
                    relationship_base = 20.0
                elif (
                    assessment.relationship is EvidenceRelationship.REJECTED
                    and category_assessment.relationship
                    in {EvidenceRelationship.DIRECT, EvidenceRelationship.ADJACENT}
                    and features.technical_specificity >= 0.12
                ):
                    # A reviewed canonical row can be relevant through its
                    # category (for example electrical skills under an
                    # electronic multidisciplinary responsibility) even when
                    # an individual display label is not copied into the ad.
                    relationship_base = 18.0
                score = (
                    relationship_base
                    + min(30.0, assessment.contextual_relevance)
                    + (category_assessment.contextual_relevance * 0.15)
                    + (12.0 if supported else -4.0)
                )
                anchor = (
                    assessment.relationship
                    in {
                        EvidenceRelationship.DIRECT,
                        EvidenceRelationship.ADJACENT,
                        EvidenceRelationship.COMPLEMENTARY,
                    }
                    or (
                        supported_by_relevant_evidence
                        and category_relevant_support_ratio >= 0.5
                        and (features.technical_specificity >= 0.08 or is_display_regrouped)
                    )
                    or (
                        category_assessment.relationship
                        in {
                            EvidenceRelationship.DIRECT,
                            EvidenceRelationship.ADJACENT,
                        }
                        and features.technical_specificity >= 0.12
                    )
                )
                complementary = supported or (
                    features.technical_specificity >= 0.08 and category_match_is_primary
                )
                scored.append(
                    (
                        skill,
                        score,
                        anchor and score >= self._minimum_skill_score,
                        complementary,
                        match,
                        features,
                        assessment,
                    )
                )
            anchors = [item for item in scored if item[2]]
            if not anchors:
                continue
            anchors.sort(
                key=lambda item: (
                    -item[1],
                    category.skills.index(item[0]),
                )
            )
            complements = [item for item in scored if item not in anchors and item[3]]
            complements.sort(
                key=lambda item: (
                    -int(_contains_phrase(confirmed_evidence_text, _normalize(item[0].value))),
                    -item[1],
                    category.skills.index(item[0]),
                )
            )
            selection_pool = [*anchors, *complements]
            selected_records: list[
                tuple[
                    ReviewedTechnicalSkill,
                    float,
                    bool,
                    bool,
                    FeatureMatch,
                    ReviewedTextFeatures,
                    EvidenceRelationshipAssessment,
                ]
            ] = []
            for record in selection_pool:
                if len(selected_records) >= self._maximum_skills_per_display_row:
                    break
                proposed_values = [item[0].value for item in [*selected_records, record]]
                if not self._skill_row_estimator.estimate(category.category, proposed_values).wraps:
                    selected_records.append(record)
            if is_display_regrouped:
                selected_records.sort(key=lambda item: category.skills.index(item[0]))
            selected = [item[0] for item in selected_records]
            skill_scores = [item[1] for item in selected_records]
            one_skill_exception_reason: str | None = None
            if len(selected) == 1:
                strongest_score = skill_scores[0]
                normalized_skill = _normalize(selected[0].value)
                demonstrated_complement = _contains_phrase(
                    confirmed_evidence_text, normalized_skill
                ) and _contains_phrase(relevant_evidence_text, normalized_skill)
                if strongest_score < 32.0 and not demonstrated_complement:
                    continue
                one_skill_exception_reason = (
                    "The row contains one reviewed skill because it is unusually important "
                    "or demonstrably complementary, has no compatible reviewed peer in its "
                    "source category, and omitting it would remove distinct technical coverage."
                )
            coverage: list[tuple[str, str]] = []
            normalized_features: list[str] = []
            meaningful_overlap: list[str] = []
            supported_ids: list[str] = []
            declared_only_ids: list[str] = []
            selected_relationships: list[EvidenceRelationship] = []
            requirement_by_id = {item.id: item for item in context.requirements.requirements}
            for (
                skill,
                _score,
                _anchor,
                _complementary,
                _match,
                features,
                assessment,
            ) in selected_records:
                normalized = _normalize(skill.value)
                seen_normalized_skills.add(normalized)
                normalized_features.extend(features.specific_phrases)
                meaningful_overlap.extend(assessment.meaningful_overlap)
                supported = _contains_phrase(confirmed_evidence_text, normalized)
                supported_by_relevant_evidence = _contains_phrase(
                    relevant_evidence_text,
                    normalized,
                )
                effective_relationship = assessment.relationship
                if (
                    effective_relationship is EvidenceRelationship.REJECTED
                    and supported_by_relevant_evidence
                ):
                    effective_relationship = EvidenceRelationship.COMPLEMENTARY
                elif (
                    effective_relationship is EvidenceRelationship.REJECTED
                    and category_assessment.relationship
                    in {EvidenceRelationship.DIRECT, EvidenceRelationship.ADJACENT}
                ):
                    effective_relationship = EvidenceRelationship.ADJACENT
                selected_relationships.append(effective_relationship)
                if supported:
                    supported_ids.append(skill.id or normalized)
                else:
                    declared_only_ids.append(skill.id or normalized)
                requirement_ids = [
                    *assessment.direct_requirement_ids,
                    *assessment.adjacent_requirement_ids,
                    *assessment.complementary_requirement_ids,
                ]
                for requirement_id in requirement_ids:
                    requirement = requirement_by_id.get(requirement_id)
                    if requirement is not None:
                        coverage.append((f"requirement:{requirement_id}", requirement.text))
            score = round(
                max(skill_scores)
                + (sum(skill_scores[1:]) * 0.24)
                + (min(4, len(selected)) * 2.5)
                - (14.0 if len(selected) == 1 else 0.0),
                2,
            )
            category_id = category.id or ""
            width_estimate = self._skill_row_estimator.estimate(
                category.category,
                [skill.value for skill in selected],
            )
            # A credible row that remains visibly sparse is less valuable than
            # an equally credible row that uses the Template V1 line well. The
            # bonus is deliberately bounded: it never admits an unrelated row,
            # but lets a fuller fourth/fifth reviewed row compete with a weak
            # bullet through the normal page-fit search.
            if len(selected) >= 2 and any(
                relationship
                in {
                    EvidenceRelationship.DIRECT,
                    EvidenceRelationship.ADJACENT,
                    EvidenceRelationship.COMPLEMENTARY,
                }
                for relationship in selected_relationships
            ):
                score = round(
                    score + max(0.0, 0.65 - width_estimate.used_width_ratio) * 28.0,
                    2,
                )
            compatible_omitted = tuple(
                item[0].value for item in selection_pool if item not in selected_records
            )
            underfill_exception_reason: str | None = None
            if width_estimate.used_width_ratio < 0.75:
                if compatible_omitted:
                    underfill_exception_reason = (
                        "Compatible reviewed skills remain, but each would wrap the measured "
                        "Template V1 row or lose the normal page-fit comparison."
                    )
                else:
                    underfill_exception_reason = (
                        "No additional reviewed skill met the row's requirement and evidence "
                        "compatibility threshold without creating a misleading category."
                    )
            normalized_coverage = _deduplicated_coverage(coverage)
            ranked.append(
                _SkillCandidate(
                    category_id=category_id,
                    label=category.category,
                    category=category.model_copy(
                        update={
                            "values": [skill.value for skill in selected],
                            "skills": selected,
                        }
                    ),
                    score=score,
                    coverage_keys=tuple(key for key, _ in normalized_coverage),
                    coverage_labels=tuple(label for _, label in normalized_coverage),
                    normalized_features=tuple(_maximal_phrases(normalized_features)),
                    meaningful_overlap=tuple(_maximal_phrases(meaningful_overlap)),
                    supported_skill_ids=tuple(supported_ids),
                    declared_only_skill_ids=tuple(declared_only_ids),
                    construction_reason=(
                        "Constructed from reviewed posting anchors plus a bounded number "
                        "of demonstrated or category-compatible reviewed complements; "
                        "declared-only skills retained a measured penalty."
                    ),
                    provenance=tuple(
                        skill.source_reference
                        or category.source_reference
                        or f"profile.technical_skills[{category_id}]"
                        for skill in selected
                    ),
                    source_category_ids=(category_id,),
                    one_skill_exception_reason=one_skill_exception_reason,
                    grouping_reason=(
                        "Display-only row joins reviewed flat skills through shared posting "
                        "requirements or evidence-backed compatibility; original source order "
                        "is only a deterministic secondary preference."
                        if is_display_regrouped
                        else "Preserved the reviewed canonical skill category."
                    ),
                    relationship=min(
                        selected_relationships,
                        key=_relationship_order,
                        default=EvidenceRelationship.REJECTED,
                    ),
                    original_order=original_order,
                    estimated_available_width_points=width_estimate.available_width_points,
                    estimated_used_width_points=width_estimate.used_width_points,
                    estimated_remaining_width_points=width_estimate.remaining_width_points,
                    estimated_used_width_ratio=width_estimate.used_width_ratio,
                    compatible_omitted_skill_values=compatible_omitted,
                    underfill_exception_reason=underfill_exception_reason,
                )
            )
        ranked.sort(key=lambda item: (-item.score, item.original_order, item.category_id))
        related_count = sum(
            item.relationship is not EvidenceRelationship.REJECTED for item in ranked
        )
        if related_count < 2:
            ranked = [
                item
                for item in ranked
                if item.relationship is not EvidenceRelationship.REJECTED
                or (len(source_categories) <= 3 and item.supported_skill_ids)
            ]
        return ranked

    def _expansions(
        self,
        state: _State,
        profile: MasterProfile,
        bullets: list[_BulletCandidate],
        experience_packages: dict[str, list[_ExperiencePackage]],
        skills: list[_SkillCandidate],
        bullet_by_id: dict[str, _BulletCandidate],
        skill_by_id: dict[str, _SkillCandidate],
        constraints: TemplateConstraints,
        redundancy_by_source: dict[str, float],
    ) -> list[_Expansion]:
        selected_entries = {bullet_by_id[item].entry_id for item in state.bullet_ids}
        selected_entry_counts = Counter(bullet_by_id[item].entry_id for item in state.bullet_ids)
        selected_direct_requirements = {
            requirement_id
            for item in state.bullet_ids
            for requirement_id in bullet_by_id[item].direct_requirement_ids
        }
        options: list[_Expansion] = []
        handled_experience_entries: set[str] = set()
        for candidate in bullets:
            if candidate.evidence_id in state.bullet_ids:
                continue
            opens_entry = candidate.entry_id not in selected_entries
            if opens_entry and candidate.entry_kind is EntityKind.EXPERIENCE:
                if candidate.entry_id in handled_experience_entries:
                    continue
                handled_experience_entries.add(candidate.entry_id)
                for package in experience_packages.get(candidate.entry_id, []):
                    package_candidates = [bullet_by_id[item] for item in package.bullet_ids]
                    package_penalty = 0.0
                    rejected = False
                    for package_candidate in package_candidates:
                        redundancy_penalty, duplicate = self._redundancy_penalty(
                            package_candidate,
                            state,
                            bullet_by_id,
                        )
                        dominance_penalty, dominated, _ = self._dominance_penalty(
                            package_candidate,
                            state,
                            bullet_by_id,
                        )
                        package_penalty += redundancy_penalty + dominance_penalty
                        redundancy_by_source[package_candidate.evidence_id] = max(
                            redundancy_by_source.get(package_candidate.evidence_id, 0),
                            redundancy_penalty + dominance_penalty,
                        )
                        if duplicate or dominated:
                            rejected = True
                            break
                    if rejected:
                        continue
                    proposal = _State(
                        state.bullet_ids | frozenset(package.bullet_ids),
                        state.skill_category_ids,
                    )
                    if not self._within_planning_bounds(
                        proposal,
                        profile,
                        bullet_by_id,
                        constraints,
                    ):
                        continue
                    marginal = package.total_score - package_penalty - 12.0
                    if marginal < self._minimum_marginal_score:
                        continue
                    options.append(
                        _Expansion(
                            candidate_id=package.package_id,
                            source_id=package.bullet_ids[0],
                            kind=CompositionCandidateKind.EXPERIENCE_ENTRY,
                            state=proposal,
                            marginal_score=marginal,
                            redundancy_penalty=round(package_penalty, 2),
                            preference_bonus=(
                                8.0
                                if len(package.bullet_ids) == 3
                                else 4.0
                                if len(package.bullet_ids) >= 4
                                else 0.0
                            ),
                            line_cost=package.page_cost,
                        )
                    )
                continue
            penalty, duplicate = self._redundancy_penalty(
                candidate,
                state,
                bullet_by_id,
            )
            dominance_penalty, dominated, _ = self._dominance_penalty(
                candidate,
                state,
                bullet_by_id,
            )
            penalty += dominance_penalty
            redundancy_by_source[candidate.evidence_id] = max(
                redundancy_by_source.get(candidate.evidence_id, 0),
                penalty,
            )
            if duplicate or dominated:
                continue
            depth = selected_entry_counts.get(candidate.entry_id, 0)
            if candidate.entry_kind is EntityKind.EXPERIENCE and depth >= 4:
                continue
            if (
                opens_entry
                and candidate.intrinsic_evidence_strength < 20.0
                and not (set(candidate.direct_requirement_ids) - selected_direct_requirements)
            ):
                continue
            containment_penalty = (
                max(0, depth - 1) * 10.0
                if candidate.entry_kind is EntityKind.PROJECT
                else depth * 10.0
            )
            if set(candidate.direct_requirement_ids) - selected_direct_requirements:
                containment_penalty = 0.0
            penalty += containment_penalty
            redundancy_by_source[candidate.evidence_id] = max(
                redundancy_by_source.get(candidate.evidence_id, 0),
                penalty,
            )
            kind = (
                CompositionCandidateKind.EXPERIENCE_ENTRY
                if opens_entry and candidate.entry_kind == EntityKind.EXPERIENCE
                else CompositionCandidateKind.PROJECT_ENTRY
                if opens_entry
                else CompositionCandidateKind.EXPERIENCE_BULLET
                if candidate.entry_kind == EntityKind.EXPERIENCE
                else CompositionCandidateKind.PROJECT_BULLET
            )
            opening_penalty = 6.0 if opens_entry else 0.0
            marginal = candidate.score - penalty - opening_penalty
            if marginal < self._minimum_marginal_score:
                continue
            proposal = _State(
                state.bullet_ids | {candidate.evidence_id},
                state.skill_category_ids,
            )
            if not self._within_planning_bounds(
                proposal,
                profile,
                bullet_by_id,
                constraints,
            ):
                continue
            coherence_bonus = (
                5.0
                if not opens_entry and depth == 1
                else 2.0
                if not opens_entry and depth == 2
                else 0.0
            )
            if candidate.entry_kind is EntityKind.PROJECT and not opens_entry and depth == 1:
                coherence_bonus += 9.0
            if (
                candidate.entry_kind is EntityKind.PROJECT
                and opens_entry
                and not any(
                    bullet_by_id[item].entry_kind is EntityKind.PROJECT for item in state.bullet_ids
                )
            ):
                coherence_bonus += 5.0
            options.append(
                _Expansion(
                    candidate_id=f"{kind.value}:{candidate.evidence_id}",
                    source_id=candidate.evidence_id,
                    kind=kind,
                    state=proposal,
                    marginal_score=marginal,
                    redundancy_penalty=penalty,
                    preference_bonus=coherence_bonus,
                    line_cost=(
                        candidate.line_fit.total_vertical_line_cost + (2.0 if opens_entry else 0.0)
                    ),
                )
            )
        selected_bullet_text = _normalize(
            " ".join(bullet_by_id[item].text for item in state.bullet_ids)
        )
        for skill_candidate in skills:
            if skill_candidate.category_id in state.skill_category_ids:
                continue
            if len(state.skill_category_ids) >= constraints.max_skill_lines:
                continue
            selected_coverage = {
                coverage
                for category_id in state.skill_category_ids
                for coverage in skill_by_id[category_id].coverage_keys
            }
            repeated = len(set(skill_candidate.coverage_keys) & selected_coverage)
            distinct_coverage = set(skill_candidate.coverage_keys) - selected_coverage
            if len(state.skill_category_ids) >= 3 and (
                skill_candidate.relationship
                not in {
                    EvidenceRelationship.DIRECT,
                    EvidenceRelationship.ADJACENT,
                    EvidenceRelationship.COMPLEMENTARY,
                }
                or (not distinct_coverage and not skill_candidate.supported_skill_ids)
            ):
                # Three meaningful rows are the normal soft target. A fourth
                # row must add a direct, distinct posting signal instead of
                # repeating selected evidence through another display label.
                continue
            penalty = min(skill_candidate.score * 0.35, repeated * 8.0)
            evidence_supported = any(
                _contains_phrase(selected_bullet_text, _normalize(skill.value))
                for skill in skill_candidate.category.skills
            )
            if not evidence_supported:
                declared_only_fraction = len(skill_candidate.declared_only_skill_ids) / max(
                    1,
                    len(skill_candidate.category.skills),
                )
                penalty += 3.0 + (declared_only_fraction * 2.0)
            redundancy_by_source[skill_candidate.category_id] = max(
                redundancy_by_source.get(skill_candidate.category_id, 0),
                penalty,
            )
            marginal = (skill_candidate.score * 0.52) - penalty
            if len(skill_candidate.category.skills) == 1:
                penalty += 12.0
                marginal -= 12.0
            if marginal < self._minimum_marginal_score:
                continue
            proposal = _State(
                state.bullet_ids,
                state.skill_category_ids | {skill_candidate.category_id},
            )
            options.append(
                _Expansion(
                    candidate_id=f"skill_category:{skill_candidate.category_id}",
                    source_id=skill_candidate.category_id,
                    kind=CompositionCandidateKind.SKILL_CATEGORY,
                    state=proposal,
                    marginal_score=marginal,
                    redundancy_penalty=penalty,
                    preference_bonus=(
                        8.0
                        if len(state.skill_category_ids) < 3
                        else 4.0
                        if len(state.skill_category_ids) == 3
                        else 0.0
                    ),
                    line_cost=1.0,
                )
            )
        options.sort(
            key=lambda item: (
                -((item.marginal_score + item.preference_bonus) / item.line_cost),
                -(item.marginal_score + item.preference_bonus),
                -item.marginal_score,
                item.kind.value,
                item.source_id,
            )
        )
        return options

    def _has_admissible_expansion(
        self,
        state: _State,
        profile: MasterProfile,
        bullets: list[_BulletCandidate],
        experience_packages: dict[str, list[_ExperiencePackage]],
        skills: list[_SkillCandidate],
        bullet_by_id: dict[str, _BulletCandidate],
        skill_by_id: dict[str, _SkillCandidate],
        constraints: TemplateConstraints,
        redundancy_by_source: dict[str, float],
    ) -> bool:
        return bool(
            self._expansions(
                state,
                profile,
                bullets,
                experience_packages,
                skills,
                bullet_by_id,
                skill_by_id,
                constraints,
                redundancy_by_source,
            )
        )

    def _within_planning_bounds(
        self,
        state: _State,
        profile: MasterProfile,
        bullet_by_id: dict[str, _BulletCandidate],
        constraints: TemplateConstraints,
    ) -> bool:
        counts = Counter(bullet_by_id[item].entry_id for item in state.bullet_ids)
        if len(state.bullet_ids) > self._bounds.maximum_selected_bullets:
            return False
        if self._bounds.maximum_bullets_per_entry is not None and any(
            count > self._bounds.maximum_bullets_per_entry for count in counts.values()
        ):
            return False
        entity_by_id = {item.id: item for item in [*profile.experiences, *profile.projects]}
        for entry_id, count in counts.items():
            if entity_by_id[entry_id].kind is EntityKind.EXPERIENCE and count > 4:
                return False
            if entity_by_id[entry_id].kind is not EntityKind.EXPERIENCE or count != 1:
                continue
            selected_candidate = next(
                bullet_by_id[item]
                for item in state.bullet_ids
                if bullet_by_id[item].entry_id == entry_id
            )
            if self._single_bullet_exception_reason(
                selected_candidate,
                bullet_by_id,
            ) is None:
                return False
        experience_entries = sum(
            entity_by_id[entry_id].kind == EntityKind.EXPERIENCE for entry_id in counts
        )
        project_entries = sum(
            entity_by_id[entry_id].kind == EntityKind.PROJECT for entry_id in counts
        )
        return (
            len(counts) <= self._bounds.maximum_selected_entries
            and experience_entries <= self._bounds.maximum_experience_entries
            and project_entries <= self._bounds.maximum_project_entries
            and len(state.skill_category_ids) <= constraints.max_skill_lines
        )

    def _planning_bound_reason(
        self,
        state: _State,
        profile: MasterProfile,
        bullet_by_id: dict[str, _BulletCandidate],
        constraints: TemplateConstraints,
    ) -> str:
        counts = Counter(bullet_by_id[item].entry_id for item in state.bullet_ids)
        if len(state.bullet_ids) > self._bounds.maximum_selected_bullets:
            return f"maximum_selected_bullets={self._bounds.maximum_selected_bullets}"
        if self._bounds.maximum_bullets_per_entry is not None and any(
            count > self._bounds.maximum_bullets_per_entry for count in counts.values()
        ):
            return (
                "maximum_bullets_per_entry="
                f"{self._bounds.maximum_bullets_per_entry}"
            )
        entity_by_id = {item.id: item for item in [*profile.experiences, *profile.projects]}
        if any(
            entity_by_id[entry_id].kind is EntityKind.EXPERIENCE and count > 4
            for entry_id, count in counts.items()
        ):
            return "maximum_experience_bullets_per_entry=4"
        experience_entries = sum(
            entity_by_id[entry_id].kind is EntityKind.EXPERIENCE for entry_id in counts
        )
        project_entries = sum(
            entity_by_id[entry_id].kind is EntityKind.PROJECT for entry_id in counts
        )
        if len(counts) > self._bounds.maximum_selected_entries:
            return f"maximum_selected_entries={self._bounds.maximum_selected_entries}"
        if experience_entries > self._bounds.maximum_experience_entries:
            return f"maximum_experience_entries={self._bounds.maximum_experience_entries}"
        if project_entries > self._bounds.maximum_project_entries:
            return f"maximum_project_entries={self._bounds.maximum_project_entries}"
        if len(state.skill_category_ids) > constraints.max_skill_lines:
            return f"max_skill_lines={constraints.max_skill_lines}"
        return "coherent_professional_block_or_bounded_search_limit"

    @staticmethod
    def _single_bullet_exception_reason(
        candidate: _BulletCandidate,
        bullet_by_id: dict[str, _BulletCandidate],
    ) -> ExperienceSingleBulletExceptionReason | None:
        if candidate.entry_kind is not EntityKind.EXPERIENCE:
            return None
        other_requirement_ids = {
            requirement_id
            for other in bullet_by_id.values()
            if other.entry_id != candidate.entry_id
            for requirement_id in other.direct_requirement_ids
        }
        unique_direct = set(candidate.direct_requirement_ids) - other_requirement_ids
        if (
            candidate.relationship is EvidenceRelationship.DIRECT
            and unique_direct
            and candidate.contextual_relevance >= 30.0
            and candidate.intrinsic_evidence_strength >= 25.0
        ):
            return ExperienceSingleBulletExceptionReason.UNIQUE_DIRECT_REQUIREMENT_COVERAGE
        if (
            candidate.relationship is EvidenceRelationship.DIRECT
            and candidate.contextual_relevance >= 55.0
            and candidate.intrinsic_evidence_strength >= 52.0
            and candidate.score >= 125.0
        ):
            return (
                ExperienceSingleBulletExceptionReason.REVIEWED_CENTRAL_ROLE_EXCEPTIONAL_VALUE
            )
        return None

    def _redundancy_penalty(
        self,
        candidate: _BulletCandidate,
        state: _State,
        bullet_by_id: dict[str, _BulletCandidate],
    ) -> tuple[float, bool]:
        selected = [bullet_by_id[item] for item in state.bullet_ids]
        if any(
            _near_duplicate(candidate.text, other.text) >= self._near_duplicate_threshold
            for other in selected
        ):
            return candidate.score, True
        selected_coverage = {coverage for other in selected for coverage in other.coverage_keys}
        repeated = len(set(candidate.coverage_keys) & selected_coverage)
        coverage_ratio = repeated / max(1, len(candidate.coverage_keys))
        selected_features = {feature for other in selected for feature in other.normalized_features}
        candidate_features = set(candidate.normalized_features)
        feature_repeat_ratio = len(candidate_features & selected_features) / max(
            1,
            len(candidate_features),
        )
        same_entry = [other for other in selected if other.entry_id == candidate.entry_id]
        depth = len(same_entry)
        distinct_coverage = set(candidate.coverage_keys) - selected_coverage
        distinct_features = candidate_features - selected_features
        depth_penalty = max(0, depth - 1) * (2.5 + max(0, depth - 2) * 1.5)
        if distinct_coverage or len(distinct_features) >= 2:
            depth_penalty *= 0.35
        penalty = (
            candidate.score * coverage_ratio * 0.46
            + candidate.score * feature_repeat_ratio * 0.20
            + depth_penalty
        )
        if (
            candidate.relationship is EvidenceRelationship.COMPLEMENTARY
            and coverage_ratio >= 1.0
            and not candidate.meaningful_overlap
        ):
            penalty += candidate.score * 0.40
        return round(min(candidate.score, penalty), 2), False

    @staticmethod
    def _credible_project_ids(
        bullets: list[_BulletCandidate],
    ) -> set[str]:
        counts = Counter(
            candidate.entry_id
            for candidate in bullets
            if candidate.entry_kind is EntityKind.PROJECT
        )
        return {entry_id for entry_id, count in counts.items() if count >= 2}

    @staticmethod
    def _state_has_substantive_project(
        state: _State,
        bullet_by_id: dict[str, _BulletCandidate],
    ) -> bool:
        counts = Counter(
            bullet_by_id[evidence_id].entry_id
            for evidence_id in state.bullet_ids
            if bullet_by_id[evidence_id].entry_kind is EntityKind.PROJECT
        )
        return any(count >= 2 for count in counts.values())

    @staticmethod
    def _dominance_penalty(
        candidate: _BulletCandidate,
        state: _State,
        bullet_by_id: dict[str, _BulletCandidate],
    ) -> tuple[float, bool, str | None]:
        # Dominance is an entry-substitution signal. Once the candidate's own
        # coherent entry is open, its additional reviewed bullets are governed
        # by marginal value and redundancy, not suppressed because another entry
        # covers a broad capability such as design or testing.
        if any(bullet_by_id[item].entry_id == candidate.entry_id for item in state.bullet_ids):
            return 0.0, False, None
        selected = [
            bullet_by_id[item]
            for item in state.bullet_ids
            if bullet_by_id[item].entry_id != candidate.entry_id
        ]
        candidate_coverage = set(candidate.coverage_keys)
        if not candidate_coverage:
            return 0.0, False, None
        selected_portfolio_coverage = {key for item in selected for key in item.coverage_keys}
        entry_potential_coverage = {
            key
            for item in bullet_by_id.values()
            if item.entry_id == candidate.entry_id
            for key in item.coverage_keys
        }
        if _unique_coverage(
            entry_potential_coverage,
            selected_portfolio_coverage,
        ):
            return 0.0, False, None
        entry_candidates = [
            item for item in bullet_by_id.values() if item.entry_id == candidate.entry_id
        ]
        selected_portfolio_features = {
            feature for item in selected for feature in item.normalized_features
        }
        entry_potential_features = {
            feature for item in entry_candidates for feature in item.normalized_features
        }
        if (
            len(entry_candidates) >= 2
            and len(entry_potential_features - selected_portfolio_features) >= 2
        ):
            return 0.0, False, None
        selected_by_entry: dict[str, list[_BulletCandidate]] = {}
        for item in selected:
            selected_by_entry.setdefault(item.entry_id, []).append(item)
        for entry_id, entry_bullets in sorted(selected_by_entry.items()):
            entry_coverage = {key for item in entry_bullets for key in item.coverage_keys}
            unique_coverage = _unique_coverage(
                candidate_coverage,
                entry_coverage,
            )
            overlap = (len(candidate_coverage) - len(unique_coverage)) / max(
                1, len(candidate_coverage)
            )
            strongest_intrinsic = max(item.intrinsic_evidence_strength for item in entry_bullets)
            strongest_context = max(item.contextual_relevance for item in entry_bullets)
            dominated = (
                overlap >= 0.70
                and not unique_coverage
                and strongest_intrinsic >= candidate.intrinsic_evidence_strength * 1.12
                and strongest_context >= candidate.contextual_relevance * 0.70
            )
            if dominated:
                return (
                    candidate.score,
                    True,
                    (
                        f"Entry {entry_id} dominates this overlapping evidence through "
                        "stronger intrinsic proof without losing unique requirement coverage."
                    ),
                )
        return 0.0, False, None

    @staticmethod
    def _state_coverage(
        state: _State,
        bullet_by_id: dict[str, _BulletCandidate],
        skill_by_id: dict[str, _SkillCandidate],
    ) -> set[str]:
        return {
            coverage
            for evidence_id in state.bullet_ids
            for coverage in bullet_by_id[evidence_id].coverage_keys
        } | {
            coverage
            for category_id in state.skill_category_ids
            for coverage in skill_by_id[category_id].coverage_keys
        }

    def _state_quality(
        self,
        state: _State,
        profile: MasterProfile,
        bullet_by_id: dict[str, _BulletCandidate],
        skill_by_id: dict[str, _SkillCandidate],
    ) -> float:
        bullets = [bullet_by_id[item] for item in state.bullet_ids]
        latest_experience_year = max(
            (
                year
                for entry in profile.experiences
                for value in (entry.start_date, entry.end_date)
                for year in _years(value)
            ),
            default=0,
        )
        experience_package_score = 0.0
        for entry in profile.experiences:
            entry_bullets = [
                bullet
                for bullet in bullets
                if bullet.entry_kind is EntityKind.EXPERIENCE
                and bullet.entry_id == entry.id
            ]
            if not entry_bullets:
                continue
            experience_package_score += self._score_experience_package(
                entry,
                entry_bullets,
                latest_experience_year,
                single_bullet_exception_reason=(
                    self._single_bullet_exception_reason(entry_bullets[0], bullet_by_id)
                    if len(entry_bullets) == 1
                    else None
                ),
            ).total_score
        project_bullet_score = sum(
            bullet.score for bullet in bullets if bullet.entry_kind is EntityKind.PROJECT
        )
        coverage_counts = Counter(
            coverage for bullet in bullets for coverage in bullet.coverage_keys
        )
        unique_coverage = len(coverage_counts)
        coverage_entries: dict[str, set[str]] = {}
        for bullet in bullets:
            for coverage in bullet.coverage_keys:
                coverage_entries.setdefault(coverage, set()).add(bullet.entry_id)
        repeated_coverage = sum(
            max(0, len(entry_ids) - 1) for entry_ids in coverage_entries.values()
        )
        opened_entries = {bullet.entry_id for bullet in bullets}
        direct_count = sum(bullet.relationship is EvidenceRelationship.DIRECT for bullet in bullets)
        adjacent_count = sum(
            bullet.relationship is EvidenceRelationship.ADJACENT for bullet in bullets
        )
        complementary_count = sum(
            bullet.relationship is EvidenceRelationship.COMPLEMENTARY for bullet in bullets
        )
        relationship_adjustment = (
            (direct_count * 10.0)
            + (adjacent_count * 6.0)
            + complementary_count
            - (
                max(
                    0,
                    complementary_count - max(1, direct_count + adjacent_count),
                )
                * 8.0
            )
        )
        direct_requirement_counts = Counter(
            requirement_id for bullet in bullets for requirement_id in bullet.direct_requirement_ids
        )
        direct_requirement_adjustment = (
            len(direct_requirement_counts) * 18.0
            - sum(max(0, count - 1) for count in direct_requirement_counts.values()) * 2.0
        )
        project_bullet_counts = Counter(
            bullet.entry_id for bullet in bullets if bullet.entry_kind is EntityKind.PROJECT
        )
        credible_project_ids = self._credible_project_ids(list(bullet_by_id.values()))
        project_count = len(project_bullet_counts)
        substantive_project_count = sum(count >= 2 for count in project_bullet_counts.values())
        sparse_project_count = sum(count == 1 for count in project_bullet_counts.values())
        project_depth_adjustment = (
            16.0 + max(0, substantive_project_count - 1) * 4.0
            if substantive_project_count
            else -14.0
            if credible_project_ids and project_count
            else -12.0
            if credible_project_ids
            else 0.0
        )
        sparse_skill_row_count = sum(
            len(skill_by_id[item].category.skills) == 1 for item in state.skill_category_ids
        )
        return round(
            experience_package_score
            + project_bullet_score
            + sum(skill_by_id[item].score * 0.42 for item in state.skill_category_ids)
            + (min(3, len(state.skill_category_ids)) * 10.0)
            + (5.0 if len(state.skill_category_ids) >= 4 else 0.0)
            + relationship_adjustment
            + direct_requirement_adjustment
            + project_depth_adjustment
            - (sparse_project_count * 12.0)
            + (unique_coverage * 7.0)
            - (repeated_coverage * 6.0)
            - (sparse_skill_row_count * 12.0)
            - (max(0, len(opened_entries) - 1) * 4.0)
            - sum(3.5 if bullet.line_fit.awkward_wrap_risk else 0.0 for bullet in bullets)
            - sum(max(0, bullet.line_fit.expected_line_count - 2) * 15.0 for bullet in bullets),
            2,
        )

    def _best_states(
        self,
        states: list[_EvaluatedState],
        *,
        limit: int | None = None,
    ) -> list[_EvaluatedState]:
        ordered = sorted(
            states,
            key=lambda item: (
                self._density_priority(item.evaluation.utilization_ratio),
                self._density_distance(item.evaluation.utilization_ratio),
                -item.quality,
                -item.coverage_count,
                item.three_line_bullet_count,
                item.state.key,
            ),
        )
        return ordered[: limit or self._bounds.beam_width]

    def _search_states(
        self,
        states: list[_EvaluatedState],
    ) -> list[_EvaluatedState]:
        unique = {item.state.key: item for item in states}
        ordered = sorted(
            unique.values(),
            key=lambda item: (
                self._density_priority(item.evaluation.utilization_ratio),
                self._density_distance(item.evaluation.utilization_ratio),
                -item.coverage_count,
                -item.quality,
                item.three_line_bullet_count,
                item.state.key,
            ),
        )
        return ordered[: self._bounds.beam_width]

    @staticmethod
    def _density_priority(utilization_ratio: float) -> int:
        if TEMPLATE_V1_PREFERRED_DENSITY_FLOOR <= utilization_ratio <= (
            TEMPLATE_V1_PREFERRED_DENSITY_CEILING
        ):
            return 0
        if TEMPLATE_V1_PREFERRED_DENSITY_CEILING < utilization_ratio <= (
            TEMPLATE_V1_ACCEPTABLE_DENSITY_CEILING
        ):
            return 1
        if TEMPLATE_V1_DENSITY_INVESTIGATION_FLOOR <= utilization_ratio < (
            TEMPLATE_V1_PREFERRED_DENSITY_FLOOR
        ):
            return 2
        if TEMPLATE_V1_UTILIZATION_TARGET_FLOOR <= utilization_ratio < (
            TEMPLATE_V1_DENSITY_INVESTIGATION_FLOOR
        ):
            return 3
        if utilization_ratio < TEMPLATE_V1_UTILIZATION_TARGET_FLOOR:
            return 4
        return 5

    @staticmethod
    def _density_distance(utilization_ratio: float) -> float:
        if utilization_ratio < TEMPLATE_V1_PREFERRED_DENSITY_FLOOR:
            # Treat sub-band density differences below two percentage points
            # as effectively tied so a tiny fill gain cannot defeat a clearly
            # stronger coherent portfolio. Material underfill gaps still sort
            # into different buckets before quality is considered.
            return -float(int(utilization_ratio * 50))
        return abs(utilization_ratio - TEMPLATE_V1_IDEAL_DENSITY)

    @staticmethod
    def _in_target_band(utilization_ratio: float) -> bool:
        return (
            TEMPLATE_V1_DENSITY_INVESTIGATION_FLOOR
            <= utilization_ratio
            <= TEMPLATE_V1_UTILIZATION_TARGET_CEILING
        )

    @staticmethod
    def _in_preferred_density_band(utilization_ratio: float) -> bool:
        return (
            TEMPLATE_V1_PREFERRED_DENSITY_FLOOR
            <= utilization_ratio
            <= TEMPLATE_V1_PREFERRED_DENSITY_CEILING
        )

    @staticmethod
    def _in_automatic_completion_band(utilization_ratio: float) -> bool:
        return (
            TEMPLATE_V1_PREFERRED_DENSITY_FLOOR
            <= utilization_ratio
            <= TEMPLATE_V1_ACCEPTABLE_DENSITY_CEILING
        )

    @staticmethod
    def _preferred_density_status(
        utilization_ratio: float,
    ) -> PreferredDensityStatus:
        if utilization_ratio < TEMPLATE_V1_PREFERRED_DENSITY_FLOOR:
            return PreferredDensityStatus.BELOW_PREFERRED
        if utilization_ratio <= TEMPLATE_V1_PREFERRED_DENSITY_CEILING:
            return PreferredDensityStatus.PREFERRED
        if utilization_ratio <= TEMPLATE_V1_ACCEPTABLE_DENSITY_CEILING:
            return PreferredDensityStatus.ABOVE_PREFERRED
        return PreferredDensityStatus.OVERFLOW_RISK

    @staticmethod
    def _outcome(
        final: _EvaluatedState,
        additional_evidence_unavailable: bool,
    ) -> tuple[CompositionOutcome, str]:
        evaluation = final.evaluation
        if not evaluation.exact:
            return (
                CompositionOutcome.UNVERIFIED,
                "Composition used the deterministic occupancy estimate because exact DOCX "
                "pagination was unavailable.",
            )
        if not evaluation.fits_one_page or evaluation.page_count != 1:
            return CompositionOutcome.OVERFLOW, "No evaluated composition fit exactly one page."
        if evaluation.utilization_ratio < TEMPLATE_V1_DENSITY_INVESTIGATION_FLOOR:
            if additional_evidence_unavailable:
                return (
                    CompositionOutcome.INSUFFICIENT_EVIDENCE,
                    "The result is underfilled because no additional nonredundant reviewed "
                    "evidence met the relevance threshold.",
                )
            return (
                CompositionOutcome.SEVERE_UNDERFILL,
                "The verified result remains underfilled; remaining admissible evidence did "
                "not improve the selected bounded-search result.",
            )
        if evaluation.utilization_ratio < TEMPLATE_V1_PREFERRED_DENSITY_FLOOR:
            return (
                CompositionOutcome.ACCEPTABLE_ONE_PAGE,
                "The verified composition fits one page but remains below the preferred "
                "90%-93% preferred visual range; utilization through 95% remains "
                "acceptable. Typed diagnostics identify whether evidence, match, "
                "quality, profile completeness, or search bounds limited further filling.",
            )
        return (
            CompositionOutcome.ACCEPTABLE_ONE_PAGE,
            "The deterministic final-plan objective selected a verified one-page "
            "composition within the calibrated Template V1 utilization target.",
        )

    def _resume_for_state(
        self,
        baseline: StructuredResume,
        profile: MasterProfile,
        state: _State,
        bullet_by_id: dict[str, _BulletCandidate],
        skill_by_id: dict[str, _SkillCandidate],
    ) -> StructuredResume:
        evidence_order = {evidence.id: index for index, evidence in enumerate(profile.evidence)}
        selected_by_entry: dict[str, list[StructuredBullet]] = {}
        consumed_evidence_ids: set[str] = set()
        for evidence_id in sorted(
            state.bullet_ids,
            key=lambda item: (evidence_order[item], item),
        ):
            candidate = bullet_by_id[evidence_id]
            if evidence_id in consumed_evidence_ids:
                continue
            consumed_evidence_ids.update(candidate.source_evidence_ids)
            selected_by_entry.setdefault(candidate.entry_id, []).append(
                StructuredBullet(
                    id=(
                        candidate.writing_variant.variant_id
                        if candidate.writing_variant is not None
                        else candidate.evidence_id
                    ),
                    text=candidate.text,
                    evidence_ids=list(candidate.source_evidence_ids),
                    support=ClaimSupport.DIRECT,
                    writing_variant=candidate.writing_variant,
                )
            )
        selected_entries = set(selected_by_entry)
        experiences = [item for item in profile.experiences if item.id in selected_entries]
        projects = [item for item in profile.projects if item.id in selected_entries]
        selected_skills = sorted(
            (skill_by_id[item] for item in state.skill_category_ids),
            key=lambda item: (item.original_order, item.category_id),
        )
        return baseline.model_copy(
            update={
                "entity_titles": {
                    item.id: item.title for item in [*profile.experiences, *profile.projects]
                },
                "experiences": experiences,
                "projects": projects,
                "experience_bullets": {item.id: selected_by_entry[item.id] for item in experiences},
                "project_bullets": {item.id: selected_by_entry[item.id] for item in projects},
                "technical_skills": [
                    candidate.category.model_copy(deep=True) for candidate in selected_skills
                ],
                "selected_skills": [
                    skill.value
                    for candidate in selected_skills
                    for skill in candidate.category.skills
                ],
                "composition_diagnostic": None,
                "hybrid_diagnostic": baseline.hybrid_diagnostic,
            }
        )

    def _diagnostic(
        self,
        final: _EvaluatedState,
        profile: MasterProfile,
        context: _PostingContext,
        candidate_pool: _CandidatePool,
        bullets: list[_BulletCandidate],
        experience_packages: dict[str, list[_ExperiencePackage]],
        skills: list[_SkillCandidate],
        iterations: list[PageFillIterationDiagnostic],
        overflow_sources: dict[str, float],
        redundancy_by_source: dict[str, float],
        verification_failure: str | None,
        *,
        termination_reason: CompositionTerminationReason,
        bound_excluded_sources: set[str],
        bound_exclusion_reasons: dict[str, str],
        best_estimated_utilization: float,
        best_exact_utilization: float | None,
        estimated_evaluations: int,
        exact_evaluations: int,
        expansion_operations: int,
        constraints: TemplateConstraints,
        additional_evidence_unavailable: bool,
        outcome: CompositionOutcome,
        reason: str,
        baseline_selected_entry_ids: set[str] | None,
    ) -> ResumeCompositionDiagnostic:
        selected_bullets = {
            item.evidence_id: item for item in bullets if item.evidence_id in final.state.bullet_ids
        }
        bullet_candidate_by_id = {item.evidence_id: item for item in bullets}
        selected_source_evidence_ids = {
            source_id
            for item in selected_bullets.values()
            for source_id in item.source_evidence_ids
        }
        selected_entries = {item.entry_id for item in selected_bullets.values()}
        selected_candidates: list[CompositionCandidateDiagnostic] = []
        for entry in [*profile.experiences, *profile.projects]:
            entry_bullets = [
                candidate
                for candidate in selected_bullets.values()
                if candidate.entry_id == entry.id
            ]
            if not entry_bullets:
                continue
            selected_candidates.append(
                CompositionCandidateDiagnostic(
                    candidate_id=f"{entry.kind.value}_entry:{entry.id}",
                    kind=(
                        CompositionCandidateKind.EXPERIENCE_ENTRY
                        if entry.kind == EntityKind.EXPERIENCE
                        else CompositionCandidateKind.PROJECT_ENTRY
                    ),
                    entry_id=entry.id,
                    source_ids=[entry.id, *[item.evidence_id for item in entry_bullets]],
                    provenance=[
                        f"profile.{entry.kind.value}s[{entry.id}]",
                        *[provenance for item in entry_bullets for provenance in item.provenance],
                    ],
                    relevance_score=round(sum(item.score for item in entry_bullets), 2),
                    estimated_lines=(2 + sum(item.estimated_lines for item in entry_bullets)),
                    matched_requirements=sorted(
                        {label for item in entry_bullets for label in item.coverage_labels}
                    ),
                    normalized_features=sorted(
                        {feature for item in entry_bullets for feature in item.normalized_features}
                    ),
                    meaningful_overlap=sorted(
                        {match for item in entry_bullets for match in item.meaningful_overlap}
                    ),
                    selected=True,
                    contextual_relevance=round(
                        sum(item.contextual_relevance for item in entry_bullets),
                        2,
                    ),
                    intrinsic_evidence_strength=round(
                        sum(item.intrinsic_evidence_strength for item in entry_bullets),
                        2,
                    ),
                    portfolio_contribution=round(
                        sum(item.score for item in entry_bullets),
                        2,
                    ),
                    selection_reason=(
                        "Opened as a coherent metadata-plus-bullets block because its "
                        "evidence added positive marginal posting coverage."
                    ),
                )
            )
            for candidate in entry_bullets:
                distinct_contribution = self._distinct_contribution(
                    candidate,
                    [
                        item
                        for item in selected_bullets.values()
                        if item.evidence_id != candidate.evidence_id
                    ],
                )
                selected_candidates.append(
                    self._candidate_diagnostic(
                        candidate,
                        selected=True,
                        redundancy_penalty=redundancy_by_source.get(
                            candidate.evidence_id,
                            0,
                        ),
                        selection_reason=(
                            "Selected despite estimated awkward wrapping because its "
                            "reviewed relevance and requirement coverage outweighed the "
                            "secondary line-fit penalty."
                            if candidate.line_fit.future_rewrite_recommended
                            else distinct_contribution
                        ),
                    )
                )
        for skill_candidate in skills:
            if skill_candidate.category_id not in final.state.skill_category_ids:
                continue
            selected_candidates.append(
                CompositionCandidateDiagnostic(
                    candidate_id=f"skill_category:{skill_candidate.category_id}",
                    kind=CompositionCandidateKind.SKILL_CATEGORY,
                    source_ids=[
                        skill_candidate.category_id,
                        *[skill.id or "" for skill in skill_candidate.category.skills if skill.id],
                    ],
                    provenance=list(skill_candidate.provenance),
                    relevance_score=skill_candidate.score,
                    estimated_lines=1,
                    matched_requirements=list(skill_candidate.coverage_labels),
                    normalized_features=list(skill_candidate.normalized_features),
                    meaningful_overlap=list(skill_candidate.meaningful_overlap),
                    selected=True,
                    selection_reason=(
                        skill_candidate.one_skill_exception_reason
                        or "Selected a meaningful reviewed skill row with complementary "
                        "portfolio value without exposing the full master list."
                    ),
                    redundancy_penalty=redundancy_by_source.get(
                        skill_candidate.category_id,
                        0,
                    ),
                    admission_reason=skill_candidate.construction_reason,
                    expansion_type=CompositionCandidateKind.SKILL_CATEGORY.value,
                    skill_support_status=_skill_support_status(skill_candidate),
                    evidence_relationship=skill_candidate.relationship,
                )
            )
        for index, education in enumerate(profile.education):
            if education.awards or education.gpa:
                selected_candidates.append(
                    CompositionCandidateDiagnostic(
                        candidate_id=f"education_detail:{index}:awards-gpa",
                        kind=CompositionCandidateKind.EDUCATION_DETAIL,
                        source_ids=[f"education:{index}:awards-gpa"],
                        provenance=[
                            f"profile.education[{index}].awards",
                            f"profile.education[{index}].gpa",
                        ],
                        relevance_score=0,
                        estimated_lines=1,
                        selected=True,
                        selection_reason=(
                            "Retained reviewed education detail in the mandatory base."
                        ),
                    )
                )
            if education.relevant_coursework:
                selected_candidates.append(
                    CompositionCandidateDiagnostic(
                        candidate_id=f"education_detail:{index}:coursework",
                        kind=CompositionCandidateKind.EDUCATION_DETAIL,
                        source_ids=[f"education:{index}:coursework"],
                        provenance=[f"profile.education[{index}].relevant_coursework"],
                        relevance_score=0,
                        estimated_lines=1,
                        selected=True,
                        selection_reason="Retained reviewed coursework in the mandatory base.",
                    )
                )

        excluded: list[CompositionCandidateDiagnostic] = []
        unused_admissible: list[CompositionCandidateDiagnostic] = []
        excluded_by_bounds: list[CompositionCandidateDiagnostic] = []
        excluded_by_thresholds: list[CompositionCandidateDiagnostic] = []
        selected_entry_ids = {bullet.entry_id for bullet in selected_bullets.values()}
        for candidate in bullets:
            if candidate.evidence_id in final.state.bullet_ids:
                continue
            penalty, duplicate = self._redundancy_penalty(
                candidate,
                final.state,
                {item.evidence_id: item for item in bullets},
            )
            dominance_penalty, dominated, dominance_relationship = self._dominance_penalty(
                candidate,
                final.state,
                {item.evidence_id: item for item in bullets},
            )
            penalty += dominance_penalty
            opening_penalty = 6.0 if candidate.entry_id not in selected_entry_ids else 0.0
            marginal_score = candidate.score - penalty - opening_penalty
            proposal_fits_bounds = self._within_planning_bounds(
                _State(
                    final.state.bullet_ids | {candidate.evidence_id},
                    final.state.skill_category_ids,
                ),
                profile,
                {item.evidence_id: item for item in bullets},
                constraints,
            )
            coherence_failed = (
                candidate.entry_kind is EntityKind.EXPERIENCE
                and candidate.entry_id not in selected_entry_ids
                and candidate.entry_id not in experience_packages
            )
            pruning_bound: str | None = None
            if coherence_failed:
                exclusion = (
                    "The professional experience could not form a coherent block of at "
                    "least two independently valuable bullets, and no typed exception applied."
                )
                category = CandidateExclusionCategory.COHERENT_BLOCK_MINIMUM
            elif candidate.evidence_id in overflow_sources:
                exclusion = "Rendered expansion overflowed one page and was rolled back."
                category = CandidateExclusionCategory.OVERFLOW
            elif candidate.evidence_id in bound_excluded_sources or not proposal_fits_bounds:
                pruning_bound = bound_exclusion_reasons.get(
                    candidate.evidence_id,
                    self._planning_bound_reason(
                        _State(
                            final.state.bullet_ids | {candidate.evidence_id},
                            final.state.skill_category_ids,
                        ),
                        profile,
                        {item.evidence_id: item for item in bullets},
                        constraints,
                    ),
                )
                exclusion = f"Pruned by explicit bound: {pruning_bound}."
                category = CandidateExclusionCategory.SEARCH_BOUND
            elif dominated:
                exclusion = dominance_relationship or (
                    "Suppressed because stronger selected evidence dominated the same "
                    "portfolio contribution."
                )
                category = CandidateExclusionCategory.REDUNDANCY_THRESHOLD
            elif duplicate or marginal_score < self._minimum_marginal_score:
                exclusion = "Suppressed as duplicate or near-duplicate reviewed evidence."
                category = CandidateExclusionCategory.REDUNDANCY_THRESHOLD
            else:
                exclusion = (
                    "Admissible reviewed evidence remained unused because the selected "
                    "combination ranked higher under the final-plan objective."
                )
                category = CandidateExclusionCategory.FINAL_PLAN_OBJECTIVE
            proposed_package_bullet_count = (
                sum(
                    item.entry_id == candidate.entry_id
                    for item in selected_bullets.values()
                )
                + 1
            )
            diagnostic = self._candidate_diagnostic(
                candidate,
                selected=False,
                redundancy_penalty=penalty,
                exclusion_reason=exclusion,
                exclusion_category=category,
                dominance_relationship=dominance_relationship,
                unique_capability_retained=bool(
                    _unique_coverage(
                        set(candidate.coverage_keys),
                        self._state_coverage(
                            final.state,
                            {item.evidence_id: item for item in bullets},
                            {item.category_id: item for item in skills},
                        ),
                    )
                ),
                package_id=(
                    f"proposed-package:{candidate.entry_id}:"
                    f"{proposed_package_bullet_count}"
                ),
                package_bullet_count=proposed_package_bullet_count,
                page_cost=candidate.line_fit.total_vertical_line_cost,
                pruning_bound=(
                    pruning_bound
                    if category is CandidateExclusionCategory.SEARCH_BOUND
                    else None
                ),
                would_improve_density=(
                    final.evaluation.utilization_ratio
                    < TEMPLATE_V1_PREFERRED_DENSITY_FLOOR
                    if category is CandidateExclusionCategory.SEARCH_BOUND
                    else None
                ),
            )
            excluded.append(diagnostic)
            if category is CandidateExclusionCategory.SEARCH_BOUND:
                excluded_by_bounds.append(diagnostic)
            elif category in {
                CandidateExclusionCategory.REDUNDANCY_THRESHOLD,
                CandidateExclusionCategory.COHERENT_BLOCK_MINIMUM,
            }:
                excluded_by_thresholds.append(diagnostic)
            elif category is CandidateExclusionCategory.FINAL_PLAN_OBJECTIVE:
                unused_admissible.append(diagnostic)

        for candidate in candidate_pool.ranking_bound_excluded_bullets:
            diagnostic = self._candidate_diagnostic(
                candidate,
                selected=False,
                redundancy_penalty=0,
                exclusion_reason=(
                    "Relevant reviewed evidence was excluded only by the ranked-candidate "
                    "pool bound."
                ),
                exclusion_category=CandidateExclusionCategory.SEARCH_BOUND,
            )
            excluded.append(diagnostic)
            excluded_by_bounds.append(diagnostic)

        for candidate in candidate_pool.redundancy_excluded_bullets:
            diagnostic = self._candidate_diagnostic(
                candidate,
                selected=False,
                redundancy_penalty=candidate.score,
                exclusion_reason=("Suppressed as duplicate or near-duplicate reviewed evidence."),
                exclusion_category=CandidateExclusionCategory.REDUNDANCY_THRESHOLD,
            )
            excluded.append(diagnostic)
            excluded_by_thresholds.append(diagnostic)

        for candidate in candidate_pool.relevance_excluded_bullets:
            diagnostic = self._candidate_diagnostic(
                candidate,
                selected=False,
                redundancy_penalty=0,
                exclusion_reason=(
                    "Rejected because overlap was limited to low-information generic actions."
                    if candidate.generic_only_rejected
                    else "Reviewed evidence did not meet the specific posting-relevance "
                    "or transferable-capability admission threshold."
                ),
                exclusion_category=CandidateExclusionCategory.RELEVANCE_THRESHOLD,
            )
            excluded_by_thresholds.append(diagnostic)

        selected_bullet_text = _normalize(
            " ".join(candidate.text for candidate in selected_bullets.values())
        )
        selected_coverage = {
            coverage
            for category_id in final.state.skill_category_ids
            for coverage in {item.category_id: item for item in skills}[category_id].coverage_keys
        }
        for skill_candidate in skills:
            if skill_candidate.category_id in final.state.skill_category_ids:
                continue
            repeated = len(set(skill_candidate.coverage_keys) & selected_coverage)
            penalty = min(skill_candidate.score * 0.35, repeated * 8.0)
            evidence_supported = any(
                _contains_phrase(selected_bullet_text, _normalize(skill.value))
                for skill in skill_candidate.category.skills
            )
            if not evidence_supported:
                declared_only_fraction = len(skill_candidate.declared_only_skill_ids) / max(
                    1,
                    len(skill_candidate.category.skills),
                )
                penalty += 3.0 + (declared_only_fraction * 2.0)
            marginal_score = (skill_candidate.score * 0.42) - penalty
            if len(final.state.skill_category_ids) >= constraints.max_skill_lines:
                exclusion = (
                    "Relevant reviewed skill row was excluded only by the explicit skill-row bound."
                )
                category = CandidateExclusionCategory.SEARCH_BOUND
            elif marginal_score < self._minimum_marginal_score:
                exclusion = (
                    "Reviewed skill row lacked distinct support in the selected evidence "
                    "or repeated already-covered requirements."
                )
                category = CandidateExclusionCategory.REDUNDANCY_THRESHOLD
            else:
                exclusion = (
                    "Admissible reviewed skill row remained unused because the selected "
                    "combination ranked higher under the final-plan objective."
                )
                category = CandidateExclusionCategory.FINAL_PLAN_OBJECTIVE
            diagnostic = CompositionCandidateDiagnostic(
                candidate_id=f"skill_category:{skill_candidate.category_id}",
                kind=CompositionCandidateKind.SKILL_CATEGORY,
                source_ids=[skill_candidate.category_id],
                provenance=list(skill_candidate.provenance),
                relevance_score=skill_candidate.score,
                estimated_lines=1,
                matched_requirements=list(skill_candidate.coverage_labels),
                normalized_features=list(skill_candidate.normalized_features),
                meaningful_overlap=list(skill_candidate.meaningful_overlap),
                selected=False,
                exclusion_reason=exclusion,
                exclusion_category=category,
                redundancy_penalty=penalty,
                admission_reason=skill_candidate.construction_reason,
                expansion_type=CompositionCandidateKind.SKILL_CATEGORY.value,
                skill_support_status=_skill_support_status(skill_candidate),
                evidence_relationship=skill_candidate.relationship,
            )
            excluded.append(diagnostic)
            if category is CandidateExclusionCategory.SEARCH_BOUND:
                excluded_by_bounds.append(diagnostic)
            elif category is CandidateExclusionCategory.REDUNDANCY_THRESHOLD:
                excluded_by_thresholds.append(diagnostic)
            else:
                unused_admissible.append(diagnostic)
        excluded.sort(
            key=lambda item: (
                -item.relevance_score,
                item.kind.value,
                item.candidate_id,
            )
        )
        for collection in (
            unused_admissible,
            excluded_by_bounds,
            excluded_by_thresholds,
        ):
            collection.sort(
                key=lambda item: (
                    -item.relevance_score,
                    item.kind.value,
                    item.candidate_id,
                )
            )
        bullet_counts = Counter(candidate.entry_id for candidate in selected_bullets.values())
        selected_skill_candidates = [
            candidate
            for candidate in skills
            if candidate.category_id in final.state.skill_category_ids
        ]
        desired_skill_category_count = min(3, len(skills), constraints.max_skill_lines)
        skill_category_shortfall_reason = (
            (
                "The reviewed profile contained fewer than three credible, "
                "posting-relevant skill categories."
                if len(skills) < 3
                else "Additional credible skill categories were omitted because exact "
                "page fit or stronger evidence won the final-plan comparison."
            )
            if len(selected_skill_candidates) < 3
            else None
        )
        all_relevant_bullets = [
            *bullets,
            *candidate_pool.ranking_bound_excluded_bullets,
        ]
        excluded_reason_by_source: dict[str, str] = {}
        for candidate_diagnostic in [
            *excluded,
            *excluded_by_thresholds,
            *excluded_by_bounds,
            *unused_admissible,
        ]:
            for source_id in candidate_diagnostic.source_ids:
                excluded_reason_by_source.setdefault(
                    source_id,
                    candidate_diagnostic.exclusion_reason
                    or "Not selected by the final portfolio objective.",
                )
        entry_bullet_selections: list[EntryBulletSelectionDiagnostic] = []
        for entry in [*profile.experiences, *profile.projects]:
            available_ids = [
                evidence.id
                for evidence in profile.evidence
                if evidence.confirmed and evidence.entity_id == entry.id
            ]
            if not available_ids:
                continue
            selected_ids = [
                evidence_id
                for evidence_id in available_ids
                if evidence_id in selected_source_evidence_ids
            ]
            distinct_contributions: dict[str, str] = {}
            evidence_relationships: dict[str, EvidenceRelationship] = {}
            marginal_contributions: dict[str, float] = {}
            for evidence_id in selected_ids:
                selected_candidate = next(
                    (
                        candidate
                        for candidate in selected_bullets.values()
                        if evidence_id in candidate.source_evidence_ids
                    ),
                    None,
                )
                if selected_candidate is not None:
                    evidence_relationships[evidence_id] = selected_candidate.relationship
                    marginal_contributions[evidence_id] = round(
                        selected_candidate.score
                        - redundancy_by_source.get(
                            selected_candidate.evidence_id,
                            0,
                        ),
                        2,
                    )
                    distinct_contributions[evidence_id] = self._distinct_contribution(
                        selected_candidate,
                        [
                            item
                            for item in selected_bullets.values()
                            if item.evidence_id != selected_candidate.evidence_id
                        ],
                    )
            entry_bullet_selections.append(
                EntryBulletSelectionDiagnostic(
                    entry_id=entry.id,
                    entry_kind=entry.kind.value,
                    available_bullet_ids=available_ids,
                    selected_bullet_ids=selected_ids,
                    omitted_bullet_reasons={
                        evidence_id: excluded_reason_by_source.get(
                            evidence_id,
                            "Reviewed evidence did not clear the relevance threshold.",
                        )
                        for evidence_id in available_ids
                        if evidence_id not in selected_source_evidence_ids
                    },
                    retained_all_available_bullets=(
                        bool(available_ids) and len(selected_ids) == len(available_ids)
                    ),
                    distinct_contributions=distinct_contributions,
                    evidence_relationships=evidence_relationships,
                    marginal_contributions=marginal_contributions,
                )
            )
        credible_project_ids = sorted(self._credible_project_ids(all_relevant_bullets))
        selected_project_bullet_counts = Counter(
            candidate.entry_id
            for candidate in selected_bullets.values()
            if candidate.entry_kind is EntityKind.PROJECT
        )
        substantive_project_ids = sorted(
            entry_id for entry_id, count in selected_project_bullet_counts.items() if count >= 2
        )
        selected_project_ids = [item.id for item in profile.projects if item.id in selected_entries]
        if substantive_project_ids:
            project_representation = ProjectRepresentationDiagnostic(
                status=ProjectRepresentationStatus.SUBSTANTIVE_PROJECT,
                selected_project_ids=selected_project_ids,
                substantive_project_ids=substantive_project_ids,
                credible_project_ids=credible_project_ids,
                reason=(
                    "At least one selected project retained multiple independently valuable "
                    "reviewed bullets and communicates substantive technical scope."
                ),
            )
        elif selected_project_ids:
            project_representation = ProjectRepresentationDiagnostic(
                status=ProjectRepresentationStatus.SHALLOW_PROJECT_EXCEPTION,
                selected_project_ids=selected_project_ids,
                credible_project_ids=credible_project_ids,
                reason=(
                    "The final portfolio retained only one bullet per selected project. "
                    "Every compatible second bullet lost marginal-value, redundancy, "
                    "page-fit, or final-objective comparison; the retained project evidence "
                    "still supplied distinct coverage despite its fixed block cost."
                ),
            )
        elif credible_project_ids:
            project_representation = ProjectRepresentationDiagnostic(
                status=ProjectRepresentationStatus.ZERO_PROJECT_EXCEPTION,
                credible_project_ids=credible_project_ids,
                reason=(
                    "Credible multi-bullet project evidence existed, but every project "
                    "portfolio lost the bounded quality, relevance, redundancy, line-cost, "
                    "and page-fit comparison to the selected non-project portfolio."
                ),
            )
        else:
            project_representation = ProjectRepresentationDiagnostic(
                status=ProjectRepresentationStatus.NO_CREDIBLE_PROJECT_EVIDENCE,
                reason=(
                    "The reviewed profile contained no project with at least two admitted "
                    "posting-relevant or strongly complementary bullets."
                ),
            )
        selected_skill_rows = [
            SkillRowSelectionDiagnostic(
                row_id=candidate.category_id,
                label=candidate.label,
                source_category_ids=list(candidate.source_category_ids),
                skill_ids=[skill.id or "" for skill in candidate.category.skills if skill.id],
                skill_values=[skill.value for skill in candidate.category.skills],
                provenance=list(candidate.provenance),
                relationship=candidate.relationship,
                estimated_available_width_points=candidate.estimated_available_width_points,
                estimated_used_width_points=candidate.estimated_used_width_points,
                estimated_remaining_width_points=candidate.estimated_remaining_width_points,
                estimated_used_width_ratio=candidate.estimated_used_width_ratio,
                compatible_omitted_skill_values=list(candidate.compatible_omitted_skill_values),
                underfill_exception_reason=candidate.underfill_exception_reason,
                one_skill_exception_reason=candidate.one_skill_exception_reason,
                grouping_reason=candidate.grouping_reason,
            )
            for candidate in selected_skill_candidates
        ]
        selected_skill_requirement_ids = {
            coverage_key.removeprefix("requirement:")
            for candidate in selected_skill_candidates
            for coverage_key in candidate.coverage_keys
            if coverage_key.startswith("requirement:")
        }
        evidence_by_id = {item.id: item for item in profile.evidence if item.confirmed}
        requirement_coverage: list[RequirementCoverageDiagnostic] = []
        for requirement in context.requirements.requirements:
            if requirement.authority is RequirementAuthority.INCIDENTAL:
                continue
            matching_bullets = [
                candidate
                for candidate in selected_bullets.values()
                if requirement.id
                in {
                    *candidate.direct_requirement_ids,
                    *candidate.adjacent_requirement_ids,
                    *candidate.complementary_requirement_ids,
                }
            ]
            profile_sections = (
                ["education"]
                if _education_satisfies_requirement(profile, requirement.text)
                else []
            )
            if "education" in profile_sections:
                # Reviewed education is the authoritative source for degree
                # requirements; semantically adjacent project prose must not
                # be presented as supporting degree evidence.
                matching_bullets = []
            if requirement.id in selected_skill_requirement_ids:
                profile_sections.append("technical_skills")
            component_labels = requirement.material_components or [requirement.text]
            component_matches: list[RequirementComponentMatch] = []
            component_bullets: list[_BulletCandidate] = []
            for component in component_labels:
                supporting_candidates: list[_BulletCandidate] = []
                supporting_evidence_ids: list[str] = []
                for candidate in selected_bullets.values():
                    candidate_supporting_ids = [
                        evidence_id
                        for evidence_id in candidate.source_evidence_ids
                        if (evidence := evidence_by_id.get(evidence_id)) is not None
                        and requirement_component_supported(
                            component,
                            " ".join(
                                [
                                    evidence.source_text,
                                    *evidence.technologies,
                                    *evidence.capabilities,
                                    *evidence.outcomes,
                                ]
                            ),
                        )
                    ]
                    if candidate_supporting_ids:
                        supporting_candidates.append(candidate)
                        supporting_evidence_ids.extend(candidate_supporting_ids)
                if not requirement.material_components:
                    supporting_candidates = matching_bullets
                    supporting_evidence_ids = [
                        evidence_id
                        for candidate in matching_bullets
                        for evidence_id in candidate.source_evidence_ids
                    ]
                component_bullets.extend(supporting_candidates)
                component_profile_sections = (
                    profile_sections if len(component_labels) == 1 else []
                )
                component_matches.append(
                    RequirementComponentMatch(
                        component=component,
                        normalized_component=normalize_reviewed_text(component),
                        supported=bool(
                            supporting_candidates or component_profile_sections
                        ),
                        supporting_evidence_ids=list(dict.fromkeys(supporting_evidence_ids)),
                        supporting_entry_ids=list(
                            dict.fromkeys(item.entry_id for item in supporting_candidates)
                        ),
                        relationships=list(
                            dict.fromkeys(item.relationship for item in supporting_candidates)
                        ),
                        satisfied_by_profile_sections=component_profile_sections,
                    )
                )
            attributed_bullets = list(
                {
                    item.evidence_id: item
                    for item in [*matching_bullets, *component_bullets]
                }.values()
            )
            fully_covered = bool(component_matches) and all(
                item.supported for item in component_matches
            )
            requirement_coverage.append(
                RequirementCoverageDiagnostic(
                    requirement_id=requirement.id,
                    text=requirement.text,
                    authority=requirement.authority,
                    importance=requirement.importance,
                    selected_entry_ids=list(
                        dict.fromkeys(item.entry_id for item in attributed_bullets)
                    ),
                    selected_bullet_ids=[item.evidence_id for item in attributed_bullets],
                    supporting_evidence_ids=list(
                        dict.fromkeys(
                            evidence_id
                            for component in component_matches
                            for evidence_id in component.supporting_evidence_ids
                        )
                    ),
                    relationships=list(
                        dict.fromkeys(item.relationship for item in attributed_bullets)
                    ),
                    satisfied_by_profile_sections=profile_sections,
                    component_matches=component_matches,
                    fully_covered=fully_covered,
                )
            )
        portfolio_coverage_gaps = [
            item.text
            for item in requirement_coverage
            if item.authority in {RequirementAuthority.CORE, RequirementAuthority.IMPORTANT}
            and not item.fully_covered
        ]
        selected_complementary_ids = [
            candidate.evidence_id
            for candidate in selected_bullets.values()
            if candidate.relationship is EvidenceRelationship.COMPLEMENTARY
        ]
        exclusion_by_candidate_id = {
            item.candidate_id: item.exclusion_reason or "Lost the final portfolio comparison."
            for item in excluded
        }
        direct_candidate_tradeoffs = [
            DirectCandidateTradeoffDiagnostic(
                omitted_candidate_id=candidate.evidence_id,
                selected_complementary_candidate_ids=selected_complementary_ids,
                reason=exclusion_by_candidate_id.get(
                    f"bullet:{candidate.evidence_id}",
                    "The direct candidate did not clear a bounded relevance, redundancy, "
                    "cost, or page-fit comparison.",
                ),
            )
            for candidate in all_relevant_bullets
            if candidate.relationship is EvidenceRelationship.DIRECT
            and candidate.evidence_id not in final.state.bullet_ids
            and selected_complementary_ids
        ]
        entry_package_metrics: dict[
            str, tuple[str, float, float, float, set[str], str, float]
        ] = {}
        entry_kind_by_id = {
            entry.id: entry.kind.value for entry in [*profile.experiences, *profile.projects]
        }
        for entry_id, packages in experience_packages.items():
            if not packages:
                continue
            selected_package_bullet_ids = {
                item.evidence_id
                for item in selected_bullets.values()
                if item.entry_id == entry_id
            }
            package = next(
                (
                    item
                    for item in packages
                    if selected_package_bullet_ids
                    and set(item.bullet_ids) == selected_package_bullet_ids
                ),
                packages[0],
            )
            package_candidates = [
                bullet_candidate_by_id[bullet_id]
                for bullet_id in package.bullet_ids
                if bullet_id in bullet_candidate_by_id
            ]
            current_weighted = sum(
                score * weight
                for score, weight in zip(
                    sorted((item.score for item in package_candidates), reverse=True),
                    (1.0, 0.75, 0.35, 0.15),
                    strict=False,
                )
            )
            source_weighted = sum(
                score * weight
                for score, weight in zip(
                    sorted(
                        (item.source_alternative_score for item in package_candidates),
                        reverse=True,
                    ),
                    (1.0, 0.75, 0.35, 0.15),
                    strict=False,
                )
            )
            source_only_score = (
                package.total_score
                - package.writing_quality
                - current_weighted
                + source_weighted
            )
            entry_package_metrics[entry_id] = (
                EntityKind.EXPERIENCE.value,
                package.total_score,
                package.page_cost,
                package.redundancy_penalty,
                set(package.distinct_coverage),
                package.package_id,
                round(source_only_score, 2),
            )
        project_candidates: dict[str, list[_BulletCandidate]] = {}
        for candidate in all_relevant_bullets:
            if candidate.entry_kind is EntityKind.PROJECT and candidate.admitted:
                project_candidates.setdefault(candidate.entry_id, []).append(candidate)
        for entry_id, candidates in project_candidates.items():
            ranked = sorted(candidates, key=lambda item: (-item.score, item.evidence_id))[:4]
            page_cost = 1.5 + sum(item.line_fit.total_vertical_line_cost for item in ranked)
            redundancy = sum(
                _near_duplicate(item.text, other.text) * min(item.score, other.score) * 0.18
                for index, item in enumerate(ranked)
                for other in ranked[index + 1 :]
            )
            score = sum(
                item.score * weight
                for item, weight in zip(ranked, (1.0, 0.75, 0.35, 0.15), strict=False)
            ) - redundancy - (page_cost * 0.4)
            source_only_score = sum(
                item.source_alternative_score * weight
                for item, weight in zip(
                    sorted(ranked, key=lambda item: -item.source_alternative_score),
                    (1.0, 0.75, 0.35, 0.15),
                    strict=False,
                )
            ) - redundancy - (page_cost * 0.4)
            entry_package_metrics[entry_id] = (
                EntityKind.PROJECT.value,
                round(score, 2),
                round(page_cost, 2),
                round(redundancy, 2),
                {key for item in ranked for key in item.coverage_keys},
                f"project-package:{entry_id}",
                round(source_only_score, 2),
            )
        omitted_metrics = {
            entry_id: metrics
            for entry_id, metrics in entry_package_metrics.items()
            if entry_id not in selected_entries
        }
        portfolio_marginal_comparisons: list[PortfolioMarginalComparisonDiagnostic] = []
        for entry_id in sorted(selected_entries):
            selected_metrics = entry_package_metrics.get(entry_id)
            if selected_metrics is None:
                continue
            omitted_entry_id, omitted = max(
                omitted_metrics.items(),
                key=lambda item: (item[1][1], item[0]),
                default=(None, None),
            )
            omitted_professional_id, omitted_professional = max(
                (
                    (candidate_id, metrics)
                    for candidate_id, metrics in omitted_metrics.items()
                    if metrics[0] == EntityKind.EXPERIENCE.value
                ),
                key=lambda item: (item[1][1], item[0]),
                default=(None, None),
            )
            omitted_project_id, omitted_project = max(
                (
                    (candidate_id, metrics)
                    for candidate_id, metrics in omitted_metrics.items()
                    if metrics[0] == EntityKind.PROJECT.value
                ),
                key=lambda item: (item[1][1], item[0]),
                default=(None, None),
            )
            unique_requirements = set(selected_metrics[4]) - (
                set(omitted[4]) if omitted is not None else set()
            )
            strongest_source_only_omitted = max(
                (metrics[6] for metrics in omitted_metrics.values()),
                default=float("-inf"),
            )
            portfolio_marginal_comparisons.append(
                PortfolioMarginalComparisonDiagnostic(
                    selected_entry_id=entry_id,
                    selected_entry_kind=entry_kind_by_id.get(entry_id, selected_metrics[0]),
                    selected_package_score=selected_metrics[1],
                    selected_page_cost=selected_metrics[2],
                    strongest_omitted_entry_id=omitted_entry_id,
                    strongest_omitted_entry_kind=(omitted[0] if omitted is not None else None),
                    strongest_omitted_package_score=(
                        omitted[1] if omitted is not None else None
                    ),
                    strongest_omitted_professional_entry_id=omitted_professional_id,
                    strongest_omitted_professional_package_score=(
                        omitted_professional[1]
                        if omitted_professional is not None
                        else None
                    ),
                    strongest_omitted_project_entry_id=omitted_project_id,
                    strongest_omitted_project_package_score=(
                        omitted_project[1] if omitted_project is not None else None
                    ),
                    marginal_gain=(
                        round(selected_metrics[1] - omitted[1], 2)
                        if omitted is not None
                        else None
                    ),
                    page_cost_difference=(
                        round(selected_metrics[2] - omitted[2], 2)
                        if omitted is not None
                        else None
                    ),
                    unique_requirements_contributed=sorted(unique_requirements),
                    redundancy_difference=(
                        round(selected_metrics[3] - omitted[3], 2)
                        if omitted is not None
                        else None
                    ),
                    choice_changed_after_validated_writing=(
                        entry_id not in baseline_selected_entry_ids
                        if baseline_selected_entry_ids is not None
                        else (
                            selected_metrics[1]
                            >= (omitted[1] if omitted is not None else 0.0)
                            and selected_metrics[6] < strongest_source_only_omitted
                        )
                    ),
                    selected_reason=(
                        "Selected by the bounded portfolio and page-fit objective; employer "
                        "identity contributed zero points."
                    ),
                    omitted_reason=(
                        "Strongest omitted entry lost the total relevance, technical depth, "
                        "distinctness, redundancy, metadata, and page-cost comparison."
                        if omitted is not None
                        else None
                    ),
                )
            )
        selected_skill_values = {
            skill.value.casefold()
            for candidate in selected_skill_candidates
            for skill in candidate.category.skills
        }
        source_skill_values = (
            [skill.value for category in profile.technical_skills for skill in category.skills]
            if profile.technical_skills
            else list(profile.declared_skills)
        )
        omitted_direct_skill_values: list[str] = []
        omitted_direct_skill_reasons: dict[str, str] = {}
        empty_features = extract_reviewed_text_features("")
        for value in source_skill_values:
            if value.casefold() in selected_skill_values:
                continue
            features = extract_reviewed_text_features(value)
            assessment = assess_evidence_relationship(
                bullet_text=value,
                bullet_features=features,
                entry_features=empty_features,
                structured_values=[value],
                requirements=context.requirements,
                reviewed_skill=True,
            )
            if assessment.relationship is not EvidenceRelationship.DIRECT:
                continue
            omitted_direct_skill_values.append(value)
            compatible_rows = [
                candidate.label
                for candidate in skills
                if value in candidate.compatible_omitted_skill_values
            ]
            if compatible_rows:
                omitted_direct_skill_reasons[value] = (
                    "The direct reviewed skill was compatible with "
                    + ", ".join(compatible_rows)
                    + ", but adding it would exceed the measured Template V1 row width; "
                    "the selected row retained higher-coverage skills at the same page cost."
                )
            else:
                omitted_direct_skill_reasons[value] = (
                    "The direct reviewed skill lost the normal page-fit comparison to selected "
                    "bullets or skill rows; no truthful compatible row fit within Template V1's "
                    "measured width."
                )
        relevant_unused_entry_ids = {
            candidate.entry_id
            for candidate in all_relevant_bullets
            if candidate.evidence_id not in final.state.bullet_ids
        }
        evidence_entry_ids = {item.id for item in [*profile.experiences, *profile.projects]}
        unused_reviewed_bullet_ids = [
            evidence.id
            for evidence in profile.evidence
            if evidence.confirmed
            and evidence.entity_id in evidence_entry_ids
            and evidence.id not in selected_source_evidence_ids
        ]
        diagnostic_additional_evidence_unavailable = not (unused_admissible or excluded_by_bounds)
        profile_appears_incomplete = _profile_appears_incomplete(profile)
        underfill_reasons = self._underfill_reasons(
            final,
            candidate_pool,
            unused_admissible=unused_admissible,
            excluded_by_bounds=excluded_by_bounds,
            additional_evidence_unavailable=(
                additional_evidence_unavailable and diagnostic_additional_evidence_unavailable
            ),
            profile_appears_incomplete=profile_appears_incomplete,
            termination_reason=termination_reason,
            exact_finalist_limit_reached=(
                exact_evaluations >= self._bounds.maximum_exact_finalist_evaluations
            ),
        )
        latest_experience_year = max(
            (
                year
                for entry in profile.experiences
                for value in (entry.start_date, entry.end_date)
                for year in _years(value)
            ),
            default=0,
        )
        all_best_packages = [
            packages[0] for packages in experience_packages.values() if packages
        ]
        selected_packages_by_entry: dict[str, _ExperiencePackage] = {}
        for selected_entry in profile.experiences:
            selected_entry_candidates = [
                item
                for item in selected_bullets.values()
                if item.entry_id == selected_entry.id
            ]
            if not selected_entry_candidates:
                continue
            selected_exception = (
                self._single_bullet_exception_reason(
                    selected_entry_candidates[0],
                    bullet_candidate_by_id,
                )
                if len(selected_entry_candidates) == 1
                else None
            )
            selected_packages_by_entry[selected_entry.id] = self._score_experience_package(
                selected_entry,
                selected_entry_candidates,
                latest_experience_year,
                single_bullet_exception_reason=selected_exception,
            )
        experience_package_selections: list[ExperiencePackageSelectionDiagnostic] = []
        for entry in profile.experiences:
            entry_candidates = [item for item in bullets if item.entry_id == entry.id]
            if not entry_candidates:
                continue
            alternatives = list(experience_packages.get(entry.id, []))
            selected_entry_candidates = [
                item for item in selected_bullets.values() if item.entry_id == entry.id
            ]
            selected_package = selected_packages_by_entry.get(entry.id)
            if selected_package is not None:
                if selected_package.bullet_ids not in {
                    package.bullet_ids for package in alternatives
                }:
                    alternatives.append(selected_package)
            alternatives.sort(
                key=lambda package: (
                    -package.total_score,
                    -len(package.bullet_ids),
                    package.bullet_ids,
                )
            )
            credibility_affected = False
            if selected_package is not None and selected_package.enterprise_production_contribution:
                selected_without = (
                    selected_package.total_score
                    - selected_package.enterprise_production_contribution
                )
                credibility_affected = any(
                    selected_package.total_score >= other.total_score
                    and selected_without
                    < other.total_score - other.enterprise_production_contribution
                    for other in all_best_packages
                    if other.entry_id != entry.id
                )
            coherent_minimum_failed = not alternatives and bool(entry_candidates)
            highest_selected_package = max(
                (
                    package
                    for selected_entry_id, package in selected_packages_by_entry.items()
                    if selected_entry_id != entry.id
                ),
                key=lambda package: package.total_score,
                default=None,
            )
            if selected_package is not None:
                final_reason = (
                    f"Selected its {len(selected_package.bullet_ids)}-bullet package at "
                    f"package score {selected_package.total_score:.2f} after the bounded "
                    "metadata-plus-bullets and page-fit comparison. Employer identity was "
                    "not scored."
                )
            elif alternatives:
                comparison = (
                    f"; the highest selected experience package was "
                    f"{highest_selected_package.entry_id} at "
                    f"{highest_selected_package.total_score:.2f}"
                    if highest_selected_package is not None
                    else ""
                )
                final_reason = (
                    f"Omitted because its best coherent package scored "
                    f"{alternatives[0].total_score:.2f}{comparison} and did not improve "
                    "the final relevance, strength, distinctness, metadata cost, and page-fit "
                    "portfolio. Employer identity was not scored."
                )
            else:
                final_reason = (
                    "Omitted because fewer than two independently valuable bullets were "
                    "available and no typed single-bullet exception applied. Employer "
                    "identity was not scored."
                )
            experience_package_selections.append(
                ExperiencePackageSelectionDiagnostic(
                    entry_id=entry.id,
                    source_bullets_available=len(entry_candidates),
                    validated_rewrites_available=sum(
                        candidate.writing_variant is not None for candidate in entry_candidates
                    ),
                    best_package_alternatives=[
                        ExperiencePackageAlternativeDiagnostic(
                            package_id=package.package_id,
                            bullet_ids=list(package.bullet_ids),
                            source_evidence_ids=list(package.source_evidence_ids),
                            bullet_count=len(package.bullet_ids),
                            source_bullet_count=sum(
                                bullet_candidate_by_id[bullet_id].writing_variant is None
                                for bullet_id in package.bullet_ids
                            ),
                            rewritten_bullet_count=sum(
                                bullet_candidate_by_id[bullet_id].writing_variant is not None
                                for bullet_id in package.bullet_ids
                            ),
                            package_relevance=package.package_relevance,
                            intrinsic_strength=package.intrinsic_strength,
                            writing_quality=package.writing_quality,
                            duration_recency_contribution=(
                                package.duration_recency_contribution
                            ),
                            enterprise_production_contribution=(
                                package.enterprise_production_contribution
                            ),
                            enterprise_production_evidence=list(
                                package.enterprise_production_evidence
                            ),
                            distinct_coverage=list(package.distinct_coverage),
                            page_cost=package.page_cost,
                            redundancy_penalty=package.redundancy_penalty,
                            total_score=package.total_score,
                            single_bullet_exception_reason=(
                                package.single_bullet_exception_reason
                            ),
                        )
                        for package in alternatives[:6]
                    ],
                    selected_bullet_count=len(selected_entry_candidates),
                    selected_package_id=(
                        selected_package.package_id if selected_package is not None else None
                    ),
                    selected=selected_package is not None,
                    coherent_block_minimum_failed=coherent_minimum_failed,
                    single_bullet_exception_reason=(
                        selected_package.single_bullet_exception_reason
                        if selected_package is not None
                        else None
                    ),
                    enterprise_production_tiebreaker_affected_result=credibility_affected,
                    user_priority_signal=None,
                    final_reason=final_reason,
                )
            )
        return ResumeCompositionDiagnostic(
            outcome=outcome,
            termination_reason=termination_reason,
            selected_experience_ids=[
                item.id for item in profile.experiences if item.id in selected_entries
            ],
            selected_project_ids=[
                item.id for item in profile.projects if item.id in selected_entries
            ],
            selected_bullet_ids=[
                evidence.id
                for evidence in profile.evidence
                if evidence.id in selected_source_evidence_ids
            ],
            bullet_counts=dict(bullet_counts),
            selected_skill_category_ids=[
                candidate.category_id for candidate in selected_skill_candidates
            ],
            selected_skill_category_labels=[
                candidate.label for candidate in selected_skill_candidates
            ],
            credible_skill_category_count=len(skills),
            desired_skill_category_count=desired_skill_category_count,
            skill_category_shortfall_reason=skill_category_shortfall_reason,
            entry_bullet_selections=entry_bullet_selections,
            experience_package_selections=experience_package_selections,
            portfolio_marginal_comparisons=portfolio_marginal_comparisons,
            project_representation=project_representation,
            selected_skill_rows=selected_skill_rows,
            posting_requirements=list(context.requirements.requirements),
            requirement_coverage=requirement_coverage,
            portfolio_coverage_gaps=portfolio_coverage_gaps,
            direct_candidate_tradeoffs=direct_candidate_tradeoffs,
            omitted_direct_skill_values=omitted_direct_skill_values,
            omitted_direct_skill_reasons=omitted_direct_skill_reasons,
            selected_candidates=selected_candidates,
            excluded_high_ranking_candidates=excluded,
            unused_admissible_candidates=unused_admissible,
            candidates_excluded_by_search_bounds=excluded_by_bounds,
            candidates_excluded_by_thresholds=excluded_by_thresholds,
            unused_experience_ids=[
                item.id
                for item in profile.experiences
                if item.id in relevant_unused_entry_ids and item.id not in selected_entries
            ],
            unused_project_ids=[
                item.id
                for item in profile.projects
                if item.id in relevant_unused_entry_ids and item.id not in selected_entries
            ],
            unused_reviewed_bullet_ids=unused_reviewed_bullet_ids,
            unused_relevant_skill_category_ids=[
                candidate.category_id
                for candidate in skills
                if candidate.category_id not in final.state.skill_category_ids
            ],
            page_fill_iterations=iterations,
            overflow_rollbacks=sum(item.overflow for item in iterations),
            final_utilization_ratio=final.evaluation.utilization_ratio,
            best_estimated_utilization_ratio=best_estimated_utilization,
            best_exact_verified_utilization_ratio=best_exact_utilization,
            utilization_target_floor=TEMPLATE_V1_UTILIZATION_TARGET_FLOOR,
            utilization_target_ceiling=TEMPLATE_V1_UTILIZATION_TARGET_CEILING,
            utilization_target_reached=self._in_target_band(final.evaluation.utilization_ratio),
            preferred_density_reached=self._in_preferred_density_band(
                final.evaluation.utilization_ratio
            ),
            preferred_density_status=self._preferred_density_status(
                final.evaluation.utilization_ratio
            ),
            underfill_reasons=underfill_reasons,
            profile_appears_incomplete=profile_appears_incomplete,
            normalized_posting_features=_maximal_phrases(list(context.features.specific_phrases))[
                :30
            ],
            page_count=final.evaluation.page_count,
            verification_status=(
                PageVerificationStatus.EXACT
                if final.evaluation.exact
                else PageVerificationStatus.ESTIMATED
            ),
            verification_provider=final.evaluation.provider,
            verification_failure=verification_failure or final.evaluation.verification_failure,
            additional_evidence_unavailable=(
                additional_evidence_unavailable and diagnostic_additional_evidence_unavailable
            ),
            reason=reason,
            beam_width=self._bounds.beam_width,
            maximum_page_evaluations=(
                self._bounds.maximum_estimated_page_evaluations
                + self._bounds.maximum_exact_finalist_evaluations
            ),
            maximum_estimated_page_evaluations=(self._bounds.maximum_estimated_page_evaluations),
            maximum_exact_finalist_evaluations=(self._bounds.maximum_exact_finalist_evaluations),
            maximum_expansion_operations=self._bounds.maximum_expansion_operations,
            maximum_selected_bullets=self._bounds.maximum_selected_bullets,
            maximum_selected_entries=self._bounds.maximum_selected_entries,
            estimated_page_evaluations=estimated_evaluations,
            exact_page_evaluations=exact_evaluations,
            expansion_operations=expansion_operations,
            maximum_search_depth=None,
        )

    @staticmethod
    def _candidate_diagnostic(
        candidate: _BulletCandidate,
        *,
        selected: bool,
        redundancy_penalty: float,
        selection_reason: str | None = None,
        exclusion_reason: str | None = None,
        exclusion_category: CandidateExclusionCategory | None = None,
        dominance_relationship: str | None = None,
        unique_capability_retained: bool = False,
        package_id: str | None = None,
        package_bullet_count: int | None = None,
        page_cost: float | None = None,
        pruning_bound: str | None = None,
        would_improve_density: bool | None = None,
    ) -> CompositionCandidateDiagnostic:
        return CompositionCandidateDiagnostic(
            candidate_id=f"bullet:{candidate.evidence_id}",
            kind=(
                CompositionCandidateKind.EXPERIENCE_BULLET
                if candidate.entry_kind == EntityKind.EXPERIENCE
                else CompositionCandidateKind.PROJECT_BULLET
            ),
            entry_id=candidate.entry_id,
            source_ids=list(candidate.source_evidence_ids),
            provenance=list(candidate.provenance),
            relevance_score=candidate.score,
            estimated_lines=candidate.estimated_lines,
            matched_requirements=list(candidate.coverage_labels),
            selected=selected,
            selection_reason=selection_reason,
            exclusion_reason=exclusion_reason,
            exclusion_category=exclusion_category,
            redundancy_penalty=redundancy_penalty,
            normalized_features=list(candidate.normalized_features),
            meaningful_overlap=list(candidate.meaningful_overlap),
            generic_only_rejected=candidate.generic_only_rejected,
            admission_reason=candidate.admission_reason,
            expansion_type=(
                CompositionCandidateKind.EXPERIENCE_BULLET.value
                if candidate.entry_kind == EntityKind.EXPERIENCE
                else CompositionCandidateKind.PROJECT_BULLET.value
            ),
            line_fit=candidate.line_fit,
            contextual_relevance=candidate.contextual_relevance,
            intrinsic_evidence_strength=candidate.intrinsic_evidence_strength,
            portfolio_contribution=round(
                candidate.score - redundancy_penalty,
                2,
            ),
            dominance_relationship=dominance_relationship,
            unique_capability_retained=unique_capability_retained,
            evidence_relationship=candidate.relationship,
            direct_requirement_ids=list(candidate.direct_requirement_ids),
            adjacent_requirement_ids=list(candidate.adjacent_requirement_ids),
            complementary_requirement_ids=list(candidate.complementary_requirement_ids),
            incidental_requirement_ids=list(candidate.incidental_requirement_ids),
            short_token_contributions=list(candidate.short_token_contributions),
            marginal_contribution=round(
                candidate.score - redundancy_penalty,
                2,
            ),
            writing_variant_id=(
                candidate.writing_variant.variant_id
                if candidate.writing_variant is not None
                else None
            ),
            package_id=package_id,
            package_bullet_count=package_bullet_count,
            page_cost=page_cost,
            pruning_bound=pruning_bound,
            would_improve_density=would_improve_density,
        )

    @staticmethod
    def _distinct_contribution(
        candidate: _BulletCandidate,
        other_selected: list[_BulletCandidate],
    ) -> str:
        other_coverage = {coverage for item in other_selected for coverage in item.coverage_keys}
        unique_labels = [
            label
            for key, label in zip(
                candidate.coverage_keys,
                candidate.coverage_labels,
                strict=True,
            )
            if key not in other_coverage
        ]
        other_features = {
            feature for item in other_selected for feature in item.normalized_features
        }
        unique_features = [
            feature for feature in candidate.normalized_features if feature not in other_features
        ][:3]
        contributions: list[str] = []
        if unique_labels:
            contributions.append("distinct requirement coverage: " + ", ".join(unique_labels[:3]))
        if unique_features:
            contributions.append(
                "distinct reviewed technical evidence: " + ", ".join(unique_features)
            )
        if candidate.writing_variant is not None and candidate.writing_variant.material_improvement:
            contributions.append(
                "validated wording improvement: "
                + ", ".join(candidate.writing_variant.improvement_reasons[:2])
            )
        if candidate.intrinsic_evidence_strength >= 18.0:
            contributions.append("strong intrinsic evidence or supported outcome")
        if not contributions:
            contributions.append(
                "positive independent relevance and entry context after diminishing returns"
            )
        return "Selected for " + "; ".join(contributions) + "."

    @staticmethod
    def _underfill_reasons(
        final: _EvaluatedState,
        candidate_pool: _CandidatePool,
        *,
        unused_admissible: list[CompositionCandidateDiagnostic],
        excluded_by_bounds: list[CompositionCandidateDiagnostic],
        additional_evidence_unavailable: bool,
        profile_appears_incomplete: bool,
        termination_reason: CompositionTerminationReason,
        exact_finalist_limit_reached: bool,
    ) -> list[CompositionUnderfillReason]:
        if final.evaluation.utilization_ratio >= TEMPLATE_V1_PREFERRED_DENSITY_FLOOR:
            return []
        reasons: list[CompositionUnderfillReason] = []
        if not final.evaluation.exact:
            reasons.append(CompositionUnderfillReason.PAGINATION_UNVERIFIED)
        if profile_appears_incomplete:
            reasons.append(CompositionUnderfillReason.PROFILE_INCOMPLETE)
        if (
            exact_finalist_limit_reached
            or excluded_by_bounds
            or termination_reason
            in {
                CompositionTerminationReason.ESTIMATED_EVALUATION_LIMIT,
                CompositionTerminationReason.EXPANSION_OPERATION_LIMIT,
            }
        ):
            reasons.append(CompositionUnderfillReason.SEARCH_BOUNDS_LIMITED)
        elif unused_admissible:
            reasons.append(CompositionUnderfillReason.QUALITY_LIMITED)
        elif additional_evidence_unavailable:
            if candidate_pool.relevance_excluded_bullets:
                reasons.append(CompositionUnderfillReason.JOB_MATCH_LIMITED)
            else:
                reasons.append(CompositionUnderfillReason.EVIDENCE_LIMITED)
        if (
            final.evaluation.utilization_ratio < TEMPLATE_V1_DENSITY_INVESTIGATION_FLOOR
            and not candidate_pool.ranked_bullets
            and any(candidate.admitted for candidate in candidate_pool.relevance_excluded_bullets)
        ):
            reasons.append(CompositionUnderfillReason.CANDIDATE_CONSTRUCTION_FAILURE)
        typed_limits = {
            CompositionUnderfillReason.PROFILE_INCOMPLETE,
            CompositionUnderfillReason.EVIDENCE_LIMITED,
            CompositionUnderfillReason.QUALITY_LIMITED,
            CompositionUnderfillReason.JOB_MATCH_LIMITED,
            CompositionUnderfillReason.CANDIDATE_CONSTRUCTION_FAILURE,
            CompositionUnderfillReason.RETRIEVAL_FAILURE,
            CompositionUnderfillReason.VALIDATION_LIMITED,
            CompositionUnderfillReason.SEARCH_BOUNDS_LIMITED,
        }
        if not typed_limits.intersection(reasons):
            reasons.append(
                CompositionUnderfillReason.QUALITY_LIMITED
                if candidate_pool.ranked_bullets
                else CompositionUnderfillReason.EVIDENCE_LIMITED
            )
        return list(dict.fromkeys(reasons))


def _posting_context(posting: JobPosting) -> _PostingContext:
    normalized_title = _normalize(posting.title)
    requirements = extract_posting_requirements(posting)
    authoritative_requirements = [
        item
        for item in requirements.requirements
        if item.authority is not RequirementAuthority.INCIDENTAL
    ]
    segments = [
        (
            item.normalized_text,
            {
                RequirementAuthority.CORE: 1.35,
                RequirementAuthority.IMPORTANT: 1.0,
                RequirementAuthority.BONUS: 0.55,
                RequirementAuthority.INCIDENTAL: 0.0,
            }[item.authority],
        )
        for item in authoritative_requirements
        if _meaningful_tokens(item.normalized_text)
    ]
    authoritative_description = " ".join(item.text for item in authoritative_requirements)
    normalized_description = _normalize(authoritative_description)
    authoritative_text = f"{posting.title}\n{authoritative_description}".strip()
    return _PostingContext(
        normalized_text=f"{normalized_title} {normalized_description}".strip(),
        tokens=frozenset(_meaningful_tokens(f"{normalized_title} {normalized_description}")),
        title_tokens=frozenset(_meaningful_tokens(normalized_title)),
        weighted_segments=tuple(segments),
        features=extract_reviewed_text_features(authoritative_text),
        requirements=requirements,
    )


def _education_satisfies_requirement(profile: MasterProfile, requirement_text: str) -> bool:
    """Match explicit degree requirements only against reviewed education."""

    requirement = _normalize(requirement_text)
    if not re.search(r"\b(degree|bachelor|bachelors|master|masters|bsc|msc)\b", requirement):
        return False
    asks_for_engineering = bool(re.search(r"\bengineering\b", requirement))
    asks_for_bachelor = bool(re.search(r"\b(bachelor|bachelors|bsc)\b", requirement))
    asks_for_master = bool(re.search(r"\b(master|masters|msc)\b", requirement))
    for education in profile.education:
        reviewed = _normalize(
            " ".join(
                value
                for value in (
                    education.program,
                    education.minor_or_specialization or "",
                )
                if value
            )
        )
        if asks_for_engineering and "engineering" not in reviewed:
            continue
        if asks_for_bachelor and not re.search(r"\b(bachelor|bachelors|bsc|beng)\b", reviewed):
            continue
        if asks_for_master and not re.search(r"\b(master|masters|msc|meng)\b", reviewed):
            continue
        return True
    return False


def _display_categories_from_declared_skills(
    profile: MasterProfile,
    context: _PostingContext,
    *,
    confirmed_evidence_text: str,
    relevant_evidence_text: str,
) -> list[TechnicalSkillCategory]:
    """Build non-persistent semantic rows from flat reviewed skills.

    A shared typed posting requirement is the primary compatibility signal.  It
    permits non-contiguous source values to form one row while retaining every
    original source index.  Source proximity is only used for the safe fallback
    where the posting cannot establish a stronger relationship.
    """

    ranked: list[
        tuple[
            float,
            int,
            ReviewedTechnicalSkill,
            EvidenceRelationship,
            EvidenceRelationshipAssessment,
        ]
    ] = []
    seen: set[str] = set()
    empty_entry_features = extract_reviewed_text_features("")
    for source_index, raw_value in enumerate(profile.declared_skills):
        value = raw_value.strip()
        normalized = _normalize(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        features = extract_reviewed_text_features(value)
        assessment = assess_evidence_relationship(
            bullet_text=value,
            bullet_features=features,
            entry_features=empty_entry_features,
            structured_values=[value],
            requirements=context.requirements,
            reviewed_skill=True,
        )
        supported = _contains_phrase(confirmed_evidence_text, normalized)
        supported_by_relevant_evidence = _contains_phrase(
            relevant_evidence_text,
            normalized,
        )
        relationship_base = {
            EvidenceRelationship.DIRECT: 80.0,
            EvidenceRelationship.ADJACENT: 52.0,
            EvidenceRelationship.COMPLEMENTARY: 28.0,
            EvidenceRelationship.INCIDENTAL: 0.0,
            EvidenceRelationship.REJECTED: 0.0,
        }[assessment.relationship]
        score = (
            relationship_base
            + min(30.0, assessment.contextual_relevance)
            + (12.0 if supported else -4.0)
            + (6.0 if supported_by_relevant_evidence else 0.0)
        )
        ranked.append(
            (
                score,
                source_index,
                ReviewedTechnicalSkill(
                    id=f"declared-skill:{source_index}",
                    value=value,
                    source_reference=f"profile.declared_skills[{source_index}]",
                ),
                assessment.relationship,
                assessment,
            )
        )
    direct_or_adjacent_indexes = {
        record[1]
        for record in ranked
        if record[3]
        in {
            EvidenceRelationship.DIRECT,
            EvidenceRelationship.ADJACENT,
        }
    }
    ranked = [
        record
        for record in ranked
        if (
            record[3]
            in {
                EvidenceRelationship.DIRECT,
                EvidenceRelationship.ADJACENT,
                EvidenceRelationship.COMPLEMENTARY,
            }
            or _contains_phrase(confirmed_evidence_text, _normalize(record[2].value))
            or _contains_phrase(relevant_evidence_text, _normalize(record[2].value))
            or (
                any(0 < record[1] - anchor <= 7 for anchor in direct_or_adjacent_indexes)
                and extract_reviewed_text_features(record[2].value).technical_specificity >= 0.08
            )
        )
    ]
    ranked.sort(
        key=lambda item: (
            _relationship_order(item[3]),
            -item[0],
            item[1],
            item[2].value.casefold(),
        )
    )
    selected = ranked[:24]
    selected_direct_indexes = {
        record[1]
        for record in selected
        if record[3] in {EvidenceRelationship.DIRECT, EvidenceRelationship.ADJACENT}
    }
    # Preserve nearby reviewed companions of authoritative requirements even
    # when broad evidence-supported inventory would otherwise consume the
    # bounded candidate slice first.
    for record in ranked[24:]:
        if len(selected) >= 32:
            break
        if any(abs(record[1] - index) <= 2 for index in selected_direct_indexes):
            selected.append(record)
    if not selected:
        return []
    requirement_by_id = {item.id: item for item in context.requirements.requirements}
    groups_by_requirement: dict[
        str,
        list[
            tuple[
                float,
                int,
                ReviewedTechnicalSkill,
                EvidenceRelationship,
                EvidenceRelationshipAssessment,
            ]
        ],
    ] = {}
    fallback: list[
        tuple[
            float,
            int,
            ReviewedTechnicalSkill,
            EvidenceRelationship,
            EvidenceRelationshipAssessment,
        ]
    ] = []
    for record in selected:
        assessment = record[4]
        requirement_ids = (
            *assessment.direct_requirement_ids,
            *assessment.adjacent_requirement_ids,
            *assessment.complementary_requirement_ids,
        )
        eligible_ids = [item for item in requirement_ids if item in requirement_by_id]
        if not eligible_ids:
            fallback.append(record)
            continue
        preferred_requirement_id = min(
            eligible_ids,
            key=lambda item: (
                -requirement_by_id[item].importance,
                _relationship_order(record[3]),
                item,
            ),
        )
        groups_by_requirement.setdefault(preferred_requirement_id, []).append(record)

    grouped: list[
        tuple[
            str | None,
            list[
                tuple[
                    float,
                    int,
                    ReviewedTechnicalSkill,
                    EvidenceRelationship,
                    EvidenceRelationshipAssessment,
                ]
            ],
        ]
    ] = [(requirement_id, records) for requirement_id, records in groups_by_requirement.items()]
    fallback.sort(key=lambda item: item[1])
    for record in fallback:
        compatible_group = min(
            (
                records
                for _requirement_id, records in grouped
                if any(abs(record[1] - member[1]) <= 2 for member in records)
                and (
                    _requirement_id is not None
                    or (
                        record[3] is records[-1][3]
                        and _flat_skill_capability_compatible(
                            profile,
                            record[2].value,
                            [member[2].value for member in records],
                        )
                    )
                )
            ),
            key=lambda records: min(abs(record[1] - member[1]) for member in records),
            default=None,
        )
        if compatible_group is None or len(compatible_group) >= 8:
            grouped.append((None, [record]))
        else:
            compatible_group.append(record)

    rows: list[TechnicalSkillCategory] = []
    for row_index, (requirement_id, records) in enumerate(grouped):
        records.sort(key=lambda item: (-item[0], item[1], item[2].value.casefold()))
        skills = [record[2] for record in records]
        source_indexes = [record[1] for record in records]
        requirement = requirement_by_id.get(requirement_id or "")
        label = _display_group_label(
            requirement.text if requirement is not None else "",
            [skill.value for skill in skills],
            profile,
        )
        rows.append(
            TechnicalSkillCategory(
                id=f"display-skill-row:{row_index + 1}",
                category=label,
                values=[skill.value for skill in skills],
                skills=skills,
                source_reference=(
                    "display_regrouping:"
                    + ",".join(
                        f"profile.declared_skills[{source_index}]"
                        for source_index in source_indexes
                    )
                ),
            )
        )
    return rows


def _flat_skill_capability_compatible(
    profile: MasterProfile,
    value: str,
    group_values: list[str],
) -> bool:
    """Require reviewed evidence context before joining fallback flat-skill rows."""

    def capability_labels(skill_value: str) -> set[str]:
        normalized_value = _normalize(skill_value)
        return {
            _normalize(capability)
            for evidence in profile.evidence
            if _contains_phrase(
                _normalize(" ".join([evidence.source_text, *evidence.technologies])),
                normalized_value,
            )
            for capability in evidence.capabilities
        }

    candidate_labels = capability_labels(value)
    return bool(candidate_labels) and any(
        candidate_labels & capability_labels(group_value) for group_value in group_values
    )


_DISPLAY_LABEL_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "bonus",
        "build",
        "core",
        "develop",
        "experience",
        "for",
        "in",
        "or",
        "preferred",
        "qualification",
        "qualifications",
        "related",
        "required",
        "similar",
        "skills",
        "strong",
        "the",
        "timers",
        "use",
        "using",
        "validate",
        "with",
    }
)


def _display_group_label(
    requirement_text: str,
    values: list[str],
    profile: MasterProfile,
) -> str:
    """Derive a concise display label from reviewed requirements, never new skills."""

    requirement_tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", _normalize(requirement_text))
        if token not in _DISPLAY_LABEL_STOPWORDS and len(token) > 2
    ]
    remaining = _normalize(requirement_text)
    for value in values:
        normalized_value = _normalize(value)
        if normalized_value:
            remaining = re.sub(rf"(?<!\\w){re.escape(normalized_value)}(?!\\w)", " ", remaining)
    # Standalone technical identifiers in a requirement are evidence terms, not
    # useful category names when they are not themselves displayed in the row.
    for identifier in re.findall(r"\b[A-Z][A-Z0-9+/#.-]{1,}\b", requirement_text):
        remaining = re.sub(
            rf"(?<!\\w){re.escape(_normalize(identifier))}(?!\\w)",
            " ",
            remaining,
        )
    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", remaining)
        if token not in _DISPLAY_LABEL_STOPWORDS and len(token) > 2
    ]
    if tokens:
        if tokens == ["peripherals"] and any(
            "interfac" in _normalize(skill) for skill in profile.declared_skills
        ):
            return "Interfaces & Peripherals"
        return _professional_display_case(" ".join(tokens[-3:]), requirement_text)
    if requirement_tokens:
        concept = requirement_tokens[-1]
        singular = concept[:-1] if len(concept) > 4 and concept.endswith("s") else concept
        return _professional_display_case(f"{singular} development", requirement_text)
    capability_label = _display_capability_label(profile, values)
    if capability_label:
        return capability_label
    if len(values) == 1:
        return values[0]
    return " / ".join(values[:2])


def _display_capability_label(profile: MasterProfile, values: list[str]) -> str | None:
    """Use reviewed evidence capabilities as a display-only fallback label."""

    normalized_values = [_normalize(value) for value in values]
    capability_counts: Counter[str] = Counter()
    for evidence in profile.evidence:
        evidence_text = _normalize(
            " ".join([evidence.source_text, *evidence.technologies, *evidence.capabilities])
        )
        if not any(_contains_phrase(evidence_text, value) for value in normalized_values):
            continue
        capability_counts.update(
            _normalize(capability) for capability in evidence.capabilities if capability.strip()
        )
    ranked_labels = capability_counts.most_common(2)
    labels = [label for label, _count in ranked_labels]
    if not labels:
        return None
    if len(values) <= 2 or (len(ranked_labels) == 2 and ranked_labels[0][1] > ranked_labels[1][1]):
        labels = labels[:1]
    return " & ".join(_professional_display_case(label, label) for label in labels)


def _professional_display_case(value: str, source: str) -> str:
    """Title case ordinary words while retaining identifier capitalization from source."""

    source_identifiers = {
        _normalize(identifier): identifier
        for identifier in re.findall(r"\b[A-Z][A-Z0-9+/#.-]{1,}\b", source)
    }
    return " ".join(source_identifiers.get(token, token.title()) for token in value.split())


def _evidence_score(
    evidence: EvidenceItem,
    entry: ResumeItem,
    context: _PostingContext,
    latest_year: int,
    line_fit: BulletLineFitDiagnostic,
    *,
    candidate_text: str | None = None,
    structured_values_override: list[str] | None = None,
) -> tuple[
    float,
    float,
    float,
    list[str],
    list[str],
    list[str],
    list[str],
    bool,
    bool,
    str,
    EvidenceRelationship,
    list[str],
    list[str],
    list[str],
    list[str],
    list[ShortTokenContribution],
]:
    rendered_text = candidate_text or evidence.source_text
    structured_values = (
        structured_values_override
        if structured_values_override is not None
        else [*evidence.technologies, *evidence.capabilities, *evidence.outcomes]
    )
    source_parts = [
        rendered_text,
        *structured_values,
    ]
    bullet_features = extract_reviewed_text_features(" ".join(source_parts))
    entry_features = extract_reviewed_text_features(
        " ".join(
            [
                entry.title,
                entry.subtitle or "",
                entry.technology_label or "",
                entry.description or "",
                *entry.technologies,
                *entry.capabilities,
            ]
        )
    )
    combined_features = extract_reviewed_text_features(f"{' '.join(source_parts)} {entry.title}")
    bullet_match = match_reviewed_features(bullet_features, context.features)
    entry_match = match_reviewed_features(entry_features, context.features)
    assessment = assess_evidence_relationship(
        bullet_text=rendered_text,
        bullet_features=bullet_features,
        entry_features=entry_features,
        structured_values=structured_values,
        requirements=context.requirements,
    )
    role_context_match = match_reviewed_features(
        bullet_features,
        extract_reviewed_text_features(context.requirements.role_context),
    )
    title_context_relevance = role_context_match.relevance_score
    title_context_match = bool(role_context_match.meaningful_overlap) and (
        assessment.relationship is EvidenceRelationship.REJECTED
    ) and bool(
        bullet_features.responsibility_signals or bullet_features.outcome_signals
    )
    effective_relationship = assessment.relationship
    if effective_relationship is EvidenceRelationship.REJECTED and title_context_match:
        effective_relationship = EvidenceRelationship.DIRECT
    effective_contextual_relevance = assessment.contextual_relevance + (
        min(35.0, title_context_relevance) if title_context_match else 0.0
    )
    admitted = assessment.relationship in {
        EvidenceRelationship.DIRECT,
        EvidenceRelationship.ADJACENT,
        EvidenceRelationship.COMPLEMENTARY,
    } or title_context_match
    meaningful_overlap = _maximal_phrases(
        [*assessment.meaningful_overlap, *role_context_match.meaningful_overlap]
    )
    relationship_bonus = {
        EvidenceRelationship.DIRECT: 24.0,
        EvidenceRelationship.ADJACENT: 16.0,
        EvidenceRelationship.COMPLEMENTARY: 4.0,
        EvidenceRelationship.INCIDENTAL: -6.0,
        EvidenceRelationship.REJECTED: -20.0,
    }[effective_relationship]
    evidence_strength = (
        8.0
        + (bullet_features.technical_specificity * 20.0)
        + min(10.0, len(bullet_features.responsibility_signals) * 2.5)
        + min(10.0, len(bullet_features.outcome_signals) * 3.0)
        + min(8.0, len(evidence.outcomes) * 3.0)
        + min(
            8.0,
            (len(bullet_features.outcome_signals) + len(evidence.outcomes)) * 4.0,
        )
    )
    entry_context_score = (
        min(4.0, entry_match.relevance_score * 0.12)
        if effective_relationship is not EvidenceRelationship.REJECTED
        else 0.0
    )
    awkward_penalty = 5.0 if line_fit.awkward_wrap_risk else 0.0
    three_line_penalty = max(0, line_fit.expected_line_count - 2) * 20.0
    vertical_cost_penalty = line_fit.total_vertical_line_cost * 1.2
    score = round(
        min(70.0, effective_contextual_relevance)
        + relationship_bonus
        + entry_context_score
        + (min(24.0, title_context_relevance) if title_context_match else 0.0)
        + evidence_strength
        + _recency_score(entry, latest_year)
        - awkward_penalty
        - three_line_penalty
        - vertical_cost_penalty,
        2,
    )
    requirement_by_id = {item.id: item for item in context.requirements.requirements}
    matched_requirement_ids = [
        *assessment.direct_requirement_ids,
        *assessment.adjacent_requirement_ids,
        *assessment.complementary_requirement_ids,
    ]
    coverage = [
        (f"requirement:{requirement_id}", requirement_by_id[requirement_id].text)
        for requirement_id in matched_requirement_ids
        if requirement_id in requirement_by_id
        and requirement_by_id[requirement_id].source_context != "title"
    ]
    deduplicated = _deduplicated_coverage(coverage)
    if not deduplicated and title_context_match:
        # Preserve entry-local role context as an admission signal without
        # treating the title itself as covered qualification evidence.
        deduplicated = [
            (f"context:role-title:{evidence.id}", "Role-context technical evidence")
        ]
    if not deduplicated and effective_relationship is EvidenceRelationship.ADJACENT:
        # Partial support for a compound posting requirement is useful
        # transferable context, but must not masquerade as complete
        # requirement coverage (for example firmware alone for firmware+GUI).
        context_digest = sha256(
            "|".join(assessment.meaningful_overlap).encode()
        ).hexdigest()[:10]
        deduplicated = [
            (
                f"context:{context_digest}",
                "Transferable technical context: "
                + ", ".join(assessment.meaningful_overlap[:3]),
            )
        ]
    admission_reason = (
        "Admitted through specific reviewed-text overlap with posting requirements; "
        "the matched requirement is complementary or bonus context."
        if (
            assessment.relationship is EvidenceRelationship.COMPLEMENTARY
            and assessment.meaningful_overlap
        )
        else assessment.reason
    )
    return (
        score,
        min(70.0, effective_contextual_relevance) + entry_context_score,
        evidence_strength,
        [key for key, _ in deduplicated],
        [label for _, label in deduplicated],
        _maximal_phrases(list(combined_features.specific_phrases))[:24],
        meaningful_overlap,
        bullet_match.generic_only,
        admitted,
        admission_reason,
        effective_relationship,
        list(assessment.direct_requirement_ids),
        list(assessment.adjacent_requirement_ids),
        list(assessment.complementary_requirement_ids),
        list(assessment.incidental_requirement_ids),
        list(assessment.short_token_contributions),
    )


def _recency_score(entry: ResumeItem, latest_year: int) -> float:
    if not latest_year:
        return 0.0
    value = entry.end_date or entry.start_date or ""
    if value.casefold() in {"present", "current", "ongoing"}:
        return 4.0
    years = _years(value)
    if not years:
        return 0.0
    difference = max(0, latest_year - max(years))
    return max(0.0, 4.0 - difference)


def _duration_score(entry: ResumeItem, latest_year: int) -> float:
    start_years = _years(entry.start_date)
    end_years = _years(entry.end_date)
    if not start_years:
        return 0.0
    end_value = (entry.end_date or "").casefold()
    end_year = (
        latest_year
        if end_value in {"present", "current", "ongoing"}
        else max(end_years)
        if end_years
        else max(start_years)
    )
    duration_years = max(0, end_year - min(start_years))
    return min(2.0, duration_years * 0.5)


def _reviewed_seniority_score(title: str) -> float:
    tokens = set(re.findall(r"[a-z]+", title.casefold()))
    if tokens & {"principal", "staff"}:
        return 2.0
    if tokens & {"lead", "manager", "senior"}:
        return 1.25
    return 0.0


def _years(value: str | None) -> list[int]:
    return [int(match) for match in _YEAR_PATTERN.findall(value or "")]


def _normalize(value: str) -> str:
    return normalize_reviewed_text(value)


def _primary_structured_matches(
    reviewed_values: list[str],
    context: _PostingContext,
) -> list[str]:
    candidates: set[str] = set()
    for value in reviewed_values:
        candidates.update(
            acronym.casefold() for acronym in re.findall(r"\b[A-Z][A-Z0-9+.-]{1,}\b", value)
        )
    matched: list[str] = []
    for candidate in candidates:
        if not _contains_phrase(context.normalized_text, candidate):
            continue
        title_match = " " not in candidate and _stem_token(candidate) in context.title_tokens
        segment_match = any(
            weight >= 0.75 and _contains_phrase(segment, candidate)
            for segment, weight in context.weighted_segments
        )
        if title_match or segment_match:
            matched.append(candidate)
    return _maximal_phrases(matched)


def _novel_structured_matches(
    structured_matches: list[str],
    lexical_matches: list[str],
) -> list[str]:
    return [
        candidate
        for candidate in structured_matches
        if not any(
            _contains_phrase(match, candidate) or _contains_phrase(candidate, match)
            for match in lexical_matches
        )
    ]


def _meaningful_tokens(value: str) -> set[str]:
    return {_stem_token(token) for token in value.split() if token not in _STOPWORDS}


def _stem_token(token: str) -> str:
    if len(token) > 5 and token.endswith("ing"):
        return token[:-3].rstrip("n")
    if len(token) > 4 and token.endswith("ed"):
        return token[:-2]
    if len(token) > 4 and token.endswith("es"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and token not in {"aws"}:
        return token[:-1]
    return token


def _overlap_ratio(first: set[str] | frozenset[str], second: set[str] | frozenset[str]) -> float:
    if not first or not second:
        return 0.0
    return len(first & second) / max(1, len(first))


def _contains_phrase(text: str, phrase: str) -> bool:
    return bool(phrase) and f" {phrase} " in f" {text} "


def _alias_variants(value: str) -> set[str]:
    return {value}


def _maximal_phrase_matches(variants: set[str], posting_text: str) -> list[str]:
    return _maximal_phrases(
        [variant for variant in variants if _contains_phrase(posting_text, variant)]
    )


def _maximal_phrases(phrases: list[str]) -> list[str]:
    ordered = sorted(set(filter(None, phrases)), key=lambda item: (-len(item.split()), item))
    selected: list[str] = []
    for phrase in ordered:
        if any(_contains_phrase(other, phrase) for other in selected):
            continue
        selected.append(phrase)
    return selected


def _deduplicated_coverage(coverage: list[tuple[str, str]]) -> list[tuple[str, str]]:
    output: list[tuple[str, str]] = []
    seen: set[str] = set()
    for key, label in coverage:
        if key in seen:
            continue
        seen.add(key)
        output.append((key, label))
    return output


def _near_duplicate(first: str, second: str) -> float:
    first_tokens = _meaningful_tokens(_normalize(first))
    second_tokens = _meaningful_tokens(_normalize(second))
    if not first_tokens or not second_tokens:
        return 0.0
    return len(first_tokens & second_tokens) / min(len(first_tokens), len(second_tokens))


def _unique_coverage(
    candidate_coverage: set[str],
    selected_coverage: set[str],
) -> set[str]:
    unique: set[str] = set()
    for key in candidate_coverage:
        if key in selected_coverage:
            continue
        if key.startswith("term:"):
            phrase = key.removeprefix("term:")
            if any(
                selected.startswith("term:")
                and _contains_phrase(
                    selected.removeprefix("term:"),
                    phrase,
                )
                for selected in selected_coverage
            ):
                continue
        unique.add(key)
    return unique


def _skill_support_status(candidate: _SkillCandidate) -> str:
    if candidate.supported_skill_ids and candidate.declared_only_skill_ids:
        return "mixed_declared_and_supported"
    if candidate.supported_skill_ids:
        return "declared_and_supported"
    return "declared_only"


def _relationship_order(relationship: EvidenceRelationship) -> int:
    return {
        EvidenceRelationship.DIRECT: 0,
        EvidenceRelationship.ADJACENT: 1,
        EvidenceRelationship.COMPLEMENTARY: 2,
        EvidenceRelationship.INCIDENTAL: 3,
        EvidenceRelationship.REJECTED: 4,
    }[relationship]


def _match_has_primary_posting_context(
    match: FeatureMatch,
    context: _PostingContext,
) -> bool:
    if not match.admitted:
        return False
    matched_phrases = match.meaningful_overlap
    if not matched_phrases:
        return bool(match.responsibility_overlap)
    primary_match = any(
        weight >= 0.75 and any(_contains_phrase(segment, phrase) for phrase in matched_phrases)
        for segment, weight in context.weighted_segments
    )
    return primary_match or not context.weighted_segments


def _profile_appears_incomplete(profile: MasterProfile) -> bool:
    confirmed_entry_ids = {
        evidence.entity_id for evidence in profile.evidence if evidence.confirmed
    }
    entries_without_evidence = any(
        entry.id not in confirmed_entry_ids for entry in [*profile.experiences, *profile.projects]
    )
    incomplete_experience_metadata = any(
        not item.organization or not item.start_date or not item.end_date
        for item in profile.experiences
    )
    return entries_without_evidence or incomplete_experience_metadata


def _available_variants(
    baseline: StructuredResume,
) -> dict[str, list[BulletVariantRecord]]:
    diagnostic = baseline.hybrid_diagnostic
    if diagnostic is None:
        return {}
    eligible = [
        item
        for item in diagnostic.bullet_variants
        if item.validation_status is BulletValidationStatus.VALIDATED
        and item.material_improvement
        and item.source_evidence_ids
    ]
    eligible.sort(
        key=lambda item: (
            item.line_fit.expected_line_count,
            int(item.line_fit.awkward_wrap_risk),
            abs(item.line_fit.expected_final_line_width_ratio - 0.72),
            item.variant_id,
        )
    )
    selected: dict[str, list[BulletVariantRecord]] = {}
    for item in eligible:
        selected.setdefault(item.source_evidence_ids[0], []).append(item)
    return selected


def _rewrite_substance_adjustment(
    evidence_bundle: list[EvidenceItem],
    rewritten_text: str,
    *,
    source_line_fit: BulletLineFitDiagnostic,
    rewrite_line_fit: BulletLineFitDiagnostic,
    material_improvement: bool,
) -> tuple[tuple[str, ...], tuple[str, ...], float]:
    """Score visible technical substance without rewarding provider novelty."""

    source_text = " ".join(item.source_text for item in evidence_bundle)
    normalized_source = _normalize(source_text)
    normalized_rewrite = _normalize(rewritten_text)
    technology_terms = {
        value.strip()
        for item in evidence_bundle
        for value in item.technologies
        if value.strip() and _contains_phrase(normalized_source, _normalize(value))
    }
    engineering_terms = {
        value.strip()
        for item in evidence_bundle
        for value in [*item.capabilities, *item.outcomes]
        if len(_meaningful_tokens(_normalize(value))) >= 2
        and _contains_phrase(normalized_source, _normalize(value))
    }
    source_engineering_phrases = {
        phrase
        for phrase in extract_reviewed_text_features(source_text).specific_phrases
        if len(
            phrase_tokens := re.findall(
                r"[a-z0-9]+(?:-[a-z0-9]+)*",
                phrase.casefold(),
            )
        )
        == 2
        and not set(phrase_tokens) & _STOPWORDS
        and not extract_reviewed_text_features(phrase).responsibility_signals
        and extract_reviewed_text_features(phrase).technical_specificity >= 0.25
    }
    engineering_terms.update(source_engineering_phrases)
    metric_terms = set(
        re.findall(
            r"(?<!\w)[<>~]?\d+(?:\.\d+)?(?:\s?%|[- ]?degree(?:s)?)?",
            source_text,
            re.I,
        )
    )
    supported_terms = sorted(
        technology_terms | engineering_terms | metric_terms,
        key=lambda value: (value.casefold(), value),
    )
    preserved = tuple(
        term
        for term in supported_terms
        if _contains_phrase(normalized_rewrite, _normalize(term))
    )
    removed = tuple(term for term in supported_terms if term not in preserved)
    lost_technologies = sum(term in technology_terms for term in removed)
    lost_metrics = sum(term in metric_terms for term in removed)
    lost_engineering_terms = len(removed) - lost_technologies - lost_metrics
    adjustment = -(
        (lost_technologies * 6.0)
        + (lost_metrics * 8.0)
        + (max(0, lost_engineering_terms) * 2.5)
    )
    if material_improvement and not removed:
        # A validated, substance-preserving rewrite may influence package
        # selection; provider novelty alone never reaches this branch. A
        # concise or requirement-foregrounding rewrite earns the larger
        # package signal; a merely restructured longer sentence does not.
        adjustment += 8.0 if (
            rewrite_line_fit.expected_line_count <= source_line_fit.expected_line_count
            or source_line_fit.awkward_wrap_risk
        ) else 3.0
    if (
        material_improvement
        and rewrite_line_fit.expected_line_count < source_line_fit.expected_line_count
        and (source_line_fit.expected_line_count > 2 or source_line_fit.awkward_wrap_risk)
    ):
        adjustment += 1.5
    if source_line_fit.awkward_wrap_risk and not rewrite_line_fit.awkward_wrap_risk:
        adjustment += 0.75
    return preserved, removed, round(adjustment, 2)


def _source_versus_rewrite_key(
    candidate: _BulletCandidate,
) -> tuple[int, int, float, float, int, int, float, int, str]:
    readability_adjusted_score = (
        candidate.score
        - max(0, candidate.line_fit.expected_line_count - 1) * 3.0
        - int(candidate.line_fit.awkward_wrap_risk) * 2.0
    )
    return (
        int(candidate.admitted),
        int(
            candidate.writing_variant is not None
            and candidate.writing_variant.selection_reason
            == "Explicitly approved by the user for this rebuilt artifact."
        ),
        readability_adjusted_score,
        candidate.score,
        -candidate.line_fit.expected_line_count,
        -int(candidate.line_fit.awkward_wrap_risk),
        -abs(candidate.line_fit.expected_final_line_width_ratio - 0.72),
        int(candidate.writing_variant is None),
        candidate.writing_variant.variant_id
        if candidate.writing_variant is not None
        else candidate.evidence_id,
    )


def _baseline_evidence_ids(baseline: StructuredResume) -> set[str]:
    """Return bounded planner advice without making it an admission authority."""

    return {
        evidence_id
        for section in (
            baseline.experience_bullets,
            baseline.project_bullets,
        )
        for bullets in section.values()
        for bullet in bullets
        for evidence_id in bullet.evidence_ids
    }


__all__ = ["CompositionSearchBounds", "DeterministicResumeComposer"]
