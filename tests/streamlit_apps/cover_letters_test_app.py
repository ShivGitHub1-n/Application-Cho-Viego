from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import streamlit as st

from resume_tailor.frontend.cover_letters_page import (
    CoverLettersDependencies,
    render_cover_letters_page,
)


def _clear_cover_letter_state() -> None:
    for key in (
        "cover_letter",
        "cover_letter_reviewed",
        "cover_letter_profile_fingerprint",
        "cover_letter_posting_fingerprint",
        "cover_letter_plan_fingerprint",
        "cover_letter_evidence_fingerprint",
        "cover_letter_recipient_fingerprint",
    ):
        st.session_state.pop(key, None)


@dataclass(frozen=True)
class _Claim:
    id: str
    text: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class _Paragraph:
    text: str
    claims: tuple[_Claim, ...]


@dataclass(frozen=True)
class _Letter:
    recipient: Any
    paragraphs: tuple[_Paragraph, ...]
    pending_claims: tuple[_Claim, ...]
    complete_review_confirmed: bool = False
    date_text: str = "August 5, 2026"
    salutation: str = "Dear hiring team,"
    closing: str = "Thank you for your consideration."
    signoff: str = "Sincerely,"
    signoff_name: str = "Example Candidate"
    export_path: Path | None = None
    page_count: int = 1


class _Posting:
    title = "Embedded Firmware Engineer"
    company_name = "Example Robotics"

    def model_dump_json(self) -> str:
        return '{"posting":"offline"}'


class _Plan:
    strategy = SimpleNamespace(primary_focus="Embedded systems")
    selected_entity_ids = ("experience-one",)

    def model_dump_json(self) -> str:
        return '{"plan":"offline"}'


class OfflineCoverLetterService:
    def draft_cover_letter(
        self, profile: object, posting: object, plan: object, *, recipient: Any
    ) -> _Letter:
        st.session_state["cover-letter-service-calls"] = (
            st.session_state.get("cover-letter-service-calls", 0) + 1
        )
        claims = (
            _Claim("claim-1", "Led the firmware program", ("evidence-one",)),
            _Claim("claim-2", "Improved the release process", ("evidence-two",)),
        )
        return _Letter(
            recipient=recipient,
            paragraphs=(
                _Paragraph("I bring evidence-backed embedded experience.", claims),
            ),
            pending_claims=claims,
        )

    def approve_cover_letter(
        self, letter: _Letter, approved_ids: set[str], *, reviewed: bool
    ) -> _Letter:
        st.session_state["cover-letter-approved-ids"] = set(approved_ids)
        return replace(letter, pending_claims=(), complete_review_confirmed=reviewed)

    def export_cover_letter(self, letter: _Letter, directory: Path) -> _Letter:
        if st.session_state.get("cover-test-export-mode") == "unavailable":
            from resume_tailor.infrastructure.rendering import PageCountVerificationError

            raise PageCountVerificationError("offline exact verification unavailable")
        output = directory / "offline-cover-letter.docx"
        output.write_bytes(b"offline-docx")
        return replace(letter, export_path=output, page_count=1)


st.set_page_config(layout="wide")
st.session_state.setdefault("cover-letter-service-calls", 0)
if "profile" not in st.session_state:
    from resume_tailor.domain.models import MasterProfile

    fixture_path = Path(__file__).parents[1] / "fixtures" / "profile_completeness.json"
    st.session_state["profile"] = MasterProfile.model_validate(
        json.loads(fixture_path.read_text(encoding="utf-8"))
    )
st.session_state.setdefault("posting", _Posting())
st.session_state.setdefault("plan", _Plan())
render_cover_letters_page(
    st,
    CoverLettersDependencies(
        tailor_service=OfflineCoverLetterService(),
        clear_cover_letter_state=_clear_cover_letter_state,
    ),
)
