from pathlib import Path

import pytest

from resume_tailor.domain.models import ClaimSupport, ResumeStrategy, StructuredBullet, StructuredResume
from resume_tailor.infrastructure.rendering import ManagedResumeRenderer, PageOverflowError


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

    result = ManagedResumeRenderer().render(resume, tmp_path)

    assert result.page_count == 1
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
        ManagedResumeRenderer().render(resume, tmp_path)
