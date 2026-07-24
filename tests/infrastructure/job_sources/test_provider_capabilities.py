from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from resume_tailor.domain.job_discovery.models import ConnectorType, SupportedJobSource
from resume_tailor.domain.job_discovery.providers import ProviderCapabilities, ProviderCursor
from resume_tailor.domain.job_discovery.queries import FeedKind, ProviderJobQuery
from resume_tailor.infrastructure.job_sources.greenhouse import GreenhouseConnector
from resume_tailor.infrastructure.job_sources.lever import LeverConnector

FIXTURES = Path(__file__).parents[2] / "fixtures" / "job_sources"
WHEN = datetime(2026, 7, 24, 12, tzinfo=UTC)


def _greenhouse_source() -> SupportedJobSource:
    return SupportedJobSource(
        source_id="greenhouse-acme",
        connector_type=ConnectorType.GREENHOUSE,
        company_name="Acme",
        board_token="acme",
        enabled=True,
        official_base_url="https://boards.greenhouse.io",
    )


def _lever_source() -> SupportedJobSource:
    return SupportedJobSource(
        source_id="lever-acme",
        connector_type=ConnectorType.LEVER,
        company_name="Acme",
        board_token="acme",
        enabled=True,
        official_base_url="https://jobs.lever.co",
        lever_api_region="global",
    )


def test_provider_capabilities_expose_every_retrieval_authority() -> None:
    capabilities = ProviderCapabilities(
        connector_type=ConnectorType.GREENHOUSE,
        supports_title_or_keyword=False,
        supports_sector=False,
        supports_location=False,
        supports_work_arrangement=False,
        supports_level=False,
        supports_employment_type=False,
        supports_posting_date_boundary=False,
        supports_pagination=False,
        supports_page_size=False,
        supports_availability_checks=True,
        posted_timestamp_authority="job_detail.first_published",
        updated_timestamp_authority="job.updated_at",
    )

    assert capabilities.supports_availability_checks is True
    assert capabilities.posted_timestamp_authority == "job_detail.first_published"
    assert capabilities.updated_timestamp_authority == "job.updated_at"


def test_existing_connectors_declare_truthful_capabilities_and_page_contract() -> None:
    greenhouse = GreenhouseConnector(
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json=json.loads((FIXTURES / "greenhouse_valid.json").read_text()),
                    request=request,
                )
            )
        )
    )
    lever = LeverConnector(
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json=json.loads((FIXTURES / "lever_global_page.json").read_text()),
                    request=request,
                )
            )
        )
    )
    query = ProviderJobQuery(
        feed_kind=FeedKind.TAILORED,
        titles=["RESUME SECRET TITLE"],
        page_size=25,
    )

    greenhouse_caps = greenhouse.capabilities(_greenhouse_source())
    lever_caps = lever.capabilities(_lever_source())
    assert greenhouse_caps.supports_pagination is False
    assert greenhouse_caps.posted_timestamp_authority == "job_detail.first_published"
    assert lever_caps.supports_pagination is True
    assert lever_caps.supports_page_size is True
    assert lever_caps.supports_availability_checks is True

    greenhouse_page = greenhouse.fetch_page(
        _greenhouse_source(), query, ProviderCursor(), fetched_at=WHEN
    )
    lever_page = lever.fetch_page(_lever_source(), query, ProviderCursor(), fetched_at=WHEN)
    assert greenhouse_page.records
    assert lever_page.records
    assert "RESUME SECRET TITLE" not in repr(greenhouse_page)
    assert "RESUME SECRET TITLE" not in repr(lever_page)
