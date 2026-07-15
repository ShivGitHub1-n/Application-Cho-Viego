from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from resume_tailor.domain.job_discovery.models import (
    ConnectorType,
    LeverApiRegion,
    SourceRecordWarningCode,
    SupportedJobSource,
    VerificationConfidence,
    VerificationStatus,
    WorkArrangement,
)
from resume_tailor.infrastructure.job_sources.errors import (
    JobSourceAuthenticationError,
    JobSourceEnvelopeError,
    JobSourceNotFoundError,
    JobSourceRateLimitedError,
    JobSourceTransportError,
)
from resume_tailor.infrastructure.job_sources.lever import LeverConnector

FIXTURES = Path(__file__).parents[2] / "fixtures" / "job_sources"
WHEN = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)


def _source(
    region: LeverApiRegion = LeverApiRegion.GLOBAL, **overrides: object
) -> SupportedJobSource:
    values: dict[str, object] = {
        "source_id": "acme-lever",
        "connector_type": ConnectorType.LEVER,
        "company_name": "Acme Robotics",
        "board_token": "acme",
        "enabled": True,
        "official_base_url": "https://jobs.lever.co"
        if region is LeverApiRegion.GLOBAL
        else "https://jobs.eu.lever.co",
        "lever_api_region": region,
    }
    values.update(overrides)
    return SupportedJobSource(**values)


def _fixture(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _client(handler: object) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_global_fixture_normalizes_and_does_not_use_created_at() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_fixture("lever_global_page.json"), request=request)

    result = LeverConnector(_client(handler), page_size=100).fetch(_source(), fetched_at=WHEN)
    record = result.records[0]
    assert record.external_job_id == "lever-100"
    assert record.title == "Robotics Software Engineer"
    assert record.company_name == "Acme Robotics"
    assert record.description == "Build autonomy services with Python."
    assert record.location_raw == "Toronto, ON, Canada"
    assert record.work_arrangement is WorkArrangement.REMOTE
    assert str(record.official_url) == "https://jobs.lever.co/acme/lever-100"
    assert record.posted_at is None
    assert requests[0].url.host == "api.lever.co"
    assert dict(requests[0].url.params) == {"mode": "json", "skip": "0", "limit": "100"}


def test_eu_fixture_uses_explicit_eu_api_region() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_fixture("lever_eu_page.json"), request=request)

    result = LeverConnector(_client(handler), page_size=50).fetch(
        _source(LeverApiRegion.EU), fetched_at=WHEN
    )
    assert result.records[0].external_job_id == "lever-eu-100"
    assert requests[0].url.host == "api.eu.lever.co"


def test_safe_http_upgrade_and_invalid_url_warning() -> None:
    payload = [
        {
            "id": "lever-http",
            "text": "Role",
            "hostedUrl": "http://jobs.lever.co/acme/lever-http",
        }
    ]
    result = LeverConnector(
        _client(lambda request: httpx.Response(200, json=payload, request=request))
    ).fetch(
        _source(),
        fetched_at=WHEN,
    )
    assert str(result.records[0].official_url) == "https://jobs.lever.co/acme/lever-http"

    invalid = [{"id": "lever-invalid", "text": "Role", "hostedUrl": "not-a-url"}]
    result = LeverConnector(
        _client(lambda request: httpx.Response(200, json=invalid, request=request))
    ).fetch(
        _source(),
        fetched_at=WHEN,
    )
    assert result.records == []
    assert result.warnings[0].code is SourceRecordWarningCode.INVALID_OFFICIAL_URL


def test_missing_location_warning_is_deterministic() -> None:
    payload = [
        {"id": "z", "text": "Role", "hostedUrl": "https://jobs.lever.co/acme/z"},
        {"id": "a", "text": "Role", "hostedUrl": "https://jobs.lever.co/acme/a"},
    ]
    result = LeverConnector(
        _client(lambda request: httpx.Response(200, json=payload, request=request))
    ).fetch(
        _source(),
        fetched_at=WHEN,
    )
    assert [record.external_job_id for record in result.records] == ["a", "z"]
    assert [item.external_job_id for item in result.warnings] == ["a", "z"]


def test_skip_limit_pagination_is_bounded_and_stops_deterministically() -> None:
    requests: list[httpx.Request] = []
    pages = {
        0: [_fixture("lever_global_page.json")[0]],
        1: [_fixture("lever_global_page_2.json")[0]],
        2: [],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        skip = int(request.url.params["skip"])
        return httpx.Response(200, json=pages[skip], request=request)

    result = LeverConnector(_client(handler), page_size=1, max_pages=5).fetch(
        _source(), fetched_at=WHEN
    )
    assert [record.external_job_id for record in result.records] == ["lever-100", "lever-200"]
    assert [request.url.params["skip"] for request in requests] == ["0", "1", "2"]


def test_max_pages_bounds_pagination() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_fixture("lever_global_page.json"), request=request)

    LeverConnector(_client(handler), page_size=1, max_pages=2).fetch(_source(), fetched_at=WHEN)
    assert len(requests) == 2


def test_bad_posting_is_skipped_with_exact_warning() -> None:
    result = LeverConnector(
        _client(
            lambda request: httpx.Response(
                200,
                json=_fixture("lever_malformed_record.json"),
                request=request,
            )
        )
    ).fetch(_source(), fetched_at=WHEN)
    assert result.records[0].external_job_id == "lever-ok"
    assert result.warnings[0].code is SourceRecordWarningCode.MISSING_TITLE


def test_malformed_top_level_envelope_raises() -> None:
    with pytest.raises(JobSourceEnvelopeError):
        LeverConnector(
            _client(lambda request: httpx.Response(200, json={}, request=request))
        ).fetch(_source(), fetched_at=WHEN)


@pytest.mark.parametrize(
    ("status", "exception"),
    [
        (401, JobSourceAuthenticationError),
        (403, JobSourceAuthenticationError),
        (404, JobSourceNotFoundError),
        (429, JobSourceRateLimitedError),
        (500, JobSourceTransportError),
    ],
)
def test_http_statuses_map_to_exact_exceptions(status: int, exception: type[Exception]) -> None:
    with pytest.raises(exception):
        LeverConnector(
            _client(lambda request: httpx.Response(status, json={}, request=request))
        ).fetch(_source(), fetched_at=WHEN)


def test_availability_uses_one_direct_region_specific_posting_get() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "lever-eu-100",
                "text": "Robotics Software Engineer",
                "hostedUrl": "https://jobs.eu.lever.co/acme-eu/lever-eu-100",
            },
            request=request,
        )

    result = LeverConnector(_client(handler), clock=lambda: WHEN).check(
        _source(
            LeverApiRegion.EU, board_token="acme-eu", official_base_url="https://jobs.eu.lever.co"
        ),
        "lever-eu-100",
    )
    assert result.status is VerificationStatus.VERIFIED_ACTIVE
    assert result.confidence is VerificationConfidence.HIGH
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url.host == "api.eu.lever.co"
    assert requests[0].url.path == "/v0/postings/acme-eu/lever-eu-100"
    assert str(requests[0].url.params) == ""


def test_availability_not_found_is_unavailable() -> None:
    result = LeverConnector(
        _client(lambda request: httpx.Response(404, json={}, request=request)), clock=lambda: WHEN
    ).check(_source(), "missing")
    assert result.status is VerificationStatus.UNAVAILABLE
    assert result.confidence is VerificationConfidence.LOW


def test_unknown_status_is_medium_confidence() -> None:
    result = LeverConnector(
        _client(
            lambda request: httpx.Response(
                200,
                json={
                    "id": "lever-100",
                    "text": "Role",
                    "hostedUrl": "https://jobs.lever.co/acme/lever-100",
                    "state": "pending",
                },
                request=request,
            )
        ),
        clock=lambda: WHEN,
    ).check(_source(), "lever-100")
    assert result.status is VerificationStatus.VERIFIED_STATUS_UNKNOWN
    assert result.confidence is VerificationConfidence.MEDIUM


def test_malformed_availability_identity_is_low_confidence_and_unknown() -> None:
    result = LeverConnector(
        _client(
            lambda request: httpx.Response(
                200,
                json={"id": "lever-100", "text": "Role"},
                request=request,
            )
        ),
        clock=lambda: WHEN,
    ).check(_source(), "lever-100")
    assert result.status is VerificationStatus.VERIFIED_STATUS_UNKNOWN
    assert result.confidence is VerificationConfidence.LOW
