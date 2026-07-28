from __future__ import annotations

import asyncio
import ipaddress
import posixpath
import re
import socket
import zlib
from collections.abc import AsyncIterator, Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from re import Pattern
from typing import Any, cast
from urllib.parse import unquote, urlsplit

import httpcore
import httpx

# HTTPX 0.28.1 and httpcore 1.0.9 expose the only supported backend seam for
# connecting to a validated IP while retaining the original HTTP origin. These
# private imports are intentionally isolated here; changing the dependency
# ranges requires rerunning the local HTTP/TLS transport tests.
from httpcore._backends.anyio import AnyIOBackend
from httpcore._backends.base import SOCKET_OPTION, AsyncNetworkBackend, AsyncNetworkStream
from httpx._transports.default import map_httpcore_exceptions

from resume_tailor.domain.job_discovery.hostnames import (
    HostnameValidationError,
    normalize_hostname,
)


class SafeTransportError(RuntimeError):
    """A request was rejected or failed inside the bounded safe transport."""


class BlockedDestinationError(SafeTransportError):
    """A URL or resolved destination is outside the approved network boundary."""


@dataclass(frozen=True)
class ValidatedDestination:
    host: str
    ip: str
    port: int
    scheme: str


def _normalized_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise BlockedDestinationError("DNS returned an invalid IP address") from exc
    mapped = getattr(address, "ipv4_mapped", None)
    return mapped or address


def _is_blocked_ip(value: str) -> bool:
    address = _normalized_ip(value)
    return not address.is_global or address.is_multicast or address.is_unspecified


def _compile_path_patterns(patterns: Iterable[str]) -> tuple[Pattern[str], ...]:
    compiled: list[Pattern[str]] = []
    for pattern in patterns:
        if not pattern or len(pattern) > 256 or any(ord(char) < 32 for char in pattern):
            raise BlockedDestinationError("path patterns are invalid or unbounded")
        if any(token in pattern for token in ("(?=", "(?<=", "(?!", "(?<!")):
            raise BlockedDestinationError("path patterns cannot use lookarounds")
        try:
            compiled.append(re.compile(pattern))
        except re.error as exc:
            raise BlockedDestinationError("path pattern is malformed") from exc
    return tuple(compiled)


class UrlAccessPolicy:
    def __init__(
        self,
        *,
        allowed_hosts: set[str],
        redirect_hosts: set[str] | None = None,
        allowed_path_patterns: Iterable[str] = (),
        redirect_path_patterns: Iterable[str] | None = None,
        resolver: Callable[[str], list[str]] | None = None,
    ) -> None:
        try:
            self.allowed_hosts = frozenset(normalize_hostname(host) for host in allowed_hosts)
            self.redirect_hosts = frozenset(
                normalize_hostname(host) for host in (redirect_hosts or set())
            )
        except HostnameValidationError as exc:
            raise BlockedDestinationError(str(exc)) from exc
        self.allowed_path_patterns = _compile_path_patterns(allowed_path_patterns)
        self.redirect_path_patterns = (
            _compile_path_patterns(redirect_path_patterns)
            if redirect_path_patterns is not None
            else self.allowed_path_patterns
        )
        self._resolver = resolver or self._resolve

    @staticmethod
    def _resolve(host: str) -> list[str]:
        return sorted(
            {
                cast(str, result[4][0])
                for result in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
            }
        )

    @staticmethod
    def _normalized_path(path: str) -> str:
        if not path or any(ord(char) < 32 for char in path) or "\\" in path:
            raise BlockedDestinationError("path contains controls or backslashes")
        if re.search(r"%(?:2f|2F|5c|5C|2e|2E)", path):
            raise BlockedDestinationError("encoded path separators are not permitted")
        try:
            decoded = unquote(path, errors="strict")
        except UnicodeDecodeError as exc:
            raise BlockedDestinationError("path encoding is invalid") from exc
        if any(part in {".", ".."} for part in decoded.split("/")):
            raise BlockedDestinationError("path traversal is not permitted")
        normalized = posixpath.normpath(decoded)
        if normalized != decoded or not normalized.startswith("/"):
            raise BlockedDestinationError("path normalization would change the request")
        return normalized

    def validate_authority(
        self, host: str, port: int, *, redirect: bool = False
    ) -> ValidatedDestination:
        try:
            normalized_host = normalize_hostname(host)
        except HostnameValidationError as exc:
            raise BlockedDestinationError(str(exc)) from exc
        hosts = self.allowed_hosts | self.redirect_hosts if redirect else self.allowed_hosts
        if normalized_host not in hosts:
            raise BlockedDestinationError("host is not approved")
        if port != 443:
            raise BlockedDestinationError("only HTTPS port 443 is permitted")
        try:
            addresses = self._resolver(normalized_host)
        except OSError as exc:
            raise BlockedDestinationError("DNS resolution failed") from exc
        normalized_addresses = [_normalized_ip(address) for address in addresses]
        if not normalized_addresses or any(
            not address.is_global for address in normalized_addresses
        ):
            raise BlockedDestinationError("DNS result contains a blocked or mixed destination")
        selected = normalized_addresses[0]
        return ValidatedDestination(normalized_host, selected.compressed, 443, "https")

    def validate(self, url: str, *, redirect: bool = False) -> ValidatedDestination:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.fragment:
            raise BlockedDestinationError(
                "only credential-free HTTPS URLs without fragments are permitted"
            )
        try:
            port = parsed.port or 443
        except ValueError as exc:
            raise BlockedDestinationError("URL port is invalid") from exc
        destination = self.validate_authority(parsed.hostname or "", port, redirect=redirect)
        patterns = self.redirect_path_patterns if redirect else self.allowed_path_patterns
        path = self._normalized_path(parsed.path or "/")
        if patterns and not any(pattern.search(path) for pattern in patterns):
            raise BlockedDestinationError("path is not approved")
        return destination


class ValidatingAsyncNetworkBackend(AsyncNetworkBackend):
    def __init__(self, policy: UrlAccessPolicy, *, network_backend: Any | None = None) -> None:
        self.policy = policy
        self.network_backend = network_backend or AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[SOCKET_OPTION] | None = None,
    ) -> AsyncNetworkStream:
        if local_address is not None or socket_options:
            raise BlockedDestinationError("custom local socket configuration is not permitted")
        destination = self.policy.validate_authority(host, port)
        return await self.network_backend.connect_tcp(
            destination.ip,
            destination.port,
            timeout=timeout,
            local_address=None,
            socket_options=None,
        )


class _AsyncResponseStream(httpx.AsyncByteStream):
    def __init__(self, stream: Any) -> None:
        self.stream = stream

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self.stream:
            yield chunk

    async def aclose(self) -> None:
        await self.stream.aclose()


class PinnedAsyncHTTPTransport(httpx.AsyncBaseTransport):
    def __init__(self, policy: UrlAccessPolicy, *, max_connections: int = 4) -> None:
        self.policy = policy
        self.follow_redirects = False
        backend = ValidatingAsyncNetworkBackend(policy)
        self._pool = httpcore.AsyncConnectionPool(
            max_connections=max_connections,
            max_keepalive_connections=max_connections,
            network_backend=backend,
            retries=0,
        )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.policy.validate(str(request.url))
        headers = [
            (name, value)
            for name, value in request.headers.raw
            if name.lower() not in {b"host", b":authority"}
        ]
        headers.append((b"host", request.url.raw_host))
        core_request = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=headers,
            content=request.stream,
            extensions=request.extensions,
        )
        with map_httpcore_exceptions():
            response = await self._pool.handle_async_request(core_request)
        return httpx.Response(
            response.status,
            headers=response.headers,
            stream=_AsyncResponseStream(response.stream),
            extensions=response.extensions,
            request=request,
        )

    async def aclose(self) -> None:
        await self._pool.aclose()


class SafeHttpClient:
    def __init__(
        self,
        policy: UrlAccessPolicy,
        *,
        timeout: httpx.Timeout | None = None,
        max_response_bytes: int = 2 * 1024 * 1024,
        max_encoded_response_bytes: int | None = None,
        max_expansion_ratio: float = 20.0,
        allowed_content_types: set[str] | None = None,
        max_concurrent_requests: int = 4,
        min_request_interval_seconds: float = 0.0,
        max_retries: int = 0,
        max_retry_after_seconds: float = 30.0,
        total_deadline_seconds: float | None = None,
    ) -> None:
        if max_response_bytes < 1 or max_expansion_ratio < 1:
            raise ValueError("response limits must be positive")
        if (
            max_concurrent_requests < 1
            or min_request_interval_seconds < 0
            or max_retries < 0
            or max_retry_after_seconds < 0
            or total_deadline_seconds is not None
            and total_deadline_seconds <= 0
        ):
            raise ValueError("HTTP limits are invalid")
        self.policy = policy
        self.max_response_bytes = max_response_bytes
        self.max_encoded_response_bytes = max_encoded_response_bytes or max_response_bytes * 4
        self.max_expansion_ratio = max_expansion_ratio
        self.allowed_content_types = allowed_content_types or {
            "application/json",
            "application/ld+json",
            "application/xml",
            "application/xhtml+xml",
            "text/html",
            "text/plain",
            "text/xml",
        }
        self._max_concurrent_requests = max_concurrent_requests
        self._host_semaphores: dict[str, asyncio.Semaphore] = {}
        self._host_last_request_at: dict[str, float] = {}
        self._min_request_interval_seconds = min_request_interval_seconds
        self._max_retries = max_retries
        self._max_retry_after_seconds = max_retry_after_seconds
        self._total_deadline_seconds = total_deadline_seconds
        self._client = httpx.AsyncClient(
            transport=PinnedAsyncHTTPTransport(policy),
            follow_redirects=False,
            trust_env=False,
            timeout=timeout or httpx.Timeout(15.0, connect=5.0, read=10.0),
        )

    def _host_semaphore(self, host: str) -> asyncio.Semaphore:
        if host not in self._host_semaphores:
            self._host_semaphores[host] = asyncio.Semaphore(self._max_concurrent_requests)
        return self._host_semaphores[host]

    async def _read_bounded(self, response: httpx.Response) -> bytes:
        content_length = response.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.max_encoded_response_bytes:
                    raise SafeTransportError("response exceeds maximum encoded size")
            except ValueError:
                raise SafeTransportError("response Content-Length is invalid") from None
        encoding = response.headers.get("content-encoding", "identity").strip().lower()
        if encoding in {"", "identity"}:
            decompressor: Any | None = None
        elif encoding == "gzip":
            decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
        elif encoding == "deflate":
            decompressor = zlib.decompressobj()
        else:
            raise SafeTransportError("response encoding is not supported")
        encoded_size = 0
        decoded_size = 0
        output = bytearray()

        async for chunk in response.aiter_raw():
            encoded_size += len(chunk)
            if encoded_size > self.max_encoded_response_bytes:
                raise SafeTransportError("response exceeds maximum encoded size")
            if decompressor is None:
                decoded = chunk
            else:
                try:
                    decoded = decompressor.decompress(
                        chunk, self.max_response_bytes - decoded_size + 1
                    )
                except zlib.error as exc:
                    raise SafeTransportError("compressed response is malformed") from exc
            decoded_size += len(decoded)
            if decoded_size > self.max_response_bytes:
                raise SafeTransportError("response exceeds maximum size")
            if (
                decompressor is not None
                and decoded_size > max(encoded_size, 1) * self.max_expansion_ratio
            ):
                raise SafeTransportError("response expansion ratio exceeds maximum")
            output.extend(decoded)
        if decompressor is not None:
            try:
                tail = decompressor.flush(self.max_response_bytes - decoded_size + 1)
            except zlib.error as exc:
                raise SafeTransportError("compressed response is malformed") from exc
            decoded_size += len(tail)
            if decoded_size > self.max_response_bytes or not decompressor.eof:
                raise SafeTransportError("compressed response is invalid or oversized")
            output.extend(tail)
        return bytes(output)

    @staticmethod
    def _retry_delay(response: httpx.Response, cap: float) -> float:
        value = response.headers.get("retry-after")
        if value is None:
            return 0.0
        try:
            return min(max(float(value), 0.0), cap)
        except ValueError:
            try:
                target = parsedate_to_datetime(value)
                if target.tzinfo is None:
                    target = target.replace(tzinfo=UTC)
                seconds = (target - datetime.now(UTC)).total_seconds()
                return min(max(seconds, 0.0), cap)
            except (TypeError, ValueError, OverflowError):
                return cap

    async def get(self, url: str, *, headers: dict[str, str] | None = None) -> httpx.Response:
        current = url
        redirect_count = 0
        retries = 0
        started = asyncio.get_running_loop().time()
        request_headers = dict(headers or {})
        request_headers["Accept-Encoding"] = "identity"
        while True:
            if (
                self._total_deadline_seconds is not None
                and asyncio.get_running_loop().time() - started >= self._total_deadline_seconds
            ):
                raise SafeTransportError("source total deadline exceeded")
            destination = self.policy.validate(current, redirect=redirect_count > 0)
            host = destination.host
            async with self._host_semaphore(host):
                now = asyncio.get_running_loop().time()
                delay = self._min_request_interval_seconds - (
                    now - self._host_last_request_at.get(host, 0.0)
                )
                if delay > 0:
                    await asyncio.sleep(delay)
                self._host_last_request_at[host] = asyncio.get_running_loop().time()
                try:
                    remaining = (
                        None
                        if self._total_deadline_seconds is None
                        else max(
                            self._total_deadline_seconds
                            - (asyncio.get_running_loop().time() - started),
                            0.0,
                        )
                    )
                    async with asyncio.timeout(remaining):
                        async with self._client.stream(
                            "GET", current, headers=request_headers
                        ) as response:
                            if response.status_code in {301, 302, 303, 307, 308}:
                                location = response.headers.get("location")
                                if not location:
                                    raise SafeTransportError("redirect did not include a location")
                                redirect_count += 1
                                if redirect_count > 3:
                                    raise SafeTransportError("redirect limit exceeded")
                                current = str(httpx.URL(current).join(location))
                                continue
                            if (
                                response.status_code in {429, 502, 503, 504}
                                and retries < self._max_retries
                            ):
                                retries += 1
                                retry_delay = self._retry_delay(
                                    response, self._max_retry_after_seconds
                                )
                                if retry_delay:
                                    await asyncio.sleep(retry_delay)
                                continue
                            content_type = (
                                response.headers.get("content-type", "").split(";", 1)[0].strip()
                            )
                            if content_type not in self.allowed_content_types:
                                raise SafeTransportError("content type is not allowed")
                            body = await self._read_bounded(response)
                            response_headers = response.headers.copy()
                            response_headers.pop("content-encoding", None)
                            response_headers["content-length"] = str(len(body))
                            return httpx.Response(
                                response.status_code,
                                headers=response_headers,
                                content=body,
                                request=response.request,
                                extensions=response.extensions,
                            )
                except TimeoutError as exc:
                    raise SafeTransportError("source total deadline exceeded") from exc
                except httpx.TransportError:
                    if retries >= self._max_retries:
                        raise
                    retries += 1

    async def aclose(self) -> None:
        await self._client.aclose()

    def get_sync(self, url: str, *, headers: dict[str, str] | None = None) -> httpx.Response:
        """Synchronous bridge for the existing synchronous connector port."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.get(url, headers=headers))
        raise RuntimeError("SafeHttpClient.get_sync cannot run inside an event loop")

    def close(self) -> None:
        """Synchronous cleanup hook; async callers must use ``aclose``."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            if not self._client.is_closed:
                asyncio.run(self.aclose())
        else:
            raise RuntimeError("use aclose() while an event loop is running")


__all__ = [
    "BlockedDestinationError",
    "PinnedAsyncHTTPTransport",
    "SafeHttpClient",
    "SafeTransportError",
    "UrlAccessPolicy",
    "ValidatedDestination",
    "ValidatingAsyncNetworkBackend",
]
