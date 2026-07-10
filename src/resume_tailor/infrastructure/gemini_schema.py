from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import BaseModel


def gemini_response_schema(model_type: type[BaseModel]) -> dict[str, Any]:
    raw_schema = model_type.model_json_schema()
    definitions = raw_schema.pop("$defs", {})
    return _sanitize(raw_schema, definitions)


def _sanitize(node: Any, definitions: dict[str, Any]) -> Any:
    if isinstance(node, list):
        return [_sanitize(item, definitions) for item in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        reference = node["$ref"].removeprefix("#/$defs/")
        resolved = deepcopy(definitions[reference])
        resolved.update({key: value for key, value in node.items() if key != "$ref"})
        return _sanitize(resolved, definitions)
    unsupported = {"$defs", "$schema", "additionalProperties", "default", "examples"}
    return {
        key: _sanitize(value, definitions)
        for key, value in node.items()
        if key not in unsupported
    }
