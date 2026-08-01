from __future__ import annotations

import json
from datetime import UTC, datetime

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
from resume_tailor.domain.models import RoleFamily

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


def test_multi_page_item_order_and_duplicate_placement_are_canonical() -> None:
    source = _source("source-a")

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

        def __init__(self, page_records: list[list[SourceJobRecord]]) -> None:
            self.page_records = page_records

        def fetch_page(self, source, query, cursor, *, fetched_at):
            page_index = 0 if cursor.value is None else 1
            return JobSourcePage(
                source=source,
                cursor=cursor,
                next_cursor=type(cursor)(value="page-2") if page_index == 0 else type(cursor)(),
                records=self.page_records[page_index],
                has_more=page_index == 0,
            )

    def records(order: tuple[str, str, str, str]) -> list[list[SourceJobRecord]]:
        values = {
            "first": SourceJobRecord(
                external_job_id="first",
                title="Software Engineer",
                company_name="Example Robotics",
                description="Build first systems.",
                official_url="https://boards.greenhouse.io/source-a/jobs/first",
            ),
            "shared": SourceJobRecord(
                external_job_id="shared",
                title="Software Engineer",
                company_name="Example Robotics",
                description="Build shared systems.",
                official_url="https://boards.greenhouse.io/source-a/jobs/shared",
                source_payload={"requisition_id": "REQ-SHARED"},
            ),
            "second": SourceJobRecord(
                external_job_id="second",
                title="Software Engineer",
                company_name="Example Robotics",
                description="Build second systems.",
                official_url="https://boards.greenhouse.io/source-a/jobs/second",
            ),
        }
        first_page = [values[key] for key in order[:2]]
        second_page = [values[key] for key in order[2:]]
        return [first_page, second_page]

    def canonical(order: tuple[str, str, str, str]) -> tuple[object, str]:
        outcome = RetrievalService(
            sources=[source],
            connectors={ConnectorType.GREENHOUSE: Connector(records(order))},
        ).retrieve(ExploreJobQuery(sectors=["Software Engineering"]), fetched_at=NOW)
        jobs = [
            normalize_job_record(item.record, source, fetched_at=NOW)
            for item in outcome.records
        ]
        deduplicated = deduplicate_jobs(jobs)
        return deduplicated, json.dumps(deduplicated.model_dump(mode="json"), sort_keys=True)

    first = canonical(("shared", "first", "second", "shared"))
    second = canonical(("first", "shared", "shared", "second"))

    # Providers must paginate sequentially, so page order itself is not a legal
    # input. This exercises the supported multi-page boundary: record order and
    # duplicate placement may vary within the pages reached by the same cursors.
    assert first == second
    assert len(first[0].jobs) == 3


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


def test_preference_order_permutations_produce_one_tailored_query() -> None:
    def preferences(
        titles: list[str], locations: list[str], preferred_companies: list[str]
    ) -> JobSearchPreferences:
        return JobSearchPreferences(
            user_id="user-1",
            profile_id="profile-1",
            version=1,
            role_family_priority=[RoleFamily.SOFTWARE_DATA_ENGINEERING],
            target_titles=titles,
            related_title_variants=[],
            technical_themes=["python", "sql"],
            career_interests=["robotics", "software"],
            job_levels=[JobLevel.MID],
            locations=[NormalizedLocation(raw=value) for value in locations],
            work_arrangement=WorkArrangement.REMOTE,
            work_arrangement_mode=WorkArrangementPreferenceMode.PREFERRED,
            preferred_companies=preferred_companies,
            created_at=NOW,
        )

    first = TailoredJobQuery(
        preferences=preferences(
            ["Software Engineer", "Backend Engineer"],
            ["Toronto", "Montreal"],
            ["Example Robotics", "Acme Systems"],
        )
    )
    second = TailoredJobQuery(
        preferences=preferences(
            ["Software Engineer", "Backend Engineer"],
            ["Montreal", "Toronto"],
            ["Acme Systems", "Example Robotics"],
        )
    )

    assert first.to_provider_query() == second.to_provider_query()


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
