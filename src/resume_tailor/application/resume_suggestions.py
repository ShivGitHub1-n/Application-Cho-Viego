from __future__ import annotations

from dataclasses import dataclass

from resume_tailor.domain.models import MasterProfile, ResumeItem, StructuredBullet


class ResumeSuggestionParentError(ValueError):
    pass


@dataclass(frozen=True)
class CanonicalSuggestionParent:
    entry: ResumeItem
    confirmed_evidence_ids: tuple[str, ...]


def canonical_suggestion_parent(
    profile: MasterProfile,
    bullet: StructuredBullet,
) -> CanonicalSuggestionParent:
    """Resolve a suggestion through authoritative parent and evidence ownership."""

    variant = bullet.writing_variant
    entry_id = variant.entry_id if variant is not None else ""
    if not entry_id:
        owners = {
            item.entity_id
            for item in profile.evidence
            if item.confirmed and item.id in set(bullet.evidence_ids)
        }
        entry_id = next(iter(owners)) if len(owners) == 1 else ""
    return canonical_entry_for_evidence(profile, entry_id, bullet.evidence_ids)


def canonical_entry_for_evidence(
    profile: MasterProfile,
    entry_id: str,
    evidence_ids: list[str],
) -> CanonicalSuggestionParent:
    entries = {item.id: item for item in [*profile.experiences, *profile.projects]}
    entry = entries.get(entry_id)
    if entry is None:
        raise ResumeSuggestionParentError("Suggestion has no canonical profile parent.")
    evidence_owner = {
        item.id: item.entity_id for item in profile.evidence if item.confirmed
    }
    confirmed_ids = tuple(dict.fromkeys(evidence_ids))
    if not confirmed_ids or any(
        evidence_owner.get(item) != entry.id for item in confirmed_ids
    ):
        raise ResumeSuggestionParentError(
            "Suggestion evidence does not belong to its canonical profile parent."
        )
    return CanonicalSuggestionParent(entry=entry, confirmed_evidence_ids=confirmed_ids)


__all__ = [
    "CanonicalSuggestionParent",
    "ResumeSuggestionParentError",
    "canonical_entry_for_evidence",
    "canonical_suggestion_parent",
]
