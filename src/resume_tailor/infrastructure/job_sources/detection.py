from __future__ import annotations

import re
from urllib.parse import urlsplit

from pydantic import BaseModel

from resume_tailor.domain.job_discovery.hostnames import (
    HostnameValidationError,
    hostname_is_same_or_subdomain,
    normalize_hostname,
)


class DetectedSourceStrategy(BaseModel):
    kind: str
    evidence: tuple[str, ...] = ()
    authorizes_provider: bool = False
    deferred: bool = False


_KNOWN = {
    "workday.com": "workday",
    "myworkdayjobs.com": "workday",
    "icims.com": "icims",
    "smartrecruiters.com": "smartrecruiters",
    "ashbyhq.com": "ashby",
    "workable.com": "workable",
    "jobvite.com": "jobvite",
    "successfactors.com": "successfactors",
}
_URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)


def _normalized_approved(values: set[str]) -> set[str]:
    normalized: set[str] = set()
    for value in values:
        try:
            normalized.add(normalize_hostname(value))
        except HostnameValidationError:
            continue
    return normalized


def _host(url: str) -> str | None:
    try:
        value = urlsplit(url).hostname
        return normalize_hostname(value) if value else None
    except (ValueError, HostnameValidationError):
        return None


def detect_source_strategy(
    url: str,
    html: str,
    *,
    approved_hosts: set[str],
    approved_redirect_hosts: set[str] | None = None,
) -> DetectedSourceStrategy:
    page_host = _host(url)
    allowed_hosts = _normalized_approved(approved_hosts)
    redirect_hosts = _normalized_approved(approved_redirect_hosts or set())
    if page_host is None or page_host not in allowed_hosts | redirect_hosts:
        return DetectedSourceStrategy(kind="unknown", deferred=True)

    evidence_hosts = {page_host}
    for candidate in _URL_PATTERN.findall(html):
        candidate_host = _host(candidate)
        if candidate_host is not None and candidate_host in allowed_hosts | redirect_hosts:
            evidence_hosts.add(candidate_host)

    provider_signals: set[str] = set()
    for evidence_host in evidence_hosts:
        if evidence_host in redirect_hosts | allowed_hosts:
            if hostname_is_same_or_subdomain(evidence_host, "greenhouse.io"):
                provider_signals.add("greenhouse")
            if hostname_is_same_or_subdomain(evidence_host, "lever.co"):
                provider_signals.add("lever")
    if len(provider_signals) > 1:
        return DetectedSourceStrategy(
            kind="conflicting_provider_signals",
            evidence=tuple(sorted(provider_signals)),
            deferred=True,
        )
    if provider_signals:
        return DetectedSourceStrategy(
            kind=next(iter(provider_signals)),
            evidence=tuple(
                sorted(
                    f"approved redirect host:{host}"
                    for host in evidence_hosts
                    if host in redirect_hosts
                )
            ),
        )

    unsupported = {
        kind
        for marker, kind in _KNOWN.items()
        if any(
            hostname_is_same_or_subdomain(evidence_host, marker)
            for evidence_host in evidence_hosts
        )
    }
    if unsupported:
        return DetectedSourceStrategy(
            kind=sorted(unsupported)[0], evidence=tuple(sorted(unsupported)), deferred=True
        )
    if re.search(r'"@type"\s*:\s*"?JobPosting', html, re.IGNORECASE):
        return DetectedSourceStrategy(
            kind="first_party_jobposting", evidence=(f"approved host:{page_host}",)
        )
    return DetectedSourceStrategy(kind="unknown", deferred=True)


__all__ = ["DetectedSourceStrategy", "detect_source_strategy"]
