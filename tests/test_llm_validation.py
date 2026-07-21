# Provider fixture prose is intentionally retained as exact test input.
# ruff: noqa: E501

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
    BulletRewriteClaim,
    BulletRewriteOutput,
    BulletShorteningOutput,
    BulletShorteningRequest,
    CompositionRecommendationOutput,
    EvidenceGrouping,
)
from resume_tailor.domain.models import ClaimConfidence


def test_composition_rejects_unknown_and_cross_entry_evidence() -> None:
    output = CompositionRecommendationOutput(
        selected_entry_ids=["entry-1"],
        proposed_evidence_groupings=[
            EvidenceGrouping(entry_id="entry-1", evidence_ids=["evidence-2"])
        ],
        rationale="Use evidence.",
    )

    with pytest.raises(GroundingValidationError):
        validate_composition(output, {"entry-1", "entry-2"}, {"evidence-2": "entry-2"})


def test_same_entry_enrichment_accepts_one_connected_story_and_exact_platform() -> None:
    groups = [
        ApprovedEvidenceGroup(
            entry_id="controller-entry",
            evidence_ids=["controller-action"],
            source_texts=["Developed firmware for the motor controller."],
            capabilities=["motor controller"],
            max_rendered_lines=2,
        ),
        ApprovedEvidenceGroup(
            entry_id="controller-entry",
            evidence_ids=["controller-platform"],
            source_texts=["Validated STM32 motor-controller timing over SPI."],
            technologies=["STM32", "SPI"],
            capabilities=["motor controller"],
            max_rendered_lines=2,
        ),
    ]
    text = "Developed and validated STM32 motor-controller firmware over SPI."
    output = BulletRewriteOutput(
        bullets=[
            BulletRewrite(
                entry_id="controller-entry",
                final_bullet_text=text,
                source_evidence_ids=["controller-action", "controller-platform"],
                preserved_technologies=["STM32", "SPI"],
                evidence_combined=True,
                confidence=0.9,
                claims=[
                    BulletRewriteClaim(
                        text=text,
                        supporting_evidence_ids=[
                            "controller-action",
                            "controller-platform",
                        ],
                    )
                ],
            )
        ]
    )

    validate_rewrites(output, groups)


def test_same_entry_enrichment_rejects_unrelated_achievements() -> None:
    groups = [
        ApprovedEvidenceGroup(
            entry_id="mixed-entry",
            evidence_ids=["firmware-story"],
            source_texts=["Developed STM32 firmware over SPI."],
            technologies=["STM32", "SPI"],
            max_rendered_lines=2,
        ),
        ApprovedEvidenceGroup(
            entry_id="mixed-entry",
            evidence_ids=["budget-story"],
            source_texts=["Prepared quarterly procurement budgets for suppliers."],
            capabilities=["procurement budgeting"],
            max_rendered_lines=2,
        ),
    ]
    text = "Developed STM32 firmware over SPI while preparing supplier budgets."
    output = BulletRewriteOutput(
        bullets=[
            BulletRewrite(
                entry_id="mixed-entry",
                final_bullet_text=text,
                source_evidence_ids=["firmware-story", "budget-story"],
                evidence_combined=True,
                confidence=0.9,
                claims=[
                    BulletRewriteClaim(
                        text=text,
                        supporting_evidence_ids=["firmware-story", "budget-story"],
                    )
                ],
            )
        ]
    )

    with pytest.raises(GroundingValidationError, match="coherent engineering story"):
        validate_rewrites(output, groups)


def test_icd_conservative_authorship_paraphrase_preserves_ownership_and_scope() -> None:
    source = "Authored an interface control document covering sensor and actuator interfaces."
    text = "Defined sensor and actuator interfaces by authoring an interface control document."
    groups = [
        ApprovedEvidenceGroup(
            entry_id="systems-entry",
            evidence_ids=["icd-evidence"],
            source_texts=[source],
            capabilities=["interface control document"],
            max_rendered_lines=2,
        )
    ]
    output = BulletRewriteOutput(
        bullets=[
            BulletRewrite(
                entry_id="systems-entry",
                final_bullet_text=text,
                source_evidence_ids=["icd-evidence"],
                evidence_combined=False,
                confidence=0.9,
                claims=[
                    BulletRewriteClaim(
                        text=text,
                        supporting_evidence_ids=["icd-evidence"],
                    )
                ],
            )
        ]
    )

    validate_rewrites(output, groups)


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


def test_rewrite_allows_substantial_strongly_implied_tailoring() -> None:
    group = ApprovedEvidenceGroup(
        entry_id="entry-1",
        evidence_ids=["evidence-1"],
        source_texts=["Developed STM32 firmware and validated SPI communication."],
        technologies=["STM32", "SPI"],
        max_rendered_lines=2,
    )
    output = BulletRewriteOutput(
        bullets=[
            BulletRewrite(
                entry_id="entry-1",
                final_bullet_text="Integrated STM32 firmware with SPI validation workflows.",
                source_evidence_ids=["evidence-1"],
                preserved_technologies=["STM32", "SPI"],
                preserved_metrics=[],
                emphasized_terms=["embedded validation"],
                evidence_combined=False,
                concise_alternative="Integrated sensor firmware validation workflows.",
                confidence=0.8,
                support=ClaimConfidence.STRONGLY_IMPLIED,
                support_rationale="The workflow is strongly implied by the firmware development and validation evidence.",
            )
        ]
    )

    validate_rewrites(output, [group])


def test_rewrite_supports_split_and_combined_evidence() -> None:
    groups = [
        ApprovedEvidenceGroup(
            entry_id="entry-1",
            evidence_ids=["evidence-1"],
            source_texts=["Built a sensor interface."],
            max_rendered_lines=2,
        ),
        ApprovedEvidenceGroup(
            entry_id="entry-1",
            evidence_ids=["evidence-2"],
            source_texts=["Validated the sensor interface on hardware."],
            max_rendered_lines=2,
        ),
    ]
    output = BulletRewriteOutput(
        bullets=[
            BulletRewrite(
                entry_id="entry-1",
                final_bullet_text="Built the sensor interface.",
                source_evidence_ids=["evidence-1"],
                evidence_combined=False,
                concise_alternative="Built a sensor interface.",
                confidence=0.9,
            ),
            BulletRewrite(
                entry_id="entry-1",
                final_bullet_text="Validated the interface on hardware.",
                source_evidence_ids=["evidence-1"],
                evidence_combined=False,
                concise_alternative="Validated the interface.",
                confidence=0.9,
            ),
            BulletRewrite(
                entry_id="entry-1",
                final_bullet_text="Built and validated a sensor interface on hardware.",
                source_evidence_ids=["evidence-1", "evidence-2"],
                evidence_combined=True,
                concise_alternative="Validated a sensor interface.",
                confidence=0.9,
            ),
        ]
    )

    validate_rewrites(output, groups)


def test_rewrite_rejects_unsupported_confidence_and_new_metrics() -> None:
    group = ApprovedEvidenceGroup(
        entry_id="entry-1",
        evidence_ids=["evidence-1"],
        source_texts=["Built a sensor interface."],
        max_rendered_lines=2,
    )
    output = BulletRewriteOutput(
        bullets=[
            BulletRewrite(
                entry_id="entry-1",
                final_bullet_text="Built a 60 FPS sensor interface.",
                source_evidence_ids=["evidence-1"],
                evidence_combined=False,
                concise_alternative="Built a sensor interface.",
                confidence=0.1,
                support=ClaimConfidence.UNSUPPORTED,
            )
        ]
    )

    with pytest.raises(GroundingValidationError):
        validate_rewrites(output, [group])


def test_rewrite_preserves_supported_metric_and_technology() -> None:
    group = ApprovedEvidenceGroup(
        entry_id="entry-1",
        evidence_ids=["evidence-1"],
        source_texts=["Measured 30 FPS perception with OpenCV."],
        technologies=["OpenCV"],
        metrics=["30 FPS"],
        max_rendered_lines=2,
    )
    output = BulletRewriteOutput(
        bullets=[
            BulletRewrite(
                entry_id="entry-1",
                final_bullet_text="Validated OpenCV perception at 30 FPS.",
                source_evidence_ids=["evidence-1"],
                preserved_technologies=["OpenCV"],
                preserved_metrics=["30 FPS"],
                evidence_combined=False,
                concise_alternative="Validated OpenCV perception at 30 FPS.",
                confidence=0.9,
            )
        ]
    )

    validate_rewrites(output, [group])


def test_rewrite_rejects_unsupported_named_technology() -> None:
    group = ApprovedEvidenceGroup(
        entry_id="entry-1",
        evidence_ids=["evidence-1"],
        source_texts=["Deployed a reviewed cloud service."],
        technologies=["cloud service"],
        max_rendered_lines=2,
    )
    output = BulletRewriteOutput(
        bullets=[
            BulletRewrite(
                entry_id="entry-1",
                final_bullet_text="Deployed a reviewed cloud service on AWS.",
                source_evidence_ids=["evidence-1"],
                preserved_technologies=["AWS"],
                evidence_combined=False,
                confidence=0.9,
            )
        ]
    )

    with pytest.raises(GroundingValidationError, match="unsupported"):
        validate_rewrites(output, [group])


def test_rewrite_rejects_unsupported_outcome() -> None:
    group = ApprovedEvidenceGroup(
        entry_id="entry-1",
        evidence_ids=["evidence-1"],
        source_texts=["Validated a sensor interface."],
        max_rendered_lines=2,
    )
    output = BulletRewriteOutput(
        bullets=[
            BulletRewrite(
                entry_id="entry-1",
                final_bullet_text="Validated a sensor interface and eliminated defects.",
                source_evidence_ids=["evidence-1"],
                evidence_combined=False,
                concise_alternative="Validated a sensor interface.",
                confidence=0.9,
            )
        ]
    )

    with pytest.raises(GroundingValidationError, match="unsupported outcomes"):
        validate_rewrites(output, [group])


def test_rewrite_rejects_claim_provenance_outside_evidence_bundle() -> None:
    group = ApprovedEvidenceGroup(
        entry_id="entry-1",
        evidence_ids=["evidence-1"],
        source_texts=["Validated a sensor interface."],
        max_rendered_lines=2,
    )
    output = BulletRewriteOutput(
        bullets=[
            BulletRewrite(
                entry_id="entry-1",
                final_bullet_text="Validated a sensor interface.",
                source_evidence_ids=["evidence-1"],
                evidence_combined=False,
                concise_alternative="Validated a sensor interface.",
                confidence=0.9,
                claims=[
                    BulletRewriteClaim(
                        text="Validated a sensor interface.",
                        supporting_evidence_ids=["evidence-2"],
                    )
                ],
            )
        ]
    )

    with pytest.raises(GroundingValidationError, match="outside its bundle"):
        validate_rewrites(output, [group])


def test_rewrite_rejects_combining_facts_from_unrelated_entries() -> None:
    groups = [
        ApprovedEvidenceGroup(
            entry_id="entry-1",
            evidence_ids=["evidence-1"],
            source_texts=["Built a sensor interface."],
            max_rendered_lines=2,
        ),
        ApprovedEvidenceGroup(
            entry_id="entry-2",
            evidence_ids=["evidence-2"],
            source_texts=["Validated a deployment pipeline."],
            max_rendered_lines=2,
        ),
    ]
    output = BulletRewriteOutput(
        bullets=[
            BulletRewrite(
                entry_id="entry-1",
                final_bullet_text=("Built a sensor interface and validated a deployment pipeline."),
                source_evidence_ids=["evidence-1", "evidence-2"],
                evidence_combined=True,
                concise_alternative="Built and validated integrated systems.",
                confidence=0.9,
            )
        ]
    )

    with pytest.raises(GroundingValidationError, match="cross-entry bullet"):
        validate_rewrites(output, groups)


def test_ownership_gerund_is_recognized_but_new_ensuring_outcome_stays_rejected() -> None:
    source = (
        "Supported functional safety by developing supervisory safety logic and "
        "emergency-stop control strategies."
    )
    rewrite = (
        "Developed supervisory safety logic and emergency-stop control strategies, "
        "ensuring robust functional safety."
    )
    group = ApprovedEvidenceGroup(
        entry_id="entry-1",
        evidence_ids=["evidence-1"],
        source_texts=[source],
        capabilities=["functional safety", "supervisory safety logic"],
        max_rendered_lines=2,
    )
    output = BulletRewriteOutput(
        bullets=[
            BulletRewrite(
                entry_id="entry-1",
                final_bullet_text=rewrite,
                source_evidence_ids=["evidence-1"],
                evidence_combined=False,
                confidence=0.9,
                claims=[
                    BulletRewriteClaim(
                        text=rewrite,
                        supporting_evidence_ids=["evidence-1"],
                    )
                ],
            )
        ]
    )

    with pytest.raises(GroundingValidationError) as raised:
        validate_rewrites(output, [group])

    assert any("unsupported causal outcome" in item for item in raised.value.failures)
    assert not any("ownership or causality" in item for item in raised.value.failures)


def test_collaboration_to_development_ownership_strengthening_remains_rejected() -> None:
    source = "Collaborated on integrating a real-time perception pipeline."
    rewrite = "Developed a real-time perception pipeline."
    group = ApprovedEvidenceGroup(
        entry_id="entry-1",
        evidence_ids=["evidence-1"],
        source_texts=[source],
        max_rendered_lines=2,
    )
    output = BulletRewriteOutput(
        bullets=[
            BulletRewrite(
                entry_id="entry-1",
                final_bullet_text=rewrite,
                source_evidence_ids=["evidence-1"],
                evidence_combined=False,
                confidence=0.9,
            )
        ]
    )

    with pytest.raises(GroundingValidationError, match="ownership or causality"):
        validate_rewrites(output, [group])


def test_exact_reviewed_langgraph_passes_and_absent_aws_stays_rejected() -> None:
    group = ApprovedEvidenceGroup(
        entry_id="entry-1",
        evidence_ids=["evidence-1"],
        source_texts=["Developed LangGraph evaluation workflows."],
        technologies=["LangGraph"],
        max_rendered_lines=2,
    )
    supported = BulletRewriteOutput(
        bullets=[
            BulletRewrite(
                entry_id="entry-1",
                final_bullet_text="Built LangGraph evaluation workflows.",
                source_evidence_ids=["evidence-1"],
                preserved_technologies=["LangGraph"],
                evidence_combined=False,
                confidence=0.9,
            )
        ]
    )
    validate_rewrites(supported, [group])

    unsupported = supported.model_copy(
        update={
            "bullets": [
                supported.bullets[0].model_copy(
                    update={
                        "final_bullet_text": "Built LangGraph workflows on AWS.",
                        "preserved_technologies": ["LangGraph", "AWS"],
                    }
                )
            ]
        }
    )
    with pytest.raises(GroundingValidationError, match="AWS|aws"):
        validate_rewrites(unsupported, [group])
