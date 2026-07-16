from __future__ import annotations

import re
from datetime import datetime

from resume_tailor.domain.job_discovery.models import (
    DiscoveredJob,
    EligibilityAssessment,
    EligibilityReasonCode,
    EligibilityStatus,
    JobLevel,
    JobSearchPreferences,
    VerificationStatus,
    WorkArrangement,
    WorkArrangementPreferenceMode,
)
from resume_tailor.domain.models import MasterProfile

_UNKNOWN_VERIFICATION = {
    VerificationStatus.UNVERIFIED,
    VerificationStatus.VERIFIED_STATUS_UNKNOWN,
}


def _location_matches(job: DiscoveredJob, preferences: JobSearchPreferences) -> bool | None:
    if not preferences.locations:
        return None
    if not job.location.parseable:
        return None
    for target in preferences.locations:
        if (
            (target.city is None or target.city == job.location.city)
            and (target.region is None or target.region == job.location.region)
            and (
                target.country_code is None
                or target.country_code == job.location.country_code
            )
        ):
            return True
    return False


def _arrangement_conflict(
    job: DiscoveredJob, preferences: JobSearchPreferences
) -> bool | None:
    mode = preferences.work_arrangement_mode
    desired = preferences.work_arrangement
    if mode in {
        WorkArrangementPreferenceMode.PREFERRED,
        WorkArrangementPreferenceMode.ACCEPTABLE,
    }:
        return False
    if desired is WorkArrangement.UNKNOWN:
        return False
    if job.work_arrangement is WorkArrangement.UNKNOWN:
        return None
    if mode is WorkArrangementPreferenceMode.REQUIRED:
        return job.work_arrangement is not desired
    if mode is WorkArrangementPreferenceMode.EXCLUDED:
        return job.work_arrangement is desired
    return False


def _company_excluded(job: DiscoveredJob, preferences: JobSearchPreferences) -> bool:
    company = job.normalized_company_name or job.company_name.casefold().strip()
    return company in {value.casefold().strip() for value in preferences.excluded_companies}


def _authorization_conflict(
    job: DiscoveredJob, preferences: JobSearchPreferences
) -> bool | None:
    language = " ".join(job.requirements.authorization_language).casefold()
    if not language:
        return False
    constraints = [value.casefold().strip() for value in preferences.work_authorization_constraints]
    if not constraints:
        return None
    countries = {"canada", "united states", "usa", "us", "ca"}
    mentioned_countries = {country for country in countries if country in language}
    allowed_countries = {
        country for country in countries if any(country in constraint for constraint in constraints)
    }
    if mentioned_countries and allowed_countries and not mentioned_countries & allowed_countries:
        return True
    if "sponsor" in language and any("no sponsorship" in constraint for constraint in constraints):
        return True
    return False


def _degree_conflict(job: DiscoveredJob, profile: MasterProfile | None) -> bool | None:
    requirements = job.requirements.degree_requirements
    if not requirements:
        return False
    if profile is None or not profile.education:
        return None
    programs = [education.program.casefold() for education in profile.education]
    for requirement in requirements:
        lowered = requirement.casefold()
        degree_terms = (
            "bachelor",
            "master",
            "ph.d",
            "phd",
            "doctorate",
            "diploma",
        )
        matching_terms = [term for term in degree_terms if term in lowered]
        if matching_terms and any(
            term in program for term in matching_terms for program in programs
        ):
            return False
    return True


def _graduation_conflict(job: DiscoveredJob, profile: MasterProfile | None) -> bool | None:
    requirements = job.requirements.graduation_requirements
    if not requirements:
        return False
    if profile is None or not profile.education:
        return None
    years = {
        int(match.group(0))
        for education in profile.education
        for value in (education.expected_graduation_date, education.graduation_date)
        if value
        for match in [re.search(r"\b20\d{2}\b", value)]
        if match
    }
    required_years = {
        int(match.group(0))
        for requirement in requirements
        for match in [re.search(r"\b20\d{2}\b", requirement)]
        if match
    }
    if not years or not required_years:
        return None
    return not bool(years & required_years)


class EligibilityEvaluator:
    def assess(
        self,
        job: DiscoveredJob,
        preferences: JobSearchPreferences,
        *,
        as_of: datetime,
        profile: MasterProfile | None = None,
    ) -> EligibilityAssessment:
        reasons: list[EligibilityReasonCode] = []
        explanations: list[str] = []
        unknown = False

        if job.verification_status in {
            VerificationStatus.UNAVAILABLE,
            VerificationStatus.EXPIRED,
        }:
            reasons.append(EligibilityReasonCode.VERIFICATION_UNAVAILABLE)
            explanations.append("The source marked this posting unavailable or expired.")
        elif job.verification_status in _UNKNOWN_VERIFICATION:
            unknown = True

        arrangement_conflict = _arrangement_conflict(job, preferences)
        if arrangement_conflict is True:
            reasons.append(EligibilityReasonCode.WORK_ARRANGEMENT_CONFLICT)
            explanations.append("The posting conflicts with the selected work-arrangement rule.")
        elif arrangement_conflict is None:
            unknown = True

        location_match = _location_matches(job, preferences)
        if location_match is False:
            reasons.append(EligibilityReasonCode.LOCATION_MISMATCH)
            explanations.append("The posting location does not match any selected location.")
        elif location_match is None and preferences.locations:
            unknown = True

        posting_age_days: int | None = None
        if job.posted_at is None:
            if preferences.max_posting_age_days is not None:
                unknown = True
        elif preferences.max_posting_age_days is not None:
            posting_age_days = max(0, (as_of - job.posted_at).days)
            if posting_age_days > preferences.max_posting_age_days:
                reasons.append(EligibilityReasonCode.POSTING_TOO_OLD)
                explanations.append("The known posting age exceeds the selected maximum age.")

        if _company_excluded(job, preferences):
            reasons.append(EligibilityReasonCode.COMPANY_EXCLUDED)
            explanations.append("The company is on the excluded-company list.")

        authorization_conflict = _authorization_conflict(job, preferences)
        if authorization_conflict is True:
            reasons.append(EligibilityReasonCode.AUTHORIZATION_CONFLICT)
            explanations.append(
                "The posting's explicit authorization language conflicts with preferences."
            )
        elif authorization_conflict is None:
            unknown = True

        degree_conflict = _degree_conflict(job, profile)
        if degree_conflict is True:
            reasons.append(EligibilityReasonCode.DEGREE_CONFLICT)
            explanations.append(
                "The explicit degree requirement conflicts with the reviewed profile."
            )
        elif degree_conflict is None:
            unknown = True

        graduation_conflict = _graduation_conflict(job, profile)
        if graduation_conflict is True:
            reasons.append(EligibilityReasonCode.GRADUATION_CONFLICT)
            explanations.append(
                "The explicit graduation-date requirement conflicts with the reviewed profile."
            )
        elif graduation_conflict is None:
            unknown = True

        if preferences.job_levels and job.requirements.job_level is not JobLevel.UNKNOWN:
            if job.requirements.job_level not in preferences.job_levels:
                reasons.append(EligibilityReasonCode.JOB_LEVEL_MISMATCH)
                explanations.append("The posting level is outside the selected job levels.")
        elif preferences.job_levels:
            unknown = True

        if (
            preferences.job_levels
            and job.requirements.experience_years is not None
            and all(level in {JobLevel.INTERN, JobLevel.ENTRY} for level in preferences.job_levels)
            and job.requirements.experience_years >= 3
        ):
            reasons.append(EligibilityReasonCode.EXPERIENCE_REQUIREMENT_TOO_HIGH)
            explanations.append(
                "The experience requirement is substantially above the selected level."
            )

        if reasons:
            status = EligibilityStatus.INELIGIBLE
        elif unknown:
            status = EligibilityStatus.UNKNOWN
        else:
            status = EligibilityStatus.ELIGIBLE
        return EligibilityAssessment(
            status=status,
            reasons=reasons,
            explanations=explanations,
            location_match=location_match,
            verification_confidence=job.verification_confidence,
            posting_age_days=posting_age_days,
        )


def assess_eligibility(
    job: DiscoveredJob,
    preferences: JobSearchPreferences,
    *,
    as_of: datetime,
) -> EligibilityAssessment:
    return EligibilityEvaluator().assess(job, preferences, as_of=as_of)
