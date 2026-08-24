from __future__ import annotations

from dataclasses import dataclass

from resume_tailor.application.resume_features import (
    extract_reviewed_text_features,
    normalize_reviewed_text,
)


@dataclass(frozen=True)
class SemanticNormalizationResult:
    """Deterministically proven posting terminology introduced by a rewrite."""

    entailed_target_terms: tuple[str, ...] = ()
    allowed_feature_tokens: frozenset[str] = frozenset()
    support_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class _EvidenceDimension:
    indicators: tuple[str, ...]
    minimum_matches: int = 1


@dataclass(frozen=True)
class _SemanticRule:
    target_terms: tuple[str, ...]
    evidence_dimensions: tuple[_EvidenceDimension, ...]
    reason: str


_PROGRAMMABLE_DEVICE = _EvidenceDimension(
    (
        "microcontroller",
        "microcontrollers",
        "mcu",
        "stm32",
        "esp32",
        "arduino",
        "bare-metal",
        "embedded controller",
        "embedded processor",
    )
)
_SOFTWARE_IMPLEMENTATION = _EvidenceDimension(
    (
        "code",
        "coded",
        "coding",
        "programmed",
        "programming",
        "implemented software",
        "developed software",
        "control code",
        "c++",
        "rust",
        "assembly language",
    )
)
_IMPLEMENTATION_OWNERSHIP = _EvidenceDimension(
    (
        "developed",
        "implemented",
        "programmed",
        "wrote",
        "authored",
        "built",
        "created",
        "coded",
    )
)
_PHYSICAL_HARDWARE = _EvidenceDimension(
    (
        "microcontroller",
        "mcu",
        "stm32",
        "esp32",
        "pcb",
        "circuit board",
        "circuit",
        "motor",
        "actuator",
        "sensor",
        "wiring",
        "electrical",
        "electronic",
        "mechanical assembly",
        "embedded device",
    )
)
_TEST_OR_VALIDATION = _EvidenceDimension(
    (
        "tested",
        "testing",
        "validated",
        "validation",
        "verified",
        "bench-tested",
        "bench testing",
        "qualified",
        "qualification",
        "inspected",
    )
)
_DEBUGGING = _EvidenceDimension(
    (
        "debugged",
        "debugging",
        "diagnosed",
        "diagnosing",
        "troubleshot",
        "troubleshooting",
        "fault isolation",
    )
)
_DESIGN_OR_BUILD = _EvidenceDimension(
    (
        "designed",
        "modeled",
        "created",
        "fabricated",
        "built",
        "constructed",
        "assembled",
    )
)


_SEMANTIC_RULES: tuple[_SemanticRule, ...] = (
    _SemanticRule(
        target_terms=("firmware",),
        evidence_dimensions=(
            _PROGRAMMABLE_DEVICE,
            _SOFTWARE_IMPLEMENTATION,
            _IMPLEMENTATION_OWNERSHIP,
        ),
        reason=(
            "programmable-device evidence includes explicit software implementation and "
            "authorship"
        ),
    ),
    _SemanticRule(
        target_terms=("embedded",),
        evidence_dimensions=(_PROGRAMMABLE_DEVICE,),
        reason="reviewed evidence identifies a programmable embedded device",
    ),
    _SemanticRule(
        target_terms=("fixture", "fixtures"),
        evidence_dimensions=(
            _EvidenceDimension(
                (
                    "mount",
                    "mounts",
                    "mounting bracket",
                    "mounting brackets",
                    "bracket",
                    "brackets",
                    "jig",
                    "jigs",
                    "test stand",
                    "tooling",
                )
            ),
            _DESIGN_OR_BUILD,
        ),
        reason="reviewed evidence proves designed or built physical mounting tooling",
    ),
    _SemanticRule(
        target_terms=("enclosure", "enclosures"),
        evidence_dimensions=(
            _EvidenceDimension(
                ("enclosure", "enclosures", "housing", "housings", "chassis", "casing")
            ),
            _DESIGN_OR_BUILD,
        ),
        reason="reviewed evidence explicitly proves a designed or built housing",
    ),
    _SemanticRule(
        target_terms=("pcb bring-up", "board bring-up", "bring-up"),
        evidence_dimensions=(
            _EvidenceDimension(("pcb", "circuit board", "printed circuit board")),
            _EvidenceDimension(
                (
                    "bring-up",
                    "first power-on",
                    "initial power-on",
                    "commissioned",
                    "commissioning",
                )
            ),
        ),
        reason="reviewed circuit-board evidence explicitly proves initial commissioning",
    ),
    _SemanticRule(
        target_terms=("hardware validation",),
        evidence_dimensions=(_PHYSICAL_HARDWARE, _TEST_OR_VALIDATION),
        reason="reviewed evidence proves testing or validation of physical hardware",
    ),
    _SemanticRule(
        target_terms=("embedded debugging",),
        evidence_dimensions=(_PROGRAMMABLE_DEVICE, _DEBUGGING),
        reason="reviewed evidence proves debugging on a programmable embedded device",
    ),
    _SemanticRule(
        target_terms=("electromechanical prototype", "electromechanical prototyping"),
        evidence_dimensions=(
            _EvidenceDimension(("motor", "actuator", "servo", "robotic arm", "robot")),
            _EvidenceDimension(
                (
                    "prototype",
                    "prototyped",
                    "built",
                    "assembled",
                    "fabricated",
                    "integrated",
                )
            ),
        ),
        reason="reviewed evidence proves building or integrating an actuated physical system",
    ),
    _SemanticRule(
        target_terms=("data pipeline", "data pipelines"),
        evidence_dimensions=(
            _EvidenceDimension(("data", "dataset", "datasets", "records")),
            _EvidenceDimension(
                (
                    "extract",
                    "extracted",
                    "ingest",
                    "ingested",
                    "transform",
                    "transformed",
                    "load",
                    "loaded",
                    "normalize",
                    "normalized",
                ),
                minimum_matches=2,
            ),
            _IMPLEMENTATION_OWNERSHIP,
        ),
        reason="reviewed evidence proves authored multi-stage data processing",
    ),
    _SemanticRule(
        target_terms=("model evaluation",),
        evidence_dimensions=(
            _EvidenceDimension(
                (
                    "model",
                    "models",
                    "classifier",
                    "classifiers",
                    "neural network",
                    "language model",
                )
            ),
            _EvidenceDimension(
                (
                    "evaluated",
                    "tested",
                    "validated",
                    "benchmarked",
                    "measured accuracy",
                    "measured precision",
                    "measured recall",
                )
            ),
        ),
        reason="reviewed evidence proves testing or measurement of model behavior",
    ),
)

def evidence_entailed_target_terminology(
    rewritten_text: str,
    source_texts: list[str],
    structured_facts: list[str],
    target_texts: list[str],
) -> SemanticNormalizationResult:
    """Prove bounded terminology normalization without creating evidence authority.

    A term is eligible only when it appears in both the generated wording and the
    authoritative posting context. Direct reviewed structured facts and a small
    set of compositional engineering concepts can prove the term.
    Ordinary morphological or linguistic normalization remains governed by the
    existing validator and does not receive material-rewrite authority here.
    Anything else remains review-required upstream.
    """

    rewritten = normalize_reviewed_text(rewritten_text)
    source = normalize_reviewed_text(" ".join(source_texts))
    structured = normalize_reviewed_text(" ".join(structured_facts))
    reviewed = " ".join(part for part in (source, structured) if part)
    targets = normalize_reviewed_text(" ".join(target_texts))
    if not rewritten or not reviewed or not targets:
        return SemanticNormalizationResult()

    entailed: list[str] = []
    reasons: list[str] = []

    for fact in structured_facts:
        normalized_fact = normalize_reviewed_text(fact)
        if (
            normalized_fact
            and not _contains_phrase(source, normalized_fact)
            and _contains_phrase(rewritten, normalized_fact)
            and _contains_phrase(targets, normalized_fact)
        ):
            entailed.append(normalized_fact)
            reasons.append(f"reviewed structured fact directly supports {normalized_fact!r}")

    for rule in _SEMANTIC_RULES:
        generated_rule_terms = [
            term
            for term in rule.target_terms
            if _contains_phrase(rewritten, term)
            and not _contains_phrase(source, term)
        ]
        target_uses_rule = any(_contains_phrase(targets, term) for term in rule.target_terms)
        if not generated_rule_terms or not target_uses_rule or not all(
            _dimension_is_satisfied(reviewed, dimension)
            for dimension in rule.evidence_dimensions
        ):
            continue
        entailed.extend(generated_rule_terms)
        reasons.extend(f"{term!r}: {rule.reason}" for term in generated_rule_terms)

    ordered_terms = tuple(dict.fromkeys(entailed))
    allowed_tokens = frozenset(
        token
        for term in ordered_terms
        for token in extract_reviewed_text_features(term).meaningful_tokens
    )
    return SemanticNormalizationResult(
        entailed_target_terms=ordered_terms,
        allowed_feature_tokens=allowed_tokens,
        support_reasons=tuple(dict.fromkeys(reasons)),
    )


def _dimension_is_satisfied(text: str, dimension: _EvidenceDimension) -> bool:
    return (
        sum(_contains_phrase(text, indicator) for indicator in dimension.indicators)
        >= dimension.minimum_matches
    )


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized_phrase = normalize_reviewed_text(phrase)
    return bool(normalized_phrase) and f" {normalized_phrase} " in f" {text} "


__all__ = [
    "SemanticNormalizationResult",
    "evidence_entailed_target_terminology",
]
