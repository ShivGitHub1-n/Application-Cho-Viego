from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256

from pydantic import BaseModel, Field

from resume_tailor.application.generation_diagnostics import Clock
from resume_tailor.domain.generated_artifact import (
    ArtifactDownload,
    ArtifactFingerprintInputs,
    GeneratedResumeArtifact,
    GenerationStage,
    StageTiming,
)
from resume_tailor.domain.models import JobPosting, MasterProfile, TailoringPlan


class ResumeGenerationConfiguration(BaseModel):
    template_identity: str
    composition_contract_version: str
    writing_policy_version: str
    writing_contract_version: str
    feature_flags: dict[str, bool] = Field(default_factory=dict)
    provider: str
    model: str
    provider_timeout_seconds: float = Field(gt=0)
    provider_retry_count: int = Field(ge=0)


def content_fingerprint(value: object) -> str:
    if isinstance(value, BaseModel):
        serialized = value.model_dump_json()
    else:
        serialized = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return sha256(serialized.encode("utf-8")).hexdigest()


def artifact_fingerprint(inputs: ArtifactFingerprintInputs) -> str:
    payload = inputs.model_dump(mode="json")
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_fingerprint_inputs(
    *,
    profile: MasterProfile,
    posting: JobPosting,
    plan: TailoringPlan,
    approved_claim_ids: set[str],
    template_identity: str,
    composition_contract_version: str,
    writing_policy_version: str,
    writing_contract_version: str,
    feature_flags: dict[str, bool],
    provider: str,
    model: str,
) -> ArtifactFingerprintInputs:
    return ArtifactFingerprintInputs(
        reviewed_profile_fingerprint=content_fingerprint(profile),
        normalized_posting_fingerprint=content_fingerprint(posting),
        validated_plan_fingerprint=content_fingerprint(plan),
        approved_claim_ids=sorted(approved_claim_ids),
        template_identity=template_identity,
        composition_contract_version=composition_contract_version,
        writing_policy_version=writing_policy_version,
        writing_contract_version=writing_contract_version,
        feature_flags=dict(sorted(feature_flags.items())),
        provider=provider,
        model=model,
    )


def prepare_artifact_download(
    artifact: GeneratedResumeArtifact,
    *,
    clock: Clock,
) -> ArtifactDownload:
    started = clock()
    payload = artifact.docx_bytes
    timing = StageTiming(
        stage=GenerationStage.DOWNLOAD_PREPARATION,
        elapsed_seconds=max(0.0, clock() - started),
    )
    return ArtifactDownload(
        artifact_fingerprint=artifact.artifact_fingerprint,
        docx_bytes=payload,
        preparation_timing=timing,
    )


def generation_timestamp(now: Callable[[], datetime] | None = None) -> datetime:
    value = (now or (lambda: datetime.now(UTC)))()
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


__all__ = [
    "ResumeGenerationConfiguration",
    "artifact_fingerprint",
    "build_fingerprint_inputs",
    "content_fingerprint",
    "generation_timestamp",
    "prepare_artifact_download",
]
