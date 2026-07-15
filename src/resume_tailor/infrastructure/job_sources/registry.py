from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pydantic import ValidationError

from resume_tailor.domain.job_discovery.models import (
    ConnectorType,
    SupportedJobSource,
)


class SourceConfigurationError(ValueError):
    """Operator configuration does not describe a supported source."""


class SourceRegistry:
    """Deterministic in-memory view of explicitly approved source configuration."""

    def __init__(self, sources: Iterable[SupportedJobSource] = ()) -> None:
        materialized = list(sources)
        source_ids = [source.source_id for source in materialized]
        if len(source_ids) != len(set(source_ids)):
            raise SourceConfigurationError("duplicate source_id values are not allowed")
        self._sources = tuple(
            sorted(materialized, key=lambda source: (source.source_id, source.connector_type.value))
        )

    @classmethod
    def from_json(cls, payload: str) -> SourceRegistry:
        try:
            decoded = json.loads(payload)
        except (TypeError, json.JSONDecodeError) as exc:
            raise SourceConfigurationError(
                "source registry configuration is not valid JSON"
            ) from exc
        return cls(_parse_sources(decoded))

    @classmethod
    def from_path(cls, path: str | Path) -> SourceRegistry:
        resolved = Path(path)
        try:
            payload = resolved.read_text(encoding="utf-8")
        except OSError as exc:
            raise SourceConfigurationError(f"cannot read source registry: {resolved}") from exc
        return cls.from_json(payload)

    def list_enabled(self) -> list[SupportedJobSource]:
        return [source.model_copy(deep=True) for source in self._sources if source.enabled]


def _parse_sources(decoded: Any) -> list[SupportedJobSource]:
    if isinstance(decoded, dict):
        if set(decoded) != {"sources"} or not isinstance(decoded["sources"], list):
            raise SourceConfigurationError("source registry object must contain a sources list")
        decoded = decoded["sources"]
    if not isinstance(decoded, list):
        raise SourceConfigurationError("source registry must be a list of sources")
    return [_parse_source(item, index) for index, item in enumerate(decoded)]


def _parse_source(value: Any, index: int) -> SupportedJobSource:
    if not isinstance(value, dict):
        raise SourceConfigurationError(f"source entry {index} must be an object")
    if not isinstance(value.get("enabled"), bool):
        raise SourceConfigurationError(f"source entry {index} enabled must be a boolean")

    try:
        source = SupportedJobSource.model_validate(value)
    except ValidationError as exc:
        raise SourceConfigurationError(
            f"invalid source entry {index}: {exc.errors()[0]['msg']}"
        ) from exc

    if not source.source_id.strip():
        raise SourceConfigurationError(f"source entry {index} source_id is required")
    if not source.company_name.strip():
        raise SourceConfigurationError(f"source entry {index} company_name is required")
    if not source.board_token.strip() or any(char.isspace() for char in source.board_token):
        raise SourceConfigurationError(f"source entry {index} board_token/site is invalid")
    if "/" in source.board_token or "\\" in source.board_token:
        raise SourceConfigurationError(f"source entry {index} board_token/site is invalid")

    parsed_url = urlsplit(str(source.official_base_url))
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
        raise SourceConfigurationError(f"source entry {index} official_base_url is invalid")

    if source.connector_type is ConnectorType.LEVER and source.lever_api_region is None:
        raise SourceConfigurationError(f"source entry {index} Lever region is required")
    if source.connector_type is ConnectorType.GREENHOUSE and source.lever_api_region is not None:
        raise SourceConfigurationError(
            f"source entry {index} Greenhouse cannot specify Lever region"
        )
    return source


def load_source_registry(configuration: str | Path | None = None) -> list[SupportedJobSource]:
    """Load only explicit operator configuration; the default registry is empty."""

    if configuration is None:
        return []
    if isinstance(configuration, Path):
        return SourceRegistry.from_path(configuration).list_enabled()
    stripped = configuration.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return SourceRegistry.from_json(configuration).list_enabled()
    return SourceRegistry.from_path(configuration).list_enabled()


__all__ = ["SourceConfigurationError", "SourceRegistry", "load_source_registry"]
