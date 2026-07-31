from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, cast

from resume_tailor.domain.job_discovery.models import (
    JobLevel,
    JobSearchPreferences,
    JobSearchPreferenceSuggestion,
    NormalizedLocation,
    WorkArrangement,
    WorkArrangementPreferenceMode,
)
from resume_tailor.domain.models import RoleFamily
from resume_tailor.ports.job_discovery import PreferenceVersionConflictError


def render_preferences(
    experience: Any,
    profile_id: str,
    *,
    streamlit_module: Any,
) -> None:
    streamlit_module.subheader("Preferences")
    streamlit_module.caption(
        "Keep required constraints, preferred signals, acceptable alternatives, "
        "and exclusions explicit."
    )
    confirmed = experience.get_preferences(profile_id)
    suggestion = streamlit_module.session_state.get("jobs_preference_suggestion")
    if streamlit_module.button("Suggest preferences", key="jobs-suggest-preferences"):
        suggestion = experience.suggest_preferences(profile_id)
        streamlit_module.session_state["jobs_preference_suggestion"] = suggestion
        streamlit_module.session_state["jobs_preference_draft"] = suggestion
    if suggestion is not None:
        rationale = " ".join(getattr(suggestion, "rationale", []))
        with streamlit_module.container(border=True, key="jobs-preference-suggestion"):
            streamlit_module.markdown("**Suggested preferences**")
            streamlit_module.info(
                "Suggestions are editable and are not persisted until confirmed."
                + (f" Rationale: {rationale}" if rationale else "")
            )

    if confirmed is not None:
        with streamlit_module.container(border=True, key="jobs-preference-confirmed"):
            streamlit_module.success(f"Confirmed preferences · version {confirmed.version}")
            streamlit_module.caption(
                "These values are the current source for Tailored recommendations."
            )

    source = streamlit_module.session_state.get("jobs_preference_draft") or confirmed or suggestion
    if source is None:
        with streamlit_module.container(border=True, key="jobs-preference-empty"):
            streamlit_module.subheader("No confirmed preferences yet")
            streamlit_module.write(
                "Suggest or edit preferences, then confirm them before refreshing Tailored jobs."
            )
        return

    draft = _render_editor(source, profile_id, streamlit_module)
    streamlit_module.session_state["jobs_preference_draft"] = draft
    with streamlit_module.container(key="jobs-preference-actions"):
        if streamlit_module.button(
            "Confirm preferences",
            key="jobs-confirm-preferences",
            type="primary",
            width="content",
        ):
            try:
                saved = experience.confirm_preferences(
                    draft.model_copy(update={"confirmed_at": datetime.now(UTC)})
                )
            except PreferenceVersionConflictError:
                streamlit_module.error(
                    "These preferences conflict with a newer confirmed version. "
                    "Review the latest values and confirm again."
                )
            else:
                streamlit_module.session_state["jobs_confirmed_preferences"] = saved
                streamlit_module.session_state["jobs_preference_draft"] = saved
                streamlit_module.success(f"Preferences confirmed · version {saved.version}")


def _render_editor(
    source: JobSearchPreferences | JobSearchPreferenceSuggestion,
    profile_id: str,
    streamlit_module: Any,
) -> JobSearchPreferences:
    with streamlit_module.container(key="jobs-preference-editor"):
        left, right = streamlit_module.columns([1, 1], gap="large")
        with left:
            with streamlit_module.container(border=True, key="jobs-preference-role-direction"):
                streamlit_module.markdown("**Role direction**")
                streamlit_module.caption("What kinds of roles should lead the feed?")
                roles = streamlit_module.multiselect(
                    "Role-family priorities",
                    [item.value for item in RoleFamily],
                    default=[item.value for item in getattr(source, "role_family_priority", [])],
                    key="jobs-pref-role-families",
                )
                titles = streamlit_module.text_area(
                    "Target titles",
                    _join(getattr(source, "target_titles", [])),
                    key="jobs-pref-target-titles",
                )
                related = streamlit_module.text_area(
                    "Related title variants",
                    _join(getattr(source, "related_title_variants", [])),
                    key="jobs-pref-related-titles",
                )
            with streamlit_module.container(border=True, key="jobs-preference-skills"):
                streamlit_module.markdown("**Skills and interests**")
                streamlit_module.caption(
                    "Signals that are preferred, not automatically hard eligibility rules."
                )
                themes = streamlit_module.text_area(
                    "Technical themes",
                    _join(getattr(source, "technical_themes", [])),
                    key="jobs-pref-themes",
                )
                interests = streamlit_module.text_area(
                    "Career interests",
                    _join(getattr(source, "career_interests", [])),
                    key="jobs-pref-interests",
                )
        with right:
            with streamlit_module.container(border=True, key="jobs-preference-constraints"):
                streamlit_module.markdown("**Work constraints**")
                streamlit_module.caption(
                    "Required, preferred, acceptable, and excluded conditions."
                )
                levels = streamlit_module.multiselect(
                    "Job levels",
                    [item.value for item in JobLevel],
                    default=[item.value for item in getattr(source, "job_levels", [])],
                    key="jobs-pref-levels",
                )
                location_text = streamlit_module.text_input(
                    "Locations (one per line or comma-separated)",
                    _join(getattr(source, "locations", [])),
                    key="jobs-pref-locations",
                )
                arrangement = streamlit_module.selectbox(
                    "Work arrangement",
                    [item.value for item in WorkArrangement],
                    index=_index(
                        WorkArrangement,
                        getattr(source, "work_arrangement", WorkArrangement.UNKNOWN),
                    ),
                    key="jobs-pref-arrangement",
                )
                arrangement_mode = streamlit_module.selectbox(
                    "Preference mode",
                    [item.value for item in WorkArrangementPreferenceMode],
                    index=_index(
                        WorkArrangementPreferenceMode,
                        getattr(
                            source,
                            "work_arrangement_mode",
                            WorkArrangementPreferenceMode.PREFERRED,
                        ),
                    ),
                    key="jobs-pref-arrangement-mode",
                )
                max_age = streamlit_module.number_input(
                    "Maximum posting age (days)",
                    value=int(getattr(source, "max_posting_age_days", 30) or 0),
                    min_value=0,
                    key="jobs-pref-max-age",
                )
            with streamlit_module.container(border=True, key="jobs-preference-companies"):
                streamlit_module.markdown("**Companies and authorization**")
                streamlit_module.caption("Preferred signals and explicit exclusions.")
                preferred = streamlit_module.text_input(
                    "Preferred companies",
                    _join(getattr(source, "preferred_companies", [])),
                    key="jobs-pref-preferred-companies",
                )
                excluded = streamlit_module.text_input(
                    "Excluded companies",
                    _join(getattr(source, "excluded_companies", [])),
                    key="jobs-pref-excluded-companies",
                )
                authorization = streamlit_module.text_input(
                    "Work-authorization constraints",
                    _join(getattr(source, "work_authorization_constraints", [])),
                    key="jobs-pref-authorization",
                )

    locations = [_location(value) for value in _split(location_text)]
    created_at = (
        getattr(source, "generated_at", None)
        or getattr(source, "created_at", None)
        or datetime.now(UTC)
    )
    return JobSearchPreferences(
        user_id="local-user",
        profile_id=profile_id,
        version=int(getattr(source, "version", 1)),
        role_family_priority=[RoleFamily(value) for value in roles],
        target_titles=_split(titles),
        related_title_variants=_split(related),
        technical_themes=_split(themes),
        career_interests=_split(interests),
        job_levels=[JobLevel(value) for value in levels],
        locations=locations,
        work_arrangement=WorkArrangement(arrangement),
        work_arrangement_mode=WorkArrangementPreferenceMode(arrangement_mode),
        preferred_companies=_split(preferred),
        excluded_companies=_split(excluded),
        work_authorization_constraints=_split(authorization),
        max_posting_age_days=int(max_age),
        created_at=created_at,
        confirmed_at=getattr(source, "confirmed_at", None),
    )


def _location(value: str) -> NormalizedLocation:
    parts = [part.strip() for part in value.split(",") if part.strip()]
    return NormalizedLocation(raw=value, city=parts[0] if parts else None, parseable=bool(parts))


def _index(enum_type: type[Any], value: Any) -> int:
    actual = getattr(value, "value", value)
    items = cast(Iterable[Any], enum_type)
    return next((index for index, item in enumerate(items) if item.value == actual), 0)


def _split(value: str) -> list[str]:
    return [part.strip() for part in value.replace("\n", ",").split(",") if part.strip()]


def _join(values: Any) -> str:
    return ", ".join(
        str(getattr(value, "raw", getattr(value, "value", value))) for value in values
    )


__all__ = ["render_preferences"]
