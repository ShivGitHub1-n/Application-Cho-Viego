"""Staged Resume Studio presentation backed by the established tailoring service."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from resume_tailor.application.job_intake import InvalidJobDescriptionError, build_job_posting
from resume_tailor.domain.llm_models import LanguageModelError
from resume_tailor.domain.models import MasterProfile, TemplateConstraints
from resume_tailor.frontend.document_canvas import generated_resume_groups, render_document_canvas
from resume_tailor.frontend.shared_components import render_page_header
from resume_tailor.infrastructure.rendering import (
    PageCountVerificationError,
    PageOverflowError,
)


class ResumeStudioStage(StrEnum):
    JOB_CONTEXT = "Job context"
    STRATEGY = "Strategy"
    EVIDENCE = "Evidence selection"
    REVIEW = "Resume review"
    EXPORT = "Export"


STAGE_OPTIONS = tuple(stage.value for stage in ResumeStudioStage)

_ACTIVE_STAGE_KEY = "resume_studio_stage"
_STAGE_WIDGET_KEY = "_resume_studio_stage_widget"
_PENDING_STAGE_KEY = "resume_studio_pending_stage"
_JOB_TITLE_KEY = "job_title_input"
_JOB_TITLE_WIDGET_KEY = "_resume_studio_job_title_widget"
_JOB_DESCRIPTION_KEY = "job_description_input"
_JOB_DESCRIPTION_WIDGET_KEY = "_resume_studio_job_description_widget"
_REVIEW_CONFIRMED_KEY = "resume_studio_review_confirmed"
_REVIEW_WIDGET_KEY = "_resume_studio_review_confirmed_widget"


@dataclass(frozen=True)
class ResumeStudioDependencies:
    """Dependencies supplied by the Streamlit application composition root."""

    tailor_service: Any
    resume_renderer: Any
    invalidate_tailoring: Callable[[], None]


def _profile_fingerprint(profile: MasterProfile) -> str:
    return profile.model_dump_json()


def _normalize_stage(value: object) -> ResumeStudioStage:
    try:
        return ResumeStudioStage(str(value))
    except ValueError:
        return ResumeStudioStage.JOB_CONTEXT


def _consume_stage_intent(streamlit_module: Any) -> ResumeStudioStage:
    """Resolve permanent and pending state before the native pills widget exists."""

    state = streamlit_module.session_state
    pending = state.pop(_PENDING_STAGE_KEY, None)
    raw_active = state.get(_ACTIVE_STAGE_KEY)
    active_stage = _normalize_stage(pending if pending is not None else raw_active)
    state[_ACTIVE_STAGE_KEY] = active_stage.value
    if pending is not None or raw_active not in STAGE_OPTIONS or _STAGE_WIDGET_KEY not in state:
        state[_STAGE_WIDGET_KEY] = active_stage.value
    return active_stage


def _request_stage(streamlit_module: Any, stage: ResumeStudioStage) -> None:
    """Request navigation on the next rerun without mutating a live widget key."""

    streamlit_module.session_state[_PENDING_STAGE_KEY] = stage.value
    streamlit_module.rerun()


def _clear_resume_export_artifacts(streamlit_module: Any) -> None:
    """Remove export artifacts whenever the document/export authority changes."""

    for key in ("resume_export_docx", "resume_export_pdf", "resume_export_status"):
        streamlit_module.session_state.pop(key, None)


def _invalidate_resume_presentation_state(
    streamlit_module: Any, dependencies: ResumeStudioDependencies
) -> None:
    """Clear derived UI artifacts alongside the authoritative workflow reset."""

    dependencies.invalidate_tailoring()
    for key in (
        "resume_approved_claim_ids",
        "resume_evidence_selection_ids",
        "resume_generated_approval_ids",
        _REVIEW_CONFIRMED_KEY,
        _REVIEW_WIDGET_KEY,
    ):
        streamlit_module.session_state.pop(key, None)
    _clear_resume_export_artifacts(streamlit_module)


def _invalidate_if_inputs_changed(
    streamlit_module: Any,
    dependencies: ResumeStudioDependencies,
    profile: MasterProfile | None,
) -> None:
    state = streamlit_module.session_state
    if profile is not None and state.get("workflow_profile_fingerprint") not in (
        None,
        _profile_fingerprint(profile),
    ):
        _invalidate_resume_presentation_state(streamlit_module, dependencies)
        state[_PENDING_STAGE_KEY] = ResumeStudioStage.JOB_CONTEXT.value
        return
    description = str(state.get(_JOB_DESCRIPTION_KEY, "")).strip()
    if not description or state.get("workflow_posting_fingerprint") is None:
        return
    try:
        posting = build_job_posting(
            "local-posting", str(state.get(_JOB_TITLE_KEY, "")), description
        )
    except InvalidJobDescriptionError:
        _invalidate_resume_presentation_state(streamlit_module, dependencies)
        state[_PENDING_STAGE_KEY] = ResumeStudioStage.JOB_CONTEXT.value
        return
    if state["workflow_posting_fingerprint"] != posting.model_dump_json():
        _invalidate_resume_presentation_state(streamlit_module, dependencies)
        state[_PENDING_STAGE_KEY] = ResumeStudioStage.JOB_CONTEXT.value


def _prepare_job_context_widgets(streamlit_module: Any) -> None:
    state = streamlit_module.session_state
    state.setdefault(_JOB_TITLE_KEY, "")
    state.setdefault(_JOB_DESCRIPTION_KEY, "")
    if _JOB_TITLE_WIDGET_KEY not in state:
        state[_JOB_TITLE_WIDGET_KEY] = state[_JOB_TITLE_KEY]
    if _JOB_DESCRIPTION_WIDGET_KEY not in state:
        state[_JOB_DESCRIPTION_WIDGET_KEY] = state[_JOB_DESCRIPTION_KEY]


def _sync_job_context(streamlit_module: Any) -> None:
    state = streamlit_module.session_state
    state[_JOB_TITLE_KEY] = str(state.get(_JOB_TITLE_WIDGET_KEY, ""))
    state[_JOB_DESCRIPTION_KEY] = str(state.get(_JOB_DESCRIPTION_WIDGET_KEY, ""))


def _approval_widget_key(kind: str, item_id: str) -> str:
    """Return a transient key for an approval control.

    The permanent approval sets below are workflow authority. These keys only
    hold the value while the corresponding conditional widget is rendered.
    """

    return f"_resume_{kind}_approval_widget_{item_id}"


def _seed_approval_widget(
    streamlit_module: Any, key: str, approved_ids: set[str], item_id: str
) -> None:
    state = streamlit_module.session_state
    if key not in state:
        state[key] = item_id in approved_ids


def _record_evidence_selection(streamlit_module: Any, approved_ids: set[str]) -> None:
    state = streamlit_module.session_state
    previous = set(state.get("resume_evidence_selection_ids", set()))
    if previous != approved_ids:
        state["resume_evidence_selection_ids"] = approved_ids
        state.pop("resume", None)
        state.pop(_REVIEW_CONFIRMED_KEY, None)
        state[_REVIEW_WIDGET_KEY] = False
        _clear_resume_export_artifacts(streamlit_module)


def _record_generated_approvals(streamlit_module: Any, approved_ids: set[str]) -> None:
    state = streamlit_module.session_state
    previous = set(state.get("resume_generated_approval_ids", set()))
    if previous != approved_ids:
        state["resume_generated_approval_ids"] = approved_ids
        state.pop(_REVIEW_CONFIRMED_KEY, None)
        state[_REVIEW_WIDGET_KEY] = False
        _clear_resume_export_artifacts(streamlit_module)


def _sync_review_confirmation(streamlit_module: Any) -> None:
    state = streamlit_module.session_state
    confirmed = bool(state.get(_REVIEW_WIDGET_KEY, False))
    if bool(state.get(_REVIEW_CONFIRMED_KEY, False)) != confirmed:
        state[_REVIEW_CONFIRMED_KEY] = confirmed
        _clear_resume_export_artifacts(streamlit_module)


def _render_job_context(
    streamlit_module: Any,
    dependencies: ResumeStudioDependencies,
    profile: MasterProfile | None,
) -> None:
    streamlit_module.subheader("Job context")
    if profile is None:
        streamlit_module.info(
            "Choose a reviewed Career Profile before creating a tailoring strategy."
        )
        return
    streamlit_module.caption(f"Using reviewed profile · {profile.display_name} · {profile.id}")
    _prepare_job_context_widgets(streamlit_module)
    title = streamlit_module.text_input(
        "Job title",
        key=_JOB_TITLE_WIDGET_KEY,
        on_change=_sync_job_context,
        args=(streamlit_module,),
    )
    description = streamlit_module.text_area(
        "Paste job description",
        key=_JOB_DESCRIPTION_WIDGET_KEY,
        height=220,
        placeholder="Paste the full posting or arrive here from a selected Jobs posting.",
        on_change=_sync_job_context,
        args=(streamlit_module,),
    )
    if streamlit_module.button(
        "Create authoritative strategy", key="resume-create-strategy", type="primary"
    ):
        try:
            _sync_job_context(streamlit_module)
            posting = build_job_posting("local-posting", title, description)
            _invalidate_resume_presentation_state(streamlit_module, dependencies)
            plan = dependencies.tailor_service.create_plan(profile, posting, TemplateConstraints())
            state = streamlit_module.session_state
            state["posting"] = posting
            state["plan"] = plan
            state["workflow_profile_fingerprint"] = _profile_fingerprint(profile)
            state["workflow_posting_fingerprint"] = posting.model_dump_json()
            state["resume_approved_claim_ids"] = set()
            state["resume_evidence_selection_ids"] = set()
            state[_REVIEW_CONFIRMED_KEY] = False
            _request_stage(streamlit_module, ResumeStudioStage.STRATEGY)
        except (InvalidJobDescriptionError, ValueError, LanguageModelError) as error:
            streamlit_module.error(f"Job context could not produce a strategy: {error}")


def _render_strategy(streamlit_module: Any, plan: Any | None) -> None:
    streamlit_module.subheader("Recommended strategy")
    if plan is None:
        streamlit_module.info("Create job context before reviewing the recommendation.")
        return
    strategy = getattr(plan, "strategy", None)
    if strategy is None:
        warnings = getattr(getattr(plan, "report", None), "warnings", ())
        streamlit_module.warning(
            warnings[0] if warnings else "A strategy is not available for this context."
        )
        return
    streamlit_module.write(strategy.rationale)
    streamlit_module.caption(f"Primary focus: {strategy.primary_focus}")
    report = plan.report
    if report.profile_fit and report.profile_fit.status.value != "sufficient":
        streamlit_module.warning(report.profile_fit.reason)
    if report.uncovered_signals:
        streamlit_module.warning("Profile gaps: " + ", ".join(report.uncovered_signals))
    streamlit_module.markdown("**Decision review**")
    for decision in report.decisions:
        streamlit_module.write(f"{decision.action.replace('_', ' ').title()} — {decision.reason}")
    if streamlit_module.button("Review evidence selection", key="resume-to-evidence"):
        _request_stage(streamlit_module, ResumeStudioStage.EVIDENCE)


def _pending_claim_ids(plan: Any) -> list[str]:
    return [
        candidate.id
        for candidate in plan.claim_candidates
        if candidate.support.value == "strong_inference_pending_review"
    ]


def _render_evidence_selection(
    streamlit_module: Any,
    dependencies: ResumeStudioDependencies,
    profile: MasterProfile | None,
    plan: Any | None,
) -> None:
    streamlit_module.subheader("Evidence selection")
    if profile is None or plan is None or getattr(plan, "strategy", None) is None:
        streamlit_module.info(
            "A reviewed profile and strategy are required before document generation."
        )
        return
    streamlit_module.caption("Only reviewed profile evidence can support generated résumé content.")
    approved_ids: set[str] = set()
    permanent_ids = set(
        streamlit_module.session_state.get("resume_evidence_selection_ids", set())
    )
    for claim_id in _pending_claim_ids(plan):
        widget_key = _approval_widget_key("evidence", claim_id)
        _seed_approval_widget(streamlit_module, widget_key, permanent_ids, claim_id)
        if streamlit_module.checkbox(
            f"Approve inferred wording: {claim_id}", key=widget_key
        ):
            approved_ids.add(claim_id)
    _record_evidence_selection(streamlit_module, approved_ids)
    if streamlit_module.button(
        "Build reviewed resume", key="resume-build-document", type="primary"
    ):
        try:
            _clear_resume_export_artifacts(streamlit_module)
            streamlit_module.session_state["resume"] = dependencies.tailor_service.build_document(
                plan, profile, approved_ids
            )
            streamlit_module.session_state["resume_approved_claim_ids"] = approved_ids
            streamlit_module.session_state[_REVIEW_CONFIRMED_KEY] = False
            streamlit_module.session_state.pop(_REVIEW_WIDGET_KEY, None)
            _request_stage(streamlit_module, ResumeStudioStage.REVIEW)
        except (ValueError, LanguageModelError) as error:
            streamlit_module.error(f"Résumé document could not be built: {error}")


def _render_review(streamlit_module: Any, plan: Any | None, profile: MasterProfile | None) -> None:
    streamlit_module.subheader("Résumé review")
    resume = streamlit_module.session_state.get("resume")
    if plan is None or profile is None or resume is None:
        streamlit_module.info("Build a reviewed résumé before document review.")
        return
    render_document_canvas(
        streamlit_module,
        title="Résumé review canvas",
        sections=generated_resume_groups(resume),
        caption=(
            "This canvas is a review surface. DOCX rendering and exact page "
            "verification remain authoritative."
        ),
    )
    pending_ids: set[str] = set()
    permanent_ids = set(
        streamlit_module.session_state.get("resume_generated_approval_ids", set())
    )
    if resume.review_pending_bullets or resume.review_pending_skills:
        streamlit_module.markdown("**Approval-required generated content**")
        for bullet in resume.review_pending_bullets:
            widget_key = _approval_widget_key("generated_bullet", bullet.id)
            _seed_approval_widget(streamlit_module, widget_key, permanent_ids, bullet.id)
            if streamlit_module.checkbox(
                f"Approve inferred bullet: {bullet.text}", key=widget_key
            ):
                pending_ids.add(bullet.id)
        for skill in resume.review_pending_skills:
            widget_key = _approval_widget_key("generated_skill", skill.id)
            _seed_approval_widget(streamlit_module, widget_key, permanent_ids, skill.id)
            if streamlit_module.checkbox(
                f"Approve inferred skill: {skill.value}", key=widget_key
            ):
                pending_ids.add(skill.id)
    _record_generated_approvals(streamlit_module, pending_ids)
    state = streamlit_module.session_state
    if _REVIEW_WIDGET_KEY not in state:
        state[_REVIEW_WIDGET_KEY] = bool(state.get(_REVIEW_CONFIRMED_KEY, False))
    reviewed = streamlit_module.checkbox(
        "I reviewed the generated résumé content for export.",
        key=_REVIEW_WIDGET_KEY,
        on_change=_sync_review_confirmation,
        args=(streamlit_module,),
    )
    if streamlit_module.button("Continue to export", key="resume-to-export", disabled=not reviewed):
        _sync_review_confirmation(streamlit_module)
        _request_stage(streamlit_module, ResumeStudioStage.EXPORT)


def _render_export(
    streamlit_module: Any,
    dependencies: ResumeStudioDependencies,
    plan: Any | None,
    profile: MasterProfile | None,
) -> None:
    streamlit_module.subheader("Export")
    resume = streamlit_module.session_state.get("resume")
    reviewed = bool(streamlit_module.session_state.get(_REVIEW_CONFIRMED_KEY))
    if plan is None or profile is None or resume is None or not reviewed:
        streamlit_module.warning(
            "Complete document review before requesting exact page verification and export."
        )
        return
    streamlit_module.caption("Exact one-page verification is required before export.")
    if streamlit_module.button(
        "Verify and prepare export", key="resume-verify-export", type="primary"
    ):
        _clear_resume_export_artifacts(streamlit_module)
        try:
            approved_claims = set(
                streamlit_module.session_state.get("resume_approved_claim_ids", set())
            )
            approved_generated = set(
                streamlit_module.session_state.get("resume_generated_approval_ids", set())
            )
            export_resume = dependencies.tailor_service.build_document(
                plan, profile, approved_claims | approved_generated
            )
            with TemporaryDirectory() as directory:
                rendered = dependencies.resume_renderer.render(export_resume, Path(directory))
                streamlit_module.session_state["resume_export_docx"] = (
                    rendered.docx_path.read_bytes()
                )
                streamlit_module.session_state["resume_export_pdf"] = rendered.pdf_path.read_bytes()
                streamlit_module.session_state["resume_export_status"] = (
                    f"Verified exactly one page via {rendered.measurement_provider}."
                )
        except PageCountVerificationError as error:
            streamlit_module.error(f"Exact page verification is unavailable: {error}")
        except PageOverflowError as error:
            streamlit_module.error(
                f"The résumé cannot be exported until overflow is resolved: {error}"
            )
        except (ValueError, LanguageModelError) as error:
            streamlit_module.error(f"Résumé export failed: {error}")
    status = streamlit_module.session_state.get("resume_export_status")
    if status:
        streamlit_module.success(status)
        streamlit_module.download_button(
            "Download DOCX",
            streamlit_module.session_state["resume_export_docx"],
            "tailored-resume.docx",
            key="resume-download-docx",
        )
        streamlit_module.download_button(
            "Download PDF",
            streamlit_module.session_state["resume_export_pdf"],
            "tailored-resume.pdf",
            key="resume-download-pdf",
        )


def render_resume_studio_page(
    streamlit_module: Any, dependencies: ResumeStudioDependencies
) -> None:
    """Render five stages without taking ownership of planning or rendering policy."""

    profile = streamlit_module.session_state.get("profile")
    reviewed_profile = profile if isinstance(profile, MasterProfile) else None
    _invalidate_if_inputs_changed(streamlit_module, dependencies, reviewed_profile)
    active_stage = _consume_stage_intent(streamlit_module)
    render_page_header(
        streamlit_module,
        "Resume Studio",
        "One evidence-backed strategy, reviewed before document generation and export.",
    )
    selected = streamlit_module.pills(
        "Resume Studio stages",
        STAGE_OPTIONS,
        key=_STAGE_WIDGET_KEY,
    )
    selected_stage = _normalize_stage(selected)
    if selected_stage is not active_stage:
        streamlit_module.session_state[_ACTIVE_STAGE_KEY] = selected_stage.value
        active_stage = selected_stage
    plan = streamlit_module.session_state.get("plan")
    if active_stage is ResumeStudioStage.JOB_CONTEXT:
        _render_job_context(streamlit_module, dependencies, reviewed_profile)
    elif active_stage is ResumeStudioStage.STRATEGY:
        _render_strategy(streamlit_module, plan)
    elif active_stage is ResumeStudioStage.EVIDENCE:
        _render_evidence_selection(streamlit_module, dependencies, reviewed_profile, plan)
    elif active_stage is ResumeStudioStage.REVIEW:
        _render_review(streamlit_module, plan, reviewed_profile)
    else:
        _render_export(streamlit_module, dependencies, plan, reviewed_profile)


__all__ = [
    "ResumeStudioDependencies",
    "ResumeStudioStage",
    "_clear_resume_export_artifacts",
    "render_resume_studio_page",
]
