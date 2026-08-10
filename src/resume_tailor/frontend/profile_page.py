"""Career Profile workspace backed by the existing master-profile authority."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
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
    "Overview",
    "Profile data",
    "Evidence",
    "Import résumé",
    "Advanced",
)
PROFILE_DATA_SECTIONS = ("Personal", "Education", "Experiences", "Projects", "Skills")
_EDITOR_SECTION_BY_PROFILE_DATA = {
    "Personal": "Personal information",
    "Education": "Education",
    "Experiences": "Experiences",
    "Projects": "Projects",
    "Skills": "Skills",
}
_LEGACY_SECTION_MAP = {
    "Personal information": ("Profile data", "Personal"),
    "Education": ("Profile data", "Education"),
    "Experiences": ("Profile data", "Experiences"),
    "Projects": ("Profile data", "Projects"),
    "Skills": ("Profile data", "Skills"),
    "Evidence library": ("Evidence", None),
    "Import": ("Import résumé", None),
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
                profile_id.strip() or "local-profile", extracted.source_format, extracted.text
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
    labels = {item.id: f"{item.display_name} — {item.id}" for item in profiles}
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


def _render_overview_v2(
    streamlit_module: Any, dependencies: ProfilePageDependencies, profile: MasterProfile | None
) -> MasterProfile | None:
    streamlit_module.subheader("Profile overview")
    streamlit_module.caption(
        "This reviewed profile is the source of truth for Jobs, Resume Studio, and Cover Letters."
    )
    if profile is None:
        streamlit_module.info(
            "Import a résumé, create a profile manually, or load a reviewed profile to begin."
        )
        actions = streamlit_module.columns(3)
        with actions[0]:
            if streamlit_module.button(
                "Import a résumé", key="profile-onboard-import", type="primary"
            ):
                streamlit_module.session_state["profile_pending_section"] = "Import résumé"
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
                streamlit_module.session_state["profile_pending_section"] = "Profile data"
                streamlit_module.session_state["profile_data_pending_section"] = "Personal"
                streamlit_module.rerun()
        with actions[2]:
            if streamlit_module.button(
                "Load an existing reviewed profile", key="profile-onboard-load"
            ):
                streamlit_module.session_state["profile_selector_focus"] = True
                streamlit_module.session_state["profile_pending_section"] = "Overview"
                streamlit_module.rerun()
        _render_reviewed_profile_selector(streamlit_module, dependencies, None)
        return None
    streamlit_module.markdown(
        f"**{profile.display_name}** · `{profile.id}` · version {profile.version}"
    )
    columns = streamlit_module.columns(5)
    values = (
        ("Education", len(profile.education)),
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
    try:
        profiles = list(dependencies.profile_repository.list_all())
    except (ProfileStoreError, CorruptStoredProfileError, ValueError) as error:
        streamlit_module.error(f"Reviewed profiles could not be listed: {error}")
        profiles = []
    if profiles:
        ids = [item.id for item in profiles]
        labels = {item.id: f"{item.display_name} — {item.id}" for item in profiles}
        selected = streamlit_module.selectbox(
            "Reviewed profile",
            ids,
            index=ids.index(profile.id) if profile is not None and profile.id in ids else 0,
            format_func=lambda value: labels[value],
            key="profile-reviewed-selector",
        )
        if streamlit_module.button(
            "Load selected profile", key="profile-reviewed-load", type="primary"
        ):
            _load_existing_profile(streamlit_module, dependencies, selected)
            streamlit_module.rerun()
    else:
        streamlit_module.info("No reviewed profiles are available yet.")
    buttons = streamlit_module.columns(2)
    with buttons[0]:
        if streamlit_module.button("Edit profile", key="profile-edit-action", type="primary"):
            streamlit_module.session_state["profile_pending_section"] = "Profile data"
            streamlit_module.session_state["profile_data_pending_section"] = "Personal"
            streamlit_module.rerun()
    with buttons[1]:
        if streamlit_module.button("Import a newer résumé", key="profile-import-action"):
            streamlit_module.session_state["profile_pending_section"] = "Import résumé"
            streamlit_module.rerun()
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
    current = streamlit_module.session_state.get("profile-active-section", "Overview")
    section = streamlit_module.pills(
        "Career Profile sections",
        PROFILE_SECTIONS,
        default=current if current in PROFILE_SECTIONS else "Overview",
        key="profile-active-section",
    )
    active_section = section if section in PROFILE_SECTIONS else "Overview"
    if active_section == "Overview":
        editable_profile = _render_overview_v2(streamlit_module, dependencies, editable_profile)
    elif active_section == "Import résumé":
        editable_profile = _render_import(streamlit_module, dependencies, editable_profile)
    elif active_section == "Advanced":
        editable_profile = _render_advanced(streamlit_module, dependencies, editable_profile)
    elif active_section == "Evidence":
        if editable_profile is None:
            streamlit_module.info("Load or import a profile before reviewing evidence.")
        else:
            render_profile_editor(
                streamlit_module,
                editable_profile,
                "Evidence library",
                on_save=lambda edited: _persist_profile(streamlit_module, dependencies, edited),
                on_discard=lambda: streamlit_module.session_state.__setitem__(
                    "profile_editor_discard_pending", True
                ),
            )
    elif active_section == "Profile data":
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
    streamlit_module.caption(
        streamlit_module.session_state.get("profile_load_status", "Profile not loaded.")
    )


def render_profile_page(streamlit_module: Any, dependencies: ProfilePageDependencies) -> None:
    """Render Career Profile without taking ownership of repository or policy construction."""

    return _render_profile_page_v2(streamlit_module, dependencies)
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
            streamlit_module,
            editable_profile,
            expected_source_key,
            force=discard_pending,
        )
    render_page_header(
        streamlit_module,
        "Career Profile",
        "Reviewed source of truth for tailored jobs and evidence-backed documents.",
    )
    section = streamlit_module.pills(
        "Career Profile sections",
        PROFILE_SECTIONS,
        default=streamlit_module.session_state.get("profile-active-section", "Overview"),
        key="profile-active-section",
    )
    active_section = section if section in PROFILE_SECTIONS else "Overview"
    if active_section == "Overview":
        editable_profile = _render_overview(streamlit_module, dependencies, editable_profile)
    elif active_section == "Import":
        editable_profile = _render_import(streamlit_module, dependencies, editable_profile)
    elif active_section == "Advanced":
        editable_profile = _render_advanced(streamlit_module, dependencies, editable_profile)
    elif editable_profile is None:
        streamlit_module.info("Load or import a profile before editing this section.")
    else:

        def discard() -> None:
            streamlit_module.session_state["profile_editor_discard_pending"] = True

        render_profile_editor(
            streamlit_module,
            editable_profile,
            active_section,
            on_save=lambda edited: _persist_profile(streamlit_module, dependencies, edited),
            on_discard=discard,
        )
    streamlit_module.caption(
        streamlit_module.session_state.get("profile_load_status", "Profile not loaded.")
    )


__all__ = ["PROFILE_SECTIONS", "ProfilePageDependencies", "render_profile_page"]
