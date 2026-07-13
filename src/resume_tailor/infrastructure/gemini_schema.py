from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import BaseModel


def gemini_response_schema(
    model_type: type[BaseModel],
    *,
    excluded_properties: set[str] | None = None,
) -> dict[str, Any]:
    raw_schema = model_type.model_json_schema()
    definitions = raw_schema.pop("$defs", {})
    return _sanitize(raw_schema, definitions, excluded_properties or set())


def _sanitize(node: Any, definitions: dict[str, Any], excluded_properties: set[str]) -> Any:
    if isinstance(node, list):
        return [_sanitize(item, definitions, excluded_properties) for item in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        reference = node["$ref"].removeprefix("#/$defs/")
        resolved = deepcopy(definitions[reference])
        resolved.update({key: value for key, value in node.items() if key != "$ref"})
        return _sanitize(resolved, definitions, excluded_properties)
    unsupported = {"$defs", "$schema", "additionalProperties", "default", "examples"}
    properties = node.get("properties")
    if isinstance(properties, dict) and excluded_properties:
        properties = {
            key: value for key, value in properties.items() if key not in excluded_properties
        }
    required = node.get("required")
    if isinstance(required, list) and excluded_properties:
        required = [key for key in required if key not in excluded_properties]
    return {
        key: _sanitize(
            properties if key == "properties" else required if key == "required" else value,
            definitions,
            excluded_properties,
        )
        for key, value in node.items()
        if key not in unsupported
    }
