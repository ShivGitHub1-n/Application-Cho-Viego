from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from resume_tailor.domain.job_discovery.ids import job_id
from resume_tailor.domain.job_discovery.location import parse_location
from resume_tailor.domain.job_discovery.models import (
    DiscoveredJob,
    SourceJobRecord,
    SupportedJobSource,
)
from resume_tailor.domain.job_discovery.requirements import RequirementExtractor
from resume_tailor.domain.job_discovery.role_signals import classify_role_signals

_SAFE_HTTPS_HOSTS = {
    "boards.greenhouse.io",
    "job-boards.greenhouse.io",
    "jobs.lever.co",
    "jobs.eu.lever.co",
}
_TRACKING_QUERY_PREFIXES = ("utm_",)
_TERM_ALIASES = {
    "js": "javascript",
    "ts": "typescript",
    "cpp": "c++",
    "c plus plus": "c++",
    "csharp": "c#",
    "c sharp": "c#",
    "postgres": "postgresql",
    "k8s": "kubernetes",
    "ros 2": "ros2",
    "ros2": "ros2",
    "ml": "machine learning",
    "ai": "artificial intelligence",
    "sr": "senior",
    "jr": "junior",
}


def _normalized_space(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return re.sub(r"\s+", " ", normalized).strip()


def normalize_job_term(value: str) -> str:
    value = _normalized_space(value).casefold()
    value = re.sub(r"[^\w+#]+", " ", value, flags=re.UNICODE)
    value = re.sub(r"\s+", " ", value).strip()
    for alias, canonical in sorted(_TERM_ALIASES.items(), key=lambda item: -len(item[0])):
        value = re.sub(rf"(?<!\w){re.escape(alias)}(?!\w)", canonical, value)
    return re.sub(r"\s+", " ", value).strip()


def _canonical_url(value: str, source: SupportedJobSource) -> str:
    parsed = urlsplit(_normalized_space(value))
    host = (parsed.hostname or "").casefold()
    scheme = parsed.scheme.casefold()
    source_host = urlsplit(str(source.official_base_url)).hostname or ""
    if scheme == "http" and (host in _SAFE_HTTPS_HOSTS or host == source_host.casefold()):
        scheme = "https"
    netloc = host
    if parsed.port is not None and parsed.port not in (80, 443):
        netloc = f"{host}:{parsed.port}"
    path = re.sub(r"/{2,}", "/", parsed.path).rstrip("/") or "/"
    query = urlencode(
        sorted(
            (key, val)
            for key, val in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.casefold().startswith(_TRACKING_QUERY_PREFIXES)
        )
    )
    return urlunsplit((scheme, netloc, path, query, ""))


def _description_hash(description: str) -> str:
    return hashlib.sha256(normalize_job_term(description).encode("utf-8")).hexdigest()


class JobNormalizer:
    def normalize(
        self,
        record: SourceJobRecord | DiscoveredJob,
        source: SupportedJobSource,
        *,
        fetched_at: datetime,
    ) -> DiscoveredJob:
        if isinstance(record, DiscoveredJob):
            return record.model_copy(deep=True)

        external_job_id = _normalized_space(record.external_job_id)
        title = _normalized_space(record.title)
        company_name = _normalized_space(record.company_name)
        description = _normalized_space(record.description)
        location = parse_location(record.location_raw)
        url = _canonical_url(str(record.official_url), source)
        requirement_signals = RequirementExtractor().extract(
            title,
            description,
            record.location_raw,
            record.work_arrangement,
        )
        role_classification = classify_role_signals(title, description)
        completeness: list[str] = []
        if not external_job_id:
            completeness.append("missing_external_job_id")
        if not title:
            completeness.append("missing_title")
        if not company_name:
            completeness.append("missing_company_name")
        if not description:
            completeness.append("missing_description")
        if not location.parseable:
            completeness.append("missing_or_unparseable_location")
        if not record.posted_at:
            completeness.append("missing_posted_at")
        return DiscoveredJob(
            id=job_id(source.connector_type.value, source.source_id, external_job_id),
            source=source.model_copy(deep=True),
            external_job_id=external_job_id,
            title=title,
            company_name=company_name,
            description=description,
            official_url=url,
            location=location,
            work_arrangement=record.work_arrangement,
            role_family=role_classification.primary_family,
            role_family_scores={
                family: role_classification.family_scores[family]
                for family in sorted(
                    role_classification.family_scores, key=lambda item: item.value
                )
            },
            requirements=requirement_signals,
            posted_at=record.posted_at,
            source_updated_at=record.source_updated_at,
            application_deadline=record.application_deadline,
            completeness=completeness,
            fetched_at=fetched_at,
        requisition_id=_requisition_id(record),
            normalized_title=normalize_job_term(title),
            normalized_company_name=normalize_job_term(company_name),
            canonical_description_hash=_description_hash(description),
        )


def _requisition_id(record: SourceJobRecord) -> str | None:
    value = record.source_payload.get("requisition_id")
    if value is None:
        return None
    cleaned = _normalized_space(str(value))
    return cleaned or None


def normalize_job_record(
    record: SourceJobRecord | DiscoveredJob,
    source: SupportedJobSource,
    *,
    fetched_at: datetime,
) -> DiscoveredJob:
    return JobNormalizer().normalize(record, source, fetched_at=fetched_at)
