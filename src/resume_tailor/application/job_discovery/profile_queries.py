from __future__ import annotations

from dataclasses import dataclass

from resume_tailor.domain.models import MasterProfile
from resume_tailor.infrastructure.profile_repository import ProfileStoreError
from resume_tailor.ports.interfaces import MasterProfileRepository


@dataclass(frozen=True)
class ReviewedProfileView:
    profile_id: str
    user_id: str
    display_name: str
    version: int

    @property
    def label(self) -> str:
        return self.display_name.strip() or self.profile_id


@dataclass(frozen=True)
class ReviewedProfileQueryResult:
    profiles: list[ReviewedProfileView]
    warning: str | None = None

    @property
    def empty_message(self) -> str:
        return "A reviewed profile is required before discovering jobs."


class ReviewedProfileQueryService:
    """Load valid reviewed profiles through the existing profile repository."""

    def __init__(self, profiles: MasterProfileRepository) -> None:
        self._profiles = profiles

    def list_reviewed_profiles(self) -> ReviewedProfileQueryResult:
        try:
            profiles = self._profiles.list_all()
            views = [_to_view(profile) for profile in profiles]
        except (ProfileStoreError, ValueError):
            return ReviewedProfileQueryResult(
                profiles=[],
                warning="Reviewed profiles are temporarily unavailable.",
            )
        return ReviewedProfileQueryResult(profiles=views)

    def get_reviewed_profile(self, profile_id: str) -> ReviewedProfileView | None:
        """Resolve one reviewed profile through the canonical profile authority."""

        try:
            profile = self._profiles.get(profile_id)
        except (ProfileStoreError, ValueError):
            return None
        return None if profile is None else _to_view(profile)


def _to_view(profile: MasterProfile) -> ReviewedProfileView:
    return ReviewedProfileView(
        profile_id=profile.id,
        user_id=profile.user_id,
        display_name=profile.display_name,
        version=profile.version,
    )


__all__ = [
    "ReviewedProfileQueryResult",
    "ReviewedProfileQueryService",
    "ReviewedProfileView",
]
