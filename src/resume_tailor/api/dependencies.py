from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from resume_tailor.application.job_discovery.confirmation import (
    ConfirmJobSearchPreferencesService,
)
from resume_tailor.application.job_discovery.preferences import (
    SuggestJobSearchPreferencesService,
)
from resume_tailor.application.job_discovery.queries import (
    GetCurrentJobSearchPreferencesService,
    GetDiscoveryRunService,
)
from resume_tailor.application.job_discovery.refresh import RefreshJobDiscoveryService


@dataclass
class JobDiscoveryServiceBundle:
    suggest_preferences: SuggestJobSearchPreferencesService
    refresh: RefreshJobDiscoveryService
    confirm_preferences: ConfirmJobSearchPreferencesService | None = None
    current_preferences: GetCurrentJobSearchPreferencesService | None = None
    runs: GetDiscoveryRunService | None = None
    close_resources: Callable[[], None] | None = None

    def close(self) -> None:
        if self.close_resources is not None:
            close_resources = self.close_resources
            self.close_resources = None
            close_resources()


def get_job_discovery_services() -> JobDiscoveryServiceBundle:
    from resume_tailor.infrastructure.dependencies import create_job_discovery_services

    return create_job_discovery_services()


__all__ = ["JobDiscoveryServiceBundle", "get_job_discovery_services"]
