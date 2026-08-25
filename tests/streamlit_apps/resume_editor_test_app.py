from __future__ import annotations

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
        return ResumeEditorRender(
            document_fingerprint=f"render-{st.session_state['editor-render-calls']}",
            docx_bytes=source_docx_bytes or resume.model_dump_json().encode(),
            pdf_bytes=b"%PDF-sanitized",
            page_count=1,
            exact_pagination=True,
            pagination_provider="exact sanitized renderer",
            utilization_ratio=0.84,
            status=ResumeEditorFitStatus.FITS_ONE_PAGE,
        )


entry = ResumeItem(
    id="experience-controls",
    title="Controls Engineer",
    kind=EntityKind.EXPERIENCE,
    organization="Northstar Mobility",
)
profile = MasterProfile(
    id="profile-editor-ui",
    user_id="user-editor-ui",
    display_name="Candidate",
    experiences=[entry],
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
    artifact_fingerprint=f"artifact-editor-ui-{application.casefold().replace(' ', '-')}",
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
