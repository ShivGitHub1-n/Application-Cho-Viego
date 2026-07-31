"""Provider-neutral retrieval, provenance, and source-outcome contracts."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from resume_tailor.domain.job_discovery.models import (
    ConnectorType,
    SourceDefinition,
    SourceJobRecord,
    SourceProvenance,
    SourceRecordWarning,
)
from resume_tailor.domain.job_discovery.queries import (
    ProviderFilterDisposition,
    ProviderJobQuery,
)


class ProviderCapabilities(BaseModel):
    connector_type: ConnectorType
    supports_title_or_keyword: bool
    supports_sector: bool
    supports_location: bool
    supports_work_arrangement: bool
    supports_level: bool
    supports_employment_type: bool
    supports_posting_date_boundary: bool
    supports_pagination: bool
    supports_page_size: bool
    supports_availability_checks: bool
    posted_timestamp_authority: str | None = None
    updated_timestamp_authority: str | None = None
    max_page_size: int | None = Field(default=None, ge=1)


class ProviderFilterPlan(BaseModel):
    provider_query: ProviderJobQuery
    dispositions: dict[str, ProviderFilterDisposition] = Field(default_factory=dict)


class ProviderCursor(BaseModel):
    value: str | None = None


class JobSourcePage(BaseModel):
    source: SourceDefinition
    cursor: ProviderCursor = Field(default_factory=ProviderCursor)
    next_cursor: ProviderCursor = Field(default_factory=ProviderCursor)
    records: list[SourceJobRecord] = Field(default_factory=list)
    warnings: list[SourceRecordWarning] = Field(default_factory=list)
    has_more: bool = False


class SourceDiagnosticKind(StrEnum):
    WARNING = "warning"
    ERROR = "error"


class SourceDiagnostic(BaseModel):
    kind: SourceDiagnosticKind
    source_id: str
    connector_type: ConnectorType
    page: int
    cursor: str | None = None
    code: str
    message: str
    external_job_id: str | None = None


class SourceOutcomeStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class SourceOutcome(BaseModel):
    source_id: str
    connector_type: ConnectorType
    status: SourceOutcomeStatus
    pages_fetched: int = 0
    records_retrieved: int = 0
    records_accepted: int = 0
    filter_plan: ProviderFilterPlan | None = None
    warnings: list[SourceDiagnostic] = Field(default_factory=list)
    errors: list[SourceDiagnostic] = Field(default_factory=list)


class RetrievedSourceRecord(BaseModel):
    source: SourceDefinition
    record: SourceJobRecord
    provenance: SourceProvenance


class RetrievalOutcome(BaseModel):
    records: list[RetrievedSourceRecord] = Field(default_factory=list)
    source_outcomes: list[SourceOutcome] = Field(default_factory=list)
    partial_success: bool = False
    retrieved_count: int = 0
    accepted_count: int = 0


__all__ = [
    "JobSourcePage",
    "ProviderCapabilities",
    "ProviderCursor",
    "ProviderFilterPlan",
    "RetrievedSourceRecord",
    "RetrievalOutcome",
    "SourceDiagnostic",
    "SourceDiagnosticKind",
    "SourceOutcome",
    "SourceOutcomeStatus",
    "SourceProvenance",
]
