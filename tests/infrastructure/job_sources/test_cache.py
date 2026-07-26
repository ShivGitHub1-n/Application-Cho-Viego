from __future__ import annotations

from resume_tailor.infrastructure.job_sources.cache import (
    ConditionalCacheMetadata,
    decide_conditional_cache,
)


def test_304_reuse_requires_all_three_plan_identity_values() -> None:
    previous = ConditionalCacheMetadata("source-a", "a", "r", "e", etag="x")
    assert decide_conditional_cache(
        previous,
        source_id="source-a",
        audit_version="a",
        registry_plan_hash="r",
        extraction_profile_hash="e",
    ).reuse_membership_on_not_modified
    for field, value in (
        ("audit_version", "b"),
        ("registry_plan_hash", "x"),
        ("extraction_profile_hash", "x"),
    ):
        values = {
            "source_id": "source-a",
            "audit_version": "a",
            "registry_plan_hash": "r",
            "extraction_profile_hash": "e",
        }
        values[field] = value
        decision = decide_conditional_cache(previous, **values)
        assert decision.reuse_membership_on_not_modified is False


def test_304_reuse_requires_source_identity_and_plan_hash_ignores_audit_date() -> None:
    previous = ConditionalCacheMetadata("source-a", "a", "r", "e", etag="x")
    assert decide_conditional_cache(
        previous,
        source_id="source-a",
        audit_version="a",
        registry_plan_hash="r",
        extraction_profile_hash="e",
    ).reuse_membership_on_not_modified
    assert not decide_conditional_cache(
        previous,
        source_id="source-b",
        audit_version="a",
        registry_plan_hash="r",
        extraction_profile_hash="e",
    ).reuse_membership_on_not_modified
