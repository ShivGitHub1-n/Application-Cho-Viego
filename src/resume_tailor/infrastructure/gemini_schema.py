from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, cast

from pydantic import BaseModel

_SUPPORTED_SCHEMA_KEYWORDS = frozenset(
    {
        "$anchor",
        "$defs",
        "$id",
        "$ref",
        "additionalProperties",
        "anyOf",
        "description",
        "enum",
        "format",
        "items",
        "maxItems",
        "maximum",
        "minItems",
        "minimum",
        "oneOf",
        "prefixItems",
        "properties",
        "propertyOrdering",
        "required",
        "title",
        "type",
    }
)
_LOCALLY_ENFORCED_KEYWORDS = frozenset(
    {
        "$schema",
        "const",
        "default",
        "examples",
        "maxLength",
        "minLength",
        "pattern",
        "uniqueItems",
    }
)
_UNSUPPORTED_STRUCTURAL_KEYWORDS = frozenset({"allOf", "not", "if", "then", "else"})


@dataclass(frozen=True)
class GeminiSchemaAudit:
    byte_length: int
    nesting_depth: int
    property_count: int
    enum_count: int
    ref_count: int
    defs_count: int
    keywords: tuple[str, ...]
    unsupported_keyword_paths: tuple[str, ...]
    ref_sibling_violation_paths: tuple[str, ...]
    complexity_findings: tuple[str, ...]


@dataclass(frozen=True)
class GeminiSchemaTransform:
    schema: dict[str, Any]
    source_audit: GeminiSchemaAudit
    pre_inline_audit: GeminiSchemaAudit
    provider_audit: GeminiSchemaAudit
    removed_keyword_paths: tuple[str, ...]
    inlined_ref_count: int


class GeminiSchemaCompatibilityError(ValueError):
    pass


def gemini_response_schema(
    model_type: type[BaseModel],
    *,
    excluded_properties: set[str] | None = None,
) -> dict[str, Any]:
    """Return a non-mutating Gemini JSON-Schema view of one canonical model.

    The provider view removes only validation/annotation keywords that Gemini's
    documented JSON-Schema subset does not accept. Pydantic validation against
    ``model_type`` remains authoritative after the response is received.
    """

    return gemini_schema_transform(
        model_type,
        excluded_properties=excluded_properties,
    ).schema


def gemini_schema_transform(
    model_type: type[BaseModel],
    *,
    excluded_properties: set[str] | None = None,
) -> GeminiSchemaTransform:
    return transform_gemini_schema(
        model_type.model_json_schema(),
        excluded_properties=excluded_properties,
    )


def transform_gemini_schema(
    schema: dict[str, Any],
    *,
    excluded_properties: set[str] | None = None,
) -> GeminiSchemaTransform:
    """Build the Gemini view for an already materialized JSON Schema."""

    raw_schema = deepcopy(schema)
    source_audit = audit_gemini_schema(raw_schema)
    structural_paths = tuple(
        path
        for path in source_audit.unsupported_keyword_paths
        if path.rsplit(".", 1)[-1] in _UNSUPPORTED_STRUCTURAL_KEYWORDS
    )
    if structural_paths:
        raise GeminiSchemaCompatibilityError(
            "Gemini provider schema contains unsupported structural keywords at: "
            + ", ".join(structural_paths)
        )
    removed: list[str] = []
    transformed = _transform_schema(
        deepcopy(raw_schema),
        excluded_properties or set(),
        "$",
        removed,
    )
    transformed_schema = cast(dict[str, Any], transformed)
    pre_inline_audit = audit_gemini_schema(transformed_schema)
    provider_schema, inlined_ref_count = inline_local_schema_refs(transformed_schema)
    provider_audit = audit_gemini_schema(provider_schema)
    if provider_audit.unsupported_keyword_paths:
        raise GeminiSchemaCompatibilityError(
            "Gemini provider schema still contains unsupported keywords at: "
            + ", ".join(provider_audit.unsupported_keyword_paths)
        )
    return GeminiSchemaTransform(
        schema=provider_schema,
        source_audit=source_audit,
        pre_inline_audit=pre_inline_audit,
        provider_audit=provider_audit,
        removed_keyword_paths=tuple(sorted(removed)),
        inlined_ref_count=inlined_ref_count,
    )


def audit_gemini_schema(schema: dict[str, Any]) -> GeminiSchemaAudit:
    state = _AuditState()
    _audit_schema_node(schema, "$", 1, state)
    encoded = json.dumps(
        schema,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    complexity: list[str] = []
    if len(encoded) > 32_000:
        complexity.append("schema_byte_length_exceeds_conservative_32000_boundary")
    if state.maximum_depth > 16:
        complexity.append("schema_nesting_depth_exceeds_conservative_16_boundary")
    if state.property_count > 128:
        complexity.append("schema_property_count_exceeds_conservative_128_boundary")
    return GeminiSchemaAudit(
        byte_length=len(encoded),
        nesting_depth=state.maximum_depth,
        property_count=state.property_count,
        enum_count=state.enum_count,
        ref_count=state.ref_count,
        defs_count=state.defs_count,
        keywords=tuple(sorted(state.keywords)),
        unsupported_keyword_paths=tuple(sorted(state.unsupported_keyword_paths)),
        ref_sibling_violation_paths=tuple(
            sorted(state.ref_sibling_violation_paths)
        ),
        complexity_findings=tuple(complexity),
    )


@dataclass
class _AuditState:
    maximum_depth: int = 0
    property_count: int = 0
    enum_count: int = 0
    ref_count: int = 0
    defs_count: int = 0
    keywords: set[str] = field(default_factory=set)
    unsupported_keyword_paths: list[str] = field(default_factory=list)
    ref_sibling_violation_paths: list[str] = field(default_factory=list)


def _audit_schema_node(
    node: object,
    path: str,
    depth: int,
    state: _AuditState,
) -> None:
    if not isinstance(node, dict):
        return
    state.maximum_depth = max(state.maximum_depth, depth)
    if "$ref" in node and any(not key.startswith("$") for key in node if key != "$ref"):
        state.ref_sibling_violation_paths.append(path)
    for key, value in node.items():
        state.keywords.add(key)
        if key not in _SUPPORTED_SCHEMA_KEYWORDS:
            state.unsupported_keyword_paths.append(f"{path}.{key}")
        if key == "properties" and isinstance(value, dict):
            state.property_count += len(value)
            for property_name, property_schema in value.items():
                _audit_schema_node(
                    property_schema,
                    f"{path}.properties.{property_name}",
                    depth + 1,
                    state,
                )
        elif key == "$defs" and isinstance(value, dict):
            state.defs_count += len(value)
            for definition_name, definition_schema in value.items():
                _audit_schema_node(
                    definition_schema,
                    f"{path}.$defs.{definition_name}",
                    depth + 1,
                    state,
                )
        elif key == "$ref":
            state.ref_count += 1
        elif key == "enum" and isinstance(value, list):
            state.enum_count += 1
        elif key in {"items", "additionalProperties"}:
            _audit_schema_node(value, f"{path}.{key}", depth + 1, state)
        elif key in {"anyOf", "oneOf", "allOf", "prefixItems"} and isinstance(
            value, list
        ):
            for index, member in enumerate(value):
                _audit_schema_node(member, f"{path}.{key}[{index}]", depth + 1, state)


def _transform_schema(
    node: object,
    excluded_properties: set[str],
    path: str,
    removed: list[str],
) -> object:
    if isinstance(node, list):
        return [
            _transform_schema(item, excluded_properties, f"{path}[{index}]", removed)
            for index, item in enumerate(node)
        ]
    if not isinstance(node, dict):
        return node
    transformed: dict[str, Any] = {}
    for key, value in node.items():
        key_path = f"{path}.{key}"
        if key in _LOCALLY_ENFORCED_KEYWORDS:
            removed.append(key_path)
            continue
        if key == "properties" and isinstance(value, dict):
            transformed[key] = {
                property_name: _transform_schema(
                    property_schema,
                    excluded_properties,
                    f"{key_path}.{property_name}",
                    removed,
                )
                for property_name, property_schema in value.items()
                if property_name not in excluded_properties
            }
            continue
        if key == "required" and isinstance(value, list):
            transformed[key] = [
                item for item in value if item not in excluded_properties
            ]
            continue
        if key == "$defs" and isinstance(value, dict):
            transformed[key] = {
                definition_name: _transform_schema(
                    definition_schema,
                    excluded_properties,
                    f"{key_path}.{definition_name}",
                    removed,
                )
                for definition_name, definition_schema in value.items()
            }
            continue
        transformed[key] = _transform_schema(value, excluded_properties, key_path, removed)
    return transformed


def inline_local_schema_refs(schema: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Inline acyclic local JSON-Schema references without mutating input."""

    root = deepcopy(schema)
    inlined_count = 0

    def resolve(node: object, path: str, stack: tuple[str, ...]) -> object:
        nonlocal inlined_count
        if isinstance(node, list):
            return [
                resolve(item, f"{path}[{index}]", stack)
                for index, item in enumerate(node)
            ]
        if not isinstance(node, dict):
            return node
        reference = node.get("$ref")
        if isinstance(reference, str):
            if not reference.startswith("#/"):
                raise GeminiSchemaCompatibilityError(
                    f"Gemini provider schema contains a non-local reference at {path}."
                )
            non_dollar_siblings = [
                key for key in node if key != "$ref" and not key.startswith("$")
            ]
            if non_dollar_siblings:
                raise GeminiSchemaCompatibilityError(
                    "Gemini provider schema contains non-$ siblings beside $ref at "
                    f"{path}: {', '.join(sorted(non_dollar_siblings))}"
                )
            if reference in stack:
                raise GeminiSchemaCompatibilityError(
                    f"Gemini provider schema contains a cyclic reference at {path}."
                )
            target = _resolve_json_pointer(root, reference, path)
            resolved_target = resolve(
                deepcopy(target),
                path,
                (*stack, reference),
            )
            if not isinstance(resolved_target, dict):
                raise GeminiSchemaCompatibilityError(
                    f"Gemini provider schema reference at {path} is not an object schema."
                )
            dollar_siblings = {
                key: resolve(value, f"{path}.{key}", stack)
                for key, value in node.items()
                if key != "$ref"
            }
            conflicts = set(resolved_target).intersection(dollar_siblings)
            if conflicts:
                raise GeminiSchemaCompatibilityError(
                    "Gemini provider schema cannot safely inline conflicting $ siblings at "
                    f"{path}: {', '.join(sorted(conflicts))}"
                )
            inlined_count += 1
            return {**resolved_target, **dollar_siblings}
        return {
            key: resolve(value, f"{path}.{key}", stack)
            for key, value in node.items()
            if key != "$defs"
        }

    resolved = resolve(root, "$", ())
    if not isinstance(resolved, dict):
        raise GeminiSchemaCompatibilityError("Gemini provider schema root must be an object.")
    return resolved, inlined_count


def _resolve_json_pointer(root: dict[str, Any], reference: str, path: str) -> object:
    current: object = root
    for raw_part in reference.removeprefix("#/").split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or part not in current:
            raise GeminiSchemaCompatibilityError(
                f"Gemini provider schema contains an unresolved reference at {path}."
            )
        current = current[part]
    return current


__all__ = [
    "GeminiSchemaAudit",
    "GeminiSchemaCompatibilityError",
    "GeminiSchemaTransform",
    "audit_gemini_schema",
    "gemini_response_schema",
    "gemini_schema_transform",
    "inline_local_schema_refs",
    "transform_gemini_schema",
]
