from __future__ import annotations

from html import unescape
from html.parser import HTMLParser
import re


_ESCAPED_TAG_PATTERN = re.compile(
    r"(?:&lt;|&amp;lt;)\s*/?\s*"
    r"[a-z][a-z0-9:-]*(?:\s+[^<>]*?)?\s*/?\s*"
    r"(?:&gt;|&amp;gt;)",
    re.IGNORECASE,
)
_MAX_TAG_DECODE_PASSES = 2


def _decode_escaped_tag(match: re.Match[str]) -> str:
    value = match.group(0)
    for _ in range(_MAX_TAG_DECODE_PASSES):
        decoded = unescape(value)
        if decoded == value:
            break
        value = decoded
    return value


class _PlainTextHTMLParser(HTMLParser):
    _BLOCK_TAGS = {
        "address",
        "article",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "p",
        "section",
        "tr",
    }
    _SKIPPED_TAGS = {"script", "style", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skipped_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        if tag in self._SKIPPED_TAGS:
            self._skipped_depth += 1
        elif not self._skipped_depth and tag == "br":
            self.parts.append("\n")
        elif not self._skipped_depth and tag == "li":
            self.parts.append("\n- ")
        elif not self._skipped_depth and tag in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag in self._SKIPPED_TAGS and self._skipped_depth:
            self._skipped_depth -= 1
        elif not self._skipped_depth and tag in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if not self._skipped_depth and tag.casefold() == "br":
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skipped_depth:
            self.parts.append(data)


def normalize_job_description_for_display(description: str) -> str:
    """Convert untrusted provider markup into readable text for plain UI output."""

    decoded_description = _ESCAPED_TAG_PATTERN.sub(_decode_escaped_tag, description)

    parser = _PlainTextHTMLParser()
    parser.feed(decoded_description)
    parser.close()
    text = "".join(parser.parts)
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


__all__ = ["normalize_job_description_for_display"]
