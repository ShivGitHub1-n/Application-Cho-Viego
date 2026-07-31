from __future__ import annotations

from resume_tailor.infrastructure.job_sources.detection import detect_source_strategy


def test_detects_provider_and_known_unsupported_platforms() -> None:
    assert detect_source_strategy(
        "https://job-boards.greenhouse.io/acme", "", approved_hosts={"job-boards.greenhouse.io"}
    ).kind == "greenhouse"
    assert detect_source_strategy(
        "https://jobs.lever.co/acme", "", approved_hosts={"jobs.lever.co"}
    ).kind == "lever"
    assert (
        detect_source_strategy(
            "https://acme.wd5.myworkdayjobs.com/en-US/jobs",
            "",
            approved_hosts={"acme.wd5.myworkdayjobs.com"},
        ).kind
        == "workday"
    )
    assert detect_source_strategy(
        "https://careers.example.com/jobs", "", approved_hosts={"careers.example.com"}
    ).kind == "unknown"


def test_detects_jobposting_jsonld_without_authorizing_a_provider() -> None:
    html = '<script type="application/ld+json">{"@type":"JobPosting","title":"Engineer"}</script>'
    result = detect_source_strategy(
        "https://careers.example.com/jobs/1", html, approved_hosts={"careers.example.com"}
    )
    assert result.kind == "first_party_jobposting"
    assert result.authorizes_provider is False


def test_detection_rejects_deceptive_and_unapproved_provider_signals() -> None:
    result = detect_source_strategy(
        "https://careers.example.com/jobs",
        '<a href="https://greenhouse.io.evil/jobs">Greenhouse</a>',
        approved_hosts={"careers.example.com"},
        approved_redirect_hosts={"job-boards.greenhouse.io"},
    )
    assert result.kind == "unknown"
    assert result.deferred is True


def test_detection_defers_conflicting_provider_signals() -> None:
    result = detect_source_strategy(
        "https://careers.example.com/jobs",
        '<a href="https://job-boards.greenhouse.io/acme">x</a>'
        '<a href="https://jobs.lever.co/acme">y</a>',
        approved_hosts={"careers.example.com"},
        approved_redirect_hosts={"job-boards.greenhouse.io", "jobs.lever.co"},
    )
    assert result.kind == "conflicting_provider_signals"
    assert result.deferred is True
