import json
from pathlib import Path
from tempfile import TemporaryDirectory

import streamlit as st

from resume_tailor.application.job_intake import InvalidJobDescriptionError, build_job_posting, normalize_job_description
from resume_tailor.application.workflow_state import invalidate_derived_workflow
from resume_tailor.domain.llm_models import LanguageModelError
from resume_tailor.domain.models import MasterProfile, StructuredResume, TemplateConstraints
from resume_tailor.infrastructure.dependencies import create_profile_repository, create_tailor_service
from resume_tailor.infrastructure.rendering import ManagedResumeRenderer, PageOverflowError
from resume_tailor.infrastructure.profile_repository import CorruptStoredProfileError, ProfileStoreError
from resume_tailor.infrastructure.resume_extraction import ResumeExtractionError, extract_resume_text


st.set_page_config(page_title="Resume Tailor", page_icon="📄", layout="wide")
st.title("Resume Tailor")
st.caption("One evidence-backed recommendation for engineering opportunities.")

service = create_tailor_service()
profile_repository = create_profile_repository()


def clear_tailoring_state() -> None:
    invalidate_derived_workflow(st.session_state)


def profile_fingerprint(profile: MasterProfile) -> str:
    return profile.model_dump_json()


if "profile_load_status" not in st.session_state:
    try:
        persisted = profile_repository.get("local-profile")
        if persisted is not None:
            st.session_state["profile"] = persisted
            st.session_state["profile_id"] = persisted.id
            st.session_state["profile_load_status"] = "Loaded from persistent storage."
        else:
            st.session_state["profile_load_status"] = "No saved profile found."
    except (ProfileStoreError, CorruptStoredProfileError) as error:
        st.session_state["profile_load_status"] = f"Saved profile unavailable: {error}"


def generated_content_review(resume: StructuredResume) -> dict[str, list[str]]:
    """Return the selected generated content in reviewable, text-only groups."""

    education = [
        "; ".join(
            value
            for value in (
                record.school,
                record.program,
                record.location,
                record.graduation_date or record.expected_graduation_date,
            )
            if value
        )
        for record in resume.education
    ]
    skills = [
        f"{category.category}: {', '.join(skill.value for skill in category.skills)}"
        for category in resume.technical_skills
    ]
    experience = []
    for entity_id, bullets in resume.experience_bullets.items():
        title = resume.entity_titles.get(entity_id, entity_id)
        experience.extend([f"{title}: {bullet.text}" for bullet in bullets])
    projects = []
    for entity_id, bullets in resume.project_bullets.items():
        title = resume.entity_titles.get(entity_id, entity_id)
        projects.extend([f"{title}: {bullet.text}" for bullet in bullets])
    return {
        "education": education,
        "technical_skills": skills,
        "experience": experience,
        "projects": projects,
    }

profile_id = st.text_input("Profile ID", value=st.session_state.get("profile_id", "local-profile"))
uploaded_resume = st.file_uploader("Upload resume for profile draft (.docx or text-based .pdf)", type=["docx", "pdf"])
if st.button("Extract profile draft from resume"):
    try:
        if uploaded_resume is None:
            raise ResumeExtractionError("Choose a DOCX or text-based PDF resume first.")
        extracted = extract_resume_text(uploaded_resume.name, uploaded_resume.getvalue())
        result = service.extract_profile_draft(
            profile_id.strip() or "local-profile",
            extracted.source_format,
            extracted.text,
        )
        st.session_state["profile_extraction_draft"] = result.output
        st.session_state["profile_extraction_source"] = extracted
        st.success("Draft profile extracted. Review and correct it before approval.")
    except (ResumeExtractionError, ValueError, LanguageModelError) as error:
        st.error(f"Resume extraction failed: {error}")

draft_output = st.session_state.get("profile_extraction_draft")
if draft_output:
    if "profile_extraction_json" not in st.session_state:
        st.session_state["profile_extraction_json"] = json.dumps(
            draft_output.profile.model_dump(mode="json"), indent=2
        )
    st.subheader("Extracted profile draft")
    if draft_output.missing_fields:
        st.warning("Missing fields: " + ", ".join(draft_output.missing_fields))
    if draft_output.uncertain_fields:
        st.warning("Uncertain fields: " + ", ".join(draft_output.uncertain_fields))
    if draft_output.extraction_notes:
        st.info("Extraction notes: " + " ".join(draft_output.extraction_notes))
    if draft_output.fidelity_flags:
        st.warning("Fidelity flags: " + " ".join(draft_output.fidelity_flags))
    st.text_area("Correct extracted profile JSON before approval", height=260, key="profile_extraction_json")
    if st.button("Approve and save extracted profile"):
        try:
            approved_profile = MasterProfile.model_validate(
                json.loads(st.session_state["profile_extraction_json"])
            )
            profile_repository.save(approved_profile)
            clear_tailoring_state()
            st.session_state["profile"] = approved_profile
            st.session_state["profile_id"] = approved_profile.id
            st.session_state["profile_load_status"] = "Saved successfully after extraction review."
            st.session_state.pop("profile_extraction_draft", None)
            st.session_state.pop("profile_extraction_json", None)
            st.success("Extracted profile approved and saved.")
        except (json.JSONDecodeError, ValueError, ProfileStoreError) as error:
            st.error(f"Extracted profile was not saved: {error}")

profile_json = st.text_area(
    "Reviewed career profile (JSON)",
    placeholder='{"id":"profile-1","user_id":"local-user","display_name":"Your Name","experiences":[],"projects":[],"evidence":[]}',
    height=180,
    key="profile_json_input",
)
st.caption(st.session_state.get("profile_load_status", "Profile not loaded."))
save_col, load_col = st.columns(2)
with save_col:
    save_profile = st.button("Save profile")
with load_col:
    load_profile = st.button("Load saved profile")
posting_text = st.text_area("Paste job description", height=180, key="job_description_input")
posting_title = st.text_input("Job title", value="Embedded Firmware Engineer")

if st.session_state.get("workflow_posting_fingerprint") and posting_text.strip():
    try:
        current_posting = build_job_posting("local-posting", posting_title, posting_text)
        if current_posting.model_dump_json() != st.session_state["workflow_posting_fingerprint"]:
            clear_tailoring_state()
    except InvalidJobDescriptionError:
        clear_tailoring_state()
if st.session_state.get("workflow_profile_fingerprint") and profile_json.strip():
    try:
        current_profile = MasterProfile.model_validate(json.loads(profile_json))
        if profile_fingerprint(current_profile) != st.session_state["workflow_profile_fingerprint"]:
            clear_tailoring_state()
    except (json.JSONDecodeError, ValueError):
        clear_tailoring_state()

if save_profile:
    try:
        profile = MasterProfile.model_validate(json.loads(profile_json))
        if profile.id != profile_id.strip():
            raise ValueError("Profile ID field must match the profile JSON id")
        profile_repository.save(profile)
        clear_tailoring_state()
        st.session_state["profile"] = profile
        st.session_state["profile_id"] = profile.id
        st.session_state["profile_load_status"] = "Saved successfully."
        st.success("Master profile saved.")
    except (json.JSONDecodeError, ValueError, ProfileStoreError) as error:
        st.error(f"Profile was not saved: {error}")

if load_profile:
    try:
        loaded = profile_repository.get(profile_id.strip())
        if loaded is None:
            st.warning("No saved profile exists for that profile ID.")
        else:
            clear_tailoring_state()
            st.session_state["profile"] = loaded
            st.session_state["profile_id"] = loaded.id
            st.session_state["profile_load_status"] = "Loaded from persistent storage."
            st.success("Master profile loaded. Review the active profile before tailoring.")
    except (ProfileStoreError, CorruptStoredProfileError, ValueError) as error:
        st.error(f"Profile could not be loaded: {error}")

if posting_text.strip():
    try:
        st.subheader("Job description preview")
        st.code(normalize_job_description(posting_text))
    except InvalidJobDescriptionError as error:
        st.error(str(error))

if st.button("Recommend resume strategy", type="primary"):
    try:
        profile = (
            MasterProfile.model_validate(json.loads(profile_json))
            if profile_json.strip()
            else st.session_state.get("profile")
        )
        if profile is None:
            raise ValueError("Enter or load a reviewed master profile first")
        posting = build_job_posting("local-posting", posting_title, posting_text)
        previous_profile = st.session_state.get("profile")
        if previous_profile is not None and profile_fingerprint(previous_profile) != profile_fingerprint(profile):
            clear_tailoring_state()
        previous_posting = st.session_state.get("posting")
        if previous_posting is not None and previous_posting.model_dump_json() != posting.model_dump_json():
            clear_tailoring_state()
        plan = service.create_plan(profile, posting, TemplateConstraints())
        st.session_state["profile"] = profile
        st.session_state["profile_id"] = profile.id
        st.session_state["posting"] = posting
        if previous_profile is None or profile_fingerprint(previous_profile) != profile_fingerprint(profile):
            st.session_state["profile_load_status"] = "Newly entered; not saved."
        st.session_state["workflow_profile_fingerprint"] = profile_fingerprint(profile)
        st.session_state["workflow_posting_fingerprint"] = posting.model_dump_json()
        st.session_state["plan"] = plan
        st.session_state.pop("resume", None)
        st.session_state["generated_content_reviewed"] = False
    except (json.JSONDecodeError, InvalidJobDescriptionError, ValueError) as error:
        st.error(f"Profile or job description is invalid: {error}")

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
            st.session_state["resume"] = service.build_document(plan, profile, approved_ids)
            st.session_state["generated_content_reviewed"] = False

        resume = st.session_state.get("resume")
        if resume:
            st.subheader("Generated resume review")
            st.caption("Review the selected content below before exporting the submission document.")
            review_groups = generated_content_review(resume)
            for label, items in review_groups.items():
                if items:
                    st.markdown(f"**{label.replace('_', ' ').title()}**")
                    for item in items:
                        st.write(item)
            pending_approved_ids: set[str] = set()
            if resume.review_pending_bullets or resume.review_pending_skills:
                st.markdown("**Strongly implied content requiring approval**")
                for bullet in resume.review_pending_bullets:
                    if st.checkbox(
                        f"Approve inferred bullet: {bullet.text}",
                        key=f"approve-generated-{bullet.id}",
                    ):
                        pending_approved_ids.add(bullet.id)
                for skill in resume.review_pending_skills:
                    if st.checkbox(
                        f"Approve inferred skill: {skill.value}",
                        key=f"approve-generated-{skill.id}",
                    ):
                        pending_approved_ids.add(skill.id)
            st.checkbox(
                "I reviewed the generated resume content and approve it for export.",
                key="generated_content_reviewed",
            )
            if st.button(
                "Export reviewed resume",
                disabled=not st.session_state.get("generated_content_reviewed", False),
            ):
                try:
                    approved_for_export = approved_ids | pending_approved_ids
                    export_resume = service.build_document(plan, profile, approved_for_export)
                    with TemporaryDirectory() as directory:
                        result = ManagedResumeRenderer().render(export_resume, Path(directory))
                        st.download_button("Download DOCX", result.docx_path.read_bytes(), "tailored-resume.docx")
                        st.download_button("Download PDF", result.pdf_path.read_bytes(), "tailored-resume.pdf")
                except PageOverflowError as error:
                    st.error(str(error))
