from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from resume_tailor.domain.job_discovery.models import (
    ConnectorType,
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
from resume_tailor.infrastructure.job_sources.greenhouse import GreenhouseConnector

FIXTURES = Path(__file__).parents[2] / "fixtures" / "job_sources"
WHEN = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)


def _source(**overrides: object) -> SupportedJobSource:
    values: dict[str, object] = {
        "source_id": "acme-greenhouse",
        "connector_type": ConnectorType.GREENHOUSE,
        "company_name": "Acme Robotics",
        "board_token": "acme",
        "enabled": True,
        "official_base_url": "https://boards.greenhouse.io",
    }
    values.update(overrides)
    return SupportedJobSource(**values)


def _client(
    payload: object,
    *,
    status_code: int = 200,
    calls: list[httpx.Request] | None = None,
) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request)
        return httpx.Response(status_code, json=payload, request=request)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _fixture(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_valid_fixture_normalizes_without_detail_requests() -> None:
    calls: list[httpx.Request] = []
    client = _client(_fixture("greenhouse_valid.json"), calls=calls)
    result = GreenhouseConnector(client).fetch(_source(), fetched_at=WHEN)

    assert [record.external_job_id for record in result.records] == ["100", "200"]
    first = result.records[0]
    assert first.title == "Perception Engineer"
    assert first.company_name == "Acme Robotics"
    assert "Python" in first.description
    assert first.location_raw == "Toronto, ON, Canada"
    assert first.work_arrangement is WorkArrangement.HYBRID
    assert str(first.official_url) == "https://boards.greenhouse.io/acme/jobs/gh-100"
    assert first.source_updated_at == datetime(2026, 7, 14, 10, 0, tzinfo=UTC)
    assert first.posted_at is None
    assert [request.url.path for request in calls] == ["/v1/boards/acme/jobs"]


def test_detail_mode_is_explicit_and_maps_only_approved_detail_dates() -> None:
    calls: list[httpx.Request] = []
    list_payload = _fixture("greenhouse_valid.json")
    detail_payload = {
        "id": 100,
        "title": "Perception Engineer",
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/gh-100",
        "first_published": "2026-06-01T09:00:00Z",
        "application_deadline": "2026-08-01T23:59:00Z",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/100"):
            return httpx.Response(200, json=detail_payload, request=request)
        return httpx.Response(200, json=list_payload, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = GreenhouseConnector(client, fetch_details=True).fetch(_source(), fetched_at=WHEN)
    assert result.records[0].posted_at == datetime(2026, 6, 1, 9, tzinfo=UTC)
    assert result.records[0].application_deadline == datetime(2026, 8, 1, 23, 59, tzinfo=UTC)
    assert len(calls) == 3


def test_source_connector_skips_bad_record_with_warning_and_fails_bad_envelope() -> None:
    source = _source()
    result = GreenhouseConnector(_client(_fixture("greenhouse_malformed_record.json"))).fetch(
        source, fetched_at=WHEN
    )
    assert result.records[0].external_job_id == "ok-1"
    assert result.warnings[0].code is SourceRecordWarningCode.MISSING_TITLE
    with pytest.raises(JobSourceEnvelopeError):
        GreenhouseConnector(_client(_fixture("greenhouse_malformed_envelope.json"))).fetch(
            source, fetched_at=WHEN
        )


def test_malformed_top_level_envelope_raises() -> None:
    with pytest.raises(JobSourceEnvelopeError):
        GreenhouseConnector(_client(_fixture("greenhouse_malformed_envelope.json"))).fetch(
            _source(), fetched_at=WHEN
        )


def test_url_policy_accepts_safe_http_upgrade_but_preserves_arbitrary_http() -> None:
    safe = _fixture("greenhouse_valid.json")
    assert isinstance(safe, dict)
    safe["jobs"][0]["absolute_url"] = "http://boards.greenhouse.io/acme/jobs/gh-100"
    result = GreenhouseConnector(_client(safe)).fetch(_source(), fetched_at=WHEN)
    assert str(result.records[0].official_url).startswith("https://boards.greenhouse.io/")

    arbitrary = _fixture("greenhouse_valid.json")
    arbitrary["jobs"][0]["absolute_url"] = "http://careers.example.com/acme/jobs/gh-100"
    result = GreenhouseConnector(_client(arbitrary)).fetch(_source(), fetched_at=WHEN)
    assert str(result.records[0].official_url).startswith("http://careers.example.com/")


def test_missing_optional_fields_warn_without_fabricating_values() -> None:
    payload = {
        "jobs": [
            {
                "id": "missing-fields",
                "title": "Role",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/missing-fields",
                "updated_at": "not-a-date",
            }
        ]
    }
    result = GreenhouseConnector(_client(payload)).fetch(_source(), fetched_at=WHEN)
    assert result.records[0].posted_at is None
    assert result.records[0].location_raw is None
    assert [warning.code for warning in result.warnings] == [
        SourceRecordWarningCode.INVALID_LOCATION,
        SourceRecordWarningCode.INVALID_TIMESTAMP,
    ]


def test_invalid_official_url_is_a_record_warning() -> None:
    payload = {"jobs": [{"id": "bad-url", "title": "Role", "absolute_url": "not-a-url"}]}
    result = GreenhouseConnector(_client(payload)).fetch(_source(), fetched_at=WHEN)
    assert result.records == []
    assert result.warnings[0].code is SourceRecordWarningCode.INVALID_OFFICIAL_URL


def test_explicit_unknown_status_is_medium_confidence() -> None:
    payload = {
        "id": 100,
        "title": "Perception Engineer",
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/gh-100",
        "status": "pending",
    }
    result = GreenhouseConnector(_client(payload), clock=lambda: WHEN).check(_source(), "100")
    assert result.status is VerificationStatus.VERIFIED_STATUS_UNKNOWN
    assert result.confidence is VerificationConfidence.MEDIUM


def test_malformed_availability_identity_is_low_confidence_and_unknown() -> None:
    payload = {"id": 100, "title": "Perception Engineer"}
    result = GreenhouseConnector(_client(payload), clock=lambda: WHEN).check(_source(), "100")
    assert result.status is VerificationStatus.VERIFIED_STATUS_UNKNOWN
    assert result.confidence is VerificationConfidence.LOW


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
        GreenhouseConnector(_client({}, status_code=status)).fetch(_source(), fetched_at=WHEN)


def test_transport_failure_maps_to_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(JobSourceTransportError):
        GreenhouseConnector(client).fetch(_source(), fetched_at=WHEN)


def test_availability_returns_verified_active_with_high_confidence() -> None:
    payload = {
        "id": 100,
        "title": "Perception Engineer",
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/gh-100",
    }
    result = GreenhouseConnector(_client(payload), clock=lambda: WHEN).check(_source(), "gh-100")
    assert result.status is VerificationStatus.VERIFIED_ACTIVE
    assert result.confidence is VerificationConfidence.HIGH


def test_availability_not_found_is_explicit_unavailable() -> None:
    result = GreenhouseConnector(_client({}, status_code=404), clock=lambda: WHEN).check(
        _source(), "missing"
    )
    assert result.status is VerificationStatus.UNAVAILABLE
    assert result.confidence is VerificationConfidence.LOW
