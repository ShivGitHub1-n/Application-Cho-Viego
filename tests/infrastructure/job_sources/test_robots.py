from __future__ import annotations

from datetime import UTC, datetime, timedelta

from resume_tailor.infrastructure.job_sources.robots import (
    RobotsCacheEntry,
    RobotsDecision,
    evaluate_robots_response,
    parse_robots,
)


def test_rfc9309_longest_match_and_equal_allow_tie() -> None:
    policy = """User-agent: *
Disallow: /careers
Allow: /careers/public
Disallow: /careers/public/private
Allow: /careers/public/private
"""
    rules = parse_robots(policy)
    assert rules.decide("/careers") is RobotsDecision.DISALLOW
    assert rules.decide("/careers/public") is RobotsDecision.ALLOW
    assert rules.decide("/careers/public/private") is RobotsDecision.ALLOW


def test_exact_user_agent_group_precedes_wildcard() -> None:
    rules = parse_robots(
        """User-agent: *\nDisallow: /\n\nUser-agent: Cho-Viego\nAllow: /careers\n"""
    )
    assert rules.decide("/careers", user_agent="Cho-Viego") is RobotsDecision.ALLOW
    assert rules.decide("/other", user_agent="Cho-Viego") is RobotsDecision.ALLOW


def test_robots_status_policy_and_cache_expiry() -> None:
    assert evaluate_robots_response(404, None).decision is RobotsDecision.ALLOW
    assert evaluate_robots_response(403, None).decision is RobotsDecision.UNKNOWN
    assert evaluate_robots_response(503, None).decision is RobotsDecision.DISALLOW
    fetched = datetime(2026, 7, 24, tzinfo=UTC)
    cached = RobotsCacheEntry(fetched, parse_robots("User-agent: *\nAllow: /"))
    assert (
        evaluate_robots_response(
            503, None, cache=cached, now=fetched + timedelta(hours=23)
        ).decision
        is RobotsDecision.DISALLOW
    )
    assert (
        evaluate_robots_response(
            503, None, cache=cached, now=fetched + timedelta(hours=25)
        ).decision
        is RobotsDecision.DISALLOW
    )


def test_robots_fails_closed_for_malformed_and_rate_limited_responses() -> None:
    assert (
        evaluate_robots_response(429, "not a robots document").decision
        is RobotsDecision.DISALLOW
    )
    assert (
        evaluate_robots_response(200, "not a robots document").decision
        is RobotsDecision.DISALLOW
    )


def test_robots_terminal_wildcard_and_versioned_product_token() -> None:
    rules = parse_robots(
        "User-agent: Cho-Viego\nDisallow: /private*$\n"
        "\nUser-agent: *\nDisallow: /fallback\n"
    )
    assert rules.decide("/private/x", user_agent="Cho-Viego/1.0") is RobotsDecision.DISALLOW
    assert rules.decide("/fallback", user_agent="OtherBot/1.0") is RobotsDecision.DISALLOW
