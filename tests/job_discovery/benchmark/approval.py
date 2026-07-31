from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from tests.job_discovery.benchmark.loader import _read_development_split, _read_manifest
from tests.job_discovery.benchmark.metrics import canonical_json
from tests.job_discovery.benchmark.models import BenchmarkCase

_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "job_discovery" / "benchmark"
APPROVAL_PATH = _ROOT / "approval.json"


def _approved_payload(value: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload = copy.deepcopy(value)
    for case in payload:
        case.pop("reviewer_decision", None)
        case.pop("reviewer_notes", None)
        case.pop("approval_status", None)
        case.pop("stage", None)
        case.pop("proposal_status", None)
    return payload


def approved_calibration_checksum(value: list[dict[str, Any]]) -> str:
    return hashlib.sha256(canonical_json(_approved_payload(value)).encode("utf-8")).hexdigest()


def approved_validation_checksum(value: list[dict[str, Any]]) -> str:
    return hashlib.sha256(canonical_json(_approved_payload(value)).encode("utf-8")).hexdigest()


def validation_semantic_decision_digest(value: list[dict[str, Any]]) -> str:
    """Hash validation decisions while excluding the two authorized explanation edits."""
    payload = _approved_payload(value)
    for case in payload:
        if case["case_id"] == "validation-064":
            case["rationale"] = ""
        elif case["case_id"] == "validation-070":
            for pair in case["comparable_pair_annotations"]:
                if pair["other_case_id"] == "validation-064":
                    pair.pop("rationale", None)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def load_approval_record() -> dict[str, Any]:
    return json.loads(APPROVAL_PATH.read_text(encoding="utf-8"))


def load_approved_calibration() -> list[BenchmarkCase]:
    manifest = _read_manifest()
    record = load_approval_record()
    approval = record["calibration"]
    if approval.get("approved") is not True or approval.get("approval_status") != "approved":
        raise ValueError("Calibration approval is not recorded in the approval record")
    if approval.get("labels_frozen") is not True:
        raise ValueError("Approved calibration labels are not frozen")
    if manifest.approval_status != "partially_approved":
        raise ValueError("Manifest does not record a partially approved benchmark")
    if manifest.approval.get("calibration_approval_status") != "approved":
        raise ValueError("Manifest does not record approved calibration")
    if manifest.approval.get("calibration_approved_checksum") != approval.get("approved_checksum"):
        raise ValueError("Manifest calibration checksum does not match approval record")
    cases = _read_development_split(manifest, "calibration")
    raw = json.loads((_ROOT / manifest.splits["calibration"].path).read_text(encoding="utf-8"))
    if approved_calibration_checksum(raw) != approval["approved_checksum"]:
        raise ValueError("Approved calibration checksum mismatch")
    return [case.model_copy(update={"stage": "B", "approval_status": "approved"}) for case in cases]


def load_approved_validation() -> list[BenchmarkCase]:
    manifest = _read_manifest()
    record = load_approval_record()
    approval = record["validation"]
    if approval.get("approved") is not True or approval.get("approval_status") != "approved":
        raise ValueError("Validation approval is not recorded in the approval record")
    if approval.get("labels_frozen") is not True:
        raise ValueError("Approved validation labels are not frozen")
    if manifest.approval_status != "partially_approved":
        raise ValueError("Manifest does not record a partially approved benchmark")
    if manifest.approval.get("validation_approval_status") != "approved":
        raise ValueError("Manifest does not record approved validation")
    if manifest.approval.get("validation_approved_checksum") != approval.get("approved_checksum"):
        raise ValueError("Manifest validation checksum does not match approval record")
    if manifest.approval.get("validation_semantic_decision_digest") != approval.get(
        "semantic_decision_digest"
    ):
        raise ValueError("Manifest validation semantic digest does not match approval record")
    cases = _read_development_split(manifest, "validation")
    raw = json.loads((_ROOT / manifest.splits["validation"].path).read_text(encoding="utf-8"))
    if approved_validation_checksum(raw) != approval["approved_checksum"]:
        raise ValueError("Approved validation checksum mismatch")
    if validation_semantic_decision_digest(raw) != approval["semantic_decision_digest"]:
        raise ValueError("Approved validation semantic-decision digest mismatch")
    return [case.model_copy(update={"stage": "B", "approval_status": "approved"}) for case in cases]
