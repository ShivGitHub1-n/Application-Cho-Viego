"""Runtime observations kept separate from the approved source registry."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SourceLifecycleOutcome(StrEnum):
    NEVER_RUN = "never_run"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class SourceHealth(StrEnum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class SourceRuntimeState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1)
    last_attempted_at: datetime | None = None
    last_successful_at: datetime | None = None
    last_complete_at: datetime | None = None
    last_outcome: SourceLifecycleOutcome = SourceLifecycleOutcome.NEVER_RUN
    diagnostic_codes: list[str] = Field(default_factory=list)
    consecutive_failure_count: int = Field(default=0, ge=0)
    next_eligible_refresh_at: datetime | None = None
    content_fingerprint: str | None = None
    source_state_fingerprint: str | None = None
    audit_version: str | None = None
    registry_plan_hash: str | None = None
    extraction_profile_hash: str | None = None
    conditional_validators: dict[str, str] = Field(default_factory=dict)
    browser_required: bool = False
    source_health: SourceHealth = SourceHealth.UNKNOWN
    incomplete_static: bool = False
    updated_at: datetime | None = None

    def attempted(self, at: datetime) -> SourceRuntimeState:
        return self.model_copy(
            update={
                "last_attempted_at": at,
                "updated_at": at,
                "last_outcome": SourceLifecycleOutcome.INTERRUPTED,
            }
        ).with_state_fingerprint()

    def completed(
        self,
        *,
        at: datetime,
        outcome: SourceLifecycleOutcome,
        diagnostic_codes: list[str] | tuple[str, ...] = (),
        content: object | None = None,
        browser_required: bool = False,
        incomplete_static: bool = False,
    ) -> SourceRuntimeState:
        failures = (
            self.consecutive_failure_count + 1 if outcome is SourceLifecycleOutcome.FAILED else 0
        )
        content_fingerprint = self.content_fingerprint
        if content is not None:
            content_fingerprint = fingerprint_content(content)
        successful = (
            at
            if outcome in {SourceLifecycleOutcome.SUCCESS, SourceLifecycleOutcome.PARTIAL}
            else self.last_successful_at
        )
        complete = at if outcome is SourceLifecycleOutcome.SUCCESS else self.last_complete_at
        health = (
            SourceHealth.HEALTHY
            if outcome is SourceLifecycleOutcome.SUCCESS
            else SourceHealth.DEGRADED
            if outcome is SourceLifecycleOutcome.PARTIAL
            else SourceHealth.UNAVAILABLE
        )
        return self.model_copy(
            update={
                "last_attempted_at": at,
                "last_successful_at": successful,
                "last_complete_at": complete,
                "last_outcome": outcome,
                "diagnostic_codes": sorted(set(diagnostic_codes)),
                "consecutive_failure_count": failures,
                "content_fingerprint": content_fingerprint,
                "browser_required": browser_required,
                "incomplete_static": incomplete_static,
                "source_health": health,
                "updated_at": at,
            }
        ).with_state_fingerprint()

    def with_state_fingerprint(self) -> SourceRuntimeState:
        payload = self.model_dump(mode="json", exclude={"source_state_fingerprint"})
        fingerprint = _sha256(payload)
        return self.model_copy(update={"source_state_fingerprint": fingerprint})


class SourceIdentityAlias(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1)
    identity_kind: str = Field(min_length=1, max_length=64)
    identity_value: str = Field(min_length=1, max_length=512)
    external_identity: str | None = None
    requisition_identity: str | None = None
    application_identity: str | None = None
    canonical_detail_identity: str | None = None
    job_id: str | None = None
    created_at: datetime | None = None


def fingerprint_content(value: object) -> str:
    return _sha256(value)


def _sha256(value: object) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "SourceHealth",
    "SourceLifecycleOutcome",
    "SourceRuntimeState",
    "SourceIdentityAlias",
    "fingerprint_content",
]
