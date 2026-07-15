from __future__ import annotations

import re
from dataclasses import dataclass

from resume_tailor.domain.job_discovery.capabilities import normalize_capability_term
from resume_tailor.domain.job_discovery.location import parse_location
from resume_tailor.domain.job_discovery.models import (
    JobLevel,
    JobRequirement,
    JobRequirementSignals,
    ProfileCapabilityIndex,
    RequirementCategory,
    RequirementImportance,
    WorkArrangement,
)
from resume_tailor.domain.job_discovery.role_signals import (
    ROLE_SIGNAL_CATALOG,
    classify_role_signals,
)

_REQUIRED_PHRASES = ("must", "required", "minimum", "strong proficiency")
_PREFERRED_PHRASES = ("preferred", "nice to have", "bonus")
_MARKETING_PHRASES = (
    "we are",
    "our mission",
    "we believe",
    "join us",
    "make an impact",
    "world-class",
    "fast-growing",
    "innovative company",
    "great culture",
)
_REQUIREMENT_CONTEXT = (
    "experience with",
    "knowledge of",
    "proficiency in",
    "familiarity with",
    "skills in",
    "background in",
    "ability to",
)
_RESPONSIBILITY_VERBS = (
    "design",
    "build",
    "develop",
    "implement",
    "maintain",
    "test",
    "analyze",
    "deploy",
    "integrate",
    "research",
    "evaluate",
)


@dataclass(frozen=True)
class RequirementCatalogEntry:
    canonical: str
    aliases: tuple[str, ...]
    category: RequirementCategory
    required_phrases: tuple[str, ...] = _REQUIRED_PHRASES
    preferred_phrases: tuple[str, ...] = _PREFERRED_PHRASES


def _entry(
    canonical: str,
    aliases: tuple[str, ...] = (),
    category: RequirementCategory = RequirementCategory.TECHNOLOGY,
) -> RequirementCatalogEntry:
    normalized = normalize_capability_term(canonical)
    all_aliases = tuple(dict.fromkeys((canonical, *aliases)))
    return RequirementCatalogEntry(normalized, all_aliases, category)


_TECHNOLOGY_ENTRIES = (
    _entry("python"),
    _entry("java"),
    _entry("javascript", ("js",)),
    _entry("typescript", ("ts",)),
    _entry("c++", ("cpp", "c plus plus")),
    _entry("c#", ("csharp", "c sharp")),
    _entry("go", ("golang",)),
    _entry("rust"),
    _entry("sql"),
    _entry("postgresql", ("postgres",)),
    _entry("mysql"),
    _entry("git"),
    _entry("linux"),
    _entry("docker"),
    _entry("kubernetes", ("k8s",)),
    _entry("aws"),
    _entry("azure"),
    _entry("gcp", ("google cloud",)),
    _entry("cuda"),
    _entry("tensorflow"),
    _entry("pytorch"),
    _entry("scikit-learn", ("scikit learn", "sklearn")),
    _entry("opencv"),
    _entry("ros2", ("ros 2",)),
    _entry("embedded c", ("embedded-c",)),
    _entry("microcontrollers", ("microcontroller",)),
    _entry("firmware"),
    _entry("apis", ("api",)),
    _entry("distributed systems"),
    _entry("data structures"),
    _entry("algorithms"),
    _entry("testing", ("test automation",)),
    _entry("system design"),
)


def _catalog() -> tuple[RequirementCatalogEntry, ...]:
    entries: dict[str, RequirementCatalogEntry] = {
        entry.canonical: entry for entry in _TECHNOLOGY_ENTRIES
    }
    technology_terms = {
        normalize_capability_term(alias)
        for entry in _TECHNOLOGY_ENTRIES
        for alias in entry.aliases
    }
    for signal in ROLE_SIGNAL_CATALOG:
        canonical = normalize_capability_term(signal.canonical_term)
        if canonical not in entries:
            aliases = tuple(
                alias
                for alias in signal.aliases
                if normalize_capability_term(alias) not in technology_terms
                or normalize_capability_term(alias) == canonical
            )
            entries[canonical] = _entry(
                canonical,
                aliases,
                RequirementCategory.ROLE,
            )
    return tuple(entries[canonical] for canonical in sorted(entries))


JOB_REQUIREMENT_TERM_CATALOG = _catalog()


def _pattern(phrase: str) -> re.Pattern[str]:
    escaped = re.escape(phrase.casefold()).replace(r"\ ", r"\s+")
    return re.compile(rf"(?<!\w){escaped}(?!\w)", re.IGNORECASE)


def _sentence_at(text: str, start: int, end: int) -> str:
    left = max(
        text.rfind(".", 0, start),
        text.rfind("!", 0, start),
        text.rfind("?", 0, start),
        text.rfind("\n", 0, start),
    )
    right_candidates = [
        position
        for position in (
            text.find(".", end),
            text.find("!", end),
            text.find("?", end),
            text.find("\n", end),
        )
        if position >= 0
    ]
    right = min(right_candidates, default=len(text) - 1)
    return text[left + 1 : right + 1].strip()


def _importance(context: str) -> RequirementImportance:
    lowered = context.casefold()
    required_positions = [
        lowered.find(phrase) for phrase in _REQUIRED_PHRASES if phrase in lowered
    ]
    preferred_positions = [
        lowered.find(phrase) for phrase in _PREFERRED_PHRASES if phrase in lowered
    ]
    if required_positions and (
        not preferred_positions or max(required_positions) >= max(preferred_positions)
    ):
        return RequirementImportance.REQUIRED
    if preferred_positions:
        return RequirementImportance.PREFERRED
    return RequirementImportance.UNKNOWN


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _is_marketing_only(sentence: str) -> bool:
    lowered = sentence.casefold()
    if not any(phrase in lowered for phrase in _MARKETING_PHRASES):
        return False
    return not any(
        phrase in lowered
        for phrase in (
            *_REQUIRED_PHRASES,
            *_PREFERRED_PHRASES,
            *_REQUIREMENT_CONTEXT,
            *_RESPONSIBILITY_VERBS,
        )
    )


def _arrangement(text: str, supplied: WorkArrangement) -> WorkArrangement:
    if supplied is not WorkArrangement.UNKNOWN:
        return supplied
    lowered = text.casefold()
    if re.search(r"\bhybrid\b", lowered):
        return WorkArrangement.HYBRID
    if re.search(r"\bon[- ]?site\b|\bin office\b", lowered):
        return WorkArrangement.ONSITE
    if re.search(r"\bremote\b|\bwork from home\b", lowered):
        return WorkArrangement.REMOTE
    return WorkArrangement.UNKNOWN


def _job_level(title: str, text: str) -> JobLevel:
    lowered = f"{title} {text}".casefold()
    for phrase, level in (
        ("intern", JobLevel.INTERN),
        ("co-op", JobLevel.INTERN),
        ("coop", JobLevel.INTERN),
        ("new graduate", JobLevel.ENTRY),
        ("entry level", JobLevel.ENTRY),
        ("entry-level", JobLevel.ENTRY),
        ("junior", JobLevel.JUNIOR),
        ("senior", JobLevel.SENIOR),
        ("lead", JobLevel.LEAD),
        ("mid-level", JobLevel.MID),
        ("mid level", JobLevel.MID),
    ):
        if re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", lowered):
            return level
    return JobLevel.UNKNOWN


def _sentences(text: str) -> list[tuple[str, int, int]]:
    return [
        (match.group(0).strip(), match.start(), match.end())
        for match in re.finditer(r"[^.!?\n]+[.!?]?(?:\s+|$)", text)
        if match.group(0).strip()
    ]


class RequirementExtractor:
    def __init__(self, profile_index: ProfileCapabilityIndex | None = None) -> None:
        self._profile_index = profile_index

    def extract(
        self,
        title: str,
        description: str,
        location_raw: str | None,
        work_arrangement: WorkArrangement,
        profile_index: ProfileCapabilityIndex | None = None,
    ) -> JobRequirementSignals:
        profile_index = profile_index if profile_index is not None else self._profile_index
        source = title.strip()
        if description.strip():
            source = f"{source}\n{description.strip()}" if source else description.strip()

        entries = {entry.canonical: entry for entry in JOB_REQUIREMENT_TERM_CATALOG}
        if profile_index is not None:
            for term in profile_index.terms:
                normalized = normalize_capability_term(term)
                if normalized and normalized not in entries:
                    entries[normalized] = _entry(normalized)

        matches: list[JobRequirement] = []
        for entry in entries.values():
            for alias in entry.aliases:
                for match in _pattern(alias).finditer(source):
                    sentence = _sentence_at(source, match.start(), match.end())
                    if _is_marketing_only(sentence):
                        continue
                    matches.append(
                        JobRequirement(
                            term=entry.canonical,
                            category=entry.category,
                            importance=_importance(sentence),
                            source_text=sentence,
                            source_start=match.start(),
                            source_end=match.end(),
                        )
                    )
        matches.sort(key=lambda item: (item.source_start, item.source_end, item.term))

        first_match: dict[str, JobRequirement] = {}
        for requirement in matches:
            previous = first_match.get(requirement.term)
            if previous is None or (
                requirement.importance is RequirementImportance.REQUIRED
                and previous.importance is not RequirementImportance.REQUIRED
            ):
                first_match[requirement.term] = requirement
        ordered_matches = sorted(
            first_match.values(), key=lambda item: (item.source_start, item.term)
        )
        required = [
            item.term
            for item in ordered_matches
            if item.importance is RequirementImportance.REQUIRED
        ]
        preferred = [
            item.term
            for item in ordered_matches
            if item.importance is RequirementImportance.PREFERRED
        ]
        unknown = [
            item.term
            for item in ordered_matches
            if item.importance is RequirementImportance.UNKNOWN
        ]

        experience_matches = list(
            re.finditer(
                r"(?:(?:at least|minimum(?: of)?|over|more than)\s+)?(\d+)\s*\+?\s+years?",
                source,
                re.IGNORECASE,
            )
        )
        experience_years = max((int(match.group(1)) for match in experience_matches), default=None)
        degree_requirements = _unique(
            [
                re.sub(r"\s+", " ", match.group(0).casefold()).strip()
                for match in re.finditer(
                    r"\b(?:bachelor(?:'s)?|master(?:'s)?|ph\.?d\.?|doctorate|diploma)(?:\s+degree)?\b",
                    source,
                    re.IGNORECASE,
                )
            ]
        )
        graduation_requirements = _unique(
            [
                re.sub(r"\s+", " ", match.group(0).casefold()).strip()
                for match in re.finditer(
                    r"\b(?:expected to )?graduate(?:d|ion)?(?: by \w+ \d{4})?\b|\bclass of \d{4}\b",
                    source,
                    re.IGNORECASE,
                )
            ]
        )
        certification_requirements = _unique(
            [
                _sentence_at(source, match.start(), match.end())
                for match in re.finditer(
                    r"\b(?:certif(?:ied|ication)|certificate)\b",
                    source,
                    re.IGNORECASE,
                )
            ]
        )
        authorization_language = _unique(
            [
                sentence
                for sentence, _start, _end in _sentences(source)
                if re.search(
                    (
                        r"\b(?:authorized to work|work authorization|visa sponsorship|"
                        r"sponsor(?:ship)?|security clearance|citizen(?:ship)?)\b"
                    ),
                    sentence,
                    re.IGNORECASE,
                )
            ]
        )
        responsibilities = _unique(
            [
                sentence
                for sentence, _start, _end in _sentences(description)
                if re.search(
                    rf"\b(?:{'|'.join(_RESPONSIBILITY_VERBS)})\b",
                    sentence,
                    re.IGNORECASE,
                )
                and not _is_marketing_only(sentence)
            ]
        )
        role_result = classify_role_signals(title, description)
        material_gaps = [
            f"No reviewed profile evidence or skill was found for required {term}."
            for term in required
            if profile_index is not None and term not in profile_index.terms
        ]
        return JobRequirementSignals(
            required_terms=_unique(required),
            preferred_terms=_unique(preferred),
            unknown_terms=_unique(unknown),
            responsibilities=responsibilities,
            experience_years=experience_years,
            degree_requirements=degree_requirements,
            graduation_requirements=graduation_requirements,
            certification_requirements=certification_requirements,
            work_arrangement=_arrangement(source, work_arrangement),
            authorization_language=authorization_language,
            role_signals=[signal.id for signal in role_result.signals],
            job_level=_job_level(title, description),
            location=parse_location(location_raw) if location_raw else None,
            requirements=ordered_matches,
            material_gaps=material_gaps,
        )
