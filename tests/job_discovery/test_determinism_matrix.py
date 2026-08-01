from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from resume_tailor.application.job_discovery.queries import GetJobFeedService
from resume_tailor.application.job_discovery.refresh import RefreshJobDiscoveryService
from resume_tailor.application.job_discovery.retrieval import RetrievalService
from resume_tailor.domain.job_discovery.deduplication import deduplicate_jobs
from resume_tailor.domain.job_discovery.evaluation import (
    InternalDiagnostics,
    JobEvaluation,
    JobEvaluator,
    ProvisionalAssessment,
    RoleRelevanceAssessment,
)
from resume_tailor.domain.job_discovery.evidence import (
    EvidenceLedger,
    EvidenceQuality,
    canonical_requirement_set,
)
from resume_tailor.domain.job_discovery.feeds import rank_feed_candidates
from resume_tailor.domain.job_discovery.models import (
    ConnectorType,
    EligibilityAssessment,
    EligibilityStatus,
    FitGrade,
    JobLevel,
    JobRequirement,
    JobRequirementSignals,
    JobSearchPreferences,
    NormalizedLocation,
    ProfileCapabilityEvidence,
    ProfileCapabilityIndex,
    RequirementCategory,
    RequirementImportance,
    SourceJobRecord,
    SupportedJobSource,
    VerificationConfidence,
    WorkArrangement,
    WorkArrangementPreferenceMode,
)
from resume_tailor.domain.job_discovery.normalization import normalize_job_record
from resume_tailor.domain.job_discovery.providers import JobSourcePage, ProviderCapabilities
from resume_tailor.domain.job_discovery.queries import ExploreJobQuery, FeedKind, TailoredJobQuery
from resume_tailor.domain.job_discovery.requirements import RequirementExtractor
from resume_tailor.domain.job_discovery.source_lifecycle import (
    SourceLifecycleOutcome,
    SourceRuntimeState,
    fingerprint_content,
)
from resume_tailor.domain.models import MasterProfile, RoleFamily
from resume_tailor.infrastructure.job_discovery_sqlite import (
    SQLiteAtomicJobDiscoveryPersistence,
    SQLiteDiscoveredJobRepository,
    SQLiteDiscoveryRunRepository,
    SQLiteJobRecommendationRepository,
    SQLiteSourceIdentityAliasRepository,
)

NOW = datetime(2026, 7, 30, 12, tzinfo=UTC)


def _source(source_id: str) -> SupportedJobSource:
    return SupportedJobSource(
        source_id=source_id,
        connector_type=ConnectorType.GREENHOUSE,
        company_name="Example Robotics",
        board_token=source_id,
        enabled=True,
        official_base_url="https://boards.greenhouse.io",
    )


def _job(source_id: str, external_id: str, *, posted_at: datetime | None = NOW):
    return normalize_job_record(
        SourceJobRecord(
            external_job_id=external_id,
            title="Software Engineer",
            company_name="Example Robotics",
            description="Build Python services and test reliable systems.",
            official_url=f"https://boards.greenhouse.io/{source_id}/jobs/{external_id}",
            location_raw="Toronto, ON, Canada",
            work_arrangement=WorkArrangement.REMOTE,
            posted_at=posted_at,
            source_payload={"requisition_id": f"REQ-{external_id}"},
        ),
        _source(source_id),
        fetched_at=NOW,
    )


def _evaluation(job, grade: FitGrade = FitGrade.GOOD) -> JobEvaluation:
    return JobEvaluation(
        job_id=job.id,
        eligibility=EligibilityAssessment(
            status=EligibilityStatus.ELIGIBLE,
            verification_confidence=VerificationConfidence.HIGH,
        ),
        role_relevance=RoleRelevanceAssessment(relevant=True),
        fit_grade=grade,
        diagnostics=InternalDiagnostics(total=50),
        provisional=ProvisionalAssessment(),
    )


def _refresh_preferences(
    *,
    locations: list[str] | None = None,
    levels: list[JobLevel] | None = None,
    preferred_companies: list[str] | None = None,
    career_interests: list[str] | None = None,
) -> JobSearchPreferences:
    return JobSearchPreferences(
        user_id="user-1",
        profile_id="profile-1",
        version=1,
        role_family_priority=[RoleFamily.SOFTWARE_DATA_ENGINEERING],
        target_titles=["Software Engineer"],
        related_title_variants=["Backend Engineer"],
        technical_themes=["python"],
        career_interests=career_interests or ["software"],
        job_levels=levels or [JobLevel.MID],
        locations=[NormalizedLocation(raw=value) for value in locations or ["Toronto"]],
        work_arrangement=WorkArrangement.REMOTE,
        work_arrangement_mode=WorkArrangementPreferenceMode.PREFERRED,
        preferred_companies=preferred_companies or [],
        created_at=NOW,
        confirmed_at=NOW,
    )


class _RefreshProfileRepository:
    def __init__(self) -> None:
        self.profile = MasterProfile(
            id="profile-1",
            user_id="user-1",
            version=1,
            display_name="Candidate",
            experiences=[
                {
                    "id": "entry-1",
                    "title": "Software Engineer",
                    "kind": "experience",
                    "technologies": ["Python"],
                }
            ],
            evidence=[
                {
                    "id": "evidence-1",
                    "entity_id": "entry-1",
                    "source_text": "Built Python software systems.",
                    "technologies": ["Python"],
                }
            ],
        )

    def get(self, profile_id: str) -> MasterProfile | None:
        return self.profile if profile_id == self.profile.id else None

    def list_all(self) -> list[MasterProfile]:
        return [self.profile]


class _RefreshPreferencesRepository:
    def __init__(self, preferences: JobSearchPreferences) -> None:
        self.preferences = preferences

    def get_current(self, user_id: str, profile_id: str) -> JobSearchPreferences | None:
        if (user_id, profile_id) != (self.preferences.user_id, self.preferences.profile_id):
            return None
        return self.preferences


class _RefreshSourceRepository:
    def __init__(self, sources: list[SupportedJobSource]) -> None:
        self.sources = sources

    def list_enabled(self) -> list[SupportedJobSource]:
        return list(self.sources)


class _PagedRefreshConnector:
    def __init__(self, pages: list[list[SourceJobRecord]]) -> None:
        self.pages = pages

    def capabilities(self, source: SupportedJobSource) -> ProviderCapabilities:
        return ProviderCapabilities(
            connector_type=source.connector_type,
            supports_title_or_keyword=False,
            supports_sector=True,
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
        page_index = 0 if cursor.value is None else int(cursor.value)
        next_index = page_index + 1
        return JobSourcePage(
            source=source,
            cursor=cursor,
            next_cursor=type(cursor)(value=str(next_index))
            if next_index < len(self.pages)
            else type(cursor)(),
            records=list(self.pages[page_index]),
            has_more=next_index < len(self.pages),
        )


def _refresh_record(
    external_id: str,
    *,
    source_id: str,
    company: str = "Example Robotics",
    description: str = "Required Python. Build reliable systems.",
    location_raw: str | None = "Toronto, ON, Canada",
    posted_at: datetime | None = NOW,
    requisition_id: str | None = None,
) -> SourceJobRecord:
    url_id = requisition_id or external_id
    return SourceJobRecord(
        external_job_id=external_id,
        title="Software Engineer",
        company_name=company,
        description=description,
        official_url=f"https://boards.greenhouse.io/{source_id}/jobs/{url_id}",
        location_raw=location_raw,
        work_arrangement=WorkArrangement.REMOTE,
        posted_at=posted_at,
        source_payload={"requisition_id": requisition_id or f"REQ-{external_id}"},
    )


def _refresh_scenario(
    tmp_path: Path,
    *,
    preferences: JobSearchPreferences,
    page_arrangement: list[list[SourceJobRecord]],
) -> dict[str, object]:
    sources = [_source("source-a"), _source("source-b")]
    database = tmp_path / "refresh.sqlite3"
    profiles = _RefreshProfileRepository()
    discovered_jobs = SQLiteDiscoveredJobRepository(database)
    recommendations = SQLiteJobRecommendationRepository(database)
    runs = SQLiteDiscoveryRunRepository(database)
    aliases = SQLiteSourceIdentityAliasRepository(database)
    refresh = RefreshJobDiscoveryService(
        profiles=profiles,
        preferences=_RefreshPreferencesRepository(preferences),
        sources=_RefreshSourceRepository(sources),
        connectors={
            ConnectorType.GREENHOUSE: {
                "source-a": _PagedRefreshConnector(page_arrangement),
                "source-b": _PagedRefreshConnector(
                    [[
                        _refresh_record(
                            "shared-b",
                            source_id="source-b",
                            requisition_id="REQ-SHARED",
                        )
                    ]]
                ),
            }
        },
        discovered_jobs=discovered_jobs,
        recommendations=recommendations,
        runs=runs,
        atomic_persistence=SQLiteAtomicJobDiscoveryPersistence(database),
        aliases=aliases,
    )
    feeds = GetJobFeedService(recommendations, runs)
    tailored_run = refresh.refresh(
        "user-1", "profile-1", preferences, started_at=NOW
    )
    explore_run = refresh.refresh_explore(
        "user-1",
        sectors=["Software Engineering"],
        profile_id="profile-1",
        started_at=NOW,
    )

    def feed_payload(feed_kind: FeedKind, *, excluded_only: bool) -> dict[str, object]:
        details = feeds.get(
            "user-1", feed_kind, profile_id="profile-1", excluded_only=excluded_only
        )
        return {
            "items": [item.model_dump(mode="json") for item in details.items],
            "excluded_count": details.excluded_count,
        }

    def job_payloads(feed_kind: FeedKind) -> list[dict[str, object]]:
        visible = feeds.get("user-1", feed_kind, profile_id="profile-1")
        excluded = feeds.get(
            "user-1", feed_kind, profile_id="profile-1", excluded_only=True
        )
        job_ids = {item.job_id for item in [*visible.items, *excluded.items]}
        return sorted(
            [discovered_jobs.get(job_id).model_dump(mode="json") for job_id in job_ids],
            key=lambda item: str(item["id"]),
        )

    return {
        "tailored_run": tailored_run.model_dump(mode="json"),
        "explore_run": explore_run.model_dump(mode="json"),
        "tailored": feed_payload(FeedKind.TAILORED, excluded_only=False),
        "tailored_excluded": feed_payload(FeedKind.TAILORED, excluded_only=True),
        "explore": feed_payload(FeedKind.EXPLORE, excluded_only=False),
        "explore_excluded": feed_payload(FeedKind.EXPLORE, excluded_only=True),
        "tailored_jobs": job_payloads(FeedKind.TAILORED),
        "explore_jobs": job_payloads(FeedKind.EXPLORE),
        "aliases": sorted(
            [
                alias.model_dump(mode="json")
                for source in sources
                for alias in aliases.list_for_source(source.source_id)
            ],
            key=lambda item: (str(item["source_id"]), str(item["identity_value"])),
        ),
    }


def test_provider_source_page_and_posting_order_is_canonical() -> None:
    sources = [_source("source-b"), _source("source-a")]

    class Connector:
        def capabilities(self, source: SupportedJobSource) -> ProviderCapabilities:
            return ProviderCapabilities(
                connector_type=source.connector_type,
                supports_title_or_keyword=False,
                supports_sector=True,
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
            return JobSourcePage(
                source=source,
                records=[
                    SourceJobRecord(
                        external_job_id="2",
                        title="Software Engineer",
                        company_name="Example Robotics",
                        description="Build systems.",
                        official_url=f"https://boards.greenhouse.io/{source.source_id}/jobs/2",
                    ),
                    SourceJobRecord(
                        external_job_id="1",
                        title="Software Engineer",
                        company_name="Example Robotics",
                        description="Build systems.",
                        official_url=f"https://boards.greenhouse.io/{source.source_id}/jobs/1",
                    ),
                ],
            )

    outcome = RetrievalService(
        sources=sources,
        connectors={ConnectorType.GREENHOUSE: Connector()},
    ).retrieve(
        ExploreJobQuery(sectors=["Software Engineering"]),
        fetched_at=NOW,
    )

    assert [(item.source_id, item.status.value) for item in outcome.source_outcomes] == [
        ("source-a", "success"),
        ("source-b", "success"),
    ]
    assert [
        (item.source.source_id, item.record.external_job_id)
        for item in outcome.records
    ] == [("source-a", "1"), ("source-a", "2"), ("source-b", "1"), ("source-b", "2")]


def test_multi_page_item_order_and_duplicate_placement_are_canonical(tmp_path: Path) -> None:
    preferences = _refresh_preferences().model_copy(
        update={"excluded_companies": ["Excluded Corp"]}
    )
    shared_a = _refresh_record(
        "shared-a",
        source_id="source-a",
        requisition_id="REQ-SHARED",
    )
    eligible = _refresh_record("eligible", source_id="source-a")
    unknown = _refresh_record(
        "unknown",
        source_id="source-a",
        location_raw=None,
        posted_at=None,
    )
    dont_match = _refresh_record(
        "dont-match",
        source_id="source-a",
        company="Excluded Corp",
        description="Required CUDA and JAX. Build unrelated systems.",
    )

    first_dir = tmp_path / "first-pages"
    second_dir = tmp_path / "second-pages"
    first_dir.mkdir()
    second_dir.mkdir()
    first = _refresh_scenario(
        first_dir,
        preferences=preferences,
        page_arrangement=[[shared_a, eligible], [unknown, dont_match]],
    )
    second = _refresh_scenario(
        second_dir,
        preferences=preferences,
        page_arrangement=[[eligible, shared_a], [dont_match, unknown]],
    )

    # Sequential cursor order is contractual; the supported nondeterministic
    # boundary is item order and duplicate placement within the real pages.
    assert first == second
    assert len(first["tailored"]["items"]) >= 1
    assert first["tailored_excluded"]["items"]
    assert any(item["provisional"] for item in first["tailored"]["items"])


def test_requirement_and_evidence_order_permutations_are_canonical() -> None:
    requirements = [
        JobRequirement(
            term="python",
            category=RequirementCategory.TECHNOLOGY,
            importance=RequirementImportance.REQUIRED,
            source_text="Python experience is required.",
            source_start=20,
            source_end=26,
        ),
        JobRequirement(
            term="api",
            category=RequirementCategory.TECHNOLOGY,
            importance=RequirementImportance.PREFERRED,
            source_text="API knowledge is preferred.",
            source_start=0,
            source_end=3,
        ),
    ]
    profile_evidence = [
        ProfileCapabilityEvidence(
            source_type="confirmed_evidence",
            source_id="evidence-b",
            source_text="Built Python APIs.",
            demonstrated=True,
        ),
        ProfileCapabilityEvidence(
            source_type="confirmed_evidence",
            source_id="evidence-a",
            source_text="Built Python APIs.",
            demonstrated=True,
        ),
    ]

    canonical_a = canonical_requirement_set(requirements)
    canonical_b = canonical_requirement_set(list(reversed(requirements)))
    ledger_a = EvidenceLedger.allocate(
        canonical_a,
        ProfileCapabilityIndex(terms={"python": profile_evidence, "api": profile_evidence}),
    )
    ledger_b = EvidenceLedger.allocate(
        canonical_b,
        ProfileCapabilityIndex(
            terms={
                "python": list(reversed(profile_evidence)),
                "api": list(reversed(profile_evidence)),
            }
        ),
    )

    assert canonical_a == canonical_b
    assert ledger_a.model_dump(mode="json") == ledger_b.model_dump(mode="json")
    assert ledger_a.allocations[0].evidence_id == "evidence-a"
    assert ledger_a.matches[0].evidence_quality is EvidenceQuality.DEMONSTRATED

    evaluation_preferences = JobSearchPreferences(
        user_id="user-1",
        profile_id="profile-1",
        version=1,
        role_family_priority=[RoleFamily.SOFTWARE_DATA_ENGINEERING],
        target_titles=["Software Engineer"],
        related_title_variants=[],
        technical_themes=["python"],
        career_interests=[],
        job_levels=[],
        locations=[],
        work_arrangement=WorkArrangement.UNKNOWN,
        preferred_companies=[],
        created_at=NOW,
    )
    job = _job("source-a", "evaluation").model_copy(
        update={"requirements": JobRequirementSignals(requirements=requirements)}
    )
    evaluation_a = JobEvaluator().evaluate(
        job,
        evaluation_preferences,
        ProfileCapabilityIndex(terms={"python": profile_evidence, "api": profile_evidence}),
        as_of=NOW,
    )
    evaluation_b = JobEvaluator().evaluate(
        job.model_copy(
            update={
                "requirements": JobRequirementSignals(
                    requirements=list(reversed(requirements))
                )
            }
        ),
        evaluation_preferences,
        ProfileCapabilityIndex(
            terms={
                "python": list(reversed(profile_evidence)),
                "api": list(reversed(profile_evidence)),
            }
        ),
        as_of=NOW,
    )
    assert evaluation_a.model_dump(mode="json") == evaluation_b.model_dump(mode="json")


def test_preference_order_permutations_produce_one_tailored_query(tmp_path: Path) -> None:
    def preferences(
        titles: list[str],
        locations: list[str],
        preferred_companies: list[str],
        career_interests: list[str],
        job_levels: list[JobLevel],
    ) -> JobSearchPreferences:
        return JobSearchPreferences(
            user_id="user-1",
            profile_id="profile-1",
            version=1,
            role_family_priority=[RoleFamily.SOFTWARE_DATA_ENGINEERING],
            target_titles=titles,
            related_title_variants=[],
            technical_themes=["python", "sql"],
            career_interests=career_interests,
            job_levels=job_levels,
            locations=[NormalizedLocation(raw=value) for value in locations],
            work_arrangement=WorkArrangement.REMOTE,
            work_arrangement_mode=WorkArrangementPreferenceMode.PREFERRED,
            preferred_companies=preferred_companies,
            created_at=NOW,
        )

    first = preferences(
        ["Software Engineer", "Backend Engineer"],
        ["Toronto", "Montreal"],
        ["Example Robotics", "Acme Systems"],
        ["robotics", "software"],
        [JobLevel.MID, JobLevel.SENIOR],
    )
    second = preferences(
        ["Software Engineer", "Backend Engineer"],
        ["Montreal", "Toronto"],
        ["Acme Systems", "Example Robotics"],
        ["software", "robotics"],
        [JobLevel.SENIOR, JobLevel.MID],
    )

    first_query = TailoredJobQuery(
        preferences=first,
        source_restrictions=["source-b", "source-a"],
    ).to_provider_query()
    second_query = TailoredJobQuery(
        preferences=second,
        source_restrictions=["source-a", "source-b"],
    ).to_provider_query()
    assert first_query == second_query
    assert first_query.titles == ["Software Engineer", "Backend Engineer"]

    first_dir = tmp_path / "first-preferences"
    second_dir = tmp_path / "second-preferences"
    first_dir.mkdir()
    second_dir.mkdir()
    records = [[
        _refresh_record("preferred", source_id="source-a", company="Example Robotics"),
        _refresh_record("other", source_id="source-a", company="Acme Systems"),
    ]]
    first_output = _refresh_scenario(
        first_dir,
        preferences=first,
        page_arrangement=records,
    )
    second_output = _refresh_scenario(
        second_dir,
        preferences=second,
        page_arrangement=records,
    )

    assert first_output["tailored"] == second_output["tailored"]
    assert first_output["tailored_excluded"] == second_output["tailored_excluded"]
    assert first_output["tailored_jobs"] == second_output["tailored_jobs"]
    assert first_output["aliases"] == second_output["aliases"]
    first_grades = {
        item["job_id"]: item["score"]["fit_grade"]
        for item in first_output["tailored"]["items"]
    }
    second_grades = {
        item["job_id"]: item["score"]["fit_grade"]
        for item in second_output["tailored"]["items"]
    }
    assert first_grades == second_grades


def test_alias_and_canonical_serialization_is_input_order_independent() -> None:
    first = _job("source-a", "a", posted_at=NOW).model_copy(
        update={"requisition_id": "REQ-SHARED"}
    )
    second = _job("source-b", "b", posted_at=NOW).model_copy(
        update={"requisition_id": "REQ-SHARED"}
    )
    forward = deduplicate_jobs([first, second])
    reverse = deduplicate_jobs([second, first])

    assert forward == reverse
    assert json.dumps(forward.model_dump(mode="json"), sort_keys=True) == json.dumps(
        reverse.model_dump(mode="json"), sort_keys=True
    )
    assert [item.source_id for item in forward.jobs[0].source_provenance] == [
        "source-a",
        "source-b",
    ]


def test_requirement_evidence_and_preference_order_have_stable_serialized_output() -> None:
    extractor = RequirementExtractor()
    first = extractor.extract(
        "Software Engineer",
        "Required experience with Python and Docker. Preferred knowledge of SQL.",
        "Toronto",
        WorkArrangement.REMOTE,
    )
    second = extractor.extract(
        "Software Engineer",
        "Required experience with Python and Docker. Preferred knowledge of SQL.",
        "Toronto",
        WorkArrangement.REMOTE,
    )
    assert first == second
    assert [item.term for item in first.requirements] == sorted(
        [item.term for item in first.requirements],
        key=lambda term: next(
            item.source_start for item in first.requirements if item.term == term
        ),
    )

    content_a = {"provider": ["greenhouse", "lever"], "requirements": ["python", "sql"]}
    content_b = {"requirements": ["python", "sql"], "provider": ["greenhouse", "lever"]}
    assert fingerprint_content(content_a) == fingerprint_content(content_b)
    runtime = SourceRuntimeState(source_id="source-a")
    assert runtime.completed(
        at=NOW,
        outcome=SourceLifecycleOutcome.SUCCESS,
        diagnostic_codes=["z", "a"],
    ).diagnostic_codes == [
        "a",
        "z",
    ]


def test_equal_rank_ties_use_stable_ids_for_tailored_and_explore() -> None:
    jobs = [_job("source-a", "b"), _job("source-a", "a")]
    candidates = [(job, _evaluation(job)) for job in jobs]
    expected = [job.id for job in sorted(jobs, key=lambda job: job.id)]

    tailored = rank_feed_candidates(candidates, feed_kind=FeedKind.TAILORED)
    explore = rank_feed_candidates(candidates, feed_kind=FeedKind.EXPLORE)

    assert [item.job.id for item in tailored.items] == expected
    assert [item.job.id for item in explore.items] == expected
