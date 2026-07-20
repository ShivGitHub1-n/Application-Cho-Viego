from __future__ import annotations

from collections.abc import MutableMapping
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Any, cast

import streamlit as st
from pydantic import ValidationError

from resume_tailor.application.generated_artifact import prepare_artifact_download
from resume_tailor.application.job_intake import (
    InvalidJobDescriptionError,
    build_job_posting,
    normalize_job_description,
)
from resume_tailor.application.profile_editor import (
    EntryKind,
    ProfileEditorInputError,
    add_bullet,
    add_education,
    add_entry,
    add_skill_category,
    editor_state_to_profile,
    empty_profile_editor_state,
    move_item,
    parse_profile_json,
    profile_change_fingerprint,
    remove_bullet,
    remove_education,
    remove_entry,
    remove_skill_category,
)
from resume_tailor.application.skill_categories import propose_reviewed_skill_categories
from resume_tailor.application.workflow_state import (
    ACTIVE_POSTING_KEY,
    POSTING_FINGERPRINT_KEY,
    get_active_posting,
    has_cover_letter_prerequisites,
    invalidate_posting_derived_workflow,
    invalidate_profile_derived_workflow,
)
from resume_tailor.domain.cover_letter import CoverLetterRecipient
from resume_tailor.domain.generated_artifact import (
    GeneratedResumeArtifact,
    GenerationStage,
)
from resume_tailor.domain.llm_models import LanguageModelError
from resume_tailor.domain.models import (
    JobPosting,
    MasterProfile,
    StructuredResume,
    TemplateConstraints,
)
from resume_tailor.domain.profile_completeness import (
    ProfileCompletenessReport,
    validate_master_profile_completeness,
)
from resume_tailor.frontend.job_discovery_view import (
    ApplicationJobDiscoveryDeliveryApi,
    render_job_discovery_view,
)
from resume_tailor.frontend.role_classification_view import (
    build_role_classification_diagnostic_view,
)
from resume_tailor.frontend.state import (
    NAVIGATION_ITEMS,
    initialize_frontend_state,
    navigate_to,
    populate_profile_editor_state,
)
from resume_tailor.infrastructure.application_data import application_database_path
from resume_tailor.infrastructure.config import Settings
from resume_tailor.infrastructure.dependencies import (
    create_job_discovery_services,
    create_profile_repository,
    create_tailor_service,
)
from resume_tailor.infrastructure.job_discovery_sqlite import SQLiteDiscoveredJobRepository
from resume_tailor.infrastructure.profile_repository import (
    CorruptStoredProfileError,
    ProfileStoreError,
    SQLiteMasterProfileRepository,
)
from resume_tailor.infrastructure.rendering import (
    PageOverflowError,
)
from resume_tailor.infrastructure.resume_extraction import (
    ResumeExtractionError,
    extract_resume_text,
)

st.set_page_config(
    page_title="Application Viego",
    page_icon=":material/description:",
    layout="wide",
)
st.markdown(
    """
    <style>
    .block-container {max-width: 1180px; padding-top: 1.8rem; padding-bottom: 3rem;}
    [data-testid="stSidebar"] .stCaption {line-height: 1.35;}
    </style>
    """,
    unsafe_allow_html=True,
)
_streamlit_run_started = perf_counter()

_PROGRESS_LABELS = {
    GenerationStage.PROFILE_LOADING: "Loading profile",
    GenerationStage.POSTING_NORMALIZATION: "Analyzing posting",
    GenerationStage.EVIDENCE_RETRIEVAL: "Retrieving evidence",
    GenerationStage.DETERMINISTIC_PLANNING: "Planning resume",
    GenerationStage.SEMANTIC_PLANNING: "Planning resume",
    GenerationStage.WRITER_CACHE_LOOKUP: "Tailoring bullets",
    GenerationStage.PROVIDER_REQUEST: "Tailoring bullets",
    GenerationStage.PROVIDER_RESPONSE_PARSING: "Tailoring bullets",
    GenerationStage.CLAIM_VALIDATION: "Validating claims",
    GenerationStage.COMPOSITION_CANDIDATE_CONSTRUCTION: "Fitting page",
    GenerationStage.PORTFOLIO_PAGE_FIT_SEARCH: "Fitting page",
    GenerationStage.DOCX_RENDERING: "Rendering document",
    GenerationStage.EXACT_WORD_PAGINATION: "Verifying pagination",
    GenerationStage.ESTIMATED_PAGINATION_FALLBACK: "Verifying pagination",
}


def _editor_widget_key(token: str, *parts: object) -> str:
    digest = sha256((token + ":" + ":".join(map(str, parts))).encode()).hexdigest()[:18]
    return f"profile-editor-{digest}"


def _state() -> MutableMapping[str, Any]:
    return cast(MutableMapping[str, Any], st.session_state)


def _active_posting() -> JobPosting | None:
    return cast(JobPosting | None, get_active_posting(_state()))


def _build_and_store_resume_artifact(
    service: Any,
    plan: Any,
    profile: MasterProfile,
    approved_claim_ids: set[str],
) -> GeneratedResumeArtifact:
    existing = cast(
        GeneratedResumeArtifact | None,
        st.session_state.get("generated_resume_artifact"),
    )
    with st.status("Building reviewed resume", expanded=True) as status:
        seen_labels: set[str] = set()

        def show_stage(stage: GenerationStage) -> None:
            label = _PROGRESS_LABELS.get(stage)
            if label is None:
                return
            status.update(label=label)
            if label not in seen_labels:
                status.write(label)
                seen_labels.add(label)

        service.telemetry.set_stage_callback(show_stage)
        try:
            artifact = service.build_generated_artifact(
                plan,
                profile,
                approved_claim_ids,
                existing_artifact=existing,
            )
        finally:
            service.telemetry.set_stage_callback(None)
        if artifact is not existing:
            storage_started = service.telemetry.clock()
            with service.telemetry.measure(GenerationStage.GENERATED_ARTIFACT_STORAGE):
                st.session_state["generated_resume_artifact"] = artifact
            storage_elapsed = service.telemetry.clock() - storage_started
            artifact = artifact.model_copy(
                update={
                    "stage_timings": service.telemetry.timings(),
                    "total_build_seconds": artifact.total_build_seconds + storage_elapsed,
                }
            )
        st.session_state["generated_resume_artifact"] = artifact
        st.session_state["resume"] = artifact.final_resume
        st.session_state["generated_content_reviewed"] = False
        status.update(label="Complete", state="complete", expanded=False)
    return artifact


def _render_artifact_summary(artifact: GeneratedResumeArtifact) -> None:
    composition = artifact.composition_diagnostic
    provider = artifact.provider_diagnostic
    pagination = artifact.pagination_diagnostic
    utilization = (
        f"{composition.final_utilization_ratio:.0%}" if composition is not None else "unavailable"
    )
    st.success(f"Completed in {artifact.total_build_seconds:.2f} seconds.")
    st.caption(
        f"Provider: {provider.status} · {provider.call_count} call(s) · "
        f"{provider.cache_hit_count} cache hit(s) · Pagination: {pagination.status} · "
        f"Utilization: {utilization}"
    )
    if provider.deterministic_fallback_used:
        st.info(provider.reason)
    if pagination.failure_reason:
        st.warning("Exact pagination was unavailable: " + pagination.failure_reason)
    if composition is not None:
        for warning in composition.underfill_reasons:
            if warning.value != "none":
                st.warning("Composition warning: " + warning.value.replace("_", " "))
    with st.expander("Build timing", expanded=False):
        for timing in artifact.stage_timings:
            detail = f" · {timing.detail}" if timing.detail else ""
            st.write(
                f"{timing.stage.value.replace('_', ' ').title()}: "
                f"{timing.elapsed_seconds:.3f}s · {timing.status.value}"
                f" · {timing.invocation_count} invocation(s){detail}"
            )


def _comma_text(value: list[str]) -> str:
    return ", ".join(value)


def _clear_cover_letter_state() -> None:
    for key in (
        "cover_letter",
        "cover_letter_reviewed",
        "cover_letter_profile_fingerprint",
        "cover_letter_posting_fingerprint",
        "cover_letter_plan_fingerprint",
        "cover_letter_evidence_fingerprint",
        "cover_letter_recipient_fingerprint",
    ):
        st.session_state.pop(key, None)


def _go_to_page(page: str) -> None:
    navigate_to(_state(), page)


def _persist_profile(
    profile: MasterProfile,
    repository: SQLiteMasterProfileRepository,
) -> bool:
    previous = st.session_state.get("profile")
    changed = previous is None or profile_change_fingerprint(
        previous
    ) != profile_change_fingerprint(profile)
    try:
        repository.save(profile)
    except (ProfileStoreError, ValueError):
        st.session_state["profile_editor_errors"] = [
            "The profile could not be saved to application storage."
        ]
        return False
    if changed:
        invalidate_profile_derived_workflow(_state())
    st.session_state["profile"] = profile
    st.session_state["profile_id"] = profile.id
    st.session_state["profile_load_status"] = "Reviewed profile saved."
    populate_profile_editor_state(
        _state(),
        profile,
        f"saved:{profile.id}:{profile_change_fingerprint(profile)}",
        defer_raw_json=True,
    )
    st.session_state.pop("profile_extraction_draft", None)
    st.session_state.pop("profile_extraction_source", None)
    st.session_state.pop("profile_editor_errors", None)
    return True


def _completeness_report(profile: MasterProfile | None) -> ProfileCompletenessReport | None:
    return validate_master_profile_completeness(profile) if profile is not None else None


def _render_profile_status(profile: MasterProfile | None) -> None:
    report = _completeness_report(profile)
    with st.container(border=True):
        if profile is None or report is None:
            st.markdown("**Profile status**")
            st.caption("No reviewed profile is loaded.")
            return
        st.markdown(f"**Profile status · `{profile.id}`**")
        if report.incomplete_field_paths:
            st.warning(
                f"Review needed · {len(report.incomplete_field_paths)} incomplete template fields",
                icon=":material/warning:",
            )
        else:
            st.success("Complete for Template V1", icon=":material/check_circle:")
        st.caption(st.session_state.get("profile_load_status", "Profile loaded."))


def _render_completeness_details(profile: MasterProfile) -> None:
    report = validate_master_profile_completeness(profile)
    if not report.incomplete_field_paths:
        st.success("All Template V1 completeness checks are satisfied.")
        return
    st.warning("Known facts are preserved, but these fields need review before generation:")
    for path in report.incomplete_field_paths:
        st.write(f"- `{path}`")


def _render_home() -> None:
    st.title("Application Viego")
    st.caption("An evidence-backed workspace for opportunity-specific applications.")
    profile = st.session_state.get("profile")
    columns = st.columns(3)
    with columns[0]:
        _render_profile_status(profile)
    with columns[1]:
        with st.container(border=True):
            st.markdown("**Tailoring status**")
            if st.session_state.get("resume") is not None:
                st.success("Resume ready for review")
            elif st.session_state.get("plan") is not None:
                st.info("Strategy ready")
            else:
                st.caption("No active strategy.")
    with columns[2]:
        with st.container(border=True):
            st.markdown("**Job Search status**")
            if st.session_state.get("job_discovery_run") is not None:
                st.info("Discovery results in this session")
            else:
                st.caption("No discovery run in this session.")
    st.subheader("Continue your workflow")
    with st.container(horizontal=True):
        st.button(
            "Review profile",
            icon=":material/person:",
            on_click=_go_to_page,
            args=("Profile",),
        )
        st.button(
            "Tailor resume",
            type="primary",
            icon=":material/description:",
            disabled=profile is None,
            on_click=_go_to_page,
            args=("Tailor Resume",),
        )
        st.button(
            "Search jobs",
            icon=":material/search:",
            disabled=profile is None,
            on_click=_go_to_page,
            args=("Job Search",),
        )
    if profile is None:
        st.info(
            "Start on the Profile page. Upload a resume or enter reviewed facts in "
            "the structured editor.",
            icon=":material/info:",
        )


def _render_profile_page(
    repository: SQLiteMasterProfileRepository,
    service: Any,
) -> None:
    st.title("Profile")
    st.caption(
        "Review canonical facts and evidence. Generated wording is kept outside this profile."
    )
    _render_profile_status(st.session_state.get("profile"))
    selected_id = st.text_input(
        "Selected profile ID",
        key="profile_id_input",
        placeholder="shiv-arora-master-v1",
    ).strip()
    st.caption(f"Active selection: `{selected_id or 'none'}`")
    with st.container(horizontal=True):
        load_clicked = st.button(
            "Load saved profile",
            icon=":material/folder_open:",
        )
        new_clicked = st.button(
            "Start blank profile",
            icon=":material/add:",
        )
    if load_clicked:
        try:
            if not selected_id:
                raise ValueError("Enter a profile ID to load.")
            loaded = repository.get(selected_id)
            if loaded is None:
                st.warning("No saved profile exists for that profile ID.")
            else:
                invalidate_profile_derived_workflow(_state())
                st.session_state["profile"] = loaded
                st.session_state["profile_id"] = loaded.id
                st.session_state["profile_load_status"] = "Loaded from application storage."
                populate_profile_editor_state(
                    _state(),
                    loaded,
                    f"saved:{loaded.id}:{profile_change_fingerprint(loaded)}",
                )
                st.success("Saved profile loaded.")
        except (ProfileStoreError, CorruptStoredProfileError, ValueError):
            st.error("The saved profile could not be loaded safely.")
    if new_clicked:
        if not selected_id:
            st.error("Enter a profile ID before starting a blank profile.")
        else:
            st.session_state["profile_editor_state"] = empty_profile_editor_state(selected_id)
            st.session_state["profile_editor_source_key"] = f"blank:{selected_id}"
            st.session_state["profile_editor_raw_json"] = ""
            st.session_state.pop("profile_editor_errors", None)

    with st.container(border=True):
        st.subheader("Import resume")
        uploaded = st.file_uploader(
            "Resume file",
            type=["docx", "pdf"],
            help="DOCX and text-based PDF are supported. Extracted facts always require review.",
        )
        if st.button(
            "Extract profile draft",
            icon=":material/upload_file:",
            disabled=uploaded is None,
        ):
            try:
                if uploaded is None:
                    raise ResumeExtractionError("Choose a resume file first.")
                if not selected_id:
                    raise ValueError("Enter a profile ID before extraction.")
                extracted = extract_resume_text(uploaded.name, uploaded.getvalue())
                result = service.extract_profile_draft(
                    selected_id,
                    extracted.source_format,
                    extracted.text,
                )
                st.session_state["profile_extraction_draft"] = result.output
                st.session_state["profile_extraction_source"] = extracted
                populate_profile_editor_state(
                    _state(),
                    result.output.profile,
                    "extracted:"
                    f"{result.output.profile.id}:"
                    f"{profile_change_fingerprint(result.output.profile)}",
                )
                st.success("Draft extracted into the structured editor below.")
            except ResumeExtractionError as error:
                st.error(str(error))
            except (LanguageModelError, ValueError):
                st.error(
                    "Profile extraction is unavailable. Configure the language model, "
                    "or enter reviewed facts manually."
                )

    draft = st.session_state.get("profile_extraction_draft")
    if draft is not None:
        with st.container(border=True):
            st.markdown("**Import review**")
            if draft.missing_fields:
                st.warning("Missing: " + ", ".join(draft.missing_fields))
            if draft.uncertain_fields:
                st.warning("Uncertain: " + ", ".join(draft.uncertain_fields))
            if draft.fidelity_flags:
                st.error(
                    "Unsupported extracted facts require correction: "
                    + " ".join(draft.fidelity_flags)
                )
            if draft.extraction_notes:
                st.caption(" ".join(draft.extraction_notes))

    if "profile_editor_state" not in st.session_state:
        active = st.session_state.get("profile")
        if active is not None:
            populate_profile_editor_state(
                _state(),
                active,
                f"active:{active.id}:{profile_change_fingerprint(active)}",
            )
        elif selected_id:
            st.session_state["profile_editor_state"] = empty_profile_editor_state(selected_id)
            st.session_state["profile_editor_source_key"] = f"blank:{selected_id}"
            st.session_state["profile_editor_raw_json"] = ""

    editor_state = st.session_state.get("profile_editor_state")
    if editor_state is None:
        st.info("Enter a profile ID to open the structured editor.")
        return
    _render_structured_profile_editor(editor_state, repository)
    active_profile = st.session_state.get("profile")
    if active_profile is not None:
        with st.expander(
            "Profile completeness",
            icon=":material/fact_check:",
        ):
            _render_completeness_details(active_profile)


def _render_structured_profile_editor(
    state: dict[str, Any],
    repository: SQLiteMasterProfileRepository,
) -> None:
    source_key = str(st.session_state.get("profile_editor_source_key", "structured-editor"))
    st.subheader("Structured profile editor")
    st.caption("Fields stay blank until entered or extracted; examples are never saved as facts.")
    with st.expander("Personal information", expanded=True):
        state["display_name"] = st.text_input(
            "Candidate name",
            state.get("display_name", ""),
            key=_editor_widget_key(source_key, "name"),
            placeholder="Full reviewed name",
        )
        contact = state.setdefault("contact", {})
        columns = st.columns(3)
        with columns[0]:
            contact["phone"] = st.text_input(
                "Phone",
                contact.get("phone", ""),
                key=_editor_widget_key(source_key, "phone"),
            )
        with columns[1]:
            contact["email"] = st.text_input(
                "Email",
                contact.get("email", ""),
                key=_editor_widget_key(source_key, "email"),
            )
        with columns[2]:
            contact["location"] = st.text_input(
                "Location",
                contact.get("location", ""),
                key=_editor_widget_key(source_key, "location"),
            )
        for index, link in enumerate(list(contact.get("links", []))):
            link_id = link.get("id", f"link-{index}")
            with st.container(horizontal=True, vertical_alignment="bottom"):
                link["value"] = st.text_input(
                    f"Link {index + 1}",
                    link.get("value", ""),
                    key=_editor_widget_key(source_key, "link", link_id),
                )
                if st.button(
                    "Remove",
                    key=_editor_widget_key(source_key, "remove-link", link_id),
                ):
                    contact["links"].pop(index)
                    st.rerun()
        if st.button(
            "Add link",
            icon=":material/add:",
            key=_editor_widget_key(source_key, "add-link"),
        ):
            contact.setdefault("links", []).append(
                {"id": f"link-{len(contact.get('links', []))}", "value": ""}
            )
            st.rerun()

    with st.expander("Education", expanded=True):
        for index, record in enumerate(state.get("education", [])):
            with st.container(border=True):
                st.markdown(f"**Education {index + 1}**")
                record["school"] = st.text_input(
                    "Institution",
                    record.get("school", ""),
                    key=_editor_widget_key(source_key, "education", index, "school"),
                )
                record["program"] = st.text_input(
                    "Degree or program",
                    record.get("program", ""),
                    key=_editor_widget_key(source_key, "education", index, "program"),
                )
                columns = st.columns(3)
                with columns[0]:
                    record["start_date"] = st.text_input(
                        "Start date",
                        record.get("start_date", ""),
                        key=_editor_widget_key(source_key, "education", index, "start"),
                    )
                    record["expected_graduation_date"] = st.text_input(
                        "Expected graduation date",
                        record.get("expected_graduation_date", ""),
                        key=_editor_widget_key(source_key, "education", index, "expected"),
                    )
                with columns[1]:
                    record["graduation_date"] = st.text_input(
                        "Completed graduation date",
                        record.get("graduation_date", ""),
                        key=_editor_widget_key(source_key, "education", index, "graduation"),
                    )
                    record["graduation_status"] = st.selectbox(
                        "Graduation status",
                        ["unknown", "expected", "completed"],
                        index=["unknown", "expected", "completed"].index(
                            str(record.get("graduation_status", "unknown"))
                        ),
                        key=_editor_widget_key(source_key, "education", index, "status"),
                    )
                with columns[2]:
                    record["location"] = st.text_input(
                        "Location",
                        record.get("location", ""),
                        key=_editor_widget_key(source_key, "education", index, "location"),
                    )
                    record["gpa"] = st.text_input(
                        "GPA",
                        record.get("gpa", ""),
                        key=_editor_widget_key(source_key, "education", index, "gpa"),
                    )
                record["minor_or_specialization"] = st.text_input(
                    "Minor or specialization",
                    record.get("minor_or_specialization", ""),
                    key=_editor_widget_key(source_key, "education", index, "minor"),
                )
                record["co_op_designation"] = st.text_input(
                    "Co-op designation",
                    record.get("co_op_designation", ""),
                    key=_editor_widget_key(source_key, "education", index, "coop"),
                )
                record["awards"] = st.text_input(
                    "Awards",
                    _comma_text(record.get("awards", [])),
                    key=_editor_widget_key(source_key, "education", index, "awards"),
                    help="Comma-separated reviewed awards.",
                ).split(",")
                record["relevant_coursework"] = st.text_input(
                    "Relevant coursework",
                    _comma_text(record.get("relevant_coursework", [])),
                    key=_editor_widget_key(source_key, "education", index, "coursework"),
                    help="Comma-separated reviewed courses.",
                ).split(",")
                with st.container(horizontal=True):
                    if st.button(
                        "Move up",
                        disabled=index == 0,
                        key=_editor_widget_key(source_key, "education-up", index),
                    ):
                        st.session_state["profile_editor_state"] = move_item(
                            state, "education", index, -1
                        )
                        st.rerun()
                    if st.button(
                        "Move down",
                        disabled=index == len(state.get("education", [])) - 1,
                        key=_editor_widget_key(source_key, "education-down", index),
                    ):
                        st.session_state["profile_editor_state"] = move_item(
                            state, "education", index, 1
                        )
                        st.rerun()
                    if st.button(
                        "Remove education",
                        key=_editor_widget_key(source_key, "education-remove", index),
                    ):
                        st.session_state["profile_editor_state"] = remove_education(state, index)
                        st.rerun()
        if st.button(
            "Add education",
            icon=":material/add:",
            key=_editor_widget_key(source_key, "education-add"),
        ):
            st.session_state["profile_editor_state"] = add_education(state)
            st.rerun()

    _render_profile_entries(state, "experiences", "Experiences", source_key)
    _render_profile_entries(state, "projects", "Projects", source_key)
    _render_profile_skills(state, source_key)

    for error in st.session_state.get("profile_editor_errors", []):
        st.error(error)
    if st.button(
        "Validate and save profile",
        type="primary",
        icon=":material/save:",
        key=_editor_widget_key(source_key, "save"),
    ):
        try:
            edited = editor_state_to_profile(state)
            if _persist_profile(edited, repository):
                st.success("Reviewed profile saved.")
        except (ValidationError, ValueError, TypeError) as error:
            message = _profile_error_message(error)
            st.session_state["profile_editor_errors"] = [message]
            st.error(message)

    with st.expander(
        "Advanced · raw profile JSON",
        icon=":material/code:",
    ):
        st.caption(
            "Use this fallback only when a schema field is not exposed above. "
            "It follows the same validation and save path."
        )
        pending_raw_json = st.session_state.pop("profile_editor_pending_raw_json", None)
        if pending_raw_json is not None:
            st.session_state["profile_editor_raw_json"] = pending_raw_json
        raw = st.text_area(
            "Raw profile JSON",
            key="profile_editor_raw_json",
            height=280,
        )
        if st.button(
            "Validate and save raw JSON",
            key=_editor_widget_key(source_key, "raw-save"),
        ):
            try:
                raw_profile = parse_profile_json(
                    raw,
                    expected_profile_id=str(
                        st.session_state.get("profile_id_input", state.get("id", ""))
                    ),
                )
                if _persist_profile(raw_profile, repository):
                    st.success("Reviewed raw profile saved.")
            except ProfileEditorInputError as error:
                st.session_state["profile_editor_errors"] = [str(error)]
                st.error(str(error))


def _render_profile_entries(
    state: dict[str, Any],
    kind: EntryKind,
    heading: str,
    source_key: str,
) -> None:
    with st.expander(heading, expanded=True):
        for index, entry in enumerate(state.get(kind, [])):
            entry_id = entry.get("id", f"{kind}-{index}")
            with st.container(border=True):
                st.markdown(f"**{heading[:-1]} {index + 1}** · `{entry_id}`")
                entry["title"] = st.text_input(
                    "Name or title",
                    entry.get("title", ""),
                    key=_editor_widget_key(source_key, kind, entry_id, "title"),
                    placeholder="Enter a reviewed title",
                )
                entry["organization"] = st.text_input(
                    "Employer or organization",
                    entry.get("organization", ""),
                    key=_editor_widget_key(source_key, kind, entry_id, "organization"),
                )
                columns = st.columns(3)
                with columns[0]:
                    entry["start_date"] = st.text_input(
                        "Start date",
                        entry.get("start_date", ""),
                        key=_editor_widget_key(source_key, kind, entry_id, "start"),
                    )
                with columns[1]:
                    entry["end_date"] = st.text_input(
                        "End date",
                        entry.get("end_date", ""),
                        key=_editor_widget_key(source_key, kind, entry_id, "end"),
                    )
                with columns[2]:
                    entry["location"] = st.text_input(
                        "Location",
                        entry.get("location", ""),
                        key=_editor_widget_key(source_key, kind, entry_id, "location"),
                    )
                entry["subtitle"] = st.text_input(
                    "Subtitle",
                    entry.get("subtitle", ""),
                    key=_editor_widget_key(source_key, kind, entry_id, "subtitle"),
                )
                entry["technology_label"] = st.text_input(
                    "Technology label",
                    entry.get("technology_label", ""),
                    key=_editor_widget_key(source_key, kind, entry_id, "technology-label"),
                )
                entry["award_or_placement"] = st.text_input(
                    "Award or placement",
                    entry.get("award_or_placement", ""),
                    key=_editor_widget_key(source_key, kind, entry_id, "award"),
                )
                entry["technologies"] = st.text_input(
                    "Technologies",
                    _comma_text(entry.get("technologies", [])),
                    key=_editor_widget_key(source_key, kind, entry_id, "technologies"),
                    help="Comma-separated reviewed technologies.",
                ).split(",")
                entry["capabilities"] = st.text_input(
                    "Capabilities",
                    _comma_text(entry.get("capabilities", [])),
                    key=_editor_widget_key(source_key, kind, entry_id, "capabilities"),
                ).split(",")
                entry["description"] = st.text_area(
                    "Description",
                    entry.get("description", ""),
                    key=_editor_widget_key(source_key, kind, entry_id, "description"),
                )
                st.markdown("**Evidence statements**")
                for bullet_index, bullet in enumerate(list(entry.get("bullets", []))):
                    bullet_id = bullet.get("id", f"bullet-{bullet_index}")
                    bullet["text"] = st.text_area(
                        f"Evidence statement {bullet_index + 1}",
                        bullet.get("text", ""),
                        key=_editor_widget_key(source_key, kind, entry_id, "bullet", bullet_id),
                    )
                    bullet["source_reference"] = st.text_input(
                        "Source reference",
                        bullet.get("source_reference", "") or "",
                        key=_editor_widget_key(
                            source_key, kind, entry_id, "bullet-source", bullet_id
                        ),
                    )
                    bullet["confirmed"] = st.checkbox(
                        "Evidence is confirmed",
                        bool(bullet.get("confirmed", True)),
                        key=_editor_widget_key(
                            source_key, kind, entry_id, "bullet-confirmed", bullet_id
                        ),
                    )
                    if st.button(
                        "Remove evidence statement",
                        key=_editor_widget_key(
                            source_key, kind, entry_id, "bullet-remove", bullet_id
                        ),
                    ):
                        st.session_state["profile_editor_state"] = remove_bullet(
                            state, kind, entry_id, bullet_id
                        )
                        st.rerun()
                with st.container(horizontal=True):
                    if st.button(
                        "Add evidence statement",
                        key=_editor_widget_key(source_key, kind, entry_id, "bullet-add"),
                    ):
                        st.session_state["profile_editor_state"] = add_bullet(state, kind, entry_id)
                        st.rerun()
                    if st.button(
                        "Move up",
                        disabled=index == 0,
                        key=_editor_widget_key(source_key, kind, entry_id, "up"),
                    ):
                        st.session_state["profile_editor_state"] = move_item(state, kind, index, -1)
                        st.rerun()
                    if st.button(
                        "Move down",
                        disabled=index == len(state.get(kind, [])) - 1,
                        key=_editor_widget_key(source_key, kind, entry_id, "down"),
                    ):
                        st.session_state["profile_editor_state"] = move_item(state, kind, index, 1)
                        st.rerun()
                    if st.button(
                        "Remove entry",
                        key=_editor_widget_key(source_key, kind, entry_id, "remove"),
                    ):
                        st.session_state["profile_editor_state"] = remove_entry(
                            state, kind, entry_id
                        )
                        st.rerun()
        if st.button(
            f"Add {heading[:-1].lower()}",
            icon=":material/add:",
            key=_editor_widget_key(source_key, kind, "add"),
        ):
            st.session_state["profile_editor_state"] = add_entry(state, kind)
            st.rerun()


def _render_profile_skills(state: dict[str, Any], source_key: str) -> None:
    with st.expander("Technical skills", expanded=True):
        state["declared_skills"] = st.text_input(
            "Legacy flat skills",
            _comma_text(state.get("declared_skills", [])),
            key=_editor_widget_key(source_key, "declared-skills"),
            help="Readable for compatibility. Reviewed categories below are authoritative.",
        ).split(",")
        if (
            state.get("declared_skills")
            and not state.get("technical_skills")
            and st.button(
                "Propose categories from reviewed skills",
                key=_editor_widget_key(source_key, "propose-categories"),
            )
        ):
            proposed = propose_reviewed_skill_categories(
                [value.strip() for value in state["declared_skills"] if value.strip()]
            )
            state["technical_skills"] = [
                {
                    "id": category.id,
                    "category": category.category,
                    "skills": [{"id": None, "value": value} for value in category.values],
                }
                for category in proposed
            ]
            st.session_state["profile_editor_state"] = state
            st.rerun()
        for index, category in enumerate(list(state.get("technical_skills", []))):
            category_id = category.get("id", f"category-{index}")
            with st.container(border=True):
                category["category"] = st.text_input(
                    "Category label",
                    category.get("category", ""),
                    key=_editor_widget_key(source_key, "category", category_id, "label"),
                )
                for skill_index, skill in enumerate(list(category.get("skills", []))):
                    skill_id = skill.get("id") or f"skill-{skill_index}"
                    with st.container(horizontal=True, vertical_alignment="bottom"):
                        skill["value"] = st.text_input(
                            "Reviewed skill",
                            skill.get("value", ""),
                            key=_editor_widget_key(
                                source_key,
                                "category",
                                category_id,
                                "skill",
                                skill_id,
                            ),
                        )
                        if st.button(
                            "Remove",
                            key=_editor_widget_key(
                                source_key,
                                "category",
                                category_id,
                                "skill-remove",
                                skill_id,
                            ),
                        ):
                            category["skills"].pop(skill_index)
                            st.rerun()
                with st.container(horizontal=True):
                    if st.button(
                        "Add skill",
                        key=_editor_widget_key(source_key, "category", category_id, "skill-add"),
                    ):
                        category.setdefault("skills", []).append({"id": None, "value": ""})
                        st.rerun()
                    if st.button(
                        "Remove category",
                        key=_editor_widget_key(source_key, "category", category_id, "remove"),
                    ):
                        st.session_state["profile_editor_state"] = remove_skill_category(
                            state, category_id
                        )
                        st.rerun()
        if st.button(
            "Add skill category",
            icon=":material/add:",
            key=_editor_widget_key(source_key, "category-add"),
        ):
            st.session_state["profile_editor_state"] = add_skill_category(state)
            st.rerun()


def _profile_error_message(error: Exception) -> str:
    if isinstance(error, ValidationError):
        first = error.errors(include_url=False, include_context=False)[0]
        location = ".".join(str(part) for part in first.get("loc", ())) or "profile"
        return f"Profile field {location!r} is invalid: {first.get('msg', 'Invalid value')}."
    return str(error)


def _generated_content_review(resume: StructuredResume) -> dict[str, list[str]]:
    education = [
        "; ".join(
            value
            for value in (
                record.school,
                record.program,
                record.start_date,
                record.expected_graduation_date or record.graduation_date,
                record.location,
                f"GPA {record.gpa}" if record.gpa else None,
                *record.awards,
                *record.relevant_coursework,
            )
            if value
        )
        for record in resume.education
    ]
    skills = [
        f"{category.category}: {', '.join(skill.value for skill in category.skills)}"
        for category in resume.technical_skills
    ]
    experience = [
        f"{resume.entity_titles.get(entity_id, entity_id)}: {bullet.text}"
        for entity_id, bullets in resume.experience_bullets.items()
        for bullet in bullets
    ]
    projects = [
        f"{resume.entity_titles.get(entity_id, entity_id)}: {bullet.text}"
        for entity_id, bullets in resume.project_bullets.items()
        for bullet in bullets
    ]
    return {
        "education": education,
        "technical skills": skills,
        "experience": experience,
        "projects": projects,
    }


def _render_role_diagnostic(plan: Any) -> None:
    view = build_role_classification_diagnostic_view(plan.report.role)
    if not view.semantic_enabled:
        return
    with st.container(border=True):
        st.markdown("**Role classification**")
        st.write(f"Resolved role family: {view.resolved_role_family}")
        st.caption(f"Selected source: {view.selected_source}")
        if view.fallback_reason:
            st.caption(f"Fallback: {view.fallback_reason}")
        if view.confidence is not None:
            st.caption(f"Validated Gemini confidence: {view.confidence:.0%}")
        if view.cached_reuse is not None:
            st.caption("Cached result reused: " + ("Yes" if view.cached_reuse else "No"))


def _render_composition_diagnostic(resume: StructuredResume) -> None:
    diagnostic = resume.composition_diagnostic
    if diagnostic is None:
        return
    with st.expander("Composition diagnostic"):
        st.write(diagnostic.reason)
        verification = (
            f"Exact page verification via {diagnostic.verification_provider}"
            if diagnostic.verification_status.value == "exact"
            else f"Estimated page fit via {diagnostic.verification_provider}"
        )
        st.caption(
            f"Outcome: {diagnostic.outcome.value.replace('_', ' ')} · "
            f"utilization: {diagnostic.final_utilization_ratio:.1%} · {verification}"
        )
        st.caption(
            "Termination: "
            + diagnostic.termination_reason.value.replace("_", " ")
            + f" · target: {diagnostic.utilization_target_floor:.0%}–"
            + f"{diagnostic.utilization_target_ceiling:.0%} · "
            + ("target reached" if diagnostic.utilization_target_reached else "target not reached")
        )
        exact_best = (
            f"{diagnostic.best_exact_verified_utilization_ratio:.1%}"
            if diagnostic.best_exact_verified_utilization_ratio is not None
            else "Unavailable"
        )
        st.caption(
            f"Best estimated utilization: "
            f"{diagnostic.best_estimated_utilization_ratio:.1%} · "
            f"best exact verified utilization: {exact_best}"
        )
        st.caption(
            f"Preferred density: {diagnostic.preferred_density_floor:.0%}-"
            f"{diagnostic.preferred_density_ceiling:.0%}; "
            + diagnostic.preferred_density_status.value.replace("_", " ")
        )
        if diagnostic.underfill_reasons:
            st.write(
                "Underfill classification: "
                + ", ".join(
                    reason.value.replace("_", " ") for reason in diagnostic.underfill_reasons
                )
            )
        st.caption(
            "Profile appears incomplete: "
            + ("Yes" if diagnostic.profile_appears_incomplete else "No")
        )
        if diagnostic.posting_requirements:
            st.markdown("**Posting requirements**")
            for requirement in diagnostic.posting_requirements:
                st.caption(
                    f"{requirement.authority.value}: {requirement.text} "
                    f"(importance {requirement.importance:.2f})"
                )
        if diagnostic.requirement_coverage:
            st.markdown("**Requirement coverage**")
            for coverage in diagnostic.requirement_coverage:
                relationships = ", ".join(
                    relationship.value for relationship in coverage.relationships
                )
                st.caption(
                    f"{coverage.text}: "
                    + (
                        f"{', '.join(coverage.selected_entry_ids)} via "
                        f"{relationships or 'reviewed evidence'}"
                        if coverage.selected_bullet_ids
                        else "uncovered"
                    )
                )
        if diagnostic.portfolio_coverage_gaps:
            st.write(
                "Portfolio coverage gaps: "
                + "; ".join(diagnostic.portfolio_coverage_gaps)
            )
        if diagnostic.direct_candidate_tradeoffs:
            st.markdown("**Direct-evidence tradeoffs**")
            for tradeoff in diagnostic.direct_candidate_tradeoffs:
                st.caption(
                    f"{tradeoff.omitted_candidate_id}: {tradeoff.reason}"
                )
        st.write(
            "Selected experiences: " + (", ".join(diagnostic.selected_experience_ids) or "None")
        )
        st.write("Selected projects: " + (", ".join(diagnostic.selected_project_ids) or "None"))
        st.write(
            "Selected bullets: "
            + (
                ", ".join(
                    f"{entry_id} ({count})" for entry_id, count in diagnostic.bullet_counts.items()
                )
                or "None"
            )
        )
        for entry in diagnostic.entry_bullet_selections:
            if not entry.selected_bullet_ids:
                continue
            retained = (
                "all retained"
                if entry.retained_all_available_bullets
                else f"{len(entry.omitted_bullet_reasons)} omitted"
            )
            st.caption(
                f"{entry.entry_id}: {len(entry.selected_bullet_ids)}/"
                f"{len(entry.available_bullet_ids)} bullets selected · {retained}"
            )
        if diagnostic.project_representation is not None:
            st.caption(
                "Project representation: "
                + diagnostic.project_representation.status.value.replace("_", " ")
            )
            st.write(diagnostic.project_representation.reason)
        st.write(
            "Selected skill categories: "
            + (", ".join(diagnostic.selected_skill_category_labels) or "None")
        )
        for row in diagnostic.selected_skill_rows:
            st.caption(
                f"{row.label}: {', '.join(row.skill_values)} "
                f"({len(row.skill_values)} reviewed skill(s), {row.relationship.value})"
            )
            st.caption(
                "Estimated Template V1 row width: "
                f"{row.estimated_used_width_points:.1f}/"
                f"{row.estimated_available_width_points:.1f} pt "
                f"({row.estimated_used_width_ratio:.0%}); "
                f"{row.estimated_remaining_width_points:.1f} pt remaining"
            )
            if row.grouping_reason:
                st.write(row.grouping_reason)
            st.caption("Source provenance: " + ", ".join(row.provenance))
            if row.compatible_omitted_skill_values:
                st.caption(
                    "Compatible omitted skills: "
                    + ", ".join(row.compatible_omitted_skill_values)
                )
            if row.underfill_exception_reason:
                st.caption("Underfill exception: " + row.underfill_exception_reason)
            if row.one_skill_exception_reason:
                st.write(row.one_skill_exception_reason)
        if diagnostic.omitted_direct_skill_values:
            st.write(
                "Omitted direct reviewed skills: "
                + ", ".join(diagnostic.omitted_direct_skill_values)
            )
            for skill, reason in diagnostic.omitted_direct_skill_reasons.items():
                st.caption(f"{skill}: {reason}")
        st.caption(
            f"Credible skill categories: {diagnostic.credible_skill_category_count} Â· "
            f"soft target: {diagnostic.desired_skill_category_count}"
        )
        if diagnostic.skill_category_shortfall_reason:
            st.caption("Skill-category shortfall: " + diagnostic.skill_category_shortfall_reason)
        st.caption(
            f"{diagnostic.estimated_page_evaluations} estimated render(s) · "
            f"{diagnostic.exact_page_evaluations} exact pagination attempt(s) · "
            f"{diagnostic.expansion_operations} expansion operation(s) · "
            f"{diagnostic.overflow_rollbacks} overflow rollback(s) · "
            "additional evidence unavailable: "
            + ("Yes" if diagnostic.additional_evidence_unavailable else "No")
        )
        hybrid = resume.hybrid_diagnostic
        if hybrid is not None:
            st.markdown("**Hybrid evidence and writing**")
            st.caption(
                "Writing: "
                + hybrid.writer_execution_status.value.replace("_", " ")
            )
            st.write(hybrid.writing_reason)
            st.caption(
                f"Planning: {hybrid.planning_status.value.replace('_', ' ')} · "
                f"provider calls: {hybrid.provider_call_count} · "
                f"cache hits: {hybrid.provider_cache_hits} · "
                f"layout input: {hybrid.layout_input.replace('_', ' ')}"
            )
            st.caption(
                f"Source bullets: {hybrid.source_bullet_count} · "
                f"rewritten: {hybrid.rewritten_bullet_count} · "
                f"fallback: {hybrid.fallback_bullet_count} · "
                f"rejected variants: {hybrid.rejected_variant_count}"
            )
            if hybrid.estimated_remaining_lines is not None:
                st.caption(f"Estimated remaining text lines: {hybrid.estimated_remaining_lines}")
            if hybrid.retrieval is not None:
                st.write(
                    "Retrieved reviewed evidence: "
                    f"{len(hybrid.retrieval.admitted)} admitted, "
                    f"{len(hybrid.retrieval.rejected)} rejected from "
                    f"{hybrid.retrieval.complete_profile_evidence_count} current items."
                )
                for item in hybrid.retrieval.admitted[:8]:
                    st.caption(
                        f"{item.evidence_id}: "
                        f"{item.admission_status.value.replace('_', ' ')} · "
                        f"relevance {item.contextual_relevance:.1f} · "
                        f"strength {item.intrinsic_evidence_strength:.1f}"
                    )
            selected_variants = [item for item in hybrid.bullet_variants if item.selected]
            if selected_variants:
                st.write("Validated rewritten bullets used by layout:")
                for item in selected_variants:
                    st.caption(
                        f"{item.variant_id} · "
                        f"{item.intended_length_class.value.replace('_', ' ')} · "
                        f"{item.validation_status.value.replace('_', ' ')}"
                    )
                    st.write(f"Source: {' '.join(item.original_reviewed_text)}")
                    st.write(f"Written: {item.rewritten_text}")
            if hybrid.rejected_variants:
                st.write("Rejected generated variants:")
                for item in hybrid.rejected_variants[:8]:
                    st.caption(f"{item.variant_id}: " + "; ".join(item.validation_reasons))
            if hybrid.validation_failures:
                st.write("Provider output validation failures:")
                for failure in hybrid.validation_failures[:8]:
                    st.caption(failure)
        st.write(
            "Unused relevant entries: "
            + (
                ", ".join(
                    [
                        *diagnostic.unused_experience_ids,
                        *diagnostic.unused_project_ids,
                    ]
                )
                or "None"
            )
        )
        st.write(
            "Unused reviewed bullets: "
            + (", ".join(diagnostic.unused_reviewed_bullet_ids) or "None")
        )
        for entry in diagnostic.entry_bullet_selections:
            if not entry.omitted_bullet_reasons:
                continue
            st.markdown(f"**Omitted bullets · {entry.entry_id}**")
            for evidence_id, omission_reason in entry.omitted_bullet_reasons.items():
                st.write(f"{evidence_id}: {omission_reason}")
        retained_all_entries = [
            entry
            for entry in diagnostic.entry_bullet_selections
            if entry.retained_all_available_bullets and entry.selected_bullet_ids
        ]
        if retained_all_entries:
            st.markdown("**Entries retaining all reviewed bullets**")
            for entry in retained_all_entries:
                st.write(entry.entry_id)
                for evidence_id, contribution in entry.distinct_contributions.items():
                    st.caption(f"{evidence_id}: {contribution}")
        st.write(
            "Unused relevant skill rows: "
            + (", ".join(diagnostic.unused_relevant_skill_category_ids) or "None")
        )
        if diagnostic.selected_candidates:
            st.markdown("**Selection reasons**")
            for candidate in diagnostic.selected_candidates:
                if candidate.kind.value == "education_detail":
                    continue
                st.write(
                    f"{candidate.candidate_id}: "
                    f"{candidate.selection_reason or 'Selected by deterministic ranking.'}"
                )
                if candidate.kind.value.endswith("bullet"):
                    st.caption(
                        "Relationship: "
                        + candidate.evidence_relationship.value
                        + f"; marginal contribution: {candidate.marginal_contribution:.1f}"
                    )
                    for token in candidate.short_token_contributions:
                        context = ", ".join(token.corroborating_context) or "none"
                        st.caption(
                            f"Short token {token.token}: contribution "
                            f"{token.contribution:.1f}; corroborated "
                            f"{'yes' if token.corroborated else 'no'}; context: {context}"
                        )
                if candidate.line_fit is not None:
                    st.caption(
                        f"Estimated line fit: {candidate.line_fit.expected_line_count} line(s); "
                        "final-line width "
                        f"{candidate.line_fit.expected_final_line_width_ratio:.0%}; "
                        "future shortening candidate: "
                        + ("Yes" if candidate.line_fit.future_rewrite_recommended else "No")
                    )
        diagnostic_groups = (
            (
                "Unused admissible candidates",
                diagnostic.unused_admissible_candidates,
            ),
            (
                "Candidates excluded only by bounds",
                diagnostic.candidates_excluded_by_search_bounds,
            ),
            (
                "Candidates excluded by relevance or redundancy thresholds",
                diagnostic.candidates_excluded_by_thresholds,
            ),
        )
        for label, candidates in diagnostic_groups:
            if not candidates:
                continue
            st.markdown(f"**{label}**")
            for candidate in candidates:
                penalty = (
                    f" Redundancy penalty: {candidate.redundancy_penalty:.1f}."
                    if candidate.redundancy_penalty
                    else ""
                )
                st.write(
                    f"{candidate.candidate_id}: "
                    f"{candidate.exclusion_reason or 'Not selected.'}{penalty}"
                )
        if diagnostic.verification_failure:
            st.warning(
                "Exact pagination provider failure retained for diagnosis: "
                + diagnostic.verification_failure
            )


def _render_tailor_page(service: Any) -> None:
    st.title("Tailor resume")
    profile = st.session_state.get("profile")
    if profile is None:
        st.info("Load and review a profile before tailoring a resume.")
        return
    _render_profile_status(profile)
    active_posting = _active_posting()
    with st.container(border=True):
        st.subheader("Opportunity")
        with st.form("tailoring-opportunity"):
            st.text_input(
                "Job title",
                value=(active_posting.title if active_posting is not None else ""),
                key="job_title_input",
                placeholder="Role title",
            )
            st.text_area(
                "Job description",
                key="job_description_input",
                height=240,
                placeholder="Paste the complete job description.",
            )
            recommend = st.form_submit_button(
                "Recommend resume strategy",
                type="primary",
                icon=":material/auto_awesome:",
            )
    raw_posting = st.session_state.get("job_description_input", "")
    if raw_posting.strip():
        try:
            with st.expander("Normalized job description"):
                st.code(normalize_job_description(raw_posting))
        except InvalidJobDescriptionError:
            pass
    if recommend:
        try:
            service.start_generation()
            service.telemetry.record(
                GenerationStage.STREAMLIT_RERUN_OVERHEAD,
                perf_counter() - _streamlit_run_started,
            )
            with service.telemetry.measure(
                GenerationStage.PROFILE_LOADING,
                detail="Reviewed profile reused from Streamlit session state.",
            ):
                service.telemetry.increment("profile_loads")
                profile = cast(MasterProfile, st.session_state["profile"])
            with service.telemetry.measure(GenerationStage.POSTING_NORMALIZATION):
                service.telemetry.increment("posting_normalizations")
                posting = build_job_posting(
                    "local-posting",
                    st.session_state.get("job_title_input", ""),
                    st.session_state.get("job_description_input", ""),
                )
            previous_posting = _active_posting()
            if (
                previous_posting is not None
                and previous_posting.model_dump_json() != posting.model_dump_json()
            ):
                invalidate_posting_derived_workflow(_state())
            plan = service.create_plan(profile, posting, TemplateConstraints())
            st.session_state[ACTIVE_POSTING_KEY] = posting
            st.session_state[POSTING_FINGERPRINT_KEY] = posting.model_dump_json()
            st.session_state["workflow_profile_fingerprint"] = profile_change_fingerprint(profile)
            st.session_state["plan"] = plan
            st.session_state.pop("resume", None)
            st.session_state.pop("generated_resume_artifact", None)
            st.session_state["generated_content_reviewed"] = False
            _clear_cover_letter_state()
        except (InvalidJobDescriptionError, ValueError) as error:
            st.error(str(error))

    plan = st.session_state.get("plan")
    current_posting = _active_posting()
    if plan is None or current_posting is None:
        st.info("Add the opportunity above to create an evidence-backed strategy.")
        return
    _render_role_diagnostic(plan)
    if plan.strategy is None:
        st.warning(plan.report.warnings[0] if plan.report.warnings else "No supported strategy.")
        return
    with st.container(border=True):
        st.subheader("Recommended strategy")
        st.write(plan.strategy.rationale)
        st.caption(f"Primary focus: {plan.strategy.primary_focus}")
        if plan.report.profile_fit and plan.report.profile_fit.status.value != "sufficient":
            st.warning(plan.report.profile_fit.reason)
        with st.expander("Decision details"):
            for decision in plan.report.decisions:
                st.write(f"**{decision.action.replace('_', ' ').title()}** · {decision.reason}")
            if plan.report.uncovered_signals:
                st.warning("Profile gaps: " + ", ".join(plan.report.uncovered_signals))

    review_ids = [
        candidate.id
        for candidate in plan.claim_candidates
        if candidate.support.value == "strong_inference_pending_review"
    ]
    approved_ids = {
        claim_id
        for claim_id in review_ids
        if st.checkbox(
            f"Approve inferred wording: {claim_id}",
            key=f"approve-{claim_id}",
        )
    }
    if st.button(
        "Build reviewed resume",
        type="primary",
        icon=":material/build:",
    ):
        service.telemetry.record(
            GenerationStage.STREAMLIT_RERUN_OVERHEAD,
            perf_counter() - _streamlit_run_started,
        )
        try:
            _build_and_store_resume_artifact(
                service,
                plan,
                profile,
                approved_ids,
            )
        except (PageOverflowError, ValueError) as error:
            st.error(str(error))

    resume = st.session_state.get("resume")
    if resume is None:
        return
    artifact = cast(
        GeneratedResumeArtifact | None,
        st.session_state.get("generated_resume_artifact"),
    )
    if artifact is not None:
        _render_artifact_summary(artifact)
    _render_composition_diagnostic(resume)
    st.subheader("Generated resume review")
    for label, items in _generated_content_review(resume).items():
        if items:
            with st.container(border=True):
                st.markdown(f"**{label.title()}**")
                for item in items:
                    st.write(item)
    pending_approved_ids: set[str] = set()
    if resume.review_pending_bullets or resume.review_pending_skills:
        with st.container(border=True):
            st.markdown("**Inferred content awaiting approval**")
            for bullet in resume.review_pending_bullets:
                if st.checkbox(
                    f"Approve inferred bullet: {bullet.text}",
                    key=f"approve-generated-{bullet.id}",
                ):
                    pending_approved_ids.add(bullet.id)
            for skill in resume.review_pending_skills:
                if st.checkbox(
                    f"Approve inferred skill: {skill.value}",
                    key=f"approve-generated-{skill.id}",
                ):
                    pending_approved_ids.add(skill.id)
    with st.container(border=True):
        st.markdown("**Resume Review / Editor**")
        st.caption(
            "Reserved for the future reorder, evidence-view, undo/redo, live-preview, "
            "and page-fit editor. No editing controls are implied in this release."
        )
    st.checkbox(
        "I reviewed the generated resume content and approve it for export.",
        key="generated_content_reviewed",
    )
    final_approved_ids = approved_ids | pending_approved_ids
    artifact_is_current = False
    if artifact is not None:
        try:
            artifact_is_current = artifact.artifact_fingerprint == (
                service.expected_artifact_fingerprint(
                    plan,
                    profile,
                    final_approved_ids,
                )
            )
        except ValueError:
            artifact_is_current = False
    if artifact is not None and not artifact_is_current:
        st.warning("Approved wording changed. Rebuild once before downloading the artifact.")
        if st.button(
            "Rebuild with approved wording",
            type="primary",
            icon=":material/build:",
        ):
            try:
                artifact = _build_and_store_resume_artifact(
                    service,
                    plan,
                    profile,
                    final_approved_ids,
                )
                artifact_is_current = True
            except (PageOverflowError, ValueError) as error:
                st.error(str(error))
    if artifact is not None:
        download = prepare_artifact_download(
            artifact,
            clock=service.telemetry.clock,
        )
        st.download_button(
            "Download DOCX",
            download.docx_bytes,
            "tailored-resume.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            icon=":material/download:",
            disabled=(
                not st.session_state.get("generated_content_reviewed", False)
                or not artifact_is_current
            ),
            on_click="ignore",
        )
        st.caption(
            f"Download preparation: {download.preparation_timing.elapsed_seconds:.3f}s · "
            "stored artifact bytes reused"
        )


def _render_cover_letter_page(service: Any) -> None:
    st.title("Cover letter")
    if not has_cover_letter_prerequisites(_state()):
        st.info("Create a reviewed profile and resume strategy before drafting a cover letter.")
        return
    profile = st.session_state["profile"]
    plan = st.session_state["plan"]
    posting = _active_posting()
    if posting is None:
        st.info("Create a reviewed profile and resume strategy before drafting a cover letter.")
        return
    st.caption("The draft reuses the active plan and confirmed evidence.")
    with st.container(border=True):
        recipient_name = st.text_input(
            "Recipient name",
            key="cover_recipient_name",
        )
        recipient_title = st.text_input(
            "Recipient title",
            key="cover_recipient_title",
        )
        recipient_company = st.text_input(
            "Company override",
            value=posting.company_name or "",
            key="cover_recipient_company",
        )
        recipient = CoverLetterRecipient(
            name=recipient_name.strip() or None,
            title=recipient_title.strip() or None,
            company=recipient_company.strip() or posting.company_name,
        )
        evidence_fingerprint = ":".join(
            sorted(
                item.id
                for item in profile.evidence
                if item.confirmed and item.entity_id in set(plan.selected_entity_ids)
            )
        )
        current_fingerprints = {
            "cover_letter_profile_fingerprint": profile_change_fingerprint(profile),
            "cover_letter_posting_fingerprint": posting.model_dump_json(),
            "cover_letter_plan_fingerprint": plan.model_dump_json(),
            "cover_letter_evidence_fingerprint": evidence_fingerprint,
            "cover_letter_recipient_fingerprint": recipient.model_dump_json(),
        }
        if any(
            st.session_state.get(key) is not None and st.session_state.get(key) != value
            for key, value in current_fingerprints.items()
        ):
            _clear_cover_letter_state()
        if st.button(
            "Generate cover-letter draft",
            type="primary",
            icon=":material/article:",
        ):
            try:
                st.session_state["cover_letter"] = service.draft_cover_letter(
                    profile,
                    posting,
                    plan,
                    recipient=recipient,
                )
                st.session_state["cover_letter_reviewed"] = False
                st.session_state.update(current_fingerprints)
            except (ValueError, LanguageModelError):
                st.error("Cover-letter drafting failed. Review configuration and inputs.")
    letter = st.session_state.get("cover_letter")
    if letter is None:
        return
    with st.container(border=True):
        st.subheader("Draft review")
        st.write(letter.date_text)
        st.write(letter.salutation)
        for paragraph in letter.paragraphs:
            st.write(paragraph.text)
            for claim in paragraph.claims:
                st.caption(
                    f"{claim.confidence.value.replace('_', ' ').title()} · "
                    f"evidence: {', '.join(claim.evidence_ids)}"
                )
        st.write(letter.closing)
        st.write(letter.signoff)
        st.write(f"**{letter.signoff_name}**")
    pending = {
        claim.id
        for claim in letter.pending_claims
        if st.checkbox(
            f"Approve strongly implied claim: {claim.text}",
            key=f"cover-approve-{claim.id}",
        )
    }
    reviewed = st.checkbox(
        "I reviewed the complete cover letter and its evidence.",
        key="cover_letter_reviewed",
    )
    if st.button(
        "Confirm cover-letter review",
        disabled=not reviewed,
    ):
        st.session_state["cover_letter"] = service.approve_cover_letter(
            letter,
            pending,
            reviewed=reviewed,
        )
        st.success("Cover-letter review recorded.")
    letter = st.session_state.get("cover_letter")
    can_export = bool(letter and letter.complete_review_confirmed and not letter.pending_claims)
    if st.button(
        "Export reviewed cover letter",
        type="primary",
        icon=":material/download:",
        disabled=not can_export,
    ):
        try:
            with TemporaryDirectory() as directory:
                exported = service.export_cover_letter(letter, Path(directory))
                st.session_state["cover_letter"] = exported
                st.download_button(
                    "Download cover-letter DOCX",
                    Path(exported.export_path).read_bytes(),
                    "cover-letter.docx",
                )
                st.success(f"Verified exactly {exported.page_count} page via DOCX measurement.")
        except (ValueError, PageOverflowError) as error:
            st.error(str(error))


def _render_job_search_page(
    settings: Settings,
    repository: SQLiteMasterProfileRepository,
) -> None:
    profile = st.session_state.get("profile")
    if profile is None:
        st.title("Job Search")
        st.info("Load a reviewed profile before configuring Job Search.")
        return
    if not settings.job_discovery_enabled or settings.job_discovery_source_registry_path is None:
        st.warning(
            "No approved job sources are configured. You can still review saved "
            "jobs and preferences; configure an approved registry before refresh."
        )
    if "_job_discovery_services" not in st.session_state:
        st.session_state["_job_discovery_services"] = create_job_discovery_services(settings)
    services = st.session_state["_job_discovery_services"]
    database = application_database_path(
        settings.app_data_directory,
        settings.profile_store_filename,
    )
    render_job_discovery_view(
        ApplicationJobDiscoveryDeliveryApi(
            services,
            [profile],
            SQLiteDiscoveredJobRepository(database),
        )
    )


def _render_settings_page(
    settings: Settings,
    repository: SQLiteMasterProfileRepository,
) -> None:
    st.title("Settings / Diagnostics")
    st.caption("Operational details stay compact; internal state is collapsed.")
    database = application_database_path(
        settings.app_data_directory,
        settings.profile_store_filename,
    )
    with st.container(border=True):
        st.markdown("**Application data**")
        st.code(str(settings.app_data_directory))
        st.caption(f"Database: {database.name}")
        st.caption("Override with APPLICATION_VIEGO_DATA_DIR for tests or portable use.")
    with st.container(border=True):
        st.markdown("**Deterministic availability**")
        st.write(
            "Available without Gemini credentials: "
            + ("Yes" if settings.llm_deterministic_fallback else "No")
        )
        st.write(
            "Gemini role classification: "
            + ("Enabled" if settings.llm_enable_role_classification else "Disabled")
        )
    report = repository.migration_report
    if report is not None:
        with st.container(border=True):
            st.markdown("**Repository-local compatibility import**")
            if report.source_database is None:
                st.caption("No repository-local compatibility source was selected.")
            else:
                st.caption(f"Checked: {report.source_database}")
                st.write(f"Imported rows: {report.imported_row_count}")
            for issue in report.issues:
                st.warning(issue)
    with st.expander(
        "Session diagnostics",
        icon=":material/monitoring:",
    ):
        st.json(
            {
                "active_page": st.session_state.get("active_page"),
                "profile_id": st.session_state.get("profile_id"),
                "has_plan": st.session_state.get("plan") is not None,
                "has_resume": st.session_state.get("resume") is not None,
                "has_cover_letter": st.session_state.get("cover_letter") is not None,
                "has_job_discovery_run": (st.session_state.get("job_discovery_run") is not None),
            }
        )


initialize_frontend_state(_state())
settings = Settings()
if "_tailor_service" not in st.session_state:
    st.session_state["_tailor_service"] = create_tailor_service()
if "_profile_repository" not in st.session_state:
    st.session_state["_profile_repository"] = create_profile_repository()
service = st.session_state["_tailor_service"]
profile_repository = st.session_state["_profile_repository"]

if not st.session_state.get("_profile_bootstrap_complete"):
    st.session_state["_profile_bootstrap_complete"] = True
    try:
        persisted = profile_repository.get(st.session_state["profile_id"])
        if persisted is not None:
            st.session_state["profile"] = persisted
            st.session_state["profile_id"] = persisted.id
            st.session_state["profile_id_input"] = persisted.id
            st.session_state["profile_load_status"] = "Loaded from persistent storage."
            populate_profile_editor_state(
                _state(),
                persisted,
                f"saved:{persisted.id}:{profile_change_fingerprint(persisted)}",
            )
    except (ProfileStoreError, CorruptStoredProfileError):
        st.session_state["profile_load_status"] = (
            "Saved profile data requires repair before it can be loaded."
        )

with st.sidebar:
    st.markdown("### Application Viego")
    st.caption("Evidence-backed application workspace")
    selected_navigation = st.radio(
        "Primary navigation",
        NAVIGATION_ITEMS,
        key="navigation_selection",
    )
    st.session_state["active_page"] = selected_navigation
    st.caption("Profile · " + str(st.session_state.get("profile_id", "not selected")))

active_page = st.session_state["active_page"]
if active_page == "Home / Workspace":
    _render_home()
elif active_page == "Profile":
    _render_profile_page(profile_repository, service)
elif active_page == "Tailor Resume":
    _render_tailor_page(service)
elif active_page == "Cover Letter":
    _render_cover_letter_page(service)
elif active_page == "Job Search":
    _render_job_search_page(settings, profile_repository)
elif active_page == "Settings / Diagnostics":
    _render_settings_page(settings, profile_repository)
