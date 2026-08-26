from __future__ import annotations

import base64

import streamlit as st

from resume_tailor.application.resume_editor import ResumeEditorService
from resume_tailor.domain.generated_artifact import GeneratedResumeArtifact
from resume_tailor.domain.models import (
    ClaimSupport,
    EntityKind,
    EvidenceItem,
    JobPosting,
    MasterProfile,
    ResumeItem,
    ResumeStrategy,
    StructuredBullet,
    StructuredResume,
    TechnicalSkillCategory,
)
from resume_tailor.domain.resume_editor import ResumeEditorFitStatus, ResumeEditorRender
from resume_tailor.frontend.resume_editor import render_resume_editor

_PREVIEW_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "AAMAAWgmWQ0AAAAASUVORK5CYII="
)


class _Renderer:
    def render(
        self,
        resume: StructuredResume,
        *,
        source_docx_bytes: bytes | None = None,
    ) -> ResumeEditorRender:
        st.session_state["editor-render-calls"] = (
            st.session_state.get("editor-render-calls", 0) + 1
        )
        page_count = int(st.session_state.get("editor-preview-pages", 1))
        return ResumeEditorRender(
            document_fingerprint=f"render-{st.session_state['editor-render-calls']}",
            docx_bytes=source_docx_bytes or resume.model_dump_json().encode(),
            pdf_bytes=b"%PDF-sanitized",
            preview_page_pngs=[_PREVIEW_PNG] * page_count,
            page_count=page_count,
            exact_pagination=True,
            pagination_provider="exact sanitized renderer",
            utilization_ratio=0.84 if page_count == 1 else 1.12,
            status=(
                ResumeEditorFitStatus.FITS_ONE_PAGE
                if page_count == 1
                else ResumeEditorFitStatus.EXCEEDS_ONE_PAGE
            ),
        )


entry = ResumeItem(
    id="experience-controls",
    title="Controls Engineer",
    kind=EntityKind.EXPERIENCE,
    organization="Northstar Mobility",
)
omitted_experience = ResumeItem(
    id="experience-lab",
    title="Hardware Lab Assistant",
    kind=EntityKind.EXPERIENCE,
    organization="Northstar Lab",
)
omitted_project = ResumeItem(
    id="project-arm",
    title="Long Reach Manipulator",
    kind=EntityKind.PROJECT,
)
profile = MasterProfile(
    id="profile-editor-ui",
    user_id="user-editor-ui",
    display_name="Candidate",
    experiences=[entry, omitted_experience],
    projects=[omitted_project],
    technical_skills=[TechnicalSkillCategory(category="Languages", values=["C++", "Python"])],
    evidence=[
        EvidenceItem(
            id="evidence-firmware",
            entity_id=entry.id,
            source_text="Developed STM32 control firmware in C++ for actuator feedback.",
            technologies=["STM32", "C++"],
        ),
        EvidenceItem(
            id="evidence-wiring",
            entity_id=entry.id,
            source_text="Built and validated wiring harnesses for control hardware.",
            technologies=["wiring harnesses"],
        ),
        EvidenceItem(
            id="evidence-lab",
            entity_id=omitted_experience.id,
            source_text="Soldered and inspected prototype control boards.",
            technologies=["soldering"],
        ),
        EvidenceItem(
            id="evidence-arm",
            entity_id=omitted_project.id,
            source_text="Designed a SolidWorks actuator bracket for a long-reach arm.",
            technologies=["SolidWorks"],
        ),
    ],
)
resume = StructuredResume(
    profile_id=profile.id,
    profile_version=profile.version,
    posting_id="posting-editor-ui",
    template_id="managed-engineering-v1",
    display_name=profile.display_name,
    strategy=ResumeStrategy(
        role_family="embedded",
        primary_focus="Embedded controls",
        rationale="Use reviewed controls evidence.",
    ),
    entity_titles={entry.id: entry.title},
    technical_skills=[profile.technical_skills[0].model_copy(deep=True)],
    experiences=[entry],
    experience_bullets={
        entry.id: [
            StructuredBullet(
                id="bullet-firmware",
                text=profile.evidence[0].source_text,
                evidence_ids=[profile.evidence[0].id],
                support=ClaimSupport.DIRECT,
            ),
            StructuredBullet(
                id="bullet-wiring",
                text=profile.evidence[1].source_text,
                evidence_ids=[profile.evidence[1].id],
                support=ClaimSupport.DIRECT,
            ),
        ]
    },
)
application = st.selectbox("Application", ["Job A", "Job B"], key="editor-application")
preview_pages = st.selectbox("Preview pages", [1, 2], key="editor-preview-pages")
posting = JobPosting(
    id=f"posting-editor-ui-{application.casefold().replace(' ', '-')}",
    title="Embedded Engineer" if application == "Job A" else "Controls Test Engineer",
    description=(
        "Develop and validate embedded controls on physical hardware."
        if application == "Job A"
        else "Test controls, feedback, and wiring on electromechanical systems."
    ),
)
resume = resume.model_copy(update={"posting_id": posting.id})
artifact = GeneratedResumeArtifact.model_construct(
    artifact_fingerprint=(
        f"artifact-editor-ui-{application.casefold().replace(' ', '-')}-{preview_pages}"
    ),
    final_resume=resume,
    docx_bytes=b"PK-sanitized-docx",
)
st.session_state.setdefault("editor-render-calls", 0)
render_resume_editor(
    st,
    service=ResumeEditorService(_Renderer()),
    artifact=artifact,
    profile=profile,
    posting=posting,
    clear_export=lambda module: None,
)
