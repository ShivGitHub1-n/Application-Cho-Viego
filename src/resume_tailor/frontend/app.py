import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

import streamlit as st
from pydantic import ValidationError

from resume_tailor.application.job_intake import InvalidJobDescriptionError, build_job_posting, normalize_job_description
from resume_tailor.application.profile_editor import (
    add_bullet,
    add_education,
    add_entry,
    add_skill_category,
    editor_state_to_profile,
    move_item,
    profile_change_fingerprint,
    profile_to_editor_state,
    remove_bullet,
    remove_education,
    remove_entry,
    remove_skill_category,
    unknown_profile_fields,
)
from resume_tailor.application.workflow_state import invalidate_derived_workflow
from resume_tailor.domain.cover_letter import CoverLetterRecipient
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


def clear_cover_letter_state() -> None:
    for key in (
        "cover_letter",
        "cover_letter_reviewed",
        "cover_letter_profile_fingerprint",
        "cover_letter_posting_fingerprint",
        "cover_letter_plan_fingerprint",
        "cover_letter_evidence_fingerprint",
        "cover_letter_recipient_fingerprint",
    ):
        st.session_state.pop(key, None)


def profile_fingerprint(profile: MasterProfile) -> str:
    return profile.model_dump_json()


def initialize_profile_editor(profile: MasterProfile, source_key: str) -> None:
    if st.session_state.get("profile_editor_source_key") == source_key:
        return
    st.session_state["profile_editor_state"] = profile_to_editor_state(profile)
    st.session_state["profile_editor_source_key"] = source_key
    st.session_state["profile_editor_raw_json"] = json.dumps(
        profile.model_dump(mode="json"), indent=2
    )
    st.session_state.pop("profile_editor_errors", None)


def persist_profile_from_editor(profile: MasterProfile) -> bool:
    previous = st.session_state.get("profile")
    changed = previous is None or profile_change_fingerprint(previous) != profile_change_fingerprint(profile)
    try:
        profile_repository.save(profile)
    except (ProfileStoreError, ValueError) as error:
        st.session_state["profile_editor_errors"] = [f"Persistence failed: {error}"]
        return False
    if changed:
        clear_tailoring_state()
    st.session_state["profile"] = profile
    st.session_state["profile_id"] = profile.id
    st.session_state["profile_load_status"] = "Profile saved successfully."
    initialize_profile_editor(profile, f"saved:{profile.id}:{profile_change_fingerprint(profile)}")
    st.session_state.pop("profile_extraction_draft", None)
    st.session_state.pop("profile_extraction_source", None)
    st.session_state.pop("profile_editor_errors", None)
    return True


if "profile_load_status" not in st.session_state:
    try:
        persisted = profile_repository.get("local-profile")
        if persisted is not None:
            st.session_state["profile"] = persisted
            st.session_state["profile_id"] = persisted.id
            st.session_state["profile_load_status"] = "Loaded from persistent storage."
            initialize_profile_editor(persisted, f"saved:{persisted.id}:{profile_change_fingerprint(persisted)}")
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
        initialize_profile_editor(
            result.output.profile,
            f"extracted:{result.output.profile.id}:{profile_change_fingerprint(result.output.profile)}",
        )
        st.success("Draft profile extracted. Review and correct it before approval.")
    except (ResumeExtractionError, ValueError, LanguageModelError) as error:
        st.error(f"Resume extraction failed: {error}")

draft_output = st.session_state.get("profile_extraction_draft")
if draft_output:
    st.subheader("Extracted profile draft")
    if draft_output.missing_fields:
        st.warning("Missing fields: " + ", ".join(draft_output.missing_fields))
    if draft_output.uncertain_fields:
        st.warning("Uncertain fields: " + ", ".join(draft_output.uncertain_fields))
    if draft_output.extraction_notes:
        st.info("Extraction notes: " + " ".join(draft_output.extraction_notes))
    if draft_output.fidelity_flags:
        st.warning("Fidelity flags: " + " ".join(draft_output.fidelity_flags))
    st.info("Use the structured master-profile editor below to review and correct this draft before saving.")

profile_json = st.text_area(
    "Advanced profile input (JSON)",
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
        raw_profile_payload = json.loads(profile_json)
        if not isinstance(raw_profile_payload, dict):
            raise ValueError("Profile JSON must be an object.")
        unknown = unknown_profile_fields(raw_profile_payload)
        if unknown:
            raise ValueError("Unsupported top-level fields cannot be safely round-tripped: " + ", ".join(unknown))
        profile = MasterProfile.model_validate(raw_profile_payload)
        if profile.id != profile_id.strip():
            raise ValueError("Profile ID field must match the profile JSON id")
        if persist_profile_from_editor(profile):
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
            initialize_profile_editor(loaded, f"saved:{loaded.id}:{profile_change_fingerprint(loaded)}")
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
        clear_cover_letter_state()
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

# Cover letters are a separate derived workflow. They reuse the active plan and selected
# evidence, but never share generated-resume or approval state.
if profile is None or plan is None or not getattr(plan, "strategy", None):
    st.subheader("Cover letter")
    st.info("Create a valid master profile, pasted job posting, and tailoring plan to enable cover-letter drafting.")
else:
    st.subheader("Cover letter")
    st.caption("This draft reuses the current tailoring plan and selected confirmed evidence.")
    recipient_name = st.text_input("Recipient name (optional)", key="cover_recipient_name")
    recipient_title = st.text_input("Recipient title (optional)", key="cover_recipient_title")
    recipient_company = st.text_input(
        "Recipient/company override (optional)", value=posting.company_name or "", key="cover_recipient_company"
    )
    recipient = CoverLetterRecipient(
        name=recipient_name.strip() or None,
        title=recipient_title.strip() or None,
        company=recipient_company.strip() or posting.company_name,
    )
    evidence_fingerprint = ":".join(sorted(
        item.id for item in profile.evidence
        if item.confirmed and item.entity_id in set(plan.selected_entity_ids)
    ))
    recipient_fingerprint = recipient.model_dump_json()
    plan_fingerprint = plan.model_dump_json()
    current_cover_fingerprints = {
        "cover_letter_profile_fingerprint": profile_fingerprint(profile),
        "cover_letter_posting_fingerprint": posting.model_dump_json(),
        "cover_letter_plan_fingerprint": plan_fingerprint,
        "cover_letter_evidence_fingerprint": evidence_fingerprint,
        "cover_letter_recipient_fingerprint": recipient_fingerprint,
    }
    if any(
        st.session_state.get(key) is not None and st.session_state.get(key) != value
        for key, value in current_cover_fingerprints.items()
    ):
        clear_cover_letter_state()
    if st.button("Generate cover-letter draft", key="generate_cover_letter"):
        try:
            st.session_state["cover_letter"] = service.draft_cover_letter(
                profile, posting, plan, recipient=recipient
            )
            st.session_state["cover_letter_reviewed"] = False
            st.session_state.update(current_cover_fingerprints)
        except (ValueError, LanguageModelError) as error:
            st.error(f"Cover-letter drafting failed: {error}")

    letter = st.session_state.get("cover_letter")
    if letter:
        st.markdown("**Draft review**")
        st.write(f"{letter.date_text}")
        st.write(letter.salutation)
        for paragraph in letter.paragraphs:
            st.write(paragraph.text)
            for claim in paragraph.claims:
                label = "Explicitly supported" if claim.confidence.value == "explicitly_supported" else "Strongly implied — approval required"
                st.caption(f"{label}: {claim.text} (evidence: {', '.join(claim.evidence_ids)})")
        st.write(letter.closing)
        st.write(letter.signoff)
        st.write(f"**{letter.signoff_name}**")
        pending_approved = {
            claim.id
            for claim in letter.pending_claims
            if st.checkbox(
                f"Approve strongly implied claim: {claim.text}",
                key=f"cover-approve-{claim.id}",
            )
        }
        reviewed = st.checkbox(
            "I reviewed the complete cover letter and its supporting evidence.",
            key="cover_letter_reviewed",
        )
        if st.button(
            "Confirm cover-letter review",
            key="confirm_cover_letter_review",
            disabled=not reviewed,
        ):
            st.session_state["cover_letter"] = service.approve_cover_letter(
                letter, pending_approved, reviewed=reviewed
            )
            st.success("Cover-letter review recorded.")
        letter = st.session_state.get("cover_letter")
        can_export = bool(letter and letter.complete_review_confirmed and not letter.pending_claims)
        st.caption("Exact one-page verification is required before export.")
        if st.button("Export reviewed cover letter", key="export_cover_letter", disabled=not can_export):
            try:
                with TemporaryDirectory() as directory:
                    exported = service.export_cover_letter(letter, Path(directory))
                    st.session_state["cover_letter"] = exported
                    st.download_button(
                        "Download cover-letter DOCX",
                        Path(exported.export_path).read_bytes(),
                        "cover-letter.docx",
                        key="download_cover_letter",
                    )
                    st.success(f"Verified exactly one page via {exported.page_count}-page DOCX measurement.")
            except (ValueError, PageOverflowError) as error:
                st.error(f"Cover-letter export failed: {error}")


def _editor_widget_key(token: str, *parts: object) -> str:
    return "profile-editor-" + sha256((token + ":" + ":".join(map(str, parts))).encode()).hexdigest()[:18]


def _comma_text(value: list[str]) -> str:
    return ", ".join(value)


def render_profile_editor(profile: MasterProfile) -> None:
    """Render the structured editor; all mutations remain session-local until save."""

    source_key = st.session_state.get("profile_editor_source_key", f"saved:{profile.id}")
    initialize_profile_editor(profile, source_key)
    state = st.session_state["profile_editor_state"]
    token = str(source_key)
    st.divider()
    st.header("Structured master-profile editor")
    st.caption("Review and correct the profile locally. Nothing is persisted until you validate and save it.")

    with st.expander("Personal information", expanded=True):
        state["display_name"] = st.text_input("Candidate name", state.get("display_name", ""), key=_editor_widget_key(token, "name"))
        contact = state.setdefault("contact", {})
        contact["phone"] = st.text_input("Phone", contact.get("phone", ""), key=_editor_widget_key(token, "phone"))
        contact["email"] = st.text_input("Email", contact.get("email", ""), key=_editor_widget_key(token, "email"))
        contact["location"] = st.text_input("Meaningful location", contact.get("location", ""), key=_editor_widget_key(token, "location"))
        if str(contact.get("location", "")).strip().casefold() == "canada":
            st.warning("A standalone country is not a meaningful resume location; it will be omitted on save.")
        st.markdown("**Links**")
        for index, link in enumerate(list(contact.get("links", []))):
            link_key = link.get("id", f"link-{index}")
            cols = st.columns([5, 1])
            with cols[0]:
                link["value"] = st.text_input(
                    f"Link {index + 1}", link.get("value", ""), key=_editor_widget_key(token, "link", link_key)
                )
            with cols[1]:
                if st.button("Remove", key=_editor_widget_key(token, "remove-link", link_key)):
                    contact["links"].pop(index)
                    st.rerun()
        if st.button("Add link", key=_editor_widget_key(token, "add-link")):
            used = {item.get("id") for item in contact.get("links", [])}
            contact.setdefault("links", []).append({"id": f"link-{len(used)}", "value": ""})
            st.rerun()

    with st.expander("Education", expanded=True):
        for index, record in enumerate(state.get("education", [])):
            with st.container(border=True):
                st.markdown(f"**Education {index + 1}**")
                record["school"] = st.text_input("Institution", record.get("school", ""), key=_editor_widget_key(token, "education", index, "school"))
                record["program"] = st.text_input("Degree or program", record.get("program", ""), key=_editor_widget_key(token, "education", index, "program"))
                c1, c2 = st.columns(2)
                with c1:
                    record["minor_or_specialization"] = st.text_input("Minor or specialization", record.get("minor_or_specialization", ""), key=_editor_widget_key(token, "education", index, "minor"))
                    record["start_date"] = st.text_input("Start date", record.get("start_date", ""), key=_editor_widget_key(token, "education", index, "start"))
                    record["graduation_date"] = st.text_input("Graduation date", record.get("graduation_date", ""), key=_editor_widget_key(token, "education", index, "graduation"))
                    record["location"] = st.text_input("Location", record.get("location", ""), key=_editor_widget_key(token, "education", index, "location"))
                with c2:
                    record["co_op_designation"] = st.text_input("Co-op designation", record.get("co_op_designation", ""), key=_editor_widget_key(token, "education", index, "coop"))
                    record["expected_graduation_date"] = st.text_input("Expected graduation date", record.get("expected_graduation_date", ""), key=_editor_widget_key(token, "education", index, "expected"))
                    record["gpa"] = st.text_input("GPA", record.get("gpa", ""), key=_editor_widget_key(token, "education", index, "gpa"))
                record["awards"] = st.text_input("Awards (comma-separated)", _comma_text(record.get("awards", [])), key=_editor_widget_key(token, "education", index, "awards")).split(",")
                record["relevant_coursework"] = st.text_input("Relevant coursework (comma-separated)", _comma_text(record.get("relevant_coursework", [])), key=_editor_widget_key(token, "education", index, "coursework")).split(",")
                buttons = st.columns(3)
                with buttons[0]:
                    if st.button("Move up", key=_editor_widget_key(token, "education-up", index)) and index > 0:
                        state = move_item(state, "education", index, -1)
                        st.session_state["profile_editor_state"] = state
                        st.rerun()
                with buttons[1]:
                    if st.button("Move down", key=_editor_widget_key(token, "education-down", index)) and index < len(state.get("education", [])) - 1:
                        state = move_item(state, "education", index, 1)
                        st.session_state["profile_editor_state"] = state
                        st.rerun()
                with buttons[2]:
                    if st.button("Remove education", key=_editor_widget_key(token, "education-remove", index)):
                        st.session_state["profile_editor_state"] = remove_education(state, index)
                        st.rerun()
        if st.button("Add education", key=_editor_widget_key(token, "education-add")):
            st.session_state["profile_editor_state"] = add_education(state)
            st.rerun()

    def render_entries(kind: str, heading: str) -> None:
        with st.expander(heading, expanded=True):
            for index, entry in enumerate(state.get(kind, [])):
                entry_id = entry.get("id", f"{kind}-{index}")
                with st.container(border=True):
                    st.markdown(f"**{heading[:-1]} {index + 1}** · `{entry_id}`")
                    entry["title"] = st.text_input("Name or title", entry.get("title", ""), key=_editor_widget_key(token, kind, entry_id, "title"))
                    entry["organization"] = st.text_input("Employer or organization", entry.get("organization", ""), key=_editor_widget_key(token, kind, entry_id, "organization"))
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        entry["start_date"] = st.text_input("Start date", entry.get("start_date", ""), key=_editor_widget_key(token, kind, entry_id, "start"))
                    with c2:
                        entry["end_date"] = st.text_input("End date", entry.get("end_date", ""), key=_editor_widget_key(token, kind, entry_id, "end"))
                    with c3:
                        entry["location"] = st.text_input("Location", entry.get("location", ""), key=_editor_widget_key(token, kind, entry_id, "location"))
                    entry["subtitle"] = st.text_input("Subtitle", entry.get("subtitle", ""), key=_editor_widget_key(token, kind, entry_id, "subtitle"))
                    entry["technology_label"] = st.text_input("Technology label", entry.get("technology_label", ""), key=_editor_widget_key(token, kind, entry_id, "technology-label"))
                    entry["award_or_placement"] = st.text_input("Award or placement", entry.get("award_or_placement", ""), key=_editor_widget_key(token, kind, entry_id, "award"))
                    entry["technologies"] = st.text_input("Technologies (comma-separated)", _comma_text(entry.get("technologies", [])), key=_editor_widget_key(token, kind, entry_id, "technologies")).split(",")
                    entry["capabilities"] = st.text_input("Capabilities (comma-separated)", _comma_text(entry.get("capabilities", [])), key=_editor_widget_key(token, kind, entry_id, "capabilities")).split(",")
                    entry["description"] = st.text_area("Description", entry.get("description", ""), key=_editor_widget_key(token, kind, entry_id, "description"))
                    st.markdown("**Evidence statements / bullets**")
                    for bullet_index, bullet in enumerate(list(entry.get("bullets", []))):
                        bullet_id = bullet.get("id", f"bullet-{bullet_index}")
                        bullet["text"] = st.text_area(f"Bullet {bullet_index + 1} · {bullet_id}", bullet.get("text", ""), key=_editor_widget_key(token, kind, entry_id, "bullet", bullet_id))
                        bullet["source_reference"] = st.text_input("Evidence source reference", bullet.get("source_reference", "") or "", key=_editor_widget_key(token, kind, entry_id, "bullet-source", bullet_id))
                        bullet["technologies"] = st.text_input("Evidence technologies", _comma_text(bullet.get("technologies", [])), key=_editor_widget_key(token, kind, entry_id, "bullet-tech", bullet_id)).split(",")
                        bullet["capabilities"] = st.text_input("Evidence capabilities", _comma_text(bullet.get("capabilities", [])), key=_editor_widget_key(token, kind, entry_id, "bullet-cap", bullet_id)).split(",")
                        bullet["outcomes"] = st.text_input("Evidence outcomes", _comma_text(bullet.get("outcomes", [])), key=_editor_widget_key(token, kind, entry_id, "bullet-outcomes", bullet_id)).split(",")
                        bullet["confirmed"] = st.checkbox("Evidence is confirmed", bool(bullet.get("confirmed", True)), key=_editor_widget_key(token, kind, entry_id, "bullet-confirmed", bullet_id))
                        if st.button("Remove bullet", key=_editor_widget_key(token, kind, entry_id, "bullet-remove", bullet_id)):
                            st.session_state["profile_editor_state"] = remove_bullet(state, kind, entry_id, bullet_id)
                            st.rerun()
                    if st.button("Add bullet", key=_editor_widget_key(token, kind, entry_id, "bullet-add")):
                        st.session_state["profile_editor_state"] = add_bullet(state, kind, entry_id)
                        st.rerun()
                    buttons = st.columns(4)
                    with buttons[0]:
                        if st.button("Move up", key=_editor_widget_key(token, kind, entry_id, "up")) and index > 0:
                            st.session_state["profile_editor_state"] = move_item(state, kind, index, -1)
                            st.rerun()
                    with buttons[1]:
                        if st.button("Move down", key=_editor_widget_key(token, kind, entry_id, "down")) and index < len(state.get(kind, [])) - 1:
                            st.session_state["profile_editor_state"] = move_item(state, kind, index, 1)
                            st.rerun()
                    with buttons[2]:
                        if st.button("Remove entry", key=_editor_widget_key(token, kind, entry_id, "remove")):
                            st.session_state["profile_editor_state"] = remove_entry(state, kind, entry_id)
                            st.rerun()
            if st.button(f"Add {heading[:-1].lower()}", key=_editor_widget_key(token, kind, "add")):
                st.session_state["profile_editor_state"] = add_entry(state, kind)  # type: ignore[arg-type]
                st.rerun()

    render_entries("experiences", "Experiences")
    render_entries("projects", "Projects")

    with st.expander("Technical skills", expanded=True):
        state["declared_skills"] = st.text_input(
            "Legacy declared skills (comma-separated)",
            _comma_text(state.get("declared_skills", [])),
            key=_editor_widget_key(token, "declared-skills"),
        ).split(",")
        for index, category in enumerate(list(state.get("technical_skills", []))):
            category_id = category.get("id", f"category-{index}")
            category["category"] = st.text_input("Category name", category.get("category", ""), key=_editor_widget_key(token, "category", category_id, "label"))
            for skill_index, skill in enumerate(list(category.get("skills", []))):
                skill_id = skill.get("id") or f"skill-{skill_index}"
                cols = st.columns([5, 1])
                with cols[0]:
                    skill["value"] = st.text_input("Skill", skill.get("value", ""), key=_editor_widget_key(token, "category", category_id, "skill", skill_id))
                with cols[1]:
                    if st.button("Remove", key=_editor_widget_key(token, "category", category_id, "skill-remove", skill_id)):
                        category["skills"].pop(skill_index)
                        st.rerun()
            if st.button("Add skill", key=_editor_widget_key(token, "category", category_id, "skill-add")):
                category.setdefault("skills", []).append({"id": None, "value": ""})
                st.rerun()
            if st.button("Remove category", key=_editor_widget_key(token, "category", category_id, "remove")):
                st.session_state["profile_editor_state"] = remove_skill_category(state, category_id)
                st.rerun()
        if st.button("Add skill category", key=_editor_widget_key(token, "category-add")):
            st.session_state["profile_editor_state"] = add_skill_category(state)
            st.rerun()

    errors = st.session_state.get("profile_editor_errors", [])
    for error in errors:
        st.error(error)
    if st.button("Validate and Save Profile", type="primary", key=_editor_widget_key(token, "save")):
        try:
            edited_profile = editor_state_to_profile(state)
            if edited_profile.id != profile.id:
                raise ValueError("Profile ID cannot be changed in the editor.")
            if persist_profile_from_editor(edited_profile):
                st.success("Validated profile saved. Downstream documents were refreshed only if the profile changed.")
        except (ValidationError, ValueError, TypeError) as error:
            st.session_state["profile_editor_errors"] = [str(error)]
            st.error(f"Profile was not saved: {error}")

    with st.expander("Advanced fallback: raw profile JSON"):
        st.caption("Use this only for schema fields not yet exposed above. It uses the same domain validation and SQLite save pathway.")
        raw = st.text_area("Raw profile JSON", key="profile_editor_raw_json", height=260)
        if st.button("Validate and Save Raw JSON", key=_editor_widget_key(token, "raw-save")):
            try:
                raw_payload = json.loads(raw)
                if not isinstance(raw_payload, dict):
                    raise ValueError("Profile JSON must be an object.")
                unknown = unknown_profile_fields(raw_payload)
                if unknown:
                    raise ValueError("Unsupported top-level fields cannot be safely round-tripped: " + ", ".join(unknown))
                raw_profile = MasterProfile.model_validate(raw_payload)
                if raw_profile.id != profile.id:
                    raise ValueError("Profile ID cannot be changed in the editor.")
                if persist_profile_from_editor(raw_profile):
                    st.success("Validated raw profile saved.")
            except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as error:
                st.session_state["profile_editor_errors"] = [str(error)]
                st.error(f"Raw profile was not saved: {error}")


active_editor_profile = (
    draft_output.profile
    if draft_output is not None
    else st.session_state.get("profile")
)
if active_editor_profile is not None:
    render_profile_editor(active_editor_profile)
