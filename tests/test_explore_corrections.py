from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from resume_tailor.application.job_discovery.experience import _recommendation_view
from resume_tailor.application.job_discovery.queries import GetJobFeedService
from resume_tailor.domain.job_discovery.feeds import FeedVisibility, _visibility
from resume_tailor.domain.job_discovery.models import (
    ConnectorType,
    DiscoveredJob,
    EligibilityStatus,
    FeedKind,
    FitGrade,
    NormalizedLocation,
    RecommendationVisibility,
    SupportedJobSource,
    VerificationConfidence,
    VerificationStatus,
    WorkArrangement,
)
from resume_tailor.domain.job_discovery.queries import ExploreJobQuery
from resume_tailor.infrastructure.config import Settings
from resume_tailor.infrastructure.dependencies import create_job_discovery_services
from resume_tailor.infrastructure.job_discovery_sqlite import (
    SQLiteDiscoveredJobRepository,
    SQLiteSupportedJobSourceRepository,
)


def test_job_services_reuse_persisted_approved_sources_without_registry_path(
    tmp_path: Path,
) -> None:
    source = SupportedJobSource(
        source_id="example-board",
        connector_type=ConnectorType.GREENHOUSE,
        company_name="Example",
        board_token="example",
        enabled=True,
        official_base_url="https://example.test",
    )
    database = tmp_path / "jobs.sqlite3"
    SQLiteSupportedJobSourceRepository(database).save(source)

    services = create_job_discovery_services(
        Settings(
            app_data_directory=tmp_path,
            profile_store_filename="jobs.sqlite3",
            job_discovery_source_registry_path=None,
        )
    )

    assert [item.source_id for item in services.refresh._sources.list_enabled()] == [
        "example-board"
    ]
    services.close_resources()


def test_explore_feed_query_isolated_by_sector() -> None:
    created = datetime(2026, 1, 1, tzinfo=UTC)

    class Recommendations:
        def list_for_feed(
            self, user_id: str, feed_kind: str, *, include_excluded: bool
        ) -> list[object]:
            del user_id, feed_kind, include_excluded
            return [
                type(
                    "Recommendation",
                    (),
                    {
                        "profile_id": "profile",
                        "explore_sector": "Software Engineering",
                        "visibility": RecommendationVisibility.VISIBLE,
                        "created_at": created,
                        "run_id": "software",
                        "job_id": "software",
                    },
                )(),
                type(
                    "Recommendation",
                    (),
                    {
                        "profile_id": "profile",
                        "explore_sector": "Robotics / Autonomous Systems",
                        "visibility": RecommendationVisibility.VISIBLE,
                        "created_at": created,
                        "run_id": "robotics",
                        "job_id": "robotics",
                    },
                )(),
            ]

    details = GetJobFeedService(Recommendations()).get(
        "user", FeedKind.EXPLORE, profile_id="profile", sector="Robotics / Autonomous Systems"
    )

    assert [item.job_id for item in details.items] == ["robotics"]


def test_explore_keeps_weak_and_ineligible_roles_browsable() -> None:
    evaluation = SimpleNamespace(
        fit_grade=FitGrade.DONT_MATCH,
        eligibility=SimpleNamespace(status=EligibilityStatus.INELIGIBLE),
        diagnostics=SimpleNamespace(total=0),
    )

    assert _visibility(evaluation, feed_kind=FeedKind.EXPLORE) is FeedVisibility.VISIBLE


def test_recommendation_metadata_uses_earliest_provenance_and_latest_fetch() -> None:
    first = datetime(2026, 1, 1, tzinfo=UTC)
    latest = datetime(2026, 1, 4, tzinfo=UTC)
    job = SimpleNamespace(
        posted_at=datetime(2025, 12, 30, tzinfo=UTC),
        fetched_at=latest,
        source_provenance=[
            type("Provenance", (), {"fetched_at": latest})(),
            type("Provenance", (), {"fetched_at": first})(),
        ],
        location=SimpleNamespace(raw="Toronto"),
        company_name="Example",
        source=SimpleNamespace(company_name="Example", source_id="example"),
        work_arrangement=WorkArrangement.HYBRID,
        verification_status=VerificationStatus.VERIFIED_STATUS_UNKNOWN,
        verification_confidence=VerificationConfidence.MEDIUM,
        title="Example role",
        official_url="https://example.test/job",
    )
    recommendation = SimpleNamespace(
        id="recommendation",
        job_id="job",
        feed_kind=FeedKind.EXPLORE,
        score=SimpleNamespace(fit_grade=FitGrade.GOOD),
        eligibility=SimpleNamespace(status=EligibilityStatus.ELIGIBLE),
        provisional=False,
        reasons=[],
        gaps=[],
        unresolved_facts=[],
        primary_role_family=None,
        visibility=RecommendationVisibility.VISIBLE,
    )

    view = _recommendation_view(recommendation, job, now=datetime(2026, 1, 5, tzinfo=UTC))

    assert view.first_seen_at == first
    assert view.checked_at == latest
    assert view.first_seen_label == "First seen 4 days ago"
    assert view.checked_label == "Checked 1 day ago"


def test_explore_provider_query_uses_sector_terms_without_tailored_profile_terms() -> None:
    query = ExploreJobQuery(
        sectors=["Controls / Mechatronics"],
        profile_id="profile",
        evaluate_fit=True,
    ).to_provider_query()

    assert query.sectors == ["Controls / Mechatronics"]
    assert "Controls Engineer" in query.titles
    assert "Mechatronics Engineer" in query.titles
    assert "Software Engineer" not in query.titles
    assert query.locations == []


def test_discovered_job_upsert_preserves_first_seen_across_refreshes(tmp_path: Path) -> None:
    source = SupportedJobSource(
        source_id="example-board",
        connector_type=ConnectorType.GREENHOUSE,
        company_name="Example",
        board_token="example",
        enabled=True,
        official_base_url="https://example.test",
    )
    first = datetime(2026, 1, 1, tzinfo=UTC)
    second = datetime(2026, 1, 4, tzinfo=UTC)

    def job(fetched_at: datetime) -> DiscoveredJob:
        return DiscoveredJob(
            id="job-1",
            source=source,
            external_job_id="external-1",
            title="Example role",
            company_name="Example",
            description="Description",
            official_url="https://example.test/job-1",
            location=NormalizedLocation(raw="Toronto"),
            work_arrangement=WorkArrangement.HYBRID,
            fetched_at=fetched_at,
        )

    repository = SQLiteDiscoveredJobRepository(tmp_path / "jobs.sqlite3")
    repository.upsert(job(first))
    repository.upsert(job(second))

    assert repository.get("job-1").first_seen_at == first


def created_at() -> datetime:
    return datetime(2026, 1, 1, tzinfo=UTC)
