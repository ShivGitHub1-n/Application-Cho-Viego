from __future__ import annotations

import asyncio
import gzip
import http.server
import ssl
import threading
import zlib
from collections.abc import AsyncIterator
from datetime import UTC
from pathlib import Path

import httpcore
import httpx
import pytest

from resume_tailor.infrastructure.job_sources.safe_http import (
    BlockedDestinationError,
    PinnedAsyncHTTPTransport,
    SafeHttpClient,
    SafeTransportError,
    UrlAccessPolicy,
    ValidatedDestination,
    ValidatingAsyncNetworkBackend,
)


def test_backend_connects_only_to_validated_address() -> None:
    calls: list[tuple[str, int]] = []

    class FakeBackend:
        async def connect_tcp(self, host: str, port: int, **kwargs: object):
            calls.append((host, port))
            raise RuntimeError("stop after address assertion")

    policy = UrlAccessPolicy(
        allowed_hosts={"careers.example.com"},
        resolver=lambda _: ["93.184.216.34"],
    )
    backend = ValidatingAsyncNetworkBackend(policy, network_backend=FakeBackend())
    with pytest.raises(RuntimeError):
        asyncio.run(backend.connect_tcp("careers.example.com", 443))
    assert calls == [("93.184.216.34", 443)]


def test_backend_uses_authority_validation_without_request_path() -> None:
    calls: list[tuple[str, int]] = []

    class FakeBackend:
        async def connect_tcp(self, host: str, port: int, **kwargs: object):
            calls.append((host, port))
            raise RuntimeError("stop after address assertion")

    policy = UrlAccessPolicy(
        allowed_hosts={"careers.example.com"},
        allowed_path_patterns=(r"^/jobs/[^/]+$",),
        resolver=lambda _: ["93.184.216.34"],
    )
    backend = ValidatingAsyncNetworkBackend(policy, network_backend=FakeBackend())
    with pytest.raises(RuntimeError):
        asyncio.run(backend.connect_tcp("careers.example.com", 443))
    assert calls == [("93.184.216.34", 443)]


def test_transport_requires_https_and_manual_redirects() -> None:
    policy = UrlAccessPolicy(allowed_hosts={"careers.example.com"})
    transport = PinnedAsyncHTTPTransport(policy)
    assert transport.follow_redirects is False


def test_safe_http_revalidates_approved_redirect_host_and_path() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                302,
                headers={"location": "https://redirect.example.com/jobs/2"},
                request=request,
            )

        class FinalBody(httpx.AsyncByteStream):
            async def __aiter__(self) -> AsyncIterator[bytes]:
                yield b"ok"

            async def aclose(self) -> None:
                return None

        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            stream=FinalBody(),
            request=request,
        )

    async def run() -> None:
        client = SafeHttpClient(
            UrlAccessPolicy(
                allowed_hosts={"careers.example.com"},
                redirect_hosts={"redirect.example.com"},
                allowed_path_patterns=(r"^/jobs/1$",),
                redirect_path_patterns=(r"^/jobs/2$",),
                resolver=lambda _: ["93.184.216.34"],
            )
        )
        await client._client.aclose()
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            follow_redirects=False,
            trust_env=False,
        )
        response = await client.get("https://careers.example.com/jobs/1")
        assert response.text == "ok"
        await client.aclose()

    asyncio.run(run())
    assert calls == 2


@pytest.mark.parametrize(
    "location",
    [
        "https://unapproved.example.com/jobs/2",
        "https://redirect.example.com/private/2",
    ],
)
def test_safe_http_rejects_unapproved_redirect_destination(location: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": location}, request=request)

    async def run() -> None:
        client = SafeHttpClient(
            UrlAccessPolicy(
                allowed_hosts={"careers.example.com"},
                redirect_hosts={"redirect.example.com"},
                allowed_path_patterns=(r"^/jobs/1$",),
                redirect_path_patterns=(r"^/jobs/2$",),
                resolver=lambda _: ["93.184.216.34"],
            )
        )
        await client._client.aclose()
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            follow_redirects=False,
            trust_env=False,
        )
        with pytest.raises(BlockedDestinationError):
            await client.get("https://careers.example.com/jobs/1")
        await client.aclose()

    asyncio.run(run())


def test_safe_http_client_redacts_body_and_uses_allowed_content_types() -> None:
    from resume_tailor.infrastructure.job_sources.safe_http import SafeHttpClient

    client = SafeHttpClient(UrlAccessPolicy(allowed_hosts={"careers.example.com"}))
    assert client.max_response_bytes > 0
    client.close()


def test_safe_http_client_enforces_decoded_limit_while_streaming() -> None:
    class Chunks(httpx.AsyncByteStream):
        consumed = 0

        async def __aiter__(self) -> AsyncIterator[bytes]:
            for chunk in (b"1234", b"5678", b"90ab", b"cdef", b"ghij"):
                type(self).consumed += len(chunk)
                yield chunk

        async def aclose(self) -> None:
            return None

    async def run() -> None:
        from resume_tailor.infrastructure.job_sources.safe_http import SafeHttpClient

        client = SafeHttpClient(
            UrlAccessPolicy(
                allowed_hosts={"careers.example.com"},
                resolver=lambda _: ["93.184.216.34"],
            ),
            max_response_bytes=8,
        )
        await client._client.aclose()
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    headers={"content-type": "text/plain"},
                    stream=Chunks(),
                    request=request,
                )
            ),
            follow_redirects=False,
            trust_env=False,
        )
        with pytest.raises(Exception, match="maximum size"):
            await client.get("https://careers.example.com/jobs/1")
        await client.aclose()

    asyncio.run(run())
    assert Chunks.consumed < 20


def test_transport_replaces_caller_host_header_with_request_authority() -> None:
    from resume_tailor.infrastructure.job_sources.safe_http import PinnedAsyncHTTPTransport

    policy = UrlAccessPolicy(
        allowed_hosts={"careers.example.com"},
        resolver=lambda _: ["93.184.216.34"],
    )
    transport = PinnedAsyncHTTPTransport(policy)
    seen: list[object] = []

    async def handle(request: object) -> object:
        seen.append(request)
        return httpcore.Response(200, headers=[], content=b"")

    import httpcore

    transport._pool.handle_async_request = handle  # type: ignore[method-assign]
    response = asyncio.run(
        transport.handle_async_request(
            httpx.Request(
                "GET",
                "https://careers.example.com/jobs/1",
                headers={"Host": "evil.example.com"},
            )
        )
    )
    assert response.status_code == 200
    assert dict(seen[0].headers)[b"host"] == b"careers.example.com"  # type: ignore[attr-defined]
    asyncio.run(transport.aclose())


@pytest.mark.parametrize(
    ("encoding", "body"),
    [
        ("gzip", gzip.compress(b"expanded body" * 20)),
        ("deflate", zlib.compress(b"expanded body" * 20)),
    ],
)
def test_safe_http_bounds_supported_decompression(encoding: str, body: bytes) -> None:
    async def run() -> None:
        from resume_tailor.infrastructure.job_sources.safe_http import (
            SafeHttpClient,
            SafeTransportError,
        )

        class EncodedBody(httpx.AsyncByteStream):
            async def __aiter__(self) -> AsyncIterator[bytes]:
                yield body

            async def aclose(self) -> None:
                return None

        client = SafeHttpClient(
            UrlAccessPolicy(
                allowed_hosts={"careers.example.com"},
                resolver=lambda _: ["93.184.216.34"],
            ),
            max_response_bytes=32,
            max_expansion_ratio=100,
        )
        await client._client.aclose()
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    headers={"content-type": "text/plain", "content-encoding": encoding},
                    stream=EncodedBody(),
                    request=request,
                )
            ),
            follow_redirects=False,
            trust_env=False,
        )
        with pytest.raises(SafeTransportError, match="maximum size"):
            await client.get("https://careers.example.com/jobs/1")
        await client.aclose()

    asyncio.run(run())


def test_safe_http_rejects_unsupported_encoding_without_buffering() -> None:
    async def run() -> None:
        from resume_tailor.infrastructure.job_sources.safe_http import (
            SafeHttpClient,
            SafeTransportError,
        )

        client = SafeHttpClient(
            UrlAccessPolicy(
                allowed_hosts={"careers.example.com"},
                resolver=lambda _: ["93.184.216.34"],
            )
        )
        await client._client.aclose()
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    headers={"content-type": "text/plain", "content-encoding": "br"},
                    content=b"not decoded",
                    request=request,
                )
            ),
            follow_redirects=False,
            trust_env=False,
        )
        with pytest.raises(SafeTransportError, match="not supported"):
            await client.get("https://careers.example.com/jobs/1")
        await client.aclose()

    asyncio.run(run())


def test_safe_http_rejects_oversized_content_length_before_iteration() -> None:
    class Body(httpx.AsyncByteStream):
        consumed = 0
        closed = False

        async def __aiter__(self) -> AsyncIterator[bytes]:
            type(self).consumed += 1
            yield b"never-read"

        async def aclose(self) -> None:
            type(self).closed = True

    async def run() -> None:
        client = SafeHttpClient(
            UrlAccessPolicy(
                allowed_hosts={"careers.example.com"},
                resolver=lambda _: ["93.184.216.34"],
            ),
            max_response_bytes=8,
        )
        await client._client.aclose()
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    headers={"content-type": "text/plain", "content-length": "100"},
                    stream=Body(),
                    request=request,
                )
            ),
            trust_env=False,
        )
        with pytest.raises(SafeTransportError, match="encoded size"):
            await client.get("https://careers.example.com/jobs/1")
        await client.aclose()

    asyncio.run(run())
    assert Body.consumed == 0
    assert Body.closed


def test_safe_http_closes_stream_after_chunked_encoded_overflow() -> None:
    class Body(httpx.AsyncByteStream):
        consumed = 0
        closed = False

        async def __aiter__(self) -> AsyncIterator[bytes]:
            for chunk in (b"1234", b"5678", b"90ab"):
                type(self).consumed += 1
                yield chunk

        async def aclose(self) -> None:
            type(self).closed = True

    async def run() -> None:
        client = SafeHttpClient(
            UrlAccessPolicy(
                allowed_hosts={"careers.example.com"},
                resolver=lambda _: ["93.184.216.34"],
            ),
            max_response_bytes=32,
            max_encoded_response_bytes=8,
        )
        await client._client.aclose()
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    headers={"content-type": "text/plain"},
                    stream=Body(),
                    request=request,
                )
            ),
            trust_env=False,
        )
        with pytest.raises(SafeTransportError, match="encoded size"):
            await client.get("https://careers.example.com/jobs/1")
        await client.aclose()

    asyncio.run(run())
    assert Body.consumed == 3
    assert Body.closed


@pytest.mark.parametrize("encoding", ["gzip", "deflate"])
def test_safe_http_closes_stream_after_malformed_compression(encoding: str) -> None:
    class Body(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b"malformed-compressed-body"

        async def aclose(self) -> None:
            type(self).closed = True

    async def run() -> None:
        client = SafeHttpClient(
            UrlAccessPolicy(
                allowed_hosts={"careers.example.com"},
                resolver=lambda _: ["93.184.216.34"],
            )
        )
        await client._client.aclose()
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    headers={
                        "content-type": "text/plain",
                        "content-encoding": encoding,
                    },
                    stream=Body(),
                    request=request,
                )
            ),
            trust_env=False,
        )
        with pytest.raises(SafeTransportError, match="compressed response"):
            await client.get("https://careers.example.com/jobs/1")
        await client.aclose()

    asyncio.run(run())
    assert Body.closed


def test_safe_http_does_not_retry_cancellation() -> None:
    class Body(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b"first"
            await asyncio.Event().wait()

        async def aclose(self) -> None:
            type(self).closed = True

    async def run() -> None:
        client = SafeHttpClient(
            UrlAccessPolicy(
                allowed_hosts={"careers.example.com"},
                resolver=lambda _: ["93.184.216.34"],
            ),
            max_retries=3,
        )
        await client._client.aclose()
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    headers={"content-type": "text/plain"},
                    stream=Body(),
                    request=request,
                )
            ),
            trust_env=False,
        )
        task = asyncio.create_task(client.get("https://careers.example.com/jobs/1"))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await client.aclose()

    asyncio.run(run())
    assert Body.closed


def test_safe_http_closes_retry_response_before_next_attempt() -> None:
    closed: list[bool] = []
    calls = 0

    class RetryBody(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b"retry body"

        async def aclose(self) -> None:
            closed.append(True)

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                503,
                headers={"content-type": "text/plain"},
                stream=RetryBody(),
                request=request,
            )
        class SuccessBody(httpx.AsyncByteStream):
            async def __aiter__(self) -> AsyncIterator[bytes]:
                yield b"ok"

            async def aclose(self) -> None:
                return None

        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            stream=SuccessBody(),
            request=request,
        )

    async def run() -> None:
        client = SafeHttpClient(
            UrlAccessPolicy(
                allowed_hosts={"careers.example.com"},
                resolver=lambda _: ["93.184.216.34"],
            ),
            max_retries=1,
        )
        await client._client.aclose()
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            trust_env=False,
        )
        response = await client.get("https://careers.example.com/jobs/1")
        assert response.text == "ok"
        await client.aclose()

    asyncio.run(run())
    assert calls == 2
    assert closed == [True]


@pytest.mark.parametrize(
    ("content_type", "body"),
    [("text/html", b"<html></html>"), ("application/json", b"{}"), ("application/xml", b"<root/>")],
)
def test_safe_http_returns_bounded_supported_documents(content_type: str, body: bytes) -> None:
    async def run() -> None:
        client = SafeHttpClient(
            UrlAccessPolicy(
                allowed_hosts={"careers.example.com"},
                resolver=lambda _: ["93.184.216.34"],
            ),
            max_response_bytes=128,
        )
        await client._client.aclose()

        class SuccessBody(httpx.AsyncByteStream):
            async def __aiter__(self) -> AsyncIterator[bytes]:
                yield body

            async def aclose(self) -> None:
                return None

        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    headers={"content-type": content_type},
                    stream=SuccessBody(),
                    request=request,
                )
            ),
            trust_env=False,
        )
        response = await client.get("https://careers.example.com/jobs/1")
        assert response.content == body
        await client.aclose()

    asyncio.run(run())


class _LocalHttpsPolicy(UrlAccessPolicy):
    def __init__(self, host: str, port: int, allowed_paths: tuple[str, ...]) -> None:
        super().__init__(
            allowed_hosts={host},
            allowed_path_patterns=allowed_paths,
            resolver=lambda _: ["127.0.0.1"],
        )
        self._test_host = host
        self._test_port = port

    def validate_authority(
        self, host: str, port: int, *, redirect: bool = False
    ) -> ValidatedDestination:
        if host.lower().rstrip(".") != self._test_host or port != self._test_port:
            raise BlockedDestinationError("local test authority is not approved")
        return ValidatedDestination(self._test_host, "127.0.0.1", port, "https")


def _certificate(tmp_path: Path, hostname: str) -> tuple[str, str]:
    from datetime import datetime, timedelta

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    path = tmp_path
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(minutes=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(hostname)]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_path = path / f"{hostname}.crt"
    key_path = path / f"{hostname}.key"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    return str(cert_path), str(key_path)


def test_real_pinned_transport_proves_path_host_sni_and_ip_destination(tmp_path: Path) -> None:
    pytest.importorskip("cryptography")
    host = "careers.example.com"
    requests: list[tuple[str, str | None]] = []
    sni_names: list[str | None] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            requests.append((self.path, self.headers.get("host")))
            payload = b"bounded"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            return None

    cert_path, key_path = _certificate(tmp_path, host)
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(cert_path, key_path)
    server_context.set_servername_callback(lambda sock, name, context: sni_names.append(name))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.socket = server_context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client_context = ssl.create_default_context(cafile=cert_path)
    policy = _LocalHttpsPolicy(host, server.server_port, (r"^/jobs/123$",))
    transport = PinnedAsyncHTTPTransport(policy)

    async def run() -> None:
        await transport._pool.aclose()
        transport._pool = httpcore.AsyncConnectionPool(
            ssl_context=client_context,
            max_connections=2,
            max_keepalive_connections=2,
            network_backend=ValidatingAsyncNetworkBackend(policy),
            retries=0,
        )
        async with httpx.AsyncClient(transport=transport, trust_env=False) as client:
            response = await client.get(
                f"https://{host}:{server.server_port}/jobs/123",
                headers={"Host": "attacker.example"},
            )
            assert response.status_code == 200
            assert response.text == "bounded"

    try:
        asyncio.run(run())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert requests == [("/jobs/123", host)]
    assert sni_names == [host]


def test_real_pinned_transport_rejects_wrong_hostname_certificate(tmp_path: Path) -> None:
    pytest.importorskip("cryptography")
    host = "careers.example.com"
    cert_path, key_path = _certificate(tmp_path, "wrong.example.com")

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return None

    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(cert_path, key_path)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.socket = server_context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client_context = ssl.create_default_context(cafile=cert_path)
    policy = _LocalHttpsPolicy(host, server.server_port, (r"^/jobs/123$",))
    transport = PinnedAsyncHTTPTransport(policy)

    async def run() -> None:
        await transport._pool.aclose()
        transport._pool = httpcore.AsyncConnectionPool(
            ssl_context=client_context,
            max_connections=1,
            max_keepalive_connections=1,
            network_backend=ValidatingAsyncNetworkBackend(policy),
            retries=0,
        )
        async with httpx.AsyncClient(transport=transport, trust_env=False) as client:
            with pytest.raises(httpx.TransportError):
                await client.get(f"https://{host}:{server.server_port}/jobs/123")

    try:
        asyncio.run(run())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
