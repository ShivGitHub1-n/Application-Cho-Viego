from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConditionalCacheMetadata:
    source_id: str
    audit_version: str
    registry_plan_hash: str
    extraction_profile_hash: str
    etag: str | None = None
    last_modified: str | None = None


@dataclass(frozen=True)
class ConditionalCacheDecision:
    use_conditional_request: bool
    reuse_membership_on_not_modified: bool
    reason: str


def decide_conditional_cache(
    previous: ConditionalCacheMetadata | None,
    *,
    source_id: str,
    audit_version: str,
    registry_plan_hash: str,
    extraction_profile_hash: str,
) -> ConditionalCacheDecision:
    if previous is None:
        return ConditionalCacheDecision(False, False, "no historical validator")
    matching_plan = (
        previous.source_id == source_id
        and
        previous.audit_version == audit_version
        and previous.registry_plan_hash == registry_plan_hash
        and previous.extraction_profile_hash == extraction_profile_hash
    )
    if not matching_plan:
        return ConditionalCacheDecision(False, False, "audit or plan identity changed")
    return ConditionalCacheDecision(True, True, "validated plan identity")


__all__ = [
    "ConditionalCacheDecision",
    "ConditionalCacheMetadata",
    "decide_conditional_cache",
]
