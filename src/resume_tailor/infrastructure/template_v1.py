from __future__ import annotations

from functools import lru_cache
from hashlib import sha256
from pathlib import Path

from resume_tailor.domain.layout import LayoutProfile, ObservedValue, ParagraphLayout

TEMPLATE_V1_ID = "application-viego-resume-v1"
TEMPLATE_V1_REFERENCE_SHA256 = "2b9dd1474b9e4a303a87b8a147f3511460988104efde7cfa053cad64294369cd"
TEMPLATE_V1_LAYOUT_FILENAME = "template_v1_layout.json"
TEMPLATE_V1_DOCX_FILENAME = "template_v1.docx"
TEMPLATE_V1_DOCX_SHA256 = "2b4eeae9bed52ff27b86cb1e9f75516d0a9935359658849589b37ffef0a5974e"
TEMPLATE_V1_LINE_SPACING_TWIPS = 240
TEMPLATE_V1_LINE_SPACING_RULE = "exact"
TEMPLATE_V1_ZERO_PARAGRAPH_SPACING_TWIPS = 0


@lru_cache(maxsize=1)
def _cached_template_v1_layout_profile() -> LayoutProfile:
    path = Path(__file__).resolve().parent.parent / "templates" / TEMPLATE_V1_LAYOUT_FILENAME
    profile = LayoutProfile.model_validate_json(path.read_text(encoding="utf-8"))
    return _with_explicit_paragraph_spacing(profile)


def _with_explicit_paragraph_spacing(profile: LayoutProfile) -> LayoutProfile:
    """Resolve Template V1's implicit canonical defaults into explicit OOXML values."""

    semantic_roles = {
        role_name: role.model_copy(
            update={
                "paragraph": _explicit_paragraph_spacing(role.paragraph),
            }
        )
        for role_name, role in profile.semantic_roles.items()
    }
    transitions = [
        transition.model_copy(
            update={
                "resolved_source_space_after_twips": _explicit_transition_value(
                    transition.resolved_source_space_after_twips,
                    transition.source_space_after_twips,
                ),
                "resolved_destination_space_before_twips": _explicit_transition_value(
                    transition.resolved_destination_space_before_twips,
                    transition.destination_space_before_twips,
                ),
            }
        )
        for transition in profile.transition_spacings
    ]
    return profile.model_copy(
        update={
            "semantic_roles": semantic_roles,
            "transition_spacings": transitions,
        }
    )


def _explicit_paragraph_spacing(layout: ParagraphLayout) -> ParagraphLayout:
    space_after = layout.space_after_twips
    if not _is_twips(space_after.value):
        space_after = _canonical_spacing_value(TEMPLATE_V1_ZERO_PARAGRAPH_SPACING_TWIPS)
    return layout.model_copy(
        update={
            "space_after_twips": space_after,
            "line_spacing_twips": _canonical_spacing_value(TEMPLATE_V1_LINE_SPACING_TWIPS),
            "line_spacing_rule": _canonical_spacing_value(TEMPLATE_V1_LINE_SPACING_RULE),
        }
    )


def _explicit_transition_value(
    resolved: ObservedValue | None,
    observed: ObservedValue,
) -> ObservedValue:
    for candidate in (resolved, observed):
        if candidate is not None and _is_twips(candidate.value):
            return candidate
    return _canonical_spacing_value(TEMPLATE_V1_ZERO_PARAGRAPH_SPACING_TWIPS)


def _canonical_spacing_value(value: int | str) -> ObservedValue:
    return ObservedValue(
        value=value,
        provenance="inferred_recurring_pattern",
    )


def _is_twips(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def load_template_v1_layout_profile() -> LayoutProfile:
    """Load the content-free diagnostic layout profile."""

    return _cached_template_v1_layout_profile().model_copy(deep=True)


def template_v1_docx_path() -> Path:
    """Return the validated packaged static DOCX used as Template V1 authority."""

    path = Path(__file__).resolve().parent.parent / "templates" / TEMPLATE_V1_DOCX_FILENAME
    if not path.is_file():
        raise FileNotFoundError(f"Packaged Template V1 DOCX is missing: {path}")
    actual_sha256 = sha256(path.read_bytes()).hexdigest()
    if actual_sha256 != TEMPLATE_V1_DOCX_SHA256:
        raise ValueError(
            "Packaged Template V1 DOCX failed its integrity check: "
            f"expected {TEMPLATE_V1_DOCX_SHA256}, got {actual_sha256}"
        )
    return path


__all__ = [
    "TEMPLATE_V1_ID",
    "TEMPLATE_V1_DOCX_SHA256",
    "TEMPLATE_V1_REFERENCE_SHA256",
    "load_template_v1_layout_profile",
    "template_v1_docx_path",
]
