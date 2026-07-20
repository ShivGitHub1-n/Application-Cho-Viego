from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from resume_tailor.domain.resume_composition import (
    BulletLineFitDiagnostic,
    LineFitVerificationStatus,
)

_TOKEN_PATTERN = re.compile(
    r"(?<![\w+#./-])(?:\.(?=[a-z]))?[a-z0-9][a-z0-9.+#/-]*",
    re.IGNORECASE,
)
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "intern",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "their",
        "this",
        "to",
        "using",
        "we",
        "with",
        "you",
        "your",
    }
)
_GENERIC_ACTIONS = frozenset(
    {
        "automate",
        "automated",
        "build",
        "built",
        "create",
        "created",
        "design",
        "designed",
        "develop",
        "developed",
        "implement",
        "implemented",
        "improve",
        "improved",
        "support",
        "supported",
        "test",
        "tested",
        "work",
        "worked",
    }
)
_LOW_INFORMATION = frozenset(
    {
        "application",
        "applications",
        "analysis",
        "automation",
        "build",
        "deployment",
        "distributed",
        "experience",
        "failure",
        "health",
        "integration",
        "monitoring",
        "project",
        "responsible",
        "role",
        "solution",
        "system",
        "systems",
        "task",
        "technical",
        "technology",
        "testing",
        "tool",
        "validation",
        "various",
    }
)
_RESPONSIBILITY_TERMS: dict[str, frozenset[str]] = {
    "implementation": frozenset(
        {"build", "built", "code", "coded", "configure", "configured", "implement", "implemented"}
    ),
    "design": frozenset(
        {"architect", "architected", "design", "designed", "model", "modeled", "specified"}
    ),
    "integration": frozenset(
        {"assemble", "assembled", "commission", "commissioned", "integrate", "integrated"}
    ),
    "testing_validation": frozenset(
        {
            "calibrate",
            "calibrated",
            "inspect",
            "inspected",
            "test",
            "tested",
            "validate",
            "validated",
        }
    ),
    "debugging": frozenset(
        {
            "debug",
            "debugged",
            "diagnose",
            "diagnosed",
            "investigate",
            "investigated",
            "troubleshoot",
        }
    ),
    "safety_reliability": frozenset(
        {"fail-safe", "hazard", "reliability", "reliable", "safety", "secure", "stability"}
    ),
    "ownership_scope": frozenset(
        {"coordinate", "coordinated", "lead", "led", "own", "owned", "review", "reviewed"}
    ),
    "deployment_operations": frozenset(
        {
            "deploy",
            "deployed",
            "maintain",
            "maintained",
            "monitor",
            "monitored",
            "operate",
            "operated",
        }
    ),
}
_OUTCOME_TERMS = frozenset(
    {
        "accelerated",
        "decreased",
        "delivered",
        "eliminated",
        "enabled",
        "increased",
        "improved",
        "reduced",
        "resolved",
        "saved",
    }
)


@dataclass(frozen=True)
class ReviewedTextFeatures:
    normalized_text: str
    ordered_tokens: tuple[str, ...]
    meaningful_tokens: frozenset[str]
    specific_phrases: tuple[str, ...]
    responsibility_signals: tuple[str, ...]
    outcome_signals: tuple[str, ...]
    technical_specificity: float


@dataclass(frozen=True)
class FeatureMatch:
    admitted: bool
    generic_only: bool
    meaningful_overlap: tuple[str, ...]
    responsibility_overlap: tuple[str, ...]
    matched_requirements: tuple[str, ...]
    relevance_score: float
    reason: str


def normalize_reviewed_text(value: str) -> str:
    """Normalize for comparison without mutating source text or technical syntax."""

    folded = unicodedata.normalize("NFKC", value).casefold()
    tokens = (token.rstrip("./-") for token in _TOKEN_PATTERN.findall(folded))
    return " ".join(token for token in tokens if token)


def extract_reviewed_text_features(value: str) -> ReviewedTextFeatures:
    normalized = normalize_reviewed_text(value)
    ordered_tokens = tuple(normalized.split())
    meaningful_base = tuple(
        token
        for token in ordered_tokens
        if token not in _STOPWORDS
        and token not in _GENERIC_ACTIONS
        and token not in _LOW_INFORMATION
    )
    meaningful = tuple(
        dict.fromkeys(
            part
            for token in meaningful_base
            for part in _comparison_parts(token)
            if part not in _STOPWORDS
            and part not in _GENERIC_ACTIONS
            and part not in _LOW_INFORMATION
        )
    )
    phrases: list[str] = []
    for size in range(4, 1, -1):
        for index in range(len(ordered_tokens) - size + 1):
            window = ordered_tokens[index : index + size]
            informative = [
                token
                for token in window
                if token not in _STOPWORDS
                and token not in _GENERIC_ACTIONS
                and token not in _LOW_INFORMATION
            ]
            if len(informative) < 2:
                continue
            phrases.append(" ".join(window))
    phrases.extend(token for token in meaningful if _is_specific_singleton(token))
    extracted_phrases = tuple(
        sorted(
            set(filter(None, phrases)),
            key=lambda item: (-len(item.split()), -len(item), item),
        )
    )
    responsibilities = tuple(
        label
        for label, terms in _RESPONSIBILITY_TERMS.items()
        if any(token in terms for token in ordered_tokens)
    )
    outcomes = tuple(
        token
        for token in ordered_tokens
        if token in _OUTCOME_TERMS or any(character.isdigit() for character in token)
    )
    symbol_terms = sum(
        any(character in token for character in "+#./-")
        or any(character.isdigit() for character in token)
        for token in meaningful
    )
    specificity = min(
        1.0,
        (min(12, len(set(meaningful))) * 0.055)
        + (min(4, len(extracted_phrases)) * 0.045)
        + (symbol_terms * 0.08)
        + (len(responsibilities) * 0.035),
    )
    return ReviewedTextFeatures(
        normalized_text=normalized,
        ordered_tokens=ordered_tokens,
        meaningful_tokens=frozenset(meaningful),
        specific_phrases=extracted_phrases,
        responsibility_signals=responsibilities,
        outcome_signals=tuple(dict.fromkeys(outcomes)),
        technical_specificity=round(specificity, 4),
    )


def match_reviewed_features(
    candidate: ReviewedTextFeatures,
    posting: ReviewedTextFeatures,
) -> FeatureMatch:
    phrase_overlap = _maximal_phrases(
        [
            phrase
            for phrase in candidate.specific_phrases
            if _contains_phrase(posting.normalized_text, phrase)
        ]
    )
    shared_tokens = candidate.meaningful_tokens & posting.meaningful_tokens
    singleton_overlap = sorted(
        token
        for token in shared_tokens
        if _is_specific_singleton(token)
        and not any(_contains_phrase(phrase, token) for phrase in phrase_overlap)
    )
    meaningful_overlap = tuple([*phrase_overlap, *singleton_overlap])
    high_signal_overlap = tuple(
        phrase
        for phrase in meaningful_overlap
        if len(phrase.split()) >= 2
        or len(phrase) >= 8
        or any(character.isdigit() for character in phrase)
        or any(character in phrase for character in "+#./-")
    )
    alphabetic_singletons = tuple(
        phrase for phrase in meaningful_overlap if phrase not in high_signal_overlap
    )
    responsibility_overlap = tuple(
        signal
        for signal in candidate.responsibility_signals
        if signal in posting.responsibility_signals
    )
    generic_shared = set(candidate.ordered_tokens) & set(posting.ordered_tokens) & _GENERIC_ACTIONS
    specific_overlap_admits = bool(high_signal_overlap) or len(alphabetic_singletons) >= 2
    generic_only = bool(generic_shared or responsibility_overlap) and not (specific_overlap_admits)
    responsibility_adjacent = (
        bool(responsibility_overlap)
        and len(shared_tokens) >= 3
        and candidate.technical_specificity >= 0.18
    )
    admitted = specific_overlap_admits or responsibility_adjacent
    phrase_score = sum(
        8.0 + min(12.0, len(phrase.split()) * 3.0) for phrase in meaningful_overlap[:6]
    )
    responsibility_score = min(18.0, len(responsibility_overlap) * 6.0)
    specificity_score = candidate.technical_specificity * 14.0
    relevance_score = round(
        phrase_score + responsibility_score + specificity_score,
        2,
    )
    if generic_only:
        reason = "Rejected because overlap was limited to low-information generic actions."
    elif meaningful_overlap:
        reason = "Admitted through specific reviewed-text overlap with posting requirements."
    elif responsibility_adjacent:
        reason = (
            "Admitted as specific transferable evidence sharing a posting responsibility "
            "and a meaningful technical concept."
        )
    else:
        reason = "Rejected because no specific or credibly adjacent posting evidence matched."
    return FeatureMatch(
        admitted=admitted,
        generic_only=generic_only,
        meaningful_overlap=meaningful_overlap,
        responsibility_overlap=responsibility_overlap,
        matched_requirements=meaningful_overlap,
        relevance_score=relevance_score,
        reason=reason,
    )


class TemplateV1BulletLineEstimator:
    """Deterministic line-fit estimate derived from packaged Template V1 geometry."""

    available_width_points = 520.45
    font_size_points = 10.0
    awkward_width_fraction = 0.18

    def estimate(self, text: str) -> BulletLineFitDiagnostic:
        words = text.split()
        if not words:
            return BulletLineFitDiagnostic(
                verification_status=LineFitVerificationStatus.ESTIMATED,
                expected_line_count=1,
                expected_final_line_word_count=0,
                expected_final_line_width_ratio=0,
                total_vertical_line_cost=1,
                awkward_wrap_risk=False,
                three_line_risk=False,
                future_rewrite_recommended=False,
            )
        lines: list[list[str]] = [[]]
        widths: list[float] = [0.0]
        for word in words:
            word_width = _estimated_word_width(word, self.font_size_points)
            separator = _estimated_word_width(" ", self.font_size_points) if lines[-1] else 0.0
            if lines[-1] and widths[-1] + separator + word_width > self.available_width_points:
                lines.append([word])
                widths.append(word_width)
            else:
                lines[-1].append(word)
                widths[-1] += separator + word_width
        final_word_count = len(lines[-1])
        final_width_ratio = min(1.0, widths[-1] / self.available_width_points)
        awkward = len(lines) > 1 and (
            final_word_count <= 2 or final_width_ratio < self.awkward_width_fraction
        )
        three_line = len(lines) >= 3
        vertical_cost = len(lines) + (0.35 if awkward else 0.0) + (max(0, len(lines) - 2) * 0.75)
        return BulletLineFitDiagnostic(
            verification_status=LineFitVerificationStatus.ESTIMATED,
            expected_line_count=len(lines),
            expected_final_line_word_count=final_word_count,
            expected_final_line_width_ratio=round(final_width_ratio, 4),
            total_vertical_line_cost=round(vertical_cost, 2),
            awkward_wrap_risk=awkward,
            three_line_risk=three_line,
            future_rewrite_recommended=awkward or three_line,
        )


def _is_specific_singleton(token: str) -> bool:
    if token in _STOPWORDS or token in _GENERIC_ACTIONS or token in _LOW_INFORMATION:
        return False
    return (
        len(token) >= 5
        or any(character.isdigit() for character in token)
        or any(character in token for character in "+#./-")
    )


def _comparison_parts(token: str) -> tuple[str, ...]:
    parts = tuple(part for part in re.split(r"[-/]", token) if part)
    return tuple(dict.fromkeys((token, *parts)))


def _maximal_phrases(phrases: list[str]) -> list[str]:
    ordered = sorted(
        set(filter(None, phrases)),
        key=lambda item: (-len(item.split()), -len(item), item),
    )
    selected: list[str] = []
    for phrase in ordered:
        if any(_contains_phrase(other, phrase) for other in selected):
            continue
        selected.append(phrase)
    return selected


def _contains_phrase(text: str, phrase: str) -> bool:
    return bool(phrase) and f" {phrase} " in f" {text} "


def _estimated_word_width(value: str, font_size: float) -> float:
    width_em = 0.0
    for character in value:
        if character.isspace():
            width_em += 0.25
        elif character in "ilI.,:;'|!":
            width_em += 0.25
        elif character in "mwMW@%&":
            width_em += 0.82
        elif character.isupper():
            width_em += 0.62
        elif character.isdigit():
            width_em += 0.50
        elif character in "+#/-()":
            width_em += 0.42
        else:
            width_em += 0.46
    return width_em * font_size


__all__ = [
    "FeatureMatch",
    "ReviewedTextFeatures",
    "TemplateV1BulletLineEstimator",
    "extract_reviewed_text_features",
    "match_reviewed_features",
    "normalize_reviewed_text",
]
