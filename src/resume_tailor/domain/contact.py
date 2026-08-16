from __future__ import annotations

import re
from urllib.parse import urlsplit

_WEB_SCHEMES = {"http", "https"}


def normalize_contact_destination(value: str) -> str | None:
    """Return a safe external contact target without guessing missing personal data."""

    text = _repair_escaped_scheme(value.strip())
    if not text or any(character.isspace() for character in text):
        return None
    if text.casefold().startswith("mailto:"):
        address = text[7:]
        return text if address and "@" in address and "\\" not in address else None
    if "@" in text and "://" not in text and "/" not in text:
        return f"mailto:{text}" if "\\" not in text else None
    has_explicit_scheme = "://" in text
    if not has_explicit_scheme:
        bare_host = text.split("/", 1)[0]
        if not bare_host.casefold().startswith("www.") and "." not in bare_host:
            return None
    candidate = text if has_explicit_scheme else f"https://{text}"
    if "\\" in candidate:
        return None
    parsed = urlsplit(candidate)
    if parsed.scheme.casefold() not in _WEB_SCHEMES or not parsed.hostname:
        return None
    return candidate


def contact_destination_key(value: str) -> str:
    normalized = normalize_contact_destination(value)
    return (normalized or _repair_escaped_scheme(value.strip())).casefold().rstrip("/")


def compact_contact_display(value: str) -> str:
    """Remove transport-only URL syntax while preserving reviewed host/path ordering."""

    cleaned = _repair_escaped_scheme(value.strip())
    normalized = normalize_contact_destination(cleaned)
    if normalized is None:
        return cleaned.replace("\\", "")
    if normalized.casefold().startswith("mailto:"):
        return normalized[7:]
    parsed = urlsplit(normalized)
    host = parsed.netloc.removeprefix("www.")
    path = parsed.path.rstrip("/")
    return f"{host}{path}" if path else host


def compact_contact_label(value: str) -> str:
    """Derive a compact, non-personal label for a legacy contact destination."""

    normalized = normalize_contact_destination(value)
    if normalized is None:
        return re.sub(r"\\+(?=[:/])", "", value.strip())
    if normalized.casefold().startswith("mailto:"):
        return "Email"
    parsed = urlsplit(normalized)
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    path_tokens = {
        token
        for token in re.split(r"[^a-z0-9]+", parsed.path.casefold())
        if token
    }
    if host == "linkedin.com" or host.endswith(".linkedin.com"):
        return "LinkedIn"
    if host == "github.com" or host.endswith(".github.com"):
        return "GitHub"
    if "portfolio" in host or path_tokens.intersection({"portfolio", "projects", "work"}):
        return "Portfolio"
    return "Website"


def safe_contact_display(display_text: str, destination: str | None = None) -> str:
    cleaned = _repair_escaped_scheme(display_text.strip())
    if not cleaned:
        return compact_contact_label(destination or "")
    if normalize_contact_destination(cleaned) is not None:
        return compact_contact_label(destination or cleaned)
    return re.sub(r"\\+(?=[:/])", "", cleaned)


def _repair_escaped_scheme(value: str) -> str:
    return re.sub(r"^(https?)\\://", r"\1://", value, flags=re.IGNORECASE)


__all__ = [
    "compact_contact_display",
    "compact_contact_label",
    "contact_destination_key",
    "normalize_contact_destination",
    "safe_contact_display",
]
