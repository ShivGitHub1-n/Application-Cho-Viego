from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import date
from hashlib import sha256
from time import perf_counter

from resume_tailor.domain.company_research import (
    CompanyFactConfidence,
    CompanyResearchBundle,
    CompanyResearchEvent,
    CompanyResearchFact,
    CompanyResearchRequest,
    CompanyResearchSource,
    CompanyResearchStatus,
    CompanySourceDocument,
    CompanySourceType,
)
from resume_tailor.ports.company_research import CompanySourceFetcher

Clock = Callable[[], float]
Today = Callable[[], date]

_MAX_SOURCE_FETCHES = 3
_MAX_FACTS = 5
_GENERIC_MARKETING = (
    "changing the future",
    "cutting-edge",
    "driving innovation",
    "improving people",
    "industry-leading",
    "make the world",
    "meaningful impact",
    "our mission",
    "revolutionize",
    "transforming the industry",
    "world-class",
)
_STOPWORDS = {
    "about",
    "and",
    "are",
    "company",
    "for",
    "from",
    "into",
    "our",
    "role",
    "that",
    "the",
    "their",
    "this",
    "with",
    "you",
    "your",
}


class BoundedCompanyResearchService:
    """Fetch and cache a small, attributable set of approved company facts."""

    def __init__(
        self,
        fetcher: CompanySourceFetcher | None = None,
        *,
        max_fetches: int = _MAX_SOURCE_FETCHES,
        clock: Clock = perf_counter,
        today: Today | None = None,
    ) -> None:
        if max_fetches < 0 or max_fetches > _MAX_SOURCE_FETCHES:
            raise ValueError(f"Company research supports at most {_MAX_SOURCE_FETCHES} fetches")
        self._fetcher = fetcher
        self._max_fetches = max_fetches
        self._clock = clock
        self._today = today or date.today
        self._cache: dict[str, CompanyResearchBundle] = {}

    def research(self, request: CompanyResearchRequest) -> CompanyResearchBundle:
        started = self._clock()
        cache_key = self._cache_key(request)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached.model_copy(
                update={
                    "cache_hit": True,
                    "network_request_count": 0,
                    "events": list(
                        dict.fromkeys([*cached.events, CompanyResearchEvent.RESEARCH_CACHE_HIT])
                    ),
                    "elapsed_seconds": max(0.0, self._clock() - started),
                }
            )
        bundle = self._research_uncached(request, started)
        self._cache[cache_key] = bundle
        return bundle

    def _research_uncached(
        self,
        request: CompanyResearchRequest,
        started: float,
    ) -> CompanyResearchBundle:
        sources: list[CompanyResearchSource] = []
        facts: list[CompanyResearchFact] = []
        events: list[CompanyResearchEvent] = []
        limitations: list[str] = []
        network_requests = 0
        fetch_failures = 0
        fetched_documents = 0

        posting_source, posting_facts = self._posting_authority(request)
        sources.append(posting_source)
        facts.extend(posting_facts)

        if request.company_name is None:
            limitations.extend(
                [
                    "No validated company identity was available.",
                    "Official company research was not attempted; the validated posting "
                    "remains the only company authority.",
                ]
            )
            return self._bundle(
                request,
                status=(
                    CompanyResearchStatus.POSTING_ONLY
                    if facts
                    else CompanyResearchStatus.NOT_REQUIRED
                ),
                sources=sources,
                facts=facts,
                events=events,
                limitations=limitations,
                network_requests=0,
                started=started,
            )

        if request.user_supplied_facts:
            source = self._user_source(request)
            sources.append(source)
            facts.extend(
                self._facts_from_text(
                    source,
                    " ".join(request.user_supplied_facts),
                    request,
                    confidence=CompanyFactConfidence.USER_AUTHORITY,
                    exact_sentences=request.user_supplied_facts,
                )
            )

        if not request.enabled:
            limitations.append("External company research was disabled.")
            return self._bundle(
                request,
                status=(
                    CompanyResearchStatus.POSTING_ONLY if facts else CompanyResearchStatus.DISABLED
                ),
                sources=sources,
                facts=facts,
                events=events,
                limitations=limitations,
                network_requests=0,
                started=started,
            )

        approved_sources = request.approved_sources[: self._max_fetches]
        if len(request.approved_sources) > self._max_fetches:
            events.append(CompanyResearchEvent.FETCH_LIMIT_REACHED)
        if not approved_sources:
            limitations.append("No approved official company source URLs were supplied.")
        elif not request.company_domain:
            limitations.append("An approved company domain is required before source fetching.")
        elif self._fetcher is None:
            limitations.append("No company-source fetcher is configured.")
        else:
            for approved in approved_sources:
                if approved.source_type is CompanySourceType.SEARCH_SNIPPET:
                    events.append(CompanyResearchEvent.UNVERIFIED_SNIPPET_REJECTED)
                    continue
                network_requests += 1
                try:
                    document = self._fetcher.fetch(
                        approved,
                        company_domain=request.company_domain,
                    )
                except Exception:
                    fetch_failures += 1
                    limitations.append(f"Approved source fetch failed: {approved.url}")
                    continue
                if (
                    not document.verified_source
                    or document.source_type is CompanySourceType.SEARCH_SNIPPET
                ):
                    events.append(CompanyResearchEvent.UNVERIFIED_SNIPPET_REJECTED)
                    continue
                fetched_documents += 1
                source = self._source_from_document(document)
                sources.append(source)
                facts.extend(
                    self._facts_from_text(
                        source,
                        document.text,
                        request,
                        confidence=CompanyFactConfidence.VERIFIED,
                    )
                )

        facts = self._deduplicate_facts(facts)[:_MAX_FACTS]
        if self._has_conflict(facts):
            events.append(CompanyResearchEvent.CONFLICTING_SOURCES)
            facts = [
                fact.model_copy(update={"confidence": CompanyFactConfidence.CONFLICTING})
                if self._fact_conflicts(fact, facts)
                else fact
                for fact in facts
            ]
        verified = [
            fact
            for fact in facts
            if fact.confidence
            in {CompanyFactConfidence.VERIFIED, CompanyFactConfidence.USER_AUTHORITY}
        ]
        posting_only = [
            fact for fact in facts if fact.confidence is CompanyFactConfidence.POSTING_AUTHORITY
        ]
        if verified:
            status = CompanyResearchStatus.VERIFIED
        elif fetch_failures:
            status = CompanyResearchStatus.SOURCE_FETCH_FAILED
        elif approved_sources and fetched_documents:
            status = CompanyResearchStatus.FACT_NOT_VERIFIED
        elif approved_sources and (not request.company_domain or self._fetcher is None):
            status = CompanyResearchStatus.OFFICIAL_SOURCE_NOT_FOUND
        elif posting_only:
            status = CompanyResearchStatus.POSTING_ONLY
        elif network_requests:
            status = CompanyResearchStatus.SOURCE_FETCH_FAILED
        elif request.enabled:
            status = CompanyResearchStatus.OFFICIAL_SOURCE_NOT_FOUND
        else:
            status = CompanyResearchStatus.DISABLED
        return self._bundle(
            request,
            status=status,
            sources=sources,
            facts=facts,
            events=events,
            limitations=limitations,
            network_requests=network_requests,
            started=started,
        )

    def _posting_authority(
        self,
        request: CompanyResearchRequest,
    ) -> tuple[CompanyResearchSource, list[CompanyResearchFact]]:
        identifier = request.job_url or f"posting:{request.posting_fingerprint}"
        source = CompanyResearchSource(
            id=self._stable_id("company-source", identifier),
            source_url=request.job_url,
            stable_identifier=identifier,
            title=f"{request.role_title} job posting",
            publisher=request.company_name or "Job posting",
            retrieved_on=self._today(),
            source_type=CompanySourceType.JOB_POSTING,
            content_fingerprint=self._fingerprint(request.posting_description),
        )
        facts = self._facts_from_text(
            source,
            request.posting_description,
            request,
            confidence=CompanyFactConfidence.POSTING_AUTHORITY,
        )
        if not facts and request.posting_description.strip():
            sentence = " ".join(request.posting_description.split())[:700]
            facts = [
                CompanyResearchFact(
                    id=self._stable_id("company-fact", f"{source.id}:{sentence}"),
                    source_id=source.id,
                    fact=sentence,
                    supported_claim=sentence,
                    confidence=CompanyFactConfidence.POSTING_AUTHORITY,
                    relevant_role_terms=sorted(
                        self._content_terms(f"{request.role_title} {sentence}")
                    )[:12],
                )
            ]
        return source, facts

    def _user_source(self, request: CompanyResearchRequest) -> CompanyResearchSource:
        text = "\n".join(request.user_supplied_facts)
        return CompanyResearchSource(
            id=self._stable_id("company-source", f"user:{self._fingerprint(text)}"),
            stable_identifier=f"user-supplied:{request.company_name}",
            title="User-supplied company information",
            publisher="Application user",
            retrieved_on=self._today(),
            source_type=CompanySourceType.USER_SUPPLIED,
            content_fingerprint=self._fingerprint(text),
        )

    def _source_from_document(self, document: CompanySourceDocument) -> CompanyResearchSource:
        return CompanyResearchSource(
            id=self._stable_id("company-source", document.source_url),
            source_url=document.source_url,
            stable_identifier=document.source_url,
            title=document.title,
            publisher=document.publisher,
            retrieved_on=document.retrieved_on,
            source_type=document.source_type,
            content_fingerprint=self._fingerprint(document.text),
        )

    def _facts_from_text(
        self,
        source: CompanyResearchSource,
        text: str,
        request: CompanyResearchRequest,
        *,
        confidence: CompanyFactConfidence,
        exact_sentences: list[str] | None = None,
    ) -> list[CompanyResearchFact]:
        sentences = exact_sentences or self._sentences(text)
        role_terms = self._content_terms(f"{request.role_title} {request.posting_description}")
        ranked: list[tuple[int, int, str, list[str]]] = []
        for index, sentence in enumerate(sentences):
            cleaned = " ".join(sentence.split()).strip(" -\t")
            lowered = cleaned.casefold()
            minimum_length = 15 if exact_sentences is not None else 35
            if len(cleaned) < minimum_length or len(cleaned) > 700:
                continue
            if any(phrase in lowered for phrase in _GENERIC_MARKETING):
                continue
            overlap = sorted(self._content_terms(cleaned) & role_terms)
            technical_signal = bool(
                re.search(
                    r"\b(?:build|built|design|engineer|firmware|hardware|platform|product|"
                    r"robot|software|system|test|manufactur|security|data|cloud|model)\w*\b",
                    lowered,
                )
            )
            score = len(overlap) * 3 + (2 if technical_signal else 0)
            if score <= 0 and exact_sentences is None:
                continue
            ranked.append((-score, index, cleaned, overlap))
        ranked.sort()
        return [
            CompanyResearchFact(
                id=self._stable_id("company-fact", f"{source.id}:{sentence}"),
                source_id=source.id,
                fact=sentence,
                supported_claim=sentence,
                confidence=confidence,
                relevant_role_terms=overlap[:12],
            )
            for _, _, sentence, overlap in ranked[:2]
        ]

    def _bundle(
        self,
        request: CompanyResearchRequest,
        *,
        status: CompanyResearchStatus,
        sources: list[CompanyResearchSource],
        facts: list[CompanyResearchFact],
        events: list[CompanyResearchEvent],
        limitations: list[str],
        network_requests: int,
        started: float,
    ) -> CompanyResearchBundle:
        fingerprint_payload = {
            "company_name": request.company_name,
            "status": status.value,
            "sources": [source.model_dump(mode="json") for source in sources],
            "facts": [fact.model_dump(mode="json") for fact in facts],
        }
        fingerprint = self._fingerprint(
            json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":"))
        )
        return CompanyResearchBundle(
            company_name=request.company_name,
            status=status,
            research_fingerprint=fingerprint,
            sources=sources,
            facts=facts,
            events=list(dict.fromkeys(events)),
            limitations=list(dict.fromkeys(limitations)),
            network_request_count=network_requests,
            elapsed_seconds=max(0.0, self._clock() - started),
        )

    @staticmethod
    def _cache_key(request: CompanyResearchRequest) -> str:
        return sha256(request.model_dump_json().encode("utf-8")).hexdigest()

    @staticmethod
    def _fingerprint(value: str) -> str:
        return sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _stable_id(prefix: str, value: str) -> str:
        return f"{prefix}:{sha256(value.encode('utf-8')).hexdigest()[:16]}"

    @staticmethod
    def _sentences(text: str) -> list[str]:
        sentences: list[str] = []
        for line in text.replace("\r", "\n").splitlines():
            cleaned = re.sub(r"^\s*[-*\u2022]\s*", "", line).strip()
            if not cleaned or re.fullmatch(r"[\w /&,()-]+:", cleaned):
                continue
            sentences.extend(
                item.strip()
                for item in re.split(r"(?<=[.!?])\s+", cleaned)
                if item.strip()
            )
        if sentences:
            return sentences
        normalized = re.sub(r"\s+", " ", text).strip()
        return [item.strip() for item in re.split(r"(?<=[.!?])\s+", normalized) if item.strip()]

    @staticmethod
    def _content_terms(text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-z][a-z0-9+#.-]{2,}", text.casefold())
            if token not in _STOPWORDS
        }

    @staticmethod
    def _deduplicate_facts(facts: list[CompanyResearchFact]) -> list[CompanyResearchFact]:
        output: list[CompanyResearchFact] = []
        seen: set[str] = set()
        for fact in facts:
            key = re.sub(r"\W+", " ", fact.fact.casefold()).strip()
            if key not in seen:
                output.append(fact)
                seen.add(key)
        return output

    @classmethod
    def _has_conflict(cls, facts: list[CompanyResearchFact]) -> bool:
        return any(cls._fact_conflicts(fact, facts) for fact in facts)

    @classmethod
    def _fact_conflicts(
        cls,
        fact: CompanyResearchFact,
        facts: list[CompanyResearchFact],
    ) -> bool:
        terms = cls._content_terms(fact.fact)
        fact_negated = bool(
            re.search(r"\b(?:does not|is not|no longer|without)\b", fact.fact.casefold())
        )
        for other in facts:
            if other.id == fact.id or other.source_id == fact.source_id:
                continue
            other_terms = cls._content_terms(other.fact)
            other_negated = bool(
                re.search(r"\b(?:does not|is not|no longer|without)\b", other.fact.casefold())
            )
            if fact_negated != other_negated and len(terms & other_terms) >= 4:
                return True
        return False


__all__ = ["BoundedCompanyResearchService"]
