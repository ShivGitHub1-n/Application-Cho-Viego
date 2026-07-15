from __future__ import annotations

from typing import Any

import httpx

from resume_tailor.ports.job_discovery import (
    JobSourceAuthenticationError,
    JobSourceEnvelopeError,
    JobSourceNotFoundError,
    JobSourceRateLimitedError,
    JobSourceTransportError,
)


def request_json(
    client: httpx.Client,
    url: str,
    *,
    timeout: float,
    params: dict[str, Any] | None = None,
) -> Any:
    for attempt in range(3):
        try:
            response = client.get(url, params=params, timeout=timeout)
        except httpx.TimeoutException as exc:
            if attempt == 2:
                raise JobSourceTransportError("job source request timed out") from exc
            continue
        except httpx.RequestError as exc:
            if attempt == 2:
                raise JobSourceTransportError("job source request failed") from exc
            continue

        if response.status_code >= 500 and attempt < 2:
            continue
        break

    if response.status_code in (401, 403):
        raise JobSourceAuthenticationError("job source rejected the request")
    if response.status_code == 404:
        raise JobSourceNotFoundError("job source resource was not found")
    if response.status_code == 429:
        raise JobSourceRateLimitedError("job source rate limit reached")
    if response.is_error:
        raise JobSourceTransportError(f"job source returned HTTP {response.status_code}")
    try:
        return response.json()
    except ValueError as exc:
        raise JobSourceEnvelopeError("job source returned invalid JSON") from exc


__all__ = [
    "JobSourceAuthenticationError",
    "JobSourceEnvelopeError",
    "JobSourceNotFoundError",
    "JobSourceRateLimitedError",
    "JobSourceTransportError",
    "request_json",
]
