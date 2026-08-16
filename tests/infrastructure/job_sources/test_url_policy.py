from __future__ import annotations

import pytest

from resume_tailor.infrastructure.job_sources.safe_http import (
    BlockedDestinationError,
    UrlAccessPolicy,
)


def test_policy_rejects_private_and_ip_literal_hosts() -> None:
    policy = UrlAccessPolicy(allowed_hosts={"careers.example.com"})
    with pytest.raises(BlockedDestinationError):
        policy.validate("http://careers.example.com/jobs")
    with pytest.raises(BlockedDestinationError):
        policy.validate("https://127.0.0.1/jobs")


def test_policy_enforces_exact_hosts_and_paths() -> None:
    policy = UrlAccessPolicy(
        allowed_hosts={"careers.example.com"},
        allowed_path_patterns=(r"^/jobs(?:/[^/]+)?$",),
        resolver=lambda _: ["93.184.216.34"],
    )
    assert policy.validate("https://careers.example.com/jobs/one").host == "careers.example.com"
    with pytest.raises(BlockedDestinationError):
        policy.validate("https://other.example.com/jobs/one")
    with pytest.raises(BlockedDestinationError):
        policy.validate("https://careers.example.com/admin")


def test_mixed_dns_answers_fail_closed() -> None:
    policy = UrlAccessPolicy(
        allowed_hosts={"careers.example.com"},
        resolver=lambda _: ["203.0.113.10", "192.168.1.10"],
    )
    with pytest.raises(BlockedDestinationError):
        policy.validate("https://careers.example.com/jobs")


def test_policy_rejects_fragments_ports_and_encoded_path_traversal() -> None:
    policy = UrlAccessPolicy(
        allowed_hosts={"careers.example.com"},
        allowed_path_patterns=(r"^/jobs/[^/]+$",),
        resolver=lambda _: ["93.184.216.34"],
    )
    for url in (
        "https://careers.example.com:8443/jobs/one",
        "https://careers.example.com/jobs/one#fragment",
        "https://careers.example.com/jobs/%2e%2e/admin",
        "https://careers.example.com/jobs/%2fadmin",
        "https://evil-example.com/jobs/one",
    ):
        with pytest.raises(BlockedDestinationError):
            policy.validate(url)


def test_policy_accepts_one_trailing_slash_without_accepting_duplicate_slashes() -> None:
    policy = UrlAccessPolicy(
        allowed_hosts={"careers.example.com"},
        allowed_path_patterns=(r"^/careers/positions/?$",),
        resolver=lambda _: ["93.184.216.34"],
    )

    destination = policy.validate("https://careers.example.com/careers/positions/")

    assert destination.host == "careers.example.com"
    with pytest.raises(BlockedDestinationError):
        policy.validate("https://careers.example.com/careers//positions/")
