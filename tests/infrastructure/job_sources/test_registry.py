from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from resume_tailor.domain.job_discovery.company_sources import ExtractionProfileSpec, RobotsPolicy
from resume_tailor.domain.job_discovery.models import ConnectorType, LeverApiRegion
from resume_tailor.infrastructure.job_sources.registry import (
    CompanySourceRegistry,
    SourceConfigurationError,
    SourceRegistry,
    adapt_legacy_sources,
    compute_extraction_profile_hash,
    compute_registry_plan_hash,
    load_approved_source_registry,
    load_company_source_registry,
    load_source_registry,
    validate_legacy_compatibility,
)


def _source(**overrides: object) -> dict[str, object]:
    source = {
        "source_id": "acme-greenhouse",
        "connector_type": "greenhouse",
        "company_name": "Acme Robotics",
        "board_token": "acme",
        "enabled": True,
        "official_base_url": "https://boards.greenhouse.io",
        "lever_api_region": None,
    }
    source.update(overrides)
    return source


def test_default_registry_is_empty() -> None:
    assert SourceRegistry().list_enabled() == []
    assert load_source_registry() == []


@pytest.mark.parametrize(
    ("payload", "connector_type", "region"),
    [
        ([_source()], ConnectorType.GREENHOUSE, None),
        (
            [
                _source(
                    source_id="acme-lever-global",
                    connector_type="lever",
                    official_base_url="https://jobs.lever.co",
                    lever_api_region="global",
                )
            ],
            ConnectorType.LEVER,
            LeverApiRegion.GLOBAL,
        ),
        (
            [
                _source(
                    source_id="acme-lever-eu",
                    connector_type="lever",
                    board_token="acme-eu",
                    official_base_url="https://jobs.eu.lever.co",
                    lever_api_region="eu",
                )
            ],
            ConnectorType.LEVER,
            LeverApiRegion.EU,
        ),
    ],
)
def test_loads_valid_explicit_sources(
    payload: list[dict[str, object]],
    connector_type: ConnectorType,
    region: LeverApiRegion | None,
) -> None:
    sources = load_source_registry(json.dumps(payload))
    assert len(sources) == 1
    assert sources[0].connector_type is connector_type
    assert sources[0].lever_api_region is region


def test_disabled_sources_are_not_returned_and_order_is_deterministic() -> None:
    payload = [
        _source(source_id="zeta"),
        _source(source_id="alpha", board_token="alpha", enabled=False),
        _source(source_id="beta", board_token="beta"),
    ]
    registry = SourceRegistry.from_json(json.dumps(payload))
    assert [source.source_id for source in registry.list_enabled()] == ["beta", "zeta"]


@pytest.mark.parametrize(
    "payload",
    [
        "not-json",
        json.dumps({"sources": {}}),
        json.dumps([_source(connector_type="unsupported")]),
        json.dumps([_source(board_token="")]),
        json.dumps([_source(enabled="yes")]),
        json.dumps([_source(official_base_url="ftp://boards.greenhouse.io")]),
        json.dumps(
            [
                _source(
                    connector_type="lever",
                    official_base_url="https://jobs.lever.co",
                    lever_api_region="mars",
                )
            ]
        ),
        json.dumps([_source(connector_type="greenhouse", lever_api_region="global")]),
    ],
)
def test_invalid_operator_configuration_raises_source_configuration_error(payload: str) -> None:
    with pytest.raises(SourceConfigurationError):
        load_source_registry(payload)


def test_object_configuration_requires_a_sources_list() -> None:
    assert (
        load_source_registry(json.dumps({"sources": [_source()]}))[0].source_id == "acme-greenhouse"
    )


def test_registry_rejects_duplicate_source_ids() -> None:
    with pytest.raises(SourceConfigurationError, match="duplicate"):
        SourceRegistry.from_json(json.dumps([_source(), _source()]))


def test_legacy_registry_rejects_duplicate_provider_board_identity() -> None:
    with pytest.raises(SourceConfigurationError, match="provider-board"):
        SourceRegistry.from_json(
            json.dumps([_source(), _source(source_id="other-source")])
        )


def test_registry_rejects_duplicate_company_and_provider_identity() -> None:
    registry = load_company_source_registry(Path("config/approved-job-sources.json"))
    source = next(
        item for item in registry.list_all() if item.source_plan.provider_configuration is not None
    )
    with pytest.raises(SourceConfigurationError, match="company_id"):
        CompanySourceRegistry([source, source.model_copy(update={"source_id": "other"})])
    duplicate = source.model_copy(
        update={"source_id": "other", "company_id": "other", "canonical_domain": "other.example"}
    )
    with pytest.raises(SourceConfigurationError, match="provider-board"):
        CompanySourceRegistry([source, duplicate])


def test_hashes_ignore_display_metadata_but_track_execution_plan() -> None:
    registry = load_company_source_registry(Path("config/approved-job-sources.json"))
    source = registry.list_all()[0]
    baseline = [source]
    display_change = source.model_copy(update={"enabled": not source.enabled, "priority_tier": 99})
    assert compute_registry_plan_hash(baseline) == compute_registry_plan_hash([display_change])
    plan_change = source.model_copy(
        update={"source_plan": source.source_plan.model_copy(update={"max_listing_pages": 19})}
    )
    assert compute_registry_plan_hash(baseline) != compute_registry_plan_hash([plan_change])
    profile_change = source.model_copy(
        update={
            "extraction_profile": ExtractionProfileSpec(
                profile_id="profile", title_selectors=[".job-title"]
            )
        }
    )
    assert compute_extraction_profile_hash(baseline) != compute_extraction_profile_hash(
        [profile_change]
    )


def test_geographic_metadata_does_not_change_execution_plan_hash() -> None:
    registry = load_company_source_registry(Path("config/approved-job-sources.json"))
    source = next(item for item in registry.list_enabled() if item.source_id == "waabi")
    changed = source.model_copy(
        update={
            "geographic_coverage": source.geographic_coverage.model_copy(
                update={
                    "geographic_evidence": [
                        source.geographic_coverage.geographic_evidence[0].model_copy(
                            update={"note": "revised evidence wording"}
                        )
                    ]
                }
            )
        }
    )
    assert compute_registry_plan_hash([source]) == compute_registry_plan_hash([changed])


def test_registry_plan_hash_ignores_audit_date_but_tracks_robots_policy() -> None:
    registry = load_company_source_registry(Path("config/approved-job-sources.json"))
    source = next(item for item in registry.list_all() if item.source_id == "rocket-lab")
    date_change = source.model_copy(
        update={
            "source_plan": source.source_plan.model_copy(
                update={"audit_date": date(2026, 7, 25)}
            ),
            "first_party_audit": source.first_party_audit.model_copy(
                update={"audit_date": date(2026, 7, 25)}
            ),
        }
    )
    assert compute_registry_plan_hash([source]) == compute_registry_plan_hash([date_change])
    robots_change = source.model_copy(update={"robots_policy": RobotsPolicy.DEFER})
    assert compute_registry_plan_hash([source]) != compute_registry_plan_hash([robots_change])


def test_legacy_same_board_is_rejected_even_when_source_ids_differ() -> None:
    company_registry = load_company_source_registry(Path("config/approved-job-sources.json"))
    company = next(item for item in company_registry.list_all() if item.source_id == "anthropic")
    legacy = load_source_registry(
        json.dumps(
            [
                _source(
                    source_id="legacy-anthropic",
                    board_token="anthropic",
                    company_name="Different Display Name",
                )
            ]
        )
    )[0]
    with pytest.raises(SourceConfigurationError, match="same provider board"):
        validate_legacy_compatibility([company], [legacy])


def test_legacy_conflict_is_checked_during_company_registry_load() -> None:
    legacy = load_source_registry(json.dumps([_source(board_token="anthropic")]))[0]
    with pytest.raises(SourceConfigurationError, match="same provider board"):
        CompanySourceRegistry.from_path(
            Path("config/approved-job-sources.json"), legacy_sources=[legacy]
        )


def test_approved_loader_mandatorily_checks_legacy_configuration() -> None:
    legacy = json.dumps([_source(board_token="anthropic")])
    with pytest.raises(SourceConfigurationError, match="same provider board"):
        load_approved_source_registry(
            Path("config/approved-job-sources.json"), legacy
        )


def test_loader_freshness_policy_rejects_stale_enabled_sources_without_mutation() -> None:
    registry = load_company_source_registry(Path("config/approved-job-sources.json"))
    source = next(item for item in registry.list_all() if item.source_id == "anthropic")
    stale = source.model_copy(
        update={
            "source_plan": source.source_plan.model_copy(update={"audit_date": date(2020, 1, 1)})
        }
    )
    payload = json.dumps(
        {"version": 1, "companies": [stale.model_dump(mode="json")]}
    )
    with pytest.raises(SourceConfigurationError, match="stale"):
        load_company_source_registry(payload, reference_date=date(2020, 7, 1))
    structural = CompanySourceRegistry.from_json(payload)
    assert structural.list_all()[0].source_plan.audit_date == date(2020, 1, 1)


def test_legacy_adaptation_is_not_fabricated_audit_approval() -> None:
    legacy = load_source_registry(json.dumps([_source(enabled=True)]))[0]
    adapted = adapt_legacy_sources([legacy])[0]
    assert adapted.enabled is False
    assert adapted.audit_state.value == "deferred"
    assert adapted.source_plan.audit_date is None
    assert "manual/provider compatibility only" in adapted.provenance_notes
