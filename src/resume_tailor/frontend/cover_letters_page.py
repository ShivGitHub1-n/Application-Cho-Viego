"""Cover Letters workspace using the existing evidence-backed service boundary."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from resume_tailor.application.job_intake import InvalidJobDescriptionError, build_job_posting
from resume_tailor.application.workflow_state import set_active_application_context
from resume_tailor.domain.cover_letter import CoverLetterRecipient
from resume_tailor.domain.llm_models import LanguageModelError
from resume_tailor.domain.models import JobPosting, MasterProfile
from resume_tailor.frontend.cover_letter_view import render_cover_letter_view
from resume_tailor.frontend.document_canvas import render_document_canvas
from resume_tailor.frontend.shared_components import render_page_header
from resume_tailor.infrastructure.rendering import PageCountVerificationError, PageOverflowError


@dataclass(frozen=True)
class CoverLettersDependencies:
    """Composition-root dependencies; this page owns presentation state only."""

    tailor_service: Any
    clear_cover_letter_state: Callable[[], None]


def _profile_fingerprint(profile: MasterProfile) -> str:
    return profile.model_dump_json()


def _clear_cover_letter_export_artifacts(streamlit_module: Any) -> None:
    for key in ("cover_export_docx", "cover_export_status"):
        streamlit_module.session_state.pop(key, None)


def _clear_cover_letter_presentation_state(
    streamlit_module: Any, dependencies: CoverLettersDependencies
) -> None:
    dependencies.clear_cover_letter_state()
    streamlit_module.session_state.pop("cover_letter_claim_decisions", None)
    for key in tuple(streamlit_module.session_state):
        if key.startswith("_cover_claim_decision_widget_"):
            streamlit_module.session_state.pop(key, None)
    _clear_cover_letter_export_artifacts(streamlit_module)


def _decision_widget_key(claim_id: str) -> str:
    return f"_cover_claim_decision_widget_{claim_id}"


def _sync_claim_decision(streamlit_module: Any, claim_id: str, widget_key: str) -> None:
    """Persist an explicit decision without treating an unresolved claim as excluded."""

    state = streamlit_module.session_state
    decision = str(state.get(widget_key, "Approval required"))
    decisions = dict(state.get("cover_letter_claim_decisions", {}))
    previous = decisions.get(claim_id, "Approval required")
    if decision == "Approval required":
        decisions.pop(claim_id, None)
    else:
        decisions[claim_id] = decision
    if previous != decision:
        _clear_cover_letter_export_artifacts(streamlit_module)
    state["cover_letter_claim_decisions"] = decisions


def _current_fingerprints(
    profile: MasterProfile, posting: Any, plan: Any, recipient: Any
) -> dict[str, str]:
    selected_entities = set(plan.selected_entity_ids)
    evidence_fingerprint = ":".join(
        sorted(
            item.id
            for item in profile.evidence
            if item.confirmed and item.entity_id in selected_entities
        )
    )
    return {
        "cover_letter_profile_fingerprint": _profile_fingerprint(profile),
        "cover_letter_posting_fingerprint": posting.model_dump_json(),
        "cover_letter_plan_fingerprint": plan.model_dump_json(),
        "cover_letter_evidence_fingerprint": evidence_fingerprint,
        "cover_letter_recipient_fingerprint": recipient.model_dump_json(),
    }


def _render_setup(
    streamlit_module: Any,
    dependencies: CoverLettersDependencies,
    profile: MasterProfile,
    posting: Any,
    plan: Any,
) -> None:
    streamlit_module.subheader("Application context")
    streamlit_module.caption(
        f"Linked job · {posting.title} · {posting.company_name}. "
        "This draft uses the active tailoring plan."
    )
    recipient_name = streamlit_module.text_input(
        "Recipient name (optional)", key="cover_recipient_name"
    )
    recipient_title = streamlit_module.text_input(
        "Recipient title (optional)", key="cover_recipient_title"
    )
    recipient_company = streamlit_module.text_input(
        "Recipient or company (optional)",
        value=posting.company_name or "",
        key="cover_recipient_company",
    )
    recipient = CoverLetterRecipient(
        name=recipient_name.strip() or None,
        title=recipient_title.strip() or None,
        company=recipient_company.strip() or posting.company_name,
    )
    fingerprints = _current_fingerprints(profile, posting, plan, recipient)
    if any(
        streamlit_module.session_state.get(key) is not None
        and streamlit_module.session_state.get(key) != value
        for key, value in fingerprints.items()
    ):
        _clear_cover_letter_presentation_state(streamlit_module, dependencies)
    if streamlit_module.button(
        "Generate evidence-backed draft", key="cover-generate-draft", type="primary"
    ):
        try:
            _clear_cover_letter_presentation_state(streamlit_module, dependencies)
            streamlit_module.session_state["cover_letter"] = (
                dependencies.tailor_service.draft_cover_letter(
                    profile, posting, plan, recipient=recipient
                )
            )
            streamlit_module.session_state["cover_letter_reviewed"] = False
            streamlit_module.session_state["cover_letter_claim_decisions"] = {}
            streamlit_module.session_state.update(fingerprints)
            streamlit_module.success("Draft created for evidence and claim review.")
        except (ValueError, LanguageModelError) as error:
            streamlit_module.error(f"Cover-letter drafting failed: {error}")


def _render_review(
    streamlit_module: Any,
    dependencies: CoverLettersDependencies,
) -> None:
    letter = streamlit_module.session_state.get("cover_letter")
    if letter is None:
        streamlit_module.info("Generate a draft to open the document review and claim inspector.")
        return
    streamlit_module.subheader("Document review")
    sections = {
        "Recipient": [
            value
            for value in (
                letter.date_text,
                letter.salutation,
                letter.recipient.company,
            )
            if value
        ],
        "Letter": [paragraph.text for paragraph in letter.paragraphs],
        "Closing": [letter.closing, letter.signoff, letter.signoff_name],
    }
    review_column, inspector_column = streamlit_module.columns((3, 2))
    with review_column:
        render_document_canvas(
            streamlit_module,
            title="Cover-letter review canvas",
            sections=sections,
            caption=(
                "Subtle claim markers are reviewed alongside the letter. The service and "
                "renderer remain the authority for generated content and page fit."
            ),
        )
        for paragraph in letter.paragraphs:
            pending = [claim for claim in paragraph.claims if claim in letter.pending_claims]
            if pending:
                streamlit_module.caption(
                    "Approval-required claim marker · " + ", ".join(claim.id for claim in pending)
                )
    with inspector_column:
        streamlit_module.markdown("### Claim inspector")
        streamlit_module.caption(
            "Approve supported implications or exclude them from the final letter."
        )
        decisions = dict(streamlit_module.session_state.get("cover_letter_claim_decisions", {}))
        approved_ids: set[str] = set()
        for claim in letter.pending_claims:
            streamlit_module.markdown(f"**{claim.text}**")
            streamlit_module.caption("Supporting evidence: " + ", ".join(claim.evidence_ids))
            widget_key = _decision_widget_key(claim.id)
            if widget_key not in streamlit_module.session_state:
                streamlit_module.session_state[widget_key] = decisions.get(
                    claim.id, "Approval required"
                )
            decision = streamlit_module.selectbox(
                "Decision",
                ("Approval required", "Approve", "Exclude"),
                key=widget_key,
                label_visibility="collapsed",
                on_change=_sync_claim_decision,
                args=(streamlit_module, claim.id, widget_key),
            )
            if decision == "Approve":
                approved_ids.add(claim.id)
        unresolved = [
            claim.id
            for claim in letter.pending_claims
            if decisions.get(claim.id, "Approval required") not in {"Approve", "Exclude"}
        ]
        if unresolved:
            streamlit_module.warning(
                "Make an explicit Approve or Exclude decision for every approval-required claim."
            )
    reviewed = streamlit_module.checkbox(
        "I reviewed the complete cover letter and its supporting evidence.",
        key="cover_letter_reviewed",
    )
    if streamlit_module.button(
        "Confirm cover-letter review",
        key="cover-confirm-review",
        disabled=not reviewed or bool(unresolved),
    ):
        try:
            _clear_cover_letter_export_artifacts(streamlit_module)
            streamlit_module.session_state["cover_letter"] = (
                dependencies.tailor_service.approve_cover_letter(
                    letter, approved_ids, reviewed=True
                )
            )
            streamlit_module.success(
                "Cover-letter review recorded. Resume approvals remain separate."
            )
        except ValueError as error:
            streamlit_module.error(f"Cover-letter review could not be recorded: {error}")


def _render_export(streamlit_module: Any, dependencies: CoverLettersDependencies) -> None:
    streamlit_module.subheader("Export")
    letter = streamlit_module.session_state.get("cover_letter")
    can_export = bool(letter and letter.complete_review_confirmed and not letter.pending_claims)
    streamlit_module.caption("Exact one-page verification is required before export.")
    if streamlit_module.button(
        "Verify and prepare cover-letter export",
        key="cover-verify-export",
        type="primary",
        disabled=not can_export,
    ):
        _clear_cover_letter_export_artifacts(streamlit_module)
        try:
            with TemporaryDirectory() as directory:
                exported = dependencies.tailor_service.export_cover_letter(letter, Path(directory))
                if exported.export_path is None:
                    raise ValueError("Cover-letter export did not produce a file.")
                streamlit_module.session_state["cover_letter"] = exported
                streamlit_module.session_state["cover_export_docx"] = Path(
                    exported.export_path
                ).read_bytes()
                streamlit_module.session_state["cover_export_status"] = (
                    f"Verified exactly one page via {exported.page_count}-page DOCX measurement."
                )
        except PageCountVerificationError as error:
            streamlit_module.error(f"Exact page verification is unavailable: {error}")
        except PageOverflowError as error:
            streamlit_module.error(f"Cover-letter overflow must be resolved before export: {error}")
        except ValueError as error:
            streamlit_module.error(f"Cover-letter export failed: {error}")
    status = streamlit_module.session_state.get("cover_export_status")
    if status:
        streamlit_module.success(status)
        streamlit_module.download_button(
            "Download cover-letter DOCX",
            streamlit_module.session_state["cover_export_docx"],
            "cover-letter.docx",
            key="cover-download-docx",
        )


def render_cover_letters_page(
    streamlit_module: Any, dependencies: CoverLettersDependencies
) -> None:
    """Render setup, document review, inspector, and authoritative export gate."""

    render_page_header(
        streamlit_module,
        "Cover Letters",
        "Evidence-backed application letters linked to the active job and tailoring plan.",
    )
    profile = streamlit_module.session_state.get("profile")
    plan = streamlit_module.session_state.get("plan")
    posting = streamlit_module.session_state.get("posting")
    if not isinstance(profile, MasterProfile):
        streamlit_module.info(
            "Choose a reviewed Career Profile before drafting a cover letter."
        )
        return
    if posting is None:
        with streamlit_module.form("cover-letter-direct-job-context", border=True):
            streamlit_module.subheader("Job context")
            company = streamlit_module.text_input("Company", key="cover_direct_company")
            title = streamlit_module.text_input("Role", key="cover_direct_role")
            description = streamlit_module.text_area(
                "Paste job description",
                key="cover_direct_posting",
                height=220,
            )
            submitted = streamlit_module.form_submit_button(
                "Use this job for Cover Letters",
                type="primary",
            )
        if submitted:
            try:
                direct_posting = build_job_posting(
                    "cover-letter-direct-posting",
                    title,
                    description,
                    company_name=company,
                )
            except InvalidJobDescriptionError as error:
                streamlit_module.error(str(error))
            else:
                set_active_application_context(streamlit_module.session_state, direct_posting)
                streamlit_module.rerun()
        return
    with streamlit_module.expander("Use a different pasted job", expanded=False):
        streamlit_module.session_state.setdefault(
            "cover_direct_company", posting.company_name or ""
        )
        streamlit_module.session_state.setdefault("cover_direct_role", posting.title)
        streamlit_module.session_state.setdefault(
            "cover_direct_posting", str(getattr(posting, "description", ""))
        )
        with streamlit_module.form("cover-letter-direct-job-context", border=True):
            company = streamlit_module.text_input(
                "Company",
                key="cover_direct_company",
            )
            title = streamlit_module.text_input(
                "Role",
                key="cover_direct_role",
            )
            description = streamlit_module.text_area(
                "Paste job description",
                key="cover_direct_posting",
                height=180,
            )
            replace_context = streamlit_module.form_submit_button(
                "Use this job for Cover Letters"
            )
        if replace_context:
            try:
                replacement = build_job_posting(
                    "cover-letter-direct-posting",
                    title,
                    description,
                    company_name=company,
                )
            except InvalidJobDescriptionError as error:
                streamlit_module.error(str(error))
            else:
                set_active_application_context(streamlit_module.session_state, replacement)
                streamlit_module.rerun()
    if hasattr(dependencies.tailor_service, "generate_cover_letter_artifact"):
        if not isinstance(posting, JobPosting):
            streamlit_module.error("The active application context is not a validated posting.")
            return
        # The converged application uses the newer immutable-artifact workflow.
        # Keep the Precision Workbench route and header, but delegate generation,
        # evidence review, approval, currentness, and stored-byte download to the
        # accepted cover-letter delivery view instead of the legacy draft/export
        # methods retained by the deterministic page harness.
        render_cover_letter_view(
            dependencies.tailor_service,
            profile,
            posting,
            plan,
        )
        return
    if plan is None:
        streamlit_module.info(
            "This compatibility-only cover-letter path requires a tailoring plan."
        )
        return
    _render_setup(streamlit_module, dependencies, profile, posting, plan)
    _render_review(streamlit_module, dependencies)
    _render_export(streamlit_module, dependencies)


__all__ = [
    "CoverLettersDependencies",
    "_clear_cover_letter_export_artifacts",
    "render_cover_letters_page",
]
