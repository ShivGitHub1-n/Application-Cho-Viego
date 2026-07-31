from __future__ import annotations

import re
from pathlib import Path

AUDIT = Path(__file__).parents[3] / "docs" / "job-discovery" / "PROVIDER_AUDIT.md"
REQUIRED_FIELDS = (
    "Official mechanism and owner",
    "Access or authentication requirements",
    "Public-job access boundary",
    "Stable job ID authority",
    "Description quality",
    "Location authority",
    "Application URL authority",
    "Posted/update timestamp authority",
    "Pagination",
    "Supported query filters",
    "Rate-limit or retry guidance",
    "Availability-check behavior",
    "Offline fixture testability",
    "Terms or access concerns",
    "Decision",
    "Exact reason for the decision",
    "Date accessed",
)


def test_provider_audit_has_complete_entries_and_one_decision_each() -> None:
    content = AUDIT.read_text(encoding="utf-8")
    sections = re.split(r"(?m)^## ", content)[1:]
    assert {section.splitlines()[0] for section in sections} >= {
        "Greenhouse",
        "Lever",
        "Ashby",
        "SmartRecruiters",
    }
    for section in sections:
        if section.splitlines()[0] not in {"Greenhouse", "Lever", "Ashby", "SmartRecruiters"}:
            continue
        for field in REQUIRED_FIELDS:
            assert f"- {field}:" in section
        assert len(re.findall(r"(?m)^- Decision: (approved|rejected|deferred)$", section)) == 1
