from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CompanyResearchStatus(StrEnum):
    VERIFIED = "verified"
    POSTING_ONLY = "posting_only"
    UNAVAILABLE = "company_research_unavailable"
    OFFICIAL_SOURCE_NOT_FOUND = "official_source_not_found"
    SOURCE_FETCH_FAILED = "source_fetch_failed"
    FACT_NOT_VERIFIED = "company_fact_not_verified"
    DISABLED = "research_disabled"
    NOT_REQUIRED = "research_not_required"


class CompanyResearchEvent(StrEnum):
    RESEARCH_CACHE_HIT = "research_cache_hit"
    UNVERIFIED_SNIPPET_REJECTED = "unverified_snippet_rejected"
    CONFLICTING_SOURCES = "conflicting_company_sources"
    FETCH_LIMIT_REACHED = "research_fetch_limit_reached"


class CompanySourceType(StrEnum):
    JOB_POSTING = "job_posting"
    OFFICIAL_WEBSITE = "official_website"
    OFFICIAL_PRODUCT = "official_product_page"
    OFFICIAL_ENGINEERING = "official_engineering_page"
    OFFICIAL_CAREERS = "official_careers_page"
    OFFICIAL_TECHNICAL_PUBLICATION = "official_technical_publication"
    OFFICIAL_PRESS_RELEASE = "official_press_release"
    APPROVED_TRUSTWORTHY = "approved_trustworthy_source"
    USER_SUPPLIED = "user_supplied_company_information"
    SEARCH_SNIPPET = "search_result_snippet"


class CompanyFactConfidence(StrEnum):
    VERIFIED = "verified"
    POSTING_AUTHORITY = "posting_authority"
    USER_AUTHORITY = "user_authority"
    CONFLICTING = "conflicting"
    UNAVAILABLE = "unavailable"


class ApprovedCompanySource(BaseModel):
    url: str
    source_type: CompanySourceType
    approved_third_party: bool = False


class CompanyResearchRequest(BaseModel):
    company_name: str | None = None
    company_domain: str | None = None
    role_title: str
    job_url: str | None = None
    posting_fingerprint: str
    posting_description: str
    approved_sources: list[ApprovedCompanySource] = Field(default_factory=list, max_length=3)
    user_supplied_facts: list[str] = Field(default_factory=list, max_length=3)
    enabled: bool = True


class CompanySourceDocument(BaseModel):
    source_url: str
    title: str
    publisher: str
    source_type: CompanySourceType
    retrieved_on: date
    text: str = Field(min_length=1, max_length=120_000)
    verified_source: bool = True


class CompanyResearchSource(BaseModel):
    id: str
    source_url: str | None = None
    stable_identifier: str
    title: str
    publisher: str
    retrieved_on: date
    source_type: CompanySourceType
    content_fingerprint: str


class CompanyResearchFact(BaseModel):
    id: str
    source_id: str
    fact: str = Field(min_length=1, max_length=700)
    supported_claim: str = Field(min_length=1, max_length=700)
    confidence: CompanyFactConfidence
    relevant_role_terms: list[str] = Field(default_factory=list)


class CompanyResearchBundle(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_name: str | None = None
    status: CompanyResearchStatus
    research_fingerprint: str
    sources: list[CompanyResearchSource] = Field(default_factory=list)
    facts: list[CompanyResearchFact] = Field(default_factory=list)
    events: list[CompanyResearchEvent] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    network_request_count: int = Field(default=0, ge=0, le=3)
    cache_hit: bool = False
    elapsed_seconds: float = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_provenance(self) -> CompanyResearchBundle:
        source_ids = {source.id for source in self.sources}
        unknown = {fact.source_id for fact in self.facts} - source_ids
        if unknown:
            raise ValueError(f"Company facts reference unknown source IDs: {sorted(unknown)}")
        return self


__all__ = [
    "ApprovedCompanySource",
    "CompanyFactConfidence",
    "CompanyResearchBundle",
    "CompanyResearchEvent",
    "CompanyResearchFact",
    "CompanyResearchRequest",
    "CompanyResearchSource",
    "CompanyResearchStatus",
    "CompanySourceDocument",
    "CompanySourceType",
]
