import json
from pathlib import Path
from types import SimpleNamespace

import streamlit as st

from resume_tailor.frontend.profile_page import ProfilePageDependencies, render_profile_page
from resume_tailor.infrastructure.resume_extraction import ExtractedResumeText


class InMemoryProfileRepository:
    def __init__(self, profile: object) -> None:
        self._profiles = {
            "local-profile": profile,
            "profile-existing": profile.model_copy(
                update={"id": "profile-existing", "display_name": "Second Candidate"}
            ),
        }

    def get(self, profile_id: str) -> object | None:
        if (
            st.session_state.get("profile-test-scenario") == "No profile"
            and profile_id == "local-profile"
        ):
            return None
        return self._profiles.get(profile_id)

    def list_all(self) -> list[object]:
        if st.session_state.get("profile-test-scenario") == "No profile":
            return [value for key, value in self._profiles.items() if key != "local-profile"]
        return list(self._profiles.values())

    def save(self, profile: object) -> None:
        self._profiles[profile.id] = profile
        st.session_state["profile-test-save-count"] = (
            st.session_state.get("profile-test-save-count", 0) + 1
        )


def _fixture_profile() -> object:
    from resume_tailor.domain.models import MasterProfile

    fixture_path = Path(__file__).parents[1] / "fixtures" / "profile_completeness.json"
    return MasterProfile.model_validate(json.loads(fixture_path.read_text(encoding="utf-8")))


st.set_page_config(layout="wide")
if "profile-test-repository" not in st.session_state:
    st.session_state["profile-test-repository"] = InMemoryProfileRepository(_fixture_profile())
st.session_state.setdefault("profile-test-save-count", 0)
scenario = st.selectbox(
    "Profile test scenario",
    ("Existing local", "No profile", "Seed extracted draft"),
    key="profile-test-scenario",
)
if scenario == "No profile":
    if not st.session_state.get("profile-test-no-profile-initialized", False):
        st.session_state.pop("profile", None)
        st.session_state.pop("profile_id", None)
        st.session_state.pop("jobs_profile_id", None)
        st.session_state["profile-test-no-profile-initialized"] = True
    st.session_state.pop("profile_extraction_draft", None)
elif scenario == "Seed extracted draft":
    if (
        "profile_extraction_draft" not in st.session_state
        and not st.session_state.get("profile-test-save-count")
    ):
        draft_profile = st.session_state["profile-test-repository"].get("local-profile").model_copy(
            update={"id": "draft-profile", "display_name": "Draft Candidate"}
        )
        st.session_state["profile_extraction_draft"] = SimpleNamespace(
            profile=draft_profile,
            missing_fields=("Education awards",),
            uncertain_fields=("Employment dates",),
            extraction_notes=("Review extracted dates before saving.",),
            fidelity_flags=("Formatting was not preserved in extraction.",),
        )
        st.session_state["profile_extraction_source"] = ExtractedResumeText(
            filename="review-source.docx",
            source_format="docx",
            text=(
                "Example Candidate\nEmbedded Systems Intern — Example Robotics\n"
                "Built and tested an embedded sensor interface."
            ),
        )
else:
    st.session_state.pop("profile-test-no-profile-initialized", None)
    st.session_state.pop("profile_extraction_draft", None)
    st.session_state.pop("profile_extraction_source", None)

render_profile_page(
    st,
    ProfilePageDependencies(
        profile_repository=st.session_state["profile-test-repository"],
        tailor_service=object(),
        invalidate_tailoring=lambda: st.session_state.__setitem__("profile-test-invalidated", True),
    ),
)
