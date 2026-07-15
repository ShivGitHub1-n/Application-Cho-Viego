from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from resume_tailor.domain.job_discovery.models import ConnectorType, SupportedJobSource
from resume_tailor.infrastructure.config import Settings
from resume_tailor.infrastructure.job_sources.greenhouse import GreenhouseConnector
from resume_tailor.infrastructure.job_sources.lever import LeverConnector
from resume_tailor.infrastructure.job_sources.registry import load_source_registry

pytestmark = pytest.mark.job_source_integration


def test_configured_job_source_fetch_smoke(request: pytest.FixtureRequest) -> None:
    """Fetch one explicitly approved source only when this marker is selected."""

    if "job_source_integration" not in request.config.getoption("markexpr"):
        pytest.skip(
            "Select -m job_source_integration to run the live job-source smoke test."
        )

    settings = Settings()
    if not settings.job_discovery_enabled or settings.job_discovery_source_registry_path is None:
        pytest.skip("No approved job sources are configured; live smoke test skipped.")

    sources = load_source_registry(settings.job_discovery_source_registry_path)
    if not sources:
        pytest.skip("No approved job sources are configured; live smoke test skipped.")

    source = sources[0]
    with httpx.Client(timeout=settings.job_discovery_source_timeout_seconds) as client:
        connector = _connector(source, settings, client)
        connector.fetch(source, fetched_at=datetime.now(UTC))


def _connector(
    source: SupportedJobSource,
    settings: Settings,
    client: httpx.Client,
) -> GreenhouseConnector | LeverConnector:
    if source.connector_type is ConnectorType.GREENHOUSE:
        return GreenhouseConnector(
            client,
            timeout=settings.job_discovery_source_timeout_seconds,
            api_base_url=str(settings.job_discovery_greenhouse_api_base_url),
        )
    return LeverConnector(
        client,
        timeout=settings.job_discovery_source_timeout_seconds,
        page_size=settings.job_discovery_source_page_size,
        max_pages=settings.job_discovery_source_max_pages,
        global_api_base_url=settings.job_discovery_lever_global_api_base_url,
        eu_api_base_url=settings.job_discovery_lever_eu_api_base_url,
    )
