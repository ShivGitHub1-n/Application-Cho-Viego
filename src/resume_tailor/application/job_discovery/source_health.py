from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from resume_tailor.domain.job_discovery.models import SourceDefinition
from resume_tailor.domain.job_discovery.source_lifecycle import SourceRuntimeState
from resume_tailor.ports.job_discovery import SourceRuntimeStateRepository


class SourceHealthSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    company_name: str
    mechanism: str
    enabled: bool
    runnable: bool
    provider_type: str | None = None
    toronto_gta_relevance: bool = False
    last_attempted_at: datetime | None = None
    last_successful_at: datetime | None = None
    source_health: str = "unknown"
    browser_required: bool = False
    next_eligible_refresh_at: datetime | None = None
    diagnostic_codes: list[str] = Field(default_factory=list)
    audit_version: str | None = None
    registry_plan_hash: str | None = None
    extraction_profile_hash: str | None = None


class SourceHealthQueryService:
    def __init__(
        self, sources: list[SourceDefinition], states: SourceRuntimeStateRepository
    ) -> None:
        self._sources = tuple(sorted(sources, key=lambda item: item.source_id))
        self._states = states

    def list(self) -> list[SourceHealthSummary]:
        return [self.get(source.source_id) for source in self._sources]

    def get(self, source_id: str) -> SourceHealthSummary:
        source = next((item for item in self._sources if item.source_id == source_id), None)
        if source is None:
            raise KeyError(source_id)
        state = self._states.get(source_id) or SourceRuntimeState(source_id=source_id)
        return SourceHealthSummary(
            source_id=source.source_id,
            company_name=source.company_name,
            mechanism=source.connector_type.value,
            enabled=source.enabled,
            runnable=source.enabled,
            provider_type=(
                source.connector_type.value
                if source.connector_type.value != "first_party"
                else None
            ),
            toronto_gta_relevance=bool(
                getattr(source, "toronto_gta_relevance", False)
                or getattr(
                    getattr(source, "geographic_coverage", None),
                    "toronto_gta_presence",
                    False,
                )
            ),
            last_attempted_at=state.last_attempted_at,
            last_successful_at=state.last_successful_at,
            source_health=state.source_health.value,
            browser_required=state.browser_required,
            next_eligible_refresh_at=state.next_eligible_refresh_at,
            diagnostic_codes=list(state.diagnostic_codes),
            audit_version=source.audit_version,
            registry_plan_hash=source.registry_plan_hash,
            extraction_profile_hash=source.extraction_profile_hash,
        )


__all__ = ["SourceHealthQueryService", "SourceHealthSummary"]
