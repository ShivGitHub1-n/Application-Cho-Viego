from __future__ import annotations

from hashlib import sha256
from typing import Any, cast

import streamlit as st

from resume_tailor.application.cover_letter import CoverLetterCandidateRejectionError
from resume_tailor.application.generated_artifact import content_fingerprint
from resume_tailor.application.workflow_state import (
    COVER_LETTER_ARTIFACT_KEY,
    COVER_LETTER_CANDIDATE_DIAGNOSTICS_KEY,
    COVER_LETTER_GENERATION_ERROR_KEY,
    COVER_LETTER_INPUT_FINGERPRINT_KEY,
    COVER_LETTER_REVIEW_STATE_KEY,
)
from resume_tailor.domain.company_research import (
    ApprovedCompanySource,
    CompanyResearchRequest,
    CompanySourceType,
)
from resume_tailor.domain.cover_letter import (
    CoverLetterQualityGateStatus,
    CoverLetterRecipient,
    CoverLetterReviewState,
    GeneratedCoverLetterArtifact,
)
from resume_tailor.domain.llm_models import LanguageModelError
from resume_tailor.domain.models import JobPosting, MasterProfile, TailoringPlan


def render_cover_letter_view(
    service: Any,
    profile: MasterProfile,
    posting: JobPosting,
    plan: TailoringPlan | None,
) -> None:
    """Render a review-first cover-letter workflow around immutable artifacts."""

    with st.container(border=True):
        company_column, role_column = st.columns(2)
        company_column.caption("COMPANY")
        company_column.write(posting.company_name or "Company not provided")
        role_column.caption("ROLE")
        role_column.write(posting.title)
        if posting.source_url:
            st.caption(f"Active posting: {posting.source_url}")
    st.caption(
        "This letter independently selects narrative evidence from the active reviewed "
        "Career Profile. It does not require or copy a generated résumé."
    )
    inputs = _render_inputs(posting)
    recipient, research_request, motivation, submitted = inputs
    input_fingerprint = _input_fingerprint(recipient, research_request, motivation)

    if submitted:
        previous = st.session_state.get(COVER_LETTER_ARTIFACT_KEY)
        st.session_state[COVER_LETTER_REVIEW_STATE_KEY] = CoverLetterReviewState.GENERATING.value
        st.session_state.pop(COVER_LETTER_GENERATION_ERROR_KEY, None)
        st.session_state.pop(COVER_LETTER_CANDIDATE_DIAGNOSTICS_KEY, None)
        try:
            with st.status("Generating grounded cover letter", expanded=True) as status:
                status.write("Selecting reviewed evidence and checking approved company sources")
                artifact = cast(
                    GeneratedCoverLetterArtifact,
                    service.generate_cover_letter_artifact(
                        profile,
                        posting,
                        plan,
                        recipient=recipient,
                        final_resume=None,
                        research_request=research_request,
                        explicit_motivation=motivation,
                    ),
                )
                status.update(label="Cover letter generated", state="complete")
            artifact_to_store, committed = _artifact_after_build(previous, artifact)
            st.session_state[COVER_LETTER_ARTIFACT_KEY] = artifact_to_store
            st.session_state[COVER_LETTER_REVIEW_STATE_KEY] = artifact.review_state.value
            if committed:
                st.session_state[COVER_LETTER_INPUT_FINGERPRINT_KEY] = input_fingerprint
                st.session_state[COVER_LETTER_CANDIDATE_DIAGNOSTICS_KEY] = (
                    artifact.candidate_validations
                )
            else:
                failed_gates = [
                    gate.code
                    for gate in artifact.quality_gates
                    if gate.status is CoverLetterQualityGateStatus.FAILED
                ]
                st.session_state[COVER_LETTER_GENERATION_ERROR_KEY] = (
                    "The new artifact failed quality gates and the prior valid artifact "
                    f"was preserved. Failed gates: {', '.join(failed_gates) or 'unknown'}."
                )
        except CoverLetterCandidateRejectionError as error:
            if previous is not None:
                st.session_state[COVER_LETTER_ARTIFACT_KEY] = previous
            st.session_state[COVER_LETTER_REVIEW_STATE_KEY] = (
                CoverLetterReviewState.GENERATION_FAILED.value
            )
            st.session_state[COVER_LETTER_CANDIDATE_DIAGNOSTICS_KEY] = error.diagnostics
            st.session_state[COVER_LETTER_GENERATION_ERROR_KEY] = str(error)
        except (ValueError, LanguageModelError) as error:
            if previous is not None:
                st.session_state[COVER_LETTER_ARTIFACT_KEY] = previous
            st.session_state[COVER_LETTER_REVIEW_STATE_KEY] = (
                CoverLetterReviewState.GENERATION_FAILED.value
            )
            st.session_state[COVER_LETTER_GENERATION_ERROR_KEY] = str(error)

    error_message = st.session_state.get(COVER_LETTER_GENERATION_ERROR_KEY)
    if error_message:
        st.error(f"Cover-letter generation failed: {error_message}")
        diagnostics = st.session_state.get(COVER_LETTER_CANDIDATE_DIAGNOSTICS_KEY, [])
        if diagnostics:
            with st.expander("Candidate validation details", expanded=True):
                for diagnostic in diagnostics:
                    failed = ", ".join(diagnostic.rejection_codes) or "none"
                    st.write(
                        f"Candidate {diagnostic.candidate_index + 1} "
                        f"({diagnostic.generation_source}): {failed}"
                    )
                    for summary in diagnostic.rejection_summaries:
                        st.caption(summary)
    stored_artifact = cast(
        GeneratedCoverLetterArtifact | None,
        st.session_state.get(COVER_LETTER_ARTIFACT_KEY),
    )
    if stored_artifact is None:
        return
    artifact = stored_artifact

    artifact_current = bool(
        service.cover_letter_artifact_is_current(
            artifact,
            profile,
            posting,
            plan,
            recipient=recipient,
            final_resume=None,
            research_request=research_request,
            explicit_motivation=motivation,
        )
    )
    if not artifact_current:
        st.warning(
            "This artifact is stale because a profile, posting, research, or letter input "
            "changed. It cannot be approved or downloaded."
        )

    _render_status(artifact, artifact_current)
    _render_letter(artifact)
    _render_diagnostics(artifact)
    artifact = _render_approval(service, artifact, artifact_current)
    _render_download(service, artifact, artifact_current)


def _render_inputs(
    posting: JobPosting,
) -> tuple[CoverLetterRecipient, CompanyResearchRequest, str | None, bool]:
    posting_fingerprint = content_fingerprint(posting)
    widget_scope = posting_fingerprint[:16]
    with st.form("cover-letter-inputs", border=True):
        recipient_name = st.text_input(
            "Recipient name (optional)",
            key=f"cover_recipient_name_{widget_scope}",
        )
        recipient_title = st.text_input(
            "Recipient title (optional)",
            key=f"cover_recipient_title_{widget_scope}",
        )
        company_domain = st.text_input(
            "Company domain (optional)",
            help="Used to restrict official-source fetching to the company's domain.",
            key=f"cover_company_domain_{widget_scope}",
        )
        official_urls_text = st.text_area(
            "Official company source URLs (optional, one per line; maximum three)",
            height=96,
            key=f"cover_official_urls_{widget_scope}",
        )
        company_facts_text = st.text_area(
            "Verified company facts you supplied (optional, one per line; maximum three)",
            height=96,
            key=f"cover_company_facts_{widget_scope}",
        )
        motivation_text = st.text_area(
            "Your motivation or role preference (optional)",
            help="Only explicit wording entered here may be treated as personal motivation.",
            height=88,
            key=f"cover_motivation_{widget_scope}",
        )
        submitted = st.form_submit_button(
            "Generate cover letter",
            type="primary",
            icon=":material/article:",
        )
    recipient = CoverLetterRecipient(
        name=recipient_name.strip() or None,
        title=recipient_title.strip() or None,
        company=posting.company_name,
    )
    official_urls = [line.strip() for line in official_urls_text.splitlines() if line.strip()][:3]
    user_facts = [line.strip() for line in company_facts_text.splitlines() if line.strip()][:3]
    research_request = CompanyResearchRequest(
        company_name=recipient.company,
        company_domain=company_domain.strip() or None,
        role_title=posting.title,
        job_url=posting.source_url,
        posting_fingerprint=posting_fingerprint,
        posting_description=posting.description,
        approved_sources=[
            ApprovedCompanySource(
                url=url,
                source_type=CompanySourceType.OFFICIAL_WEBSITE,
            )
            for url in official_urls
        ],
        user_supplied_facts=user_facts,
    )
    return recipient, research_request, motivation_text.strip() or None, submitted


def _input_fingerprint(
    recipient: CoverLetterRecipient,
    research_request: CompanyResearchRequest,
    motivation: str | None,
) -> str:
    serialized = (
        recipient.model_dump_json() + research_request.model_dump_json() + (motivation or "")
    )
    return sha256(serialized.encode()).hexdigest()


def _artifact_after_build(
    previous: GeneratedCoverLetterArtifact | None,
    generated: GeneratedCoverLetterArtifact,
) -> tuple[GeneratedCoverLetterArtifact, bool]:
    """Preserve the last valid bytes when a rebuild returns failed quality gates."""

    if previous is not None and previous.ready_for_review and not generated.ready_for_review:
        return previous, False
    return generated, True


def _render_status(
    artifact: GeneratedCoverLetterArtifact,
    artifact_current: bool,
) -> None:
    passed_claims = not any(
        gate.status is CoverLetterQualityGateStatus.FAILED
        for gate in artifact.quality_gates
        if gate.gate in {"candidate_grounding", "company_grounding", "resume_consistency"}
    )
    columns = st.columns(4)
    columns[0].metric(
        "Research",
        artifact.company_research.status.value.replace("_", " ").title(),
    )
    columns[1].metric("Writer", _writer_status(artifact))
    columns[2].metric("Claims", "Passed" if passed_claims else "Review required")
    columns[3].metric("Page use", f"{artifact.page_fit.estimated_utilization:.0%}")
    st.caption(
        f"State: {artifact.review_state.value.replace('_', ' ')} · "
        f"Artifact v{artifact.artifact_version} · "
        f"{'Current' if artifact_current else 'Stale'} · "
        f"{artifact.page_fit.estimated_remaining_lines} estimated lines remaining"
    )


def _writer_status(artifact: GeneratedCoverLetterArtifact) -> str:
    diagnostic = artifact.provider_diagnostic
    if diagnostic.provider_candidate_selected and not diagnostic.fallback_reason:
        return "Gemini"
    reason = diagnostic.fallback_reason
    if reason is None:
        return "Gemini"
    labels = {
        "provider_disabled": "provider disabled",
        "credentials_absent": "provider unavailable",
        "provider_malformed_after_repair": "response parsing failed",
        "provider_timeout": "provider timed out",
        "provider_rate_limit": "provider rate limited",
        "provider_unavailable": "provider unavailable",
        "all_generated_paragraphs_rejected": "response failed validation",
        "provider_page_fit_rejected": "provider draft did not fit",
    }
    return "Fallback — " + labels.get(reason.value, "provider draft not used")


def _render_letter(artifact: GeneratedCoverLetterArtifact) -> None:
    with st.container(border=True):
        st.subheader("Letter review")
        st.write(artifact.letter.date_text)
        st.write(artifact.letter.salutation)
        for paragraph in artifact.letter.paragraphs:
            st.write(paragraph.text)
        st.write(artifact.letter.signoff)
        st.write(f"**{artifact.letter.signoff_name}**")


def _render_diagnostics(artifact: GeneratedCoverLetterArtifact) -> None:
    with st.expander("Evidence, sources, and diagnostics", expanded=False):
        for paragraph in artifact.letter.paragraphs:
            st.markdown(f"**{paragraph.purpose.value.replace('_', ' ').title()}**")
            st.caption(
                "Candidate evidence: "
                + (", ".join(paragraph.candidate_evidence_ids) or "none")
                + " · Company facts: "
                + (", ".join(paragraph.company_research_ids) or "none")
            )
        for source in artifact.company_research.sources:
            st.write(
                f"Source: {source.title} — {source.publisher} ({source.retrieved_on.isoformat()})"
            )
            if source.source_url:
                st.caption(source.source_url)
        for gate in artifact.quality_gates:
            st.write(
                f"{gate.gate.replace('_', ' ').title()}: "
                f"{gate.status.value.replace('_', ' ')} — {gate.detail}"
            )
        st.json(
            {
                "provider": artifact.provider_diagnostic.model_dump(mode="json"),
                "call_counts": artifact.call_counts.model_dump(mode="json"),
                "page_fit": artifact.page_fit.model_dump(mode="json"),
                "candidate_validations": [
                    item.model_dump(mode="json") for item in artifact.candidate_validations
                ],
                "research_events": [item.value for item in artifact.company_research.events],
                "research_limitations": artifact.company_research.limitations,
                "rejected_claims": [
                    item.model_dump(mode="json") for item in artifact.rejected_claims
                ],
                "review_required_claims": [
                    item.model_dump(mode="json") for item in artifact.review_required_claims
                ],
                "resume_consistency": [
                    item.model_dump(mode="json") for item in artifact.resume_consistency
                ],
            },
            expanded=False,
        )


def _render_approval(
    service: Any,
    artifact: GeneratedCoverLetterArtifact,
    artifact_current: bool,
) -> GeneratedCoverLetterArtifact:
    already_approved = artifact.review_state in {
        CoverLetterReviewState.APPROVED,
        CoverLetterReviewState.DOWNLOADED,
    }
    if already_approved:
        st.success("This exact artifact is approved.")
        return artifact
    if artifact_current:
        st.download_button(
            "Download review DOCX for inspection",
            data=artifact.docx_bytes,
            file_name="cover-letter-review.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key="cover_letter_review_download",
        )
    reviewed = st.checkbox(
        "I reviewed the complete letter, evidence, and company-source report.",
        key="cover_letter_complete_review",
    )
    if artifact.page_fit.manual_word_inspection_required:
        st.error(
            "Exact pagination was unavailable. This review copy cannot be approved or "
            "exported; generate in an environment with Microsoft Word or LibreOffice "
            "pagination configured."
        )
    if st.button(
        "Approve cover letter",
        type="primary",
        icon=":material/verified:",
        disabled=(
            not reviewed
            or not artifact.ready_for_review
            or not artifact_current
        ),
    ):
        artifact = cast(
            GeneratedCoverLetterArtifact,
            service.approve_cover_letter_artifact(
                artifact,
                expected_fingerprint=artifact.artifact_fingerprint,
                manual_word_inspection_confirmed=False,
            ),
        )
        st.session_state[COVER_LETTER_ARTIFACT_KEY] = artifact
        st.session_state[COVER_LETTER_REVIEW_STATE_KEY] = artifact.review_state.value
        st.success("Cover letter approved. The stored DOCX is ready to download.")
    return artifact


def _render_download(
    service: Any,
    artifact: GeneratedCoverLetterArtifact,
    artifact_current: bool,
) -> None:
    if (
        artifact.review_state
        not in {
            CoverLetterReviewState.APPROVED,
            CoverLetterReviewState.DOWNLOADED,
        }
        or not artifact_current
    ):
        st.caption("Download is enabled after explicit approval of the current artifact.")
        return
    download = service.prepare_cover_letter_download(
        artifact,
        expected_fingerprint=artifact.artifact_fingerprint,
    )

    def mark_downloaded() -> None:
        current = cast(
            GeneratedCoverLetterArtifact,
            st.session_state[COVER_LETTER_ARTIFACT_KEY],
        )
        if current.review_state is CoverLetterReviewState.APPROVED:
            updated = service.mark_cover_letter_downloaded(current)
            st.session_state[COVER_LETTER_ARTIFACT_KEY] = updated
            st.session_state[COVER_LETTER_REVIEW_STATE_KEY] = updated.review_state.value

    st.download_button(
        "Download approved DOCX",
        data=download.docx_bytes,
        file_name="cover-letter.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        icon=":material/download:",
        on_click=mark_downloaded,
    )
    st.caption(
        f"Prepared in {download.elapsed_seconds:.3f}s from exact stored bytes; zero "
        "generation, research, validation, rendering, or pagination calls."
    )


__all__ = ["render_cover_letter_view"]
