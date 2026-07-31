from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import TypeAdapter

from tests.job_discovery.benchmark.models import BenchmarkCase, BenchmarkManifest

_MANIFEST_PATH = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "job_discovery"
    / "benchmark"
    / "manifest.json"
)
_CASES = TypeAdapter(list[BenchmarkCase])
_MANIFEST = TypeAdapter(BenchmarkManifest)
_DEVELOPMENT_SPLITS = ("calibration", "validation")


class LockedBenchmarkAccessError(PermissionError):
    """Locked expectations require both a marked test and explicit authorization."""


def _read_manifest() -> BenchmarkManifest:
    return _MANIFEST.validate_json(_MANIFEST_PATH.read_bytes())


def _split_path(manifest: BenchmarkManifest, split: str) -> Path:
    return _MANIFEST_PATH.parent / manifest.splits[split].path


def _read_development_split(manifest: BenchmarkManifest, split: str) -> list[BenchmarkCase]:
    split_config = manifest.splits[split]
    split_path = _split_path(manifest, split)
    raw_bytes = split_path.read_bytes()
    if split_config.sha256:
        actual = hashlib.sha256(raw_bytes).hexdigest()
        if actual != split_config.sha256:
            raise ValueError(f"Checksum mismatch for benchmark split: {split}")
    cases = _CASES.validate_json(raw_bytes)
    ids = [case.case_id for case in cases]
    if ids != split_config.proposed_case_ids:
        raise ValueError(f"Benchmark split membership mismatch: {split}")
    if len(cases) != split_config.case_count or any(case.split != split for case in cases):
        raise ValueError(f"Benchmark split contract mismatch: {split}")
    return cases


def load_cases_for_contract_validation() -> dict[str, list[BenchmarkCase]]:
    """Load only development bodies; locked bodies are intentionally not parsed."""

    manifest = _read_manifest()
    paths = [manifest.splits[name].path for name in (*_DEVELOPMENT_SPLITS, "locked")]
    if paths != ["calibration.json", "validation.json", "locked.json"]:
        raise ValueError("Benchmark split fixtures must be separate, named JSON files")
    return {split: _read_development_split(manifest, split) for split in _DEVELOPMENT_SPLITS}


def load_development_cases() -> list[BenchmarkCase]:
    manifest = _read_manifest()
    cases = [
        case
        for split in _DEVELOPMENT_SPLITS
        for case in _read_development_split(manifest, split)
    ]
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("Benchmark case IDs must be unique across development splits")
    return cases


def load_pilot_calibration_group_01() -> list[BenchmarkCase]:
    """Load only the calibration pilot group for the bounded repair workflow."""

    manifest = _read_manifest()
    cases = _read_development_split(manifest, "calibration")
    pilot = [case for case in cases if case.ranking_group == "calibration-group-01"]
    if len(pilot) != 10:
        raise ValueError("Calibration-group-01 pilot must contain exactly ten cases")
    return pilot


def load_calibration_group(ranking_group: str) -> list[BenchmarkCase]:
    """Load one named calibration group without touching locked fixtures."""

    manifest = _read_manifest()
    cases = _read_development_split(manifest, "calibration")
    group = [case for case in cases if case.ranking_group == ranking_group]
    if len(group) != 10:
        raise ValueError(f"{ranking_group} must contain exactly ten cases")
    return group


def load_validation_group(ranking_group: str) -> list[BenchmarkCase]:
    """Load one named validation group without touching locked fixtures."""

    manifest = _read_manifest()
    cases = _read_development_split(manifest, "validation")
    group = [case for case in cases if case.ranking_group == ranking_group]
    if len(group) != 10:
        raise ValueError(f"{ranking_group} must contain exactly ten cases")
    return group


def locked_proposal_metadata() -> dict[str, object]:
    """Return manifest-only locked metadata without deserializing locked cases."""

    manifest = _read_manifest()
    split = manifest.splits["locked"]
    path = _split_path(manifest, "locked")
    return {
        "path": str(path),
        "sha256": split.sha256,
        "case_count": split.case_count,
        "proposed_case_ids": list(split.proposed_case_ids),
        "bytes_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def load_locked_cases(*, authorized: bool, marker_enabled: bool = False) -> list[BenchmarkCase]:
    """Parse locked expectations only from a dedicated, marked authorized test."""

    if not authorized or not marker_enabled:
        raise LockedBenchmarkAccessError(
            "Locked benchmark loading requires the job_discovery_locked marker "
            "and explicit authorization"
        )
    manifest = _read_manifest()
    split_config = manifest.splits["locked"]
    raw_bytes = _split_path(manifest, "locked").read_bytes()
    if split_config.sha256 != hashlib.sha256(raw_bytes).hexdigest():
        raise ValueError("Checksum mismatch for locked benchmark proposal")
    cases = _CASES.validate_json(raw_bytes)
    if [case.case_id for case in cases] != split_config.proposed_case_ids:
        raise ValueError("Locked benchmark proposal membership mismatch")
    return cases
