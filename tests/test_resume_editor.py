from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import pytest
from docx import Document
from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen.canvas import Canvas

from resume_tailor.application.resume_editor import (
    ResumeEditorApprovalError,
    ResumeEditorError,
    ResumeEditorGroundingError,
    ResumeEditorService,
    omitted_reviewed_entries,
    resume_editor_application_fingerprint,
)
from resume_tailor.domain.hybrid_resume import BulletVariantRecord
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
from resume_tailor.frontend.resume_editor import (
    exact_preview_pdf_bytes,
    suggestion_presentation,
)
from resume_tailor.infrastructure.resume_editor_rendering import (
    TemplateV1ResumeEditorRenderer,
    render_pdf_preview_pages,
)

FRONTEND_PATH = (
    Path(__file__).parents[1] / "src" / "resume_tailor" / "frontend" / "resume_editor.py"
)


class _Renderer:
    def __init__(self) -> None:
        self.calls = 0

    def render(
        self,
        resume: StructuredResume,
        *,
        source_docx_bytes: bytes | None = None,
    ) -> ResumeEditorRender:
        self.calls += 1
        bullet_count = sum(
            len(items)
            for section in (resume.experience_bullets, resume.project_bullets)
            for items in section.values()
        )
        pages = 2 if bullet_count > 5 else 1
        payload = source_docx_bytes or resume.model_dump_json().encode()
        return ResumeEditorRender(
            document_fingerprint=f"render-{self.calls}",
            docx_bytes=payload,
            pdf_bytes=b"%PDF-test",
            page_count=pages,
            exact_pagination=True,
            pagination_provider="exact test renderer",
            utilization_ratio=0.84 if pages == 1 else 1.2,
            status=(
                ResumeEditorFitStatus.FITS_ONE_PAGE
                if pages == 1
                else ResumeEditorFitStatus.EXCEEDS_ONE_PAGE
            ),
        )


def _profile() -> MasterProfile:
    experience = ResumeItem(
        id="exp-controls",
        title="Controls Engineer",
        kind=EntityKind.EXPERIENCE,
        organization="Northstar Mobility",
    )
    project = ResumeItem(
        id="project-hand",
        title="Robotic Hand",
        kind=EntityKind.PROJECT,
    )
    omitted = ResumeItem(
        id="project-arm",
        title="Long Reach Manipulator",
        kind=EntityKind.PROJECT,
    )
    return MasterProfile(
        id="profile-editor",
        user_id="user-editor",
        display_name="Candidate",
        experiences=[experience],
        projects=[project, omitted],
        technical_skills=[
            TechnicalSkillCategory(category="Languages", values=["C++", "Python"]),
            TechnicalSkillCategory(category="Design", values=["SolidWorks"]),
        ],
        evidence=[
            EvidenceItem(
                id="e-fw",
                entity_id=experience.id,
                source_text="Developed STM32 control firmware in C++ for actuator feedback.",
                technologies=["STM32", "C++"],
                capabilities=["control firmware", "actuator feedback"],
            ),
            EvidenceItem(
                id="e-wire",
                entity_id=experience.id,
                source_text="Built and validated vehicle wiring harnesses for control hardware.",
                technologies=["wiring harnesses"],
                capabilities=["hardware validation"],
            ),
            EvidenceItem(
                id="e-hand",
                entity_id=project.id,
                source_text="Validated three servo channels through 500 actuation cycles.",
                technologies=["servos"],
                outcomes=["500 actuation cycles"],
            ),
            EvidenceItem(
                id="e-arm-cad",
                entity_id=omitted.id,
                source_text="Designed a SolidWorks actuator bracket for a long-reach arm.",
                technologies=["SolidWorks"],
                capabilities=["actuator bracket"],
            ),
            EvidenceItem(
                id="e-arm-test",
                entity_id=omitted.id,
                source_text="Tested the arm transmission under repeated extension loads.",
                capabilities=["transmission testing"],
            ),
        ],
    )


def _bullet(
    bullet_id: str,
    text: str,
    evidence_ids: list[str],
    *,
    entry_id: str | None = None,
) -> StructuredBullet:
    variant = (
        BulletVariantRecord.model_construct(
            variant_id=bullet_id,
            entry_id=entry_id,
            source_evidence_ids=evidence_ids,
        )
        if entry_id
        else None
    )
    return StructuredBullet(
        id=bullet_id,
        text=text,
        evidence_ids=evidence_ids,
        support=ClaimSupport.DIRECT,
        writing_variant=variant,
    )


def _resume(profile: MasterProfile | None = None) -> StructuredResume:
    profile = profile or _profile()
    return StructuredResume(
        profile_id=profile.id,
        profile_version=profile.version,
        posting_id="posting-editor",
        template_id="managed-engineering-v1",
        display_name=profile.display_name,
        strategy=ResumeStrategy(
            role_family="embedded",
            primary_focus="Embedded controls",
            rationale="Use reviewed controls evidence.",
        ),
        entity_titles={item.id: item.title for item in [*profile.experiences, *profile.projects]},
        technical_skills=[profile.technical_skills[0].model_copy(deep=True)],
        experiences=[profile.experiences[0].model_copy(deep=True)],
        projects=[profile.projects[0].model_copy(deep=True)],
        experience_bullets={
            "exp-controls": [
                _bullet(
                    "bullet-fw",
                    profile.evidence[0].source_text,
                    ["e-fw"],
                ),
                _bullet(
                    "bullet-wire",
                    profile.evidence[1].source_text,
                    ["e-wire"],
                ),
            ]
        },
        project_bullets={
            "project-hand": [
                _bullet(
                    "bullet-hand",
                    profile.evidence[2].source_text,
                    ["e-hand"],
                )
            ]
        },
    )


def test_manual_edit_changes_only_application_resume_and_retains_provenance() -> None:
    profile = _profile()
    resume = _resume(profile)
    service = ResumeEditorService(_Renderer())

    edited = service.edit_bullet(
        resume,
        profile,
        entry_id="exp-controls",
        bullet_id="bullet-fw",
        text="Developed C++ STM32 control firmware for actuator feedback.",
    )

    assert edited.experience_bullets["exp-controls"][0].text.startswith("Developed C++")
    assert edited.experience_bullets["exp-controls"][0].evidence_ids == ["e-fw"]
    assert resume.experience_bullets["exp-controls"][0].text.startswith("Developed STM32")
    assert profile.evidence[0].source_text.startswith("Developed STM32")


def test_manual_edit_rejects_unsupported_job_keyword() -> None:
    with pytest.raises(ResumeEditorGroundingError):
        ResumeEditorService(_Renderer()).edit_bullet(
            _resume(),
            _profile(),
            entry_id="exp-controls",
            bullet_id="bullet-fw",
            text="Owned ISO 26262 certification for production motor controllers.",
        )


def test_delete_reorder_and_final_bullet_removal_preserve_entry_invariants() -> None:
    service = ResumeEditorService(_Renderer())
    resume = _resume()
    reordered = service.move_bullet(
        resume, entry_id="exp-controls", bullet_id="bullet-wire", offset=-1
    )
    assert reordered.experience_bullets["exp-controls"][0].id == "bullet-wire"
    one_left = service.remove_bullet(
        reordered, entry_id="exp-controls", bullet_id="bullet-fw"
    )
    removed = service.remove_bullet(
        one_left, entry_id="exp-controls", bullet_id="bullet-wire"
    )
    assert "exp-controls" not in removed.experience_bullets
    assert not removed.experiences


def test_direct_and_multi_source_suggestions_do_not_fake_one_current_bullet() -> None:
    service = ResumeEditorService(_Renderer())
    profile = _profile()
    resume = _resume(profile)
    direct = _bullet(
        "suggestion-direct",
        "Developed embedded C++ firmware on STM32 for actuator feedback.",
        ["e-fw"],
        entry_id="exp-controls",
    )
    replaced = service.apply_suggestion(resume, profile, direct)
    assert replaced.experience_bullets["exp-controls"][0].id == "suggestion-direct"
    combined = _bullet(
        "suggestion-combined",
        "Developed STM32 controls and validated the associated wiring harnesses.",
        ["e-fw", "e-wire"],
        entry_id="exp-controls",
    )
    combined_resume = service.apply_suggestion(resume, profile, combined)
    assert [item.id for item in combined_resume.experience_bullets["exp-controls"]] == [
        "suggestion-combined"
    ]
    assert combined_resume.experience_bullets["exp-controls"][0].evidence_ids == [
        "e-fw",
        "e-wire",
    ]

    direct_view = suggestion_presentation(resume, direct, "exp-controls")
    combined_view = suggestion_presentation(resume, combined, "exp-controls")
    assert direct_view.mode == "replacement"
    assert direct_view.current_bullet == resume.experience_bullets["exp-controls"][0].text
    assert combined_view.mode == "evidence_synthesis"
    assert combined_view.current_bullet is None
    assert combined_view.reviewed_fact_count == 2


def test_omitted_project_suggestion_adds_canonical_parent_and_cannot_cross_attach() -> None:
    service = ResumeEditorService(_Renderer())
    profile = _profile()
    suggestion = _bullet(
        "suggestion-arm",
        "Designed a SolidWorks actuator bracket for a long-reach arm.",
        ["e-arm-cad"],
        entry_id="project-arm",
    )
    edited = service.apply_suggestion(_resume(profile), profile, suggestion)
    assert edited.projects[-1].title == "Long Reach Manipulator"
    assert edited.project_bullets["project-arm"][0].id == "suggestion-arm"

    wrong_parent = _bullet(
        "suggestion-wrong",
        "Designed a bracket.",
        ["e-arm-cad"],
        entry_id="project-hand",
    )
    with pytest.raises(ResumeEditorError):
        service.apply_suggestion(_resume(profile), profile, wrong_parent)


def test_entries_can_be_reordered_and_removed_without_losing_parent_identity() -> None:
    service = ResumeEditorService(_Renderer())
    profile = _profile()
    suggestion = _bullet(
        "suggestion-arm-order",
        "Designed a SolidWorks actuator bracket for a long-reach arm.",
        ["e-arm-cad"],
        entry_id="project-arm",
    )
    expanded = service.apply_suggestion(_resume(profile), profile, suggestion)
    reordered = service.move_entry(expanded, entry_id="project-arm", offset=-1)
    assert [item.id for item in reordered.projects] == ["project-arm", "project-hand"]
    assert reordered.project_bullets["project-arm"][0].evidence_ids == ["e-arm-cad"]
    removed = service.remove_entry(reordered, entry_id="project-hand")
    assert [item.id for item in removed.projects] == ["project-arm"]
    assert "project-hand" not in removed.project_bullets


def test_omitted_experience_suggestion_adds_canonical_experience_parent() -> None:
    profile = _profile()
    omitted = ResumeItem(
        id="exp-lab",
        title="Hardware Lab Assistant",
        kind=EntityKind.EXPERIENCE,
        organization="Northstar Lab",
    )
    profile.experiences.append(omitted)
    profile.evidence.append(
        EvidenceItem(
            id="e-lab",
            entity_id=omitted.id,
            source_text="Soldered and inspected prototype control boards.",
            capabilities=["soldering", "inspection"],
        )
    )
    suggestion = _bullet(
        "suggestion-lab",
        "Soldered and inspected prototype control boards.",
        ["e-lab"],
        entry_id=omitted.id,
    )
    edited = ResumeEditorService(_Renderer()).apply_suggestion(
        _resume(profile), profile, suggestion
    )
    assert edited.experiences[-1].title == "Hardware Lab Assistant"
    assert edited.experience_bullets[omitted.id][0].id == "suggestion-lab"


def test_explicit_reviewed_entries_are_canonical_staged_and_parent_bound() -> None:
    renderer = _Renderer()
    service = ResumeEditorService(renderer)
    profile = _profile()
    resume = _resume(profile)
    assert [item.id for item in omitted_reviewed_entries(
        profile, resume, EntityKind.PROJECT
    )] == ["project-arm"]
    assert omitted_reviewed_entries(profile, resume, EntityKind.EXPERIENCE) == []

    staged = service.add_reviewed_entry(
        resume,
        profile,
        entry_id="project-arm",
        evidence_ids=["e-arm-cad", "e-arm-test"],
        expected_kind=EntityKind.PROJECT,
    )
    assert renderer.calls == 0
    assert staged.projects[-1].title == "Long Reach Manipulator"
    assert [item.evidence_ids for item in staged.project_bullets["project-arm"]] == [
        ["e-arm-cad"],
        ["e-arm-test"],
    ]
    assert omitted_reviewed_entries(profile, staged, EntityKind.PROJECT) == []

    service.create_revision(
        staged,
        profile,
        application_fingerprint="application-explicit-entry",
        baseline_artifact_fingerprint="artifact-explicit-entry",
        revision_number=1,
    )
    assert renderer.calls == 1

    with pytest.raises(ResumeEditorError, match="already"):
        service.add_reviewed_entry(
            staged,
            profile,
            entry_id="project-arm",
            evidence_ids=["e-arm-cad"],
            expected_kind=EntityKind.PROJECT,
        )
    with pytest.raises(ResumeEditorError, match="canonical profile parent"):
        service.add_reviewed_entry(
            resume,
            profile,
            entry_id="unreviewed-project",
            evidence_ids=["e-arm-cad"],
            expected_kind=EntityKind.PROJECT,
        )
    with pytest.raises(ResumeEditorError, match="does not belong"):
        service.add_reviewed_entry(
            resume,
            profile,
            entry_id="project-arm",
            evidence_ids=["e-fw"],
            expected_kind=EntityKind.PROJECT,
        )


def test_explicit_reviewed_experience_addition_uses_experience_section() -> None:
    profile = _profile()
    omitted = ResumeItem(
        id="exp-lab-explicit",
        title="Prototype Lab Assistant",
        kind=EntityKind.EXPERIENCE,
        organization="Northstar Lab",
    )
    profile.experiences.append(omitted)
    profile.evidence.append(
        EvidenceItem(
            id="e-lab-explicit",
            entity_id=omitted.id,
            source_text="Soldered and inspected prototype control boards.",
        )
    )
    edited = ResumeEditorService(_Renderer()).add_reviewed_entry(
        _resume(profile),
        profile,
        entry_id=omitted.id,
        evidence_ids=["e-lab-explicit"],
        expected_kind=EntityKind.EXPERIENCE,
    )
    assert edited.experiences[-1].id == omitted.id
    assert omitted.id in edited.experience_bullets
    assert omitted.id not in edited.project_bullets


def test_reviewed_skill_add_remove_and_unsupported_skill_rejection() -> None:
    service = ResumeEditorService(_Renderer())
    profile = _profile()
    edited = service.set_reviewed_skills(
        _resume(profile), profile, ["SolidWorks", "C++"]
    )
    assert [category.category for category in edited.technical_skills] == [
        "Design",
        "Languages",
    ]
    assert edited.selected_skills == ["SolidWorks", "C++"]
    with pytest.raises(ResumeEditorError, match="reviewed Career Profile"):
        service.set_reviewed_skills(edited, profile, ["Kubernetes"])


def test_applied_revision_renders_once_keeps_overflow_and_requires_exact_approval() -> None:
    renderer = _Renderer()
    service = ResumeEditorService(renderer)
    profile = _profile()
    resume = _resume(profile)
    revision = service.create_revision(
        resume,
        profile,
        application_fingerprint="application-a",
        baseline_artifact_fingerprint="artifact-a",
        revision_number=1,
        now=datetime(2026, 8, 25, tzinfo=UTC),
    )
    assert renderer.calls == 1
    assert revision.render.status is ResumeEditorFitStatus.FITS_ONE_PAGE
    with pytest.raises(ResumeEditorApprovalError):
        service.prepare_download(revision, approved_revision_fingerprint=None)
    download = service.prepare_download(
        revision,
        approved_revision_fingerprint=revision.revision_fingerprint,
    )
    assert download.docx_bytes == revision.render.docx_bytes
    assert renderer.calls == 1

    crowded = resume.model_copy(deep=True)
    crowded.project_bullets["project-hand"] = [
        *crowded.project_bullets["project-hand"],
        *[
            _bullet(f"extra-{index}", profile.evidence[2].source_text, ["e-hand"])
            for index in range(3)
        ],
    ]
    overflow = service.create_revision(
        crowded,
        profile,
        application_fingerprint="application-a",
        baseline_artifact_fingerprint="artifact-a",
        revision_number=2,
    )
    assert renderer.calls == 2
    assert overflow.resume.project_bullets["project-hand"] == crowded.project_bullets[
        "project-hand"
    ]
    assert overflow.render.status is ResumeEditorFitStatus.EXCEEDS_ONE_PAGE
    with pytest.raises(ResumeEditorApprovalError):
        service.prepare_download(
            overflow,
            approved_revision_fingerprint=overflow.revision_fingerprint,
        )


def test_application_fingerprint_isolates_job_a_and_job_b_editor_state() -> None:
    profile = _profile()
    job_a = JobPosting(
        id="job-a",
        title="Embedded Engineer",
        description="Develop and validate embedded controls on hardware.",
    )
    job_b = JobPosting(
        id="job-b",
        title="Software Engineer",
        description="Build and test distributed software services.",
    )
    context_a = resume_editor_application_fingerprint(profile, job_a, "artifact-a")
    context_b = resume_editor_application_fingerprint(profile, job_b, "artifact-b")
    assert context_a != context_b
    workspaces = {context_a: {"staged_resume": _resume(profile)}}
    assert context_b not in workspaces


def _sanitized_pdf(page_count: int) -> bytes:
    output = BytesIO()
    canvas = Canvas(output, pagesize=letter)
    for page_number in range(1, page_count + 1):
        canvas.drawString(72, 720, f"Sanitized resume page {page_number}")
        canvas.showPage()
    canvas.save()
    return output.getvalue()


@pytest.mark.parametrize("page_count", [1, 2])
def test_exact_pdf_pages_become_complete_aspect_preserving_png_preview(
    page_count: int,
) -> None:
    pages = render_pdf_preview_pages(_sanitized_pdf(page_count), zoom=1.0)
    assert len(pages) == page_count
    for page_png in pages:
        with Image.open(BytesIO(page_png)) as image:
            assert image.format == "PNG"
            assert image.width / image.height == pytest.approx(letter[0] / letter[1], rel=0.01)


def test_preview_frontend_has_no_data_pdf_iframe_and_download_uses_exact_bytes() -> None:
    source = FRONTEND_PATH.read_text(encoding="utf-8")
    assert "data:application/pdf;base64" not in source
    assert "streamlit_module.iframe(" not in source
    revision = ResumeEditorService(_Renderer()).create_revision(
        _resume(),
        _profile(),
        application_fingerprint="application-preview",
        baseline_artifact_fingerprint="artifact-preview",
        revision_number=1,
    )
    assert exact_preview_pdf_bytes(revision) is revision.render.pdf_bytes


def test_editor_preview_is_converted_from_the_rendered_docx_without_trimming() -> None:
    class _PdfConverter:
        def convert(self, docx_path: Path, pdf_path: Path) -> str:
            from reportlab.pdfgen.canvas import Canvas

            assert docx_path.is_file()
            canvas = Canvas(str(pdf_path))
            canvas.drawString(72, 720, "Sanitized résumé preview")
            canvas.save()
            return "sanitized test converter"

    renderer = TemplateV1ResumeEditorRenderer(converter=_PdfConverter())
    result = renderer.render(_resume())
    assert result.exact_pagination
    assert result.page_count == 1
    assert result.pdf_bytes and result.pdf_bytes.startswith(b"%PDF")
    assert len(result.preview_page_pngs) == 1
    assert result.docx_bytes.startswith(b"PK")
    assert result.pagination_provider == "sanitized test converter page tree"


def test_omitted_entry_heading_and_metadata_participate_in_real_geometry() -> None:
    class _PdfConverter:
        def convert(self, docx_path: Path, pdf_path: Path) -> str:
            from reportlab.pdfgen.canvas import Canvas

            canvas = Canvas(str(pdf_path))
            canvas.drawString(72, 720, "Sanitized résumé preview")
            canvas.save()
            return "sanitized test converter"

    profile = _profile()
    service = ResumeEditorService(_Renderer())
    suggestion = _bullet(
        "suggestion-arm-geometry",
        "Designed a SolidWorks actuator bracket for a long-reach arm.",
        ["e-arm-cad"],
        entry_id="project-arm",
    )
    base = _resume(profile)
    expanded = service.apply_suggestion(base, profile, suggestion)
    renderer = TemplateV1ResumeEditorRenderer(converter=_PdfConverter())
    base_render = renderer.render(base)
    expanded_render = renderer.render(expanded)
    paragraphs = [
        item.text for item in Document(BytesIO(expanded_render.docx_bytes)).paragraphs
    ]
    assert "Long Reach Manipulator" in "\n".join(paragraphs)
    assert expanded_render.utilization_ratio > base_render.utilization_ratio
