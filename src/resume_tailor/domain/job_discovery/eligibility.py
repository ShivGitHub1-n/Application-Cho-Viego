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
        job_raw = job.location.raw.casefold().strip()
        exact_raw = {
            target.raw.casefold().strip() for target in preferences.locations if target.raw.strip()
        }
        if job_raw and job_raw in exact_raw:
            return True
        if "remote" in job_raw and "canada" in job_raw:
            if any("remote" in value and "canada" in value for value in exact_raw):
                return True
        return None
    for target in preferences.locations:
        if (
            (target.city is None or target.city == job.location.city)
            and (target.region is None or target.region == job.location.region)
            and (target.country_code is None or target.country_code == job.location.country_code)
        ):
            return True
    return False


def _arrangement_conflict(job: DiscoveredJob, preferences: JobSearchPreferences) -> bool | None:
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
    job: DiscoveredJob,
    preferences: JobSearchPreferences,
    profile: MasterProfile | None = None,
) -> bool | None:
    language = " ".join(job.requirements.authorization_language).casefold()
    if not language:
        return None if profile is not None and profile.requires_sponsorship else False
    constraints = [value.casefold().strip() for value in preferences.work_authorization_constraints]
    countries = {"canada", "united states", "usa", "us", "ca"}
    mentioned_countries = {
        country
        for country in countries
        if re.search(rf"(?<!\w){re.escape(country)}(?!\w)", language)
    }
    allowed_countries = {
        country
        for country in countries
        if any(
            re.search(rf"(?<!\w){re.escape(country)}(?!\w)", constraint)
            for constraint in constraints
        )
    }
    if mentioned_countries and allowed_countries and not mentioned_countries & allowed_countries:
        return True
    sponsorship_unavailable = bool(
        re.search(
            r"\b(?:no|without|does not provide|cannot provide|unavailable)\s+"
            r"(?:visa\s+)?sponsorship\b",
            language,
        )
    )
    sponsorship_available = bool(
        re.search(
            r"\b(?:sponsorship|visa sponsorship)\s+(?:is\s+)?(?:available|provided|offered)\b",
            language,
        )
    )
    requires_sponsorship = bool(profile and profile.requires_sponsorship)
    if sponsorship_unavailable and (
        requires_sponsorship
        or any(re.search(r"\bno\s+sponsorship\b", constraint) for constraint in constraints)
    ):
        return True
    if sponsorship_available:
        return False
    if not constraints and not requires_sponsorship:
        return None
    return False


def _degree_conflict(job: DiscoveredJob, profile: MasterProfile | None) -> bool | None:
    requirements = job.requirements.degree_requirements
    if not requirements:
        return False
    if (
        job.requirements.degree_equivalent_experience
        and profile is not None
        and profile.experiences
    ):
        return False
    if profile is None or not profile.education:
        return None
    programs = [education.program.casefold() for education in profile.education]
    highest = 0
    for program in programs:
        if re.search(r"\b(?:ph\.?d|doctorate)\b", program):
            highest = max(highest, 3)
        elif re.search(r"\bmaster(?:'s)?\b", program):
            highest = max(highest, 2)
        elif re.search(r"\bbachelor(?:'s)?\b|\bdiploma\b", program):
            highest = max(highest, 1)
    for requirement in requirements:
        lowered = requirement.casefold()
        if re.search(r"\b(?:ph\.?d|doctorate)\b", lowered) and highest >= 3:
            return False
        if re.search(r"\bmaster(?:'s)?\b", lowered) and highest >= 2:
            return False
        if re.search(r"\bbachelor(?:'s)?\b|\bdiploma\b", lowered) and highest >= 1:
            return False
    return True


def _credential_conflicts(
    job: DiscoveredJob, profile: MasterProfile | None
) -> tuple[bool | None, list[str], list[str]]:
    language = " ".join(job.requirements.authorization_language).casefold()
    if not language:
        return False, [], []
    conflict = False
    unknown = False
    posting_refs: list[str] = []
    profile_refs: list[str] = []
    if re.search(r"\b(?:active\s+)?(?:professional\s+)?license|designation\b", language):
        posting_refs.append("eligibility:license")
        status = profile.professional_license_status if profile is not None else "unknown"
        profile_refs.append("profile:professional-license-status")
        if status == "confirmed_none":
            conflict = True
        elif status in {"unknown", "none_recorded"}:
            unknown = True
    if re.search(r"\b(?:active\s+)?(?:secret|top secret|security)\s+clearance\b", language):
        posting_refs.append("eligibility:clearance")
        status = profile.clearance_status if profile is not None else "unknown"
        profile_refs.append("profile:clearance-status")
        if status == "confirmed_none":
            conflict = True
        elif status in {"unknown", "none_recorded"}:
            unknown = True
    if re.search(r"\bcitizenship\b|\bcitizen\b", language):
        posting_refs.append("eligibility:citizenship")
        locations = [
            value.casefold() for value in (profile.authorized_work_locations if profile else [])
        ]
        if profile is None or not locations:
            unknown = True
        elif not any("united states" in value or value in {"us", "usa"} for value in locations):
            conflict = True
        profile_refs.append("profile:authorized-work-locations")
    if conflict:
        return True, posting_refs, profile_refs
    if unknown:
        return None, posting_refs, profile_refs
    return False, posting_refs, profile_refs


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
        posting_references: list[str] = []
        profile_references: list[str] = []
        conflict_references: list[str] = []
        unresolved_facts: list[str] = []
        unknown = False

        if job.verification_status in {
            VerificationStatus.UNAVAILABLE,
            VerificationStatus.EXPIRED,
        }:
            reasons.append(EligibilityReasonCode.VERIFICATION_UNAVAILABLE)
            explanations.append("The source marked this posting unavailable or expired.")
            posting_references.append("eligibility:verification")
        elif job.verification_status in _UNKNOWN_VERIFICATION:
            unknown = True
            unresolved_facts.append("Source verification status is not confirmed active.")
            posting_references.append("eligibility:verification")

        arrangement_conflict = _arrangement_conflict(job, preferences)
        if arrangement_conflict is True:
            reasons.append(EligibilityReasonCode.WORK_ARRANGEMENT_CONFLICT)
            explanations.append("The posting conflicts with the selected work-arrangement rule.")
            posting_references.append("eligibility:work-arrangement")
        elif arrangement_conflict is None:
            unknown = True
            unresolved_facts.append("The posting does not establish the required work arrangement.")
            posting_references.append("eligibility:work-arrangement")

        location_match = _location_matches(job, preferences)
        if location_match is False:
            reasons.append(EligibilityReasonCode.LOCATION_MISMATCH)
            explanations.append("The posting location does not match any selected location.")
            posting_references.append("eligibility:location")
        elif location_match is None and preferences.locations:
            unknown = True
            unresolved_facts.append(
                "The posting location cannot be matched exactly from its stated location."
            )
            posting_references.append("eligibility:location")

        posting_age_days: int | None = None
        if job.posted_at is None:
            if preferences.max_posting_age_days is not None:
                unknown = True
        elif preferences.max_posting_age_days is not None:
            posting_age_days = max(0, (as_of - job.posted_at).days)
            if posting_age_days > preferences.max_posting_age_days:
                reasons.append(EligibilityReasonCode.POSTING_TOO_OLD)
                explanations.append("The known posting age exceeds the selected maximum age.")
                posting_references.append("eligibility:posting-date")

        if _company_excluded(job, preferences):
            reasons.append(EligibilityReasonCode.COMPANY_EXCLUDED)
            explanations.append("The company is on the excluded-company list.")
            posting_references.append("eligibility:company")

        authorization_conflict = _authorization_conflict(job, preferences, profile)
        if authorization_conflict is True:
            reasons.append(EligibilityReasonCode.AUTHORIZATION_CONFLICT)
            explanations.append(
                "The posting's explicit authorization language conflicts with preferences."
            )
            posting_references.append("eligibility:authorization")
            conflict_references.append("eligibility:authorization")
        elif authorization_conflict is None:
            unknown = True
            unresolved_facts.append(
                "Authorization or sponsorship compatibility is not fully established."
            )
            posting_references.append("eligibility:authorization")

        credential_conflict, credential_posting_refs, credential_profile_refs = (
            _credential_conflicts(job, profile)
        )
        posting_references.extend(credential_posting_refs)
        profile_references.extend(credential_profile_refs)
        if credential_conflict is True:
            reasons.append(EligibilityReasonCode.AUTHORIZATION_CONFLICT)
            explanations.append(
                "A mandatory credential or citizenship requirement conflicts with the "
                "reviewed profile."
            )
            conflict_references.extend(credential_posting_refs)
        elif credential_conflict is None:
            unknown = True
            unresolved_facts.append("A mandatory credential or citizenship fact is unresolved.")

        degree_conflict = _degree_conflict(job, profile)
        if degree_conflict is True:
            reasons.append(EligibilityReasonCode.DEGREE_CONFLICT)
            explanations.append(
                "The explicit degree requirement conflicts with the reviewed profile."
            )
        elif degree_conflict is None:
            unknown = True
            unresolved_facts.append(
                "The profile does not establish the required degree or equivalent experience."
            )
            posting_references.append("eligibility:degree")

        graduation_conflict = _graduation_conflict(job, profile)
        if graduation_conflict is True:
            reasons.append(EligibilityReasonCode.GRADUATION_CONFLICT)
            explanations.append(
                "The explicit graduation-date requirement conflicts with the reviewed profile."
            )
        elif graduation_conflict is None:
            unknown = True
            unresolved_facts.append(
                "The graduation-date requirement cannot be resolved from reviewed profile dates."
            )
            posting_references.append("eligibility:graduation")

        if preferences.job_levels and job.requirements.job_level is not JobLevel.UNKNOWN:
            if job.requirements.job_level not in preferences.job_levels:
                reasons.append(EligibilityReasonCode.JOB_LEVEL_MISMATCH)
                explanations.append("The posting level is outside the selected job levels.")
                posting_references.append("eligibility:level")
                conflict_references.append("eligibility:level")
        elif preferences.job_levels:
            unknown = True
            unresolved_facts.append("The posting does not state a job level.")
            posting_references.append("eligibility:level")

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
            posting_references.append("eligibility:experience")
            conflict_references.append("eligibility:experience")

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
            posting_references=sorted(set(posting_references)),
            profile_references=sorted(set(profile_references)),
            conflict_references=sorted(set(conflict_references)),
            unresolved_facts=sorted(set(unresolved_facts)),
        )


def assess_eligibility(
    job: DiscoveredJob,
    preferences: JobSearchPreferences,
    *,
    as_of: datetime,
) -> EligibilityAssessment:
    return EligibilityEvaluator().assess(job, preferences, as_of=as_of)
