from __future__ import annotations

from typing import Any

from resume_tailor.application.job_discovery.presentation import (
    normalize_job_description_for_display,
)


def render_saved_jobs(experience: Any, profile_id: str, *, streamlit_module: Any) -> None:
    streamlit_module.subheader("Saved")
    streamlit_module.caption(
        "Immutable snapshots stay available for review even when a live posting changes "
        "or disappears."
    )
    saved_jobs = experience.list_saved_jobs(profile_id)
    if not saved_jobs:
        with streamlit_module.container(border=True, key="jobs-saved-empty"):
            streamlit_module.subheader("No saved jobs yet")
            streamlit_module.write(
                "Save a recommendation to keep its official posting snapshot here."
            )
        return

    checked = streamlit_module.session_state.get("jobs_checked_saved_jobs", {})
    saved_by_id = {saved.saved_id: checked.get(saved.saved_id, saved) for saved in saved_jobs}
    selected_id = streamlit_module.session_state.get("jobs_saved_selected_id")
    if selected_id not in saved_by_id:
        selected_id = next(iter(saved_by_id))
    streamlit_module.session_state["jobs_saved_selected_id"] = selected_id

    left, right = streamlit_module.columns([0.38, 0.62], gap="large")
    with left:
        streamlit_module.subheader(f"Saved snapshots · {len(saved_jobs)}")
        for saved in saved_by_id.values():
            _render_saved_card(
                saved, selected=saved.saved_id == selected_id, streamlit_module=streamlit_module
            )
    with right:
        _render_saved_detail(saved_by_id[selected_id], profile_id, experience, streamlit_module)


def _render_saved_card(saved: Any, *, selected: bool, streamlit_module: Any) -> None:
    with streamlit_module.container(
        border=True, key=f"jobs-saved-card-{_safe_key(saved.saved_id)}"
    ):
        streamlit_module.markdown(f"**{saved.title}**")
        streamlit_module.caption(saved.company)
        streamlit_module.caption(
            f"{saved.location_label} · {saved.work_arrangement.value.title()} · "
            f"Saved {saved.saved_at.strftime('%b %d, %Y')}"
        )
        streamlit_module.caption(f"Availability: {saved.availability.title()}")
        if selected:
            streamlit_module.markdown(
                '<span class="jobs-saved-selected-marker" aria-hidden="true"></span>'
                '<span class="jobs-selected-label">Selected</span>',
                unsafe_allow_html=True,
            )
        elif streamlit_module.button(
            "View snapshot",
            key=f"jobs-select-saved-{saved.saved_id}",
            type="tertiary",
            width="content",
        ):
            streamlit_module.session_state["jobs_saved_selected_id"] = saved.saved_id


def _render_saved_detail(
    saved: Any, profile_id: str, experience: Any, streamlit_module: Any
) -> None:
    with streamlit_module.container(border=True, key="jobs-saved-detail-panel"):
        streamlit_module.caption("Saved immutable snapshot")
        streamlit_module.subheader(saved.title)
        streamlit_module.caption(saved.company)
        streamlit_module.caption(
            f"{saved.location_label} · {saved.work_arrangement.value.title()} · "
            f"Saved {saved.saved_at.strftime('%b %d, %Y')}"
        )
        streamlit_module.caption(f"Availability: {saved.availability.title()}")
        if saved.checked_at:
            streamlit_module.caption(f"Last checked {saved.checked_at.strftime('%b %d, %Y')}")
        streamlit_module.caption(f"Source: {saved.source_id}")
        if saved.availability == "unavailable":
            streamlit_module.warning("Unavailable posting retained as an immutable snapshot.")
        with streamlit_module.container(key="jobs-saved-action-row"):
            actions = streamlit_module.columns(3, gap="small")
            with actions[0]:
                if saved.official_url:
                    streamlit_module.link_button(
                        "Open saved official posting",
                        saved.official_url,
                        type="primary",
                        width="content",
                    )
                else:
                    streamlit_module.caption("Official posting link unavailable.")
            with actions[1]:
                if streamlit_module.button(
                    "Check availability", key=f"jobs-check-{saved.saved_id}", width="content"
                ):
                    try:
                        checked = experience.check_saved_job_availability(
                            saved.saved_id, profile_id
                        )
                    except Exception:
                        streamlit_module.warning(
                            "Availability could not be checked. The saved snapshot was preserved."
                        )
                    else:
                        streamlit_module.session_state.setdefault("jobs_checked_saved_jobs", {})[
                            saved.saved_id
                        ] = checked
                        streamlit_module.success(
                            f"Availability checked: {checked.availability.title()}"
                        )
            with actions[2]:
                if streamlit_module.button(
                    "Tailor resume from snapshot",
                    key=f"jobs-tailor-saved-{saved.saved_id}",
                    width="content",
                ):
                    handoff = experience.prepare_saved_tailoring(saved.saved_id, profile_id)
                    from resume_tailor.frontend.jobs_page import apply_tailoring_handoff

                    apply_tailoring_handoff(streamlit_module.session_state, handoff)
                    streamlit_module.rerun()
        streamlit_module.divider()
        streamlit_module.markdown("#### Snapshot description")
        streamlit_module.write(normalize_job_description_for_display(saved.description))


def _safe_key(value: str) -> str:
    return "".join(
        character if character.isalnum() or character in "-_" else "-" for character in value
    )


__all__ = ["render_saved_jobs"]
