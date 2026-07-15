from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel

from resume_tailor.api.dependencies import (
    JobDiscoveryServiceBundle,
    get_job_discovery_services,
)
from resume_tailor.application.job_discovery.preferences import ProfileNotFoundError
from resume_tailor.application.job_discovery.queries import (
    DiscoveryRunNotFoundError,
    PreferencesNotFoundError,
)
from resume_tailor.application.job_discovery.saved import (
    DiscoveredJobNotFoundError,
    SavedJobNotFoundError,
)
from resume_tailor.domain.job_discovery.models import (
    DiscoveryRun,
    JobRecommendation,
    JobSearchPreferences,
    JobSearchPreferenceSuggestion,
    SavedJob,
)
from resume_tailor.ports.job_discovery import PreferenceVersionConflictError


class SuggestPreferencesRequest(BaseModel):
    profile_id: str
    user_id: str = "local-user"


class ConfirmPreferencesRequest(JobSearchPreferences):
    pass


class RefreshDiscoveryRequest(BaseModel):
    profile_id: str
    user_id: str = "local-user"


class RefreshDiscoveryResponse(BaseModel):
    run: DiscoveryRun
    recommendations: list[JobRecommendation]


class PreferencesSuggestionResponse(BaseModel):
    suggestion: JobSearchPreferenceSuggestion


class ConfirmPreferencesResponse(BaseModel):
    preferences: JobSearchPreferences


class SaveJobRequest(BaseModel):
    job_id: str


class SavedJobResponse(BaseModel):
    saved_job: SavedJob


class SavedJobsResponse(BaseModel):
    saved_jobs: list[SavedJob]


class AvailabilityResponse(BaseModel):
    saved_job: SavedJob


router = APIRouter(prefix="/job-discovery", tags=["job-discovery"])


@router.post(
    "/preferences/suggest",
    response_model=PreferencesSuggestionResponse,
)
def suggest_preferences(
    request: SuggestPreferencesRequest,
    services: JobDiscoveryServiceBundle = Depends(get_job_discovery_services),  # noqa: B008
) -> PreferencesSuggestionResponse:
    try:
        try:
            suggestion = services.suggest_preferences.suggest(
                request.user_id,
                request.profile_id,
                generated_at=datetime.now(UTC),
            )
        except ProfileNotFoundError as error:
            raise HTTPException(status_code=404, detail="Profile was not found.") from error
        return PreferencesSuggestionResponse(suggestion=suggestion)
    finally:
        services.close()


@router.post(
    "/preferences/confirm",
    response_model=ConfirmPreferencesResponse,
)
def confirm_preferences(
    request: ConfirmPreferencesRequest,
    services: JobDiscoveryServiceBundle = Depends(get_job_discovery_services),  # noqa: B008
) -> ConfirmPreferencesResponse:
    if services.confirm_preferences is None:
        raise HTTPException(status_code=503, detail="Preference confirmation is unavailable.")
    try:
        try:
            preferences = services.confirm_preferences.confirm(request)
        except ProfileNotFoundError as error:
            raise HTTPException(status_code=404, detail="Profile was not found.") from error
        except PreferenceVersionConflictError as error:
            raise HTTPException(
                status_code=409,
                detail="That preference version already contains different data.",
            ) from error
        return ConfirmPreferencesResponse(preferences=preferences)
    finally:
        services.close()


@router.post(
    "/refresh",
    response_model=RefreshDiscoveryResponse,
)
def refresh_discovery(
    request: RefreshDiscoveryRequest,
    services: JobDiscoveryServiceBundle = Depends(get_job_discovery_services),  # noqa: B008
) -> RefreshDiscoveryResponse:
    if services.current_preferences is None:
        raise HTTPException(status_code=503, detail="Job-search preferences are unavailable.")
    try:
        try:
            preferences = services.current_preferences.get(request.user_id, request.profile_id)
            run = services.refresh.refresh(
                request.user_id,
                request.profile_id,
                preferences,
                started_at=datetime.now(UTC),
            )
        except ProfileNotFoundError as error:
            raise HTTPException(status_code=404, detail="Profile was not found.") from error
        except PreferencesNotFoundError as error:
            raise HTTPException(status_code=404, detail="Preferences were not found.") from error
        if services.runs is None:
            return RefreshDiscoveryResponse(run=run, recommendations=[])
        details = services.runs.get(request.user_id, run.id)
        if details is None or isinstance(details, DiscoveryRun):
            return RefreshDiscoveryResponse(run=run, recommendations=[])
        return RefreshDiscoveryResponse(
            run=details.run,
            recommendations=details.recommendations,
        )
    finally:
        services.close()


@router.get(
    "/runs/{run_id}",
    response_model=RefreshDiscoveryResponse,
)
def get_discovery_run(
    run_id: str = Path(min_length=1),
    user_id: str = Query(default="local-user", min_length=1),
    services: JobDiscoveryServiceBundle = Depends(get_job_discovery_services),  # noqa: B008
) -> RefreshDiscoveryResponse:
    if services.runs is None:
        raise HTTPException(status_code=503, detail="Discovery run retrieval is unavailable.")
    try:
        try:
            details = services.runs.get(user_id, run_id)
        except DiscoveryRunNotFoundError as error:
            raise HTTPException(status_code=404, detail="Discovery run was not found.") from error
        if details is None:
            raise HTTPException(status_code=404, detail="Discovery run was not found.")
        if isinstance(details, DiscoveryRun):
            return RefreshDiscoveryResponse(run=details, recommendations=[])
        return RefreshDiscoveryResponse(
            run=details.run,
            recommendations=details.recommendations,
        )
    finally:
        services.close()


@router.post("/saved", response_model=SavedJobResponse)
def save_job(
    request: SaveJobRequest,
    services: JobDiscoveryServiceBundle = Depends(get_job_discovery_services),  # noqa: B008
) -> SavedJobResponse:
    if services.save is None:
        raise HTTPException(status_code=503, detail="Saved-job persistence is unavailable.")
    try:
        try:
            saved = services.save.save(
                "local-user",
                request.job_id,
                saved_at=datetime.now(UTC),
            )
        except DiscoveredJobNotFoundError as error:
            raise HTTPException(status_code=404, detail="Discovered job was not found.") from error
        return SavedJobResponse(saved_job=saved)
    finally:
        services.close()


@router.get("/saved", response_model=SavedJobsResponse)
def list_saved_jobs(
    services: JobDiscoveryServiceBundle = Depends(get_job_discovery_services),  # noqa: B008
) -> SavedJobsResponse:
    if services.save is None:
        raise HTTPException(status_code=503, detail="Saved-job persistence is unavailable.")
    try:
        return SavedJobsResponse(saved_jobs=services.save.list("local-user"))
    finally:
        services.close()


@router.post("/saved/{saved_id}/availability", response_model=AvailabilityResponse)
def check_saved_job_availability(
    saved_id: str = Path(min_length=1),
    services: JobDiscoveryServiceBundle = Depends(get_job_discovery_services),  # noqa: B008
) -> AvailabilityResponse:
    if services.check_saved_availability is None:
        raise HTTPException(status_code=503, detail="Saved-job availability is unavailable.")
    try:
        try:
            saved = services.check_saved_availability.check(
                "local-user",
                saved_id,
                checked_at=datetime.now(UTC),
            )
        except SavedJobNotFoundError as error:
            raise HTTPException(status_code=404, detail="Saved job was not found.") from error
        return AvailabilityResponse(saved_job=saved)
    finally:
        services.close()


__all__ = [
    "AvailabilityResponse",
    "ConfirmPreferencesRequest",
    "ConfirmPreferencesResponse",
    "JobDiscoveryServiceBundle",
    "PreferencesSuggestionResponse",
    "RefreshDiscoveryRequest",
    "RefreshDiscoveryResponse",
    "SaveJobRequest",
    "SavedJobResponse",
    "SavedJobsResponse",
    "get_discovery_run",
    "check_saved_job_availability",
    "list_saved_jobs",
    "refresh_discovery",
    "router",
    "save_job",
    "suggest_preferences",
]
