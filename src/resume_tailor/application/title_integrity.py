from __future__ import annotations

import re

from resume_tailor.application.resume_features import normalize_reviewed_text

_ROLE_NOUN = (
    r"(?:architect|developer|designer|director|engineer|intern|lead|manager|"
    r"specialist|technician)"
)
_TITLE_WORD = r"[A-Za-z][A-Za-z0-9+#./-]*"
_ASSERTED_TITLE_PATTERNS = (
    re.compile(
        rf"\b(?:as|serving as|in the role of)\s+(?:an?\s+|the\s+)?"
        rf"(?P<title>(?:{_TITLE_WORD}\s+){{0,5}}{_ROLE_NOUN})"
        r"(?=\s+(?:at|for|on|within)\b|[,.;:]|$)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"^\s*(?P<title>(?:{_TITLE_WORD}\s+){{0,5}}{_ROLE_NOUN})\s*:",
        re.IGNORECASE,
    ),
)


def asserted_role_titles(text: str) -> tuple[str, ...]:
    """Return explicit role-title assertions without inferring from action verbs."""

    titles: list[str] = []
    for pattern in _ASSERTED_TITLE_PATTERNS:
        titles.extend(match.group("title").strip() for match in pattern.finditer(text))
    return tuple(dict.fromkeys(titles))


def conflicting_role_titles(text: str, authoritative_title: str) -> tuple[str, ...]:
    authoritative = normalize_reviewed_text(authoritative_title)
    return tuple(
        title
        for title in asserted_role_titles(text)
        if normalize_reviewed_text(title) != authoritative
    )


def remove_conflicting_title_authority(text: str, authoritative_title: str) -> str:
    """Remove conflicting title assertions from scoring text, never display text."""

    cleaned = text
    for pattern in _ASSERTED_TITLE_PATTERNS:
        cleaned = pattern.sub(
            lambda match: (
                match.group(0)
                if normalize_reviewed_text(match.group("title"))
                == normalize_reviewed_text(authoritative_title)
                else " "
            ),
            cleaned,
        )
    return " ".join(cleaned.split())


__all__ = [
    "asserted_role_titles",
    "conflicting_role_titles",
    "remove_conflicting_title_authority",
]
