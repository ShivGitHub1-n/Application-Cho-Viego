from __future__ import annotations

import hashlib
import json
import time
from typing import TypeVar

from pydantic import BaseModel

ModelType = TypeVar("ModelType", bound=BaseModel)


class InMemoryLlmCache:
    def __init__(self, ttl_seconds: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._values: dict[str, tuple[float, BaseModel]] = {}

    def key_for(self, operation: str, model: str, payload: BaseModel) -> str:
        serialized = json.dumps(
            {"operation": operation, "model": model, "payload": payload.model_dump(mode="json")},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def get(self, key: str, result_type: type[ModelType]) -> ModelType | None:
        value = self._values.get(key)
        if value is None or value[0] <= time.monotonic():
            self._values.pop(key, None)
            return None
        return result_type.model_validate(value[1].model_dump(mode="json"))

    def set(self, key: str, value: BaseModel) -> None:
        self._values[key] = (time.monotonic() + self._ttl_seconds, value)
