import pytest

from resume_tailor.application.llm_validation import (
    GroundingValidationError,
    validate_composition,
    validate_rewrites,
    validate_shortening,
)
from resume_tailor.domain.llm_models import (
    ApprovedEvidenceGroup,
    BulletRewrite,
    BulletRewriteOutput,
    BulletShorteningOutput,
    BulletShorteningRequest,
    CompositionRecommendationOutput,
    EvidenceGrouping,
)


def test_composition_rejects_unknown_and_cross_entry_evidence() -> None:
    output = CompositionRecommendationOutput(
        selected_entry_ids=["entry-1"],
        proposed_evidence_groupings=[EvidenceGrouping(entry_id="entry-1", evidence_ids=["evidence-2"])],
        rationale="Use evidence.",
    )

    with pytest.raises(GroundingValidationError):
        validate_composition(output, {"entry-1", "entry-2"}, {"evidence-2": "entry-2"})


def test_shortening_rejects_new_metrics_and_dropped_facts() -> None:
    request = BulletShorteningRequest(
        bullet_id="bullet-1",
        entry_id="entry-1",
        original_text="Validated 30 FPS perception using OpenCV.",
        source_evidence_ids=["evidence-1"],
        source_texts=["Validated 30 FPS perception using OpenCV."],
        protected_facts=["30 FPS", "OpenCV"],
        max_rendered_lines=2,
    )
    output = BulletShorteningOutput(
        original_bullet_id="bullet-1",
        shortened_text="Validated 60 FPS perception.",
        source_evidence_ids=["evidence-1"],
        preserved_facts=[],
        removed_wording=["OpenCV"],
        no_new_claim_introduced=True,
    )

    with pytest.raises(GroundingValidationError):
        validate_shortening(output, request)


def test_rewrite_rejects_declared_skill_as_work_claim() -> None:
    group = ApprovedEvidenceGroup(
        entry_id="entry-1",
        evidence_ids=["evidence-1"],
        source_texts=["Developed STM32 firmware with SPI communication."],
        technologies=["STM32", "SPI"],
        max_rendered_lines=2,
    )
    output = BulletRewriteOutput(
        bullets=[
            BulletRewrite(
                entry_id="entry-1",
                final_bullet_text="Developed STM32 firmware with SPI communication using PyTorch.",
                source_evidence_ids=["evidence-1"],
                preserved_technologies=["STM32", "SPI"],
                preserved_metrics=[],
                emphasized_terms=[],
                evidence_combined=False,
                concise_alternative="Developed STM32 firmware with SPI communication.",
                confidence=0.9,
            )
        ]
    )

    with pytest.raises(GroundingValidationError):
        validate_rewrites(output, [group])
