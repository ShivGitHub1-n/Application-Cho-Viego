from pathlib import Path
from dataclasses import dataclass

import pytest
from docx import Document

from resume_tailor.domain.models import ClaimSupport, ResumeStrategy, StructuredBullet, StructuredResume
from resume_tailor.infrastructure.rendering import (
    ManagedResumeRenderer,
    PageCountMeasurement,
    PageCountVerificationError,
    PageOverflowError,
)


@dataclass
class _SequencePageCountProvider:
    counts: list[int]

    def measure(self, docx_path: Path) -> PageCountMeasurement:
        count = self.counts.pop(0) if len(self.counts) > 1 else self.counts[0]
        return PageCountMeasurement(
            page_count=count,
            provider="test-sequence-provider",
            confidence="exact",
            exact=True,
        )


class _EstimatedPageCountProvider:
    def measure(self, docx_path: Path) -> PageCountMeasurement:
        return PageCountMeasurement(
            page_count=1,
            provider="estimate-only",
            confidence="estimated",
            exact=False,
        )


def test_managed_renderer_exports_docx_and_one_page_pdf(tmp_path: Path) -> None:
    resume = StructuredResume(
        profile_id="profile-1",
        profile_version=1,
        posting_id="posting-1",
        template_id="managed-engineering-v1",
        display_name="Avery Engineer",
        strategy=ResumeStrategy(
            role_family="embedded_firmware",
            primary_focus="embedded firmware development",
            rationale="Use verified evidence.",
        ),
        entity_titles={"experience-1": "Firmware Intern"},
        experience_bullets={
            "experience-1": [
                StructuredBullet(
                    id="evidence-1",
                    text="Developed STM32 firmware and validated SPI sensor communication.",
                    evidence_ids=["evidence-1"],
                    support=ClaimSupport.DIRECT,
                )
            ]
        },
        selected_skills=["STM32", "C", "SPI"],
    )

    result = ManagedResumeRenderer(
        page_count_provider=_SequencePageCountProvider([1])
    ).render(resume, tmp_path)

    assert result.page_count == 1
    assert result.exact_page_count_verified is True
    assert result.docx_path.exists()
    assert result.pdf_path.read_bytes().startswith(b"%PDF")


def test_managed_renderer_rejects_overflow(tmp_path: Path) -> None:
    bullet = StructuredBullet(
        id="evidence-overflow",
        text="Verified firmware validation evidence " * 30,
        evidence_ids=["evidence-overflow"],
        support=ClaimSupport.DIRECT,
    )
    resume = StructuredResume(
        profile_id="profile-1",
        profile_version=1,
        posting_id="posting-1",
        template_id="managed-engineering-v1",
        display_name="Avery Engineer",
        strategy=ResumeStrategy(
            role_family="embedded_firmware",
            primary_focus="embedded firmware development",
            rationale="Use verified evidence.",
        ),
        entity_titles={"experience-1": "Firmware Intern"},
        experience_bullets={"experience-1": [bullet] * 30},
    )

    with pytest.raises(PageOverflowError):
        ManagedResumeRenderer(
            page_count_provider=_SequencePageCountProvider([1])
        ).render(resume, tmp_path)


def test_strict_docx_page_gate_reduces_optional_content_until_one_page(tmp_path: Path) -> None:
    bullet = StructuredBullet(
        id="evidence-reduce",
        text="Verified firmware validation evidence.",
        evidence_ids=["evidence-reduce"],
        support=ClaimSupport.DIRECT,
    )
    resume = StructuredResume(
        profile_id="profile-1",
        profile_version=1,
        posting_id="posting-1",
        template_id="managed-engineering-v1",
        display_name="Avery Engineer",
        strategy=ResumeStrategy(
            role_family="embedded_firmware",
            primary_focus="embedded firmware development",
            rationale="Use verified evidence.",
        ),
        entity_titles={"experience-1": "Firmware Intern"},
        experience_bullets={"experience-1": [bullet]},
    )
    provider = _SequencePageCountProvider([2, 1])
    renderer = ManagedResumeRenderer(page_count_provider=provider)
    output = renderer.render_docx(resume, tmp_path / "reduced.docx")

    assert output.exists()
    assert renderer.last_measurement is not None
    assert renderer.last_measurement.page_count == 1
    assert renderer.last_measurement.exact is True
    assert renderer.last_overflow_reduction_count == 1
    assert "Verified firmware" not in "\n".join(
        paragraph.text for paragraph in Document(output).paragraphs
    )


def test_strict_docx_page_gate_rejects_estimates(tmp_path: Path) -> None:
    renderer = ManagedResumeRenderer(page_count_provider=_EstimatedPageCountProvider())
    resume = StructuredResume(
        profile_id="profile-1",
        profile_version=1,
        posting_id="posting-1",
        template_id="managed-engineering-v1",
        display_name="Avery Engineer",
        strategy=ResumeStrategy(
            role_family="embedded_firmware",
            primary_focus="embedded firmware development",
            rationale="Use verified evidence.",
        ),
    )

    with pytest.raises(PageCountVerificationError, match="not exact"):
        renderer.render_docx(resume, tmp_path / "estimated.docx")


def test_underfill_expansion_is_disabled_and_geometry_is_not_a_page_fit_control(
    tmp_path: Path,
) -> None:
    provider = _SequencePageCountProvider([2, 1])
    renderer = ManagedResumeRenderer(page_count_provider=provider)
    assert renderer.underfill_expansion_enabled is False

    bullet = StructuredBullet(
        id="evidence-geometry",
        text="Verified firmware validation evidence.",
        evidence_ids=["evidence-geometry"],
        support=ClaimSupport.DIRECT,
    )
    resume = StructuredResume(
        profile_id="profile-1",
        profile_version=1,
        posting_id="posting-1",
        template_id="managed-engineering-v1",
        display_name="Avery Engineer",
        strategy=ResumeStrategy(
            role_family="embedded_firmware",
            primary_focus="embedded firmware development",
            rationale="Use verified evidence.",
        ),
        entity_titles={"experience-1": "Firmware Intern"},
        experience_bullets={"experience-1": [bullet]},
    )
    output = renderer.render_docx(resume, tmp_path / "geometry-stable.docx")
    document = Document(output)
    page = renderer.layout_profile.page
    section = document.sections[0]
    assert section.left_margin.twips == page.left_margin_twips
    assert section.right_margin.twips == page.right_margin_twips
    assert section.top_margin.twips == page.top_margin_twips
    assert section.bottom_margin.twips == page.bottom_margin_twips
