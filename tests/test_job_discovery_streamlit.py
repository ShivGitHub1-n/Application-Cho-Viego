from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from resume_tailor.domain.job_discovery.models import (
    DiscoveryRunStatus,
    JobLevel,
    JobSearchPreferences,
    JobSearchPreferenceSuggestion,
    MatchLabel,
    NormalizedLocation,
    SavedJobAvailability,
    WorkArrangement,
    WorkArrangementPreferenceMode,
)
from resume_tailor.domain.models import RoleFamily
from resume_tailor.frontend.job_discovery_view import render_job_discovery_view
from resume_tailor.ports.job_discovery import PreferenceVersionConflictError

WHEN = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


class FakeStreamlit:
    def __init__(self, clicked: set[str] | None = None) -> None:
        self.clicked = clicked or set()
        self.session_state: dict[str, object] = {}
        self.text: list[str] = []
        self.input_values: dict[str, object] = {}
        self.selected_profile = "p1"

    def _record(self, value: object) -> None:
        self.text.append(str(value))

    def title(self, value): self._record(value)
    def caption(self, value): self._record(value)
    def header(self, value): self._record(value)
    def subheader(self, value): self._record(value)
    def info(self, value): self._record(value)
    def warning(self, value): self._record(value)
    def error(self, value): self._record(value)
    def success(self, value): self._record(value)
    def markdown(self, value): self._record(value)
    def write(self, value): self._record(value)
    def divider(self): pass

    def button(self, label, **kwargs):
        self._record(label)
        return label in self.clicked

    def selectbox(self, label, options, index=0, **kwargs):
        self._record(label)
        if label == "Reviewed profile" and self.selected_profile in options:
            return self.selected_profile
        return options[index] if options else None

    def text_input(self, label, value="", **kwargs):
        self._record(label)
        self.input_values[label] = value
        return value

    def text_area(self, label, value="", **kwargs):
        self._record(label)
        self.input_values[label] = value
        return value

    def multiselect(self, label, options, default=None, **kwargs):
        self._record(label)
        return list(default or [])

    def number_input(self, label, value=0, **kwargs):
        self._record(label)
        return value

    @contextmanager
    def expander(self, label, **kwargs):
        self._record(label)
        yield self

    def link_button(self, label, url, **kwargs):
        self._record(label)
        self._record(url)


class FakeApi:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.suggestion = JobSearchPreferenceSuggestion(
            profile_id="p1",
            generated_at=WHEN,
            role_family_priority=[RoleFamily.SOFTWARE_DATA_ENGINEERING],
            target_titles=["Software Engineer"],
            related_title_variants=["Backend Engineer"],
            technical_themes=["Python"],
            career_interests=["Developer tools"],
            job_levels=[JobLevel.ENTRY],
            locations=[NormalizedLocation(city="Toronto", region="ON", country_code="CA")],
            work_arrangement=WorkArrangement.HYBRID,
            work_arrangement_mode=WorkArrangementPreferenceMode.PREFERRED,
            preferred_companies=["Example"],
            rationale=["Role-family evidence was reviewed."],
        )
        self.refresh_result = SimpleNamespace(
            run=SimpleNamespace(
                status=DiscoveryRunStatus.NO_SOURCES_CONFIGURED,
                warnings=[],
                source_warnings=[],
                error_messages=[],
            ),
            recommendations=[],
        )
        self.saved_jobs = []
        self.current_preferences: JobSearchPreferences | None = None

    def list_reviewed_profiles(self):
        return [SimpleNamespace(id="p1", display_name="Reviewed Candidate")]

    def suggest_preferences(self, profile_id):
        self.calls.append(("suggest", profile_id))
        return self.suggestion

    def get_current_preferences(self, profile_id):
        if (
            self.current_preferences is not None
            and self.current_preferences.profile_id == profile_id
        ):
            return self.current_preferences
        return None

    def confirm_preferences(self, preferences):
        self.calls.append(("confirm", preferences))
        self.current_preferences = preferences
        return preferences

    def refresh(self, profile_id):
        self.calls.append(("refresh", profile_id))
        return self.refresh_result

    def get_job(self, job_id):
        return SimpleNamespace(
            id=job_id,
            title="Software Engineer",
            company_name="Example",
            official_url="https://boards.greenhouse.io/example/jobs/123",
            source=SimpleNamespace(company_name="Example", connector_type="greenhouse"),
            verification_status="verified_active",
            location=SimpleNamespace(raw="Toronto, ON, Canada"),
            work_arrangement="hybrid",
        )

    def save_job(self, job_id):
        self.calls.append(("save", job_id))

    def list_saved_jobs(self):
        self.calls.append(("list_saved", None))
        return self.saved_jobs

    def check_saved_job_availability(self, saved_id):
        self.calls.append(("check", saved_id))
        return self.saved_jobs[0]


def _confirmed_preferences(api: FakeApi, *, profile_id: str = "p1", titles=None):
    suggestion = api.suggestion.model_copy(update={"profile_id": profile_id})
    return JobSearchPreferences(
        user_id="local-user",
        profile_id=profile_id,
        version=2,
        role_family_priority=suggestion.role_family_priority,
        target_titles=list(titles or suggestion.target_titles),
        related_title_variants=suggestion.related_title_variants,
        technical_themes=suggestion.technical_themes,
        career_interests=suggestion.career_interests,
        job_levels=suggestion.job_levels,
        locations=suggestion.locations,
        work_arrangement=suggestion.work_arrangement,
        work_arrangement_mode=suggestion.work_arrangement_mode,
        preferred_companies=suggestion.preferred_companies,
        created_at=WHEN,
        confirmed_at=WHEN,
    )


def test_streamlit_does_not_render_radius_or_distance():
    fake_st = FakeStreamlit()
    fake_api = FakeApi()
    render_job_discovery_view(fake_api, streamlit_module=fake_st)
    rendered_text = " ".join(fake_st.text)
    assert "radius" not in rendered_text.lower()
    assert "distance" not in rendered_text.lower()
    assert "Target titles" not in fake_st.text


def test_confirmed_preferences_rehydrate_in_a_fresh_streamlit_session():
    fake_api = FakeApi()
    fake_api.current_preferences = _confirmed_preferences(
        fake_api, titles=["Software Engineer"]
    )
    fake_st = FakeStreamlit()

    render_job_discovery_view(fake_api, streamlit_module=fake_st)

    assert fake_st.input_values["Target titles"] == "Software Engineer"
    assert not any(name == "suggest" for name, _ in fake_api.calls)


def test_rehydrated_preferences_can_be_confirmed_without_a_session_suggestion():
    fake_api = FakeApi()
    fake_api.current_preferences = _confirmed_preferences(
        fake_api, titles=["Restored Engineer"]
    )
    fake_st = FakeStreamlit({"Confirm preferences"})

    render_job_discovery_view(fake_api, streamlit_module=fake_st)

    confirmed = next(value for name, value in fake_api.calls if name == "confirm")
    assert confirmed.target_titles == ["Restored Engineer"]
    assert confirmed.confirmed_at is not None
    assert confirmed.confirmed_at > WHEN


def test_regenerated_suggestion_does_not_overwrite_current_confirmed_preferences():
    fake_api = FakeApi()
    fake_api.current_preferences = _confirmed_preferences(
        fake_api, titles=["Confirmed Engineer"]
    )
    fake_api.suggestion = fake_api.suggestion.model_copy(
        update={"target_titles": ["Regenerated Engineer"]}
    )
    fake_st = FakeStreamlit({"Suggest preferences"})

    render_job_discovery_view(fake_api, streamlit_module=fake_st)

    assert fake_api.current_preferences.target_titles == ["Confirmed Engineer"]
    assert fake_st.input_values["Target titles"] == "Regenerated Engineer"


def test_profile_switch_loads_profile_specific_confirmed_preferences():
    fake_api = FakeApi()
    fake_api.list_reviewed_profiles = lambda: [
        SimpleNamespace(id="p1", display_name="First"),
        SimpleNamespace(id="p2", display_name="Second"),
    ]
    fake_api.current_preferences = _confirmed_preferences(
        fake_api, profile_id="p2", titles=["Second Profile Role"]
    )
    fake_st = FakeStreamlit()
    fake_st.selected_profile = "p2"

    render_job_discovery_view(fake_api, streamlit_module=fake_st)

    assert fake_st.input_values["Target titles"] == "Second Profile Role"


def test_job_discovery_view_is_composed_from_app():
    app_source = (
        Path(__file__).parents[1] / "src" / "resume_tailor" / "frontend" / "app.py"
    ).read_text(encoding="utf-8")
    assert "render_job_discovery_view" in app_source


def test_view_composes_profile_suggestion_edit_confirmation_and_refresh():
    fake_api = FakeApi()
    fake_st = FakeStreamlit({"Suggest preferences"})
    render_job_discovery_view(fake_api, streamlit_module=fake_st)
    assert ("suggest", "p1") in fake_api.calls
    assert "Target titles" in fake_st.text
    assert "Related title variants" in fake_st.text
    assert "Technical themes" in fake_st.text
    assert "Career interests" in fake_st.text
    assert "Job levels" in fake_st.text
    assert "Locations" in fake_st.text
    assert "Work arrangement" in fake_st.text
    assert "Work arrangement mode" in fake_st.text
    assert "Preferred companies" in fake_st.text
    assert "Excluded companies" in fake_st.text
    assert "Work-authorization constraints" in fake_st.text
    assert "Maximum posting age (days)" in fake_st.text

    fake_st.clicked = {"Confirm preferences"}
    render_job_discovery_view(fake_api, streamlit_module=fake_st)
    assert any(name == "confirm" for name, _ in fake_api.calls)

    fake_st.clicked = {"Refresh recommendations"}
    render_job_discovery_view(fake_api, streamlit_module=fake_st)
    assert ("refresh", "p1") in fake_api.calls
    assert "No approved job sources are configured" in " ".join(fake_st.text)


def test_preference_editor_preserves_all_suggested_locations():
    fake_api = FakeApi()
    fake_api.suggestion = fake_api.suggestion.model_copy(
        update={
            "locations": [
                NormalizedLocation(city="Toronto", region="ON", country_code="CA"),
                NormalizedLocation(city="Montreal", region="QC", country_code="CA"),
            ]
        }
    )
    fake_st = FakeStreamlit({"Suggest preferences", "Confirm preferences"})

    render_job_discovery_view(fake_api, streamlit_module=fake_st)

    confirmed = next(value for name, value in fake_api.calls if name == "confirm")
    assert [(location.city, location.region) for location in confirmed.locations] == [
        ("Toronto", "ON"),
        ("Montreal", "QC"),
    ]


def test_view_renders_results_and_saved_unavailable_snapshot_without_probability_language():
    fake_api = FakeApi()
    fake_api.refresh_result = SimpleNamespace(
        run=SimpleNamespace(
            status=DiscoveryRunStatus.COMPLETED_WITH_WARNINGS,
            warnings=["One source returned a partial response."],
            source_warnings=[],
            error_messages=[],
        ),
        recommendations=[
            SimpleNamespace(
                job_id="job-1",
                primary_role_family=RoleFamily.SOFTWARE_DATA_ENGINEERING,
                score=SimpleNamespace(total=82.0, label=MatchLabel.GOOD, provisional=False),
                reasons=["Demonstrated Python in Project One."],
                gaps=[
                    "Preferred Kubernetes is not present in reviewed profile evidence or skills."
                ],
            )
        ],
    )
    fake_api.saved_jobs = [
        SimpleNamespace(
            id="saved-1",
            availability=SavedJobAvailability.UNAVAILABLE,
            saved_at=WHEN,
            checked_at=WHEN,
            posting_snapshot=SimpleNamespace(
                title="Saved Software Engineer",
                description="Original saved description.",
                official_url="https://boards.greenhouse.io/example/jobs/123",
            ),
        )
    ]
    fake_st = FakeStreamlit({"Refresh recommendations", "Check availability saved-1"})
    fake_st.session_state["job_discovery_confirmed_preferences"] = SimpleNamespace()
    fake_st.session_state["job_discovery_profile_id"] = "p1"
    render_job_discovery_view(fake_api, streamlit_module=fake_st)

    rendered_text = " ".join(fake_st.text)
    assert "82.0% profile-fit score" in rendered_text
    assert "Good Match" in rendered_text
    assert "Demonstrated Python in Project One." in rendered_text
    assert "Preferred Kubernetes" in rendered_text
    assert "verified active" in rendered_text
    assert "https://boards.greenhouse.io/example/jobs/123" in rendered_text
    assert "Original saved description." in rendered_text
    assert "hiring probability" not in rendered_text.lower()
    assert ("check", "saved-1") in fake_api.calls
    assert "job_discovery_checked_saved_jobs" in fake_st.session_state


def test_view_reports_preference_conflict_as_readable_error():
    fake_api = FakeApi()
    fake_api.confirm_preferences = lambda preferences: (_ for _ in ()).throw(
        PreferenceVersionConflictError("conflict")
    )
    fake_st = FakeStreamlit({"Suggest preferences", "Confirm preferences"})

    render_job_discovery_view(fake_api, streamlit_module=fake_st)

    assert any("conflict with a newer confirmed version" in text for text in fake_st.text)
