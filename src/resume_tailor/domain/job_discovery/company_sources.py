from __future__ import annotations

import posixpath
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Literal
from urllib.parse import unquote, urlsplit

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator

from resume_tailor.domain.job_discovery.hostnames import (
    HostnameValidationError,
    normalize_hostname,
)


class SourceMechanism(StrEnum):
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    FIRST_PARTY = "first_party"
    DEFERRED = "deferred"


class ListingDiscoveryMode(StrEnum):
    PROVIDER = "provider"
    SITEMAP = "sitemap"
    STATIC_INDEX = "static_index"
    BROWSER_INDEX = "browser_index"
    DIRECT_DETAIL_URLS = "direct_detail_urls"


class PageFetchMode(StrEnum):
    STATIC_HTTP = "static_http"
    BROWSER = "browser"


class DetailExtractionMode(StrEnum):
    JSON_LD_THEN_HTML = "json_ld_then_html"
    JSON_LD_ONLY = "json_ld_only"
    DETERMINISTIC_HTML = "deterministic_html"


class BrowserActionSpec(BaseModel):
    """A bounded, declarative action permitted by an audited browser plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action_type: Literal["wait_for_selector", "click", "load_more"]
    selector: str = Field(min_length=1, max_length=256)
    max_attempts: int = Field(default=1, ge=1, le=10)
    timeout_ms: int = Field(default=5_000, ge=100, le=30_000)

    @field_validator("selector")
    @classmethod
    def validate_selector(cls, value: str) -> str:
        if any(ord(char) < 32 for char in value) or "javascript:" in value.casefold():
            raise ValueError("browser selectors must be bounded and declarative")
        return value


class SourceAuditState(StrEnum):
    APPROVED = "approved"
    DEFERRED = "deferred"
    STALE = "stale"
    REJECTED = "rejected"


@dataclass(frozen=True)
class SourceAuditFreshnessResult:
    source_id: str
    eligible: bool
    stale: bool
    reason: str


@dataclass(frozen=True)
class SourceAuditFreshnessPolicy:
    max_age_days: int = 180

    def __post_init__(self) -> None:
        if self.max_age_days < 0:
            raise ValueError("audit freshness window must be non-negative")

    def evaluate(
        self, source: CompanyCareerSource, *, reference_date: date
    ) -> SourceAuditFreshnessResult:
        audit_date = source.source_plan.audit_date
        if audit_date is None:
            return SourceAuditFreshnessResult(
                source.source_id,
                eligible=False,
                stale=True,
                reason="audit date is absent",
            )
        if audit_date > reference_date:
            return SourceAuditFreshnessResult(
                source.source_id, eligible=False, stale=True, reason="audit date is in the future"
            )
        age = (reference_date - audit_date).days
        stale = age > self.max_age_days
        return SourceAuditFreshnessResult(
            source.source_id,
            eligible=not stale and source.audit_state is SourceAuditState.APPROVED,
            stale=stale,
            reason="audit is fresh" if not stale else "audit is stale",
        )


class RobotsPolicy(StrEnum):
    ALLOW = "allow"
    DISALLOW = "disallow"
    DEFER = "defer"
    UNKNOWN = "unknown"


class GeographicEvidenceKind(StrEnum):
    OFFICIAL_OFFICE = "official_office"
    OFFICIAL_HIRING_PRESENCE = "official_hiring_presence"
    OFFICIAL_JOB_LOCATION = "official_job_location"
    REMOTE_ELIGIBILITY = "remote_eligibility"
    OTHER = "other"


class GeographicEvidenceReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(min_length=1, max_length=120)
    kind: GeographicEvidenceKind
    country_code: str = Field(min_length=2, max_length=2)
    region: str | None = Field(default=None, max_length=120)
    locality: str | None = Field(default=None, max_length=120)
    source_reference: str = Field(min_length=1, max_length=500)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("country_code")
    @classmethod
    def normalize_evidence_country(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{2}", normalized):
            raise ValueError("evidence country code must be a two-letter ISO code")
        return normalized

    @field_validator("source_reference")
    @classmethod
    def validate_source_reference(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or any(ord(char) < 32 for char in normalized):
            raise ValueError("evidence source reference must be non-empty and printable")
        parsed = urlsplit(normalized)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("evidence source reference must be an HTTPS URL")
        return normalized


_GTA_LOCALITIES = frozenset(
    {
        "toronto",
        "north york",
        "scarborough",
        "etobicoke",
        "markham",
        "richmond hill",
        "vaughan",
        "mississauga",
        "brampton",
        "oakville",
        "burlington",
        "aurora",
        "oshawa",
    }
)


def normalize_geographic_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not normalized or any(ord(char) < 32 for char in normalized):
        raise ValueError("geographic labels must be non-empty and printable")
    normalized = " ".join(normalized.casefold().split())
    normalized = normalized.rstrip(".,;:")
    normalized = normalized.rstrip()
    if not normalized:
        raise ValueError("geographic labels must contain identity characters")
    return normalized


class GeographicCoverage(BaseModel):
    """Audited geography metadata; it does not participate in fit scoring."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    country_codes: list[str] = Field(default_factory=lambda: ["US"])
    regions: list[str] = Field(default_factory=lambda: ["north america"])
    localities: list[str] = Field(default_factory=list)
    toronto_gta_presence: bool = False
    geographic_evidence: list[GeographicEvidenceReference] = Field(default_factory=list)
    target_user_relevance: Literal["toronto_gta", "global", "other"] = "global"

    @field_validator("country_codes")
    @classmethod
    def normalize_country_codes(cls, values: list[str]) -> list[str]:
        normalized = sorted({value.strip().upper() for value in values})
        if not normalized or any(not re.fullmatch(r"[A-Z]{2}", value) for value in normalized):
            raise ValueError("country codes must be normalized two-letter ISO codes")
        return normalized

    @field_validator("regions", "localities")
    @classmethod
    def normalize_geographic_labels(cls, values: list[str]) -> list[str]:
        try:
            return sorted({normalize_geographic_label(value) for value in values})
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

    @model_validator(mode="after")
    def validate_toronto_evidence(self) -> GeographicCoverage:
        if self.toronto_gta_presence:
            qualifying = {
                GeographicEvidenceKind.OFFICIAL_OFFICE,
                GeographicEvidenceKind.OFFICIAL_HIRING_PRESENCE,
                GeographicEvidenceKind.OFFICIAL_JOB_LOCATION,
            }
            if not any(
                evidence.kind in qualifying
                and evidence.country_code == "CA"
                and evidence.locality is not None
                and normalize_geographic_label(evidence.locality) in _GTA_LOCALITIES
                for evidence in self.geographic_evidence
            ):
                raise ValueError(
                    "Toronto/GTA presence requires qualifying official Canadian GTA evidence"
                )
        return self


class ProviderConnectorConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_type: Literal["greenhouse", "lever"]
    board_token: str
    lever_api_region: Literal["global", "eu"] | None = None

    @field_validator("board_token")
    @classmethod
    def validate_board_token(cls, value: str) -> str:
        if not value or any(char.isspace() for char in value) or "/" in value or "\\" in value:
            raise ValueError("provider board token must be an exact opaque token")
        return value

    @model_validator(mode="after")
    def validate_region(self) -> ProviderConnectorConfiguration:
        if self.connector_type == "lever" and self.lever_api_region is None:
            raise ValueError("Lever requires an explicit API region")
        if self.connector_type == "greenhouse" and self.lever_api_region is not None:
            raise ValueError("Greenhouse cannot specify a Lever API region")
        return self


class AuditedHostRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    host: str
    allowed_path_patterns: list[str] = Field(min_length=1)
    audit_reason: str = Field(min_length=1)

    @field_validator("host")
    @classmethod
    def normalize_host(cls, value: str) -> str:
        try:
            return normalize_hostname(value)
        except HostnameValidationError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("allowed_path_patterns")
    @classmethod
    def validate_paths(cls, patterns: list[str]) -> list[str]:
        _validate_path_patterns(patterns)
        return sorted(set(patterns))


class FirstPartyAuditEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    canonical_employer_url: AnyHttpUrl
    listing_index_urls: list[AnyHttpUrl] = Field(min_length=1)
    navigation_hosts: list[str] = Field(min_length=1)
    redirect_hosts: list[str] = Field(default_factory=list)
    allowed_listing_path_patterns: list[str] = Field(min_length=1)
    allowed_detail_path_patterns: list[str] = Field(min_length=1)
    robots_decision: Literal["allow", "defer", "disallow"]
    listing_discovery_mode: ListingDiscoveryMode
    detail_fetch_mode: PageFetchMode
    detail_extraction_mode: DetailExtractionMode
    stable_identity_authority: str = Field(min_length=1)
    canonical_detail_url_authority: str = Field(min_length=1)
    application_url_authority: str = Field(min_length=1)
    application_hosts: list[AuditedHostRule] = Field(min_length=1)
    completeness_boundary: str = Field(min_length=1)
    data_authority: Literal["employer_host", "approved_provider", "unaudited_api"]
    competing_provider_authority: bool
    fixture_index_path: str = Field(min_length=1)
    fixture_detail_path: str = Field(min_length=1)
    audit_version: str = Field(min_length=1)
    audit_date: date

    @field_validator("navigation_hosts", "redirect_hosts")
    @classmethod
    def normalize_hosts(cls, hosts: list[str]) -> list[str]:
        try:
            return sorted({normalize_hostname(host) for host in hosts})
        except HostnameValidationError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("canonical_employer_url", mode="before")
    @classmethod
    def validate_canonical_url(cls, value: object) -> object:
        if isinstance(value, str):
            parsed = urlsplit(value)
            if parsed.scheme != "https" or parsed.username or parsed.password or parsed.fragment:
                raise ValueError("audit URLs must be credential-free HTTPS URLs without fragments")
            if parsed.port not in (None, 443):
                raise ValueError("audit URLs may only use HTTPS port 443")
        return value

    @field_validator("fixture_index_path", "fixture_detail_path")
    @classmethod
    def validate_fixture_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or ".." in path.parts
            or "\\" in value
            or re.match(r"^[A-Za-z]:", value)
        ):
            raise ValueError("audit fixture paths must be safe repository-relative paths")
        return value

    @field_validator("allowed_listing_path_patterns", "allowed_detail_path_patterns")
    @classmethod
    def validate_patterns(cls, patterns: list[str]) -> list[str]:
        _validate_path_patterns(patterns)
        return patterns

    @model_validator(mode="after")
    def validate_authority(self) -> FirstPartyAuditEvidence:
        if self.data_authority != "employer_host" or self.competing_provider_authority:
            raise ValueError("enabled first-party evidence must be employer-host and uncontested")
        if self.robots_decision != "allow":
            raise ValueError("enabled first-party evidence requires an allow robots decision")
        if self.listing_discovery_mode is ListingDiscoveryMode.PROVIDER:
            raise ValueError("first-party evidence cannot use provider discovery")
        application_hosts = [rule.host for rule in self.application_hosts]
        if len(application_hosts) != len(set(application_hosts)):
            raise ValueError("application hosts must be unique after normalization")
        for url in (self.canonical_employer_url, *self.listing_index_urls):
            parsed = urlsplit(str(url))
            if (
                parsed.scheme != "https"
                or parsed.username
                or parsed.password
                or parsed.fragment
                or parsed.port not in (None, 443)
            ):
                raise ValueError("audit URLs must be credential-free HTTPS URLs on port 443")
        return self

    def is_application_url_allowed(self, url: str) -> bool:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.username
            or parsed.password
            or parsed.fragment
            or parsed.port not in (None, 443)
        ):
            return False
        try:
            host = normalize_hostname(parsed.hostname or "")
        except HostnameValidationError:
            return False
        path = parsed.path or "/"
        if (
            any(ord(char) < 32 for char in path)
            or "\\" in path
            or re.search(r"%(?:2f|2F|5c|5C|2e|2E)", path)
        ):
            return False
        for rule in self.application_hosts:
            if rule.host == host and any(
                re.search(pattern, path) is not None for pattern in rule.allowed_path_patterns
            ):
                return True
        return False


class ExtractionProfileSpec(BaseModel):
    """Declarative future extraction hints; no executable registry content."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: str
    allowed_link_path_patterns: list[str] = Field(default_factory=list)
    job_card_attributes: dict[str, str] = Field(default_factory=dict)
    stable_id_attributes: list[str] = Field(default_factory=list)
    title_selectors: list[str] = Field(default_factory=list)
    detail_container_selectors: list[str] = Field(default_factory=list)
    labeled_field_mappings: dict[str, str] = Field(default_factory=dict)
    pagination_link_patterns: list[str] = Field(default_factory=list)
    canonical_url_policy: str = "canonical_then_source"

    @field_validator(
        "allowed_link_path_patterns",
        "stable_id_attributes",
        "title_selectors",
        "detail_container_selectors",
        "pagination_link_patterns",
    )
    @classmethod
    def reject_executable_hints(cls, values: list[str]) -> list[str]:
        forbidden = ("import ", "__", "javascript:", "file:", "eval(")
        if any(any(token in value.lower() for token in forbidden) for value in values):
            raise ValueError("extraction hints must be declarative")
        return values


class AuditedSourcePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mechanism: SourceMechanism
    listing_discovery_mode: ListingDiscoveryMode | None
    detail_fetch_mode: PageFetchMode | None
    detail_extraction_mode: DetailExtractionMode | None
    provider_configuration: ProviderConnectorConfiguration | None = None
    provider_source_id: None = None
    sitemap_urls: list[AnyHttpUrl] = Field(default_factory=list)
    sitemap_path_patterns: list[str] = Field(default_factory=list)
    index_urls: list[AnyHttpUrl] = Field(default_factory=list)
    direct_detail_urls: list[AnyHttpUrl] = Field(default_factory=list)
    allowed_job_path_patterns: list[str] = Field(default_factory=list)
    navigation_hosts: list[str] = Field(default_factory=list)
    redirect_hosts: list[str] = Field(default_factory=list)
    browser_resource_hosts: list[str] = Field(default_factory=list)
    browser_api_hosts: list[str] = Field(default_factory=list)
    browser_actions: list[BrowserActionSpec] = Field(default_factory=list, max_length=32)
    max_listing_pages: int = 0
    max_browser_listing_pages: int = 0
    max_browser_actions: int = 0
    max_job_detail_pages: int = 0
    max_network_requests: int = 0
    max_total_render_seconds: int = 0
    audit_version: str = Field(min_length=1)
    audit_date: date | None

    @field_validator(
        "navigation_hosts",
        "redirect_hosts",
        "browser_resource_hosts",
        "browser_api_hosts",
    )
    @classmethod
    def validate_hosts(cls, hosts: list[str]) -> list[str]:
        try:
            return sorted({normalize_hostname(host) for host in hosts})
        except HostnameValidationError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator(
        "max_listing_pages",
        "max_browser_listing_pages",
        "max_browser_actions",
        "max_job_detail_pages",
        "max_network_requests",
        "max_total_render_seconds",
    )
    @classmethod
    def validate_limits(cls, value: int) -> int:
        if value < 0 or value > 10_000:
            raise ValueError("source limits must be bounded between 0 and 10000")
        return value

    @field_validator("allowed_job_path_patterns")
    @classmethod
    def validate_allowed_paths(cls, patterns: list[str]) -> list[str]:
        _validate_path_patterns(patterns)
        return patterns

    @field_validator("sitemap_path_patterns")
    @classmethod
    def validate_sitemap_paths(cls, patterns: list[str]) -> list[str]:
        _validate_path_patterns(patterns)
        return patterns

    @model_validator(mode="after")
    def validate_combination(self) -> AuditedSourcePlan:
        if self.mechanism in {SourceMechanism.GREENHOUSE, SourceMechanism.LEVER}:
            if (
                not self.provider_configuration
                or self.listing_discovery_mode is not ListingDiscoveryMode.PROVIDER
            ):
                raise ValueError("provider plans require provider identity and provider discovery")
            if self.provider_configuration.connector_type != self.mechanism.value:
                raise ValueError("provider mechanism and connector type must agree")
            if self.detail_fetch_mode is not None or self.detail_extraction_mode is not None:
                raise ValueError("provider plans cannot configure first-party detail extraction")
            if self.max_listing_pages < 1:
                raise ValueError("provider plans require a positive listing-page bound")
        elif self.mechanism is SourceMechanism.FIRST_PARTY:
            if self.provider_configuration is not None:
                raise ValueError("first-party plans cannot configure a provider")
            if (
                not self.listing_discovery_mode
                or self.listing_discovery_mode is ListingDiscoveryMode.PROVIDER
            ):
                raise ValueError("first-party plans require non-provider listing discovery")
            if not self.detail_fetch_mode or not self.detail_extraction_mode:
                raise ValueError("first-party plans require detail fetch and extraction modes")
            if self.max_listing_pages < 1 or self.max_job_detail_pages < 1:
                raise ValueError("first-party plans require positive retrieval bounds")
        else:
            if self.provider_configuration is not None:
                raise ValueError("deferred plans cannot configure a provider")
            if any(
                value is not None
                for value in (
                    self.listing_discovery_mode,
                    self.detail_fetch_mode,
                    self.detail_extraction_mode,
                )
            ):
                raise ValueError("deferred plans cannot configure execution modes")
        if self.detail_fetch_mode is PageFetchMode.BROWSER:
            if not self.browser_resource_hosts and not self.browser_api_hosts:
                raise ValueError("browser plans require audited resource or API hosts")
            if self.max_browser_actions < 1 or self.max_total_render_seconds < 1:
                raise ValueError("browser plans require positive browser limits")
        if self.listing_discovery_mode is ListingDiscoveryMode.SITEMAP and not self.sitemap_urls:
            raise ValueError("sitemap discovery requires sitemap URLs")
        if self.sitemap_urls and not self.sitemap_path_patterns:
            raise ValueError("sitemap URLs require explicit sitemap path patterns")
        if (
            self.listing_discovery_mode
            in {
                ListingDiscoveryMode.STATIC_INDEX,
                ListingDiscoveryMode.BROWSER_INDEX,
            }
            and not self.index_urls
        ):
            raise ValueError("index discovery requires index URLs")
        if (
            self.listing_discovery_mode is ListingDiscoveryMode.DIRECT_DETAIL_URLS
            and not self.direct_detail_urls
        ):
            raise ValueError("direct-detail discovery requires direct URLs")
        for url in (*self.sitemap_urls, *self.index_urls, *self.direct_detail_urls):
            parsed = urlsplit(str(url))
            if parsed.scheme != "https" or parsed.username or parsed.password or parsed.fragment:
                raise ValueError("source-plan URLs must be credential-free HTTPS URLs")
            if parsed.port not in (None, 443):
                raise ValueError("source-plan URLs may only use HTTPS port 443")
        return self


class CompanyCareerSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    company_id: str
    canonical_company_name: str
    canonical_domain: str
    careers_entry_url: AnyHttpUrl
    allowed_hosts: list[str]
    redirect_hosts: list[str] = Field(default_factory=list)
    industry_tags: list[str] = Field(default_factory=list)
    role_family_tags: list[str] = Field(default_factory=list)
    geographic_coverage: GeographicCoverage = Field(default_factory=GeographicCoverage)
    priority_tier: int
    enabled: bool
    audit_state: SourceAuditState
    crawl_cadence_minutes: int
    robots_policy: RobotsPolicy
    browser_rendering_allowed: bool
    source_plan: AuditedSourcePlan
    first_party_audit: FirstPartyAuditEvidence | None = None
    extraction_profile: ExtractionProfileSpec | None = None
    audit_fixture_paths: list[str] = Field(default_factory=list)
    audit_evidence_urls: list[AnyHttpUrl] = Field(default_factory=list)
    provenance_notes: str = ""

    @property
    def deterministic_source_priority(self) -> tuple[int, int, str]:
        """Return metadata ordering: tier, GTA relevance, then source ID.

        This value is not an evaluator score, eligibility decision, feed order,
        or scheduling implementation.
        """
        return (
            self.priority_tier,
            0 if self.geographic_coverage.toronto_gta_presence else 1,
            self.source_id,
        )

    @field_validator("canonical_domain", "allowed_hosts", "redirect_hosts")
    @classmethod
    def validate_domain_values(cls, value: str | list[str]) -> str | list[str]:
        values = [value] if isinstance(value, str) else value
        try:
            normalized = [normalize_hostname(host) for host in values]
        except HostnameValidationError as exc:
            raise ValueError(str(exc)) from exc
        return normalized[0] if isinstance(value, str) else sorted(set(normalized))

    @field_validator("priority_tier", "crawl_cadence_minutes")
    @classmethod
    def validate_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("value must be positive")
        return value

    @field_validator("audit_fixture_paths")
    @classmethod
    def validate_audit_fixture_paths(cls, paths: list[str]) -> list[str]:
        for path in paths:
            if (
                not path
                or "\\" in path
                or PurePosixPath(path).is_absolute()
                or ".." in PurePosixPath(path).parts
                or re.match(r"^[A-Za-z]:", path)
            ):
                raise ValueError("audit fixture paths must be safe repository-relative paths")
        return sorted(set(paths))

    @field_validator("crawl_cadence_minutes")
    @classmethod
    def validate_cadence(cls, value: int) -> int:
        if value > 10_080:
            raise ValueError("crawl cadence must be no more than seven days")
        return value

    @model_validator(mode="after")
    def validate_source(self) -> CompanyCareerSource:
        entry = urlsplit(str(self.careers_entry_url))
        if (
            entry.scheme != "https"
            or entry.username
            or entry.password
            or entry.fragment
            or entry.port not in (None, 443)
        ):
            raise ValueError("careers entry must be a credential-free HTTPS URL on port 443")
        try:
            entry_host = normalize_hostname(entry.hostname or "")
        except HostnameValidationError as exc:
            raise ValueError(str(exc)) from exc
        if entry_host not in set(self.allowed_hosts):
            raise ValueError("careers entry must be HTTPS and use an allowed host")
        if not set(self.source_plan.navigation_hosts).issubset(self.allowed_hosts):
            raise ValueError("source-plan navigation hosts must be approved company hosts")
        if not set(self.source_plan.redirect_hosts).issubset(self.redirect_hosts):
            raise ValueError("source-plan redirect hosts must be approved redirect hosts")
        browser_hosts = set(self.source_plan.browser_resource_hosts) | set(
            self.source_plan.browser_api_hosts
        )
        if not browser_hosts.issubset(
            set(self.allowed_hosts)
            | set(self.redirect_hosts)
            | set(self.source_plan.redirect_hosts)
        ):
            raise ValueError("browser resource hosts require explicit company or redirect approval")
        if self.source_plan.mechanism is SourceMechanism.DEFERRED and self.enabled:
            raise ValueError("deferred sources cannot be enabled")
        if self.enabled and self.audit_state is not SourceAuditState.APPROVED:
            raise ValueError("only approved sources can be enabled")
        if self.enabled and self.source_plan.audit_date is None:
            raise ValueError("enabled sources require an audit date")
        if (
            self.enabled
            and self.source_plan.mechanism
            in {
                SourceMechanism.GREENHOUSE,
                SourceMechanism.LEVER,
            }
            and self.source_plan.provider_configuration is None
        ):
            raise ValueError("enabled provider sources require typed provider configuration")
        if self.enabled and self.source_plan.mechanism is SourceMechanism.FIRST_PARTY:
            if self.first_party_audit is None:
                raise ValueError("enabled first-party sources require complete audit evidence")
            if self.first_party_audit.audit_version != self.source_plan.audit_version:
                raise ValueError("first-party audit and source plan versions must match")
            if (
                self.source_plan.audit_date is None
                or self.first_party_audit.audit_date != self.source_plan.audit_date
            ):
                raise ValueError("first-party audit and source plan dates must match")
            audit = self.first_party_audit
            approved_hosts = set(self.allowed_hosts) | set(self.redirect_hosts)
            audit_url_hosts = {
                normalize_hostname(urlsplit(str(url)).hostname or "")
                for url in (audit.canonical_employer_url, *audit.listing_index_urls)
            }
            if not audit_url_hosts.issubset(approved_hosts):
                raise ValueError("first-party audit URLs must use approved hosts")
            if not set(audit.navigation_hosts).issubset(set(self.source_plan.navigation_hosts)):
                raise ValueError("first-party audit navigation hosts must be in the source plan")
            if not set(audit.redirect_hosts).issubset(set(self.source_plan.redirect_hosts)):
                raise ValueError("first-party audit redirect hosts must be in the source plan")
            if (
                audit.listing_discovery_mode is not self.source_plan.listing_discovery_mode
                or audit.detail_fetch_mode is not self.source_plan.detail_fetch_mode
                or audit.detail_extraction_mode is not self.source_plan.detail_extraction_mode
            ):
                raise ValueError("first-party audit modes must match the source plan")
        _validate_source_plan_urls(self)
        for url in self.audit_evidence_urls:
            parsed = urlsplit(str(url))
            if (
                parsed.scheme != "https"
                or parsed.username
                or parsed.password
                or parsed.fragment
                or parsed.port not in (None, 443)
            ):
                raise ValueError(
                    "audit evidence URLs must be credential-free HTTPS URLs on port 443"
                )
        if (
            self.source_plan.mechanism is SourceMechanism.FIRST_PARTY
            and not self.extraction_profile
        ):
            # The default JSON-LD path has no company-specific executable hints.
            if self.source_plan.detail_extraction_mode is DetailExtractionMode.DETERMINISTIC_HTML:
                raise ValueError("deterministic HTML plans require an extraction profile")
        if (
            self.source_plan.mechanism is SourceMechanism.FIRST_PARTY
            and self.browser_rendering_allowed
        ):
            if self.source_plan.detail_fetch_mode is not PageFetchMode.BROWSER:
                raise ValueError("browser permission must agree with browser detail fetch")
        return self


def _validate_path_patterns(patterns: list[str]) -> None:
    for pattern in patterns:
        lowered = pattern.lower()
        path_expression = pattern[1:] if pattern.startswith("^") else pattern
        if (
            not path_expression.startswith("/")
            or len(pattern) > 256
            or any(ord(char) < 32 for char in pattern)
            or "\\" in pattern
            or "%2f" in lowered
            or "%5c" in lowered
            or "%2e" in lowered
            or "/../" in unquote(pattern).replace("//", "/")
            or "(?=" in pattern
            or "(?<=" in pattern
            or "(?!" in pattern
            or "(?<!" in pattern
            or re.search(r"\((?!\?:)[^)]*[+*][^)]*\)[+*?]", pattern) is not None
        ):
            raise ValueError("path patterns contain an unsafe or ambiguous expression")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError("path pattern is malformed") from exc


def _validate_source_plan_urls(source: CompanyCareerSource) -> None:
    plan = source.source_plan
    if not (plan.sitemap_urls or plan.index_urls or plan.direct_detail_urls):
        return
    navigation_hosts = set(plan.navigation_hosts)
    audit = source.first_party_audit
    listing_patterns = (
        audit.allowed_listing_path_patterns if audit is not None else plan.allowed_job_path_patterns
    )
    detail_patterns = (
        audit.allowed_detail_path_patterns if audit is not None else plan.allowed_job_path_patterns
    )
    for urls, patterns, label in (
        (plan.sitemap_urls, plan.sitemap_path_patterns, "sitemap"),
        (plan.index_urls, listing_patterns, "index"),
        (plan.direct_detail_urls, detail_patterns, "detail"),
    ):
        for url in urls:
            parsed = urlsplit(str(url))
            try:
                host = normalize_hostname(parsed.hostname or "")
            except HostnameValidationError as exc:
                raise ValueError(f"{label} URL host is invalid") from exc
            if host not in navigation_hosts:
                raise ValueError(f"{label} URLs must use an approved navigation host")
            path = _normalized_audited_path(parsed.path or "/")
            if not patterns or not any(re.search(pattern, path) for pattern in patterns):
                raise ValueError(f"{label} URL path is not approved")


def _normalized_audited_path(path: str) -> str:
    if (
        not path
        or any(ord(char) < 32 for char in path)
        or "\\" in path
        or re.search(r"%(?:2f|2F|5c|5C|2e|2E)", path)
    ):
        raise ValueError("path contains an encoded or ambiguous separator")
    try:
        decoded = unquote(path, errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("path encoding is invalid") from exc
    if any(part in {".", ".."} for part in decoded.split("/")):
        raise ValueError("path traversal is not permitted")
    normalized = posixpath.normpath(decoded)
    if decoded.endswith("/") and normalized != "/":
        normalized += "/"
    if normalized != decoded or not normalized.startswith("/"):
        raise ValueError("path normalization would change the request")
    return normalized


__all__ = [
    "AuditedSourcePlan",
    "AuditedHostRule",
    "BrowserActionSpec",
    "CompanyCareerSource",
    "DetailExtractionMode",
    "ExtractionProfileSpec",
    "FirstPartyAuditEvidence",
    "GeographicCoverage",
    "GeographicEvidenceKind",
    "GeographicEvidenceReference",
    "ListingDiscoveryMode",
    "PageFetchMode",
    "ProviderConnectorConfiguration",
    "RobotsPolicy",
    "SourceAuditState",
    "SourceAuditFreshnessPolicy",
    "SourceAuditFreshnessResult",
    "SourceMechanism",
]
