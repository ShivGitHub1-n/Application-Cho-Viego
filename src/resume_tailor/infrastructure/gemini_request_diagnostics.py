from __future__ import annotations

import re
from importlib.metadata import PackageNotFoundError, version
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from resume_tailor.domain.hybrid_resume import ProviderRequestShapeDiagnostic
from resume_tailor.infrastructure.gemini_schema import GeminiSchemaTransform

_GEMINI_31_MINIMUM_SDK = (2, 1, 0)


def google_genai_version() -> str:
    try:
        return version("google-genai")
    except PackageNotFoundError:
        return "not-installed"


def build_request_shape_diagnostic(
    *,
    client: object,
    model: str,
    config: object,
    schema_transform: GeminiSchemaTransform,
    sdk_version: str | None = None,
) -> ProviderRequestShapeDiagnostic:
    resolved_sdk_version = sdk_version or google_genai_version()
    api_version, endpoint = _client_endpoint(client)
    config_fields = _config_fields(config)
    audit = schema_transform.provider_audit
    findings = [
        *schema_transform.provider_audit.complexity_findings,
        *_sdk_api_compatibility_findings(
            model=model,
            sdk_version=resolved_sdk_version,
            api_version=api_version,
        ),
    ]
    if schema_transform.inlined_ref_count:
        findings.append(
            f"provider_schema_inlined_local_refs:{schema_transform.inlined_ref_count}"
        )
    if audit.unsupported_keyword_paths:
        findings.append(
            "unsupported_provider_schema_keywords:"
            + ",".join(audit.unsupported_keyword_paths)
        )
    return ProviderRequestShapeDiagnostic(
        sdk_package="google-genai",
        sdk_version=resolved_sdk_version,
        api_version=api_version,
        endpoint=endpoint,
        model=model,
        config_field_names=sorted(config_fields),
        request_field_types={
            "config": type(config).__name__,
            "contents": "str",
            "model": "str",
            **{
                f"config.{field_name}": type(field_value).__name__
                for field_name, field_value in sorted(config_fields.items())
            },
        },
        schema_byte_length=audit.byte_length,
        schema_nesting_depth=audit.nesting_depth,
        schema_property_count=audit.property_count,
        schema_enum_count=audit.enum_count,
        schema_ref_count=audit.ref_count,
        schema_defs_count=audit.defs_count,
        schema_pre_inline_ref_count=schema_transform.pre_inline_audit.ref_count,
        schema_pre_inline_defs_count=schema_transform.pre_inline_audit.defs_count,
        schema_inlined_ref_count=schema_transform.inlined_ref_count,
        source_schema_ref_sibling_violation_paths=list(
            schema_transform.source_audit.ref_sibling_violation_paths
        ),
        schema_ref_sibling_violation_paths=list(
            schema_transform.pre_inline_audit.ref_sibling_violation_paths
        ),
        schema_keywords=list(audit.keywords),
        removed_schema_keywords=sorted(
            {path.rsplit(".", 1)[-1] for path in schema_transform.removed_keyword_paths}
        ),
        compatibility_findings=list(dict.fromkeys(findings)),
    )


def has_incompatible_sdk_or_api(
    diagnostic: ProviderRequestShapeDiagnostic,
) -> bool:
    return any(
        finding.startswith("incompatible_sdk_api_version:")
        for finding in diagnostic.compatibility_findings
    )


def _config_fields(config: object) -> dict[str, object]:
    if isinstance(config, dict):
        return {str(key): value for key, value in config.items() if value is not None}
    fields_set = getattr(config, "model_fields_set", None)
    if isinstance(fields_set, set):
        return {
            str(field_name): getattr(config, field_name)
            for field_name in fields_set
            if getattr(config, field_name, None) is not None
        }
    return {}


def _client_endpoint(client: object) -> tuple[str | None, str | None]:
    api_client = getattr(client, "_api_client", None)
    http_options = getattr(api_client, "_http_options", None)
    api_version = _safe_scalar(getattr(http_options, "api_version", None))
    endpoint = _safe_endpoint(getattr(http_options, "base_url", None))
    return api_version, endpoint


def _safe_scalar(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text[:80] if re.fullmatch(r"[A-Za-z0-9._/-]+", text) else None


def _safe_endpoint(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))[:240]


def _sdk_api_compatibility_findings(
    *,
    model: str,
    sdk_version: str,
    api_version: str | None,
) -> list[str]:
    findings: list[str] = []
    if model.startswith("gemini-3.1-") and _version_tuple(sdk_version) < (
        _GEMINI_31_MINIMUM_SDK
    ):
        findings.append(
            "incompatible_sdk_api_version:gemini-3.1 requires google-genai>=2.1.0"
        )
    if api_version is not None and api_version not in {"v1", "v1beta"}:
        findings.append(
            f"incompatible_sdk_api_version:unsupported_generate_content_api={api_version}"
        )
    return findings


def _version_tuple(value: str) -> tuple[int, int, int]:
    parts = [int(part) for part in re.findall(r"\d+", value)[:3]]
    padded = (parts + [0, 0, 0])[:3]
    return padded[0], padded[1], padded[2]


__all__ = [
    "build_request_shape_diagnostic",
    "google_genai_version",
    "has_incompatible_sdk_or_api",
]
