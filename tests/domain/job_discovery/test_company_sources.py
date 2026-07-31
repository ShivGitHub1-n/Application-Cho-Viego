from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from resume_tailor.domain.job_discovery.company_sources import (
    AuditedSourcePlan,
    CompanyCareerSource,
    DetailExtractionMode,
    GeographicCoverage,
    GeographicEvidenceKind,
    GeographicEvidenceReference,
    ListingDiscoveryMode,
    PageFetchMode,
    SourceMechanism,
)


def _plan(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "mechanism": "first_party",
        "listing_discovery_mode": "static_index",
        "detail_fetch_mode": "static_http",
        "detail_extraction_mode": "json_ld_then_html",
        "provider_source_id": None,
        "sitemap_urls": [],
        "index_urls": ["https://careers.example.com/jobs"],
        "direct_detail_urls": [],
        "allowed_job_path_patterns": [r"^/jobs/[a-z0-9-]+$"],
        "navigation_hosts": ["careers.example.com"],
        "redirect_hosts": [],
        "browser_resource_hosts": [],
        "browser_api_hosts": [],
        "max_listing_pages": 4,
        "max_browser_listing_pages": 0,
        "max_browser_actions": 0,
        "max_job_detail_pages": 40,
        "max_network_requests": 0,
        "max_total_render_seconds": 0,
        "audit_version": "2026-07-24.1",
        "audit_date": date(2026, 7, 24),
    }
    value.update(overrides)
    return value


def _company(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "source_id": "example-first-party",
        "company_id": "example",
        "canonical_company_name": "Example Robotics",
        "canonical_domain": "careers.example.com",
        "careers_entry_url": "https://careers.example.com/jobs",
        "allowed_hosts": ["careers.example.com"],
        "redirect_hosts": [],
        "industry_tags": ["robotics"],
        "role_family_tags": ["robotics", "software_engineering"],
        "priority_tier": 1,
        "enabled": True,
        "audit_state": "approved",
        "crawl_cadence_minutes": 360,
        "robots_policy": "allow",
        "browser_rendering_allowed": False,
        "source_plan": _plan(),
        "first_party_audit": {
            "canonical_employer_url": "https://careers.example.com/jobs",
            "listing_index_urls": ["https://careers.example.com/jobs"],
            "navigation_hosts": ["careers.example.com"],
            "redirect_hosts": [],
            "allowed_listing_path_patterns": [r"^/jobs/?$"],
            "allowed_detail_path_patterns": [r"^/jobs/[a-z0-9-]+$"],
            "robots_decision": "allow",
            "listing_discovery_mode": "static_index",
            "detail_fetch_mode": "static_http",
            "detail_extraction_mode": "json_ld_then_html",
            "stable_identity_authority": "same-host detail URL",
            "canonical_detail_url_authority": "canonical detail URL",
            "application_url_authority": "same-host detail application action",
            "application_hosts": [
                {
                    "host": "greenhouse.io",
                    "allowed_path_patterns": [r"^/jobs/[0-9]+$"],
                    "audit_reason": "terminal application target",
                }
            ],
            "completeness_boundary": "bounded index",
            "data_authority": "employer_host",
            "competing_provider_authority": False,
            "fixture_index_path": "tests/fixtures/job_sources/company_audits/example_index.json",
            "fixture_detail_path": "tests/fixtures/job_sources/company_audits/example_detail.json",
            "audit_version": "2026-07-24.1",
            "audit_date": date(2026, 7, 24),
        },
        "extraction_profile": None,
        "audit_evidence_urls": ["https://careers.example.com/jobs"],
        "provenance_notes": "Bounded audit fixture.",
    }
    value.update(overrides)
    return value


def test_source_plan_separates_discovery_fetch_and_extraction() -> None:
    source = CompanyCareerSource.model_validate(_company())
    assert source.source_plan.mechanism is SourceMechanism.FIRST_PARTY
    assert source.source_plan.listing_discovery_mode is ListingDiscoveryMode.STATIC_INDEX
    assert source.source_plan.detail_fetch_mode is PageFetchMode.STATIC_HTTP
    assert source.source_plan.detail_extraction_mode is DetailExtractionMode.JSON_LD_THEN_HTML


def test_provider_plan_requires_provider_identity_and_provider_discovery() -> None:
    with pytest.raises(ValidationError):
        AuditedSourcePlan.model_validate(
            _plan(
                mechanism="greenhouse",
                listing_discovery_mode="static_index",
                provider_source_id=None,
            )
        )


def test_browser_plan_requires_hosts_and_positive_limits() -> None:
    with pytest.raises(ValidationError):
        AuditedSourcePlan.model_validate(
            _plan(
                detail_fetch_mode="browser",
                browser_resource_hosts=[],
                max_browser_actions=0,
            )
        )


def test_wildcard_host_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CompanyCareerSource.model_validate(_company(allowed_hosts=["*.example.com"]))


def test_geographic_coverage_normalizes_codes_and_localities() -> None:
    coverage = GeographicCoverage(
        country_codes=["ca", "CA"],
        regions=["Ontario"],
        localities=["Toronto", " toronto ", "North York"],
        toronto_gta_presence=True,
        geographic_evidence=[
            GeographicEvidenceReference(
                evidence_id="office",
                kind=GeographicEvidenceKind.OFFICIAL_OFFICE,
                country_code="CA",
                region="Ontario",
                locality="Toronto",
                source_reference="https://example.com/office",
            )
        ],
        target_user_relevance="toronto_gta",
    )
    assert coverage.country_codes == ["CA"]
    assert coverage.localities == ["north york", "toronto"]


def test_locality_terminal_punctuation_is_a_duplicate_identity() -> None:
    coverage = GeographicCoverage(localities=["Toronto", "Toronto,"])
    assert coverage.localities == ["toronto"]


def test_geographic_evidence_requires_qualified_official_reference() -> None:
    with pytest.raises(ValidationError):
        GeographicCoverage(
            country_codes=["CA"],
            regions=["Ontario"],
            localities=["Toronto"],
            toronto_gta_presence=True,
            geographic_evidence=[
                {
                    "evidence_id": "remote",
                    "kind": "remote_eligibility",
                    "country_code": "CA",
                    "source_reference": "https://example.com/jobs",
                    "note": "remote Canada only",
                }
            ],
        )


def test_geographic_evidence_accepts_official_job_location() -> None:
    coverage = GeographicCoverage(
        country_codes=["CA"],
        regions=["Ontario"],
        localities=["Toronto"],
        toronto_gta_presence=True,
        geographic_evidence=[
            {
                "evidence_id": "job-1",
                "kind": "official_job_location",
                "country_code": "CA",
                "region": "Ontario",
                "locality": "Toronto",
                "source_reference": "https://example.com/jobs/1",
            }
        ],
    )
    assert coverage.toronto_gta_presence is True


@pytest.mark.parametrize("locality", ["Toronto", "North York", "Markham"])
def test_locality_terminal_punctuation_normalizes(locality: str) -> None:
    coverage = GeographicCoverage(localities=[locality, f"{locality}."])
    assert len(coverage.localities) == 1


@pytest.mark.parametrize("value", ["\u0000Toronto", "   ...   ", ""])
def test_invalid_locality_identity_is_rejected(value: str) -> None:
    with pytest.raises(ValidationError):
        GeographicCoverage(localities=[value])


def test_qualifying_and_remote_evidence_can_coexist() -> None:
    coverage = GeographicCoverage(
        localities=["Toronto"],
        toronto_gta_presence=True,
        geographic_evidence=[
            {
                "evidence_id": "office",
                "kind": "official_office",
                "country_code": "CA",
                "locality": "Toronto",
                "source_reference": "https://example.com/office",
            },
            {
                "evidence_id": "remote",
                "kind": "remote_eligibility",
                "country_code": "CA",
                "source_reference": "https://example.com/remote",
            },
        ],
    )
    assert coverage.toronto_gta_presence is True


def test_source_priority_uses_source_id_as_final_tie_break() -> None:
    first = CompanyCareerSource.model_validate(_company(source_id="alpha"))
    second = CompanyCareerSource.model_validate(_company(source_id="beta"))
    assert first.deterministic_source_priority < second.deterministic_source_priority


def test_source_priority_tier_precedes_gta_relevance() -> None:
    higher_tier = CompanyCareerSource.model_validate(
        _company(source_id="gta", priority_tier=2, geographic_coverage={
            "localities": ["Toronto"],
            "toronto_gta_presence": True,
            "geographic_evidence": [{
                "evidence_id": "office",
                "kind": "official_office",
                "country_code": "CA",
                "locality": "Toronto",
                "source_reference": "https://example.com/office",
            }],
        })
    )
    lower_tier = CompanyCareerSource.model_validate(_company(source_id="global", priority_tier=1))
    assert lower_tier.deterministic_source_priority < higher_tier.deterministic_source_priority


@pytest.mark.parametrize("locality", ["Ottawa", "Waterloo", "Kitchener"])
def test_non_gta_locality_does_not_satisfy_toronto_presence(locality: str) -> None:
    with pytest.raises(ValidationError):
        GeographicCoverage(
            country_codes=["CA"],
            regions=["Ontario"],
            localities=[locality],
            toronto_gta_presence=True,
            geographic_evidence=[
                {
                    "evidence_id": "non-gta",
                    "kind": "official_job_location",
                    "country_code": "CA",
                    "locality": locality,
                    "source_reference": "https://example.com/job",
                }
            ],
            target_user_relevance="toronto_gta",
        )


def test_source_priority_is_priority_then_gta_then_source_id() -> None:
    gta = CompanyCareerSource.model_validate(
        _company(
            source_id="zeta",
            geographic_coverage={
                "localities": ["Toronto"],
                "toronto_gta_presence": True,
                "geographic_evidence": [
                    {
                        "evidence_id": "office",
                        "kind": "official_office",
                        "country_code": "CA",
                        "locality": "Toronto",
                        "source_reference": "https://example.com/office",
                    }
                ],
            },
        )
    )
    global_source = CompanyCareerSource.model_validate(_company(source_id="alpha"))
    assert gta.deterministic_source_priority < global_source.deterministic_source_priority
    assert gta.model_copy(
        update={"provenance_notes": "changed prose"}
    ).deterministic_source_priority == gta.deterministic_source_priority
