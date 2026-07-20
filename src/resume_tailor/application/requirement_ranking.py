from __future__ import annotations

import re
from collections import Counter
from hashlib import sha256

from resume_tailor.application.resume_features import (
    ReviewedTextFeatures,
    extract_reviewed_text_features,
    match_reviewed_features,
    normalize_reviewed_text,
)
from resume_tailor.domain.models import JobPosting
from resume_tailor.domain.requirement_ranking import (
    EvidenceRelationship,
    EvidenceRelationshipAssessment,
    PostingRequirement,
    PostingRequirementModel,
    RequirementAuthority,
    ShortTokenContribution,
)

_REQUIRED_MARKERS = re.compile(
    r"\b(required|requirements|must|minimum|need to|needs to|responsibilities|"
    r"what you will do|duties|qualifications)\b",
    re.IGNORECASE,
)
_RESPONSIBILITY_MARKERS = re.compile(
    r"\b(responsibilities|what you will do|duties|day to day|in this role)\b",
    re.IGNORECASE,
)
_BONUS_MARKERS = re.compile(
    r"\b(preferred|bonus|nice to have|asset|plus|ideally)\b",
    re.IGNORECASE,
)
_INCIDENTAL_MARKERS = re.compile(
    r"\b(incidental(?:ly)?|optional(?:ly)?|helpful|may occasionally|"
    r"company overview|about us|benefits|compensation)\b",
    re.IGNORECASE,
)
_RAW_TECHNICAL_TOKEN = re.compile(
    r"(?<![\w+#./-])[A-Za-z][A-Za-z0-9+.#/-]{0,11}(?![\w+#./-])"
)


def extract_posting_requirements(posting: JobPosting) -> PostingRequirementModel:
    raw_segments = _posting_segments(posting.description)
    provisional: list[
        tuple[str, RequirementAuthority, str, ReviewedTextFeatures]
    ] = []
    title_features = extract_reviewed_text_features(posting.title)
    if title_features.meaningful_tokens:
        provisional.append(
            (posting.title.strip(), RequirementAuthority.CORE, "title", title_features)
        )
    current_context = "posting"
    current_authority = RequirementAuthority.IMPORTANT
    for raw in raw_segments:
        heading_candidate = raw.strip(" \t\r\n-*•;")
        cleaned = heading_candidate.strip(":")
        if not cleaned:
            continue
        detected = _authority_for_text(cleaned)
        if _looks_like_heading(heading_candidate):
            current_authority = detected
            current_context = normalize_reviewed_text(cleaned) or "posting"
            continue
        authority = (
            detected
            if detected is not RequirementAuthority.IMPORTANT
            else current_authority
        )
        features = extract_reviewed_text_features(cleaned)
        if not features.meaningful_tokens and not features.responsibility_signals:
            continue
        provisional.append((cleaned, authority, current_context, features))

    phrase_counts = Counter(
        phrase
        for _text, _authority, _context, features in provisional
        for phrase in features.specific_phrases
        if len(phrase) >= 4
    )
    requirements: list[PostingRequirement] = []
    seen: set[tuple[str, RequirementAuthority]] = set()
    for text, authority, source_context, features in provisional:
        normalized = features.normalized_text
        identity = (normalized, authority)
        if not normalized or identity in seen:
            continue
        seen.add(identity)
        repetition = max(
            [
                1,
                *(
                phrase_counts[phrase]
                for phrase in features.specific_phrases
                if len(phrase) >= 4
                ),
            ]
        )
        importance = _importance(authority, features, repetition)
        digest = sha256(
            f"{authority.value}\0{source_context}\0{normalized}".encode()
        ).hexdigest()[:12]
        requirements.append(
            PostingRequirement(
                id=f"requirement:{digest}",
                text=text,
                normalized_text=normalized,
                authority=authority,
                importance=importance,
                source_context=source_context,
                repetition_count=repetition,
                technical_specificity=features.technical_specificity,
                responsibility_signals=list(features.responsibility_signals),
                specific_phrases=list(features.specific_phrases[:24]),
            )
        )
    requirements.sort(
        key=lambda item: (
            -item.importance,
            _authority_order(item.authority),
            item.id,
        )
    )
    return PostingRequirementModel(requirements=requirements)


def assess_evidence_relationship(
    *,
    bullet_text: str,
    bullet_features: ReviewedTextFeatures,
    entry_features: ReviewedTextFeatures,
    structured_values: list[str],
    requirements: PostingRequirementModel,
    reviewed_skill: bool = False,
) -> EvidenceRelationshipAssessment:
    direct: list[PostingRequirement] = []
    adjacent: list[PostingRequirement] = []
    complementary: list[PostingRequirement] = []
    incidental: list[PostingRequirement] = []
    meaningful_overlap: list[str] = []
    short_contributions: list[ShortTokenContribution] = []
    contextual_score = 0.0
    candidate_raw = " ".join([bullet_text, *structured_values])
    raw_tokens = _candidate_short_tokens(candidate_raw)
    primary_entry_context = any(
        requirement.authority
        in {RequirementAuthority.CORE, RequirementAuthority.IMPORTANT}
        and match_reviewed_features(
            entry_features,
            extract_reviewed_text_features(requirement.text),
        ).admitted
        for requirement in requirements.requirements
    )

    for requirement in requirements.requirements:
        requirement_features = extract_reviewed_text_features(requirement.text)
        bullet_match = match_reviewed_features(bullet_features, requirement_features)
        entry_match = match_reviewed_features(entry_features, requirement_features)
        meaningful_overlap.extend(bullet_match.meaningful_overlap)
        short_matches = _short_token_matches(
            raw_tokens,
            requirement,
            bullet_match.meaningful_overlap,
            bullet_match.responsibility_overlap,
            entry_match.admitted,
            reviewed_skill=reviewed_skill,
        )
        short_contributions.extend(short_matches)
        corroborated_short = any(item.corroborated for item in short_matches)
        exact_reviewed_skill = (
            reviewed_skill
            and _exact_reviewed_skill_match(bullet_text, requirement)
        )
        lexical_direct = (
            bullet_match.admitted and not bullet_match.generic_only
        ) or exact_reviewed_skill
        if (
            requirement.source_context == "title"
            and not reviewed_skill
            and not bullet_features.responsibility_signals
            and not bullet_features.outcome_signals
        ):
            lexical_direct = False
        has_responsibility_adjacency = bool(bullet_match.responsibility_overlap)
        strong_overlap_context = (
            len(bullet_match.meaningful_overlap) >= 2
            or any(
                " " in item
                or len(item) >= 8
                or any(character.isdigit() for character in item)
                or any(character in item for character in "+#./-")
                for item in bullet_match.meaningful_overlap
            )
        )
        strong_entry_adjacency = (
            (entry_match.admitted or primary_entry_context)
            and has_responsibility_adjacency
            and bullet_features.technical_specificity >= 0.25
        )
        specific_transferable_context = (
            bool(bullet_match.meaningful_overlap)
            and bool(bullet_features.responsibility_signals)
            and bullet_features.technical_specificity >= 0.45
        )
        term_family_context = _has_conservative_term_family(
            bullet_features,
            requirement_features,
        )
        contextual_adjacency = (
            (has_responsibility_adjacency or specific_transferable_context)
            and bullet_features.technical_specificity >= 0.18
            and (
                strong_overlap_context
                or corroborated_short
                or strong_entry_adjacency
                or specific_transferable_context
            )
        )

        if requirement.authority in {
            RequirementAuthority.CORE,
            RequirementAuthority.IMPORTANT,
        }:
            if lexical_direct or corroborated_short:
                direct.append(requirement)
                contextual_score += requirement.importance * (
                    10.0 + min(20.0, bullet_match.relevance_score)
                )
            elif contextual_adjacency:
                adjacent.append(requirement)
                contextual_score += requirement.importance * (
                    7.0 + min(10.0, bullet_match.relevance_score * 0.35)
                )
        elif requirement.authority is RequirementAuthority.BONUS:
            if lexical_direct or corroborated_short or term_family_context:
                complementary.append(requirement)
                contextual_score += requirement.importance * (
                    6.0 + min(8.0, bullet_match.relevance_score * 0.4)
                )
            elif contextual_adjacency:
                complementary.append(requirement)
                contextual_score += requirement.importance * 3.0
        elif lexical_direct or corroborated_short:
            incidental.append(requirement)
            contextual_score += requirement.importance * 2.0

    relationship = (
        EvidenceRelationship.DIRECT
        if direct
        else EvidenceRelationship.ADJACENT
        if adjacent
        else EvidenceRelationship.COMPLEMENTARY
        if complementary
        else EvidenceRelationship.INCIDENTAL
        if incidental
        else EvidenceRelationship.REJECTED
    )
    matched = [*direct, *adjacent, *complementary, *incidental]
    return EvidenceRelationshipAssessment(
        relationship=relationship,
        direct_requirement_ids=[item.id for item in direct],
        adjacent_requirement_ids=[item.id for item in adjacent],
        complementary_requirement_ids=[item.id for item in complementary],
        incidental_requirement_ids=[item.id for item in incidental],
        contextual_relevance=round(contextual_score, 2),
        matched_requirement_labels=[item.text for item in matched],
        meaningful_overlap=_unique_maximal_phrases(meaningful_overlap),
        short_token_contributions=_deduplicate_short_contributions(short_contributions),
        reason=_relationship_reason(relationship),
    )


def _posting_segments(description: str) -> list[str]:
    segments: list[str] = []
    for line in re.split(r"[\r\n]+", description):
        stripped = line.strip()
        if not stripped:
            continue
        sentence_parts = re.split(r"(?<=[.!?;])\s+", stripped)
        for part in sentence_parts:
            if not part.strip():
                continue
            segments.extend(_split_compound_responsibilities(part))
    return segments


def _split_compound_responsibilities(value: str) -> list[str]:
    """Split action-led clauses while keeping ordinary technical lists intact."""

    fragments = [
        fragment.strip(" ,")
        for fragment in re.split(r",\s+|\s+and\s+", value)
        if fragment.strip(" ,")
    ]
    action_led = [
        fragment
        for fragment in fragments
        if extract_reviewed_text_features(fragment).responsibility_signals
    ]
    if len(action_led) < 2:
        return [value]

    clauses: list[str] = []
    current = ""
    for fragment in fragments:
        signals = extract_reviewed_text_features(fragment).responsibility_signals
        if signals and current:
            clauses.append(current)
            current = fragment
        elif current:
            current = f"{current}, {fragment}"
        else:
            current = fragment
    if current:
        clauses.append(current)
    return clauses if len(clauses) >= 2 else [value]


def _looks_like_heading(value: str) -> bool:
    words = value.rstrip(":").split()
    responsibility_signals = extract_reviewed_text_features(
        value
    ).responsibility_signals
    return (
        value.endswith(":")
        or len(words) <= 3
        and not responsibility_signals
        and bool(
            _REQUIRED_MARKERS.search(value)
            or _RESPONSIBILITY_MARKERS.search(value)
            or _BONUS_MARKERS.search(value)
            or _INCIDENTAL_MARKERS.search(value)
        )
    )


def _authority_for_text(value: str) -> RequirementAuthority:
    if _INCIDENTAL_MARKERS.search(value):
        return RequirementAuthority.INCIDENTAL
    if _BONUS_MARKERS.search(value):
        return RequirementAuthority.BONUS
    if _REQUIRED_MARKERS.search(value) or _RESPONSIBILITY_MARKERS.search(value):
        return RequirementAuthority.CORE
    return RequirementAuthority.IMPORTANT


def _importance(
    authority: RequirementAuthority,
    features: ReviewedTextFeatures,
    repetition: int,
) -> float:
    base = {
        RequirementAuthority.CORE: 1.35,
        RequirementAuthority.IMPORTANT: 1.0,
        RequirementAuthority.BONUS: 0.58,
        RequirementAuthority.INCIDENTAL: 0.24,
    }[authority]
    specificity = min(0.24, features.technical_specificity * 0.24)
    repeated = min(0.24, max(0, repetition - 1) * 0.08)
    return round(min(2.0, base + specificity + repeated), 3)


def _authority_order(authority: RequirementAuthority) -> int:
    return {
        RequirementAuthority.CORE: 0,
        RequirementAuthority.IMPORTANT: 1,
        RequirementAuthority.BONUS: 2,
        RequirementAuthority.INCIDENTAL: 3,
    }[authority]


def _candidate_short_tokens(value: str) -> set[str]:
    tokens: set[str] = set()
    for raw in _RAW_TECHNICAL_TOKEN.findall(value):
        token = raw.rstrip("./-")
        if not token or not _is_short_or_symbolic(token):
            continue
        if token.isalpha() and not token.isupper():
            continue
        tokens.add(token)
        for component in re.split(r"[/]", token):
            if (
                component
                and _is_short_or_symbolic(component)
                and (not component.isalpha() or component.isupper())
            ):
                tokens.add(component)
    return tokens


def _is_short_or_symbolic(token: str) -> bool:
    return (
        len(token) <= 3
        or any(character.isdigit() for character in token)
        or any(character in token for character in "+#./-")
    )


def _short_token_matches(
    candidate_tokens: set[str],
    requirement: PostingRequirement,
    lexical_overlap: tuple[str, ...],
    responsibility_overlap: tuple[str, ...],
    entry_match: bool,
    *,
    reviewed_skill: bool,
) -> list[ShortTokenContribution]:
    requirement_tokens = {
        token
        for raw in _RAW_TECHNICAL_TOKEN.findall(requirement.text)
        if (token := raw.rstrip("./-"))
        and _is_short_or_symbolic(token)
        and (not token.isalpha() or token.isupper())
    }
    output: list[ShortTokenContribution] = []
    for raw in sorted(candidate_tokens, key=lambda item: (item.casefold(), item)):
        matched = next(
            (
                token
                for token in requirement_tokens
                if token.casefold() == raw.casefold()
            ),
            None,
        )
        if matched is None:
            continue
        syntax_specific = (
            any(character.isdigit() for character in raw)
            or any(character in raw for character in "+#./-")
        )
        non_short_context = [
            item
            for item in lexical_overlap
            if len(item) >= 5 or " " in item
        ]
        peer_identifiers = {
            token.casefold()
            for token in requirement_tokens
            if token.casefold() != raw.casefold()
        }
        reviewed_peer_context = (
            reviewed_skill
            and requirement.authority
            in {RequirementAuthority.CORE, RequirementAuthority.IMPORTANT}
            and len(peer_identifiers) >= 2
            and requirement.technical_specificity >= 0.12
        )
        corroborated = bool(
            syntax_specific
            or non_short_context
            or (responsibility_overlap and entry_match)
            or reviewed_peer_context
        )
        contexts = [
            *non_short_context[:3],
            *[item.replace("_", " ") for item in responsibility_overlap[:2]],
        ]
        if reviewed_peer_context:
            contexts.append("co-listed reviewed technical identifiers")
        output.append(
            ShortTokenContribution(
                token=matched,
                requirement_ids=[requirement.id],
                contribution=(
                    round(requirement.importance * (6.0 if syntax_specific else 3.0), 2)
                    if corroborated
                    else 0.0
                ),
                corroborated=corroborated,
                specificity_reason=(
                    "Symbolic or alphanumeric identifier."
                    if syntax_specific
                    else "Short alphabetic token required corroborating technical context."
                ),
                corroborating_context=list(dict.fromkeys(contexts)),
            )
        )
    return output


def _exact_reviewed_skill_match(
    candidate_raw: str,
    requirement: PostingRequirement,
) -> bool:
    normalized = normalize_reviewed_text(candidate_raw)
    return bool(normalized) and (
        f" {normalized} " in f" {requirement.normalized_text} "
    )


def _unique_maximal_phrases(values: list[str]) -> list[str]:
    ordered = sorted(
        set(filter(None, values)),
        key=lambda item: (-len(item.split()), -len(item), item),
    )
    selected: list[str] = []
    for value in ordered:
        if any(f" {value} " in f" {other} " for other in selected):
            continue
        selected.append(value)
    return selected


def _deduplicate_short_contributions(
    items: list[ShortTokenContribution],
) -> list[ShortTokenContribution]:
    grouped: dict[str, ShortTokenContribution] = {}
    for item in items:
        key = item.token.casefold()
        previous = grouped.get(key)
        if previous is None:
            grouped[key] = item
            continue
        grouped[key] = previous.model_copy(
            update={
                "requirement_ids": list(
                    dict.fromkeys([*previous.requirement_ids, *item.requirement_ids])
                ),
                "contribution": round(
                    previous.contribution + item.contribution,
                    2,
                ),
                "corroborated": previous.corroborated or item.corroborated,
                "corroborating_context": list(
                    dict.fromkeys(
                        [
                            *previous.corroborating_context,
                            *item.corroborating_context,
                        ]
                    )
                ),
            }
        )
    return sorted(grouped.values(), key=lambda item: item.token.casefold())


def _relationship_reason(relationship: EvidenceRelationship) -> str:
    return {
        EvidenceRelationship.DIRECT: (
            "The evidence itself directly matches a core or important posting requirement."
        ),
        EvidenceRelationship.ADJACENT: (
            "The evidence independently demonstrates a strongly adjacent technical "
            "responsibility with corroborating posting context."
        ),
        EvidenceRelationship.COMPLEMENTARY: (
            "The evidence supports bonus language or a transferable responsibility "
            "without displacing direct requirement authority."
        ),
        EvidenceRelationship.INCIDENTAL: (
            "The evidence matches only low-authority or incidental posting language."
        ),
        EvidenceRelationship.REJECTED: (
            "The bullet itself lacks direct, adjacent, or useful complementary support."
        ),
    }[relationship]


def _has_conservative_term_family(
    candidate: ReviewedTextFeatures,
    requirement: ReviewedTextFeatures,
) -> bool:
    for first in candidate.meaningful_tokens:
        if len(first) < 8:
            continue
        for second in requirement.meaningful_tokens:
            if len(second) < 8:
                continue
            common = 0
            for left, right in zip(first, second, strict=False):
                if left != right:
                    break
                common += 1
            if common >= 5 and common / min(len(first), len(second)) >= 0.5:
                return True
    return False


__all__ = [
    "assess_evidence_relationship",
    "extract_posting_requirements",
]
