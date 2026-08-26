"""Bounded, provider-safe retrieval orchestration."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any, cast

from resume_tailor.domain.job_discovery.models import (
    ConnectorType,
    JobSourceFetchResult,
    SourceDefinition,
    SourceJobRecord,
    SupportedJobSource,
)
from resume_tailor.domain.job_discovery.providers import (
    JobSourcePage,
    ProviderCapabilities,
    ProviderCursor,
    ProviderFilterPlan,
    RetrievalOutcome,
    RetrievedSourceRecord,
    SourceDiagnostic,
    SourceDiagnosticKind,
    SourceOutcome,
    SourceOutcomeStatus,
    SourceProvenance,
)
from resume_tailor.domain.job_discovery.queries import (
    ExploreJobQuery,
    ProviderFilterDisposition,
    ProviderJobQuery,
    TailoredJobQuery,
)
from resume_tailor.domain.job_discovery.search_taxonomy import (
    matches_any_explore_sector,
    matches_requested_levels,
    matches_title_query,
)
from resume_tailor.ports.job_discovery import JobSourceConnector

Query = TailoredJobQuery | ExploreJobQuery
ConnectorCollection = Mapping[
    ConnectorType,
    JobSourceConnector | Mapping[str, JobSourceConnector],
]


class RetrievalService:
    """Retrieve pages from enabled sources with deterministic safety bounds."""

    def __init__(
        self,
        *,
        sources: Sequence[SourceDefinition],
        connectors: ConnectorCollection,
        max_pages: int = 20,
        max_records_per_source: int = 1000,
        max_workers: int = 4,
    ) -> None:
        if max_pages <= 0 or max_records_per_source <= 0 or max_workers <= 0:
            raise ValueError("retrieval limits must be positive")
        self._sources = tuple(
            sorted(sources, key=lambda item: (item.source_id, item.connector_type.value))
        )
        self._connectors = connectors
        self._max_pages = max_pages
        self._max_records_per_source = max_records_per_source
        self._max_workers = max_workers

    def retrieve(self, query: Query, *, fetched_at: datetime) -> RetrievalOutcome:
        records: list[RetrievedSourceRecord] = []
        outcomes: list[SourceOutcome] = []
        selected = [
            source
            for source in self._sources
            if not query.source_restrictions or source.source_id in query.source_restrictions
        ]
        if len(selected) <= 1:
            retrieved = [
                self._retrieve_source(source, query, fetched_at=fetched_at)
                for source in selected
            ]
        else:
            retrieved = []
            with ThreadPoolExecutor(
                max_workers=min(self._max_workers, len(selected)),
                thread_name_prefix="job-source",
            ) as executor:
                futures = {
                    executor.submit(
                        self._retrieve_source,
                        source,
                        query,
                        fetched_at=fetched_at,
                    ): source
                    for source in selected
                }
                for future in as_completed(futures):
                    retrieved.append(future.result())
        for outcome, accepted in retrieved:
            outcomes.append(outcome)
            records.extend(accepted)
        outcomes.sort(key=lambda item: (item.source_id, item.connector_type.value))
        records.sort(
            key=lambda item: (
                item.source.source_id,
                item.provenance.page_cursor or "",
                item.record.external_job_id,
            )
        )
        successful = [item for item in outcomes if item.status is not SourceOutcomeStatus.FAILED]
        failed = [item for item in outcomes if item.status is SourceOutcomeStatus.FAILED]
        return RetrievalOutcome(
            records=records,
            source_outcomes=outcomes,
            partial_success=bool(failed and successful),
            retrieved_count=sum(item.records_retrieved for item in outcomes),
            accepted_count=len(records),
        )

    def _retrieve_source(
        self,
        source: SourceDefinition,
        query: Query,
        *,
        fetched_at: datetime,
    ) -> tuple[SourceOutcome, list[RetrievedSourceRecord]]:
        provider_query = query.to_provider_query()
        warnings: list[SourceDiagnostic] = []
        errors: list[SourceDiagnostic] = []
        accepted: list[RetrievedSourceRecord] = []
        try:
            connector = self._connector_for(source)
            capabilities = connector.capabilities(cast(Any, source))
        except Exception as error:
            errors.append(
                self._diagnostic(
                    SourceDiagnosticKind.ERROR,
                    source,
                    page=0,
                    cursor=None,
                    code=self._safe_error_code(error),
                    message=self._safe_error_message(error),
                )
            )
            return (
                SourceOutcome(
                    source_id=source.source_id,
                    connector_type=source.connector_type,
                    status=SourceOutcomeStatus.FAILED,
                    pages_fetched=0,
                    records_retrieved=0,
                    records_accepted=0,
                    filter_plan=None,
                    warnings=warnings,
                    errors=errors,
                ),
                accepted,
            )
        filter_plan = self._plan_filters(provider_query, capabilities)
        cursor = ProviderCursor()
        seen_cursors: set[str | None] = set()
        pages_fetched = 0
        records_retrieved = 0
        status = SourceOutcomeStatus.SUCCESS

        unsupported_keys = sorted(
            key
            for key, value in filter_plan.dispositions.items()
            if value is ProviderFilterDisposition.UNSUPPORTED
            and key not in {"page_size", "pagination"}
        )
        if unsupported_keys:
            warnings.append(
                self._diagnostic(
                    SourceDiagnosticKind.WARNING,
                    source,
                    page=0,
                    cursor=None,
                    code="unsupported_filter",
                    message=f"Unsupported retrieval filter: {unsupported_keys[0]}.",
                )
            )

        while pages_fetched < self._max_pages and len(accepted) < self._max_records_per_source:
            cursor_value = cursor.value
            if cursor_value in seen_cursors:
                warnings.append(
                    self._diagnostic(
                        SourceDiagnosticKind.WARNING,
                        source,
                        page=pages_fetched,
                        cursor=cursor_value,
                        code="repeated_cursor",
                        message="Provider returned a repeated cursor; retrieval stopped.",
                    )
                )
                status = SourceOutcomeStatus.PARTIAL
                break
            seen_cursors.add(cursor_value)
            pages_fetched += 1
            try:
                page = connector.fetch_page(
                    cast(Any, source),
                    provider_query.model_copy(update={"cursor": cursor_value}),
                    cursor,
                    fetched_at=fetched_at,
                )
                if not isinstance(page, JobSourcePage):
                    raise TypeError("provider page contract was not returned")
            except Exception as error:
                errors.append(
                    self._diagnostic(
                        SourceDiagnosticKind.ERROR,
                        source,
                        page=pages_fetched,
                        cursor=cursor_value,
                        code=self._safe_error_code(error),
                        message=self._safe_error_message(error),
                    )
                )
                status = (
                    SourceOutcomeStatus.PARTIAL
                    if accepted or pages_fetched > 1
                    else SourceOutcomeStatus.FAILED
                )
                break

            records_retrieved += len(page.records)
            for item in page.warnings:
                warnings.append(
                    self._diagnostic(
                        SourceDiagnosticKind.WARNING,
                        source,
                        page=pages_fetched,
                        cursor=cursor_value,
                        code=item.code.value,
                        message=self._safe_warning_message(item.code.value),
                        external_job_id=item.external_job_id,
                    )
                )
            for record in page.records:
                if self._passes_local_filters(
                    record,
                    provider_query,
                    filter_plan,
                    as_of=fetched_at,
                ):
                    accepted.append(
                        RetrievedSourceRecord(
                            source=source,
                            record=record,
                            provenance=SourceProvenance(
                                source_id=source.source_id,
                                connector_type=source.connector_type,
                                external_job_id=record.external_job_id,
                                official_url=str(record.official_url),
                                fetched_at=fetched_at,
                                page_cursor=cursor_value,
                                source_updated_at=record.source_updated_at,
                                posted_at=record.posted_at,
                            ),
                        )
                    )
                    if len(accepted) >= self._max_records_per_source:
                        break
            if not page.has_more or page.next_cursor.value is None:
                break
            cursor = page.next_cursor

        if errors and accepted:
            status = SourceOutcomeStatus.PARTIAL
        if records_retrieved and not accepted and (
            provider_query.titles or provider_query.sectors
        ):
            warnings.append(
                self._diagnostic(
                    SourceDiagnosticKind.WARNING,
                    source,
                    page=pages_fetched,
                    cursor=cursor.value,
                    code="local_filter_no_match",
                    message=(
                        "Source returned records, but none matched the requested "
                        "local retrieval boundaries."
                    ),
                )
            )
            if status is SourceOutcomeStatus.SUCCESS:
                status = SourceOutcomeStatus.PARTIAL
        elif warnings and status is SourceOutcomeStatus.SUCCESS:
            status = SourceOutcomeStatus.PARTIAL
        return (
            SourceOutcome(
                source_id=source.source_id,
                connector_type=source.connector_type,
                status=status,
                pages_fetched=pages_fetched,
                records_retrieved=records_retrieved,
                records_accepted=len(accepted),
                filter_plan=filter_plan,
                warnings=warnings,
                errors=errors,
            ),
            accepted,
        )

    def _plan_filters(
        self,
        query: ProviderJobQuery,
        capabilities: ProviderCapabilities,
    ) -> ProviderFilterPlan:
        values: dict[str, tuple[bool, bool]] = {
            "title_or_keyword": (bool(query.titles), capabilities.supports_title_or_keyword),
            "sector": (bool(query.sectors), capabilities.supports_sector),
            "location": (bool(query.locations), capabilities.supports_location),
            "work_arrangement": (
                bool(query.work_arrangements),
                capabilities.supports_work_arrangement,
            ),
            "level": (bool(query.levels), capabilities.supports_level),
            "employment_type": (
                bool(query.employment_types),
                capabilities.supports_employment_type,
            ),
            "posting_date_boundary": (
                query.max_posting_age_days is not None or query.posted_after is not None,
                capabilities.supports_posting_date_boundary,
            ),
            "page_size": (True, capabilities.supports_page_size),
            "pagination": (True, capabilities.supports_pagination),
        }
        dispositions: dict[str, ProviderFilterDisposition] = {}
        for key, (requested, supported) in values.items():
            if not requested:
                dispositions[key] = ProviderFilterDisposition.NOT_REQUESTED
            elif supported:
                dispositions[key] = ProviderFilterDisposition.PUSHED_DOWN
            elif key in {
                "title_or_keyword",
                "sector",
                "location",
                "work_arrangement",
                "level",
                "posting_date_boundary",
            }:
                dispositions[key] = ProviderFilterDisposition.LOCAL
            else:
                dispositions[key] = ProviderFilterDisposition.UNSUPPORTED
        return ProviderFilterPlan(provider_query=query, dispositions=dispositions)

    @staticmethod
    def _passes_local_filters(
        record: SourceJobRecord,
        query: ProviderJobQuery,
        plan: ProviderFilterPlan,
        *,
        as_of: datetime,
    ) -> bool:
        if plan.dispositions["title_or_keyword"] is ProviderFilterDisposition.LOCAL:
            if not matches_title_query(record.title, query.titles):
                return False
        # Provider sector search is candidate retrieval, not canonical membership.
        # Always enforce the deterministic title taxonomy after provider return.
        if query.sectors and not matches_any_explore_sector(record.title, query.sectors):
            return False
        if plan.dispositions["location"] is ProviderFilterDisposition.LOCAL:
            location = (record.location_raw or "").casefold()
            if location and not any(item.casefold() in location for item in query.locations):
                return False
        if plan.dispositions["work_arrangement"] is ProviderFilterDisposition.LOCAL:
            if (
                record.work_arrangement.value != "unknown"
                and record.work_arrangement not in query.work_arrangements
            ):
                return False
        if plan.dispositions["level"] is ProviderFilterDisposition.LOCAL:
            if not matches_requested_levels(record.title, query.levels):
                return False
        if plan.dispositions["posting_date_boundary"] is ProviderFilterDisposition.LOCAL:
            boundary = query.posted_after
            if boundary is None and query.max_posting_age_days is not None:
                boundary = as_of - timedelta(days=query.max_posting_age_days)
            if (
                boundary is not None
                and record.posted_at is not None
                and record.posted_at < boundary
            ):
                return False
        if any(
            value is ProviderFilterDisposition.UNSUPPORTED
            for key, value in plan.dispositions.items()
            if key not in {"page_size", "pagination"}
        ):
            return False
        return True

    def _connector_for(self, source: SourceDefinition) -> JobSourceConnector:
        configured = self._connectors.get(source.connector_type)
        if configured is None:
            raise RuntimeError("job source connector is not configured")
        if isinstance(configured, Mapping):
            connector = configured.get(source.source_id)
            if connector is None:
                raise RuntimeError("job source connector is not configured")
            return _as_paged_connector(connector)
        return _as_paged_connector(configured)

    @staticmethod
    def _diagnostic(
        kind: SourceDiagnosticKind,
        source: SourceDefinition,
        *,
        page: int,
        cursor: str | None,
        code: str,
        message: str,
        external_job_id: str | None = None,
    ) -> SourceDiagnostic:
        return SourceDiagnostic(
            kind=kind,
            source_id=source.source_id,
            connector_type=source.connector_type,
            page=page,
            cursor=cursor,
            code=code,
            message=message,
            external_job_id=external_job_id,
        )

    @staticmethod
    def _safe_error_code(error: Exception) -> str:
        source_code = getattr(error, "code", None)
        if isinstance(source_code, str) and re.fullmatch(r"[a-z0-9_]+", source_code):
            return source_code
        name = error.__class__.__name__
        return {
            "JobSourceEnvelopeError": "malformed_envelope",
            "JobSourceRateLimitedError": "rate_limited",
            "JobSourceAuthenticationError": "authentication_failed",
            "JobSourceNotFoundError": "not_found",
            "JobSourceTransportError": "transport_failure",
        }.get(name, "source_failure")

    @staticmethod
    def _safe_error_message(error: Exception) -> str:
        source_messages = {
            "robots_denied": "Source robots policy denied this refresh.",
            "browser_required": "Source requires the approved browser fallback.",
            "browser_unavailable": "The approved browser runtime is unavailable.",
            "listing_parse_failed": "Source listing could not be parsed deterministically.",
            "sitemap_parse_failed": "Source sitemap could not be parsed safely.",
            "detail_url_rejected": "Source returned a detail URL outside its approved policy.",
            "detail_fetch_failed": "Source detail retrieval failed.",
            "content_type_rejected": "Source content type is not approved.",
            "response_too_large": "Source response exceeded the bounded size limit.",
            "required_field_missing": "Source detail omitted a required job field.",
            "identity_missing": "Source detail omitted stable job identity.",
            "partial_detail_failure": "Some source details failed after partial retrieval.",
        }
        source_code = getattr(error, "code", None)
        if isinstance(source_code, str) and source_code in source_messages:
            return source_messages[source_code]
        return {
            "JobSourceEnvelopeError": "Provider returned a malformed page envelope.",
            "JobSourceRateLimitedError": "Provider rate limit reached.",
            "JobSourceAuthenticationError": "Provider authentication failed.",
            "JobSourceNotFoundError": "Provider resource was not found.",
            "JobSourceTransportError": "Provider transport failed.",
        }.get(error.__class__.__name__, "Provider page retrieval failed.")

    @staticmethod
    def _safe_warning_message(code: str) -> str:
        return {
            "missing_external_job_id": "Provider record was missing an external job ID.",
            "missing_title": "Provider record was missing a title.",
            "invalid_official_url": "Provider record had an invalid official URL.",
            "invalid_location": "Provider record had an invalid location.",
            "invalid_timestamp": "Provider record had an invalid timestamp.",
            "invalid_record_shape": "Provider record had an invalid shape.",
            "duplicate_record": "Provider returned a duplicate record.",
        }.get(code, "Provider returned a record warning.")


class _LegacyConnectorAdapter:
    """One-way compatibility for pre-Batch-3 connectors during this migration."""

    def __init__(self, connector: object) -> None:
        self._connector = connector

    def capabilities(self, source: SupportedJobSource) -> ProviderCapabilities:
        return ProviderCapabilities(
            connector_type=source.connector_type,
            supports_title_or_keyword=False,
            supports_sector=False,
            supports_location=False,
            supports_work_arrangement=False,
            supports_level=False,
            supports_employment_type=False,
            supports_posting_date_boundary=False,
            supports_pagination=False,
            supports_page_size=False,
            supports_availability_checks=False,
        )

    def fetch_page(
        self,
        source: SupportedJobSource,
        query: ProviderJobQuery,
        cursor: ProviderCursor,
        *,
        fetched_at: datetime,
    ) -> JobSourcePage:
        if cursor.value is not None:
            raise RuntimeError("legacy source does not support pagination")
        result = cast(Any, self._connector).fetch(source, fetched_at=fetched_at)
        if not isinstance(result, JobSourceFetchResult):
            raise TypeError("legacy connector returned an invalid fetch result")
        return JobSourcePage(
            source=source,
            cursor=cursor,
            records=result.records,
            warnings=result.warnings,
            has_more=False,
        )


def _as_paged_connector(connector: object) -> JobSourceConnector:
    if hasattr(connector, "capabilities") and hasattr(connector, "fetch_page"):
        return connector  # type: ignore[return-value]
    return _LegacyConnectorAdapter(connector)  # type: ignore[return-value]


__all__ = ["RetrievalService"]
