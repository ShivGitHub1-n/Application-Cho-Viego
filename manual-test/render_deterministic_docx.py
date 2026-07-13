from __future__ import annotations

import json
from pathlib import Path

from resume_tailor.application.services import TailorResumeService
from resume_tailor.domain.models import (
    JobPosting,
    MasterProfile,
    StructuredResume,
    TailoringPlan,
    TemplateConstraints,
)
from resume_tailor.infrastructure.optimization import (
    DeterministicResumeOptimizer,
    EvidenceBoundResumeWriter,
)
from resume_tailor.infrastructure.rendering import ManagedResumeRenderer


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "manual-test" / "generated-reference-layout-resume.docx"


def build_manual_resume() -> tuple[MasterProfile, TailoringPlan, StructuredResume]:
    profile_payload = json.loads(
        (ROOT / "manual-test" / "profile.json").read_text(encoding="utf-8")
    )
    for education in profile_payload.get("education", []):
        if education.get("gpa") is not None:
            education["gpa"] = str(education["gpa"])
    profile = MasterProfile.model_validate(profile_payload)
    description = (ROOT / "manual-test" / "job-description.txt.txt").read_text(
        encoding="utf-8"
    )
    posting = JobPosting(
        id="manual-reference-render",
        title="AI Researcher Co-op",
        description=description,
    )
    service = TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
    )
    plan = service.create_plan(profile, posting, TemplateConstraints())
    resume = service.build_document(plan, profile, set())
    return profile, plan, resume


def field_presence_diagnostic(
    profile: MasterProfile,
    plan: TailoringPlan,
    resume: StructuredResume,
) -> dict[str, object]:
    """Report structure only; never emit contact values or evidence text."""

    def education(records: list[object]) -> dict[str, object]:
        return {
            "records": len(records),
            "start_date_present": [bool(item.start_date) for item in records],
            "graduation_date_present": [
                bool(item.expected_graduation_date or item.graduation_date)
                for item in records
            ],
            "location_present": [bool(item.location) for item in records],
            "awards_count": [len(item.awards) for item in records],
            "coursework_count": [len(item.relevant_coursework) for item in records],
        }

    def entries(records: list[object], bullet_counts: dict[str, int]) -> dict[str, object]:
        return {
            "count": len(records),
            "dates_present": [bool(item.start_date or item.end_date) for item in records],
            "locations_present": [bool(item.location) for item in records],
            "selected_bullet_counts": [bullet_counts.get(item.id, 0) for item in records],
        }

    return {
        "master_profile": {
            "education": education(profile.education),
            "technical_skill_category_count": len(profile.technical_skills),
            "skills_per_category": [len(item.skills) for item in profile.technical_skills],
            "experience_count": len(profile.experiences),
            "project_count": len(profile.projects),
            "top_level_coursework_count": len(profile.coursework),
        },
        "tailoring_plan": {
            "education": education(plan.education),
            "technical_skill_category_count": len(plan.technical_skills),
            "skills_per_category": [len(item.skills) for item in plan.technical_skills],
            "legacy_selected_skill_count": len(plan.selected_skills),
            "selected_coursework_count": len(plan.selected_coursework),
            "experience_count": len(plan.selected_experiences),
            "project_count": len(plan.selected_projects),
        },
        "structured_resume": {
            "education": education(resume.education),
            "technical_skill_category_count": len(resume.technical_skills),
            "skills_per_category": [len(item.skills) for item in resume.technical_skills],
            "legacy_selected_skill_count": len(resume.selected_skills),
            "selected_coursework_count": len(resume.selected_coursework),
            "experiences": entries(
                resume.experiences,
                {key: len(value) for key, value in resume.experience_bullets.items()},
            ),
            "projects": entries(
                resume.projects,
                {key: len(value) for key, value in resume.project_bullets.items()},
            ),
        },
    }


def main() -> None:
    profile, plan, resume = build_manual_resume()
    print(json.dumps({"field_presence": field_presence_diagnostic(profile, plan, resume)}, indent=2))
    ManagedResumeRenderer().render_docx(resume, OUTPUT)
    print(json.dumps({"output": str(OUTPUT), "selected_claim_ids": plan.selected_claim_ids}))


if __name__ == "__main__":
    main()
