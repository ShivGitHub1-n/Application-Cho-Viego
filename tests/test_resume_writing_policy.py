from __future__ import annotations

from resume_tailor.application.llm_services import HybridLlmServices
from resume_tailor.application.resume_writing_policy import DEFAULT_RESUME_WRITING_POLICY
from resume_tailor.domain.hybrid_resume import BulletValidationStatus, BulletVariantRecord
from resume_tailor.domain.llm_models import (
    ApprovedEvidenceGroup,
    BulletRewrite,
    BulletRewriteClaim,
)
from resume_tailor.domain.models import JobPosting


def _variant(
    source: str,
    rewrite: str,
    *,
    metrics: list[str],
) -> tuple[list[BulletVariantRecord], list[BulletVariantRecord]]:
    group = ApprovedEvidenceGroup(
        entry_id="backend-entry",
        evidence_ids=["backend-evidence"],
        source_texts=[source],
        technologies=["Python"],
        capabilities=["API caching", "latency reduction"],
        metrics=metrics,
        max_rendered_lines=2,
    )
    output = BulletRewrite(
        entry_id="backend-entry",
        final_bullet_text=rewrite,
        source_evidence_ids=["backend-evidence"],
        preserved_technologies=["Python"],
        preserved_metrics=metrics,
        evidence_combined=False,
        confidence=0.95,
        claims=[
            BulletRewriteClaim(
                text=rewrite,
                supporting_evidence_ids=["backend-evidence"],
            )
        ],
    )
    accepted, rejected, _diagnostics = HybridLlmServices(
        None, 0, 2, False, False, False
    )._variant_records(
        [output],
        [group],
        provider="fake",
        model="fake-writer",
        posting=JobPosting(
            id="backend-posting",
            title="Backend Engineer",
            description="Build Python APIs and improve service latency.",
        ),
    )
    return accepted, rejected


def test_recruiter_policy_prioritizes_ownership_method_and_supported_xyz() -> None:
    instructions = " ".join(DEFAULT_RESUME_WRITING_POLICY.instructions).casefold()

    assert "senior technical recruiter" in instructions
    assert "ownership or contribution" in instructions
    assert "technical method or mechanism" in instructions
    assert "accomplished x, measured by y, by doing z" in instructions
    assert "never invent a metric" in instructions
    assert "keep the reviewed source unchanged" in instructions


def test_supported_xyz_style_rewrite_preserves_metric_and_facts() -> None:
    accepted, rejected = _variant(
        "By caching reviewed service results, reduced Python API latency by 30%.",
        "Reduced Python API latency by 30% by caching reviewed service results.",
        metrics=["30%"],
    )

    assert not rejected
    assert accepted
    assert accepted[0].validation_status is BulletValidationStatus.VALIDATED
    assert "30%" in accepted[0].rewritten_text


def test_no_metric_evidence_rejects_invented_xyz_metric() -> None:
    accepted, rejected = _variant(
        "Reduced Python API latency by caching reviewed service results.",
        "Reduced Python API latency 30% by caching reviewed service results.",
        metrics=[],
    )

    assert not accepted
    assert rejected
    assert any(
        any(token in reason.casefold() for token in ("metric", "number", "numeric", "30%"))
        for reason in rejected[0].validation_reasons
    )
