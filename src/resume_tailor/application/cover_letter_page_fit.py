from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from resume_tailor.domain.cover_letter import (
    CoverLetter,
    CoverLetterLayoutProfile,
    CoverLetterPageFitCandidateDiagnostic,
    CoverLetterPageFitDiagnostic,
    CoverLetterPageFitStatus,
)
from resume_tailor.ports.cover_letter_rendering import (
    CoverLetterBatchRenderer,
    CoverLetterRenderedCandidate,
)


@dataclass(frozen=True)
class FittedCoverLetter:
    letter: CoverLetter
    render: CoverLetterRenderedCandidate
    diagnostic: CoverLetterPageFitDiagnostic
    render_elapsed_seconds: float


class CoverLetterPageFitter:
    """Select among already validated prose variants without creating wording."""

    def __init__(
        self,
        renderer: CoverLetterBatchRenderer,
        *,
        clock: Callable[[], float] = perf_counter,
    ) -> None:
        self._renderer = renderer
        self._clock = clock

    def fit(
        self,
        candidates: list[CoverLetter],
        output_directory: Path,
    ) -> FittedCoverLetter:
        if not candidates:
            raise ValueError("Cover-letter page fitting requires validated candidates")
        render_started = self._clock()
        results = self._renderer.render_candidates(candidates, output_directory)
        render_elapsed_seconds = max(0.0, self._clock() - render_started)
        if len(results) != len(candidates):
            raise ValueError("Cover-letter renderer returned an incomplete candidate batch")
        profile = candidates[0].layout_profile
        diagnostics: list[CoverLetterPageFitCandidateDiagnostic] = []
        for index, (letter, result) in enumerate(zip(candidates, results, strict=True)):
            status = self._status(result, profile)
            diagnostics.append(
                CoverLetterPageFitCandidateDiagnostic(
                    candidate_id=f"cover-fit:{index}",
                    evidence_ids=sorted(
                        {
                            evidence_id
                            for paragraph in letter.paragraphs
                            for evidence_id in paragraph.candidate_evidence_ids
                        }
                    ),
                    company_research_ids=sorted(
                        {
                            research_id
                            for paragraph in letter.paragraphs
                            for research_id in paragraph.company_research_ids
                        }
                    ),
                    estimated_utilization=result.estimated_utilization,
                    estimated_remaining_lines=result.estimated_remaining_lines,
                    page_count=result.page_count,
                    exact_pagination=result.measurement.exact,
                    status=status,
                    rejection_code=self._rejection_code(status, result),
                    rejection_reason=self._rejection_reason(status, result),
                )
            )
        selected_index = self._select_index(diagnostics, profile.target_utilization)
        selected_update: dict[str, object] = {"selected": True}
        if diagnostics[selected_index].status in {
            CoverLetterPageFitStatus.PREFERRED_DENSITY,
            CoverLetterPageFitStatus.ACCEPTABLE_DENSITY,
        } and results[selected_index].measurement.exact:
            selected_update.update({"rejection_code": None, "rejection_reason": None})
        selected = diagnostics[selected_index].model_copy(update=selected_update)
        diagnostics[selected_index] = selected
        baseline_ids = set(diagnostics[0].evidence_ids)
        selected_ids = set(selected.evidence_ids)
        result = results[selected_index]
        preferred_reachable = any(
            item.status is CoverLetterPageFitStatus.PREFERRED_DENSITY for item in diagnostics
        )
        overall_status = selected.status
        if (
            not result.measurement.exact
            and overall_status is not CoverLetterPageFitStatus.BLANK_TRAILING_PAGE
        ):
            overall_status = CoverLetterPageFitStatus.PAGINATION_UNVERIFIED
        diagnostic = CoverLetterPageFitDiagnostic(
            status=overall_status,
            selected_candidate_id=selected.candidate_id,
            page_count=result.page_count,
            exact_pagination=result.measurement.exact,
            pagination_provider=result.measurement.provider,
            pagination_failure=result.pagination_failure,
            estimated_utilization=result.estimated_utilization,
            estimated_remaining_lines=result.estimated_remaining_lines,
            preferred_density_reachable=preferred_reachable,
            underfill_or_overflow=self._classification(selected, profile),
            manual_word_inspection_required=not result.measurement.exact,
            blank_trailing_page=result.blank_trailing_page,
            evidence_added_during_page_fit=sorted(selected_ids - baseline_ids),
            evidence_removed_during_page_fit=sorted(baseline_ids - selected_ids),
            candidates=diagnostics,
        )
        return FittedCoverLetter(
            letter=candidates[selected_index],
            render=result,
            diagnostic=diagnostic,
            render_elapsed_seconds=render_elapsed_seconds,
        )

    @staticmethod
    def _status(
        result: CoverLetterRenderedCandidate,
        profile: CoverLetterLayoutProfile,
    ) -> CoverLetterPageFitStatus:
        floor = float(profile.preferred_utilization_floor)
        ceiling = float(profile.preferred_utilization_ceiling)
        acceptable_floor = float(profile.acceptable_utilization_floor)
        acceptable_ceiling = float(profile.acceptable_utilization_ceiling)
        ratio = result.estimated_utilization
        if result.blank_trailing_page:
            return CoverLetterPageFitStatus.BLANK_TRAILING_PAGE
        if result.page_count > 1 or ratio > acceptable_ceiling:
            return CoverLetterPageFitStatus.OVERFLOW
        if floor <= ratio <= ceiling:
            return CoverLetterPageFitStatus.PREFERRED_DENSITY
        if acceptable_floor <= ratio <= acceptable_ceiling:
            return CoverLetterPageFitStatus.ACCEPTABLE_DENSITY
        return CoverLetterPageFitStatus.SEVERE_UNDERFILL

    @staticmethod
    def _select_index(
        diagnostics: list[CoverLetterPageFitCandidateDiagnostic],
        target: float,
    ) -> int:
        priority = {
            CoverLetterPageFitStatus.PREFERRED_DENSITY: 0,
            CoverLetterPageFitStatus.ACCEPTABLE_DENSITY: 1,
            CoverLetterPageFitStatus.SEVERE_UNDERFILL: 2,
            CoverLetterPageFitStatus.OVERFLOW: 3,
            CoverLetterPageFitStatus.BLANK_TRAILING_PAGE: 4,
            CoverLetterPageFitStatus.PAGINATION_UNVERIFIED: 1,
        }
        return min(
            range(len(diagnostics)),
            key=lambda index: (
                priority[diagnostics[index].status],
                abs(diagnostics[index].estimated_utilization - target),
                -len(diagnostics[index].evidence_ids),
                index,
            ),
        )

    @staticmethod
    def _rejection_reason(
        status: CoverLetterPageFitStatus,
        result: CoverLetterRenderedCandidate,
    ) -> str | None:
        if status is CoverLetterPageFitStatus.BLANK_TRAILING_PAGE:
            return "A blank or structurally suspect trailing second page was detected."
        if status is CoverLetterPageFitStatus.OVERFLOW:
            return "Candidate exceeds the one-page or safe-density boundary."
        if status is CoverLetterPageFitStatus.SEVERE_UNDERFILL:
            return "Candidate leaves a visibly underfilled lower page region."
        if not result.measurement.exact:
            return "Exact pagination is unavailable; manual Word inspection is required."
        return None

    @staticmethod
    def _rejection_code(
        status: CoverLetterPageFitStatus,
        result: CoverLetterRenderedCandidate,
    ) -> str | None:
        if status is CoverLetterPageFitStatus.BLANK_TRAILING_PAGE:
            return "blank_trailing_page"
        if status is CoverLetterPageFitStatus.OVERFLOW:
            return "overflow"
        if status is CoverLetterPageFitStatus.SEVERE_UNDERFILL:
            return "severe_underfill"
        if not result.measurement.exact:
            return "pagination_unverified"
        return None

    @staticmethod
    def _classification(
        diagnostic: CoverLetterPageFitCandidateDiagnostic,
        profile: CoverLetterLayoutProfile,
    ) -> str:
        if diagnostic.status is CoverLetterPageFitStatus.BLANK_TRAILING_PAGE:
            return "blank_trailing_page"
        if diagnostic.status is CoverLetterPageFitStatus.OVERFLOW:
            return "overflow"
        if diagnostic.estimated_utilization < float(profile.acceptable_utilization_floor):
            return "severe_underfill"
        return "balanced_one_page"


__all__ = ["CoverLetterPageFitter", "FittedCoverLetter"]
