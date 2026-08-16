from __future__ import annotations

from datetime import UTC, datetime

from pydantic import AnyHttpUrl

from resume_tailor.application.job_discovery.retrieval import RetrievalService
from resume_tailor.domain.job_discovery.models import (
    ConnectorType,
    JobLevel,
    JobSearchPreferences,
    NormalizedLocation,
    SourceJobRecord,
    SourceRecordWarning,
    SourceRecordWarningCode,
    SupportedJobSource,
    WorkArrangement,
    WorkArrangementPreferenceMode,
)
from resume_tailor.domain.job_discovery.providers import (
    JobSourcePage,
    ProviderCapabilities,
    ProviderCursor,
)
from resume_tailor.domain.job_discovery.queries import ExploreJobQuery, TailoredJobQuery

WHEN = datetime(2026, 7, 24, 12, tzinfo=UTC)


def _source(source_id: str) -> SupportedJobSource:
    return SupportedJobSource(
        source_id=source_id,
        connector_type=ConnectorType.GREENHOUSE,
        company_name="Acme",
        board_token=source_id,
        enabled=True,
        official_base_url=AnyHttpUrl("https://boards.greenhouse.io"),
    )


def _preferences() -> JobSearchPreferences:
    return JobSearchPreferences(
        user_id="user-1",
        profile_id="profile-1",
        version=1,
        role_family_priority=[],
        target_titles=["Engineer"],
        related_title_variants=[],
        technical_themes=["RESUME SECRET"],
        career_interests=[],
        job_levels=[JobLevel.MID],
        locations=[NormalizedLocation(raw="Toronto")],
        work_arrangement=WorkArrangement.REMOTE,
        work_arrangement_mode=WorkArrangementPreferenceMode.PREFERRED,
        preferred_companies=[],
        created_at=WHEN,
    )


def _record(external_id: str) -> SourceJobRecord:
    return SourceJobRecord(
        external_job_id=external_id,
        title="Engineer",
        company_name="Acme",
        description="Build systems.",
        official_url=AnyHttpUrl(f"https://boards.greenhouse.io/acme/jobs/{external_id}"),
    )


def _role_record(external_id: str, title: str, description: str = "Build systems."):
    return SourceJobRecord(
        external_job_id=external_id,
        title=title,
        company_name="Acme",
        description=description,
        official_url=AnyHttpUrl(
            f"https://boards.greenhouse.io/acme/jobs/{external_id}"
        ),
    )


class FakeConnector:
    def __init__(self, pages: list[JobSourcePage] | Exception) -> None:
        self.pages = pages
        self.queries = []

    def capabilities(self, source: SupportedJobSource) -> ProviderCapabilities:
        return ProviderCapabilities(
            connector_type=source.connector_type,
            supports_title_or_keyword=False,
            supports_sector=False,
            supports_location=False,
            supports_work_arrangement=False,
            supports_level=False,
            supports_employment_type=False,
            supports_posting_date_boundary=False,
            supports_pagination=True,
            supports_page_size=True,
            supports_availability_checks=True,
        )

    def fetch_page(self, source, query, cursor, *, fetched_at):
        self.queries.append(query)
        if isinstance(self.pages, Exception):
            raise self.pages
        index = 0 if cursor is None else int(cursor.value or "0")
        return self.pages[index]


def test_retrieval_stops_on_repeated_cursor_and_returns_safe_partial_diagnostics() -> None:
    source = _source("source-1")
    connector = FakeConnector(
        [
            JobSourcePage(
                source=source,
                records=[_record("1")],
                next_cursor=ProviderCursor(value="1"),
                has_more=True,
            ),
            JobSourcePage(
                source=source,
                cursor=ProviderCursor(value="1"),
                records=[_record("2")],
                next_cursor=ProviderCursor(value="1"),
                has_more=True,
            ),
        ]
    )
    query = TailoredJobQuery(
        preferences=_preferences(),
        local_profile_text="RESUME SECRET PROFILE",
        resume_text="RESUME SECRET FULL TEXT",
    )

    outcome = RetrievalService(
        sources=[source], connectors={ConnectorType.GREENHOUSE: connector}, max_pages=5
    ).retrieve(query, fetched_at=WHEN)

    assert [item.record.external_job_id for item in outcome.records] == ["1", "2"]
    assert outcome.source_outcomes[0].warnings[0].code == "repeated_cursor"
    assert outcome.source_outcomes[0].pages_fetched == 2
    assert "RESUME SECRET" not in repr(connector.queries[0])


def test_retrieval_keeps_successful_source_when_another_source_fails() -> None:
    good_source = _source("a-good")
    bad_source = _source("b-bad")
    good = FakeConnector(
        [
            JobSourcePage(
                source=good_source,
                records=[_record("good")],
            )
        ]
    )
    bad = FakeConnector(RuntimeError("safe transport failure"))

    outcome = RetrievalService(
        sources=[bad_source, good_source],
        connectors={ConnectorType.GREENHOUSE: {"a-good": good, "b-bad": bad}},
    ).retrieve(TailoredJobQuery(preferences=_preferences()), fetched_at=WHEN)

    assert [item.record.external_job_id for item in outcome.records] == ["good"]
    assert outcome.partial_success is True
    statuses = {item.source_id: item.status.value for item in outcome.source_outcomes}
    assert statuses == {"a-good": "success", "b-bad": "failed"}
    failed = next(item for item in outcome.source_outcomes if item.source_id == "b-bad")
    assert failed.errors[0].code == "source_failure"


def test_provider_warning_text_is_replaced_by_safe_structured_diagnostics() -> None:
    source = _source("source-1")
    connector = FakeConnector(
        [
            JobSourcePage(
                source=source,
                warnings=[
                    SourceRecordWarning(
                        external_job_id=None,
                        code=SourceRecordWarningCode.INVALID_LOCATION,
                        message="RESUME SECRET PROFILE",
                    )
                ],
            )
        ]
    )

    outcome = RetrievalService(
        sources=[source], connectors={ConnectorType.GREENHOUSE: connector}
    ).retrieve(
        TailoredJobQuery(
            preferences=_preferences(),
            local_profile_text="RESUME SECRET PROFILE",
            resume_text="RESUME SECRET FULL TEXT",
        ),
        fetched_at=WHEN,
    )

    diagnostic = outcome.source_outcomes[0].warnings[0]
    assert diagnostic.message == "Provider record had an invalid location."
    assert "RESUME SECRET" not in diagnostic.model_dump_json()


def test_hardware_explore_retrieves_matching_approved_source_records() -> None:
    source = _source("source-1")
    connector = FakeConnector(
        [
            JobSourcePage(
                source=source,
                records=[
                    _role_record("1", "Electrical Engineer, Manufacturing Test"),
                    _role_record("2", "Systems Integration Engineer, Air Vehicles"),
                    _role_record("3", "Robotics Software Integration Engineer"),
                    _role_record("4", "Backend Software Engineer"),
                ],
            )
        ]
    )

    outcome = RetrievalService(
        sources=[source], connectors={ConnectorType.GREENHOUSE: connector}
    ).retrieve(
        ExploreJobQuery(sectors=["Hardware / Systems Integration"]),
        fetched_at=WHEN,
    )

    assert [item.record.external_job_id for item in outcome.records] == ["1", "2", "3"]


def test_local_title_and_level_filters_use_the_posting_title_not_description_noise() -> None:
    source = _source("source-1")
    preferences = _preferences().model_copy(
        update={
            "target_titles": ["Embedded Software Engineer"],
            "related_title_variants": [],
            "job_levels": [JobLevel.ENTRY],
            "locations": [],
            "work_arrangement": WorkArrangement.UNKNOWN,
        }
    )
    connector = FakeConnector(
        [
            JobSourcePage(
                source=source,
                records=[
                    _role_record(
                        "1",
                        "Embedded Software Engineer",
                        "Partner with senior and staff engineers.",
                    ),
                    _role_record(
                        "2",
                        "Recruiter",
                        "Recruit Software Engineers and hardware leaders.",
                    ),
                    _role_record("3", "Senior Embedded Software Engineer"),
                ],
            )
        ]
    )

    outcome = RetrievalService(
        sources=[source], connectors={ConnectorType.GREENHOUSE: connector}
    ).retrieve(TailoredJobQuery(preferences=preferences), fetched_at=WHEN)

    assert [item.record.external_job_id for item in outcome.records] == ["1"]


def test_software_explore_remains_functional_without_matching_every_engineer() -> None:
    source = _source("source-1")
    connector = FakeConnector(
        [
            JobSourcePage(
                source=source,
                records=[
                    _role_record("1", "Software Engineer, Platform"),
                    _role_record("2", "Mechanical Engineer"),
                ],
            )
        ]
    )

    outcome = RetrievalService(
        sources=[source], connectors={ConnectorType.GREENHOUSE: connector}
    ).retrieve(ExploreJobQuery(sectors=["Software Engineering"]), fetched_at=WHEN)

    assert [item.record.external_job_id for item in outcome.records] == ["1"]


def test_source_with_no_sector_matches_returns_sanitized_diagnostic() -> None:
    source = _source("source-1")
    connector = FakeConnector(
        [
            JobSourcePage(
                source=source,
                records=[_role_record("1", "Account Executive")],
            )
        ]
    )

    outcome = RetrievalService(
        sources=[source], connectors={ConnectorType.GREENHOUSE: connector}
    ).retrieve(
        ExploreJobQuery(sectors=["Hardware / Systems Integration"]),
        fetched_at=WHEN,
    )

    assert outcome.records == []
    assert outcome.source_outcomes[0].warnings[-1].code == "local_filter_no_match"
    assert "Account Executive" not in outcome.source_outcomes[0].warnings[-1].message
