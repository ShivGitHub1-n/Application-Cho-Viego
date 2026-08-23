"""Staged Resume Studio presentation backed by the established tailoring service."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from resume_tailor.application.generated_artifact import (
    content_fingerprint,
    prepare_artifact_download,
)
from resume_tailor.application.job_intake import InvalidJobDescriptionError, build_job_posting
from resume_tailor.application.profile_editor import profile_change_fingerprint
from resume_tailor.application.workflow_state import (
    GENERATED_RESUME_APPROVED_CLAIMS_KEY,
    GENERATED_RESUME_ARTIFACT_VERSION_KEY,
    GENERATED_RESUME_GENERATED_APPROVALS_KEY,
    GENERATED_RESUME_REBUILD_ERROR_KEY,
    GENERATED_RESUME_REBUILD_IN_PROGRESS_KEY,
    GENERATED_RESUME_REBUILD_REQUIRED_KEY,
    GENERATED_RESUME_REVIEW_STATE_KEY,
    GENERATED_RESUME_WORDING_DIRTY_KEY,
    GeneratedResumeReviewState,
)
from resume_tailor.domain.generated_artifact import GeneratedResumeArtifact
from resume_tailor.domain.llm_models import LanguageModelError
from resume_tailor.domain.models import JobPosting, MasterProfile, TemplateConstraints
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
_JOB_COMPANY_KEY = "job_company_input"
_JOB_COMPANY_WIDGET_KEY = "_resume_studio_job_company_widget"
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


def _uses_generated_artifact_workflow(dependencies: ResumeStudioDependencies) -> bool:
    return hasattr(dependencies.tailor_service, "build_generated_artifact")


def _approved_artifact_ids(streamlit_module: Any) -> set[str]:
    return set(streamlit_module.session_state.get("resume_evidence_selection_ids", set())) | set(
        streamlit_module.session_state.get("resume_generated_approval_ids", set())
    )


def _artifact_is_current(
    dependencies: ResumeStudioDependencies,
    artifact: GeneratedResumeArtifact,
    plan: Any,
    profile: MasterProfile,
    approved_ids: set[str],
) -> bool:
    try:
        expected = dependencies.tailor_service.expected_artifact_fingerprint(
            plan,
            profile,
            approved_ids,
        )
    except (AttributeError, ValueError):
        return False
    return artifact.artifact_fingerprint == expected


def _store_generated_artifact(
    streamlit_module: Any,
    dependencies: ResumeStudioDependencies,
    profile: MasterProfile,
    plan: Any,
    approved_ids: set[str],
) -> GeneratedResumeArtifact:
    existing = streamlit_module.session_state.get("generated_resume_artifact")
    artifact = dependencies.tailor_service.build_generated_artifact(
        plan,
        profile,
        approved_ids,
        existing_artifact=existing if isinstance(existing, GeneratedResumeArtifact) else None,
    )
    if not isinstance(artifact, GeneratedResumeArtifact):
        raise ValueError("Resume generation did not return a typed artifact.")
    streamlit_module.session_state["generated_resume_artifact"] = artifact
    streamlit_module.session_state["resume"] = artifact.final_resume
    streamlit_module.session_state[GENERATED_RESUME_APPROVED_CLAIMS_KEY] = set(approved_ids)
    streamlit_module.session_state[GENERATED_RESUME_GENERATED_APPROVALS_KEY] = set(
        streamlit_module.session_state.get("resume_generated_approval_ids", set())
    )
    if artifact is not existing:
        streamlit_module.session_state[GENERATED_RESUME_ARTIFACT_VERSION_KEY] = (
            int(streamlit_module.session_state.get(GENERATED_RESUME_ARTIFACT_VERSION_KEY, 0)) + 1
        )
    streamlit_module.session_state[GENERATED_RESUME_REVIEW_STATE_KEY] = (
        GeneratedResumeReviewState.REBUILT_AWAITING_REVIEW
        if isinstance(existing, GeneratedResumeArtifact)
        else GeneratedResumeReviewState.GENERATED_AWAITING_REVIEW
    )
    streamlit_module.session_state[GENERATED_RESUME_WORDING_DIRTY_KEY] = False
    streamlit_module.session_state[GENERATED_RESUME_REBUILD_REQUIRED_KEY] = False
    streamlit_module.session_state[GENERATED_RESUME_REBUILD_IN_PROGRESS_KEY] = False
    streamlit_module.session_state.pop(GENERATED_RESUME_REBUILD_ERROR_KEY, None)
    _clear_resume_export_artifacts(streamlit_module)
    return artifact


def _profile_fingerprint(profile: MasterProfile) -> str:
    return profile_change_fingerprint(profile)


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
            "local-posting",
            str(state.get(_JOB_TITLE_KEY, "")),
            description,
            company_name=str(state.get(_JOB_COMPANY_KEY, "")),
        )
        active_posting = state.get("posting")
        if (
            isinstance(active_posting, JobPosting)
            and active_posting.title == posting.title
            and active_posting.description == posting.description
            and active_posting.company_name == posting.company_name
        ):
            posting = active_posting
    except InvalidJobDescriptionError:
        _invalidate_resume_presentation_state(streamlit_module, dependencies)
        state[_PENDING_STAGE_KEY] = ResumeStudioStage.JOB_CONTEXT.value
        return
    if state["workflow_posting_fingerprint"] != content_fingerprint(posting):
        _invalidate_resume_presentation_state(streamlit_module, dependencies)
        state[_PENDING_STAGE_KEY] = ResumeStudioStage.JOB_CONTEXT.value


def _prepare_job_context_widgets(streamlit_module: Any) -> None:
    state = streamlit_module.session_state
    state.setdefault(_JOB_TITLE_KEY, "")
    state.setdefault(_JOB_COMPANY_KEY, "")
    state.setdefault(_JOB_DESCRIPTION_KEY, "")
    if _JOB_TITLE_WIDGET_KEY not in state:
        state[_JOB_TITLE_WIDGET_KEY] = state[_JOB_TITLE_KEY]
    if _JOB_DESCRIPTION_WIDGET_KEY not in state:
        state[_JOB_DESCRIPTION_WIDGET_KEY] = state[_JOB_DESCRIPTION_KEY]
    if _JOB_COMPANY_WIDGET_KEY not in state:
        state[_JOB_COMPANY_WIDGET_KEY] = state[_JOB_COMPANY_KEY]


def _sync_job_context(streamlit_module: Any) -> None:
    state = streamlit_module.session_state
    state[_JOB_TITLE_KEY] = str(state.get(_JOB_TITLE_WIDGET_KEY, ""))
    state[_JOB_COMPANY_KEY] = str(state.get(_JOB_COMPANY_WIDGET_KEY, ""))
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


def _record_generated_approvals(
    streamlit_module: Any,
    approved_ids: set[str],
    visible_ids: set[str],
) -> None:
    state = streamlit_module.session_state
    previous = set(state.get("resume_generated_approval_ids", set()))
    remembered = previous - visible_ids
    remembered.update(approved_ids)
    if previous != remembered:
        state["resume_generated_approval_ids"] = remembered
        if isinstance(state.get("generated_resume_artifact"), GeneratedResumeArtifact):
            state[GENERATED_RESUME_REVIEW_STATE_KEY] = (
                GeneratedResumeReviewState.WORDING_CHANGED_REBUILD_REQUIRED
            )
            state[GENERATED_RESUME_WORDING_DIRTY_KEY] = True
            state[GENERATED_RESUME_REBUILD_REQUIRED_KEY] = True
        state.pop(_REVIEW_CONFIRMED_KEY, None)
        state[_REVIEW_WIDGET_KEY] = False
        _clear_resume_export_artifacts(streamlit_module)


def _sync_review_confirmation(streamlit_module: Any) -> None:
    state = streamlit_module.session_state
    confirmed = bool(state.get(_REVIEW_WIDGET_KEY, False))
    if bool(state.get(_REVIEW_CONFIRMED_KEY, False)) != confirmed:
        state[_REVIEW_CONFIRMED_KEY] = confirmed
        state["generated_content_reviewed"] = confirmed
        review_state = state.get(GENERATED_RESUME_REVIEW_STATE_KEY)
        if confirmed and review_state is GeneratedResumeReviewState.REBUILT_AWAITING_REVIEW:
            state[GENERATED_RESUME_REVIEW_STATE_KEY] = GeneratedResumeReviewState.REBUILT_APPROVED
        elif not confirmed and review_state is GeneratedResumeReviewState.REBUILT_APPROVED:
            state[GENERATED_RESUME_REVIEW_STATE_KEY] = (
                GeneratedResumeReviewState.REBUILT_AWAITING_REVIEW
            )
        _clear_resume_export_artifacts(streamlit_module)


def _mark_resume_downloaded(streamlit_module: Any) -> None:
    if streamlit_module.session_state.get(_REVIEW_CONFIRMED_KEY, False):
        streamlit_module.session_state[GENERATED_RESUME_REVIEW_STATE_KEY] = (
            GeneratedResumeReviewState.DOWNLOADED
        )


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
    company = streamlit_module.text_input(
        "Company",
        key=_JOB_COMPANY_WIDGET_KEY,
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
            active_posting = streamlit_module.session_state.get("posting")
            posting = build_job_posting(
                "local-posting",
                title,
                description,
                company_name=company,
            )
            if (
                isinstance(active_posting, JobPosting)
                and active_posting.title == posting.title
                and active_posting.description == posting.description
                and active_posting.company_name == posting.company_name
            ):
                posting = active_posting
            _invalidate_resume_presentation_state(streamlit_module, dependencies)
            if hasattr(dependencies.tailor_service, "start_generation"):
                dependencies.tailor_service.start_generation()
            plan = dependencies.tailor_service.create_plan(profile, posting, TemplateConstraints())
            state = streamlit_module.session_state
            state["posting"] = posting
            state["plan"] = plan
            state["workflow_profile_fingerprint"] = _profile_fingerprint(profile)
            state["workflow_posting_fingerprint"] = content_fingerprint(posting)
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
    streamlit_module.caption(
        "Strategy: Gemini"
        if getattr(plan, "application_strategy", None) is not None
        else "Strategy: Deterministic fallback"
    )
    application_strategy = getattr(plan, "application_strategy", None)
    if application_strategy is not None:
        streamlit_module.write(application_strategy.application_thesis)
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
    permanent_ids = set(streamlit_module.session_state.get("resume_evidence_selection_ids", set()))
    for claim_id in _pending_claim_ids(plan):
        widget_key = _approval_widget_key("evidence", claim_id)
        _seed_approval_widget(streamlit_module, widget_key, permanent_ids, claim_id)
        if streamlit_module.checkbox(f"Approve inferred wording: {claim_id}", key=widget_key):
            approved_ids.add(claim_id)
    _record_evidence_selection(streamlit_module, approved_ids)
    if streamlit_module.button(
        "Build reviewed resume", key="resume-build-document", type="primary"
    ):
        try:
            _clear_resume_export_artifacts(streamlit_module)
            if _uses_generated_artifact_workflow(dependencies):
                _store_generated_artifact(
                    streamlit_module,
                    dependencies,
                    profile,
                    plan,
                    approved_ids,
                )
            else:
                streamlit_module.session_state["resume"] = (
                    dependencies.tailor_service.build_document(plan, profile, approved_ids)
                )
            streamlit_module.session_state["resume_approved_claim_ids"] = approved_ids
            streamlit_module.session_state[_REVIEW_CONFIRMED_KEY] = False
            streamlit_module.session_state.pop(_REVIEW_WIDGET_KEY, None)
            _request_stage(streamlit_module, ResumeStudioStage.REVIEW)
        except (ValueError, LanguageModelError) as error:
            streamlit_module.error(f"Résumé document could not be built: {error}")


def _render_review(
    streamlit_module: Any,
    dependencies: ResumeStudioDependencies,
    plan: Any | None,
    profile: MasterProfile | None,
) -> None:
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
    visible_ids = {
        *[bullet.id for bullet in resume.review_pending_bullets],
        *[skill.id for skill in resume.review_pending_skills],
    }
    permanent_ids = set(streamlit_module.session_state.get("resume_generated_approval_ids", set()))
    if resume.review_pending_bullets or resume.review_pending_skills:
        streamlit_module.markdown("**Approval-required generated content**")
        for bullet in resume.review_pending_bullets:
            widget_key = _approval_widget_key("generated_bullet", bullet.id)
            _seed_approval_widget(streamlit_module, widget_key, permanent_ids, bullet.id)
            if streamlit_module.checkbox(f"Approve inferred bullet: {bullet.text}", key=widget_key):
                pending_ids.add(bullet.id)
        for skill in resume.review_pending_skills:
            widget_key = _approval_widget_key("generated_skill", skill.id)
            _seed_approval_widget(streamlit_module, widget_key, permanent_ids, skill.id)
            if streamlit_module.checkbox(f"Approve inferred skill: {skill.value}", key=widget_key):
                pending_ids.add(skill.id)
    _record_generated_approvals(streamlit_module, pending_ids, visible_ids)
    artifact = streamlit_module.session_state.get("generated_resume_artifact")
    artifact_current = True
    if isinstance(artifact, GeneratedResumeArtifact):
        artifact_current = _artifact_is_current(
            dependencies,
            artifact,
            plan,
            profile,
            _approved_artifact_ids(streamlit_module),
        )
        if not artifact_current:
            streamlit_module.warning(
                "Approved wording changed. Rebuild the immutable resume artifact "
                "before final review and download."
            )
            if streamlit_module.button(
                "Rebuild with approved wording",
                key="resume-rebuild-document",
                type="primary",
            ):
                try:
                    _store_generated_artifact(
                        streamlit_module,
                        dependencies,
                        profile,
                        plan,
                        _approved_artifact_ids(streamlit_module),
                    )
                    artifact_current = True
                    streamlit_module.success(
                        "Approved wording rebuilt. Review the updated resume before export."
                    )
                    streamlit_module.rerun()
                except (PageOverflowError, ValueError, LanguageModelError) as error:
                    streamlit_module.error(
                        f"Rebuild failed; the previous valid artifact remains available. {error}"
                    )
    state = streamlit_module.session_state
    if _REVIEW_WIDGET_KEY not in state:
        state[_REVIEW_WIDGET_KEY] = bool(state.get(_REVIEW_CONFIRMED_KEY, False))
    reviewed = streamlit_module.checkbox(
        "I reviewed the generated résumé content for export.",
        key=_REVIEW_WIDGET_KEY,
        on_change=_sync_review_confirmation,
        args=(streamlit_module,),
    )
    if streamlit_module.button(
        "Continue to export",
        key="resume-to-export",
        disabled=not reviewed or not artifact_current,
    ):
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
    streamlit_module.caption(
        "Exact Word pagination is authoritative when available. Otherwise the "
        "stored DOCX remains explicitly unverified and requires manual Word inspection."
    )
    artifact = streamlit_module.session_state.get("generated_resume_artifact")
    if isinstance(artifact, GeneratedResumeArtifact):
        if not _artifact_is_current(
            dependencies,
            artifact,
            plan,
            profile,
            _approved_artifact_ids(streamlit_module),
        ):
            streamlit_module.warning(
                "The stored resume artifact is stale. Return to Resume review and rebuild it."
            )
            return
        hybrid = artifact.writing_diagnostic
        strategy_status = (
            "Gemini"
            if getattr(artifact.final_resume, "application_strategy", None) is not None
            else "Deterministic fallback"
        )
        rewritten = hybrid.rewritten_bullet_count if hybrid is not None else 0
        writing_status = (
            f"Gemini · {rewritten} improvement(s) applied" if rewritten else "Source retained"
        )
        pagination_status = (
            "1 page verified" if artifact.pagination_diagnostic.status == "exact" else "Unverified"
        )
        streamlit_module.caption(
            f"Strategy: {strategy_status} · Writing: {writing_status} · "
            f"Validation: Passed · Pagination: {pagination_status}"
        )
        if streamlit_module.button(
            "Verify and prepare export", key="resume-verify-export", type="primary"
        ):
            _clear_resume_export_artifacts(streamlit_module)
            download = prepare_artifact_download(
                artifact,
                clock=dependencies.tailor_service.telemetry.clock,
            )
            streamlit_module.session_state["resume_export_docx"] = download.docx_bytes
            if artifact.pagination_diagnostic.status == "exact":
                streamlit_module.session_state["resume_export_status"] = (
                    "Exact one-page pagination was verified by "
                    f"{artifact.pagination_diagnostic.provider}."
                )
            else:
                streamlit_module.session_state["resume_export_status"] = (
                    "Pagination is unverified in this environment; the stored DOCX "
                    "is ready for required manual Microsoft Word inspection."
                )
        status = streamlit_module.session_state.get("resume_export_status")
        if status:
            if artifact.pagination_diagnostic.status == "exact":
                streamlit_module.success(status)
            else:
                streamlit_module.warning(status)
            streamlit_module.download_button(
                "Download DOCX",
                streamlit_module.session_state["resume_export_docx"],
                "tailored-resume.docx",
                key="resume-download-docx",
                on_click=_mark_resume_downloaded,
                args=(streamlit_module,),
            )
        return
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
        _render_review(streamlit_module, dependencies, plan, reviewed_profile)
    else:
        _render_export(streamlit_module, dependencies, plan, reviewed_profile)


__all__ = [
    "ResumeStudioDependencies",
    "ResumeStudioStage",
    "_clear_resume_export_artifacts",
    "render_resume_studio_page",
]
