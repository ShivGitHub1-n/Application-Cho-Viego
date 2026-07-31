# ruff: noqa: E501

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from resume_tailor.application.job_discovery.retrieval import RetrievalService
from resume_tailor.application.job_discovery.source_refresh import (
    RefreshRunSummary,
    SourceRefreshOrchestrator,
    SourceRefreshSummary,
)
from resume_tailor.cli.job_sources import main
from resume_tailor.domain.job_discovery.models import ConnectorType, SourceJobRecord
from resume_tailor.domain.job_discovery.providers import JobSourcePage, ProviderCapabilities
from resume_tailor.domain.job_discovery.queries import ExploreJobQuery
from resume_tailor.domain.job_discovery.source_lifecycle import SourceRuntimeState
from resume_tailor.infrastructure.job_discovery_sqlite import SQLiteSourceRuntimeStateRepository
from resume_tailor.infrastructure.job_sources.registry import (
    compile_runtime_sources,
    load_company_source_registry,
)


def test_due_refresh_dry_run_is_deterministic_json(capsys) -> None:
    exit_code = main(
        [
            "--registry",
            "config/approved-job-sources.json",
            "--format",
            "json",
            "refresh",
            "--dry-run",
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert (
        output
        == '{"forced":false,"source_ids":["tenstorrent","waabi","anduril","anthropic","figure","palantir","relativity-space","rocket-lab","spacex","zoox"],"status":"dry_run"}\n'
    )


def test_unknown_source_has_nonzero_exit_and_safe_output(capsys) -> None:
    exit_code = main(
        [
            "--registry",
            "config/approved-job-sources.json",
            "--format",
            "json",
            "refresh",
            "--source-id",
            "unknown",
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 1
    assert output == '{"code":"unknown_source","status":"failed"}\n'


def test_non_dry_refresh_uses_bounded_runtime(monkeypatch, capsys) -> None:
    class FakeRefresh:
        def refresh(self, query, *, force=False, force_source_id=None, force_all=False):
            assert query.sectors == ["Software Engineering"]
            assert query.source_restrictions == ["rocket-lab"]
            assert force is False
            assert force_source_id == "rocket-lab"
            assert force_all is False
            now = datetime(2026, 7, 26, tzinfo=UTC)
            return RefreshRunSummary(
                started_at=now,
                completed_at=now,
                sources_selected=["rocket-lab"],
                outcomes=[
                    SourceRefreshSummary(
                        source_id="rocket-lab",
                        status="success",
                        retrieved_count=1,
                        accepted_count=1,
                    )
                ],
                total_retrieved=1,
                total_accepted=1,
            )

    monkeypatch.setattr(
        "resume_tailor.cli.job_sources.create_job_discovery_services",
        lambda settings: SimpleNamespace(source_refresh=FakeRefresh(), close=lambda: None),
    )
    exit_code = main(
        [
            "--registry",
            "config/approved-job-sources.json",
            "--format",
            "json",
            "refresh",
            "--source-id",
            "rocket-lab",
        ]
    )

    assert exit_code == 0
    assert '"status":"complete"' in capsys.readouterr().out


def test_non_dry_force_uses_real_orchestrator_and_query_boundary(monkeypatch, capsys, tmp_path) -> None:
    now = datetime(2026, 7, 26, 12, tzinfo=UTC)
    registry = load_company_source_registry(
        "config/approved-job-sources.json", reference_date=now.date()
    )
    source = next(item for item in compile_runtime_sources(registry) if item.source_id == "anthropic")
    states = SQLiteSourceRuntimeStateRepository(tmp_path / "runtime.sqlite3")
    states.upsert(
        SourceRuntimeState(
            source_id=source.source_id,
            last_attempted_at=now,
            next_eligible_refresh_at=now + timedelta(hours=1),
            audit_version=source.audit_version,
            registry_plan_hash=source.registry_plan_hash,
            extraction_profile_hash=source.extraction_profile_hash,
        )
    )

    class OfflineConnector:
        queries = []

        def capabilities(self, requested_source):
            return ProviderCapabilities(
                connector_type=requested_source.connector_type,
                supports_title_or_keyword=False,
                supports_sector=False,
                supports_location=False,
                supports_work_arrangement=False,
                supports_level=False,
                supports_employment_type=False,
                supports_posting_date_boundary=False,
                supports_pagination=False,
                supports_page_size=True,
                supports_availability_checks=False,
            )

        def fetch_page(self, requested_source, query, cursor, *, fetched_at):
            self.queries.append(query)
            return JobSourcePage(
                source=requested_source,
                cursor=cursor,
                records=[
                    SourceJobRecord(
                        external_job_id="offline-anthropic-1",
                        title="Software Engineer",
                        company_name=requested_source.company_name,
                        description="Build reliable software systems.",
                        official_url="https://job-boards.greenhouse.io/anthropic/jobs/offline-anthropic-1",
                    )
                ],
            )

    connector = OfflineConnector()
    retrieval_queries = []

    def retrieval_factory(selected):
        def retrieve(query, *, fetched_at):
            assert isinstance(query, ExploreJobQuery)
            retrieval_queries.append(query)
            return RetrievalService(
                sources=selected,
                connectors={ConnectorType.GREENHOUSE: connector},
            ).retrieve(query, fetched_at=fetched_at)

        return SimpleNamespace(retrieve=retrieve)

    orchestrator = SourceRefreshOrchestrator(
        sources=[source],
        retrieval_factory=retrieval_factory,
        runtime_states=states,
        now=lambda: now,
        max_sources=1,
    )
    monkeypatch.setattr(
        "resume_tailor.cli.job_sources.create_job_discovery_services",
        lambda settings: SimpleNamespace(source_refresh=orchestrator, close=lambda: None),
    )

    normal_exit = main(
        [
            "--registry",
            "config/approved-job-sources.json",
            "--format",
            "json",
            "refresh",
        ]
    )
    assert normal_exit == 1
    assert connector.queries == []
    capsys.readouterr()

    forced_exit = main(
        [
            "--registry",
            "config/approved-job-sources.json",
            "--format",
            "json",
            "refresh",
            "--force",
        ]
    )
    output = capsys.readouterr().out
    assert forced_exit == 0
    assert len(connector.queries) == 1
    assert len(retrieval_queries) == 1
    assert retrieval_queries[0].source_restrictions == []
    assert retrieval_queries[0].sectors == ["Software Engineering"]
    assert '"status":"complete"' in output


def test_dry_run_uses_persisted_runtime_state(monkeypatch, capsys, tmp_path) -> None:
    now = datetime.now(UTC)
    registry_path = tmp_path / "approved-job-sources.json"
    registry_path.write_text(
        Path("config/approved-job-sources.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    registry = load_company_source_registry(registry_path, reference_date=now.date())
    source = next(item for item in compile_runtime_sources(registry) if item.source_id == "anthropic")
    database_path = tmp_path / "runtime.sqlite3"
    states = SQLiteSourceRuntimeStateRepository(database_path)
    state = SourceRuntimeState(
        source_id=source.source_id,
        last_attempted_at=now,
        next_eligible_refresh_at=now + timedelta(hours=1),
        audit_version=source.audit_version,
        registry_plan_hash=source.registry_plan_hash,
        extraction_profile_hash=source.extraction_profile_hash,
    )
    states.upsert(state)
    before = states.get(source.source_id)

    monkeypatch.setattr(
        "resume_tailor.cli.job_sources.Settings",
        lambda **_kwargs: SimpleNamespace(
            app_data_directory=tmp_path,
            profile_store_filename=database_path.name,
            job_discovery_source_registry_path=registry_path,
            job_discovery_source_max_pages=10,
        ),
    )

    normal_exit = main(
        ["--registry", str(registry_path), "--format", "json", "refresh", "--dry-run"]
    )
    normal_output = capsys.readouterr().out
    assert normal_exit == 0
    assert source.source_id not in normal_output
    assert states.get(source.source_id) == before

    forced_exit = main(
        [
            "--registry",
            str(registry_path),
            "--format",
            "json",
            "refresh",
            "--dry-run",
            "--force",
        ]
    )
    forced_output = capsys.readouterr().out
    assert forced_exit == 0
    assert source.source_id in forced_output
    assert states.get(source.source_id) == before
