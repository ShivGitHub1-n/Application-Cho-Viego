from __future__ import annotations

import hashlib
import json
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

from pydantic import ValidationError

from resume_tailor.domain.job_discovery.company_sources import (
    AuditedSourcePlan,
    CompanyCareerSource,
    ListingDiscoveryMode,
    ProviderConnectorConfiguration,
    RobotsPolicy,
    SourceAuditFreshnessPolicy,
    SourceAuditFreshnessResult,
    SourceAuditState,
    SourceMechanism,
)
from resume_tailor.domain.job_discovery.models import (
    ConnectorType,
    FirstPartySource,
    LeverApiRegion,
    SupportedJobSource,
)

_AUDIT_FIXTURE_MAX_BYTES = 1_000_000


def _default_audit_fixture_root() -> Path:
    return (
        Path(__file__).resolve().parents[4]
        / "tests"
        / "fixtures"
        / "job_sources"
        / "company_audits"
    )


def _resolve_audit_fixture(root: Path, reference: str) -> Path:
    if not reference or "\\" in reference:
        raise SourceConfigurationError("audit fixture reference is not a safe POSIX-relative path")
    candidate_root = root.resolve()
    candidate = (candidate_root / reference).resolve()
    try:
        candidate.relative_to(candidate_root)
    except ValueError as exc:
        raise SourceConfigurationError(
            "audit fixture path escapes the approved fixture root"
        ) from exc
    if candidate == candidate_root or candidate.suffix.lower() != ".json":
        raise SourceConfigurationError(
            "audit fixture must be a JSON file beneath the approved root"
        )
    if not candidate.is_file():
        raise SourceConfigurationError(f"audit fixture does not exist: {reference}")
    try:
        size = candidate.stat().st_size
        if size > _AUDIT_FIXTURE_MAX_BYTES:
            raise SourceConfigurationError("audit fixture exceeds the size limit")
        parsed = json.loads(candidate.read_text(encoding="utf-8"))
    except SourceConfigurationError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SourceConfigurationError(f"audit fixture cannot be parsed: {reference}") from exc
    if not isinstance(parsed, dict):
        raise SourceConfigurationError("audit fixture must contain a JSON object")
    return candidate


def _validate_audit_fixtures(registry: CompanySourceRegistry, root: Path) -> None:
    for source in registry.list_all():
        references = list(source.audit_fixture_paths)
        if source.first_party_audit is not None:
            references.extend(
                [
                    source.first_party_audit.fixture_index_path,
                    source.first_party_audit.fixture_detail_path,
                ]
            )
        for reference in references:
            _resolve_audit_fixture(root, reference)


class SourceConfigurationError(ValueError):
    """Operator configuration does not describe a supported source."""


@dataclass(frozen=True)
class ApprovedSourceRegistry:
    company_registry: CompanySourceRegistry
    legacy_sources: tuple[SupportedJobSource, ...]

    def list_enabled_company_sources(self) -> list[CompanyCareerSource]:
        return self.company_registry.list_enabled()


class SourceRegistry:
    """Deterministic in-memory view of explicitly approved source configuration."""

    def __init__(self, sources: Iterable[SupportedJobSource] = ()) -> None:
        materialized = list(sources)
        source_ids = [source.source_id for source in materialized]
        if len(source_ids) != len(set(source_ids)):
            raise SourceConfigurationError("duplicate source_id values are not allowed")
        provider_keys = [
            (
                source.connector_type.value,
                source.board_token.lower(),
                source.lever_api_region.value if source.lever_api_region else None,
            )
            for source in materialized
        ]
        if len(provider_keys) != len(set(provider_keys)):
            raise SourceConfigurationError("duplicate provider-board identities are not allowed")
        self._sources = tuple(
            sorted(materialized, key=lambda source: (source.source_id, source.connector_type.value))
        )

    @classmethod
    def from_json(cls, payload: str) -> SourceRegistry:
        try:
            decoded = json.loads(payload)
        except (TypeError, json.JSONDecodeError) as exc:
            raise SourceConfigurationError(
                "source registry configuration is not valid JSON"
            ) from exc
        return cls(_parse_sources(decoded))

    @classmethod
    def from_path(cls, path: str | Path) -> SourceRegistry:
        resolved = Path(path)
        try:
            payload = resolved.read_text(encoding="utf-8")
        except OSError as exc:
            raise SourceConfigurationError(f"cannot read source registry: {resolved}") from exc
        return cls.from_json(payload)

    def list_enabled(self) -> list[SupportedJobSource]:
        return [source.model_copy(deep=True) for source in self._sources if source.enabled]


class CompanySourceRegistry:
    """Validated view of the sole version-controlled company-source authority."""

    def __init__(self, sources: Iterable[CompanyCareerSource] = ()) -> None:
        materialized = [source.model_copy(deep=True) for source in sources]
        _validate_company_uniqueness(materialized)
        self._sources = tuple(sorted(materialized, key=lambda source: source.source_id))

    @classmethod
    def from_json(
        cls,
        payload: str,
        *,
        legacy_sources: Iterable[SupportedJobSource] = (),
    ) -> CompanySourceRegistry:
        try:
            decoded = json.loads(payload)
        except (TypeError, json.JSONDecodeError) as exc:
            raise SourceConfigurationError(
                "company registry configuration is not valid JSON"
            ) from exc
        if not isinstance(decoded, dict) or decoded.get("version") != 1:
            raise SourceConfigurationError("company registry version 1 is required")
        companies = decoded.get("companies")
        if not isinstance(companies, list):
            raise SourceConfigurationError("company registry must contain a companies list")
        parsed: list[CompanyCareerSource] = []
        for index, value in enumerate(companies):
            try:
                parsed.append(CompanyCareerSource.model_validate(value))
            except ValidationError as exc:
                message = exc.errors()[0].get("msg", "invalid company source")
                raise SourceConfigurationError(
                    f"invalid company source {index}: {message}"
                ) from exc
        registry = cls(parsed)
        validate_legacy_compatibility(registry.list_all(), legacy_sources)
        return registry

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        *,
        legacy_sources: Iterable[SupportedJobSource] = (),
    ) -> CompanySourceRegistry:
        try:
            payload = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            raise SourceConfigurationError(f"cannot read company source registry: {path}") from exc
        return cls.from_json(payload, legacy_sources=legacy_sources)

    def list_all(self) -> list[CompanyCareerSource]:
        return [source.model_copy(deep=True) for source in self._sources]

    def list_enabled(self) -> list[CompanyCareerSource]:
        return [source.model_copy(deep=True) for source in self._sources if source.enabled]

    def freshness_results(
        self,
        policy: SourceAuditFreshnessPolicy,
        *,
        reference_date: date,
    ) -> list[SourceAuditFreshnessResult]:
        return [policy.evaluate(source, reference_date=reference_date) for source in self._sources]


def _validate_company_uniqueness(sources: list[CompanyCareerSource]) -> None:
    def duplicates(values: Collection[object]) -> bool:
        return len(values) != len(set(values))

    if duplicates([source.source_id for source in sources]):
        raise SourceConfigurationError("duplicate source_id values are not allowed")
    if duplicates([source.company_id for source in sources]):
        raise SourceConfigurationError("duplicate company_id values are not allowed")
    if duplicates([source.canonical_domain for source in sources]):
        raise SourceConfigurationError("duplicate canonical domains are not allowed")
    provider_ids = [
        source.source_plan.provider_configuration
        for source in sources
        if source.source_plan.provider_configuration is not None
    ]
    provider_keys = [
        (
            value.connector_type,
            value.board_token.lower(),
            value.lever_api_region,
        )
        for value in provider_ids
    ]
    if duplicates(provider_keys):
        raise SourceConfigurationError("duplicate provider-board identities are not allowed")
    for source in sources:
        if source.enabled and source.audit_state is not SourceAuditState.APPROVED:
            raise SourceConfigurationError("enabled sources must be approved")
        if source.source_plan.mechanism is SourceMechanism.DEFERRED and source.enabled:
            raise SourceConfigurationError("deferred sources cannot be enabled")
        raw = source.model_dump(mode="json")
        serialized = json.dumps(raw, sort_keys=True).lower()
        forbidden = ("authorization", "cookie", "password", "secret", "token=")
        if any(token in serialized for token in forbidden):
            raise SourceConfigurationError(
                "credentials and secret-like configuration are not allowed"
            )


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def compute_registry_plan_hash(sources: Iterable[CompanyCareerSource]) -> str:
    material = []
    for source in sorted(sources, key=lambda item: item.source_id):
        material.append(
            {
                "source_id": source.source_id,
                "company_id": source.company_id,
                "canonical_domain": source.canonical_domain,
                "careers_entry_url": str(source.careers_entry_url),
                "allowed_hosts": sorted(source.allowed_hosts),
                "redirect_hosts": sorted(source.redirect_hosts),
                "source_plan": _stable_plan_dump(source),
                "extraction_profile_hash": compute_extraction_profile_hash([source]),
            }
        )
    return hashlib.sha256(_canonical_json(material)).hexdigest()


def compute_extraction_profile_hash(sources: Iterable[CompanyCareerSource]) -> str:
    material = []
    for source in sorted(sources, key=lambda item: item.source_id):
        material.append(
            {
                "source_id": source.source_id,
                "extraction_profile": (
                    source.extraction_profile.model_dump(mode="json")
                    if source.extraction_profile is not None
                    else None
                ),
            }
        )
    return hashlib.sha256(_canonical_json(material)).hexdigest()


def _stable_plan_dump(source: CompanyCareerSource) -> dict[str, object]:
    plan = source.source_plan.model_dump(mode="json")
    plan.pop("audit_date", None)
    plan["robots_policy"] = source.robots_policy.value
    for field in (
        "sitemap_urls",
        "sitemap_path_patterns",
        "index_urls",
        "direct_detail_urls",
        "allowed_job_path_patterns",
        "navigation_hosts",
        "redirect_hosts",
        "browser_resource_hosts",
        "browser_api_hosts",
    ):
        if isinstance(plan.get(field), list):
            plan[field] = sorted(plan[field])
    if source.first_party_audit is not None:
        audit = source.first_party_audit.model_dump(mode="json")
        audit.pop("audit_date", None)
        for field in (
            "listing_index_urls",
            "navigation_hosts",
            "redirect_hosts",
            "allowed_listing_path_patterns",
            "allowed_detail_path_patterns",
        ):
            if isinstance(audit.get(field), list):
                audit[field] = sorted(audit[field])
        plan["first_party_audit"] = audit
    return plan


def _parse_sources(decoded: Any) -> list[SupportedJobSource]:
    if isinstance(decoded, dict):
        if set(decoded) != {"sources"} or not isinstance(decoded["sources"], list):
            raise SourceConfigurationError("source registry object must contain a sources list")
        decoded = decoded["sources"]
    if not isinstance(decoded, list):
        raise SourceConfigurationError("source registry must be a list of sources")
    return [_parse_source(item, index) for index, item in enumerate(decoded)]


def _parse_source(value: Any, index: int) -> SupportedJobSource:
    if not isinstance(value, dict):
        raise SourceConfigurationError(f"source entry {index} must be an object")
    if not isinstance(value.get("enabled"), bool):
        raise SourceConfigurationError(f"source entry {index} enabled must be a boolean")

    try:
        source = SupportedJobSource.model_validate(value)
    except ValidationError as exc:
        raise SourceConfigurationError(
            f"invalid source entry {index}: {exc.errors()[0]['msg']}"
        ) from exc

    if not source.source_id.strip():
        raise SourceConfigurationError(f"source entry {index} source_id is required")
    if not source.company_name.strip():
        raise SourceConfigurationError(f"source entry {index} company_name is required")
    if not source.board_token.strip() or any(char.isspace() for char in source.board_token):
        raise SourceConfigurationError(f"source entry {index} board_token/site is invalid")
    if "/" in source.board_token or "\\" in source.board_token:
        raise SourceConfigurationError(f"source entry {index} board_token/site is invalid")

    parsed_url = urlsplit(str(source.official_base_url))
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
        raise SourceConfigurationError(f"source entry {index} official_base_url is invalid")

    if source.connector_type is ConnectorType.LEVER and source.lever_api_region is None:
        raise SourceConfigurationError(f"source entry {index} Lever region is required")
    if source.connector_type is ConnectorType.GREENHOUSE and source.lever_api_region is not None:
        raise SourceConfigurationError(
            f"source entry {index} Greenhouse cannot specify Lever region"
        )
    return source


def load_source_registry(configuration: str | Path | None = None) -> list[SupportedJobSource]:
    """Load only explicit operator configuration; the default registry is empty."""

    if configuration is None:
        return []
    if isinstance(configuration, Path):
        return SourceRegistry.from_path(configuration).list_enabled()
    stripped = configuration.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return SourceRegistry.from_json(configuration).list_enabled()
    return SourceRegistry.from_path(configuration).list_enabled()


def load_company_source_registry(
    configuration: str | Path,
    *,
    freshness_policy: SourceAuditFreshnessPolicy | None = None,
    reference_date: date | None = None,
    fixture_root: str | Path | None = None,
) -> CompanySourceRegistry:
    """Load the authoritative company registry; legacy provider config is read-only compatible."""

    if isinstance(configuration, Path):
        registry = CompanySourceRegistry.from_path(configuration)
    else:
        stripped = configuration.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            registry = CompanySourceRegistry.from_json(configuration)
        else:
            registry = CompanySourceRegistry.from_path(configuration)
    policy = freshness_policy or SourceAuditFreshnessPolicy()
    checked_on = reference_date or date.today()
    results = registry.freshness_results(policy, reference_date=checked_on)
    enabled_ids = {source.source_id for source in registry.list_all() if source.enabled}
    ineligible_enabled = [
        result.source_id
        for result in results
        if not result.eligible and result.source_id in enabled_ids
    ]
    if ineligible_enabled:
        raise SourceConfigurationError(
            "enabled sources have stale or otherwise ineligible audits: "
            + ", ".join(sorted(ineligible_enabled))
        )
    _validate_audit_fixtures(
        registry,
        Path(fixture_root) if fixture_root is not None else _default_audit_fixture_root(),
    )
    return registry


def adapt_legacy_sources(
    sources: Iterable[SupportedJobSource],
) -> list[CompanyCareerSource]:
    """Represent legacy entries without creating a second source authority."""

    adapted: list[CompanyCareerSource] = []
    for source in sources:
        entry = str(source.official_base_url)
        host = urlsplit(entry).hostname
        if host is None:
            raise SourceConfigurationError(f"legacy source {source.source_id} has no host")
        mechanism = SourceMechanism.GREENHOUSE
        if source.connector_type is ConnectorType.LEVER:
            mechanism = SourceMechanism.LEVER
        plan = AuditedSourcePlan(
            mechanism=mechanism,
            listing_discovery_mode=ListingDiscoveryMode.PROVIDER,
            detail_fetch_mode=None,
            detail_extraction_mode=None,
            provider_configuration=ProviderConnectorConfiguration(
                connector_type=cast(Any, source.connector_type.value),
                board_token=source.board_token,
                lever_api_region=(
                    source.lever_api_region.value if source.lever_api_region else None
                ),
            ),
            navigation_hosts=[host],
            max_listing_pages=20,
            audit_version="legacy-compatibility",
            audit_date=None,
        )
        adapted.append(
            CompanyCareerSource(
                source_id=source.source_id,
                company_id=source.source_id,
                canonical_company_name=source.company_name,
                canonical_domain=host,
                careers_entry_url=source.official_base_url,
                allowed_hosts=[host],
                industry_tags=[],
                role_family_tags=[],
                priority_tier=99,
                enabled=False,
                audit_state=SourceAuditState.DEFERRED,
                crawl_cadence_minutes=1440,
                robots_policy=RobotsPolicy.UNKNOWN,
                browser_rendering_allowed=False,
                source_plan=plan,
                provenance_notes=(
                    "Adapted from legacy provider configuration for manual/provider compatibility "
                    "only; it is not an autonomous or audit-approved company source."
                ),
            )
        )
    return adapted


def validate_legacy_compatibility(
    company_sources: Iterable[CompanyCareerSource],
    legacy_sources: Iterable[SupportedJobSource],
) -> None:
    company_by_provider: dict[tuple[str, str, str | None], CompanyCareerSource] = {
        (
            source.source_plan.provider_configuration.connector_type,
            source.source_plan.provider_configuration.board_token.lower(),
            source.source_plan.provider_configuration.lever_api_region,
        ): source
        for source in company_sources
        if source.source_plan.provider_configuration is not None
    }
    for legacy in legacy_sources:
        key = (
            legacy.connector_type.value,
            legacy.board_token.lower(),
            legacy.lever_api_region.value if legacy.lever_api_region else None,
        )
        company = company_by_provider.get(key)
        if company is None:
            continue
        raise SourceConfigurationError(
            "legacy and company registry configure the same provider board authority"
        )


def load_approved_source_registry(
    company_registry_configuration: str | Path,
    legacy_registry_configuration: str | Path | None = None,
    *,
    freshness_policy: SourceAuditFreshnessPolicy | None = None,
    reference_date: date | None = None,
) -> ApprovedSourceRegistry:
    company_registry = load_company_source_registry(
        company_registry_configuration,
        freshness_policy=freshness_policy,
        reference_date=reference_date,
    )
    legacy_sources = tuple(
        load_source_registry(legacy_registry_configuration)
        if legacy_registry_configuration is not None
        else []
    )
    validate_legacy_compatibility(company_registry.list_all(), legacy_sources)
    return ApprovedSourceRegistry(company_registry, legacy_sources)


def compile_runtime_sources(
    registry: CompanySourceRegistry | Iterable[CompanyCareerSource],
) -> list[SupportedJobSource | FirstPartySource]:
    """Compile the approved registry into immutable connector-facing sources.

    This is deliberately a pure transformation. It does not read configuration
    again, inspect the network, or perform robots/access checks.
    """

    sources = registry.list_all() if isinstance(registry, CompanySourceRegistry) else list(registry)
    enabled = [source for source in sources if source.enabled]
    provider_keys = [
        (
            source.source_plan.provider_configuration.connector_type,
            source.source_plan.provider_configuration.board_token.casefold(),
            source.source_plan.provider_configuration.lever_api_region,
        )
        for source in sources
        if source.source_plan.provider_configuration is not None
    ]
    if len(provider_keys) != len(set(provider_keys)):
        raise SourceConfigurationError("duplicate provider-board identities are not allowed")

    compiled: list[SupportedJobSource | FirstPartySource] = []
    for source in sorted(enabled, key=lambda item: item.source_id):
        if source.audit_state is not SourceAuditState.APPROVED:
            continue
        if source.source_plan.audit_date is None:
            continue
        plan_hash = compute_registry_plan_hash([source])
        extraction_hash = compute_extraction_profile_hash([source])
        if source.source_plan.mechanism is SourceMechanism.FIRST_PARTY:
            compiled.append(
                FirstPartySource(
                    source_id=source.source_id,
                    company_id=source.company_id,
                    company_name=source.canonical_company_name,
                    canonical_domain=source.canonical_domain,
                    official_base_url=source.careers_entry_url,
                    allowed_hosts=tuple(source.allowed_hosts),
                    redirect_hosts=tuple(source.redirect_hosts),
                    priority_tier=source.priority_tier,
                    geographic_coverage=source.geographic_coverage,
                    robots_policy=source.robots_policy,
                    browser_rendering_allowed=source.browser_rendering_allowed,
                    crawl_cadence_minutes=source.crawl_cadence_minutes,
                    source_plan=source.source_plan,
                    first_party_audit=source.first_party_audit,
                    extraction_profile=source.extraction_profile,
                    audit_version=source.source_plan.audit_version,
                    registry_plan_hash=plan_hash,
                    extraction_profile_hash=extraction_hash,
                )
            )
            continue
        configuration = source.source_plan.provider_configuration
        if configuration is None:
            raise SourceConfigurationError(f"approved source {source.source_id} has no connector")
        provider_base = (
            f"https://job-boards.greenhouse.io/{configuration.board_token}"
            if configuration.connector_type == "greenhouse"
            else f"https://jobs.lever.co/{configuration.board_token}"
        )
        compiled.append(
            SupportedJobSource(
                source_id=source.source_id,
                connector_type=ConnectorType(configuration.connector_type),
                company_name=source.canonical_company_name,
                board_token=configuration.board_token,
                enabled=True,
                official_base_url=cast(Any, provider_base),
                lever_api_region=(
                    LeverApiRegion(configuration.lever_api_region)
                    if configuration.lever_api_region is not None
                    else None
                ),
                audit_version=source.source_plan.audit_version,
                registry_plan_hash=plan_hash,
                extraction_profile_hash=extraction_hash,
                priority_tier=source.priority_tier,
                toronto_gta_relevance=source.geographic_coverage.toronto_gta_presence,
                crawl_cadence_minutes=source.crawl_cadence_minutes,
            )
        )
    return compiled


__all__ = [
    "ApprovedSourceRegistry",
    "CompanySourceRegistry",
    "SourceConfigurationError",
    "SourceRegistry",
    "compute_extraction_profile_hash",
    "compute_registry_plan_hash",
    "compile_runtime_sources",
    "load_company_source_registry",
    "load_approved_source_registry",
    "load_source_registry",
]
