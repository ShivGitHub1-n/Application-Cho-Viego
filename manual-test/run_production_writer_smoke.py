from __future__ import annotations

import json
import os
from pathlib import Path
from time import perf_counter
from typing import Any

from resume_tailor.application.generated_artifact import prepare_artifact_download
from resume_tailor.application.job_intake import build_job_posting
from resume_tailor.domain.generated_artifact import GeneratedResumeArtifact
from resume_tailor.domain.models import MasterProfile, TemplateConstraints
from resume_tailor.infrastructure.config import Settings
from resume_tailor.infrastructure.dependencies import create_tailor_service

ROOT = Path(__file__).resolve().parents[1]
MANUAL_DIR = ROOT / "manual-test"
DOCX_PATH = MANUAL_DIR / "generated-template-v1-production-writer.docx"
WRITER_DIAGNOSTICS_PATH = (
    MANUAL_DIR / "generated-template-v1-production-writer.writer.diagnostics.json"
)
PORTFOLIO_DIAGNOSTICS_PATH = (
    MANUAL_DIR / "generated-template-v1-production-writer.portfolio.diagnostics.json"
)
COMPARISON_PATH = (
    MANUAL_DIR / "generated-template-v1-production-writer.source-rewrite.diagnostics.json"
)


def main() -> int:
    profile = MasterProfile.model_validate_json(
        (MANUAL_DIR / "profile.json").read_text(encoding="utf-8")
    )
    posting = build_job_posting(
        "production-writer-smoke-embedded-systems-engineer",
        os.getenv("PRODUCTION_WRITER_JOB_TITLE", "Embedded Systems Engineer"),
        Path(
            os.getenv(
                "PRODUCTION_WRITER_JOB_DESCRIPTION_FILE",
                str(MANUAL_DIR / "embedded-systems-engineer-posting.txt"),
            )
        ).read_text(encoding="utf-8"),
    )
    loaded = Settings()
    settings = loaded.model_copy(
        update={
            "llm_enable_opportunity_analysis": False,
            "llm_enable_composition": False,
            "llm_enable_bullet_rewrite": True,
            "llm_enable_shortening": False,
            "llm_enable_role_classification": False,
            "llm_enable_cover_letter": False,
            "llm_max_calls_per_generation": 2,
            "llm_retry_count": 1,
        }
    )
    real_provider_configured = bool(
        (settings.gemini_api_key or os.getenv(settings.llm_api_key_env_var))
        and settings.gemini_model
    )
    service = create_tailor_service(settings)
    service.start_generation()
    started = perf_counter()
    plan = service.create_plan(profile, posting, TemplateConstraints())
    artifact = service.build_generated_artifact(plan, profile, set())
    total_route_seconds = perf_counter() - started

    download_started = perf_counter()
    download = prepare_artifact_download(artifact, clock=perf_counter)
    download_seconds = perf_counter() - download_started
    if download.docx_bytes != artifact.docx_bytes:
        raise RuntimeError("Download preparation did not reuse exact stored artifact bytes.")
    if any(download.generation_call_counts.model_dump().values()):
        raise RuntimeError("Download preparation executed a generation operation.")

    DOCX_PATH.write_bytes(download.docx_bytes)
    _write_json(
        WRITER_DIAGNOSTICS_PATH,
        _writer_payload(
            artifact,
            profile,
            real_provider_configured=real_provider_configured,
            total_route_seconds=total_route_seconds,
            download_seconds=download_seconds,
        ),
    )
    _write_json(
        PORTFOLIO_DIAGNOSTICS_PATH,
        _portfolio_payload(artifact, profile),
    )
    _write_json(
        COMPARISON_PATH,
        _comparison_payload(artifact),
    )
    print(
        json.dumps(
            {
                "real_provider_configured": real_provider_configured,
                "provider": artifact.provider_diagnostic.provider,
                "model": artifact.provider_diagnostic.model,
                "status": artifact.provider_diagnostic.status,
                "provider_requests": artifact.provider_diagnostic.call_count,
                "repairs": artifact.provider_diagnostic.retry_count,
                "cache_hits": artifact.provider_diagnostic.cache_hit_count,
                "finish_reason": artifact.provider_diagnostic.finish_reason,
                "failure_stage": (
                    artifact.provider_diagnostic.pipeline_issue.stage.value
                    if artifact.provider_diagnostic.pipeline_issue is not None
                    else None
                ),
                "failure_code": (
                    artifact.provider_diagnostic.pipeline_issue.code.value
                    if artifact.provider_diagnostic.pipeline_issue is not None
                    else None
                ),
                "request_shape": (
                    artifact.provider_diagnostic.request_shape.model_dump(mode="json")
                    if artifact.provider_diagnostic.request_shape is not None
                    else None
                ),
                "parsing_result": _stage_result(
                    artifact,
                    "provider_response_parsing",
                ),
                "schema_result": _schema_result(artifact),
                "grounding_result": _stage_result(artifact, "claim_validation"),
                "selected_rewrites": (
                    artifact.writing_diagnostic.rewritten_bullet_count
                    if artifact.writing_diagnostic is not None
                    else 0
                ),
                "provider_seconds": artifact.provider_diagnostic.provider_elapsed_seconds,
                "validation_seconds": (
                    artifact.provider_diagnostic.validation_elapsed_seconds
                ),
                "artifact_build_seconds": artifact.total_build_seconds,
                "total_route_seconds": round(total_route_seconds, 4),
                "download_seconds": round(download_seconds, 6),
                "download_generation_calls": 0,
                "docx": str(DOCX_PATH),
            },
            indent=2,
        )
    )
    return 0


def _stage_result(artifact: GeneratedResumeArtifact, stage_value: str) -> str:
    return next(
        timing.status.value
        for timing in artifact.stage_timings
        if timing.stage.value == stage_value
    )


def _schema_result(artifact: GeneratedResumeArtifact) -> str:
    issue = artifact.provider_diagnostic.pipeline_issue
    if issue is not None and issue.stage.value == "typed_schema_validation":
        return "failed"
    parsing = _stage_result(artifact, "provider_response_parsing")
    return "passed" if parsing == "completed" else "skipped"


def _writer_payload(
    artifact: GeneratedResumeArtifact,
    profile: MasterProfile,
    *,
    real_provider_configured: bool,
    total_route_seconds: float,
    download_seconds: float,
) -> dict[str, Any]:
    writing = artifact.writing_diagnostic
    provider = artifact.provider_diagnostic
    entry_names = {
        entry.id: {
            "title": entry.title,
            "organization": entry.organization,
            "kind": entry.kind.value,
        }
        for entry in [*profile.experiences, *profile.projects]
    }
    return {
        "human_review_required": True,
        "real_provider_configured": real_provider_configured,
        "provider": provider.model_dump(mode="json"),
        "route_total_seconds": total_route_seconds,
        "artifact_total_build_seconds": artifact.total_build_seconds,
        "download_seconds": download_seconds,
        "download_reused_exact_bytes": True,
        "download_generation_call_counts": {key: 0 for key in artifact.call_counts.model_dump()},
        "shortlisted_entries": (
            [
                {
                    **item.model_dump(mode="json"),
                    "entry": entry_names.get(item.entry_id),
                }
                for item in writing.writer_shortlist
                if item.selected
            ]
            if writing is not None
            else []
        ),
        "writing": writing.model_dump(mode="json") if writing is not None else None,
    }


def _portfolio_payload(
    artifact: GeneratedResumeArtifact,
    profile: MasterProfile,
) -> dict[str, Any]:
    entry_names = {
        entry.id: {
            "title": entry.title,
            "organization": entry.organization,
            "kind": entry.kind.value,
        }
        for entry in [*profile.experiences, *profile.projects]
    }
    writing = artifact.writing_diagnostic
    composition = artifact.composition_diagnostic
    selected_experience_ids = composition.selected_experience_ids if composition is not None else []
    selected_project_ids = composition.selected_project_ids if composition is not None else []
    retrieval = writing.retrieval if writing is not None else None
    return {
        "selected_experiences": [
            {"entry_id": entry_id, **entry_names[entry_id]} for entry_id in selected_experience_ids
        ],
        "selected_projects": [
            {"entry_id": entry_id, **entry_names[entry_id]} for entry_id in selected_project_ids
        ],
        "retrieved_candidates": [
            item.model_dump(mode="json")
            for item in (retrieval.admitted if retrieval is not None else [])
        ],
        "writer_shortlist": [
            item.model_dump(mode="json")
            for item in (writing.writer_shortlist if writing is not None else [])
        ],
        "composition": (
            artifact.composition_diagnostic.model_dump(mode="json")
            if artifact.composition_diagnostic is not None
            else None
        ),
    }


def _comparison_payload(artifact: GeneratedResumeArtifact) -> dict[str, Any]:
    writing = artifact.writing_diagnostic
    if writing is None:
        return {"variants": [], "reason": "No writing diagnostic was produced."}
    return {
        "human_review_required": True,
        "writing_status": writing.writer_execution_status.value,
        "zero_rewrite_reason": (
            writing.writing_reason if writing.rewritten_bullet_count == 0 else None
        ),
        "per_rewrite_diagnostics": [
            item.model_dump(mode="json") for item in writing.rewrite_diagnostics
        ],
        "variants": [
            {
                "variant_id": item.variant_id,
                "entry_id": item.entry_id,
                "evidence_ids": item.source_evidence_ids,
                "source": item.original_reviewed_text,
                "rewrite": item.rewritten_text,
                "claims": [claim.model_dump(mode="json") for claim in item.factual_claims],
                "requirements": item.target_job_requirements,
                "relationship": item.relationship_tier.value,
                "length_class": item.intended_length_class.value,
                "material_improvement": item.material_improvement,
                "improvement_reasons": item.improvement_reasons,
                "validation_status": item.validation_status.value,
                "validation_reasons": item.validation_reasons,
                "selected": item.selected,
                "selection_reason": item.selection_reason,
                "provider": item.provider,
                "model": item.model,
                "prompt_version": item.prompt_version,
                "policy_version": item.writing_policy_version,
            }
            for item in [*writing.bullet_variants, *writing.rejected_variants]
        ],
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
