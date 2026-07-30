from __future__ import annotations

from datetime import date

import pytest

from resume_tailor.application.company_research import BoundedCompanyResearchService
from resume_tailor.application.cover_letter import CoverLetterService
from resume_tailor.application.generated_artifact import content_fingerprint
from resume_tailor.domain.company_research import (
    ApprovedCompanySource,
    CompanyFactConfidence,
    CompanyResearchEvent,
    CompanyResearchRequest,
    CompanyResearchStatus,
    CompanySourceDocument,
    CompanySourceType,
)
from tests.cover_letter_helpers import ControlledCoverLetterRenderer, cover_letter_case


class _Fetcher:
    def __init__(self) -> None:
        self.calls = 0

    def fetch(
        self,
        source: ApprovedCompanySource,
        *,
        company_domain: str,
    ) -> CompanySourceDocument:
        self.calls += 1
        assert company_domain == "example.com"
        return CompanySourceDocument(
            source_url=source.url,
            title="Example Robotics engineering",
            publisher="Example Robotics",
            source_type=source.source_type,
            retrieved_on=date(2026, 7, 21),
            text=(
                "The robotics platform uses embedded firmware and sensor test systems "
                "to operate autonomous machines in industrial facilities."
            ),
        )


class _FailingFetcher:
    def __init__(self) -> None:
        self.calls = 0

    def fetch(self, source: ApprovedCompanySource, *, company_domain: str) -> object:
        del source, company_domain
        self.calls += 1
        raise RuntimeError("network unavailable")


def _request(**updates: object) -> CompanyResearchRequest:
    payload: dict[str, object] = {
        "company_name": "Example Robotics",
        "company_domain": "example.com",
        "role_title": "Embedded Firmware Intern",
        "job_url": "https://example.com/jobs/1",
        "posting_fingerprint": "posting-v1",
        "posting_description": (
            "Build embedded firmware and test sensor systems for autonomous robots."
        ),
        "approved_sources": [
            ApprovedCompanySource(
                url="https://example.com/engineering/robotics",
                source_type=CompanySourceType.OFFICIAL_ENGINEERING,
            )
        ],
    }
    payload.update(updates)
    return CompanyResearchRequest.model_validate(payload)


def test_official_company_research_is_bounded_attributable_and_dated() -> None:
    fetcher = _Fetcher()
    service = BoundedCompanyResearchService(fetcher, today=lambda: date(2026, 7, 21))

    bundle = service.research(_request())

    assert bundle.status is CompanyResearchStatus.VERIFIED
    assert bundle.network_request_count == 1
    assert fetcher.calls == 1
    official = [fact for fact in bundle.facts if fact.confidence is CompanyFactConfidence.VERIFIED]
    assert official
    source_ids = {source.id for source in bundle.sources}
    assert all(fact.source_id in source_ids for fact in official)
    assert all(source.retrieved_on == date(2026, 7, 21) for source in bundle.sources)


def test_research_cache_hit_performs_zero_network_calls() -> None:
    fetcher = _Fetcher()
    service = BoundedCompanyResearchService(fetcher)
    request = _request()
    service.research(request)

    cached = service.research(request)

    assert fetcher.calls == 1
    assert cached.cache_hit
    assert cached.network_request_count == 0
    assert CompanyResearchEvent.RESEARCH_CACHE_HIT in cached.events


def test_changed_posting_fingerprint_invalidates_research_cache() -> None:
    fetcher = _Fetcher()
    service = BoundedCompanyResearchService(fetcher)
    service.research(_request())

    changed = service.research(_request(posting_fingerprint="posting-v2"))

    assert fetcher.calls == 2
    assert not changed.cache_hit


def test_search_result_snippet_is_rejected_without_fetching() -> None:
    fetcher = _Fetcher()
    request = _request(
        approved_sources=[
            ApprovedCompanySource(
                url="https://example.com/search-snippet",
                source_type=CompanySourceType.SEARCH_SNIPPET,
            )
        ]
    )

    bundle = BoundedCompanyResearchService(fetcher).research(request)

    assert fetcher.calls == 0
    assert CompanyResearchEvent.UNVERIFIED_SNIPPET_REJECTED in bundle.events
    assert all(
        source.source_type is not CompanySourceType.SEARCH_SNIPPET for source in bundle.sources
    )


def test_fetch_failure_is_typed_and_posting_fallback_remains_available() -> None:
    fetcher = _FailingFetcher()

    bundle = BoundedCompanyResearchService(fetcher).research(_request())

    assert bundle.status is CompanyResearchStatus.SOURCE_FETCH_FAILED
    assert bundle.network_request_count == 1
    assert any("fetch failed" in limitation.casefold() for limitation in bundle.limitations)
    assert any(fact.confidence is CompanyFactConfidence.POSTING_AUTHORITY for fact in bundle.facts)


def test_research_disabled_uses_posting_without_network() -> None:
    fetcher = _Fetcher()

    bundle = BoundedCompanyResearchService(fetcher).research(_request(enabled=False))

    assert fetcher.calls == 0
    assert bundle.status is CompanyResearchStatus.POSTING_ONLY
    assert "External company research was disabled." in bundle.limitations


def test_no_company_identity_still_retains_posting_authority_without_network() -> None:
    bundle = BoundedCompanyResearchService().research(
        _request(company_name=None, approved_sources=[])
    )

    assert bundle.status is CompanyResearchStatus.POSTING_ONLY
    assert bundle.network_request_count == 0
    assert any(
        source.source_type is CompanySourceType.JOB_POSTING for source in bundle.sources
    )
    assert any(
        fact.confidence is CompanyFactConfidence.POSTING_AUTHORITY for fact in bundle.facts
    )
    assert any(
        "posting remains the only company authority" in limitation
        for limitation in bundle.limitations
    )


def test_cover_letter_rebinds_blank_research_authority_to_active_posting() -> None:
    profile, posting, plan = cover_letter_case()
    request = CompanyResearchRequest(
        company_name=None,
        role_title="",
        posting_fingerprint="",
        posting_description="",
        enabled=False,
    )

    artifact = CoverLetterService(
        renderer=ControlledCoverLetterRenderer([0.94]),
    ).generate_artifact(
        profile,
        posting,
        plan,
        research_request=request,
    )

    assert artifact.fingerprint_inputs.posting_fingerprint == content_fingerprint(posting)
    assert artifact.company_research.status is CompanyResearchStatus.POSTING_ONLY
    assert artifact.company_research.network_request_count == 0
    assert any(
        fact.confidence is CompanyFactConfidence.POSTING_AUTHORITY
        for fact in artifact.company_research.facts
    )


def test_company_research_fetch_limit_is_fixed_at_three() -> None:
    with pytest.raises(ValueError, match="at most 3"):
        BoundedCompanyResearchService(max_fetches=4)


def test_conflicting_authorities_are_visible() -> None:
    request = _request(
        approved_sources=[],
        user_supplied_facts=[
            "The platform does not use embedded firmware and sensor tests for autonomous robots.",
        ],
    )

    bundle = BoundedCompanyResearchService().research(request)

    assert CompanyResearchEvent.CONFLICTING_SOURCES in bundle.events
    assert any(fact.confidence is CompanyFactConfidence.CONFLICTING for fact in bundle.facts)
