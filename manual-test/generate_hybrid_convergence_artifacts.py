from __future__ import annotations

import json
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from time import perf_counter

from resume_tailor.application.generated_artifact import (
    ResumeGenerationConfiguration,
    prepare_artifact_download,
)
from resume_tailor.application.generation_diagnostics import GenerationTelemetry
from resume_tailor.application.resume_composition import DeterministicResumeComposer
from resume_tailor.application.services import TailorResumeService
from resume_tailor.domain.generated_artifact import ArtifactDownload, GeneratedResumeArtifact
from resume_tailor.domain.hybrid_resume import (
    RESUME_WRITING_CONTRACT_VERSION,
    RESUME_WRITING_POLICY_VERSION,
)
from resume_tailor.domain.models import (
    JobPosting,
    MasterProfile,
    StructuredResume,
    TemplateConstraints,
)
from resume_tailor.domain.resume_composition import RESUME_COMPOSITION_CONTRACT_VERSION
from resume_tailor.domain.resume_metadata import validate_structured_resume_metadata
from resume_tailor.infrastructure.artifact_rendering import TemplateV1ArtifactRenderer
from resume_tailor.infrastructure.composition_page_fit import TemplateV1PageFitEvaluator
from resume_tailor.infrastructure.optimization import (
    DeterministicResumeOptimizer,
    EvidenceBoundResumeWriter,
)
from resume_tailor.infrastructure.template_v1 import (
    TEMPLATE_V1_DOCX_SHA256,
    TEMPLATE_V1_ID,
    template_v1_docx_path,
)
from tests.convergence_cases import (
    mechanical_manufacturing_case,
    rich_mixed_case,
    software_cloud_case,
)

ROOT = Path(__file__).resolve().parents[1]
CaseFactory = Callable[[], tuple[MasterProfile, JobPosting]]
OUTPUTS: dict[str, tuple[CaseFactory, str]] = {
    "real_profile": (
        lambda: _real_embedded_case(),
        "generated-template-v1-requirement-aware-real-profile.docx",
    ),
    "rich_mixed": (
        rich_mixed_case,
        "generated-template-v1-hybrid-rich-mixed.docx",
    ),
    "software_cloud": (
        software_cloud_case,
        "generated-template-v1-hybrid-software-cloud.docx",
    ),
    "mechanical_manufacturing": (
        mechanical_manufacturing_case,
        "generated-template-v1-hybrid-mechanical-manufacturing.docx",
    ),
    "cybersecurity": (
        lambda: _cybersecurity_case(),
        "generated-template-v1-requirement-aware-cybersecurity.docx",
    ),
}


def _real_embedded_case() -> tuple[MasterProfile, JobPosting]:
    profile = MasterProfile.model_validate_json(
        (ROOT / "manual-test" / "profile.json").read_text(encoding="utf-8")
    )
    posting = JobPosting(
        id="world-star-tech-embedded-systems-engineer",
        title="Embedded Systems Engineer",
        description=(
            "Core responsibilities:\n"
            "- Develop firmware and GUI software for robotic in-house automation.\n"
            "- Collaborate across electronic, software, and optomechanical disciplines.\n"
            "- Develop clean, documented code from low-level embedded systems through "
            "high-level architecture.\n"
            "Required qualifications:\n"
            "- Strong C++ and Python object-oriented programming.\n"
            "- Experience with STM32 or similar microcontrollers.\n"
            "- Use timers, I2C, UART, SPI, DMA, ADC, and related peripherals.\n"
            "Preferred or bonus qualifications:\n"
            "- C# and .NET.\n"
            "- TCP sockets and cloud services.\n"
            "- Image processing."
        ),
    )
    return profile, posting


def _cybersecurity_case() -> tuple[MasterProfile, JobPosting]:
    profile, _posting = software_cloud_case()
    return (
        profile,
        JobPosting(
            id="controlled-cybersecurity-posting",
            title="Application Security Engineer",
            description=(
                "Required responsibilities:\n"
                "- Validate OAuth 2.0 authorization and API access controls.\n"
                "- Investigate SIEM alerts using application and container logs.\n"
                "- Test Docker and Kubernetes deployments for security defects.\n"
                "- Document threat scenarios, remediation evidence, and secure release "
                "controls.\n"
                "Preferred qualifications:\n"
                "- Python automation, PostgreSQL, and cloud reliability experience."
            ),
        ),
    )


def main() -> None:
    for case_name, (factory, filename) in OUTPUTS.items():
        profile, posting = factory()
        artifact = _build_artifact(profile, posting)
        download = prepare_artifact_download(
            artifact,
            clock=perf_counter,
        )
        output = ROOT / "manual-test" / filename
        output.write_bytes(download.docx_bytes)
        diagnostic_path = output.with_suffix(".diagnostics.json")
        diagnostic_path.write_text(
            json.dumps(
                _diagnostic_payload(
                    case_name,
                    profile,
                    artifact.final_resume,
                    artifact,
                    download,
                    output,
                ),
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        print(f"{case_name}: {output.name} -> {diagnostic_path.name}")


def _build_artifact(
    profile: MasterProfile,
    posting: JobPosting,
) -> GeneratedResumeArtifact:
    telemetry = GenerationTelemetry()
    service = TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
        resume_composer=DeterministicResumeComposer(
            TemplateV1PageFitEvaluator(telemetry=telemetry),
            telemetry=telemetry,
        ),
        artifact_renderer=TemplateV1ArtifactRenderer(telemetry),
        generation_configuration=ResumeGenerationConfiguration(
            template_identity=f"{TEMPLATE_V1_ID}:{TEMPLATE_V1_DOCX_SHA256}",
            composition_contract_version=RESUME_COMPOSITION_CONTRACT_VERSION,
            writing_policy_version=RESUME_WRITING_POLICY_VERSION,
            writing_contract_version=RESUME_WRITING_CONTRACT_VERSION,
            feature_flags={
                "opportunity_analysis": False,
                "semantic_composition": False,
                "bullet_rewrite": False,
                "shortening": False,
                "role_classification": False,
            },
            provider="deterministic",
            model="not-configured",
            provider_timeout_seconds=30,
            provider_retry_count=0,
        ),
        telemetry=telemetry,
    )
    service.start_generation()
    plan = service.create_plan(profile, posting, TemplateConstraints())
    return service.build_generated_artifact(plan, profile, set())


def _diagnostic_payload(
    case_name: str,
    profile: MasterProfile,
    resume: StructuredResume,
    artifact: GeneratedResumeArtifact,
    download: ArtifactDownload,
    output: Path,
) -> dict[str, object]:
    composition = resume.composition_diagnostic
    if composition is None:
        raise RuntimeError("Controlled artifact did not retain composition diagnostics")
    hybrid = resume.hybrid_diagnostic
    metadata = validate_structured_resume_metadata(resume)
    template = template_v1_docx_path().resolve()
    selected_candidate_ids = {
        candidate.candidate_id for candidate in composition.selected_candidates
    }
    strong_unused_by_id: dict[str, dict[str, object]] = {}
    for candidate in [
        *composition.unused_admissible_candidates,
        *composition.candidates_excluded_by_search_bounds,
        *composition.candidates_excluded_by_thresholds,
        *composition.excluded_high_ranking_candidates,
    ]:
        if candidate.candidate_id not in selected_candidate_ids:
            strong_unused_by_id.setdefault(
                candidate.candidate_id,
                candidate.model_dump(mode="json"),
            )
    education = [
        {
            **record.model_dump(mode="json"),
            "selected_detail_fields": metadata.education[index].selected_detail_fields,
            "rendered_date_text": metadata.education[index].rendered_date_text,
        }
        for index, record in enumerate(resume.education)
    ]
    return {
        "case": case_name,
        "artifact": str(output.relative_to(ROOT)),
        "renderer": ("resume_tailor.infrastructure.static_template_docx.render_template_v1_resume"),
        "template_path": str(template.relative_to(ROOT)),
        "template_sha256": sha256(template.read_bytes()).hexdigest().upper(),
        "metadata_fidelity": metadata.model_dump(mode="json"),
        "selected_education": education,
        "selected_experience_ids": composition.selected_experience_ids,
        "selected_project_ids": composition.selected_project_ids,
        "selected_skill_category_ids": composition.selected_skill_category_ids,
        "selected_skill_category_labels": composition.selected_skill_category_labels,
        "selected_skill_rows": [
            row.model_dump(mode="json") for row in composition.selected_skill_rows
        ],
        "posting_requirements": [
            requirement.model_dump(mode="json")
            for requirement in composition.posting_requirements
        ],
        "requirement_coverage": [
            coverage.model_dump(mode="json")
            for coverage in composition.requirement_coverage
        ],
        "portfolio_coverage_gaps": composition.portfolio_coverage_gaps,
        "direct_candidate_tradeoffs": [
            tradeoff.model_dump(mode="json")
            for tradeoff in composition.direct_candidate_tradeoffs
        ],
        "omitted_direct_skill_values": composition.omitted_direct_skill_values,
        "omitted_direct_skill_reasons": composition.omitted_direct_skill_reasons,
        "bullet_counts": composition.bullet_counts,
        "selected_bullet_ids": composition.selected_bullet_ids,
        "selected_bullet_diagnostics": [
            candidate.model_dump(mode="json")
            for candidate in composition.selected_candidates
            if candidate.kind.value.endswith("bullet")
        ],
        "entry_bullet_selections": [
            entry.model_dump(mode="json")
            for entry in composition.entry_bullet_selections
        ],
        "project_representation": (
            composition.project_representation.model_dump(mode="json")
            if composition.project_representation is not None
            else None
        ),
        "strong_unused_candidates": list(strong_unused_by_id.values()),
        "estimated_utilization_ratio": composition.final_utilization_ratio,
        "preferred_density_status": composition.preferred_density_status.value,
        "estimated_remaining_lines": (
            hybrid.estimated_remaining_lines if hybrid is not None else None
        ),
        "search_termination_reason": composition.termination_reason.value,
        "underfill_reasons": [reason.value for reason in composition.underfill_reasons],
        "bounds": {
            "beam_width": composition.beam_width,
            "maximum_estimated_page_evaluations": (composition.maximum_estimated_page_evaluations),
            "estimated_page_evaluations": composition.estimated_page_evaluations,
            "maximum_exact_finalist_evaluations": (composition.maximum_exact_finalist_evaluations),
            "exact_page_evaluations": composition.exact_page_evaluations,
            "maximum_expansion_operations": composition.maximum_expansion_operations,
            "expansion_operations": composition.expansion_operations,
            "maximum_selected_bullets": composition.maximum_selected_bullets,
            "maximum_selected_entries": composition.maximum_selected_entries,
            "candidates_excluded_by_search_bounds": len(
                composition.candidates_excluded_by_search_bounds
            ),
            "estimated_evaluation_limit_reached": (
                composition.estimated_page_evaluations
                >= composition.maximum_estimated_page_evaluations
            ),
            "exact_finalist_limit_reached": (
                composition.exact_page_evaluations >= composition.maximum_exact_finalist_evaluations
            ),
            "expansion_operation_limit_reached": (
                composition.expansion_operations >= composition.maximum_expansion_operations
            ),
            "selected_bullet_limit_reached": (
                len(composition.selected_bullet_ids) >= composition.maximum_selected_bullets
            ),
            "selected_entry_limit_reached": (
                len(composition.selected_experience_ids) + len(composition.selected_project_ids)
                >= composition.maximum_selected_entries
            ),
        },
        "provider_call_count": (hybrid.provider_call_count if hybrid is not None else 0),
        "provider_cache_hits": (hybrid.provider_cache_hits if hybrid is not None else 0),
        "writer": {
            "status": (
                hybrid.writer_execution_status.value
                if hybrid is not None
                else "rewriting_disabled"
            ),
            "reason": (
                hybrid.writing_reason
                if hybrid is not None
                else "No writer diagnostic was produced."
            ),
            "source_bullet_count": (
                hybrid.source_bullet_count if hybrid is not None else 0
            ),
            "rewritten_bullet_count": (
                hybrid.rewritten_bullet_count if hybrid is not None else 0
            ),
            "fallback_bullet_count": (
                hybrid.fallback_bullet_count if hybrid is not None else 0
            ),
            "rejected_variant_count": (
                hybrid.rejected_variant_count if hybrid is not None else 0
            ),
            "source_to_rewrite_examples": (
                [
                    {
                        "source": item.original_reviewed_text,
                        "rewrite": item.rewritten_text,
                    }
                    for item in hybrid.bullet_variants
                    if item.selected
                ]
                if hybrid is not None
                else []
            ),
        },
        "production_artifact": {
            "fingerprint": artifact.artifact_fingerprint,
            "total_build_seconds": artifact.total_build_seconds,
            "stage_timings": [
                timing.model_dump(mode="json")
                for timing in artifact.stage_timings
            ],
            "call_counts": artifact.call_counts.model_dump(mode="json"),
            "provider": artifact.provider_diagnostic.model_dump(mode="json"),
            "pagination": artifact.pagination_diagnostic.model_dump(mode="json"),
            "docx_bytes": len(artifact.docx_bytes),
        },
        "download": {
            "stored_bytes_reused": download.docx_bytes == artifact.docx_bytes,
            "preparation_seconds": download.preparation_timing.elapsed_seconds,
            "generation_call_counts": download.generation_call_counts.model_dump(
                mode="json"
            ),
        },
        "page_verification": {
            "status": composition.verification_status.value,
            "provider": composition.verification_provider,
            "failure": composition.verification_failure,
            "page_count": composition.page_count,
        },
    }


if __name__ == "__main__":
    main()
