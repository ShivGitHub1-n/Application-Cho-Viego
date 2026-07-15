from __future__ import annotations

import hashlib
from datetime import datetime


def _digest(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:24]


def job_id(connector_type: str, source_id: str, external_job_id: str) -> str:
    return f"job-{_digest(connector_type, source_id, external_job_id)}"


def run_id(
    user_id: str,
    profile_id: str,
    profile_version: str | int,
    preference_version: str | int,
    started_at: datetime,
) -> str:
    digest = _digest(
        user_id,
        profile_id,
        str(profile_version),
        str(preference_version),
        started_at.isoformat(),
    )
    return f"run-{digest}"


def recommendation_id(
    run_identifier: str,
    job_identifier: str,
    profile_version: str | int,
    preference_version: str | int,
) -> str:
    digest = _digest(
        run_identifier,
        job_identifier,
        str(profile_version),
        str(preference_version),
    )
    return f"rec-{digest}"


def saved_job_id(user_id: str, job_identifier: str) -> str:
    return f"saved-{_digest(user_id, job_identifier)}"
