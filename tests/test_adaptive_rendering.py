import importlib.util
from pathlib import Path
from types import ModuleType
from zipfile import ZipFile

from docx import Document

from resume_tailor.domain.models import (
    ClaimSupport,
    EducationRecord,
    EntityKind,
    ResumeItem,
    ResumeStrategy,
    StructuredBullet,
    StructuredResume,
    TechnicalSkillCategory,
)
from resume_tailor.infrastructure.adaptive_docx import render_structured_resume
from resume_tailor.infrastructure.reference_docx import analyze_reference_docx


REFERENCE = Path("manual-test/reference-resume.docx")


def _load_manual_render_module() -> ModuleType:
    path = Path("manual-test/render_deterministic_docx.py")
    spec = importlib.util.spec_from_file_location("manual_render_deterministic_docx", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _resume() -> StructuredResume:
    experience = ResumeItem(
        id="experience-alpha",
        title="Systems Integration Engineer",
        kind=EntityKind.EXPERIENCE,
        organization="Example Research Cooperative",
        start_date="May 2024",
        end_date="Aug 2025",
        location="Example City, ZZ",
        subtitle="Embedded Controls",
    )
    project = ResumeItem(
        id="project-beta",
        title="Adaptive Sensor Platform",
        kind=EntityKind.PROJECT,
        start_date="Jan 2024",
        end_date="Apr 2024",
        technology_label="Python, ROS 2",
    )
    return StructuredResume(
        profile_id="adaptive-profile",
        profile_version=1,
        posting_id="adaptive-posting",
        template_id="reference-derived",
        display_name="Alex Example",
        contact_line=(
            "alex@example.test | +1 555 0100 | example.test/portfolio | Example City, ZZ"
        ),
        strategy=ResumeStrategy(
            role_family="software_data_engineering",
            primary_focus="systems integration",
            rationale="Synthetic grounded fixture.",
        ),
        education=[
            EducationRecord(
                school="Example Polytechnic Institute",
                program="Bachelor of Applied Engineering, Systems Option",
                start_date="Sep 2021",
                expected_graduation_date="Apr 2026",
                location="Example City, ZZ",
                gpa="3.8/4.0",
                awards=["Example Merit Award", "Design Showcase Finalist"],
                relevant_coursework=["Control Systems", "Embedded Computing"],
            )
        ],
        technical_skills=[
            TechnicalSkillCategory(
                category="Future Integration Toolchain",
                values=["Python", "ROS 2", "Docker", "A Very Long Verified Tool Name"],
            ),
            TechnicalSkillCategory(
                category="Prototype Hardware",
                values=["STM32", "SPI"],
            ),
        ],
        experiences=[experience],
        projects=[project],
        entity_titles={experience.id: experience.title, project.id: project.title},
        experience_bullets={
            experience.id: [
                StructuredBullet(
                    id="experience-evidence",
                    text=(
                        "Integrated verified embedded controls and sensor interfaces for a "
                        "reusable prototype platform."
                    ),
                    evidence_ids=["experience-evidence"],
                    support=ClaimSupport.DIRECT,
                )
            ]
        },
        project_bullets={
            project.id: [
                StructuredBullet(
                    id="project-evidence",
                    text="Built a verified telemetry workflow using Python and ROS 2.",
                    evidence_ids=["project-evidence"],
                    support=ClaimSupport.DIRECT,
                )
            ]
        },
    )


def _paragraph(document: Document, text: str):
    return next(paragraph for paragraph in document.paragraphs if paragraph.text == text)


def test_adaptive_renderer_maps_complete_structured_resume_without_mutation(tmp_path: Path) -> None:
    before_reference = REFERENCE.read_bytes()
    profile = analyze_reference_docx(REFERENCE)
    resume = _resume()
    before_resume = resume.model_dump(mode="json")
    output = tmp_path / "adaptive.docx"

    render_structured_resume(resume, profile, output)

    assert output.exists()
    assert REFERENCE.read_bytes() == before_reference
    assert resume.model_dump(mode="json") == before_resume
    document = Document(output)
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    for expected in (
        "Alex Example",
        "Example Polytechnic Institute",
        "Sep 2021",
        "Apr 2026",
        "Bachelor of Applied Engineering, Systems Option",
        "Example City, ZZ",
        "GPA: 3.8/4.0",
        "Example Merit Award",
        "Control Systems",
        "Future Integration Toolchain:",
        "Python, ROS 2, Docker, A Very Long Verified Tool Name",
        "Prototype Hardware:",
        "Systems Integration Engineer | Embedded Controls",
        "Example Research Cooperative",
        "May 2024",
        "Aug 2025",
        "Adaptive Sensor Platform | Python, ROS 2",
        "Jan 2024",
        "Apr 2024",
    ):
        assert expected in text
    assert text.count("Integrated verified embedded controls") == 1
    assert text.count("Built a verified telemetry workflow") == 1


def test_page_header_contact_and_section_formatting_come_from_profile(tmp_path: Path) -> None:
    profile = analyze_reference_docx(REFERENCE)
    changed_page = profile.page.model_copy(
        update={"left_margin_twips": profile.page.left_margin_twips + 137}
    )
    changed_profile = profile.model_copy(update={"page": changed_page})
    output = tmp_path / "geometry.docx"
    render_structured_resume(_resume(), changed_profile, output)
    document = Document(output)
    section = document.sections[0]

    assert section.page_width.twips == changed_page.width_twips
    assert section.page_height.twips == changed_page.height_twips
    assert section.left_margin.twips == changed_page.left_margin_twips
    assert section.right_margin.twips == changed_page.right_margin_twips
    name = document.paragraphs[0]
    contact = document.paragraphs[1]
    if profile.semantic_roles["name"].paragraph.alignment.value == "center":
        assert name.alignment == 1
    assert contact.alignment == 1
    expected_family = profile.semantic_roles["name"].primary_typography.font_family.value
    if expected_family:
        assert name.runs[0].font.name == expected_family
    expected_size = profile.semantic_roles["name"].primary_typography.font_size_half_points.value
    if isinstance(expected_size, int):
        assert name.runs[0].font.size.pt == expected_size / 2
    for label in ("Education", "Technical Skills", "Technical Experience", "Projects"):
        heading = _paragraph(document, label)
        assert heading.style.name == "Normal"
        assert heading._p.pPr.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pBdr") is not None
        assert heading.runs[0].font.color.rgb is None or str(heading.runs[0].font.color.rgb) != "2F5496"


def test_contact_hyperlinks_are_compact_and_missing_fields_leave_no_separators(
    tmp_path: Path,
) -> None:
    profile = analyze_reference_docx(REFERENCE)
    output = tmp_path / "contact.docx"
    render_structured_resume(_resume(), profile, output)
    document = Document(output)
    contact = document.paragraphs[1]
    assert contact.text.count("|") == 3
    with ZipFile(output) as package:
        relationships = package.read("word/_rels/document.xml.rels").decode()
        assert "mailto:alex@example.test" in relationships
        assert "https://example.test/portfolio" in relationships

    missing = _resume().model_copy(update={"contact_line": "alex@example.test"})
    missing_output = tmp_path / "missing-contact.docx"
    render_structured_resume(missing, profile, missing_output)
    missing_contact = Document(missing_output).paragraphs[1]
    assert missing_contact.text == "alex@example.test"
    assert "|" not in missing_contact.text


def test_metadata_uses_real_tabs_and_skills_remain_separate_categories(tmp_path: Path) -> None:
    profile = analyze_reference_docx(REFERENCE)
    output = tmp_path / "tabs-skills.docx"
    render_structured_resume(_resume(), profile, output)
    document = Document(output)
    skill_rows = [
        paragraph
        for paragraph in document.paragraphs
        if paragraph.text.startswith(("Future Integration Toolchain:", "Prototype Hardware:"))
    ]
    assert len(skill_rows) == 2
    assert skill_rows[0].runs[0].bold is True
    assert skill_rows[0].paragraph_format.left_indent is not None
    assert skill_rows[0].paragraph_format.first_line_indent is not None
    with ZipFile(output) as package:
        document_xml = package.read("word/document.xml").decode()
        assert "<w:tabs>" in document_xml
        assert "<w:tab/>" in document_xml or "<w:tab " in document_xml
        assert "May 2024    Aug 2025" not in document_xml


def test_categorized_skills_override_conflicting_legacy_flat_field(tmp_path: Path) -> None:
    profile = analyze_reference_docx(REFERENCE)
    resume = _resume().model_copy(update={"selected_skills": ["Legacy Flat Value"]})
    output = tmp_path / "categorized-authority.docx"

    render_structured_resume(resume, profile, output)

    text = "\n".join(paragraph.text for paragraph in Document(output).paragraphs)
    assert "Future Integration Toolchain: Python, ROS 2, Docker" in text
    assert "Prototype Hardware: STM32, SPI" in text
    assert "Legacy Flat Value" not in text
    assert "Skills:" not in text


def test_complete_metadata_and_project_section_are_consumed_from_structured_resume(
    tmp_path: Path,
) -> None:
    profile = analyze_reference_docx(REFERENCE)
    output = tmp_path / "complete-consumption.docx"
    render_structured_resume(_resume(), profile, output)
    document = Document(output)
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)

    for value in (
        "Sep 2021",
        "Apr 2026",
        "Example City, ZZ",
        "Example Merit Award",
        "Control Systems",
        "May 2024",
        "Aug 2025",
        "Example Research Cooperative",
        "Adaptive Sensor Platform",
        "Projects",
    ):
        assert value in text
    with ZipFile(output) as package:
        xml = package.read("word/document.xml").decode()
        assert xml.count("<w:tab/>") >= 4


def test_empty_projects_do_not_create_an_empty_section(tmp_path: Path) -> None:
    profile = analyze_reference_docx(REFERENCE)
    resume = _resume().model_copy(update={"projects": [], "project_bullets": {}})
    output = tmp_path / "no-projects.docx"
    render_structured_resume(resume, profile, output)
    assert "Projects" not in [paragraph.text for paragraph in Document(output).paragraphs]


def test_manual_generation_uses_current_plan_and_structured_resume_flow() -> None:
    module = _load_manual_render_module()
    master_profile, plan, resume = module.build_manual_resume()
    diagnostic = module.field_presence_diagnostic(master_profile, plan, resume)

    assert resume.education == plan.education
    assert resume.technical_skills == plan.technical_skills
    assert resume.experiences == plan.selected_experiences
    assert resume.projects == plan.selected_projects
    assert diagnostic["structured_resume"]["technical_skill_category_count"] == len(
        resume.technical_skills
    )
    assert "contact" not in str(diagnostic).casefold()
    assert "bullet_text" not in str(diagnostic).casefold()


def test_bullets_use_profile_marker_indentation_and_role_spacing(tmp_path: Path) -> None:
    profile = analyze_reference_docx(REFERENCE)
    output = tmp_path / "bullets.docx"
    render_structured_resume(_resume(), profile, output)
    document = Document(output)
    experience_bullet = next(
        paragraph
        for paragraph in document.paragraphs
        if "Integrated verified embedded controls" in paragraph.text
    )
    bullet_role = profile.semantic_roles["experience_bullet"]
    assert experience_bullet.paragraph_format.left_indent.twips == bullet_role.bullet.left_indent_twips
    assert experience_bullet.paragraph_format.first_line_indent.twips == -bullet_role.bullet.hanging_indent_twips
    assert experience_bullet.text.startswith(experience_bullet.runs[0].text.rstrip("\t"))
    title = next(
        paragraph
        for paragraph in document.paragraphs
        if paragraph.text.startswith("Systems Integration Engineer")
    )
    employer = _paragraph(document, "Example Research Cooperative\tExample City, ZZ")
    assert title.paragraph_format.space_before != experience_bullet.paragraph_format.space_before
    assert employer.paragraph_format.space_before != title.paragraph_format.space_before
