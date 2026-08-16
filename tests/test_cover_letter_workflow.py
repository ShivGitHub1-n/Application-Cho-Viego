from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from pytest import MonkeyPatch
from streamlit.testing.v1 import AppTest

import resume_tailor.infrastructure.dependencies as dependencies
from resume_tailor.application.generated_artifact import content_fingerprint
from resume_tailor.application.workflow_state import COVER_LETTER_ARTIFACT_KEY
from resume_tailor.domain.company_research import (
    CompanyFactConfidence,
    CompanyResearchRequest,
    CompanyResearchStatus,
)
from resume_tailor.domain.cover_letter import (
    CoverLetter,
    CoverLetterPageFitStatus,
    CoverLetterQualityGateStatus,
    CoverLetterRecipient,
    CoverLetterReviewState,
    CoverLetterValidationStatus,
)
from resume_tailor.domain.models import MasterProfile
from resume_tailor.infrastructure.config import Settings
from resume_tailor.infrastructure.cover_letter_rendering import (
    CoverLetterRenderer as ProductionCoverLetterRenderer,
)
from resume_tailor.infrastructure.cover_letter_rendering import (
    CoverLetterRenderResult,
)
from resume_tailor.infrastructure.rendering import (
    DocxPageCountProvider,
    PageCountMeasurement,
    PageCountVerificationError,
)
from tests.cover_letter_helpers import rich_cover_letter_case

ROOT = Path(__file__).resolve().parents[1]
PROFILE_FIXTURE = ROOT / "tests" / "fixtures" / "world_star_tech_production_profile.json"
POSTING_FIXTURE = (
    ROOT / "tests" / "fixtures" / "titan_haptics_mechatronics_integration_engineer.txt"
)


def _navigate(app: AppTest, route: str) -> AppTest:
    return app.button(key=f"pw-route-sidebar-{route}").click().run()


class _UnavailablePaginationProvider:
    def __init__(self) -> None:
        self.calls = 0

    def measure(self, _path: Path) -> PageCountMeasurement:
        self.calls += 1
        raise PageCountVerificationError(
            "Microsoft Word pagination unavailable: null System.IntPtr"
        )

    def measure_many(self, _paths: list[Path]) -> list[PageCountMeasurement]:
        self.calls += 1
        raise PageCountVerificationError(
            "Microsoft Word pagination unavailable: null System.IntPtr"
        )


class _ExactResumePaginationProvider:
    def measure(self, _path: Path) -> PageCountMeasurement:
        return PageCountMeasurement(
            page_count=1,
            provider="synthetic exact resume pagination",
            confidence="exact",
            exact=True,
        )

    def measure_many(self, paths: list[Path]) -> list[PageCountMeasurement]:
        return [self.measure(path) for path in paths]


class _CountingResearchFetcher:
    def __init__(self) -> None:
        self.calls = 0

    def fetch(self, *_args: object, **_kwargs: object) -> object:
        self.calls += 1
        raise AssertionError("Blank optional inputs must not make a research request")


class _CountingCoverRenderer:
    def __init__(self, inner: ProductionCoverLetterRenderer) -> None:
        self._inner = inner
        self.render_calls = 0
        self.rendered_candidate_count = 0
        self.composed_paragraph_counts: list[int] = []
        self.rendered_byte_lengths: list[int] = []

    @property
    def pagination_attempt_count(self) -> int:
        return self._inner.pagination_attempt_count

    def render_candidates(
        self,
        letters: list[CoverLetter],
        output_directory: Path,
    ) -> list[CoverLetterRenderResult]:
        self.render_calls += 1
        self.rendered_candidate_count += len(letters)
        self.composed_paragraph_counts.extend(len(letter.paragraphs) for letter in letters)
        rendered = self._inner.render_candidates(letters, output_directory)
        self.rendered_byte_lengths.extend(len(item.docx_bytes) for item in rendered)
        return rendered


def _configure_offline_app(
    monkeypatch: MonkeyPatch,
    data_directory: Path,
) -> tuple[
    _UnavailablePaginationProvider,
    _CountingResearchFetcher,
    list[_CountingCoverRenderer],
    list[str],
]:
    pagination = _UnavailablePaginationProvider()
    research_fetcher = _CountingResearchFetcher()
    cover_renderers: list[_CountingCoverRenderer] = []
    provider_constructions: list[str] = []

    monkeypatch.setenv("APPLICATION_VIEGO_DATA_DIR", str(data_directory))
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GEMINI_MODEL", "")
    for name in (
        "LLM_ENABLE_ROLE_CLASSIFICATION",
        "LLM_ENABLE_OPPORTUNITY_ANALYSIS",
        "LLM_ENABLE_COMPOSITION",
        "LLM_ENABLE_BULLET_REWRITE",
        "LLM_ENABLE_SHORTENING",
        "LLM_ENABLE_COVER_LETTER",
    ):
        monkeypatch.setenv(name, "false")

    monkeypatch.setattr(
        dependencies,
        "ExactDocxPageCountProvider",
        lambda **_kwargs: _ExactResumePaginationProvider(),
    )
    monkeypatch.setattr(
        dependencies,
        "HttpxOfficialCompanySourceFetcher",
        lambda **_kwargs: research_fetcher,
    )

    def cover_renderer_factory(
        *,
        page_count_provider: DocxPageCountProvider | None = None,
    ) -> _CountingCoverRenderer:
        renderer = _CountingCoverRenderer(
            ProductionCoverLetterRenderer(page_count_provider=pagination)
        )
        cover_renderers.append(renderer)
        return renderer

    def forbidden_provider(*_args: object, **_kwargs: object) -> object:
        provider_constructions.append("gemini")
        raise AssertionError("Gemini must not be constructed in the offline workflow")

    monkeypatch.setattr(dependencies, "CoverLetterRenderer", cover_renderer_factory)
    monkeypatch.setattr(dependencies, "GeminiResumeLanguageModel", forbidden_provider)
    return pagination, research_fetcher, cover_renderers, provider_constructions


def test_production_streamlit_accepts_grounded_synthetic_senior_role(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_offline_app(monkeypatch, tmp_path)
    profile, synthetic_posting, _ = rich_cover_letter_case()
    dependencies.create_profile_repository(Settings()).save(profile)

    app = AppTest.from_file(str(ROOT / "src" / "resume_tailor" / "frontend" / "app.py"))
    app.session_state["profile_id"] = profile.id
    app.run()

    _navigate(app, "resume_studio")
    target_title = "Senior Hardware Integration Engineer"
    app.text_input(key="_resume_studio_job_title_widget").input(target_title).run()
    app.text_area(key="_resume_studio_job_description_widget").input(
        f"Company: {synthetic_posting.company_name}\n{synthetic_posting.description}"
    ).run()
    app.button(key="resume-create-strategy").click().run(timeout=30)
    posting_fingerprint = content_fingerprint(app.session_state["posting"])
    assert app.session_state["workflow_posting_fingerprint"] == posting_fingerprint

    app.button(key="resume-to-evidence").click().run()
    app.button(key="resume-build-document").click().run(timeout=60)
    _navigate(app, "cover_letters")
    next(button for button in app.button if button.label == "Generate cover letter").click().run(
        timeout=60
    )

    assert not app.exception
    assert not app.error
    artifact = app.session_state[COVER_LETTER_ARTIFACT_KEY]
    accepted = [
        candidate
        for candidate in artifact.candidate_validations
        if candidate.rendering_attempted
    ]
    letter_text = " ".join(paragraph.text for paragraph in artifact.letter.paragraphs)
    used_evidence_ids = {
        evidence_id
        for paragraph in artifact.letter.paragraphs
        for evidence_id in paragraph.candidate_evidence_ids
    }
    used_titles = {
        record.entry_title
        for record in artifact.evidence_records
        if record.id in used_evidence_ids and record.entry_title
    }

    assert artifact.ready_for_review
    assert artifact.fingerprint_inputs.posting_fingerprint == posting_fingerprint
    assert artifact.letter.job_title == target_title
    assert synthetic_posting.company_name in letter_text
    assert accepted
    assert used_titles
    assert all(title in letter_text for title in used_titles)
    assert all("unsupported_title_change" not in item.rejection_codes for item in accepted)
    assert all("copied_posting_language" not in item.rejection_codes for item in accepted)


def test_streamlit_posting_only_cover_letter_survives_unavailable_pagination(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    pagination, research_fetcher, cover_renderers, provider_constructions = _configure_offline_app(
        monkeypatch, tmp_path
    )
    profile = MasterProfile.model_validate_json(PROFILE_FIXTURE.read_text(encoding="utf-8"))
    dependencies.create_profile_repository(Settings()).save(profile)

    app = AppTest.from_file(str(ROOT / "src" / "resume_tailor" / "frontend" / "app.py"))
    app.session_state["profile_id"] = profile.id
    app.run()
    for key in (
        "posting",
        "plan",
        "generated_resume_artifact",
        COVER_LETTER_ARTIFACT_KEY,
    ):
        assert key not in app.session_state

    _navigate(app, "resume_studio")
    app.text_input(key="_resume_studio_job_title_widget").input(
        "Mechatronics Integration Engineer"
    ).run()
    app.text_area(key="_resume_studio_job_description_widget").input(
        POSTING_FIXTURE.read_text(encoding="utf-8")
    ).run()
    app.button(key="resume-create-strategy").click().run(timeout=30)

    posting = app.session_state["posting"]
    posting_fingerprint = content_fingerprint(posting)
    assert app.session_state["workflow_posting_fingerprint"] == posting_fingerprint
    assert content_fingerprint(app.session_state["plan"].posting) == posting_fingerprint

    app.button(key="resume-to-evidence").click().run()
    app.button(key="resume-build-document").click().run(timeout=60)
    resume_artifact = app.session_state["generated_resume_artifact"]
    assert resume_artifact.fingerprint_inputs.normalized_posting_fingerprint == (
        posting_fingerprint
    )

    _navigate(app, "cover_letters")
    optional_text_inputs = [
        item
        for item in app.text_input
        if item.label
        in {
            "Recipient name (optional)",
            "Recipient title (optional)",
            "Company",
            "Company domain (optional)",
        }
    ]
    for item in optional_text_inputs:
        item.input("")
        assert item.value == ""
    optional_text_areas = [
        item
        for item in app.text_area
        if item.label.startswith(("Official company", "Verified company", "Your motivation"))
    ]
    for item in optional_text_areas:
        item.input("")
        assert item.value == ""

    pagination_calls_before_cover = pagination.calls
    next(button for button in app.button if button.label == "Generate cover letter").click().run(
        timeout=60
    )

    assert not app.exception
    assert not app.error
    assert COVER_LETTER_ARTIFACT_KEY in app.session_state
    artifact = app.session_state[COVER_LETTER_ARTIFACT_KEY]
    renderer = cover_renderers[0]
    expected_research_request = CompanyResearchRequest(
        company_name=posting.company_name,
        company_domain=None,
        role_title=posting.title,
        job_url=posting.source_url,
        posting_fingerprint=posting_fingerprint,
        posting_description=posting.description,
        approved_sources=[],
        user_supplied_facts=[],
    )
    expected_recipient = CoverLetterRecipient(company=posting.company_name)

    assert artifact.fingerprint_inputs.posting_fingerprint == posting_fingerprint
    assert artifact.fingerprint_inputs.research_request_fingerprint == (
        content_fingerprint(expected_research_request)
    )
    assert artifact.fingerprint_inputs.recipient_fingerprint == (
        content_fingerprint(expected_recipient)
    )
    assert artifact.fingerprint_inputs.motivation_fingerprint is None
    assert artifact.company_research.status is CompanyResearchStatus.POSTING_ONLY
    posting_sources = {
        source.id
        for source in artifact.company_research.sources
        if source.stable_identifier.startswith("posting:")
    }
    posting_facts = {
        fact.id
        for fact in artifact.company_research.facts
        if fact.confidence is CompanyFactConfidence.POSTING_AUTHORITY
        and fact.source_id in posting_sources
    }
    verified_facts = [
        fact
        for fact in artifact.company_research.facts
        if fact.confidence is CompanyFactConfidence.VERIFIED
    ]
    assert posting_facts
    assert not verified_facts
    assert all(
        source.content_fingerprint == sha256(posting.description.encode("utf-8")).hexdigest()
        for source in artifact.company_research.sources
        if source.id in posting_sources
    )
    assert renderer.render_calls == 1
    assert renderer.rendered_candidate_count >= 1
    assert all(count >= 3 for count in renderer.composed_paragraph_counts)
    assert all(length > 0 for length in renderer.rendered_byte_lengths)
    assert artifact.candidate_validations
    assert all(
        diagnostic.posting_fingerprint == posting_fingerprint
        for diagnostic in artifact.candidate_validations
    )
    assert all(
        diagnostic.accepted_resume_narrative_fingerprint
        == artifact.fingerprint_inputs.final_resume_fingerprint
        for diagnostic in artifact.candidate_validations
    )
    accepted_candidates = [
        diagnostic
        for diagnostic in artifact.candidate_validations
        if all(
            status is not CoverLetterQualityGateStatus.FAILED
            for status in (
                diagnostic.structural_validation,
                diagnostic.company_validation,
                diagnostic.narrative_validation,
                diagnostic.claim_validation,
            )
        )
    ]
    assert accepted_candidates
    assert all(diagnostic.rendering_attempted for diagnostic in accepted_candidates)
    assert all(
        diagnostic.source_bound_sentence_count == diagnostic.sentence_count
        and diagnostic.unbound_sentence_count == 0
        for diagnostic in accepted_candidates
    )
    assert all(
        "copied_posting_language" not in diagnostic.rejection_codes
        for diagnostic in accepted_candidates
    )
    assert all(
        diagnostic.posting_authority_fact_count == len(posting_facts)
        for diagnostic in artifact.candidate_validations
    )
    assert all(
        diagnostic.verified_company_fact_count == 0 for diagnostic in artifact.candidate_validations
    )
    assert artifact.call_counts.claim_validations > 0
    assert all(
        claim.status is CoverLetterValidationStatus.SUPPORTED
        and set(claim.company_research_ids) <= posting_facts
        for paragraph in artifact.letter.paragraphs
        for claim in paragraph.claims
    )
    employer_text = " ".join(paragraph.text for paragraph in artifact.letter.paragraphs)
    employer_text_lower = employer_text.casefold()
    assert posting.company_name in employer_text
    assert "the employer" not in employer_text_lower
    assert len(artifact.letter.paragraphs) == 4
    assert 290 <= len(employer_text.split()) <= 425
    assert all(paragraph.sentence_authorities for paragraph in artifact.letter.paragraphs)
    assert max(len(paragraph.text.split()) for paragraph in artifact.letter.paragraphs) <= 135
    assert all(
        phrase not in employer_text_lower
        for phrase in (
            "reviewed evidence",
            "reviewed experience",
            "those records",
            "another reviewed example",
            "without changing the facts or scope",
            "implementation evidence",
            "includes work on act as",
            "work on working with",
        )
    )
    body_evidence_ids = [
        evidence_id
        for paragraph in artifact.letter.paragraphs[1:-1]
        for evidence_id in paragraph.candidate_evidence_ids
    ]
    assert len(body_evidence_ids) == len(set(body_evidence_ids))
    assert artifact.docx_bytes.startswith(b"PK\x03\x04")
    assert len(artifact.docx_bytes) in renderer.rendered_byte_lengths
    assert pagination.calls == pagination_calls_before_cover + 1
    page_fit_status = artifact.page_fit.status
    assert page_fit_status is CoverLetterPageFitStatus.PAGINATION_UNVERIFIED
    assert not artifact.page_fit.exact_pagination
    assert artifact.page_fit.manual_word_inspection_required
    assert 0.65 <= artifact.page_fit.estimated_utilization <= 0.96
    assert artifact.page_fit.underfill_or_overflow == "balanced_one_page"
    assert "null System.IntPtr" in (artifact.page_fit.pagination_failure or "")
    page_gate = next(gate for gate in artifact.quality_gates if gate.gate == "page_fit")
    assert page_gate.status is CoverLetterQualityGateStatus.REVIEW_REQUIRED
    assert artifact.ready_for_review
    assert artifact.review_state is CoverLetterReviewState.GENERATED_AWAITING_REVIEW
    assert any(item.value == "Letter review" for item in app.subheader)
    assert any("Exact Word pagination was unavailable" in item.value for item in app.warning)
    assert artifact.call_counts.provider_calls == 0
    assert artifact.call_counts.research_network_requests == 0
    assert research_fetcher.calls == 0
    assert not provider_constructions

    artifact_fingerprint = artifact.artifact_fingerprint
    artifact_bytes = artifact.docx_bytes
    render_calls = renderer.render_calls
    pagination_calls = pagination.calls
    next(
        button
        for button in app.get("download_button")
        if button.label == "Download review DOCX for inspection"
    ).click().run()
    inspection_artifact = app.session_state[COVER_LETTER_ARTIFACT_KEY]
    assert inspection_artifact.review_state is CoverLetterReviewState.GENERATED_AWAITING_REVIEW
    assert inspection_artifact.artifact_fingerprint == artifact_fingerprint
    assert inspection_artifact.docx_bytes == artifact_bytes
    assert renderer.render_calls == render_calls
    assert pagination.calls == pagination_calls
    assert research_fetcher.calls == 0
    assert not provider_constructions

    app.run()
    rerun_artifact = app.session_state[COVER_LETTER_ARTIFACT_KEY]
    assert rerun_artifact.artifact_fingerprint == artifact_fingerprint
    assert rerun_artifact.docx_bytes == artifact_bytes
    assert renderer.render_calls == render_calls
    assert pagination.calls == pagination_calls

    next(
        checkbox
        for checkbox in app.checkbox
        if checkbox.label.startswith("I reviewed the complete letter")
    ).check().run()
    next(
        checkbox
        for checkbox in app.checkbox
        if checkbox.label.startswith("I inspected this exact DOCX")
    ).check().run()
    next(button for button in app.button if button.label == "Approve cover letter").click().run()
    approved = app.session_state[COVER_LETTER_ARTIFACT_KEY]
    assert approved.review_state is CoverLetterReviewState.APPROVED
    assert approved.artifact_fingerprint == artifact_fingerprint
    assert approved.docx_bytes == artifact_bytes
    assert renderer.render_calls == render_calls
    assert pagination.calls == pagination_calls

    next(
        button for button in app.get("download_button") if button.label == "Download approved DOCX"
    ).click().run()
    downloaded = app.session_state[COVER_LETTER_ARTIFACT_KEY]
    assert downloaded.review_state is CoverLetterReviewState.DOWNLOADED
    assert downloaded.artifact_fingerprint == artifact_fingerprint
    assert downloaded.docx_bytes == artifact_bytes
    assert renderer.render_calls == render_calls
    assert pagination.calls == pagination_calls
    assert research_fetcher.calls == 0
    assert not provider_constructions

    _navigate(app, "resume_studio")
    app.pills(key="_resume_studio_stage_widget").set_value("Job context").run()
    app.text_area(key="_resume_studio_job_description_widget").input(
        POSTING_FIXTURE.read_text(encoding="utf-8")
        + "\n- Validate one additional hardware interface."
    ).run()
    app.button(key="resume-create-strategy").click().run(timeout=30)
    assert content_fingerprint(app.session_state["posting"]) != posting_fingerprint
    assert COVER_LETTER_ARTIFACT_KEY not in app.session_state
