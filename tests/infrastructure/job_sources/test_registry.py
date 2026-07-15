from __future__ import annotations

import json

import pytest

from resume_tailor.domain.job_discovery.models import ConnectorType, LeverApiRegion
from resume_tailor.infrastructure.job_sources.registry import (
    SourceConfigurationError,
    SourceRegistry,
    load_source_registry,
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
                    board_token="acme",
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
        _source(source_id="zeta", enabled=True),
        _source(source_id="alpha", enabled=False),
        _source(source_id="beta", enabled=True),
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
    payload = json.dumps({"sources": [_source()]})
    assert load_source_registry(payload)[0].source_id == "acme-greenhouse"


def test_registry_rejects_duplicate_source_ids() -> None:
    with pytest.raises(SourceConfigurationError, match="duplicate"):
        SourceRegistry.from_json(json.dumps([_source(), _source()]))
