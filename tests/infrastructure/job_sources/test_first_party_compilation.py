from datetime import date
from pathlib import Path

import pytest

from resume_tailor.domain.job_discovery.company_sources import SourceMechanism
from resume_tailor.domain.job_discovery.models import ConnectorType, FirstPartySource
from resume_tailor.infrastructure.job_sources.registry import (
    SourceConfigurationError,
    compile_runtime_sources,
    load_company_source_registry,
)

REGISTRY = Path("config/approved-job-sources.json")


def test_compiler_keeps_provider_sources_and_compiles_rocket_lab_as_first_party() -> None:
    registry = load_company_source_registry(REGISTRY, reference_date=date(2026, 7, 26))

    compiled = compile_runtime_sources(registry)

    assert [source.source_id for source in compiled] == sorted(
        source.source_id for source in compiled
    )
    rocket = next(source for source in compiled if source.source_id == "rocket-lab")
    assert isinstance(rocket, FirstPartySource)
    assert rocket.connector_type is ConnectorType.FIRST_PARTY
    assert rocket.mechanism is SourceMechanism.FIRST_PARTY
    assert rocket.provider_configuration is None
    assert rocket.registry_plan_hash
    assert rocket.extraction_profile_hash

    waabi = next(source for source in compiled if source.source_id == "waabi")
    assert waabi.connector_type is ConnectorType.LEVER
    assert waabi.board_token == "waabi"
    assert waabi.lever_api_region.value == "global"

    assert {source.source_id for source in compiled} == {
        "anthropic",
        "anduril",
        "figure",
        "palantir",
        "relativity-space",
        "rocket-lab",
        "spacex",
        "tenstorrent",
        "waabi",
        "zoox",
    }


def test_compiler_rejects_duplicate_provider_authority() -> None:
    registry = load_company_source_registry(REGISTRY, reference_date=date(2026, 7, 26))
    original = next(source for source in registry.list_all() if source.source_id == "anthropic")
    duplicate = original.model_copy(
        update={
            "source_id": "duplicate",
            "company_id": "duplicate",
            "enabled": False,
        }
    )
    duplicate = duplicate.model_copy(
        update={
            "source_plan": duplicate.source_plan.model_copy(
                update={
                    "provider_configuration": duplicate.source_plan.provider_configuration,
                }
            )
        }
    )

    with pytest.raises(SourceConfigurationError, match="duplicate provider-board"):
        compile_runtime_sources([*registry.list_all(), duplicate])


def test_compiler_is_offline_and_does_not_compile_disabled_sources() -> None:
    registry = load_company_source_registry(REGISTRY, reference_date=date(2026, 7, 26))

    compiled = compile_runtime_sources(registry)

    assert all(source.enabled for source in compiled)
    assert "cohere" not in {source.source_id for source in compiled}
    assert "mda-space" not in {source.source_id for source in compiled}


def test_compiled_provider_runtime_source_is_immutable() -> None:
    registry = load_company_source_registry(REGISTRY, reference_date=date(2026, 7, 26))
    source = next(
        item for item in compile_runtime_sources(registry) if item.source_id == "waabi"
    )

    with pytest.raises((TypeError, ValueError)):
        source.board_token = "other-board"  # type: ignore[misc]

    with pytest.raises((TypeError, ValueError)):
        source.lever_api_region = None  # type: ignore[misc]
