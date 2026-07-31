# ruff: noqa: E501

from datetime import UTC, datetime
from pathlib import Path

import httpx

from resume_tailor.application.job_discovery.retrieval import RetrievalService
from resume_tailor.domain.job_discovery.models import (
    ConnectorType,
    FirstPartySource,
    SourceJobRecord,
)
from resume_tailor.domain.job_discovery.providers import (
    JobSourcePage,
    ProviderCapabilities,
)
from resume_tailor.domain.job_discovery.queries import ExploreJobQuery
from resume_tailor.infrastructure.job_sources.first_party import FirstPartyCareerConnector
from resume_tailor.infrastructure.job_sources.registry import (
    compile_runtime_sources,
    load_company_source_registry,
)


class _ProviderStub:
    def capabilities(self, source):
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
            supports_page_size=True,
            supports_availability_checks=False,
        )

    def fetch_page(self, source, query, cursor, *, fetched_at):
        return JobSourcePage(
            source=source,
            cursor=cursor,
            records=[
                SourceJobRecord(
                    external_job_id="provider-1",
                    title="Platform Engineer",
                    company_name=source.company_name,
                    description="Build reliable software.",
                    official_url="https://job-boards.greenhouse.io/anthropic/jobs/provider-1",
                )
            ],
        )


def test_provider_and_first_party_sources_share_one_retrieval_service() -> None:
    registry = load_company_source_registry(
        Path("config/approved-job-sources.json"), reference_date=datetime(2026, 7, 26).date()
    )
    compiled = compile_runtime_sources(registry)
    rocket = next(source for source in compiled if source.source_id == "rocket-lab")
    anthropic = next(source for source in compiled if source.source_id == "anthropic")
    assert isinstance(rocket, FirstPartySource)
    index = "<a class='job-card' href='/careers/positions/platform-engineer/'>Platform</a>"
    detail = """<script type='application/ld+json'>{\"@type\":\"JobPosting\",\"title\":\"Platform Engineer\",\"description\":\"Build reliable software.\",\"url\":\"https://rocketlabcorp.com/careers/positions/platform-engineer/\"}</script>"""

    def fetch(url: str) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text=index if url.endswith("positions/") else detail,
        )

    outcome = RetrievalService(
        sources=[anthropic, rocket],
        connectors={
            ConnectorType.GREENHOUSE: _ProviderStub(),
            ConnectorType.FIRST_PARTY: FirstPartyCareerConnector(fetcher=fetch),
        },
    ).retrieve(
        ExploreJobQuery(sectors=["Software Engineering"]),
        fetched_at=datetime(2026, 7, 26, tzinfo=UTC),
    )

    assert [item.source.source_id for item in outcome.records] == ["anthropic", "rocket-lab"]
    assert all(
        item.source.connector_type in {ConnectorType.GREENHOUSE, ConnectorType.FIRST_PARTY}
        for item in outcome.records
    )
