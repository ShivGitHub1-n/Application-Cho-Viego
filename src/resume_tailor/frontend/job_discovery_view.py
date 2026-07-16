from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, Protocol, cast

import streamlit as st

from resume_tailor.domain.job_discovery.models import (
    JobLevel,
    JobSearchPreferences,
    JobSearchPreferenceSuggestion,
    NormalizedLocation,
    WorkArrangement,
    WorkArrangementPreferenceMode,
)
from resume_tailor.domain.models import RoleFamily
from resume_tailor.application.job_discovery.presentation import (
    normalize_job_description_for_display,
)
from resume_tailor.application.job_discovery.queries import PreferencesNotFoundError
from resume_tailor.ports.job_discovery import PreferenceVersionConflictError


class JobDiscoveryDeliveryApi(Protocol):
    def list_reviewed_profiles(self) -> Sequence[Any]: ...

    def suggest_preferences(self, profile_id: str) -> JobSearchPreferenceSuggestion: ...

    def get_current_preferences(self, profile_id: str) -> JobSearchPreferences | None: ...

    def confirm_preferences(self, preferences: JobSearchPreferences) -> JobSearchPreferences: ...

    def refresh(self, profile_id: str) -> Any: ...

    def get_job(self, job_id: str) -> Any: ...

    def save_job(self, job_id: str) -> Any: ...

    def list_saved_jobs(self) -> Sequence[Any]: ...

    def check_saved_job_availability(self, saved_id: str) -> Any: ...


class ApplicationJobDiscoveryDeliveryApi:
    """Adapt the application service bundle to the thin Streamlit boundary."""

    def __init__(self, services: Any, profiles: Sequence[Any], jobs: Any) -> None:
        self._services = services
        self._profiles = tuple(profiles)
        self._jobs = jobs

    def list_reviewed_profiles(self) -> Sequence[Any]:
        return self._profiles

    def suggest_preferences(self, profile_id: str) -> JobSearchPreferenceSuggestion:
        return cast(
            JobSearchPreferenceSuggestion,
            self._services.suggest_preferences.suggest(
                "local-user", profile_id, generated_at=datetime.now(UTC)
            ),
        )

    def get_current_preferences(self, profile_id: str) -> JobSearchPreferences | None:
        if self._services.current_preferences is None:
            return None
        try:
            return cast(
                JobSearchPreferences,
                self._services.current_preferences.get("local-user", profile_id),
            )
        except PreferencesNotFoundError:
            return None

    def confirm_preferences(self, preferences: JobSearchPreferences) -> JobSearchPreferences:
        if self._services.confirm_preferences is None:
            raise RuntimeError("Preference confirmation is unavailable.")
        return cast(
            JobSearchPreferences,
            self._services.confirm_preferences.confirm(preferences),
        )

    def refresh(self, profile_id: str) -> Any:
        if self._services.current_preferences is None:
            raise RuntimeError("Job-search preferences are unavailable.")
        preferences = self._services.current_preferences.get("local-user", profile_id)
        run = self._services.refresh.refresh(
            "local-user", profile_id, preferences, started_at=datetime.now(UTC)
        )
        details = (
            self._services.runs.get(run.user_id, run.id)
            if self._services.runs is not None
            else None
        )
        return SimpleNamespace(
            run=details.run if details is not None else run,
            recommendations=details.recommendations if details is not None else [],
        )

    def get_job(self, job_id: str) -> Any:
        return self._jobs.get(job_id)

    def save_job(self, job_id: str) -> Any:
        if self._services.save is None:
            raise RuntimeError("Saved-job persistence is unavailable.")
        return self._services.save.save("local-user", job_id, saved_at=datetime.now(UTC))

    def list_saved_jobs(self) -> Sequence[Any]:
        if self._services.save is None:
            return []
        return cast(Sequence[Any], self._services.save.list("local-user"))

    def check_saved_job_availability(self, saved_id: str) -> Any:
        if self._services.check_saved_availability is None:
            raise RuntimeError("Saved-job availability is unavailable.")
        return self._services.check_saved_availability.check(
            "local-user", saved_id, checked_at=datetime.now(UTC)
        )


def render_job_discovery_view(
    api: JobDiscoveryDeliveryApi,
    *,
    streamlit_module: Any = st,
) -> None:
    """Render the job-discovery delivery flow through an injected API boundary."""

    streamlit_module.header("Job discovery")
    streamlit_module.caption(
        "Review your search intent, refresh supported-source recommendations, "
        "and save official posting snapshots."
    )

    profiles = list(api.list_reviewed_profiles())
    if not profiles:
        streamlit_module.warning("Select a reviewed profile before discovering jobs.")
        return
    profile_by_id = {_profile_id(profile): profile for profile in profiles}
    profile_ids = list(profile_by_id)
    preferred_profile_id = streamlit_module.session_state.get(
        "job_discovery_profile_id", profile_ids[0]
    )
    selected_index = (
        profile_ids.index(preferred_profile_id) if preferred_profile_id in profile_ids else 0
    )
    selected_profile_id = streamlit_module.selectbox(
        "Reviewed profile",
        profile_ids,
        index=selected_index,
    )
    streamlit_module.session_state["job_discovery_profile_id"] = selected_profile_id

    confirmed = api.get_current_preferences(selected_profile_id)
    confirmed_profile_id = _state_profile_id(
        streamlit_module, "job_discovery_confirmed_preferences"
    )
    if confirmed is not None:
        streamlit_module.session_state["job_discovery_confirmed_preferences"] = confirmed
    elif confirmed_profile_id is not None and confirmed_profile_id != selected_profile_id:
        streamlit_module.session_state.pop("job_discovery_confirmed_preferences", None)

    if (
        _state_profile_id(streamlit_module, "job_discovery_draft_preferences")
        != selected_profile_id
    ):
        streamlit_module.session_state.pop("job_discovery_draft_preferences", None)
    if _state_profile_id(streamlit_module, "job_discovery_suggestion") != selected_profile_id:
        streamlit_module.session_state.pop("job_discovery_suggestion", None)

    if streamlit_module.button("Suggest preferences"):
        suggestion = api.suggest_preferences(selected_profile_id)
        streamlit_module.session_state["job_discovery_suggestion"] = suggestion
        streamlit_module.session_state["job_discovery_draft_preferences"] = suggestion

    suggestion = streamlit_module.session_state.get("job_discovery_suggestion")
    draft = streamlit_module.session_state.get("job_discovery_draft_preferences")
    editor_source = (
        draft
        if _state_profile_id(streamlit_module, "job_discovery_draft_preferences")
        == selected_profile_id
        else suggestion
    )
    if editor_source is None:
        editor_source = confirmed
    if isinstance(editor_source, (JobSearchPreferences, JobSearchPreferenceSuggestion)):
        _render_preference_editor(api, editor_source, streamlit_module)

    _render_run(api, selected_profile_id, streamlit_module)
    _render_saved_jobs(api, streamlit_module)


def _render_preference_editor(
    api: JobDiscoveryDeliveryApi,
    source: JobSearchPreferences | JobSearchPreferenceSuggestion,
    streamlit_module: Any,
) -> None:
    streamlit_module.subheader("Review and confirm search preferences")
    role_family_values = [family.value for family in RoleFamily]
    selected_role_families = streamlit_module.multiselect(
        "Role families",
        role_family_values,
        default=[family.value for family in source.role_family_priority],
    )
    target_titles = _split_values(
        streamlit_module.text_area("Target titles", _join_values(source.target_titles))
    )
    related_titles = _split_values(
        streamlit_module.text_area(
            "Related title variants", _join_values(source.related_title_variants)
        )
    )
    technical_themes = _split_values(
        streamlit_module.text_area("Technical themes", _join_values(source.technical_themes))
    )
    career_interests = _split_values(
        streamlit_module.text_area("Career interests", _join_values(source.career_interests))
    )
    job_level_values = [level.value for level in JobLevel]
    selected_levels = streamlit_module.multiselect(
        "Job levels",
        job_level_values,
        default=[level.value for level in source.job_levels],
    )

    streamlit_module.write("Locations")
    location_count = int(
        streamlit_module.number_input(
            "Number of locations",
            value=max(1, len(source.locations)),
            min_value=1,
        )
    )
    locations: list[NormalizedLocation] = []
    for index in range(location_count):
        location = (
            source.locations[index]
            if index < len(source.locations)
            else NormalizedLocation()
        )
        city = streamlit_module.text_input(
            f"Location {index + 1} city", location.city or ""
        )
        region = streamlit_module.text_input(
            f"Location {index + 1} region", location.region or ""
        )
        country = streamlit_module.text_input(
            f"Location {index + 1} country",
            location.country_code or location.country_name or "",
        )
        locations.append(
            NormalizedLocation(
                city=city.strip() or None,
                region=region.strip() or None,
                country_code=country.strip().upper() or None,
                raw=", ".join(part for part in (city, region, country) if part.strip()),
                parseable=bool(city.strip() or region.strip() or country.strip()),
            )
        )
    arrangement = streamlit_module.selectbox(
        "Work arrangement",
        [value.value for value in WorkArrangement],
        index=_enum_index(WorkArrangement, source.work_arrangement),
    )
    arrangement_mode = streamlit_module.selectbox(
        "Work arrangement mode",
        [value.value for value in WorkArrangementPreferenceMode],
        index=_enum_index(WorkArrangementPreferenceMode, source.work_arrangement_mode),
    )
    preferred_companies = _split_values(
        streamlit_module.text_input(
            "Preferred companies", _join_values(source.preferred_companies)
        )
    )
    excluded_companies = _split_values(
        streamlit_module.text_input(
            "Excluded companies", _join_values(getattr(source, "excluded_companies", []))
        )
    )
    authorization = _split_values(
        streamlit_module.text_input(
            "Work-authorization constraints",
            _join_values(getattr(source, "work_authorization_constraints", [])),
        )
    )
    max_age = streamlit_module.number_input(
        "Maximum posting age (days)",
        value=getattr(source, "max_posting_age_days", 30) or 0,
        min_value=0,
    )

    preferences = JobSearchPreferences(
        user_id="local-user",
        profile_id=source.profile_id,
        version=1,
        role_family_priority=[RoleFamily(value) for value in selected_role_families],
        target_titles=target_titles,
        related_title_variants=related_titles,
        technical_themes=technical_themes,
        career_interests=career_interests,
        job_levels=[JobLevel(value) for value in selected_levels],
        locations=locations,
        work_arrangement=WorkArrangement(arrangement),
        work_arrangement_mode=WorkArrangementPreferenceMode(arrangement_mode),
        preferred_companies=preferred_companies,
        excluded_companies=excluded_companies,
        work_authorization_constraints=authorization,
        max_posting_age_days=int(max_age),
        created_at=getattr(source, "generated_at", None) or getattr(source, "created_at"),
        confirmed_at=None,
    )
    if streamlit_module.button("Confirm preferences"):
        try:
            confirmed = api.confirm_preferences(
                preferences.model_copy(update={"confirmed_at": datetime.now(UTC)})
            )
        except PreferenceVersionConflictError:
            streamlit_module.error(
                "These preferences conflict with a newer confirmed version. "
                "Please review the latest values and confirm again."
            )
        else:
            streamlit_module.session_state["job_discovery_confirmed_preferences"] = confirmed
            streamlit_module.success("Preferences confirmed. Refresh recommendations when ready.")
    streamlit_module.session_state["job_discovery_draft_preferences"] = preferences
    if isinstance(source, JobSearchPreferenceSuggestion) and source.rationale:
        streamlit_module.info("Suggestion rationale: " + " ".join(source.rationale))


def _render_run(api: JobDiscoveryDeliveryApi, profile_id: str, streamlit_module: Any) -> None:
    confirmed = streamlit_module.session_state.get("job_discovery_confirmed_preferences")
    if streamlit_module.button("Refresh recommendations"):
        if confirmed is None:
            streamlit_module.warning("Confirm preferences before refreshing recommendations.")
        else:
            result = api.refresh(profile_id)
            streamlit_module.session_state["job_discovery_run"] = _value(result, "run", result)
            streamlit_module.session_state["job_discovery_recommendations"] = list(
                _value(result, "recommendations", [])
            )

    run = streamlit_module.session_state.get("job_discovery_run")
    if run is None:
        return
    raw_status = _value(run, "status", "unknown")
    status_key = str(getattr(raw_status, "value", raw_status))
    status = _display_value(raw_status)
    streamlit_module.subheader("Discovery run")
    streamlit_module.info(f"Discovery run status: {status}")
    warnings = list(_value(run, "warnings", [])) + list(_value(run, "source_warnings", []))
    warnings += list(_value(run, "error_messages", []))
    for warning in warnings:
        streamlit_module.warning(str(warning))
    if status_key == "no_sources_configured":
        streamlit_module.warning("No approved job sources are configured")

    recommendations = list(streamlit_module.session_state.get("job_discovery_recommendations", []))
    grouped: dict[tuple[str, str], list[Any]] = {}
    for recommendation in recommendations[:10]:
        family = _display_value(_value(recommendation, "primary_role_family", "Other"))
        label = _match_label(_value(_value(recommendation, "score", None), "label", "provisional"))
        grouped.setdefault((family, label), []).append(recommendation)
    for (family, label), group in grouped.items():
        streamlit_module.subheader(f"{family} — {label}")
        for recommendation in group:
            _render_recommendation(api, recommendation, streamlit_module)


def _render_recommendation(
    api: JobDiscoveryDeliveryApi,
    recommendation: Any,
    streamlit_module: Any,
) -> None:
    job_id = str(_value(recommendation, "job_id", ""))
    job = _value(recommendation, "job", None) or api.get_job(job_id)
    title = _value(job, "title", job_id)
    company = _value(job, "company_name", "Unknown company")
    score = _value(_value(recommendation, "score", None), "total", 0.0)
    label = _match_label(_value(_value(recommendation, "score", None), "label", "provisional"))
    streamlit_module.write(f"{title} — {company}")
    streamlit_module.write(f"{float(score):.1f}% profile-fit score · {label}")
    streamlit_module.write(
        f"Source: {_value(_value(job, 'source', None), 'company_name', company)} · "
        f"Verification: {_display_value(_value(job, 'verification_status', 'unknown'))}"
    )
    location = _value(_value(job, "location", None), "raw", "")
    arrangement = _display_value(_value(job, "work_arrangement", "unknown"))
    if location:
        streamlit_module.write(f"Location: {location} · Arrangement: {arrangement}")
    if _value(_value(recommendation, "score", None), "provisional", False):
        streamlit_module.warning("Provisional result: important posting details need review.")
    for reason in _value(recommendation, "reasons", []):
        streamlit_module.write(f"Reason: {reason}")
    for gap in _value(recommendation, "gaps", []):
        streamlit_module.write(f"Material gap: {gap}")
    official_url = _value(job, "official_url", "")
    if official_url:
        streamlit_module.link_button("Open official posting", official_url)
    if streamlit_module.button(f"Save job {job_id}"):
        api.save_job(job_id)
        streamlit_module.success("Saved immutable posting snapshot.")


def _render_saved_jobs(api: JobDiscoveryDeliveryApi, streamlit_module: Any) -> None:
    saved_jobs = list(api.list_saved_jobs())
    updated_saved_jobs = {
        str(_value(saved, "id", "")): saved
        for saved in streamlit_module.session_state.get(
            "job_discovery_checked_saved_jobs", {}
        ).values()
    }
    streamlit_module.subheader("Saved jobs")
    if not saved_jobs:
        streamlit_module.info("No saved jobs yet.")
        return
    for saved in saved_jobs:
        saved = updated_saved_jobs.get(str(_value(saved, "id", "")), saved)
        snapshot = _value(saved, "posting_snapshot", None)
        title = _value(snapshot, "title", _value(saved, "job_id", "Saved job"))
        availability = _display_value(_value(saved, "availability", "unknown"))
        streamlit_module.write(f"{title} · Availability: {availability}")
        if availability == "unavailable":
            streamlit_module.warning("Unavailable saved snapshot retained.")
        description = _value(snapshot, "description", "Posting description unavailable.")
        streamlit_module.write(normalize_job_description_for_display(str(description)))
        official_url = _value(snapshot, "official_url", "")
        if official_url:
            streamlit_module.link_button("Open saved official posting", official_url)
        if streamlit_module.button(f"Check availability {_value(saved, 'id', '')}"):
            updated = api.check_saved_job_availability(str(_value(saved, "id", "")))
            streamlit_module.session_state.setdefault(
                "job_discovery_checked_saved_jobs", {}
            )[str(_value(saved, "id", ""))] = updated


def _profile_id(profile: Any) -> str:
    return str(_value(profile, "id", profile))


def _state_profile_id(streamlit_module: Any, key: str) -> str | None:
    value = streamlit_module.session_state.get(key)
    profile_id = _value(value, "profile_id", None)
    return str(profile_id) if profile_id is not None else None


def _value(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _display_value(value: Any) -> str:
    return str(getattr(value, "value", value)).replace("_", " ")


def _match_label(value: Any) -> str:
    labels = {
        "strong": "Strong Match",
        "good": "Good Match",
        "stretch": "Stretch",
        "provisional": "Provisional",
    }
    return labels.get(str(getattr(value, "value", value)), _display_value(value).title())


def _enum_index(enum_type: type[Any], value: Any) -> int:
    values = list(cast(Any, enum_type))
    actual = getattr(value, "value", value)
    return next((index for index, item in enumerate(values) if item.value == actual), 0)


def _split_values(value: str) -> list[str]:
    return [part.strip() for part in value.replace("\n", ",").split(",") if part.strip()]


def _join_values(values: Sequence[Any]) -> str:
    return ", ".join(str(getattr(value, "value", value)) for value in values)


__all__ = ["JobDiscoveryDeliveryApi", "render_job_discovery_view"]
