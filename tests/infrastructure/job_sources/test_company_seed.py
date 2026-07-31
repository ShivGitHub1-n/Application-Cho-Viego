from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from resume_tailor.infrastructure.job_sources.registry import (
    SourceConfigurationError,
    load_company_source_registry,
)

FIXTURE_ROOT = Path("tests/fixtures/job_sources/company_audits")


def _copy_configured_fixtures(payload: dict[str, object], root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for company in payload["companies"]:  # type: ignore[union-attr]
        references: list[str] = list(company.get("audit_fixture_paths", []))  # type: ignore[union-attr]
        audit = company.get("first_party_audit")  # type: ignore[union-attr]
        if audit:
            references.extend([audit["fixture_index_path"], audit["fixture_detail_path"]])  # type: ignore[index]
        for reference in references:
            destination = root / reference
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(FIXTURE_ROOT / reference, destination)


def test_authoritative_seed_has_broad_disabled_registry_and_active_mvp() -> None:
    path = Path("config/approved-job-sources.json")
    registry = load_company_source_registry(path)
    sources = registry.list_all()
    enabled = registry.list_enabled()

    assert len(sources) == 41
    assert len(enabled) == 10
    assert {source.source_id for source in enabled} == {
        "anthropic",
        "anduril",
        "palantir",
        "zoox",
        "spacex",
        "relativity-space",
        "figure",
        "rocket-lab",
        "waabi",
        "tenstorrent",
    }
    assert sum(source.source_plan.mechanism.value == "first_party" for source in enabled) == 1
    assert all(source.audit_state.value == "approved" for source in enabled)
    assert all(source.source_plan.mechanism.value != "deferred" for source in enabled)
    assert all(source.source_plan.audit_version for source in enabled)
    rocket = next(source for source in enabled if source.source_id == "rocket-lab")
    assert rocket.first_party_audit is not None
    assert (FIXTURE_ROOT / rocket.first_party_audit.fixture_index_path).is_file()
    assert (FIXTURE_ROOT / rocket.first_party_audit.fixture_detail_path).is_file()


def test_enabled_provider_configuration_matches_audited_board_identity() -> None:
    registry = load_company_source_registry(Path("config/approved-job-sources.json"))
    expected = {
        "anthropic": ("greenhouse", "anthropic", None),
        "anduril": ("greenhouse", "andurilindustries", None),
        "palantir": ("lever", "palantir", "global"),
        "zoox": ("lever", "zoox", "global"),
        "spacex": ("greenhouse", "spacex", None),
        "relativity-space": ("greenhouse", "relativity", None),
        "figure": ("greenhouse", "figureai", None),
        "waabi": ("lever", "waabi", "global"),
        "tenstorrent": ("greenhouse", "tenstorrent", None),
    }
    for source_id, identity in expected.items():
        provider = next(
            source.source_plan.provider_configuration
            for source in registry.list_enabled()
            if source.source_id == source_id
        )
        assert (
            provider.connector_type,
            provider.board_token,
            provider.lever_api_region,
        ) == identity


def test_enabled_toronto_provider_audits_are_fixture_backed() -> None:
    registry = load_company_source_registry(Path("config/approved-job-sources.json"))
    for source_id in {"waabi", "tenstorrent"}:
        source = next(item for item in registry.list_enabled() if item.source_id == source_id)
        assert source.audit_fixture_paths
        for path in source.audit_fixture_paths:
            fixture = json.loads((FIXTURE_ROOT / path).read_text(encoding="utf-8"))
            assert fixture["description"] == "[redacted]"
            assert fixture["candidate_data"] is False


def test_rocket_lab_audit_fixture_is_redacted_and_first_party() -> None:
    registry = load_company_source_registry(Path("config/approved-job-sources.json"))
    source = next(item for item in registry.list_enabled() if item.source_id == "rocket-lab")
    assert source.first_party_audit is not None
    index = json.loads(
        (FIXTURE_ROOT / source.first_party_audit.fixture_index_path).read_text(encoding="utf-8")
    )
    detail = json.loads(
        (FIXTURE_ROOT / source.first_party_audit.fixture_detail_path).read_text(encoding="utf-8")
    )
    assert index["third_party_authority_hosts"] == []
    assert detail["third_party_authority_hosts"] == []
    assert detail["description"] == "[redacted]"
    assert source.first_party_audit.data_authority == "employer_host"
    assert source.first_party_audit.application_url_authority
    assert [rule.host for rule in source.first_party_audit.application_hosts] == [
        "job-boards.greenhouse.io"
    ]
    assert source.first_party_audit.is_application_url_allowed(detail["application_url"])


def test_disabled_entries_are_deferred_and_not_runnable() -> None:
    registry = load_company_source_registry(Path("config/approved-job-sources.json"))
    assert all(
        not source.enabled
        for source in registry.list_all()
        if source.audit_state.value != "approved"
    )
    assert all(
        source.source_plan.mechanism.value == "deferred"
        for source in registry.list_all()
        if not source.enabled
    )


def test_enabled_toronto_sources_have_evidenced_geographic_coverage() -> None:
    registry = load_company_source_registry(Path("config/approved-job-sources.json"))
    for source_id in {"waabi", "tenstorrent"}:
        source = next(item for item in registry.list_enabled() if item.source_id == source_id)
        assert source.geographic_coverage.toronto_gta_presence is True
        assert source.geographic_coverage.geographic_evidence
        assert "toronto" in source.geographic_coverage.localities or (
            "north york" in source.geographic_coverage.localities
        )


def test_unsupported_primary_candidates_remain_deferred() -> None:
    registry = load_company_source_registry(Path("config/approved-job-sources.json"))
    for source_id in {"cohere", "mda-space"}:
        source = next(item for item in registry.list_all() if item.source_id == source_id)
        assert source.enabled is False
        assert source.audit_state.value == "deferred"
        assert source.source_plan.mechanism.value == "deferred"


def test_registry_rejects_missing_audit_fixture(tmp_path: Path) -> None:
    payload = json.loads(Path("config/approved-job-sources.json").read_text(encoding="utf-8"))
    waabi = next(item for item in payload["companies"] if item["source_id"] == "waabi")
    waabi["audit_fixture_paths"] = ["missing.json"]
    with pytest.raises(SourceConfigurationError, match="fixture"):
        load_company_source_registry(
            json.dumps(payload), fixture_root=tmp_path
        )


def test_registry_rejects_fixture_outside_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    payload = json.loads(Path("config/approved-job-sources.json").read_text(encoding="utf-8"))
    waabi = next(item for item in payload["companies"] if item["source_id"] == "waabi")
    waabi["audit_fixture_paths"] = ["../outside.json"]
    with pytest.raises(SourceConfigurationError, match="fixture"):
        load_company_source_registry(
            json.dumps(payload), fixture_root=tmp_path
        )


@pytest.mark.parametrize(
    "reference",
    [
        "..\\outside.json",
        "docs/outside.json",
        "docs\\outside.json",
        "C:relative.json",
        "C:\\absolute.json",
        "C:/absolute.json",
        "/tmp/outside.json",
    ],
)
def test_registry_rejects_unsafe_fixture_reference(tmp_path: Path, reference: str) -> None:
    payload = json.loads(Path("config/approved-job-sources.json").read_text(encoding="utf-8"))
    waabi = next(item for item in payload["companies"] if item["source_id"] == "waabi")
    waabi["audit_fixture_paths"] = [reference]
    with pytest.raises(SourceConfigurationError, match="fixture"):
        load_company_source_registry(json.dumps(payload), fixture_root=tmp_path)


def test_registry_rejects_fixture_directory_and_unsupported_extension(tmp_path: Path) -> None:
    payload = json.loads(Path("config/approved-job-sources.json").read_text(encoding="utf-8"))
    waabi = next(item for item in payload["companies"] if item["source_id"] == "waabi")
    (tmp_path / "nested").mkdir()
    for reference in ["nested", "fixture.txt"]:
        if reference.endswith(".txt"):
            (tmp_path / reference).write_text("{}", encoding="utf-8")
        waabi["audit_fixture_paths"] = [reference]
        with pytest.raises(SourceConfigurationError, match="fixture"):
            load_company_source_registry(json.dumps(payload), fixture_root=tmp_path)


def test_registry_rejects_oversized_fixture(tmp_path: Path) -> None:
    payload = json.loads(Path("config/approved-job-sources.json").read_text(encoding="utf-8"))
    _copy_configured_fixtures(payload, tmp_path)
    waabi = next(item for item in payload["companies"] if item["source_id"] == "waabi")
    waabi["audit_fixture_paths"] = ["nested/large.json"]
    large = tmp_path / "nested" / "large.json"
    large.parent.mkdir(exist_ok=True)
    large.write_text("{" + "\"x\":\"" + ("x" * 1_000_000) + "\"}", encoding="utf-8")
    with pytest.raises(SourceConfigurationError, match="size"):
        load_company_source_registry(json.dumps(payload), fixture_root=tmp_path)


def test_registry_accepts_valid_nested_fixture(tmp_path: Path) -> None:
    payload = json.loads(Path("config/approved-job-sources.json").read_text(encoding="utf-8"))
    _copy_configured_fixtures(payload, tmp_path)
    waabi = next(item for item in payload["companies"] if item["source_id"] == "waabi")
    waabi["audit_fixture_paths"] = ["nested/waabi.json"]
    destination = tmp_path / "nested" / "waabi.json"
    destination.parent.mkdir(exist_ok=True)
    shutil.copyfile(FIXTURE_ROOT / "waabi_board.json", destination)
    registry = load_company_source_registry(json.dumps(payload), fixture_root=tmp_path)
    assert any(source.source_id == "waabi" for source in registry.list_enabled())
