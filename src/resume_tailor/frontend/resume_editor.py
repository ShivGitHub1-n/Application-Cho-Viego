from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any

from resume_tailor.application.generated_artifact import content_fingerprint
from resume_tailor.application.resume_editor import (
    ResumeEditorError,
    ResumeEditorService,
    omitted_reviewed_entries,
    resume_editor_application_fingerprint,
)
from resume_tailor.application.resume_suggestions import (
    ResumeSuggestionParentError,
    canonical_suggestion_parent,
)
from resume_tailor.application.workflow_state import (
    GENERATED_RESUME_REVIEW_STATE_KEY,
    GeneratedResumeReviewState,
)
from resume_tailor.domain.generated_artifact import GeneratedResumeArtifact
from resume_tailor.domain.models import EntityKind, JobPosting, MasterProfile, StructuredResume
from resume_tailor.domain.resume_editor import (
    ResumeEditorFitStatus,
    ResumeEditorRevision,
)

_WORKSPACES_KEY = "resume_editor_workspaces"
_ACTIVE_CONTEXT_KEY = "resume_editor_active_context"
_EDITING_BULLET_KEY = "resume_editor_editing_bullet"
_EDITOR_SECTIONS = ("education", "skills", "experience", "projects", "suggestions")


@dataclass(frozen=True)
class ResumeEditorView:
    context_fingerprint: str
    revision: ResumeEditorRevision
    has_staged_changes: bool


@dataclass(frozen=True)
class ResumeSuggestionPresentation:
    mode: str
    current_bullet: str | None
    reviewed_fact_count: int


def active_editor_view(streamlit_module: Any) -> ResumeEditorView | None:
    context = streamlit_module.session_state.get(_ACTIVE_CONTEXT_KEY)
    workspaces = streamlit_module.session_state.get(_WORKSPACES_KEY, {})
    workspace = workspaces.get(context) if isinstance(workspaces, dict) else None
    if not isinstance(workspace, dict):
        return None
    revision = workspace.get("applied_revision")
    staged = workspace.get("staged_resume")
    if not isinstance(revision, ResumeEditorRevision) or not isinstance(
        staged, StructuredResume
    ):
        return None
    return ResumeEditorView(
        context_fingerprint=str(context),
        revision=revision,
        has_staged_changes=content_fingerprint(staged) != content_fingerprint(revision.resume),
    )


def approved_editor_revision_fingerprint(streamlit_module: Any) -> str | None:
    workspace = _active_workspace(streamlit_module)
    return (
        str(workspace.get("approved_revision_fingerprint"))
        if workspace and workspace.get("approved_revision_fingerprint")
        else None
    )


def set_editor_revision_approved(streamlit_module: Any, approved: bool) -> None:
    workspace = _active_workspace(streamlit_module)
    if workspace is None:
        return
    revision = workspace.get("applied_revision")
    workspace["approved_revision_fingerprint"] = (
        revision.revision_fingerprint
        if approved and isinstance(revision, ResumeEditorRevision)
        else None
    )


def render_resume_editor(
    streamlit_module: Any,
    *,
    service: ResumeEditorService,
    artifact: GeneratedResumeArtifact,
    profile: MasterProfile,
    posting: JobPosting,
    clear_export: Any,
) -> ResumeEditorView | None:
    context = resume_editor_application_fingerprint(
        profile,
        posting,
        artifact.artifact_fingerprint,
    )
    streamlit_module.session_state[_ACTIVE_CONTEXT_KEY] = context
    workspaces = streamlit_module.session_state.setdefault(_WORKSPACES_KEY, {})
    workspace = workspaces.get(context)
    if not isinstance(workspace, dict):
        try:
            with streamlit_module.status("Preparing the document preview", expanded=True) as status:
                status.write("Rendering the generated résumé through its Word template")
                revision = service.create_revision(
                    artifact.final_resume,
                    profile,
                    application_fingerprint=context,
                    baseline_artifact_fingerprint=artifact.artifact_fingerprint,
                    revision_number=0,
                    source_docx_bytes=artifact.docx_bytes,
                )
                status.update(label="Document preview ready", state="complete")
        except ResumeEditorError as error:
            streamlit_module.error("The résumé editor could not open this document.")
            with streamlit_module.expander("Advanced diagnostics", expanded=False):
                streamlit_module.code(str(error))
            return None
        workspace = {
            "baseline_resume": artifact.final_resume.model_copy(deep=True),
            "staged_resume": revision.resume.model_copy(deep=True),
            "applied_revision": revision,
            "previous_revision": None,
            "approved_revision_fingerprint": None,
        }
        workspaces[context] = workspace
    staged = workspace.get("staged_resume")
    revision = workspace.get("applied_revision")
    if not isinstance(staged, StructuredResume) or not isinstance(
        revision, ResumeEditorRevision
    ):
        streamlit_module.error("The résumé editor state is unavailable for this application.")
        return None
    streamlit_module.session_state["resume"] = revision.resume

    dirty = content_fingerprint(staged) != content_fingerprint(revision.resume)
    _render_editor_toolbar(
        streamlit_module,
        service,
        workspace,
        profile,
        context,
        artifact,
        clear_export,
        dirty,
    )
    control_column, preview_column = streamlit_module.columns((1.05, 1.6), gap="large")
    with control_column:
        _render_structured_controls(
            streamlit_module,
            service,
            workspace,
            profile,
            context=context,
        )
    with preview_column:
        _render_preview(streamlit_module, revision)
    revision = workspace["applied_revision"]
    staged = workspace["staged_resume"]
    return ResumeEditorView(
        context_fingerprint=context,
        revision=revision,
        has_staged_changes=content_fingerprint(staged) != content_fingerprint(revision.resume),
    )


def _render_editor_toolbar(
    streamlit_module: Any,
    service: ResumeEditorService,
    workspace: dict[str, Any],
    profile: MasterProfile,
    context: str,
    artifact: GeneratedResumeArtifact,
    clear_export: Any,
    dirty: bool,
) -> None:
    revision = workspace["applied_revision"]
    with streamlit_module.container(
        horizontal=True,
        horizontal_alignment="distribute",
        vertical_alignment="center",
    ):
        with streamlit_module.container(gap=None):
            streamlit_module.markdown("### Edit your résumé")
            streamlit_module.caption(
                "Stage several changes, then update the document once."
            )
        with streamlit_module.container(horizontal=True, vertical_alignment="center"):
            if streamlit_module.button(
                "Discard staged",
                icon=":material/close:",
                disabled=not dirty,
                key="resume-editor-discard-staged",
            ):
                workspace["staged_resume"] = revision.resume.model_copy(deep=True)
                streamlit_module.session_state.pop(_EDITING_BULLET_KEY, None)
                streamlit_module.rerun()
            if streamlit_module.button(
                "Undo last apply",
                icon=":material/undo:",
                disabled=not isinstance(workspace.get("previous_revision"), ResumeEditorRevision),
                key="resume-editor-undo",
            ):
                previous = workspace.get("previous_revision")
                workspace["previous_revision"] = revision
                workspace["applied_revision"] = previous
                workspace["staged_resume"] = previous.resume.model_copy(deep=True)
                streamlit_module.session_state["resume"] = previous.resume
                workspace["approved_revision_fingerprint"] = None
                streamlit_module.session_state["resume_studio_review_confirmed"] = False
                streamlit_module.session_state.pop(
                    "_resume_studio_review_confirmed_widget", None
                )
                streamlit_module.session_state[GENERATED_RESUME_REVIEW_STATE_KEY] = (
                    GeneratedResumeReviewState.REBUILT_AWAITING_REVIEW
                )
                clear_export(streamlit_module)
                streamlit_module.rerun()
            if streamlit_module.button(
                "Reset to generated",
                icon=":material/restart_alt:",
                key="resume-editor-reset",
            ):
                workspace["staged_resume"] = workspace["baseline_resume"].model_copy(deep=True)
                _invalidate_editor_approval(workspace, clear_export, streamlit_module)
                streamlit_module.rerun()
            if streamlit_module.button(
                "Apply changes",
                type="primary",
                icon=":material/refresh:",
                disabled=not dirty,
                key="resume-editor-apply",
            ):
                _apply_staged_revision(
                    streamlit_module,
                    service,
                    workspace,
                    profile,
                    context,
                    artifact,
                    clear_export,
                )


def _apply_staged_revision(
    streamlit_module: Any,
    service: ResumeEditorService,
    workspace: dict[str, Any],
    profile: MasterProfile,
    context: str,
    artifact: GeneratedResumeArtifact,
    clear_export: Any,
) -> None:
    prior = workspace["applied_revision"]
    staged = workspace["staged_resume"]
    try:
        with streamlit_module.status("Updating preview", expanded=True) as status:
            status.write("Rebuilding the document once")
            candidate = service.create_revision(
                staged,
                profile,
                application_fingerprint=context,
                baseline_artifact_fingerprint=artifact.artifact_fingerprint,
                revision_number=prior.revision_number + 1,
            )
            if streamlit_module.session_state.get(_ACTIVE_CONTEXT_KEY) != context:
                return
            status.write("Checking the exact page count")
            workspace["previous_revision"] = prior
            workspace["applied_revision"] = candidate
            workspace["staged_resume"] = candidate.resume.model_copy(deep=True)
            streamlit_module.session_state["resume"] = candidate.resume
            workspace["approved_revision_fingerprint"] = None
            streamlit_module.session_state["resume_studio_review_confirmed"] = False
            streamlit_module.session_state.pop(
                "_resume_studio_review_confirmed_widget", None
            )
            streamlit_module.session_state[GENERATED_RESUME_REVIEW_STATE_KEY] = (
                GeneratedResumeReviewState.REBUILT_AWAITING_REVIEW
            )
            clear_export(streamlit_module)
            status.update(label="Preview updated", state="complete")
        streamlit_module.rerun()
    except ResumeEditorError as error:
        streamlit_module.error(str(error))


def _render_structured_controls(
    streamlit_module: Any,
    service: ResumeEditorService,
    workspace: dict[str, Any],
    profile: MasterProfile,
    *,
    context: str,
) -> None:
    staged = workspace["staged_resume"]
    section_labels = {
        "education": f"Education · {len(staged.education)}",
        "skills": f"Technical skills · {_visible_skill_count(staged)} visible",
        "experience": f"Experience · {len(staged.experiences)} entries",
        "projects": f"Projects · {len(staged.projects)} entries",
        "suggestions": f"Suggestions · {len(staged.review_pending_bullets)} available",
    }
    section = streamlit_module.segmented_control(
        "Editor section",
        options=_EDITOR_SECTIONS,
        default=None,
        format_func=lambda value: section_labels[value],
        key=f"resume-editor-section-{context[:12]}",
        width="stretch",
    )
    if section is None:
        streamlit_module.caption("Choose one section to edit. Your document stays in view.")
    elif section == "education":
        streamlit_module.markdown("#### Education")
        if not staged.education:
            streamlit_module.caption("No education records are visible in this résumé.")
        for record in staged.education:
            with streamlit_module.container(border=True, gap=None):
                streamlit_module.markdown(f"**{record.school}**")
                streamlit_module.caption(record.program)
    elif section == "skills":
        _render_skill_editor(streamlit_module, service, workspace, profile)
    elif section == "experience":
        _render_entry_section(
            streamlit_module,
            service,
            workspace,
            profile,
            title="Experience",
            kind=EntityKind.EXPERIENCE,
            records=staged.experiences,
            bullets=staged.experience_bullets,
            context=context,
        )
    elif section == "projects":
        _render_entry_section(
            streamlit_module,
            service,
            workspace,
            profile,
            title="Projects",
            kind=EntityKind.PROJECT,
            records=staged.projects,
            bullets=staged.project_bullets,
            context=context,
        )
    elif section == "suggestions":
        _render_editor_suggestions(
            streamlit_module,
            service,
            workspace,
            profile,
            context=context,
        )


def _render_skill_editor(
    streamlit_module: Any,
    service: ResumeEditorService,
    workspace: dict[str, Any],
    profile: MasterProfile,
) -> None:
    staged = workspace["staged_resume"]
    streamlit_module.markdown("#### Technical skills")
    options = list(
        dict.fromkeys(
            [
                value
                for category in profile.technical_skills
                for value in _skill_category_values(category)
            ]
            + list(profile.declared_skills)
        )
    )
    selected = [
        value
        for category in staged.technical_skills
        for value in _skill_category_values(category)
    ]
    with streamlit_module.form("resume-editor-skills", border=True):
        chosen = streamlit_module.multiselect(
            "Visible reviewed skills",
            options=options,
            default=[item for item in selected if item in options],
            key="resume-editor-visible-skills",
            help="Only skills from your reviewed Career Profile are available.",
        )
        submitted = streamlit_module.form_submit_button(
            "Stage skill changes",
            icon=":material/check:",
        )
    if submitted:
        try:
            workspace["staged_resume"] = service.set_reviewed_skills(
                staged, profile, list(chosen)
            )
            _mark_staged(workspace, streamlit_module)
            streamlit_module.rerun()
        except ResumeEditorError as error:
            streamlit_module.error(str(error))


def _render_entry_section(
    streamlit_module: Any,
    service: ResumeEditorService,
    workspace: dict[str, Any],
    profile: MasterProfile,
    *,
    title: str,
    kind: EntityKind,
    records: list[Any],
    bullets: dict[str, list[Any]],
    context: str,
) -> None:
    streamlit_module.markdown(f"#### {title}")
    omitted = omitted_reviewed_entries(profile, workspace["staged_resume"], kind)
    with streamlit_module.container(horizontal=True, vertical_alignment="center"):
        streamlit_module.caption(
            "Open one entry at a time. Changes remain staged until you update the preview."
        )
        if streamlit_module.button(
            f"Add {_entry_kind_label(kind)}",
            icon=":material/add:",
            disabled=not omitted,
            key=f"resume-editor-add-{kind.value}-{context[:12]}",
        ):
            workspace["adding_entry_kind"] = (
                None if workspace.get("adding_entry_kind") == kind.value else kind.value
            )
            streamlit_module.rerun()
    if workspace.get("adding_entry_kind") == kind.value:
        _render_add_reviewed_entry(
            streamlit_module,
            service,
            workspace,
            profile,
            kind=kind,
            omitted=omitted,
            context=context,
        )
    if not records:
        streamlit_module.caption(f"No {title.casefold()} entries are currently visible.")
        return
    by_id = {entry.id: entry for entry in records}
    selected_id = streamlit_module.selectbox(
        f"Choose {_entry_kind_label(kind)}",
        options=list(by_id),
        format_func=lambda value: by_id[value].title,
        key=f"resume-editor-entry-choice-{kind.value}-{context[:12]}",
    )
    entry = by_id[selected_id]
    entry_index = next(index for index, item in enumerate(records) if item.id == entry.id)
    with streamlit_module.container(border=True, key=f"resume-editor-entry-{entry.id}"):
        with streamlit_module.container(
            horizontal=True,
            horizontal_alignment="distribute",
            vertical_alignment="center",
        ):
            with streamlit_module.container(gap=None):
                streamlit_module.markdown(f"**{entry.title}**")
                if metadata := _entry_metadata(entry):
                    streamlit_module.caption(metadata)
            with streamlit_module.container(horizontal=True):
                if streamlit_module.button(
                    ":material/arrow_upward:",
                    help="Move entry up",
                    disabled=entry_index == 0,
                    key=f"resume-editor-entry-up-{entry.id}",
                ):
                    workspace["staged_resume"] = service.move_entry(
                        workspace["staged_resume"], entry_id=entry.id, offset=-1
                    )
                    _mark_staged(workspace, streamlit_module)
                    streamlit_module.rerun()
                if streamlit_module.button(
                    ":material/arrow_downward:",
                    help="Move entry down",
                    disabled=entry_index == len(records) - 1,
                    key=f"resume-editor-entry-down-{entry.id}",
                ):
                    workspace["staged_resume"] = service.move_entry(
                        workspace["staged_resume"], entry_id=entry.id, offset=1
                    )
                    _mark_staged(workspace, streamlit_module)
                    streamlit_module.rerun()
                if streamlit_module.button(
                    ":material/delete:",
                    help="Remove entry",
                    key=f"resume-editor-entry-remove-{entry.id}",
                ):
                    workspace["staged_resume"] = service.remove_entry(
                        workspace["staged_resume"], entry_id=entry.id
                    )
                    _mark_staged(workspace, streamlit_module)
                    streamlit_module.rerun()
        for bullet_index, bullet in enumerate(bullets.get(entry.id, [])):
            _render_bullet_row(
                streamlit_module,
                service,
                workspace,
                profile,
                entry.id,
                bullet,
                bullet_index,
                len(bullets.get(entry.id, [])),
            )


def _render_add_reviewed_entry(
    streamlit_module: Any,
    service: ResumeEditorService,
    workspace: dict[str, Any],
    profile: MasterProfile,
    *,
    kind: EntityKind,
    omitted: list[Any],
    context: str,
) -> None:
    if not omitted:
        streamlit_module.info("Every reviewed entry in this section is already visible.")
        return
    by_id = {entry.id: entry for entry in omitted}
    selected_id = streamlit_module.selectbox(
        f"Reviewed {_entry_kind_label(kind)}",
        options=list(by_id),
        format_func=lambda value: by_id[value].title,
        key=f"resume-editor-omitted-choice-{kind.value}-{context[:12]}",
    )
    entry = by_id[selected_id]
    if metadata := _entry_metadata(entry):
        streamlit_module.caption(metadata)
    evidence = [
        item for item in profile.evidence if item.confirmed and item.entity_id == entry.id
    ]
    evidence_by_id = {item.id: item for item in evidence}
    selected_evidence = streamlit_module.multiselect(
        "Reviewed bullets to add",
        options=list(evidence_by_id),
        format_func=lambda value: evidence_by_id[value].source_text,
        key=f"resume-editor-omitted-evidence-{kind.value}-{entry.id}-{context[:12]}",
        help="Only confirmed evidence owned by this Career Profile entry is available.",
    )
    with streamlit_module.container(horizontal=True):
        if streamlit_module.button(
            f"Stage {_entry_kind_label(kind)}",
            type="primary",
            icon=":material/add:",
            disabled=not selected_evidence,
            key=f"resume-editor-stage-entry-{kind.value}-{entry.id}",
        ):
            try:
                workspace["staged_resume"] = service.add_reviewed_entry(
                    workspace["staged_resume"],
                    profile,
                    entry_id=entry.id,
                    evidence_ids=list(selected_evidence),
                    expected_kind=kind,
                )
                workspace["adding_entry_kind"] = None
                _mark_staged(workspace, streamlit_module)
                streamlit_module.rerun()
            except ResumeEditorError as error:
                streamlit_module.error(str(error))
        if streamlit_module.button(
            "Cancel",
            icon=":material/close:",
            key=f"resume-editor-cancel-entry-{kind.value}-{context[:12]}",
        ):
            workspace["adding_entry_kind"] = None
            streamlit_module.rerun()


def _render_bullet_row(
    streamlit_module: Any,
    service: ResumeEditorService,
    workspace: dict[str, Any],
    profile: MasterProfile,
    entry_id: str,
    bullet: Any,
    index: int,
    count: int,
) -> None:
    editing = streamlit_module.session_state.get(_EDITING_BULLET_KEY)
    identity = (entry_id, bullet.id)
    if editing == identity:
        with streamlit_module.form(
            f"resume-editor-bullet-form-{entry_id}-{bullet.id}", border=False
        ):
            text = streamlit_module.text_area(
                "Bullet wording",
                value=bullet.text,
                key=f"resume-editor-bullet-text-{entry_id}-{bullet.id}",
            )
            with streamlit_module.container(horizontal=True):
                apply_edit = streamlit_module.form_submit_button(
                    "Stage edit", type="primary", icon=":material/check:"
                )
                cancel_edit = streamlit_module.form_submit_button(
                    "Cancel", icon=":material/close:"
                )
        if apply_edit:
            try:
                workspace["staged_resume"] = service.edit_bullet(
                    workspace["staged_resume"],
                    profile,
                    entry_id=entry_id,
                    bullet_id=bullet.id,
                    text=text,
                )
                _mark_staged(workspace, streamlit_module)
                streamlit_module.session_state.pop(_EDITING_BULLET_KEY, None)
                streamlit_module.rerun()
            except ResumeEditorError as error:
                streamlit_module.error(str(error))
        elif cancel_edit:
            streamlit_module.session_state.pop(_EDITING_BULLET_KEY, None)
            streamlit_module.rerun()
        return
    text_column, action_column = streamlit_module.columns((5, 1.6), gap="small")
    with text_column:
        streamlit_module.write(bullet.text)
    with action_column:
        with streamlit_module.container(horizontal=True, gap=None):
            if streamlit_module.button(
                ":material/edit:",
                help="Edit bullet",
                key=f"resume-editor-bullet-edit-{entry_id}-{bullet.id}",
            ):
                streamlit_module.session_state[_EDITING_BULLET_KEY] = identity
                streamlit_module.rerun()
            if streamlit_module.button(
                ":material/arrow_upward:",
                help="Move bullet up",
                disabled=index == 0,
                key=f"resume-editor-bullet-up-{entry_id}-{bullet.id}",
            ):
                workspace["staged_resume"] = service.move_bullet(
                    workspace["staged_resume"],
                    entry_id=entry_id,
                    bullet_id=bullet.id,
                    offset=-1,
                )
                _mark_staged(workspace, streamlit_module)
                streamlit_module.rerun()
            if streamlit_module.button(
                ":material/arrow_downward:",
                help="Move bullet down",
                disabled=index == count - 1,
                key=f"resume-editor-bullet-down-{entry_id}-{bullet.id}",
            ):
                workspace["staged_resume"] = service.move_bullet(
                    workspace["staged_resume"],
                    entry_id=entry_id,
                    bullet_id=bullet.id,
                    offset=1,
                )
                _mark_staged(workspace, streamlit_module)
                streamlit_module.rerun()
            if streamlit_module.button(
                ":material/delete:",
                help="Remove bullet",
                key=f"resume-editor-bullet-remove-{entry_id}-{bullet.id}",
            ):
                workspace["staged_resume"] = service.remove_bullet(
                    workspace["staged_resume"], entry_id=entry_id, bullet_id=bullet.id
                )
                _mark_staged(workspace, streamlit_module)
                streamlit_module.rerun()


def _render_editor_suggestions(
    streamlit_module: Any,
    service: ResumeEditorService,
    workspace: dict[str, Any],
    profile: MasterProfile,
    *,
    context: str,
) -> None:
    staged = workspace["staged_resume"]
    if not staged.review_pending_bullets:
        return
    streamlit_module.markdown("#### Suggestions")
    streamlit_module.caption("Stage supported wording changes, then update the preview once.")
    evidence = {item.id: item for item in profile.evidence if item.confirmed}
    candidates: dict[str, tuple[Any, Any]] = {}
    for suggestion in staged.review_pending_bullets:
        try:
            parent = canonical_suggestion_parent(profile, suggestion)
        except ResumeSuggestionParentError:
            continue
        candidates[suggestion.id] = (suggestion, parent)
    if not candidates:
        streamlit_module.caption("No valid suggestions are available for this revision.")
        return
    selected_id = streamlit_module.selectbox(
        "Choose suggestion",
        options=list(candidates),
        format_func=lambda value: candidates[value][1].entry.title,
        key=f"resume-editor-suggestion-choice-{context[:12]}",
    )
    suggestion, parent = candidates[selected_id]
    current = [
        *staged.experience_bullets.get(parent.entry.id, []),
        *staged.project_bullets.get(parent.entry.id, []),
    ]
    source_ids = set(suggestion.evidence_ids)
    presentation = suggestion_presentation(staged, suggestion, parent.entry.id)
    with streamlit_module.container(
        border=True, key=f"resume-editor-suggestion-{suggestion.id}"
    ):
        streamlit_module.caption(
            f"{'Experience' if parent.entry.kind is EntityKind.EXPERIENCE else 'Project'}"
        )
        streamlit_module.markdown(f"**{parent.entry.title}**")
        if presentation.mode == "replacement":
            streamlit_module.markdown(
                '<div class="pw-current-copy"><strong>Current bullet</strong><br>'
                + escape(presentation.current_bullet or "")
                + "</div>",
                unsafe_allow_html=True,
            )
        else:
            streamlit_module.caption(f"Based on {len(source_ids)} reviewed fact(s)")
        streamlit_module.markdown(
            '<div class="pw-suggested-copy"><strong>Suggested bullet</strong><br>'
            + escape(suggestion.text)
            + "</div>",
            unsafe_allow_html=True,
        )
        if presentation.mode != "replacement":
            with streamlit_module.expander("Reviewed facts", expanded=False):
                for evidence_id in suggestion.evidence_ids:
                    item = evidence.get(evidence_id)
                    if item is not None:
                        streamlit_module.write(item.source_text)
        omitted = not current
        label = "Add entry and suggestion" if omitted else "Stage suggestion"
        if streamlit_module.button(
            label,
            icon=":material/add:" if omitted else ":material/check:",
            key=f"resume-editor-use-suggestion-{suggestion.id}",
        ):
            try:
                workspace["staged_resume"] = service.apply_suggestion(
                    staged, profile, suggestion
                )
                _mark_staged(workspace, streamlit_module)
                streamlit_module.rerun()
            except ResumeEditorError as error:
                streamlit_module.error(str(error))


def _render_preview(streamlit_module: Any, revision: ResumeEditorRevision) -> None:
    render = revision.render
    with streamlit_module.container(border=True, key="resume-editor-preview"):
        with streamlit_module.container(
            horizontal=True,
            horizontal_alignment="distribute",
            vertical_alignment="center",
        ):
            with streamlit_module.container(gap=None):
                streamlit_module.markdown("### Document preview")
                streamlit_module.caption(f"Revision {revision.revision_number}")
            if render.status is ResumeEditorFitStatus.FITS_ONE_PAGE:
                streamlit_module.badge(
                    "Fits one page", icon=":material/check_circle:", color="green"
                )
            elif render.page_count and render.page_count > 1:
                streamlit_module.badge(
                    "Exceeds one page", icon=":material/warning:", color="red"
                )
            else:
                streamlit_module.badge(
                    "Preview unavailable", icon=":material/error:", color="orange"
                )
        if render.preview_page_pngs:
            for page_number, page_png in enumerate(render.preview_page_pngs, start=1):
                streamlit_module.image(
                    page_png,
                    caption=f"Page {page_number} of {len(render.preview_page_pngs)}",
                    width="stretch",
                )
        elif render.pdf_bytes:
            streamlit_module.info(
                "The exact PDF is ready, but inline page images could not be created. "
                "Use the PDF preview download below.",
                icon=":material/picture_as_pdf:",
            )
        else:
            streamlit_module.info(
                "The DOCX is preserved, but this environment could not create the visual "
                "preview.",
                icon=":material/description:",
            )
        if pdf_bytes := exact_preview_pdf_bytes(revision):
            streamlit_module.download_button(
                "Download PDF preview",
                data=pdf_bytes,
                file_name=f"resume-preview-revision-{revision.revision_number}.pdf",
                mime="application/pdf",
                icon=":material/open_in_new:",
                on_click="ignore",
                key=f"resume-editor-preview-pdf-{revision.revision_fingerprint[:12]}",
            )
        with streamlit_module.expander("Preview details", expanded=False):
            streamlit_module.write(
                {
                    "page_count": render.page_count,
                    "exact_pagination": render.exact_pagination,
                    "page_use": (
                        f"{render.utilization_ratio:.0%}"
                        if render.utilization_ratio is not None
                        else "Unavailable"
                    ),
                    "provider": render.pagination_provider,
                    "failure": render.failure_reason,
                }
            )


def exact_preview_pdf_bytes(revision: ResumeEditorRevision) -> bytes | None:
    """Return the exact current PDF bytes used to derive the inline preview pages."""

    return revision.render.pdf_bytes


def suggestion_presentation(
    resume: StructuredResume,
    suggestion: Any,
    entry_id: str,
) -> ResumeSuggestionPresentation:
    current = [
        *resume.experience_bullets.get(entry_id, []),
        *resume.project_bullets.get(entry_id, []),
    ]
    source_ids = set(suggestion.evidence_ids)
    related = [item for item in current if set(item.evidence_ids) & source_ids]
    return ResumeSuggestionPresentation(
        mode="replacement" if len(related) == 1 else "evidence_synthesis",
        current_bullet=related[0].text if len(related) == 1 else None,
        reviewed_fact_count=len(source_ids),
    )
def _active_workspace(streamlit_module: Any) -> dict[str, Any] | None:
    context = streamlit_module.session_state.get(_ACTIVE_CONTEXT_KEY)
    workspaces = streamlit_module.session_state.get(_WORKSPACES_KEY, {})
    if not isinstance(workspaces, dict):
        return None
    workspace = workspaces.get(context)
    return workspace if isinstance(workspace, dict) else None


def _skill_category_values(category: Any) -> list[str]:
    return [skill.value for skill in category.skills] if category.skills else list(category.values)


def _visible_skill_count(resume: StructuredResume) -> int:
    return sum(len(_skill_category_values(category)) for category in resume.technical_skills)


def _entry_kind_label(kind: EntityKind) -> str:
    return "experience" if kind is EntityKind.EXPERIENCE else "project"


def _entry_metadata(entry: Any) -> str:
    dates = " – ".join(value for value in (entry.start_date, entry.end_date) if value)
    return " · ".join(
        value for value in (entry.organization, entry.location, dates) if value
    )


def _mark_staged(workspace: dict[str, Any], streamlit_module: Any) -> None:
    workspace["approved_revision_fingerprint"] = None
    streamlit_module.session_state["resume_studio_review_confirmed"] = False
    streamlit_module.session_state.pop("_resume_studio_review_confirmed_widget", None)
    streamlit_module.session_state[GENERATED_RESUME_REVIEW_STATE_KEY] = (
        GeneratedResumeReviewState.GENERATED_AWAITING_REVIEW
    )


def _invalidate_editor_approval(
    workspace: dict[str, Any],
    clear_export: Any,
    streamlit_module: Any,
) -> None:
    _mark_staged(workspace, streamlit_module)
    clear_export(streamlit_module)


__all__ = [
    "ResumeEditorView",
    "ResumeSuggestionPresentation",
    "active_editor_view",
    "approved_editor_revision_fingerprint",
    "exact_preview_pdf_bytes",
    "render_resume_editor",
    "set_editor_revision_approved",
    "suggestion_presentation",
]
