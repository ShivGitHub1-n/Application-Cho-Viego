from __future__ import annotations

from pathlib import Path

from resume_tailor.application.cover_letter import CoverLetterService
from resume_tailor.application.cover_letter_page_fit import CoverLetterPageFitter
from resume_tailor.domain.cover_letter import CoverLetterPageFitStatus
from tests.cover_letter_helpers import ControlledCoverLetterRenderer, cover_letter_case


def _letter():
    profile, posting, plan = cover_letter_case()
    artifact = CoverLetterService(renderer=ControlledCoverLetterRenderer([0.94])).generate_artifact(
        profile, posting, plan
    )
    return artifact.letter


def _with_evidence(letter, evidence_id: str):
    paragraph = letter.paragraphs[1].model_copy(
        update={
            "id": f"extra-{evidence_id}",
            "candidate_evidence_ids": [evidence_id],
            "text": f"Validated technical context from evidence {evidence_id}.",
        }
    )
    return letter.model_copy(
        update={"paragraphs": [*letter.paragraphs[:-1], paragraph, letter.paragraphs[-1]]}
    )


def test_preferred_density_is_selected_before_severe_underfill(tmp_path: Path) -> None:
    baseline = _letter()
    expanded = _with_evidence(baseline, "additional-reviewed-evidence")
    renderer = ControlledCoverLetterRenderer([0.72, 0.90])

    fitted = CoverLetterPageFitter(renderer).fit([baseline, expanded], tmp_path)

    assert fitted.letter is expanded
    assert fitted.diagnostic.status is CoverLetterPageFitStatus.PREFERRED_DENSITY
    assert fitted.diagnostic.preferred_density_reachable
    assert fitted.diagnostic.evidence_added_during_page_fit == ["additional-reviewed-evidence"]
    assert renderer.pagination_attempt_count == 1


def test_materially_underfilled_letter_remains_a_failure(tmp_path: Path) -> None:
    renderer = ControlledCoverLetterRenderer([0.62])

    fitted = CoverLetterPageFitter(renderer).fit([_letter()], tmp_path)

    assert fitted.diagnostic.status is CoverLetterPageFitStatus.SEVERE_UNDERFILL
    assert fitted.diagnostic.underfill_or_overflow == "severe_underfill"
    assert not fitted.diagnostic.preferred_density_reachable
    assert fitted.diagnostic.estimated_remaining_lines > 0


def test_more_grounded_evidence_wins_when_preferred_candidates_are_equivalent(
    tmp_path: Path,
) -> None:
    baseline = _letter()
    richer = _with_evidence(baseline, "strong-company-relevant-evidence")
    renderer = ControlledCoverLetterRenderer([0.93, 0.93])

    fitted = CoverLetterPageFitter(renderer).fit([baseline, richer], tmp_path)

    assert fitted.letter is richer
    assert "strong-company-relevant-evidence" in fitted.diagnostic.candidates[1].evidence_ids


def test_exact_pagination_failure_preserves_unverified_status(tmp_path: Path) -> None:
    renderer = ControlledCoverLetterRenderer([0.94], exact=False)

    fitted = CoverLetterPageFitter(renderer).fit([_letter()], tmp_path)

    assert fitted.diagnostic.status is CoverLetterPageFitStatus.PAGINATION_UNVERIFIED
    assert not fitted.diagnostic.exact_pagination
    assert fitted.diagnostic.manual_word_inspection_required
    assert fitted.diagnostic.pagination_failure == "Word pagination unavailable"


def test_unavailable_pagination_is_not_replaced_by_estimated_underfill(
    tmp_path: Path,
) -> None:
    renderer = ControlledCoverLetterRenderer([0.50], exact=False)

    fitted = CoverLetterPageFitter(renderer).fit([_letter()], tmp_path)

    assert fitted.diagnostic.status is CoverLetterPageFitStatus.PAGINATION_UNVERIFIED
    assert fitted.diagnostic.underfill_or_overflow == "severe_underfill"
    assert fitted.diagnostic.candidates[0].status is CoverLetterPageFitStatus.SEVERE_UNDERFILL
    assert fitted.diagnostic.manual_word_inspection_required


def test_blank_trailing_second_page_is_rejected(tmp_path: Path) -> None:
    renderer = ControlledCoverLetterRenderer(
        [0.94],
        page_counts=[2],
        blank_indices={0},
    )

    fitted = CoverLetterPageFitter(renderer).fit([_letter()], tmp_path)

    assert fitted.diagnostic.status is CoverLetterPageFitStatus.BLANK_TRAILING_PAGE
    assert fitted.diagnostic.blank_trailing_page
    assert fitted.diagnostic.underfill_or_overflow == "blank_trailing_page"


def test_overflow_is_not_reported_as_balanced_one_page(tmp_path: Path) -> None:
    renderer = ControlledCoverLetterRenderer([1.08], page_counts=[2])

    fitted = CoverLetterPageFitter(renderer).fit([_letter()], tmp_path)

    assert fitted.diagnostic.status is CoverLetterPageFitStatus.OVERFLOW
    assert fitted.diagnostic.underfill_or_overflow == "overflow"


def test_page_fit_does_not_change_layout_or_factual_text(tmp_path: Path) -> None:
    baseline = _letter()
    richer = _with_evidence(baseline, "reviewed-thread")
    original_layout = richer.layout_profile.model_dump()
    original_text = [paragraph.text for paragraph in richer.paragraphs]

    fitted = CoverLetterPageFitter(ControlledCoverLetterRenderer([0.70, 0.94])).fit(
        [baseline, richer], tmp_path
    )

    assert fitted.letter.layout_profile.model_dump() == original_layout
    assert [paragraph.text for paragraph in fitted.letter.paragraphs] == original_text
    assert fitted.letter.layout_profile.body_size_pt == 11
    assert fitted.letter.layout_profile.top_margin_inches == 1
    assert fitted.letter.layout_profile.paragraph_spacing_pt == 8


def test_page_fit_preserves_strongest_company_connection(tmp_path: Path) -> None:
    baseline = _letter()
    company_ids = {
        item for paragraph in baseline.paragraphs for item in paragraph.company_research_ids
    }

    fitted = CoverLetterPageFitter(ControlledCoverLetterRenderer([0.94])).fit([baseline], tmp_path)

    selected_ids = {
        item for paragraph in fitted.letter.paragraphs for item in paragraph.company_research_ids
    }
    assert selected_ids == company_ids


def test_page_fit_has_no_provider_or_research_dependency(tmp_path: Path) -> None:
    renderer = ControlledCoverLetterRenderer([0.94])
    fitter = CoverLetterPageFitter(renderer)

    fitter.fit([_letter()], tmp_path)

    assert not hasattr(fitter, "language_model")
    assert not hasattr(fitter, "company_research")
    assert renderer.pagination_attempt_count == 1
