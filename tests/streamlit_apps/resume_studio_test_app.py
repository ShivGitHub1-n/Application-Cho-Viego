from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import streamlit as st

from resume_tailor.application.workflow_state import invalidate_derived_workflow
from resume_tailor.frontend.jobs_page import apply_tailoring_handoff
from resume_tailor.frontend.resume_studio_page import (
    ResumeStudioDependencies,
    render_resume_studio_page,
)


@dataclass(frozen=True)
class _Candidate:
    id: str
    support: SimpleNamespace


@dataclass(frozen=True)
class _GeneratedItem:
    id: str
    text: str
    value: str = ""
    evidence_ids: tuple[str, ...] = ()
    writing_variant: object | None = None


class _Plan:
    strategy = SimpleNamespace(
        rationale="Use confirmed embedded evidence.", primary_focus="Embedded systems"
    )
    report = SimpleNamespace(
        profile_fit=None,
        uncovered_signals=("Safety process",),
        decisions=(SimpleNamespace(action="include", reason="Direct evidence"),),
    )
    claim_candidates = (
        _Candidate(
            "plan-claim-1",
            SimpleNamespace(value="strong_inference_pending_review"),
        ),
    )
    selected_entity_ids = ("experience-1",)

    def model_dump_json(self) -> str:
        return '{"plan":"offline"}'


class _Resume:
    def __init__(self) -> None:
        self.education = ()
        self.technical_skills = ()
        self.experience_bullets = {}
        self.project_bullets = {}
        self.entity_titles = {}
        if st.session_state.get("resume-test-generated-pending", False):
            omitted = st.session_state.get("resume-test-omitted-entry-suggestion", False)
            self.review_pending_bullets = (
                _GeneratedItem(
                    "generated-bullet-1",
                    "A generated bullet pending review.",
                    evidence_ids=("evidence-project-two",) if omitted else (),
                    writing_variant=(SimpleNamespace(entry_id="project-two") if omitted else None),
                ),
            )
            self.review_pending_skills = (
                _GeneratedItem(
                    "generated-skill-1", "A generated skill pending review", "Embedded C"
                ),
            )
        else:
            self.review_pending_bullets = ()
            self.review_pending_skills = ()


class OfflineResumeService:
    def create_plan(self, *args: object, **kwargs: object) -> object:
        st.session_state["resume-studio-service-calls"] = (
            st.session_state.get("resume-studio-service-calls", 0) + 1
        )
        return _Plan()

    def build_document(self, *args: object, **kwargs: object) -> object:
        st.session_state["resume-studio-build-calls"] = (
            st.session_state.get("resume-studio-build-calls", 0) + 1
        )
        return _Resume()


class OfflineResumeRenderer:
    def render(self, resume: object, directory: Path) -> object:
        if st.session_state.get("resume-test-render-mode") == "unavailable":
            from resume_tailor.infrastructure.rendering import PageCountVerificationError

            raise PageCountVerificationError("offline exact verification unavailable")
        docx_path = directory / "offline-resume.docx"
        pdf_path = directory / "offline-resume.pdf"
        docx_path.write_bytes(b"offline-docx")
        pdf_path.write_bytes(b"offline-pdf")
        return SimpleNamespace(
            docx_path=docx_path,
            pdf_path=pdf_path,
            measurement_provider="offline exact verifier",
        )


st.set_page_config(layout="wide")
st.session_state.setdefault("resume-studio-service-calls", 0)
st.session_state.setdefault("resume-studio-build-calls", 0)
if st.session_state.pop("resume-test-apply-handoff", False):
    apply_tailoring_handoff(
        st.session_state,
        SimpleNamespace(
            profile_id="profile-completeness-fixture",
            title="Handoff Firmware Engineer",
            description="Build firmware from a selected reviewed Jobs posting.",
        ),
    )
if st.session_state.pop("resume-test-apply-html-handoff", False):
    apply_tailoring_handoff(
        st.session_state,
        SimpleNamespace(
            profile_id="profile-completeness-fixture",
            title="Embedded Systems Engineer",
            company="Northstar Devices",
            description=(
                "&lt;div&gt;Build embedded controls.&lt;/div&gt;"
                "&lt;ul&gt;&lt;li&gt;Validate firmware on hardware.&lt;/li&gt;&lt;/ul&gt;"
            ),
        ),
    )
if "profile" not in st.session_state:
    from resume_tailor.domain.models import MasterProfile

    fixture_path = Path(__file__).parents[1] / "fixtures" / "profile_completeness.json"
    st.session_state["profile"] = MasterProfile.model_validate(
        json.loads(fixture_path.read_text(encoding="utf-8"))
    )
render_resume_studio_page(
    st,
    ResumeStudioDependencies(
        tailor_service=OfflineResumeService(),
        resume_renderer=OfflineResumeRenderer(),
        invalidate_tailoring=lambda: invalidate_derived_workflow(st.session_state),
    ),
)

# AppTest retains the previous run's widget tree while submitting the next
# interaction. Keep deterministic pending-approval keys alive outside the
# review stage so a stage transition does not make the harness itself fail
# before the page can be evaluated. Production never renders these controls.
if (
    st.session_state.get("resume-test-generated-pending", False)
    and st.session_state.get("resume_studio_stage") != "Resume review"
):
    st.checkbox(
        "Generated bullet harness state",
        key="_resume_generated_bullet_approval_widget_generated-bullet-1",
        label_visibility="collapsed",
    )
    st.checkbox(
        "Generated skill harness state",
        key="_resume_generated_skill_approval_widget_generated-skill-1",
        label_visibility="collapsed",
    )
if st.session_state.get("resume_studio_stage") != "Resume review":
    st.checkbox(
        "Review confirmation harness state",
        key="_resume_studio_review_confirmed_widget",
        label_visibility="collapsed",
    )
