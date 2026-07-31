from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from resume_tailor.domain.job_discovery.eligibility import EligibilityEvaluator
from resume_tailor.domain.job_discovery.location import parse_location
from resume_tailor.domain.job_discovery.models import (
    ConnectorType,
    EligibilityReasonCode,
    EligibilityStatus,
    JobSearchPreferences,
    SourceJobRecord,
    SupportedJobSource,
    VerificationStatus,
    WorkArrangement,
    WorkArrangementPreferenceMode,
)
from resume_tailor.domain.job_discovery.normalization import normalize_job_record
from resume_tailor.domain.models import MasterProfile, RoleFamily

NOW = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


def _preferences(**overrides: object) -> JobSearchPreferences:
    values: dict[str, object] = {
        "user_id": "user-1",
        "profile_id": "profile-1",
        "version": 1,
        "role_family_priority": [RoleFamily.SOFTWARE_DATA_ENGINEERING],
        "target_titles": ["Software Engineer"],
        "related_title_variants": [],
        "technical_themes": [],
        "career_interests": [],
        "job_levels": [],
        "locations": [parse_location("Toronto, ON, Canada")],
        "work_arrangement": WorkArrangement.REMOTE,
        "work_arrangement_mode": WorkArrangementPreferenceMode.PREFERRED,
        "preferred_companies": [],
        "max_posting_age_days": 30,
        "created_at": NOW,
    }
    values.update(overrides)
    return JobSearchPreferences(**values)


def _job(
    *,
    location: str | None = "Toronto, ON, Canada",
    arrangement: WorkArrangement = WorkArrangement.HYBRID,
    posted_at: datetime | None = NOW - timedelta(days=5),
    status: VerificationStatus = VerificationStatus.VERIFIED_ACTIVE,
    description: str = "Required Python.",
    title: str = "Software Engineer",
):
    source = SupportedJobSource(
        source_id="acme-board",
        connector_type=ConnectorType.GREENHOUSE,
        company_name="Acme Robotics",
        board_token="acme",
        enabled=True,
        official_base_url="https://boards.greenhouse.io",
    )
    job = normalize_job_record(
        SourceJobRecord(
            external_job_id="1",
            title=title,
            company_name="Acme Robotics",
            description=description,
            official_url="https://boards.greenhouse.io/acme/jobs/1",
            location_raw=location,
            work_arrangement=arrangement,
            posted_at=posted_at,
            source_updated_at=None,
            application_deadline=None,
            source_payload={},
        ),
        source,
        fetched_at=NOW,
    )
    return job.model_copy(update={"verification_status": status})


def test_eligible_job_and_unknown_data_are_distinct() -> None:
    evaluator = EligibilityEvaluator()

    eligible = evaluator.assess(_job(), _preferences(), as_of=NOW)
    unknown = evaluator.assess(_job(location=None), _preferences(), as_of=NOW)

    assert eligible.status is EligibilityStatus.ELIGIBLE
    assert eligible.location_match is True
    assert unknown.status is EligibilityStatus.UNKNOWN
    assert unknown.location_match is None


@pytest.mark.parametrize(
    ("job", "preferences", "reason"),
    [
        (
            _job(arrangement=WorkArrangement.REMOTE),
            _preferences(
                work_arrangement=WorkArrangement.REMOTE,
                work_arrangement_mode=WorkArrangementPreferenceMode.EXCLUDED,
            ),
            EligibilityReasonCode.WORK_ARRANGEMENT_CONFLICT,
        ),
        (
            _job(arrangement=WorkArrangement.HYBRID),
            _preferences(
                work_arrangement=WorkArrangement.REMOTE,
                work_arrangement_mode=WorkArrangementPreferenceMode.REQUIRED,
            ),
            EligibilityReasonCode.WORK_ARRANGEMENT_CONFLICT,
        ),
        (
            _job(location="Austin, TX, United States"),
            _preferences(),
            EligibilityReasonCode.LOCATION_MISMATCH,
        ),
        (
            _job(posted_at=NOW - timedelta(days=31)),
            _preferences(),
            EligibilityReasonCode.POSTING_TOO_OLD,
        ),
        (
            _job(status=VerificationStatus.UNAVAILABLE),
            _preferences(),
            EligibilityReasonCode.VERIFICATION_UNAVAILABLE,
        ),
        (
            _job(status=VerificationStatus.EXPIRED),
            _preferences(),
            EligibilityReasonCode.VERIFICATION_UNAVAILABLE,
        ),
    ],
)
def test_each_hard_eligibility_conflict_is_explicit(job, preferences, reason) -> None:
    result = EligibilityEvaluator().assess(job, preferences, as_of=NOW)

    assert result.status is EligibilityStatus.INELIGIBLE
    assert reason in result.reasons


def test_preferred_and_acceptable_arrangements_never_reject() -> None:
    evaluator = EligibilityEvaluator()

    preferred = evaluator.assess(
        _job(arrangement=WorkArrangement.HYBRID),
        _preferences(
            work_arrangement=WorkArrangement.REMOTE,
            work_arrangement_mode=WorkArrangementPreferenceMode.PREFERRED,
        ),
        as_of=NOW,
    )
    acceptable = evaluator.assess(
        _job(arrangement=WorkArrangement.HYBRID),
        _preferences(
            work_arrangement=WorkArrangement.REMOTE,
            work_arrangement_mode=WorkArrangementPreferenceMode.ACCEPTABLE,
        ),
        as_of=NOW,
    )

    assert preferred.status is EligibilityStatus.ELIGIBLE
    assert acceptable.status is EligibilityStatus.ELIGIBLE


def test_job_level_filter_is_hard_only_when_preferences_have_levels() -> None:
    job = _job(title="Senior Software Engineer")

    result = EligibilityEvaluator().assess(
        job,
        _preferences(job_levels=[]),
        as_of=NOW,
    )
    rejected = EligibilityEvaluator().assess(
        job,
        _preferences(job_levels=["intern"]),
        as_of=NOW,
    )

    assert result.status is EligibilityStatus.ELIGIBLE
    assert rejected.status is EligibilityStatus.INELIGIBLE


def test_role_family_exclusion_company_and_authorization_conflicts_are_hard_gates() -> None:
    role_mismatch = EligibilityEvaluator().assess(
        _job(title="Senior Robotics Engineer"),
        _preferences(role_family_priority=[RoleFamily.SOFTWARE_DATA_ENGINEERING]),
        as_of=NOW,
    )
    excluded_company = EligibilityEvaluator().assess(
        _job(),
        _preferences(excluded_companies=["Acme Robotics"]),
        as_of=NOW,
    )
    authorization = EligibilityEvaluator().assess(
        _job(description="Required Python. Candidates must be authorized to work in Canada."),
        _preferences(work_authorization_constraints=["United States"]),
        as_of=NOW,
    )

    assert role_mismatch.status is EligibilityStatus.ELIGIBLE
    assert EligibilityReasonCode.ROLE_FAMILY_MISMATCH not in role_mismatch.reasons
    assert excluded_company.status is EligibilityStatus.INELIGIBLE
    assert authorization.status is EligibilityStatus.INELIGIBLE
    assert EligibilityReasonCode.AUTHORIZATION_CONFLICT in authorization.reasons


def test_degree_and_graduation_conflicts_are_hard_gates_when_profile_facts_are_known() -> None:
    profile = MasterProfile(
        id="profile-1",
        user_id="user-1",
        display_name="Candidate",
        education=[
            {
                "school": "University",
                "program": "Bachelor of Engineering",
                "expected_graduation_date": "2026-06-01",
            }
        ],
    )
    degree_conflict = EligibilityEvaluator().assess(
        _job(description="Required master's degree."),
        _preferences(),
        as_of=NOW,
        profile=profile,
    )
    graduation_conflict = EligibilityEvaluator().assess(
        _job(description="Required bachelor's degree. Class of 2024."),
        _preferences(),
        as_of=NOW,
        profile=profile,
    )

    assert degree_conflict.status is EligibilityStatus.INELIGIBLE
    assert EligibilityReasonCode.DEGREE_CONFLICT in degree_conflict.reasons
    assert graduation_conflict.status is EligibilityStatus.INELIGIBLE
    assert EligibilityReasonCode.GRADUATION_CONFLICT in graduation_conflict.reasons


def test_sponsorship_available_unavailable_and_unstated_preserve_authority() -> None:
    unavailable = EligibilityEvaluator().assess(
        _job(description="No visa sponsorship available. Required Python."),
        _preferences(),
        as_of=NOW,
        profile=MasterProfile(
            id="profile-1",
            user_id="user-1",
            display_name="Candidate",
            requires_sponsorship=True,
        ),
    )
    unstated = EligibilityEvaluator().assess(
        _job(description="Required Python."),
        _preferences(),
        as_of=NOW,
        profile=MasterProfile(
            id="profile-1",
            user_id="user-1",
            display_name="Candidate",
            requires_sponsorship=True,
        ),
    )
    available = EligibilityEvaluator().assess(
        _job(description="Visa sponsorship is available. Required Python."),
        _preferences(),
        as_of=NOW,
        profile=MasterProfile(
            id="profile-1",
            user_id="user-1",
            display_name="Candidate",
            requires_sponsorship=True,
        ),
    )

    assert unavailable.status is EligibilityStatus.INELIGIBLE
    assert unstated.status is EligibilityStatus.UNKNOWN
    assert available.status is EligibilityStatus.ELIGIBLE


def test_license_clearance_and_citizenship_authority_is_typed() -> None:
    license_result = EligibilityEvaluator().assess(
        _job(description="An active professional license is required."),
        _preferences(),
        as_of=NOW,
        profile=MasterProfile(
            id="profile-1",
            user_id="user-1",
            display_name="Candidate",
            professional_license_status="confirmed_none",
        ),
    )
    unknown_license = EligibilityEvaluator().assess(
        _job(description="An active professional license is required."),
        _preferences(),
        as_of=NOW,
        profile=MasterProfile(id="profile-1", user_id="user-1", display_name="Candidate"),
    )
    credential_conflict = EligibilityEvaluator().assess(
        _job(description="US citizenship and active security clearance are required."),
        _preferences(),
        as_of=NOW,
        profile=MasterProfile(
            id="profile-1",
            user_id="user-1",
            display_name="Candidate",
            authorized_work_locations=["Canada"],
            clearance_status="confirmed_none",
        ),
    )

    assert license_result.status is EligibilityStatus.INELIGIBLE
    assert "eligibility:license" in license_result.conflict_references
    assert unknown_license.status is EligibilityStatus.UNKNOWN
    assert credential_conflict.status is EligibilityStatus.INELIGIBLE
    assert "eligibility:citizenship" in credential_conflict.conflict_references
    assert "eligibility:clearance" in credential_conflict.conflict_references


def test_degree_or_equivalent_experience_remains_an_alternative() -> None:
    profile = MasterProfile(
        id="profile-1",
        user_id="user-1",
        display_name="Candidate",
        education=[{"school": "University", "program": "General Studies"}],
        experiences=[{"id": "experience-1", "title": "Engineer", "kind": "experience"}],
    )
    result = EligibilityEvaluator().assess(
        _job(description="Bachelor's degree or equivalent experience required."),
        _preferences(),
        as_of=NOW,
        profile=profile,
    )

    assert result.status is EligibilityStatus.ELIGIBLE


def test_eligibility_is_pure_and_unknown_posting_age_is_retained() -> None:
    job = _job(posted_at=None)
    preferences = _preferences()
    before = (job.model_dump(mode="python"), preferences.model_dump(mode="python"))

    result = EligibilityEvaluator().assess(job, preferences, as_of=NOW)

    assert result.posting_age_days is None
    assert job.model_dump(mode="python") == before[0]
    assert preferences.model_dump(mode="python") == before[1]
