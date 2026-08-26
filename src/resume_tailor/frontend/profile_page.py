"""Career Profile workspace backed by the existing master-profile authority."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from html import escape
from typing import Any

from pydantic import ValidationError

from resume_tailor.application.profile_editor import (
    profile_change_fingerprint,
    profile_to_editor_state,
    unknown_profile_fields,
)
from resume_tailor.domain.llm_models import LanguageModelError
from resume_tailor.domain.models import MasterProfile
from resume_tailor.frontend.profile_editor_view import render_profile_editor
from resume_tailor.frontend.shared_components import render_page_header
from resume_tailor.infrastructure.profile_repository import (
    CorruptStoredProfileError,
    ProfileStoreError,
)
from resume_tailor.infrastructure.resume_extraction import (
    ResumeExtractionError,
    extract_resume_text,
)

PROFILE_SECTIONS = (
    "Reviewed profile",
    "Source résumé",
    "Edit profile",
    "Advanced",
)
PROFILE_DATA_SECTIONS = (
    "Personal",
    "Education",
    "Experiences",
    "Projects",
    "Skills",
    "Evidence",
)
_EDITOR_SECTION_BY_PROFILE_DATA = {
    "Personal": "Personal information",
    "Education": "Education",
    "Experiences": "Experiences",
    "Projects": "Projects",
    "Skills": "Skills",
    "Evidence": "Evidence library",
}
_LEGACY_SECTION_MAP = {
    "Master profile": ("Reviewed profile", None),
    "Overview": ("Reviewed profile", None),
    "Profile data": ("Edit profile", "Personal"),
    "Evidence": ("Edit profile", "Evidence"),
    "Import résumé": ("Source résumé", None),
    "Personal information": ("Edit profile", "Personal"),
    "Education": ("Edit profile", "Education"),
    "Experiences": ("Edit profile", "Experiences"),
    "Projects": ("Edit profile", "Projects"),
    "Skills": ("Edit profile", "Skills"),
    "Evidence library": ("Edit profile", "Evidence"),
    "Import": ("Source résumé", None),
}


@dataclass(frozen=True)
class ProfilePageDependencies:
    """Explicit page dependencies supplied by the application composition root."""

    profile_repository: Any
    tailor_service: Any
    invalidate_tailoring: Callable[[], None]


def _profile_fingerprint(profile: MasterProfile) -> str:
    return profile.model_dump_json()


def _initialize_editor(
    streamlit_module: Any,
    profile: MasterProfile,
    source_key: str,
    *,
    force: bool = False,
) -> None:
    if not force and streamlit_module.session_state.get("profile_editor_source_key") == source_key:
        return
    streamlit_module.session_state["profile_editor_state"] = profile_to_editor_state(profile)
    streamlit_module.session_state["profile_editor_source_key"] = source_key
    streamlit_module.session_state["profile_editor_ui_identities"] = {}
    streamlit_module.session_state["profile_editor_raw_json"] = json.dumps(
        profile.model_dump(mode="json"), indent=2
    )
    streamlit_module.session_state.pop("profile_editor_errors", None)


def _reset_editor_widget_values(streamlit_module: Any) -> None:
    """Clear editor widget values before their next instantiation.

    Streamlit owns keyed widget values for the duration of a run, so discard
    schedules this work for the next run instead of mutating an active widget.
    """

    for key in tuple(streamlit_module.session_state):
        if key == "profile-personal-name" or key.startswith("profile-editor-"):
            streamlit_module.session_state.pop(key, None)


def _load_profile(
    streamlit_module: Any, dependencies: ProfilePageDependencies
) -> MasterProfile | None:
    profile = streamlit_module.session_state.get("profile")
    requested_id = str(
        streamlit_module.session_state.get("profile_id")
        or streamlit_module.session_state.get("jobs_profile_id")
        or ""
    ).strip()
    if isinstance(profile, MasterProfile) and (not requested_id or profile.id == requested_id):
        streamlit_module.session_state.setdefault(
            "profile_load_status", "Loaded reviewed profile from application state."
        )
        return profile
    try:
        profile = dependencies.profile_repository.get(requested_id or "local-profile")
    except (ProfileStoreError, CorruptStoredProfileError) as error:
        streamlit_module.session_state["profile_load_status"] = (
            f"Saved profile unavailable: {error}"
        )
        return None
    if profile is None:
        current_status = str(streamlit_module.session_state.get("profile_load_status", ""))
        if not ("was not found" in current_status or "could not be loaded" in current_status):
            streamlit_module.session_state["profile_load_status"] = "No saved profile found."
        return None
    streamlit_module.session_state["profile"] = profile
    streamlit_module.session_state["profile_id"] = profile.id
    streamlit_module.session_state["jobs_profile_id"] = profile.id
    streamlit_module.session_state.pop("profile_extraction_draft", None)
    streamlit_module.session_state.pop("profile_extraction_source", None)
    streamlit_module.session_state["profile_load_status"] = "Loaded from persistent storage."
    _initialize_editor(
        streamlit_module, profile, f"saved:{profile.id}:{profile_change_fingerprint(profile)}"
    )
    return profile


def _load_existing_profile(
    streamlit_module: Any, dependencies: ProfilePageDependencies, profile_id: str
) -> MasterProfile | None:
    requested_id = profile_id.strip()
    if not requested_id:
        streamlit_module.session_state["profile_load_status"] = "Enter a profile ID to load it."
        return None
    try:
        profile = dependencies.profile_repository.get(requested_id)
    except CorruptStoredProfileError as error:
        streamlit_module.session_state["profile_load_status"] = (
            f"Profile {requested_id} is corrupt and could not be loaded: {error}"
        )
        return None
    except ProfileStoreError as error:
        streamlit_module.session_state["profile_load_status"] = (
            f"Profile {requested_id} could not be loaded: {error}"
        )
        return None
    if profile is None:
        streamlit_module.session_state["profile_load_status"] = (
            f"Profile {requested_id} was not found."
        )
        return None
    previous = streamlit_module.session_state.get("profile")
    changed = not isinstance(previous, MasterProfile) or (
        profile_change_fingerprint(previous) != profile_change_fingerprint(profile)
    )
    if changed:
        dependencies.invalidate_tailoring()
    streamlit_module.session_state["profile"] = profile
    streamlit_module.session_state["profile_id"] = profile.id
    streamlit_module.session_state["jobs_profile_id"] = profile.id
    streamlit_module.session_state.pop("profile_extraction_draft", None)
    streamlit_module.session_state.pop("profile_extraction_source", None)
    streamlit_module.session_state["profile_load_status"] = f"Loaded profile {profile.id}."
    _initialize_editor(
        streamlit_module, profile, f"saved:{profile.id}:{profile_change_fingerprint(profile)}"
    )
    return profile


def _persist_profile(
    streamlit_module: Any,
    dependencies: ProfilePageDependencies,
    profile: MasterProfile,
) -> bool:
    previous = streamlit_module.session_state.get("profile")
    changed = not isinstance(previous, MasterProfile) or (
        profile_change_fingerprint(previous) != profile_change_fingerprint(profile)
    )
    try:
        dependencies.profile_repository.save(profile)
    except (ProfileStoreError, ValueError) as error:
        streamlit_module.session_state["profile_editor_errors"] = [f"Persistence failed: {error}"]
        return False
    if changed:
        dependencies.invalidate_tailoring()
    streamlit_module.session_state["profile"] = profile
    streamlit_module.session_state["profile_id"] = profile.id
    streamlit_module.session_state["jobs_profile_id"] = profile.id
    streamlit_module.session_state["profile_load_status"] = "Profile saved successfully."
    _initialize_editor(
        streamlit_module, profile, f"saved:{profile.id}:{profile_change_fingerprint(profile)}"
    )
    streamlit_module.session_state.pop("profile_extraction_draft", None)
    streamlit_module.session_state.pop("profile_extraction_source", None)
    streamlit_module.session_state.pop("profile_source_import_open", None)
    streamlit_module.session_state.pop("profile_editor_errors", None)
    return True


def _render_overview(
    streamlit_module: Any, dependencies: ProfilePageDependencies, profile: MasterProfile | None
) -> MasterProfile | None:
    streamlit_module.subheader("Profile overview")
    streamlit_module.caption(
        "This reviewed profile is the source of truth for Jobs, Resume Studio, and Cover Letters."
    )
    if profile is None:
        streamlit_module.info("Import a résumé or load a saved reviewed profile to begin.")
        profile_id = streamlit_module.text_input(
            "Existing profile ID",
            value=str(streamlit_module.session_state.get("profile_id", "local-profile")),
            key="profile-entry-id",
        )
        if streamlit_module.button(
            "Load reviewed profile", key="profile-load-existing", type="primary"
        ):
            return _load_existing_profile(streamlit_module, dependencies, profile_id)
        return None
    columns = streamlit_module.columns(4)
    values = (
        ("Experiences", len(profile.experiences)),
        ("Projects", len(profile.projects)),
        ("Evidence", len(profile.evidence)),
        ("Skill groups", len(profile.technical_skills)),
    )
    for column, (label, value) in zip(columns, values, strict=True):
        with column:
            streamlit_module.metric(label, value)
    streamlit_module.info(
        "Review confirmation, source references, and validation remain attached "
        "to profile evidence."
    )
    switch_id = streamlit_module.text_input(
        "Switch reviewed profile ID",
        value=profile.id,
        key="profile-switch-id",
    )
    if streamlit_module.button("Load another reviewed profile", key="profile-switch-load"):
        return _load_existing_profile(streamlit_module, dependencies, switch_id)
    return profile


def _render_import(
    streamlit_module: Any,
    dependencies: ProfilePageDependencies,
    profile: MasterProfile | None,
) -> MasterProfile | None:
    streamlit_module.subheader("Résumé import")
    streamlit_module.caption(
        "Extracted content is a draft until you review and explicitly save it."
    )
    profile_id = streamlit_module.text_input(
        "Profile ID",
        value=(
            profile.id
            if profile is not None
            else streamlit_module.session_state.get("profile_id", "local-profile")
        ),
        key="profile-import-id",
    )
    uploaded = streamlit_module.file_uploader(
        "Upload résumé for extracted-profile review (.docx or text-based .pdf)",
        type=["docx", "pdf"],
        key="profile-import-upload",
    )
    if streamlit_module.button("Extract profile draft", key="profile-extract-draft"):
        try:
            if uploaded is None:
                raise ResumeExtractionError("Choose a DOCX or text-based PDF résumé first.")
            extracted = extract_resume_text(uploaded.name, uploaded.getvalue())
            result = dependencies.tailor_service.extract_profile_draft(
                profile_id.strip() or "local-profile",
                extracted.source_format,
                extracted.text,
                extracted.contact_links,
            )
            streamlit_module.session_state["profile_extraction_draft"] = result.output
            streamlit_module.session_state["profile_extraction_source"] = extracted
            profile = result.output.profile
            _initialize_editor(
                streamlit_module,
                profile,
                f"extracted:{profile.id}:{profile_change_fingerprint(profile)}",
            )
            streamlit_module.success(
                "Draft profile extracted. Review and correct it before approval."
            )
        except (ResumeExtractionError, ValueError, LanguageModelError) as error:
            streamlit_module.error(f"Résumé extraction failed: {error}")
    draft = streamlit_module.session_state.get("profile_extraction_draft")
    if draft:
        streamlit_module.markdown("**Extracted-profile review**")
        for label, values in (
            ("Missing fields", draft.missing_fields),
            ("Uncertain fields", draft.uncertain_fields),
            ("Extraction notes", draft.extraction_notes),
            ("Fidelity flags", draft.fidelity_flags),
        ):
            if values:
                streamlit_module.warning(f"{label}: " + " ".join(values))
    return profile


def _render_advanced(
    streamlit_module: Any,
    dependencies: ProfilePageDependencies,
    profile: MasterProfile | None,
) -> MasterProfile | None:
    streamlit_module.subheader("Advanced tools")
    streamlit_module.caption("Raw JSON is for schema fields not represented in the focused editor.")
    if profile is None:
        streamlit_module.caption(
            "Create a reviewed profile from validated JSON when no saved profile is available."
        )
        advanced_id = streamlit_module.text_input(
            "Existing profile ID (Advanced)", key="profile-advanced-id"
        )
        if streamlit_module.button("Load profile by ID", key="profile-advanced-load"):
            _load_existing_profile(streamlit_module, dependencies, advanced_id)
            streamlit_module.rerun()
        raw = streamlit_module.text_area(
            "Raw profile JSON", key="profile-bootstrap-raw-json", height=260
        )
        if streamlit_module.button(
            "Validate and save reviewed profile", key="profile-bootstrap-save", type="primary"
        ):
            try:
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    raise ValueError("Profile JSON must be an object.")
                unknown = unknown_profile_fields(payload)
                if unknown:
                    raise ValueError(
                        "Unsupported top-level fields cannot be safely round-tripped: "
                        + ", ".join(unknown)
                    )
                raw_profile = MasterProfile.model_validate(payload)
                if _persist_profile(streamlit_module, dependencies, raw_profile):
                    streamlit_module.success("Validated raw profile saved.")
                    return raw_profile
            except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as error:
                streamlit_module.session_state["profile_editor_errors"] = [str(error)]
                streamlit_module.error(f"Raw profile was not saved: {error}")
        return None
    raw = streamlit_module.text_area("Raw profile JSON", key="profile_editor_raw_json", height=260)
    if streamlit_module.button("Validate and save raw JSON", key="profile-save-raw"):
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("Profile JSON must be an object.")
            unknown = unknown_profile_fields(payload)
            if unknown:
                raise ValueError(
                    "Unsupported top-level fields cannot be safely round-tripped: "
                    + ", ".join(unknown)
                )
            raw_profile = MasterProfile.model_validate(payload)
            if raw_profile.id != profile.id:
                raise ValueError("Profile ID cannot be changed in the editor.")
            if _persist_profile(streamlit_module, dependencies, raw_profile):
                streamlit_module.success("Validated raw profile saved.")
        except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as error:
            streamlit_module.session_state["profile_editor_errors"] = [str(error)]
            streamlit_module.error(f"Raw profile was not saved: {error}")
    return profile


def _render_reviewed_profile_selector(
    streamlit_module: Any, dependencies: ProfilePageDependencies, profile: MasterProfile | None
) -> None:
    try:
        profiles = list(dependencies.profile_repository.list_all())
    except (AttributeError, ProfileStoreError, CorruptStoredProfileError, ValueError) as error:
        streamlit_module.error(f"Reviewed profiles could not be listed: {error}")
        return
    if not profiles:
        streamlit_module.info("No reviewed profiles are available yet.")
        return
    ids = [item.id for item in profiles]
    labels = {item.id: item.display_name for item in profiles}
    active_id = getattr(profile, "id", None) or streamlit_module.session_state.get("profile_id")
    selected = streamlit_module.selectbox(
        "Reviewed profile",
        ids,
        index=ids.index(active_id) if active_id in ids else 0,
        format_func=lambda value: labels[value],
        key="profile-reviewed-selector",
    )
    if streamlit_module.button(
        "Load selected profile", key="profile-reviewed-load", type="primary"
    ):
        _load_existing_profile(streamlit_module, dependencies, selected)
        streamlit_module.rerun()


def _profile_canvas_css() -> str:
    return """
    <style>
    .st-key-reviewed-profile-canvas {
        background: linear-gradient(155deg, color-mix(in srgb, var(--pw-surface) 96%, white),
                    var(--pw-surface));
        border-color: var(--pw-border-strong) !important;
        box-shadow: 0 18px 46px color-mix(in srgb, black 18%, transparent);
        padding: clamp(1.25rem, 3vw, 2.4rem) !important;
    }
    .profile-document-section {
        color: var(--pw-text-muted);
        font-size: .72rem;
        font-weight: 750;
        letter-spacing: .12em;
        margin: 1.15rem 0 .55rem;
        text-transform: uppercase;
    }
    .profile-document-entry { margin: .15rem 0 1.05rem; }
    .profile-document-entry h4 {
        font-size: 1rem;
        line-height: 1.35;
        margin: 0 0 .12rem;
    }
    .profile-document-meta {
        color: var(--pw-text-muted);
        font-size: .82rem;
        margin-bottom: .38rem;
    }
    .profile-document-entry ul {
        line-height: 1.48;
        margin: .3rem 0 0 1.05rem;
        padding: 0;
    }
    .profile-document-entry li { margin: .27rem 0; }
    .profile-skill-line { line-height: 1.55; margin: .2rem 0; }
    .profile-review-needed {
        color: var(--pw-state-review);
        font-size: .72rem;
        font-weight: 650;
        margin-left: .35rem;
    }
    </style>
    """


def _skill_values(category: Any) -> list[str]:
    return [item.value for item in category.skills] if category.skills else list(category.values)


def _entry_metadata(entry: Any) -> str:
    dates = " – ".join(value for value in (entry.start_date, entry.end_date) if value)
    return " · ".join(
        value
        for value in (
            entry.organization,
            entry.location,
            dates,
            entry.subtitle,
            entry.technology_label,
        )
        if value
    )


def _reviewed_entry_evidence(profile: MasterProfile, entry: Any) -> list[tuple[str, bool]]:
    owned = [item for item in profile.evidence if item.entity_id == entry.id]
    if owned:
        return [(item.source_text, item.confirmed) for item in owned]
    fallback = list(dict.fromkeys([*entry.bullets, *entry.bullet_points]))
    return [(item, True) for item in fallback]


def _render_profile_entry(streamlit_module: Any, profile: MasterProfile, entry: Any) -> None:
    evidence = _reviewed_entry_evidence(profile, entry)
    details = []
    if entry.description:
        details.append(f"<p>{escape(entry.description)}</p>")
    if evidence:
        bullets = "".join(
            "<li>"
            + escape(text)
            + ("" if confirmed else '<span class="profile-review-needed">Needs review</span>')
            + "</li>"
            for text, confirmed in evidence
        )
        details.append(f"<ul>{bullets}</ul>")
    metadata = _entry_metadata(entry)
    streamlit_module.markdown(
        '<div class="profile-document-entry">'
        f"<h4>{escape(entry.title)}</h4>"
        + (f'<div class="profile-document-meta">{escape(metadata)}</div>' if metadata else "")
        + "".join(details)
        + "</div>",
        unsafe_allow_html=True,
    )


def _render_reviewed_profile_canvas(streamlit_module: Any, profile: MasterProfile) -> None:
    streamlit_module.markdown(_profile_canvas_css(), unsafe_allow_html=True)
    with streamlit_module.container(border=True, key="reviewed-profile-canvas"):
        if profile.education:
            streamlit_module.markdown(
                '<div class="profile-document-section">Education</div>',
                unsafe_allow_html=True,
            )
            for record in profile.education:
                dates = " – ".join(
                    value
                    for value in (
                        record.start_date,
                        record.expected_graduation_date or record.graduation_date,
                    )
                    if value
                )
                metadata = " · ".join(
                    value
                    for value in (
                        record.location,
                        dates,
                        f"GPA {record.gpa}" if record.gpa else None,
                    )
                    if value
                )
                details = [record.program]
                details.extend(
                    value
                    for value in (record.minor_or_specialization, record.co_op_designation)
                    if value
                )
                if record.awards:
                    details.append("Awards: " + ", ".join(record.awards))
                if record.relevant_coursework:
                    details.append("Relevant coursework: " + ", ".join(record.relevant_coursework))
                streamlit_module.markdown(
                    '<div class="profile-document-entry">'
                    f"<h4>{escape(record.school)}</h4>"
                    + (
                        f'<div class="profile-document-meta">{escape(metadata)}</div>'
                        if metadata
                        else ""
                    )
                    + f"<p>{escape(' · '.join(details))}</p>"
                    + "</div>",
                    unsafe_allow_html=True,
                )
        if profile.technical_skills:
            streamlit_module.markdown(
                '<div class="profile-document-section">Technical skills</div>',
                unsafe_allow_html=True,
            )
            for category in profile.technical_skills:
                values = ", ".join(_skill_values(category))
                streamlit_module.markdown(
                    '<div class="profile-skill-line">'
                    f"<strong>{escape(category.category)}</strong> · {escape(values)}"
                    "</div>",
                    unsafe_allow_html=True,
                )
        if profile.experiences:
            streamlit_module.markdown(
                '<div class="profile-document-section">Experience</div>',
                unsafe_allow_html=True,
            )
            for entry in profile.experiences:
                _render_profile_entry(streamlit_module, profile, entry)
        if profile.projects:
            streamlit_module.markdown(
                '<div class="profile-document-section">Projects</div>',
                unsafe_allow_html=True,
            )
            for entry in profile.projects:
                _render_profile_entry(streamlit_module, profile, entry)
        if not any(
            (profile.education, profile.technical_skills, profile.experiences, profile.projects)
        ):
            streamlit_module.caption("This reviewed profile does not contain career records yet.")


def _render_source_resume(
    streamlit_module: Any,
    dependencies: ProfilePageDependencies,
    profile: MasterProfile | None,
) -> MasterProfile | None:
    streamlit_module.subheader("Source résumé")
    source = streamlit_module.session_state.get("profile_extraction_source")
    if source is not None:
        streamlit_module.caption(
            f"Current import review · {source.filename} · {source.source_format.upper()}"
        )
        streamlit_module.warning(
            "The original uploaded file is not persisted. The extracted text below is available "
            "only during this review session and is not a visual copy of the source document."
        )
        with streamlit_module.expander("View extracted source text", expanded=False):
            streamlit_module.text(source.text)
    else:
        streamlit_module.info(
            "The reviewed Career Profile is available, but the original uploaded résumé "
            "file was not retained by the current persistence model."
        )
        streamlit_module.caption(
            "Viego stores the validated profile record, not the source DOCX/PDF bytes. "
            "Import a newer résumé to start a new review."
        )
    import_open = profile is None or bool(
        streamlit_module.session_state.get("profile_source_import_open", False)
    )
    if not import_open and streamlit_module.button(
        "Import a newer résumé",
        icon=":material/upload_file:",
        key="profile-source-import-open",
    ):
        streamlit_module.session_state["profile_source_import_open"] = True
        streamlit_module.rerun()
    if import_open:
        profile = _render_import(streamlit_module, dependencies, profile)
        if streamlit_module.session_state.get("profile_extraction_draft") is not None:
            if streamlit_module.button(
                "Review extracted profile",
                type="primary",
                icon=":material/rate_review:",
                key="profile-review-extracted",
            ):
                streamlit_module.session_state["profile_pending_section"] = "Edit profile"
                streamlit_module.session_state["profile_data_pending_section"] = "Personal"
                streamlit_module.rerun()
    return profile


def _render_overview_v2(
    streamlit_module: Any, dependencies: ProfilePageDependencies, profile: MasterProfile | None
) -> MasterProfile | None:
    streamlit_module.subheader("Reviewed Career Profile")
    if profile is None:
        streamlit_module.info(
            "Import a résumé, create a profile manually, or load a reviewed profile to begin."
        )
        actions = streamlit_module.columns(3)
        with actions[0]:
            if streamlit_module.button(
                "Import a résumé", key="profile-onboard-import", type="primary"
            ):
                streamlit_module.session_state["profile_pending_section"] = "Source résumé"
                streamlit_module.session_state["profile_source_import_open"] = True
                streamlit_module.rerun()
        with actions[1]:
            if streamlit_module.button("Create profile manually", key="profile-onboard-create"):
                profile = MasterProfile(
                    id="local-profile", user_id="local-user", display_name="New candidate"
                )
                streamlit_module.session_state["profile"] = profile
                streamlit_module.session_state["profile_id"] = profile.id
                streamlit_module.session_state["jobs_profile_id"] = profile.id
                _initialize_editor(streamlit_module, profile, "draft:local-profile", force=True)
                streamlit_module.session_state["profile_load_status"] = (
                    "New profile draft is not saved."
                )
                streamlit_module.session_state["profile_pending_section"] = "Edit profile"
                streamlit_module.session_state["profile_data_pending_section"] = "Personal"
                streamlit_module.rerun()
        with actions[2]:
            if streamlit_module.button(
                "Load an existing reviewed profile", key="profile-onboard-load"
            ):
                streamlit_module.session_state["profile_selector_focus"] = True
                streamlit_module.session_state["profile_pending_section"] = "Reviewed profile"
                streamlit_module.rerun()
        _render_reviewed_profile_selector(streamlit_module, dependencies, None)
        return None
    confirmed_evidence = sum(item.confirmed for item in profile.evidence)
    readiness_checks = (
        bool(profile.experiences or profile.projects),
        bool(confirmed_evidence),
        bool(profile.technical_skills),
        bool(profile.contact.email or profile.contact.phone),
    )
    readiness = (
        "Ready for tailoring"
        if all(readiness_checks)
        else "Nearly ready"
        if sum(readiness_checks) >= 3
        else "Needs review"
    )
    with streamlit_module.container(
        horizontal=True,
        horizontal_alignment="distribute",
        vertical_alignment="center",
    ):
        with streamlit_module.container(gap=None):
            streamlit_module.markdown(f"### {profile.display_name}")
            streamlit_module.caption(
                f"{len(profile.experiences)} experience"
                f"{'s' if len(profile.experiences) != 1 else ''} · "
                f"{len(profile.projects)} project{'s' if len(profile.projects) != 1 else ''} · "
                f"{confirmed_evidence} reviewed evidence item"
                f"{'s' if confirmed_evidence != 1 else ''}"
            )
        streamlit_module.badge(
            readiness,
            icon=(
                ":material/check_circle:"
                if readiness == "Ready for tailoring"
                else ":material/rate_review:"
            ),
            color="green" if readiness == "Ready for tailoring" else "orange",
        )
    streamlit_module.caption(
        "This is the reviewed source of truth used for job matching and document tailoring."
    )
    try:
        profiles = list(dependencies.profile_repository.list_all())
    except (ProfileStoreError, CorruptStoredProfileError, ValueError) as error:
        streamlit_module.error(f"Reviewed profiles could not be listed: {error}")
        profiles = []
    if len(profiles) > 1:
        ids = [item.id for item in profiles]
        labels = {item.id: item.display_name for item in profiles}
        with streamlit_module.expander("Switch reviewed profile", expanded=False):
            selected = streamlit_module.selectbox(
                "Reviewed profile",
                ids,
                index=ids.index(profile.id) if profile is not None and profile.id in ids else 0,
                format_func=lambda value: labels[value],
                key="profile-reviewed-selector",
            )
            if streamlit_module.button(
                "Switch profile", key="profile-reviewed-load", type="primary"
            ):
                _load_existing_profile(streamlit_module, dependencies, selected)
                streamlit_module.rerun()
    elif not profiles:
        streamlit_module.info("No reviewed profiles are available yet.")
    with streamlit_module.container(horizontal=True):
        if streamlit_module.button("Edit profile", key="profile-edit-action", type="primary"):
            streamlit_module.session_state["profile_pending_section"] = "Edit profile"
            streamlit_module.session_state["profile_data_pending_section"] = "Personal"
            streamlit_module.rerun()
        if streamlit_module.button(
            "View source résumé",
            icon=":material/description:",
            key="profile-source-action",
        ):
            streamlit_module.session_state["profile_pending_section"] = "Source résumé"
            streamlit_module.rerun()
    _render_reviewed_profile_canvas(streamlit_module, profile)
    return profile


def _render_profile_page_v2(streamlit_module: Any, dependencies: ProfilePageDependencies) -> None:
    profile = _load_profile(streamlit_module, dependencies)
    draft = streamlit_module.session_state.get("profile_extraction_draft")
    editable_profile = draft.profile if draft is not None else profile
    if editable_profile is not None:
        expected_source_key = (
            f"extracted:{editable_profile.id}:{profile_change_fingerprint(editable_profile)}"
            if draft is not None
            else f"saved:{editable_profile.id}:{profile_change_fingerprint(editable_profile)}"
        )
        discard_pending = streamlit_module.session_state.pop(
            "profile_editor_discard_pending", False
        )
        if discard_pending:
            _reset_editor_widget_values(streamlit_module)
        _initialize_editor(
            streamlit_module, editable_profile, expected_source_key, force=discard_pending
        )
    render_page_header(
        streamlit_module,
        "Career Profile",
        "Reviewed source of truth for tailored jobs and evidence-backed documents.",
        eyebrow="Profile",
    )
    legacy = streamlit_module.session_state.get("profile-active-section")
    if legacy in _LEGACY_SECTION_MAP:
        primary, secondary = _LEGACY_SECTION_MAP[legacy]
        streamlit_module.session_state["profile-active-section"] = primary
        if secondary:
            streamlit_module.session_state["profile-data-section"] = secondary
    pending = streamlit_module.session_state.pop("profile_pending_section", None)
    if pending in PROFILE_SECTIONS:
        streamlit_module.session_state["profile-active-section"] = pending
    current = streamlit_module.session_state.get(
        "profile-active-section", "Reviewed profile"
    )
    section = streamlit_module.pills(
        "Career Profile sections",
        PROFILE_SECTIONS,
        default=current if current in PROFILE_SECTIONS else "Reviewed profile",
        key="profile-active-section",
    )
    active_section = section if section in PROFILE_SECTIONS else "Reviewed profile"
    if active_section == "Reviewed profile":
        editable_profile = _render_overview_v2(streamlit_module, dependencies, editable_profile)
    elif active_section == "Source résumé":
        editable_profile = _render_source_resume(
            streamlit_module, dependencies, editable_profile
        )
    elif active_section == "Advanced":
        editable_profile = _render_advanced(streamlit_module, dependencies, editable_profile)
    elif active_section == "Edit profile":
        pending_data = streamlit_module.session_state.pop("profile_data_pending_section", None)
        current_data = streamlit_module.session_state.get("profile-data-section", "Personal")
        if pending_data in PROFILE_DATA_SECTIONS:
            current_data = pending_data
            streamlit_module.session_state["profile-data-section"] = current_data
        data_section = streamlit_module.pills(
            "Profile data sections",
            PROFILE_DATA_SECTIONS,
            default=current_data if current_data in PROFILE_DATA_SECTIONS else "Personal",
            key="profile-data-section",
        )
        if editable_profile is None:
            streamlit_module.info("Create or load a profile before editing profile data.")
        else:
            def discard() -> None:
                streamlit_module.session_state["profile_editor_discard_pending"] = True

            render_profile_editor(
                streamlit_module,
                editable_profile,
                _EDITOR_SECTION_BY_PROFILE_DATA.get(data_section, "Personal information"),
                on_save=lambda edited: _persist_profile(streamlit_module, dependencies, edited),
                on_discard=discard,
            )
    profile_status = str(streamlit_module.session_state.get("profile_load_status", ""))
    if any(
        signal in profile_status.casefold()
        for signal in ("unavailable", "could not", "not found", "not saved", "repair")
    ):
        streamlit_module.warning(profile_status)


def render_profile_page(streamlit_module: Any, dependencies: ProfilePageDependencies) -> None:
    """Render Career Profile without taking ownership of repository or policy construction."""

    _render_profile_page_v2(streamlit_module, dependencies)


__all__ = ["PROFILE_SECTIONS", "ProfilePageDependencies", "render_profile_page"]
