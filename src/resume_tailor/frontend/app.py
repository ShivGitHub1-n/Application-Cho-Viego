"""Streamlit composition root for the Precision Workbench workspaces."""

from __future__ import annotations

import sqlite3
from collections.abc import MutableMapping
from typing import Any, cast

import streamlit as st

from resume_tailor.application.job_discovery.experience import JobsExperienceService
from resume_tailor.application.workflow_state import invalidate_derived_workflow
from resume_tailor.frontend.app_shell import render_application_shell
from resume_tailor.frontend.cover_letters_page import (
    CoverLettersDependencies,
    render_cover_letters_page,
)
from resume_tailor.frontend.jobs_page import render_jobs_page, render_jobs_unavailable
from resume_tailor.frontend.profile_page import ProfilePageDependencies, render_profile_page
from resume_tailor.frontend.resume_studio_page import (
    ResumeStudioDependencies,
    render_resume_studio_page,
)
from resume_tailor.frontend.routes import AppRoute, normalize_route
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
)
from resume_tailor.infrastructure.rendering import ManagedResumeRenderer


def create_jobs_experience(
    profile_repository: Any, *, services: Any | None = None
) -> JobsExperienceService:
    """Compose the existing Jobs delivery facade without duplicating its policy."""

    settings = Settings()
    resolved_services = services or create_job_discovery_services(settings)
    database = settings.app_data_directory / settings.profile_store_filename
    handoff = resolved_services.prepare_handoff
    if handoff is None:
        raise RuntimeError("Tailoring handoff is unavailable.")
    return JobsExperienceService(
        profiles=profile_repository,
        services=resolved_services,
        jobs=SQLiteDiscoveredJobRepository(database, initialize=False),
        handoff=handoff,
    )


def _clear_tailoring_state() -> None:
    invalidate_derived_workflow(cast(MutableMapping[str, object], st.session_state))


def _clear_cover_letter_state() -> None:
    for key in (
        "cover_letter",
        "cover_letter_reviewed",
        "cover_letter_profile_fingerprint",
        "cover_letter_posting_fingerprint",
        "cover_letter_plan_fingerprint",
        "cover_letter_evidence_fingerprint",
        "cover_letter_recipient_fingerprint",
        "cover_export_docx",
        "cover_export_status",
    ):
        st.session_state.pop(key, None)


def _active_profile(profile_repository: Any) -> Any | None:
    current = st.session_state.get("profile")
    requested = st.session_state.get("profile_id") or st.session_state.get("jobs_profile_id")
    requested_profile_id = str(requested).strip() if requested else ""
    if not requested_profile_id and getattr(current, "id", None):
        requested_profile_id = str(current.id)
    if not requested_profile_id:
        requested_profile_id = "local-profile"
    try:
        profile = profile_repository.get(requested_profile_id)
    except (ProfileStoreError, CorruptStoredProfileError):
        return None
    if (
        profile is None
        and current is not None
        and getattr(current, "id", None) == requested_profile_id
    ):
        profile = current
    if (
        profile is None
        and current is not None
        and getattr(current, "id", None) != requested_profile_id
    ):
        st.session_state.pop("profile", None)
    if profile is not None:
        previous_id = getattr(current, "id", None)
        previous_fingerprint = (
            current.model_dump_json() if hasattr(current, "model_dump_json") else None
        )
        next_fingerprint = (
            profile.model_dump_json() if hasattr(profile, "model_dump_json") else None
        )
        if current is not None and (
            previous_id != profile.id or previous_fingerprint != next_fingerprint
        ):
            _clear_tailoring_state()
        st.session_state["profile"] = profile
        st.session_state["profile_id"] = profile.id
        st.session_state["jobs_profile_id"] = profile.id
    return profile


def _render_application() -> None:
    st.set_page_config(page_title="Application Cho Viego", page_icon="📄", layout="wide")
    tailor_service = create_tailor_service()
    profile_repository = create_profile_repository()
    active_profile = _active_profile(profile_repository)
    active_route = normalize_route(
        render_application_shell(
            st,
            active_profile_label=getattr(active_profile, "display_name", None),
            active_profile_id=getattr(active_profile, "id", None)
            or st.session_state.get("jobs_profile_id")
            or st.session_state.get("profile_id"),
        )
    )
    if active_route is AppRoute.CAREER_PROFILE:
        render_profile_page(
            st,
            ProfilePageDependencies(
                profile_repository=profile_repository,
                tailor_service=tailor_service,
                invalidate_tailoring=_clear_tailoring_state,
            ),
        )
    elif active_route is AppRoute.JOBS:
        services = None
        try:
            services = create_job_discovery_services(Settings())
            render_jobs_page(
                create_jobs_experience(profile_repository, services=services)
            )
        except sqlite3.OperationalError:
            render_jobs_unavailable(st)
        finally:
            if services is not None:
                services.close()
    elif active_route is AppRoute.RESUME_STUDIO:
        render_resume_studio_page(
            st,
            ResumeStudioDependencies(
                tailor_service=tailor_service,
                resume_renderer=ManagedResumeRenderer(),
                invalidate_tailoring=_clear_tailoring_state,
            ),
        )
    else:
        render_cover_letters_page(
            st,
            CoverLettersDependencies(
                tailor_service=tailor_service,
                clear_cover_letter_state=_clear_cover_letter_state,
            ),
        )


_render_application()
