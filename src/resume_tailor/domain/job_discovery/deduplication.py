from __future__ import annotations

import hashlib
from collections import defaultdict

from resume_tailor.domain.job_discovery.models import (
    DeduplicationResult,
    DiscoveredJob,
    DuplicateGroup,
)
from resume_tailor.domain.job_discovery.normalization import normalize_job_term
from resume_tailor.domain.job_discovery.requirements import RequirementExtractor
from resume_tailor.domain.job_discovery.role_signals import classify_role_signals


def _location_key(job: DiscoveredJob) -> tuple[str | None, str | None, str | None]:
    location = job.location
    return location.city, location.region, location.country_code


def _identity_keys(job: DiscoveredJob) -> tuple[tuple[str, ...], ...]:
    keys: list[tuple[str, ...]] = []
    if job.external_job_id:
        keys.append(
            (
                "external",
                job.source.connector_type.value,
                job.external_job_id,
            )
        )
    if job.requisition_id and job.normalized_company_name:
        keys.append(("requisition", job.normalized_company_name, job.requisition_id.casefold()))
    if job.official_url:
        keys.append(("url", job.official_url))
    if job.canonical_description_hash:
        keys.append(
            (
                "fallback",
                job.normalized_company_name,
                job.normalized_title,
                *(value or "" for value in _location_key(job)),
                job.requisition_id.casefold() if job.requisition_id else "",
                job.canonical_description_hash,
            )
        )
    return tuple(keys)


def _canonical_sort_key(job: DiscoveredJob) -> tuple[object, ...]:
    confidence_rank = {"high": 0, "medium": 1, "low": 2}
    return (
        len(job.completeness),
        confidence_rank[job.verification_confidence.value],
        0 if job.description else 1,
        -len(job.description),
        job.source.connector_type.value,
        job.source.source_id,
        job.external_job_id,
        job.official_url,
    )


def _output_sort_key(job: DiscoveredJob) -> tuple[str, ...]:
    return (
        job.normalized_company_name,
        job.normalized_title,
        *(value or "" for value in _location_key(job)),
        job.id,
    )


def _identity_conflicts(left: DiscoveredJob, right: DiscoveredJob) -> bool:
    if (
        left.requisition_id
        and right.requisition_id
        and left.requisition_id.casefold() != right.requisition_id.casefold()
    ):
        return True
    if left.location.parseable and right.location.parseable:
        if _location_key(left) != _location_key(right):
            return True
    if left.description and right.description:
        if left.canonical_description_hash != right.canonical_description_hash:
            return True
    return False


def _refresh_derived(job: DiscoveredJob) -> DiscoveredJob:
    requirements = RequirementExtractor().extract(
        job.title,
        job.description,
        job.location.raw,
        job.work_arrangement,
    )
    role_classification = classify_role_signals(job.title, job.description)
    completeness = [
        warning
        for warning in job.completeness
        if warning
        not in {
            "missing_description",
            "missing_or_unparseable_location",
            "missing_posted_at",
        }
    ]
    if not job.description:
        completeness.append("missing_description")
    if not job.location.parseable:
        completeness.append("missing_or_unparseable_location")
    if job.posted_at is None:
        completeness.append("missing_posted_at")
    return job.model_copy(
        update={
            "requirements": requirements,
            "role_family": role_classification.primary_family,
            "role_family_scores": {
                family: role_classification.family_scores[family]
                for family in sorted(role_classification.family_scores, key=lambda item: item.value)
            },
            "canonical_description_hash": hashlib.sha256(
                normalize_job_term(job.description).encode("utf-8")
            ).hexdigest(),
            "completeness": sorted(set(completeness)),
        }
    )


class JobDeduplicator:
    def resolve(self, jobs: list[DiscoveredJob]) -> DeduplicationResult:
        parent = list(range(len(jobs)))

        def find(index: int) -> int:
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        def union(left: int, right: int) -> None:
            left_root, right_root = find(left), find(right)
            if left_root != right_root:
                parent[max(left_root, right_root)] = min(left_root, right_root)

        seen: dict[tuple[str, ...], int] = {}
        for index, job in enumerate(jobs):
            for key in _identity_keys(job):
                previous = seen.get(key)
                if previous is not None and not _identity_conflicts(job, jobs[previous]):
                    union(index, previous)
                else:
                    seen[key] = index

        grouped: defaultdict[int, list[DiscoveredJob]] = defaultdict(list)
        for index, job in enumerate(jobs):
            grouped[find(index)].append(job)

        groups: list[DuplicateGroup] = []
        for members in grouped.values():
            ordered = sorted(members, key=_canonical_sort_key)
            canonical = ordered[0]
            aliases = sorted(ordered[1:], key=_output_sort_key)
            if aliases:
                updates: dict[str, object] = {
                    "source_alias_ids": sorted(
                        {
                            *canonical.source_alias_ids,
                            *[alias.id for alias in aliases],
                        }
                    )
                }
                for field in (
                    "posted_at",
                    "source_updated_at",
                    "application_deadline",
                    "requisition_id",
                ):
                    if getattr(canonical, field) is None:
                        values = [getattr(alias, field) for alias in aliases]
                        first_value = next((value for value in values if value is not None), None)
                        if first_value is not None:
                            updates[field] = first_value
                if not canonical.location.parseable:
                    parsed_alias = next(
                        (alias.location for alias in aliases if alias.location.parseable), None
                    )
                    if parsed_alias is not None:
                        updates["location"] = parsed_alias
                if not canonical.description:
                    fuller_description = next(
                        (alias.description for alias in aliases if alias.description), None
                    )
                    if fuller_description is not None:
                        updates["description"] = fuller_description
                canonical = canonical.model_copy(
                    update=updates
                )
                canonical = _refresh_derived(canonical)
                groups.append(DuplicateGroup(canonical=canonical, aliases=aliases))
            else:
                groups.append(DuplicateGroup(canonical=canonical, aliases=[]))

        groups.sort(key=lambda group: _output_sort_key(group.canonical))
        canonical_jobs = [group.canonical for group in groups]
        return DeduplicationResult(
            jobs=canonical_jobs,
            groups=groups,
            duplicate_count=sum(len(group.aliases) for group in groups),
        )


def deduplicate_jobs(jobs: list[DiscoveredJob]) -> DeduplicationResult:
    return JobDeduplicator().resolve(jobs)
