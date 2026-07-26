from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from resume_tailor.domain.job_discovery.company_sources import (
    AuditedSourcePlan,
    CompanyCareerSource,
    ProviderConnectorConfiguration,
    SourceAuditFreshnessPolicy,
)
from resume_tailor.infrastructure.job_sources.registry import (
    CompanySourceRegistry,
    SourceConfigurationError,
)


def _first_party_plan(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "mechanism": "first_party",
        "listing_discovery_mode": "static_index",
        "detail_fetch_mode": "static_http",
        "detail_extraction_mode": "json_ld_then_html",
        "provider_configuration": None,
        "sitemap_urls": [],
        "index_urls": ["https://careers.example.com/careers/positions/"],
        "direct_detail_urls": [],
        "allowed_job_path_patterns": [r"^/careers/positions(?:/[^/]+)?/?$"],
        "navigation_hosts": ["careers.example.com"],
        "redirect_hosts": [],
        "browser_resource_hosts": [],
        "browser_api_hosts": [],
        "max_listing_pages": 5,
        "max_browser_listing_pages": 0,
        "max_browser_actions": 0,
        "max_job_detail_pages": 100,
        "max_network_requests": 100,
        "max_total_render_seconds": 0,
        "audit_version": "2026-07-24.1",
        "audit_date": date(2026, 7, 24),
    }
    value.update(overrides)
    return value


def _audit(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "canonical_employer_url": "https://careers.example.com/careers",
        "listing_index_urls": ["https://careers.example.com/careers/positions/"],
        "navigation_hosts": ["careers.example.com"],
        "redirect_hosts": [],
        "allowed_listing_path_patterns": [r"^/careers/positions/?$"],
        "allowed_detail_path_patterns": [r"^/careers/positions/[^/]+/?$"],
        "robots_decision": "allow",
        "listing_discovery_mode": "static_index",
        "detail_fetch_mode": "static_http",
        "detail_extraction_mode": "json_ld_then_html",
        "stable_identity_authority": "same-host detail URL final numeric suffix",
        "canonical_detail_url_authority": "canonical link on employer detail page",
        "application_url_authority": "same-host detail-page application action",
        "application_hosts": [
            {
                "host": "greenhouse.io",
                "allowed_path_patterns": [r"^/jobs/[0-9]+$"],
                "audit_reason": "terminal application target",
            }
        ],
        "completeness_boundary": "bounded Load more terminates without a next page",
        "data_authority": "employer_host",
        "competing_provider_authority": False,
        "fixture_index_path": "tests/fixtures/job_sources/company_audits/example_index.json",
        "fixture_detail_path": "tests/fixtures/job_sources/company_audits/example_detail.json",
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
        "careers_entry_url": "https://careers.example.com/careers",
        "allowed_hosts": ["careers.example.com"],
        "redirect_hosts": [],
        "industry_tags": ["robotics"],
        "role_family_tags": ["robotics"],
        "priority_tier": 1,
        "enabled": True,
        "audit_state": "approved",
        "crawl_cadence_minutes": 360,
        "robots_policy": "allow",
        "browser_rendering_allowed": False,
        "source_plan": _first_party_plan(),
        "first_party_audit": _audit(),
        "audit_evidence_urls": ["https://careers.example.com/careers"],
    }
    value.update(overrides)
    return value


def test_enabled_first_party_source_requires_complete_audit_contract() -> None:
    with pytest.raises(ValidationError):
        CompanyCareerSource.model_validate(_company(first_party_audit=None))


def test_first_party_audit_rejects_unaudited_data_authority() -> None:
    with pytest.raises(ValidationError):
        CompanyCareerSource.model_validate(
            _company(first_party_audit=_audit(data_authority="unaudited_api"))
        )


def test_provider_configuration_requires_exact_board_and_region() -> None:
    greenhouse = ProviderConnectorConfiguration(
        connector_type="greenhouse", board_token="andurilindustries", lever_api_region=None
    )
    assert greenhouse.board_token == "andurilindustries"
    with pytest.raises(ValidationError):
        ProviderConnectorConfiguration(
            connector_type="lever", board_token="palantir", lever_api_region=None
        )


def test_provider_plan_mechanism_must_match_connector_configuration() -> None:
    with pytest.raises(ValidationError):
        AuditedSourcePlan.model_validate(
            {
                "mechanism": "greenhouse",
                "listing_discovery_mode": "provider",
                "detail_fetch_mode": None,
                "detail_extraction_mode": None,
                "provider_configuration": {
                    "connector_type": "lever",
                    "board_token": "wrong",
                    "lever_api_region": "global",
                },
                "audit_version": "2026-07-24.1",
                "audit_date": date(2026, 7, 24),
            }
        )


def test_canonical_domains_are_normalized_before_duplicate_detection() -> None:
    first = CompanyCareerSource.model_validate(_company())
    second_data = _company(
        source_id="other",
        company_id="other",
        canonical_domain="CAREERS.EXAMPLE.COM.",
        careers_entry_url="https://CAREERS.EXAMPLE.COM./careers",
    )
    second = CompanyCareerSource.model_validate(second_data)
    with pytest.raises(SourceConfigurationError, match="canonical domains"):
        CompanySourceRegistry([first, second])


def test_source_plan_rejects_credentials_fragments_http_and_unsupported_ports() -> None:
    with pytest.raises(ValidationError):
        CompanyCareerSource.model_validate(
            _company(careers_entry_url="https://user:password@careers.example.com/careers")
        )
    with pytest.raises(ValidationError):
        CompanyCareerSource.model_validate(
            _company(careers_entry_url="https://careers.example.com/careers#fragment")
        )
    with pytest.raises(ValidationError):
        AuditedSourcePlan.model_validate(
            _first_party_plan(index_urls=["http://careers.example.com/careers/positions/"])
        )
    with pytest.raises(ValidationError):
        AuditedSourcePlan.model_validate(
            _first_party_plan(index_urls=["https://careers.example.com:8443/careers/positions/"])
        )


@pytest.mark.parametrize(
    "pattern",
    [r"^/jobs/%2fsecret$", r"^/jobs/..\\secret$", r"^/jobs/(a+)+$", "not-a-path"],
)
def test_source_plan_rejects_unsafe_path_patterns(pattern: str) -> None:
    with pytest.raises(ValidationError):
        AuditedSourcePlan.model_validate(_first_party_plan(allowed_job_path_patterns=[pattern]))


def test_enabled_source_rejects_blank_or_stale_audit() -> None:
    with pytest.raises(ValidationError):
        CompanyCareerSource.model_validate(
            _company(source_plan=_first_party_plan(audit_version=""))
        )
    source = CompanyCareerSource.model_validate(
        _company(
            source_plan=_first_party_plan(audit_date=date(2020, 1, 1)),
            first_party_audit=_audit(audit_date=date(2020, 1, 1)),
        )
    )
    assert not SourceAuditFreshnessPolicy().evaluate(
        source, reference_date=date(2026, 7, 25)
    ).eligible


def test_first_party_audit_must_match_the_authorized_source_plan() -> None:
    with pytest.raises(ValidationError):
        CompanyCareerSource.model_validate(
            _company(first_party_audit=_audit(detail_fetch_mode="browser"))
        )


def test_audit_freshness_is_injected_and_structural_parsing_is_clock_independent() -> None:
    source = CompanyCareerSource.model_validate(
        _company(
            source_plan=_first_party_plan(audit_date=date(2020, 1, 1)),
            first_party_audit=_audit(audit_date=date(2020, 1, 1)),
        )
    )
    policy = SourceAuditFreshnessPolicy(max_age_days=180)
    assert policy.evaluate(source, reference_date=date(2020, 6, 1)).eligible
    assert not policy.evaluate(source, reference_date=date(2020, 7, 1)).eligible


def test_source_plan_urls_must_use_approved_hosts_and_paths() -> None:
    with pytest.raises(ValidationError):
        CompanyCareerSource.model_validate(
            _company(
                source_plan=_first_party_plan(
                    index_urls=["https://evil.example/jobs/positions/"]
                )
            )
        )
    with pytest.raises(ValidationError):
        CompanyCareerSource.model_validate(
            _company(
                source_plan=_first_party_plan(
                    index_urls=["https://careers.example.com/private/positions/"]
                )
            )
        )
    with pytest.raises(ValidationError):
        CompanyCareerSource.model_validate(
            _company(
                source_plan=_first_party_plan(
                    index_urls=["https://job-boards.greenhouse.io/rocketlab/jobs/1"]
                )
            )
        )
    with pytest.raises(ValidationError):
        CompanyCareerSource.model_validate(
            _company(
                source_plan=_first_party_plan(
                    direct_detail_urls=["https://evil.example/jobs/1"]
                )
            )
        )
    with pytest.raises(ValidationError):
        CompanyCareerSource.model_validate(
            _company(
                source_plan=_first_party_plan(
                    listing_discovery_mode="sitemap",
                    index_urls=[],
                    sitemap_urls=["https://evil.example/sitemap.xml"],
                    sitemap_path_patterns=[r"^/sitemap\.xml$"],
                )
            )
        )


def test_application_hosts_are_terminal_and_normalized() -> None:
    with pytest.raises(ValidationError):
        CompanyCareerSource.model_validate(
            _company(
                first_party_audit=_audit(
                    application_hosts=[
                        {
                            "host": "GREENHOUSE.IO.",
                            "allowed_path_patterns": [r"^/rocketlab/jobs/[0-9]+$"],
                            "audit_reason": "terminal application",
                        },
                        {
                            "host": "greenhouse.io",
                            "allowed_path_patterns": [r"^/rocketlab/jobs/[0-9]+$"],
                            "audit_reason": "duplicate",
                        },
                    ]
                )
            )
        )
    audit = CompanyCareerSource.model_validate(_company()).first_party_audit
    assert audit is not None
    assert not audit.is_application_url_allowed("https://greenhouse.io.evil/jobs/1")
