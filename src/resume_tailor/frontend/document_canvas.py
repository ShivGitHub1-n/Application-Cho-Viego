"""Document-oriented review surfaces; rendering authority stays in infrastructure."""

from __future__ import annotations

from typing import Any


def generated_resume_groups(resume: Any) -> dict[str, list[str]]:
    """Group generated text for review without creating new source evidence."""

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
    experience: list[str] = []
    for entity_id, bullets in resume.experience_bullets.items():
        title = resume.entity_titles.get(entity_id, entity_id)
        experience.extend(f"{title}: {bullet.text}" for bullet in bullets)
    projects: list[str] = []
    for entity_id, bullets in resume.project_bullets.items():
        title = resume.entity_titles.get(entity_id, entity_id)
        projects.extend(f"{title}: {bullet.text}" for bullet in bullets)
    return {
        "Education": education,
        "Technical skills": skills,
        "Experience": experience,
        "Projects": projects,
    }


def render_document_canvas(
    streamlit_module: Any,
    *,
    title: str,
    sections: dict[str, list[str]],
    caption: str,
) -> None:
    """Render text as a review canvas, never as a replacement DOCX renderer."""

    with streamlit_module.container(key="pw-document-canvas", border=True):
        streamlit_module.markdown(f"### {title}")
        streamlit_module.caption(caption)
        for heading, items in sections.items():
            if not items:
                continue
            streamlit_module.markdown(f"**{heading}**")
            for item in items:
                streamlit_module.write(item)


__all__ = ["generated_resume_groups", "render_document_canvas"]
