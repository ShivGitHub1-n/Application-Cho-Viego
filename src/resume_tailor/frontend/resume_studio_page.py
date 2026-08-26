"""Staged Resume Studio presentation backed by the established tailoring service."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from html import escape
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Any

from resume_tailor.application.generated_artifact import (
    content_fingerprint,
    prepare_artifact_download,
)
from resume_tailor.application.job_intake import InvalidJobDescriptionError, build_job_posting
from resume_tailor.application.profile_editor import profile_change_fingerprint
from resume_tailor.application.resume_suggestions import (
    ResumeSuggestionParentError,
    canonical_suggestion_parent,
)
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
from resume_tailor.domain.generated_artifact import GeneratedResumeArtifact, GenerationStage
from resume_tailor.domain.llm_models import LanguageModelError
from resume_tailor.domain.models import EntityKind, JobPosting, MasterProfile, TemplateConstraints
from resume_tailor.domain.resume_composition import (
    STRATEGY_UTILIZATION_ACCEPTABLE_FLOOR,
    TEMPLATE_V1_SEVERE_UNDERFILL_FLOOR,
)
from resume_tailor.frontend.document_canvas import generated_resume_groups, render_document_canvas
from resume_tailor.frontend.resume_editor import (
    active_editor_view,
    approved_editor_revision_fingerprint,
    render_resume_editor,
    set_editor_revision_approved,
)
from resume_tailor.frontend.shared_components import (
    render_empty_state,
    render_page_header,
    render_status_strip,
)
from resume_tailor.infrastructure.rendering import (
    PageCountVerificationError,
    PageOverflowError,
)


class ResumeStudioStage(StrEnum):
    JOB_CONTEXT = "Job context"
    REVIEW = "Resume review"
    EXPORT = "Export"


STAGE_OPTIONS = (
    ResumeStudioStage.JOB_CONTEXT.value,
    ResumeStudioStage.REVIEW.value,
    ResumeStudioStage.EXPORT.value,
)

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
_GENERATION_TIMINGS_KEY = "resume_generation_phase_timings"

_PLAN_PROGRESS = {
    GenerationStage.POSTING_NORMALIZATION: ("Analyzing the role", 8),
    GenerationStage.EVIDENCE_RETRIEVAL: ("Selecting your strongest evidence", 22),
    GenerationStage.DETERMINISTIC_PLANNING: ("Selecting your strongest evidence", 28),
    GenerationStage.SEMANTIC_PLANNING: ("Selecting your strongest evidence", 36),
    GenerationStage.PLAN_VALIDATION: ("Checking the tailoring plan", 43),
}

_BUILD_PROGRESS = {
    GenerationStage.WRITER_SHORTLIST: ("Tailoring bullet wording", 52),
    GenerationStage.WRITER_CACHE_LOOKUP: ("Tailoring bullet wording", 56),
    GenerationStage.PROVIDER_REQUEST: ("Tailoring bullet wording", 62),
    GenerationStage.PROVIDER_RESPONSE_PARSING: ("Tailoring bullet wording", 66),
    GenerationStage.CLAIM_VALIDATION: ("Checking claims", 71),
    GenerationStage.WRITER_VARIANT_SELECTION: ("Checking claims", 75),
    GenerationStage.COMPOSITION_CANDIDATE_CONSTRUCTION: (
        "Fitting the résumé to one page",
        80,
    ),
    GenerationStage.PORTFOLIO_PAGE_FIT_SEARCH: ("Fitting the résumé to one page", 84),
    GenerationStage.DOCX_RENDERING: ("Fitting the résumé to one page", 88),
    GenerationStage.EXACT_WORD_PAGINATION: ("Fitting the résumé to one page", 94),
}


@dataclass(frozen=True)
class ResumeStudioDependencies:
    """Dependencies supplied by the Streamlit application composition root."""

    tailor_service: Any
    resume_renderer: Any
    invalidate_tailoring: Callable[[], None]
    editor_service: Any | None = None


def _strategy_page_use_warning(composition: Any) -> str | None:
    utilization = float(composition.final_utilization_ratio)
    if utilization < TEMPLATE_V1_SEVERE_UNDERFILL_FLOOR:
        return (
            "This verified one-page résumé remains severely underfilled after bounded "
            "strategy-compatible expansion. The artifact is valid as a last resort, but review "
            "the strategy and evidence before export."
        )
    if utilization < STRATEGY_UTILIZATION_ACCEPTABLE_FLOOR:
        return (
            "This verified one-page résumé remains below the acceptable page-use range after "
            "bounded strategy-compatible expansion. Review the strategy and evidence before "
            "export."
        )
    return None


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
    approved_generated = set(
        streamlit_module.session_state.get("resume_generated_approval_ids", set())
    )
    rendered_variants = {
        bullet.writing_variant.variant_id
        for section in (
            artifact.final_resume.experience_bullets,
            artifact.final_resume.project_bullets,
        )
        for bullets in section.values()
        for bullet in bullets
        if bullet.writing_variant is not None
    }
    known_variant_ids = {
        item.variant_id
        for item in (
            artifact.writing_diagnostic.bullet_variants
            if artifact.writing_diagnostic is not None
            else []
        )
    }
    approved_bullet_variants = approved_generated & known_variant_ids
    streamlit_module.session_state["resume_suggestion_outcomes"] = {
        "applied": len(approved_bullet_variants & rendered_variants),
        "not_included": len(approved_bullet_variants - rendered_variants),
    }
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
    if str(value) in {"Strategy", "Evidence selection"}:
        return ResumeStudioStage.JOB_CONTEXT
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
        "resume_suggestion_outcomes",
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


def _posting_matches(left: JobPosting | None, right: JobPosting) -> bool:
    return bool(
        isinstance(left, JobPosting)
        and left.title == right.title
        and left.description == right.description
        and left.company_name == right.company_name
    )


def _timing_summary(timings: list[Any]) -> dict[str, float]:
    return {
        str(timing.stage.value): round(float(timing.elapsed_seconds), 3)
        for timing in timings
        if int(timing.invocation_count) > 0
    }


def _progress_callback(
    status: Any,
    progress: Any,
    mapping: dict[GenerationStage, tuple[str, int]],
) -> Callable[[GenerationStage], None]:
    last_label: list[str] = []

    def show(stage: GenerationStage) -> None:
        item = mapping.get(stage)
        if item is None:
            return
        label, percent = item
        if last_label and last_label[-1] == label:
            return
        progress.progress(percent, text=label)
        status.update(label=label)
        status.write(label)
        last_label.append(label)

    return show


def _render_tailoring_details(streamlit_module: Any, plan: Any) -> None:
    application_strategy = getattr(plan, "application_strategy", None)
    priorities = list(getattr(application_strategy, "role_priorities", ()) or ())
    if not priorities:
        primary_focus = str(getattr(getattr(plan, "strategy", None), "primary_focus", ""))
        priorities = [primary_focus] if primary_focus else []
    if priorities:
        streamlit_module.markdown("**Tailoring priorities**")
        for priority in priorities[:4]:
            text = str(getattr(priority, "theme", priority)).strip()
            if text:
                streamlit_module.markdown(f"- {text}")
    with streamlit_module.expander("Advanced tailoring details", expanded=False):
        strategy = getattr(plan, "strategy", None)
        if strategy is not None:
            streamlit_module.write(strategy.rationale)
        if application_strategy is not None:
            streamlit_module.caption(
                "Semantic strategy was used; evidence, claims, and page fit remain validated."
            )
            streamlit_module.write(application_strategy.application_thesis)
        for decision in getattr(getattr(plan, "report", None), "decisions", ()):
            streamlit_module.write(
                f"{decision.action.replace('_', ' ').title()} — {decision.reason}"
            )


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
    streamlit_module.subheader("Create a tailored résumé")
    if profile is None:
        streamlit_module.info(
            "Choose a reviewed Career Profile before generating a tailored résumé."
        )
        return
    streamlit_module.caption(f"Using {profile.display_name}'s reviewed Career Profile")
    _prepare_job_context_widgets(streamlit_module)
    has_context = bool(str(streamlit_module.session_state.get(_JOB_DESCRIPTION_KEY, "")).strip())
    if has_context:
        with streamlit_module.container(border=True, key="resume-job-summary"):
            streamlit_module.markdown(
                f"### {escape(str(streamlit_module.session_state.get(_JOB_TITLE_KEY, 'Role')))}"
            )
            company_label = str(streamlit_module.session_state.get(_JOB_COMPANY_KEY, "")).strip()
            streamlit_module.caption(company_label or "Company not provided")
        editor = streamlit_module.expander("Review or edit posting", expanded=False)
    else:
        editor = streamlit_module.container()
    with editor:
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
            "Job description",
            key=_JOB_DESCRIPTION_WIDGET_KEY,
            height=180,
            placeholder="Paste the full posting or open a role from Jobs.",
            on_change=_sync_job_context,
            args=(streamlit_module,),
        )
    if streamlit_module.button(
        "Generate tailored résumé",
        key="resume-create-strategy",
        type="primary",
        icon=":material/auto_awesome:",
    ):
        try:
            telemetry = getattr(dependencies.tailor_service, "telemetry", None)
            clock = telemetry.clock if telemetry is not None else perf_counter
            generation_started = clock()
            posting_started = clock()
            _sync_job_context(streamlit_module)
            active_posting = streamlit_module.session_state.get("posting")
            posting = build_job_posting(
                "local-posting",
                title,
                description,
                company_name=company,
            )
            if _posting_matches(active_posting, posting):
                posting = active_posting
            posting_elapsed = clock() - posting_started
            state = streamlit_module.session_state
            profile_fingerprint = _profile_fingerprint(profile)
            posting_fingerprint = content_fingerprint(posting)
            plan = state.get("plan")
            artifact = state.get("generated_resume_artifact")
            unchanged = (
                plan is not None
                and state.get("workflow_profile_fingerprint") == profile_fingerprint
                and state.get("workflow_posting_fingerprint") == posting_fingerprint
            )
            if unchanged and isinstance(artifact, GeneratedResumeArtifact) and _artifact_is_current(
                dependencies,
                artifact,
                plan,
                profile,
                _approved_artifact_ids(streamlit_module),
            ):
                state["resume"] = artifact.final_resume
                state[_GENERATION_TIMINGS_KEY] = {
                    "reused": True,
                    "posting_processing_seconds": round(posting_elapsed, 3),
                    "total_seconds": round(clock() - generation_started, 3),
                }
                streamlit_module.toast("Your current tailored résumé is ready.")
                _request_stage(streamlit_module, ResumeStudioStage.REVIEW)
                return
            if not unchanged:
                _invalidate_resume_presentation_state(streamlit_module, dependencies)
            if hasattr(dependencies.tailor_service, "start_generation"):
                dependencies.tailor_service.start_generation()
            with streamlit_module.status("Analyzing the role", expanded=True) as status:
                progress = streamlit_module.progress(4, text="Analyzing the role")
                plan_snapshot = telemetry.snapshot() if telemetry is not None else None
                if not unchanged:
                    if telemetry is not None:
                        telemetry.set_stage_callback(
                            _progress_callback(status, progress, _PLAN_PROGRESS)
                        )
                    try:
                        plan = dependencies.tailor_service.create_plan(
                            profile, posting, TemplateConstraints()
                        )
                    finally:
                        if telemetry is not None:
                            telemetry.set_stage_callback(None)
                plan_timings = (
                    telemetry.timings_since(plan_snapshot, include_missing=False)
                    if telemetry is not None and plan_snapshot is not None
                    else []
                )
                # Preserve the normalized application context even when document
                # construction fails, so retry does not lose the user's posting.
                state["posting"] = posting
                state["plan"] = plan
                state["workflow_profile_fingerprint"] = profile_fingerprint
                state["workflow_posting_fingerprint"] = posting_fingerprint
                progress.progress(48, text="Tailoring bullet wording")
                build_snapshot = telemetry.snapshot() if telemetry is not None else None
                if telemetry is not None:
                    telemetry.set_stage_callback(
                        _progress_callback(status, progress, _BUILD_PROGRESS)
                    )
                try:
                    approved_ids = _approved_artifact_ids(streamlit_module)
                    if _uses_generated_artifact_workflow(dependencies):
                        _store_generated_artifact(
                            streamlit_module,
                            dependencies,
                            profile,
                            plan,
                            approved_ids,
                        )
                    else:
                        state["resume"] = dependencies.tailor_service.build_document(
                            plan, profile, approved_ids
                        )
                finally:
                    if telemetry is not None:
                        telemetry.set_stage_callback(None)
                progress.progress(100, text="Preparing suggestions")
                status.update(label="Your tailored résumé is ready", state="complete")
            timing_details: dict[str, Any] = {}
            timing_details["posting_processing_seconds"] = round(posting_elapsed, 3)
            if telemetry is not None:
                if plan_snapshot is not None:
                    timing_details["plan"] = _timing_summary(plan_timings)
                if build_snapshot is not None:
                    timing_details["document"] = _timing_summary(
                        telemetry.timings_since(build_snapshot, include_missing=False)
                    )
                timing_details["total_seconds"] = round(
                    telemetry.clock() - generation_started, 3
                )
            else:
                timing_details["total_seconds"] = round(clock() - generation_started, 3)
            state[_GENERATION_TIMINGS_KEY] = timing_details
            state.setdefault("resume_approved_claim_ids", set())
            state.setdefault("resume_evidence_selection_ids", set())
            state[_REVIEW_CONFIRMED_KEY] = False
            state.pop(_REVIEW_WIDGET_KEY, None)
            _request_stage(streamlit_module, ResumeStudioStage.REVIEW)
        except (InvalidJobDescriptionError, ValueError, LanguageModelError) as error:
            streamlit_module.error(
                "We couldn't finish this résumé. Your profile and any previous document "
                "are safe; review the posting and try again."
            )
            with streamlit_module.expander("Advanced diagnostics", expanded=False):
                streamlit_module.code(str(error))


def _suggestion_context(profile: MasterProfile, resume: Any, bullet: Any) -> tuple[str, str, bool]:
    try:
        parent = canonical_suggestion_parent(profile, bullet)
    except ResumeSuggestionParentError:
        return "Resume wording", "", False
    entry = parent.entry
    entry_id = entry.id
    in_resume = entry_id in resume.experience_bullets or entry_id in resume.project_bullets
    kind = "Experience" if entry.kind is EntityKind.EXPERIENCE else "Project"
    return f"{kind} · {entry.title}", entry_id, not in_resume


def _source_copy(profile: MasterProfile, bullet: Any) -> list[str]:
    evidence_ids = set(getattr(bullet, "evidence_ids", ()))
    return [item.source_text for item in profile.evidence if item.id in evidence_ids]


def _render_generated_suggestions(
    streamlit_module: Any,
    profile: MasterProfile,
    resume: Any,
    permanent_ids: set[str],
) -> tuple[set[str], set[str], bool]:
    pending_ids: set[str] = set()
    visible_ids = {
        *[bullet.id for bullet in resume.review_pending_bullets],
        *[skill.id for skill in resume.review_pending_skills],
    }
    if not visible_ids:
        render_empty_state(
            streamlit_module,
            "No suggestions need a decision",
            "The current wording is ready for document review.",
            icon="check",
        )
        return pending_ids, visible_ids, False
    streamlit_module.markdown("### Suggestions")
    streamlit_module.caption(
        "Choose any supported improvements, then apply them together."
    )
    with streamlit_module.form("resume-suggestions-form", border=False):
        for bullet in resume.review_pending_bullets:
            owner, _entry_id, omitted_parent = _suggestion_context(profile, resume, bullet)
            widget_key = _approval_widget_key("generated_bullet", bullet.id)
            _seed_approval_widget(streamlit_module, widget_key, permanent_ids, bullet.id)
            with streamlit_module.container(border=True, key=f"resume-suggestion-{bullet.id}"):
                streamlit_module.markdown(
                    '<div class="pw-suggestion-label">'
                    + escape("Add omitted entry" if omitted_parent else "Suggested rewrite")
                    + "</div>",
                    unsafe_allow_html=True,
                )
                streamlit_module.markdown(f"**{owner}**")
                sources = _source_copy(profile, bullet)
                if sources:
                    streamlit_module.markdown(
                        '<div class="pw-current-copy"><strong>Current evidence</strong><br>'
                        + "<br>".join(escape(item) for item in sources)
                        + "</div>",
                        unsafe_allow_html=True,
                    )
                streamlit_module.markdown(
                    '<div class="pw-suggested-copy"><strong>Suggested wording</strong><br>'
                    + escape(bullet.text)
                    + "</div>",
                    unsafe_allow_html=True,
                )
                if omitted_parent:
                    streamlit_module.caption(
                        "Using this adds the canonical parent entry and its document cost; "
                        "the rebuilt résumé must still pass exact pagination."
                    )
                action_label = (
                    "Add project or experience" if omitted_parent else "Use suggestion"
                )
                if streamlit_module.checkbox(action_label, key=widget_key):
                    pending_ids.add(bullet.id)
        for skill in resume.review_pending_skills:
            widget_key = _approval_widget_key("generated_skill", skill.id)
            _seed_approval_widget(streamlit_module, widget_key, permanent_ids, skill.id)
            with streamlit_module.container(border=True, key=f"resume-suggestion-{skill.id}"):
                streamlit_module.markdown(
                    '<div class="pw-suggestion-label">Suggested skill</div>',
                    unsafe_allow_html=True,
                )
                streamlit_module.write(skill.value)
                if streamlit_module.checkbox("Add to skills", key=widget_key):
                    pending_ids.add(skill.id)
        submitted = streamlit_module.form_submit_button(
            "Apply selected changes",
            type="primary",
            icon=":material/check:",
            key="resume-apply-suggestions",
        )
    return pending_ids, visible_ids, submitted
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
    artifact = streamlit_module.session_state.get("generated_resume_artifact")
    if (
        isinstance(artifact, GeneratedResumeArtifact)
        and dependencies.editor_service is not None
        and isinstance(plan.posting, JobPosting)
    ):
        _render_editor_review(
            streamlit_module,
            dependencies,
            artifact,
            plan,
            profile,
        )
        return
    permanent_ids = set(streamlit_module.session_state.get("resume_generated_approval_ids", set()))
    outcomes = streamlit_module.session_state.get("resume_suggestion_outcomes", {})
    if outcomes.get("not_included"):
        streamlit_module.warning(
            "An approved suggestion could not be included after document selection and exact "
            "page fitting. It was not attached to another experience or project."
        )
    elif outcomes.get("applied"):
        streamlit_module.success("Approved suggestions were applied and page fit was rechecked.")
    control_column, document_column = streamlit_module.columns((1.05, 1.95), gap="large")
    with control_column:
        with streamlit_module.container(key="resume-controls"):
            streamlit_module.markdown("### Review controls")
            streamlit_module.caption("Choose supported improvements and apply them together.")
            pending_ids, visible_ids, suggestions_submitted = _render_generated_suggestions(
                streamlit_module, profile, resume, permanent_ids
            )
    with document_column:
        render_document_canvas(
            streamlit_module,
            title="Document preview",
            sections=generated_resume_groups(resume),
            caption=(
                "Review preview. The rendered DOCX and exact page verification remain "
                "authoritative."
            ),
        )
    if suggestions_submitted:
        previous_generated_ids = set(
            streamlit_module.session_state.get("resume_generated_approval_ids", set())
        )
        previous_review_state = streamlit_module.session_state.get(
            GENERATED_RESUME_REVIEW_STATE_KEY
        )
        _record_generated_approvals(streamlit_module, pending_ids, visible_ids)
        try:
            with streamlit_module.status("Applying your changes", expanded=True) as status:
                status.write("Rebuilding once and rechecking the one-page document")
                if _uses_generated_artifact_workflow(dependencies):
                    _store_generated_artifact(
                        streamlit_module,
                        dependencies,
                        profile,
                        plan,
                        _approved_artifact_ids(streamlit_module),
                    )
                else:
                    streamlit_module.session_state["resume"] = (
                        dependencies.tailor_service.build_document(
                            plan,
                            profile,
                            _approved_artifact_ids(streamlit_module),
                        )
                    )
                status.update(label="Suggestions applied", state="complete")
            streamlit_module.rerun()
        except (PageOverflowError, ValueError, LanguageModelError) as error:
            state = streamlit_module.session_state
            state["resume_generated_approval_ids"] = previous_generated_ids
            state[GENERATED_RESUME_GENERATED_APPROVALS_KEY] = previous_generated_ids
            state[GENERATED_RESUME_WORDING_DIRTY_KEY] = False
            state[GENERATED_RESUME_REBUILD_REQUIRED_KEY] = False
            state[GENERATED_RESUME_REBUILD_IN_PROGRESS_KEY] = False
            if previous_review_state is not None:
                state[GENERATED_RESUME_REVIEW_STATE_KEY] = previous_review_state
            streamlit_module.error(
                "Those changes could not fit safely. Your previous résumé is unchanged."
            )
            with streamlit_module.expander("Advanced diagnostics", expanded=False):
                streamlit_module.code(str(error))
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
            if streamlit_module.button("Restore current document", key="resume-rebuild-document"):
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


def _render_editor_review(
    streamlit_module: Any,
    dependencies: ResumeStudioDependencies,
    artifact: GeneratedResumeArtifact,
    plan: Any,
    profile: MasterProfile,
) -> None:
    if not _artifact_is_current(
        dependencies,
        artifact,
        plan,
        profile,
        _approved_artifact_ids(streamlit_module),
    ):
        streamlit_module.warning(
            "The generated baseline changed. Rebuild it before continuing your edits."
        )
        return
    view = render_resume_editor(
        streamlit_module,
        service=dependencies.editor_service,
        artifact=artifact,
        profile=profile,
        posting=plan.posting,
        clear_export=_clear_resume_export_artifacts,
    )
    if view is None:
        return
    render = view.revision.render
    if render.page_count is not None and render.page_count > 1:
        streamlit_module.warning(
            "This revision exceeds one page. Nothing was removed automatically; revise or undo "
            "the edit before export."
        )
    elif not render.exact_pagination:
        streamlit_module.warning(
            "Exact page verification is unavailable for this revision."
        )
    state = streamlit_module.session_state
    can_review = (
        not view.has_staged_changes
        and render.exact_pagination
        and render.page_count == 1
    )
    if not can_review:
        state[_REVIEW_CONFIRMED_KEY] = False
        state.pop(_REVIEW_WIDGET_KEY, None)
        set_editor_revision_approved(streamlit_module, False)
    if _REVIEW_WIDGET_KEY not in state:
        state[_REVIEW_WIDGET_KEY] = bool(
            state.get(_REVIEW_CONFIRMED_KEY, False)
            and approved_editor_revision_fingerprint(streamlit_module)
            == view.revision.revision_fingerprint
        )
    reviewed = streamlit_module.checkbox(
        "I reviewed this exact résumé revision for export.",
        key=_REVIEW_WIDGET_KEY,
        disabled=not can_review,
        on_change=_sync_review_confirmation,
        args=(streamlit_module,),
    )
    set_editor_revision_approved(streamlit_module, bool(reviewed and can_review))
    if streamlit_module.button(
        "Continue to export",
        key="resume-to-export",
        disabled=not reviewed or not can_review,
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
    streamlit_module.caption("Download the reviewed, one-page résumé for this application.")
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
        editor_view = active_editor_view(streamlit_module)
        if dependencies.editor_service is not None and editor_view is not None:
            _render_editor_export(streamlit_module, dependencies, editor_view)
            return
        hybrid = artifact.writing_diagnostic
        rewritten = hybrid.rewritten_bullet_count if hybrid is not None else 0
        writing_status = (
            f"{rewritten} wording improvement(s)" if rewritten else "Reviewed wording"
        )
        pagination_status = (
            "1 page verified" if artifact.pagination_diagnostic.status == "exact" else "Unverified"
        )
        composition = artifact.composition_diagnostic
        page_use = f"{composition.final_utilization_ratio:.0%}"
        density_status = composition.preferred_density_status.value.replace("_", " ")
        render_status_strip(
            streamlit_module,
            {
                "Writing": writing_status,
                "Validation": "Passed",
                "Pagination": pagination_status,
                "Page use": f"{page_use} · {density_status}",
            },
        )
        if getattr(artifact.final_resume, "application_strategy", None) is not None and (
            page_use_warning := _strategy_page_use_warning(composition)
        ):
            streamlit_module.warning(page_use_warning)
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
                    "Your one-page résumé is ready to download."
                )
            else:
                streamlit_module.session_state["resume_export_status"] = (
                    "We could not verify the final page count here. Open the document in "
                    "Word and confirm it remains one page before using it."
                )
        with streamlit_module.expander("Advanced diagnostics", expanded=False):
            streamlit_module.write(
                {
                    "strategy": (
                        "gemini"
                        if getattr(artifact.final_resume, "application_strategy", None) is not None
                        else "deterministic_fallback"
                    ),
                    "pagination_provider": artifact.pagination_diagnostic.provider,
                    "generation_timings": streamlit_module.session_state.get(
                        _GENERATION_TIMINGS_KEY, {}
                    ),
                }
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


def _render_editor_export(
    streamlit_module: Any,
    dependencies: ResumeStudioDependencies,
    editor_view: Any,
) -> None:
    revision = editor_view.revision
    render = revision.render
    if editor_view.has_staged_changes:
        streamlit_module.warning(
            "Return to résumé review and apply or discard the staged changes before export."
        )
        return
    page_status = (
        "1 page verified"
        if render.exact_pagination and render.page_count == 1
        else f"{render.page_count} pages" if render.page_count else "Unverified"
    )
    render_status_strip(
        streamlit_module,
        {
            "Revision": str(revision.revision_number),
            "Validation": "Passed",
            "Pagination": page_status,
            "Page use": (
                f"{render.utilization_ratio:.0%}"
                if render.utilization_ratio is not None
                else "Unavailable"
            ),
        },
    )
    approved = approved_editor_revision_fingerprint(streamlit_module)
    if approved != revision.revision_fingerprint:
        streamlit_module.warning(
            "Return to résumé review and approve this exact revision before export."
        )
        return
    if not render.exact_pagination or render.page_count != 1:
        streamlit_module.warning(
            "This revision cannot be exported until it is verified as exactly one page."
        )
        return
    if streamlit_module.button(
        "Prepare current revision", key="resume-editor-prepare-export", type="primary"
    ):
        _clear_resume_export_artifacts(streamlit_module)
        download = dependencies.editor_service.prepare_download(
            revision,
            approved_revision_fingerprint=approved,
        )
        streamlit_module.session_state["resume_export_docx"] = download.docx_bytes
        streamlit_module.session_state["resume_export_status"] = (
            "Your reviewed one-page revision is ready to download."
        )
    status = streamlit_module.session_state.get("resume_export_status")
    if status and streamlit_module.session_state.get("resume_export_docx"):
        streamlit_module.success(status)
        streamlit_module.download_button(
            "Download DOCX",
            streamlit_module.session_state["resume_export_docx"],
            "tailored-resume.docx",
            key="resume-editor-download-docx",
            on_click=_mark_resume_downloaded,
            args=(streamlit_module,),
        )


def render_resume_studio_page(
    streamlit_module: Any, dependencies: ResumeStudioDependencies
) -> None:
    """Render a three-step document workflow over the existing tailoring architecture."""

    profile = streamlit_module.session_state.get("profile")
    reviewed_profile = profile if isinstance(profile, MasterProfile) else None
    _invalidate_if_inputs_changed(streamlit_module, dependencies, reviewed_profile)
    active_stage = _consume_stage_intent(streamlit_module)
    render_page_header(
        streamlit_module,
        "Resume Studio",
        "Build a résumé around the experience that matters most for this role. "
        "Your reviewed profile stays the source of truth across applications.",
        eyebrow="Documents",
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
    with streamlit_module.container(key="resume-workspace"):
        if active_stage is ResumeStudioStage.JOB_CONTEXT:
            _render_job_context(streamlit_module, dependencies, reviewed_profile)
        elif active_stage is ResumeStudioStage.REVIEW:
            if plan is not None:
                _render_tailoring_details(streamlit_module, plan)
            _render_review(streamlit_module, dependencies, plan, reviewed_profile)
        else:
            _render_export(streamlit_module, dependencies, plan, reviewed_profile)


__all__ = [
    "ResumeStudioDependencies",
    "ResumeStudioStage",
    "_clear_resume_export_artifacts",
    "render_resume_studio_page",
]
