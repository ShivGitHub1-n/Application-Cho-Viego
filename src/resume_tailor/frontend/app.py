import json
from pathlib import Path
from tempfile import TemporaryDirectory

import streamlit as st

from resume_tailor.domain.models import JobPosting, MasterProfile, TemplateConstraints
from resume_tailor.infrastructure.dependencies import create_tailor_service
from resume_tailor.infrastructure.rendering import ManagedResumeRenderer, PageOverflowError


st.set_page_config(page_title="Resume Tailor", page_icon="📄", layout="wide")
st.title("Resume Tailor")
st.caption("One evidence-backed recommendation for engineering opportunities.")

service = create_tailor_service()

profile_json = st.text_area(
    "Reviewed career profile (JSON)",
    placeholder='{"id":"profile-1","user_id":"local-user","display_name":"Your Name","experiences":[],"projects":[],"evidence":[]}',
    height=180,
)
posting_text = st.text_area("Job description", height=180)
posting_title = st.text_input("Job title", value="Embedded Firmware Engineer")

if st.button("Recommend resume strategy", type="primary"):
    try:
        profile = MasterProfile.model_validate(json.loads(profile_json))
        posting = JobPosting(id="local-posting", title=posting_title, description=posting_text)
        plan = service.create_plan(profile, posting, TemplateConstraints())
        st.session_state["profile"] = profile
        st.session_state["plan"] = plan
    except (json.JSONDecodeError, ValueError) as error:
        st.error(f"Use a valid reviewed profile: {error}")

plan = st.session_state.get("plan")
profile = st.session_state.get("profile")
if plan and profile:
    if plan.strategy is None:
        st.warning(plan.report.warnings[0])
    else:
        st.subheader("Recommended strategy")
        st.write(plan.strategy.rationale)
        st.caption(f"Primary focus: {plan.strategy.primary_focus}")
        if plan.report.profile_fit and plan.report.profile_fit.status.value != "sufficient":
            st.warning(plan.report.profile_fit.reason)
        st.subheader("Decision review")
        for decision in plan.report.decisions:
            st.write(f"**{decision.action.replace('_', ' ').title()}** — {decision.reason}")
        if plan.report.uncovered_signals:
            st.warning("Profile gaps: " + ", ".join(plan.report.uncovered_signals))
        review_ids = [
            candidate.id
            for candidate in plan.claim_candidates
            if candidate.support.value == "strong_inference_pending_review"
        ]
        approved_ids = {
            claim_id
            for claim_id in review_ids
            if st.checkbox(f"Approve inferred wording: {claim_id}", key=f"approve-{claim_id}")
        }
        if st.button("Build approved resume"):
            resume = service.build_document(plan, profile, approved_ids)
            try:
                with TemporaryDirectory() as directory:
                    result = ManagedResumeRenderer().render(resume, Path(directory))
                    st.download_button("Download DOCX", result.docx_path.read_bytes(), "tailored-resume.docx")
                    st.download_button("Download PDF", result.pdf_path.read_bytes(), "tailored-resume.pdf")
            except PageOverflowError as error:
                st.error(str(error))
