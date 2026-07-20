from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import cast

from resume_tailor.application.generation_diagnostics import GenerationTelemetry
from resume_tailor.application.resume_features import (
    FeatureMatch,
    ReviewedTextFeatures,
    TemplateV1BulletLineEstimator,
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
from resume_tailor.domain.resume_composition import (
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
    PageFillIterationDiagnostic,
    PageFitEvaluation,
    PageVerificationStatus,
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


@dataclass(frozen=True)
class CompositionSearchBounds:
    beam_width: int = 6
    maximum_estimated_page_evaluations: int = 128
    maximum_exact_finalist_evaluations: int = 12
    maximum_expansion_operations: int = 1_600
    maximum_ranked_bullets: int = 48
    maximum_expansions_per_state: int = 4
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
    provenance: tuple[str, ...]
    entry_order: int
    evidence_order: int
    writing_variant: BulletVariantRecord | None = None


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
    original_order: int


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
    ranking_bound_excluded_bullets: list[_BulletCandidate]


class DeterministicResumeComposer:
    """Compose reviewed profile atoms through bounded Template V1 page-fit search."""

    _minimum_bullet_score = 12.0
    _minimum_skill_score = 12.0
    _minimum_marginal_score = 7.0
    _near_duplicate_threshold = 0.72
    _maximum_skills_per_display_row = 5

    def __init__(
        self,
        page_fit_evaluator: ResumePageFitEvaluator,
        *,
        bounds: CompositionSearchBounds | None = None,
        line_estimator: TemplateV1BulletLineEstimator | None = None,
        telemetry: GenerationTelemetry | None = None,
    ) -> None:
        self._page_fit_evaluator = page_fit_evaluator
        self._bounds = bounds or CompositionSearchBounds()
        self._line_estimator = line_estimator or TemplateV1BulletLineEstimator()
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
            candidate_pool = self._candidate_pool(
                profile,
                context,
                _available_variants(baseline),
                _baseline_evidence_ids(baseline),
            )
            bullets = candidate_pool.ranked_bullets
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
        evaluated_candidate_sources: set[str] = set()
        verification_failure: str | None = None
        estimated_evaluations = 0
        exact_evaluations = 0
        expansion_operations = 0
        best_estimated_utilization = 0.0
        best_exact_utilization: float | None = None
        completion_reserve = min(
            48,
            max(24, self._bounds.maximum_estimated_page_evaluations // 3),
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
                    bullet_by_id,
                    skill_by_id,
                ),
                coverage_count=len(coverage),
                three_line_bullet_count=sum(
                    bullet_by_id[evidence_id].line_fit.three_line_risk
                    for evidence_id in state.bullet_ids
                ),
            )

        seed_states: list[tuple[_State, str]] = []
        if bullets:
            for bullet in bullets[: self._bounds.beam_width]:
                supported_skills = [
                    candidate.category_id
                    for candidate in skills
                    if any(
                        _contains_phrase(_normalize(bullet.text), _normalize(skill.value))
                        for skill in candidate.category.skills
                    )
                ]
                credible_skill_ids = [
                    item.category_id
                    for item in skills
                    if item.category_id in supported_skills or item.supported_skill_ids
                ][: min(3, constraints.max_skill_lines)]
                seed_skill_counts = list(dict.fromkeys([len(credible_skill_ids), 0]))
                for skill_count in seed_skill_counts:
                    skill_ids = frozenset(credible_skill_ids[:skill_count])
                    state = _State(frozenset({bullet.evidence_id}), skill_ids)
                    if self._within_planning_bounds(
                        state,
                        profile,
                        bullet_by_id,
                        constraints,
                    ):
                        seed_states.append((state, bullet.evidence_id))
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
                if self._in_preferred_density_band(item.evaluation.utilization_ratio)
            ]
            if len(target_states) >= self._bounds.target_finalist_count:
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
                options = options[:remaining_operation_budget]
                termination_reason = CompositionTerminationReason.EXPANSION_OPERATION_LIMIT
            expansion_operations += len(options)
            if len(options) > self._bounds.maximum_expansions_per_state:
                bound_excluded_sources.update(
                    item.source_id for item in options[self._bounds.maximum_expansions_per_state :]
                )
                options = options[: self._bounds.maximum_expansions_per_state]
            next_states: list[_EvaluatedState] = []
            for option_index, expansion in enumerate(options):
                if estimated_evaluations >= exploration_evaluation_limit:
                    bound_excluded_sources.update(item.source_id for item in options[option_index:])
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
        completion_current = max(
            all_fitting,
            key=lambda item: (
                len(item.state.bullet_ids),
                item.quality,
                item.coverage_count,
                item.evaluation.utilization_ratio,
                item.state.key,
            ),
        )
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
                if self._in_preferred_density_band(item.evaluation.utilization_ratio)
            ]
            if preferred_states:
                completion_current = self._best_states(
                    preferred_states,
                    limit=len(preferred_states),
                )[0]
                break
            completion_options: list[_Expansion] = []
            completion_sources = [
                completion_current,
                *sorted(
                    all_fitting,
                    key=lambda item: (
                        -len(item.state.bullet_ids),
                        -item.quality,
                        -item.coverage_count,
                        -item.evaluation.utilization_ratio,
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
        if self._in_preferred_density_band(completion_current.evaluation.utilization_ratio):
            termination_reason = CompositionTerminationReason.TARGET_FINALISTS_FOUND
        elif estimated_evaluations >= self._bounds.maximum_estimated_page_evaluations:
            termination_reason = CompositionTerminationReason.ESTIMATED_EVALUATION_LIMIT

        ordered_fitting = self._best_states(all_fitting, limit=len(all_fitting))
        target_finalists = [
            item
            for item in ordered_fitting
            if self._in_preferred_density_band(item.evaluation.utilization_ratio)
        ]
        underfilled_finalists = [item for item in ordered_fitting if item not in target_finalists]
        preferred_target_count = min(
            len(target_finalists),
            max(1, self._bounds.maximum_exact_finalist_evaluations // 4),
        )
        finalists = target_finalists[:preferred_target_count]
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
        final_admissible_sources = {
            expansion.source_id
            for expansion in self._expansions(
                final.state,
                profile,
                bullets,
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
            skills,
            iterations,
            overflow_sources,
            redundancy_by_source,
            verification_failure,
            termination_reason=termination_reason,
            bound_excluded_sources=final_bound_excluded_sources,
            best_estimated_utilization=best_estimated_utilization,
            best_exact_utilization=best_exact_utilization,
            estimated_evaluations=estimated_evaluations,
            exact_evaluations=exact_evaluations,
            expansion_operations=expansion_operations,
            constraints=constraints,
            additional_evidence_unavailable=additional_evidence_unavailable,
            outcome=outcome,
            reason=reason,
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
        variants: dict[str, BulletVariantRecord] | None = None,
        advisory_evidence_ids: set[str] | None = None,
    ) -> _CandidatePool:
        candidates = self._all_bullet_candidates(
            profile,
            context,
            variants or {},
            advisory_evidence_ids or set(),
        )
        relevant = [
            candidate
            for candidate in candidates
            if candidate.admitted
            if candidate.score >= self._minimum_bullet_score and candidate.coverage_keys
        ]
        relevance_excluded = [candidate for candidate in candidates if candidate not in relevant]
        return _CandidatePool(
            ranked_bullets=relevant[: self._bounds.maximum_ranked_bullets],
            relevance_excluded_bullets=relevance_excluded,
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
        variants: dict[str, BulletVariantRecord] | None = None,
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
        candidates: list[_BulletCandidate] = []
        resolved_variants = variants or {}
        resolved_advisory_ids = advisory_evidence_ids or set()
        consumed_secondary_evidence_ids = {
            evidence_id
            for variant in resolved_variants.values()
            for evidence_id in variant.source_evidence_ids[1:]
        }
        for evidence_order, evidence in enumerate(profile.evidence):
            if evidence.id in consumed_secondary_evidence_ids:
                continue
            entry = entry_by_id.get(evidence.entity_id)
            if not evidence.confirmed or entry is None:
                continue
            writing_variant = resolved_variants.get(evidence.id)
            candidate_text = (
                writing_variant.rewritten_text
                if writing_variant is not None
                else evidence.source_text
            )
            line_fit = (
                writing_variant.line_fit
                if writing_variant is not None
                else self._line_estimator.estimate(candidate_text)
            )
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
            ) = _evidence_score(
                evidence,
                entry,
                context,
                latest_year,
                line_fit,
            )
            if evidence.id in resolved_advisory_ids:
                score = round(score + 6.0, 2)
            candidates.append(
                _BulletCandidate(
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
                    provenance=(
                        f"profile.evidence[{evidence.id}]",
                        f"profile.{entry.kind.value}s[{entry.id}]",
                        *(
                            (f"validated_writer_variant[{writing_variant.variant_id}]",)
                            if writing_variant is not None
                            else ()
                        ),
                    ),
                    entry_order=entry_order[entry.id],
                    evidence_order=evidence_order,
                    writing_variant=writing_variant,
                )
            )
        candidates.sort(
            key=lambda item: (
                -item.score,
                item.entry_order,
                item.evidence_order,
                item.evidence_id,
            )
        )
        return candidates

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
        source_categories = (
            profile.technical_skills
            or _display_categories_from_declared_skills(
                profile,
                context,
                confirmed_evidence_text=confirmed_evidence_text,
                relevant_evidence_text=relevant_evidence_text,
            )
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
            scored: list[
                tuple[
                    ReviewedTechnicalSkill,
                    float,
                    bool,
                    bool,
                    FeatureMatch,
                    ReviewedTextFeatures,
                ]
            ] = []
            for skill in category.skills:
                normalized = _normalize(skill.value)
                if not normalized or normalized in seen_normalized_skills:
                    continue
                features = extract_reviewed_text_features(skill.value)
                match = match_reviewed_features(features, context.features)
                match_is_primary = _match_has_primary_posting_context(match, context)
                supported = _contains_phrase(confirmed_evidence_text, normalized)
                supported_by_relevant_evidence = _contains_phrase(
                    relevant_evidence_text,
                    normalized,
                )
                score = (
                    (match.relevance_score * 1.5)
                    + (category_match.relevance_score * 0.35)
                    + (12.0 if supported else -4.0)
                )
                anchor = (
                    match_is_primary
                    or (
                        supported_by_relevant_evidence
                        and (
                            features.technical_specificity >= 0.08
                            or is_display_regrouped
                        )
                    )
                    or (
                        category_match_is_primary
                        and features.technical_specificity >= 0.12
                    )
                )
                complementary = (
                    supported
                    or (
                        features.technical_specificity >= 0.08
                        and category_match_is_primary
                    )
                )
                scored.append(
                    (
                        skill,
                        score,
                        anchor and score >= self._minimum_skill_score,
                        complementary,
                        match,
                        features,
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
            selected_records = anchors[: self._maximum_skills_per_display_row]
            if len(selected_records) < 2:
                complements = [
                    item
                    for item in scored
                    if item not in selected_records and item[3]
                ]
                complements.sort(
                    key=lambda item: (
                        -int(_contains_phrase(confirmed_evidence_text, _normalize(item[0].value))),
                        -item[1],
                        category.skills.index(item[0]),
                    )
                )
                selected_records.extend(complements[: 2 - len(selected_records)])
            if len(selected_records) < self._maximum_skills_per_display_row:
                additional_anchors = [
                    item
                    for item in anchors
                    if item not in selected_records
                ]
                selected_records.extend(
                    additional_anchors[
                        : self._maximum_skills_per_display_row - len(selected_records)
                    ]
                )
            selected = [item[0] for item in selected_records]
            skill_scores = [item[1] for item in selected_records]
            one_skill_exception_reason: str | None = None
            if len(selected) == 1:
                strongest_score = skill_scores[0]
                normalized_skill = _normalize(selected[0].value)
                demonstrated_complement = (
                    _contains_phrase(confirmed_evidence_text, normalized_skill)
                    and _contains_phrase(relevant_evidence_text, normalized_skill)
                )
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
            for skill, _score, _anchor, _complementary, match, features in selected_records:
                normalized = _normalize(skill.value)
                seen_normalized_skills.add(normalized)
                normalized_features.extend(features.specific_phrases)
                meaningful_overlap.extend(match.meaningful_overlap)
                supported = _contains_phrase(confirmed_evidence_text, normalized)
                if supported:
                    supported_ids.append(skill.id or normalized)
                else:
                    declared_only_ids.append(skill.id or normalized)
                for label in match.meaningful_overlap:
                    coverage.append((f"term:{label}", label))
                for label in match.responsibility_overlap:
                    coverage.append((f"responsibility:{label}", label.replace("_", " ")))
            score = round(
                max(skill_scores)
                + (sum(skill_scores[1:]) * 0.24)
                + (min(4, len(selected)) * 2.5)
                - (14.0 if len(selected) == 1 else 0.0),
                2,
            )
            category_id = category.id or ""
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
                    provenance=(
                        category.source_reference
                        or f"profile.technical_skills[{category_id}]",
                    ),
                    source_category_ids=(category_id,),
                    one_skill_exception_reason=one_skill_exception_reason,
                    original_order=original_order,
                )
            )
        ranked.sort(key=lambda item: (-item.score, item.original_order, item.category_id))
        return ranked

    def _expansions(
        self,
        state: _State,
        profile: MasterProfile,
        bullets: list[_BulletCandidate],
        skills: list[_SkillCandidate],
        bullet_by_id: dict[str, _BulletCandidate],
        skill_by_id: dict[str, _SkillCandidate],
        constraints: TemplateConstraints,
        redundancy_by_source: dict[str, float],
    ) -> list[_Expansion]:
        selected_entries = {bullet_by_id[item].entry_id for item in state.bullet_ids}
        selected_entry_counts = Counter(
            bullet_by_id[item].entry_id for item in state.bullet_ids
        )
        credible_project_ids = self._credible_project_ids(bullets)
        selected_project_ids = {
            bullet_by_id[item].entry_id
            for item in state.bullet_ids
            if bullet_by_id[item].entry_kind is EntityKind.PROJECT
        }
        options: list[_Expansion] = []
        for candidate in bullets:
            if candidate.evidence_id in state.bullet_ids:
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
            opens_entry = candidate.entry_id not in selected_entries
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
            depth = selected_entry_counts.get(candidate.entry_id, 0)
            coherence_bonus = (
                5.0
                if not opens_entry and depth == 1
                else 2.0
                if not opens_entry and depth == 2
                else 0.0
            )
            project_bonus = (
                9.0
                if (
                    candidate.entry_kind is EntityKind.PROJECT
                    and not opens_entry
                    and depth == 1
                    and candidate.entry_id in credible_project_ids
                )
                else 5.0
                if (
                    candidate.entry_kind is EntityKind.PROJECT
                    and opens_entry
                    and not selected_project_ids
                    and candidate.entry_id in credible_project_ids
                )
                else 0.0
            )
            options.append(
                _Expansion(
                    candidate_id=f"{kind.value}:{candidate.evidence_id}",
                    source_id=candidate.evidence_id,
                    kind=kind,
                    state=proposal,
                    marginal_score=marginal,
                    redundancy_penalty=penalty,
                    preference_bonus=coherence_bonus + project_bonus,
                    line_cost=(
                        candidate.line_fit.total_vertical_line_cost
                        + (2.0 if opens_entry else 0.0)
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
            if len(state.skill_category_ids) >= 3 and not distinct_coverage:
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
        if (
            self._bounds.maximum_bullets_per_entry is not None
            and any(
                count > self._bounds.maximum_bullets_per_entry
                for count in counts.values()
            )
        ):
            return False
        entity_by_id = {item.id: item for item in [*profile.experiences, *profile.projects]}
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
        selected_features = {
            feature for other in selected for feature in other.normalized_features
        }
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
        bullet_by_id: dict[str, _BulletCandidate],
        skill_by_id: dict[str, _SkillCandidate],
    ) -> float:
        bullets = [bullet_by_id[item] for item in state.bullet_ids]
        coverage_counts = Counter(
            coverage for bullet in bullets for coverage in bullet.coverage_keys
        )
        unique_coverage = len(coverage_counts)
        repeated_coverage = sum(max(0, count - 1) for count in coverage_counts.values())
        opened_entries = {bullet.entry_id for bullet in bullets}
        experience_count = len(
            {bullet.entry_id for bullet in bullets if bullet.entry_kind is EntityKind.EXPERIENCE}
        )
        project_count = len(
            {bullet.entry_id for bullet in bullets if bullet.entry_kind is EntityKind.PROJECT}
        )
        project_bullet_counts = Counter(
            bullet.entry_id
            for bullet in bullets
            if bullet.entry_kind is EntityKind.PROJECT
        )
        credible_project_ids = self._credible_project_ids(list(bullet_by_id.values()))
        substantive_project_count = sum(
            count >= 2 for count in project_bullet_counts.values()
        )
        project_representation_adjustment = (
            16.0 + max(0, substantive_project_count - 1) * 4.0
            if substantive_project_count
            else -14.0
            if credible_project_ids and project_count
            else -12.0
            if credible_project_ids
            else 0.0
        )
        portfolio_shape_bonus = (
            (6.0 if 2 <= experience_count <= 3 else 0.0)
            + project_representation_adjustment
        )
        sparse_skill_row_count = sum(
            len(skill_by_id[item].category.skills) == 1
            for item in state.skill_category_ids
        )
        return round(
            sum(bullet.score for bullet in bullets)
            + sum(skill_by_id[item].score * 0.42 for item in state.skill_category_ids)
            + (min(3, len(state.skill_category_ids)) * 10.0)
            + (5.0 if len(state.skill_category_ids) >= 4 else 0.0)
            + portfolio_shape_bonus
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
                0
                if (
                    self._in_preferred_density_band(item.evaluation.utilization_ratio)
                    and item.three_line_bullet_count == 0
                )
                else 1,
                0
                if item.evaluation.utilization_ratio
                <= TEMPLATE_V1_UTILIZATION_TARGET_CEILING
                else 1,
                -item.quality,
                -item.coverage_count,
                item.three_line_bullet_count,
                0 if self._in_target_band(item.evaluation.utilization_ratio) else 1,
                -min(
                    item.evaluation.utilization_ratio,
                    TEMPLATE_V1_IDEAL_DENSITY,
                ),
                abs(min(item.evaluation.utilization_ratio, 1.0) - TEMPLATE_V1_IDEAL_DENSITY),
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
                0
                if (
                    self._in_preferred_density_band(item.evaluation.utilization_ratio)
                    and item.three_line_bullet_count == 0
                )
                else 1,
                0
                if item.evaluation.utilization_ratio
                <= TEMPLATE_V1_UTILIZATION_TARGET_CEILING
                else 1,
                -item.quality,
                -item.coverage_count,
                item.three_line_bullet_count,
                -min(
                    item.evaluation.utilization_ratio,
                    TEMPLATE_V1_PREFERRED_DENSITY_FLOOR,
                ),
                item.state.key,
            ),
        )
        return ordered[: self._bounds.beam_width]

    @staticmethod
    def _in_target_band(utilization_ratio: float) -> bool:
        return (
            TEMPLATE_V1_UTILIZATION_TARGET_FLOOR
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
    def _preferred_density_status(
        utilization_ratio: float,
    ) -> PreferredDensityStatus:
        if utilization_ratio < TEMPLATE_V1_PREFERRED_DENSITY_FLOOR:
            return PreferredDensityStatus.BELOW_PREFERRED
        if utilization_ratio <= TEMPLATE_V1_PREFERRED_DENSITY_CEILING:
            return PreferredDensityStatus.PREFERRED
        if utilization_ratio <= TEMPLATE_V1_UTILIZATION_TARGET_CEILING:
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
        if evaluation.utilization_ratio < TEMPLATE_V1_UTILIZATION_TARGET_FLOOR:
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
                "90%-95% visual range; typed diagnostics identify whether evidence, match, "
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
        skills: list[_SkillCandidate],
        iterations: list[PageFillIterationDiagnostic],
        overflow_sources: dict[str, float],
        redundancy_by_source: dict[str, float],
        verification_failure: str | None,
        *,
        termination_reason: CompositionTerminationReason,
        bound_excluded_sources: set[str],
        best_estimated_utilization: float,
        best_exact_utilization: float | None,
        estimated_evaluations: int,
        exact_evaluations: int,
        expansion_operations: int,
        constraints: TemplateConstraints,
        additional_evidence_unavailable: bool,
        outcome: CompositionOutcome,
        reason: str,
    ) -> ResumeCompositionDiagnostic:
        selected_bullets = {
            item.evidence_id: item for item in bullets if item.evidence_id in final.state.bullet_ids
        }
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
            if candidate.evidence_id in overflow_sources:
                exclusion = "Rendered expansion overflowed one page and was rolled back."
                category = CandidateExclusionCategory.OVERFLOW
            elif candidate.evidence_id in bound_excluded_sources or not proposal_fits_bounds:
                exclusion = (
                    "Relevant reviewed evidence was excluded only by an explicit "
                    "bounded-search or selected-content limit."
                )
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
            )
            excluded.append(diagnostic)
            if category is CandidateExclusionCategory.SEARCH_BOUND:
                excluded_by_bounds.append(diagnostic)
            elif category is CandidateExclusionCategory.REDUNDANCY_THRESHOLD:
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
            for coverage in {
                item.category_id: item for item in skills
            }[category_id].coverage_keys
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
                )
            )
        credible_project_ids = sorted(self._credible_project_ids(all_relevant_bullets))
        selected_project_bullet_counts = Counter(
            candidate.entry_id
            for candidate in selected_bullets.values()
            if candidate.entry_kind is EntityKind.PROJECT
        )
        substantive_project_ids = sorted(
            entry_id
            for entry_id, count in selected_project_bullet_counts.items()
            if count >= 2
        )
        selected_project_ids = [
            item.id for item in profile.projects if item.id in selected_entries
        ]
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
                skill_ids=[
                    skill.id or ""
                    for skill in candidate.category.skills
                    if skill.id
                ],
                skill_values=[skill.value for skill in candidate.category.skills],
                provenance=list(candidate.provenance),
                one_skill_exception_reason=candidate.one_skill_exception_reason,
            )
            for candidate in selected_skill_candidates
        ]
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
            project_representation=project_representation,
            selected_skill_rows=selected_skill_rows,
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
        )

    @staticmethod
    def _distinct_contribution(
        candidate: _BulletCandidate,
        other_selected: list[_BulletCandidate],
    ) -> str:
        other_coverage = {
            coverage for item in other_selected for coverage in item.coverage_keys
        }
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
            feature
            for feature in candidate.normalized_features
            if feature not in other_features
        ][:3]
        contributions: list[str] = []
        if unique_labels:
            contributions.append(
                "distinct requirement coverage: " + ", ".join(unique_labels[:3])
            )
        if unique_features:
            contributions.append(
                "distinct reviewed technical evidence: " + ", ".join(unique_features)
            )
        if (
            candidate.writing_variant is not None
            and candidate.writing_variant.material_improvement
        ):
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
        if exact_finalist_limit_reached or excluded_by_bounds or termination_reason in {
            CompositionTerminationReason.ESTIMATED_EVALUATION_LIMIT,
            CompositionTerminationReason.EXPANSION_OPERATION_LIMIT,
        }:
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
    normalized_description = _normalize(posting.description)
    segments: list[tuple[str, float]] = []
    for raw in re.split(r"[\r\n]+|(?<=[.!?;])\s+", posting.description):
        normalized = _normalize(raw)
        if not _meaningful_tokens(normalized):
            continue
        weight = 1.0
        if re.search(r"\b(required|requirements|must|minimum)\b", normalized):
            weight += 0.35
        if re.search(r"\b(preferred|bonus|nice to have)\b", normalized):
            weight += 0.15
        if re.search(r"\b(responsibilities|what you will do|duties)\b", normalized):
            weight += 0.20
        if re.search(r"\b(incidental(?:ly)?|optional(?:ly)?|helpful)\b", normalized):
            weight *= 0.40
        segments.append((normalized, weight))
    return _PostingContext(
        normalized_text=f"{normalized_title} {normalized_description}".strip(),
        tokens=frozenset(_meaningful_tokens(f"{normalized_title} {normalized_description}")),
        title_tokens=frozenset(_meaningful_tokens(normalized_title)),
        weighted_segments=tuple(segments),
        features=extract_reviewed_text_features(f"{posting.title}\n{posting.description}"),
    )


def _display_categories_from_declared_skills(
    profile: MasterProfile,
    context: _PostingContext,
    *,
    confirmed_evidence_text: str,
    relevant_evidence_text: str,
) -> list[TechnicalSkillCategory]:
    """Build bounded rank-tier display rows from exact reviewed flat skills.

    The fallback creates no new skill values and does not change the canonical
    profile. Generic tier labels avoid a technology dictionary while exact
    source-index provenance keeps every displayed value auditable.
    """

    ranked: list[tuple[float, int, ReviewedTechnicalSkill]] = []
    seen: set[str] = set()
    for source_index, raw_value in enumerate(profile.declared_skills):
        value = raw_value.strip()
        normalized = _normalize(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        features = extract_reviewed_text_features(value)
        match = match_reviewed_features(features, context.features)
        match_is_primary = _match_has_primary_posting_context(match, context)
        supported = _contains_phrase(confirmed_evidence_text, normalized)
        supported_by_relevant_evidence = _contains_phrase(
            relevant_evidence_text,
            normalized,
        )
        eligible = match_is_primary or supported_by_relevant_evidence
        if not eligible:
            continue
        score = (
            (match.relevance_score * 1.5)
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
            )
        )
    ranked.sort(key=lambda item: (-item[0], item[1], item[2].value.casefold()))
    selected = ranked[:20]
    if not selected:
        return []
    row_count = max(1, min(4, len(selected) // 2))
    labels = (
        "Primary Technical Skills",
        "Supporting Technical Skills",
        "Complementary Technical Skills",
        "Additional Reviewed Skills",
    )
    base_size, remainder = divmod(len(selected), row_count)
    rows: list[TechnicalSkillCategory] = []
    offset = 0
    for row_index in range(row_count):
        row_size = base_size + int(row_index < remainder)
        records = selected[offset : offset + row_size]
        offset += row_size
        skills = [record[2] for record in records]
        source_indexes = [record[1] for record in records]
        rows.append(
            TechnicalSkillCategory(
                id=f"display-skill-row:{row_index + 1}",
                category=labels[row_index],
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


def _evidence_score(
    evidence: EvidenceItem,
    entry: ResumeItem,
    context: _PostingContext,
    latest_year: int,
    line_fit: BulletLineFitDiagnostic,
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
]:
    source_parts = [
        evidence.source_text,
        *evidence.technologies,
        *evidence.capabilities,
        *evidence.outcomes,
        *entry.technologies,
        *entry.capabilities,
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
    bullet_match_is_primary = _match_has_primary_posting_context(
        bullet_match,
        context,
    )
    entry_match_is_primary = _match_has_primary_posting_context(
        entry_match,
        context,
    )
    lexical_matches = [
        *bullet_match.meaningful_overlap,
        *entry_match.meaningful_overlap,
    ]
    bullet_structured_matches = _novel_structured_matches(
        _primary_structured_matches(
            [
                *evidence.technologies,
                *evidence.capabilities,
                *entry.technologies,
                *entry.capabilities,
            ],
            context,
        ),
        lexical_matches,
    )
    entry_structured_matches = _novel_structured_matches(
        _primary_structured_matches(
            [
                entry.title,
                entry.subtitle or "",
                entry.technology_label or "",
                *entry.technologies,
                *entry.capabilities,
            ],
            context,
        ),
        [*lexical_matches, *bullet_structured_matches],
    )
    admitted_by_entry_context = (
        entry_match_is_primary
        and bullet_features.technical_specificity >= 0.16
        and not bullet_match.generic_only
    )
    admitted_by_structured_context = bool(bullet_structured_matches) or (
        bool(entry_structured_matches)
        and bullet_features.technical_specificity >= 0.16
    )
    admitted = (
        bullet_match_is_primary
        or admitted_by_entry_context
        or admitted_by_structured_context
    )
    meaningful_overlap = _maximal_phrases(
        [
            *bullet_match.meaningful_overlap,
            *entry_match.meaningful_overlap,
            *bullet_structured_matches,
            *entry_structured_matches,
        ]
    )
    responsibility_overlap = tuple(
        dict.fromkeys(
            [
                *bullet_match.responsibility_overlap,
                *entry_match.responsibility_overlap,
            ]
        )
    )
    evidence_strength = (
        8.0
        + (bullet_features.technical_specificity * 20.0)
        + min(10.0, len(bullet_features.responsibility_signals) * 2.5)
        + min(10.0, len(bullet_features.outcome_signals) * 3.0)
        + min(8.0, len(evidence.outcomes) * 3.0)
    )
    entry_context_score = min(12.0, entry_match.relevance_score * 0.35)
    structured_context_score = min(
        12.0,
        (len(bullet_structured_matches) * 8.0)
        + (len(entry_structured_matches) * 4.0),
    )
    awkward_penalty = 5.0 if line_fit.awkward_wrap_risk else 0.0
    three_line_penalty = max(0, line_fit.expected_line_count - 2) * 20.0
    vertical_cost_penalty = line_fit.total_vertical_line_cost * 1.2
    score = round(
        bullet_match.relevance_score
        + entry_context_score
        + structured_context_score
        + evidence_strength
        + _recency_score(entry, latest_year)
        - awkward_penalty
        - three_line_penalty
        - vertical_cost_penalty,
        2,
    )
    coverage = [(f"term:{match}", match) for match in meaningful_overlap]
    coverage.extend(
        (f"responsibility:{signal}", signal.replace("_", " ")) for signal in responsibility_overlap
    )
    deduplicated = _deduplicated_coverage(coverage)
    if admitted_by_structured_context:
        admission_reason = (
            "Admitted through exact reviewed structured technology, capability, "
            "or entry-title evidence in primary posting context."
        )
    elif bullet_match_is_primary:
        admission_reason = bullet_match.reason
    elif bullet_match.admitted:
        admission_reason = (
            "Rejected because its specific overlap appeared only in an explicitly "
            "incidental or optional posting segment."
        )
    elif admitted_by_entry_context:
        admission_reason = (
            "Admitted as specific reviewed evidence within a directly relevant entry; "
            "generic title overlap alone was not sufficient."
        )
    else:
        admission_reason = bullet_match.reason
    return (
        score,
        bullet_match.relevance_score + entry_context_score + structured_context_score,
        evidence_strength,
        [key for key, _ in deduplicated],
        [label for _, label in deduplicated],
        _maximal_phrases(list(combined_features.specific_phrases))[:24],
        meaningful_overlap,
        bullet_match.generic_only,
        admitted,
        admission_reason,
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
            acronym.casefold()
            for acronym in re.findall(r"\b[A-Z][A-Z0-9+.-]{1,}\b", value)
        )
    matched: list[str] = []
    for candidate in candidates:
        if not _contains_phrase(context.normalized_text, candidate):
            continue
        title_match = (
            " " not in candidate
            and _stem_token(candidate) in context.title_tokens
        )
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
            _contains_phrase(match, candidate)
            or _contains_phrase(candidate, match)
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
) -> dict[str, BulletVariantRecord]:
    diagnostic = baseline.hybrid_diagnostic
    if diagnostic is None:
        return {}
    eligible = [
        item
        for item in diagnostic.bullet_variants
        if item.selected
        and item.validation_status is BulletValidationStatus.VALIDATED
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
    selected: dict[str, BulletVariantRecord] = {}
    for item in eligible:
        selected.setdefault(item.source_evidence_ids[0], item)
    return selected


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
