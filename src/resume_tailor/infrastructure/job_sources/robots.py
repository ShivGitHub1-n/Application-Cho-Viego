from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol
from urllib.parse import unquote_to_bytes, urlsplit

import httpx


class _RobotsHttpClient(Protocol):
    def get_sync(self, url: str, *, headers: dict[str, str] | None = None) -> httpx.Response: ...


class RobotsDecision(StrEnum):
    ALLOW = "allow"
    DISALLOW = "disallow"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RobotsFetchResult:
    decision: RobotsDecision
    rules: RobotsRules | None
    reason: str


@dataclass(frozen=True)
class RobotsCacheEntry:
    fetched_at: datetime
    rules: RobotsRules

    def is_fresh(self, now: datetime) -> bool:
        return now - self.fetched_at <= timedelta(hours=24)


class RobotsChecker:
    """One source-aware, fail-closed robots authority for explicit retrieval."""

    def __init__(
        self,
        client: _RobotsHttpClient,
        *,
        user_agent: str = "Cho-Viego/1.0",
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._client = client
        self._user_agent = user_agent
        self._now = now or (lambda: datetime.now(UTC))
        self._cache: dict[str, RobotsCacheEntry] = {}

    def __call__(self, url: str) -> bool:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").casefold().rstrip(".")
        if parsed.scheme.casefold() != "https" or not host:
            return False
        current = self._now()
        cached = self._cache.get(host)
        if cached is not None and cached.is_fresh(current):
            return (
                cached.rules.decide(parsed.path or "/", user_agent=self._user_agent)
                is not RobotsDecision.DISALLOW
            )
        try:
            response = self._client.get_sync(
                f"https://{host}/robots.txt",
                headers={"User-Agent": self._user_agent},
            )
        except Exception:
            return False
        result = evaluate_robots_response(
            response.status_code,
            response.content,
            cache=cached,
            now=current,
        )
        if result.rules is not None:
            self._cache[host] = RobotsCacheEntry(current, result.rules)
            return result.rules.decide(
                parsed.path or "/", user_agent=self._user_agent
            ) is not RobotsDecision.DISALLOW
        return result.decision is RobotsDecision.ALLOW


def _decode_path(value: str) -> str:
    if re.search(r"%(?![0-9a-fA-F]{2})", value):
        raise ValueError("invalid percent encoding")
    try:
        return unquote_to_bytes(value).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("robots path is not valid UTF-8") from exc


@dataclass(frozen=True)
class _Rule:
    allow: bool
    pattern: str

    @property
    def length(self) -> int:
        return len(self.pattern.replace("*", "").rstrip("$"))

    def matches(self, path: str) -> bool:
        candidate = _decode_path(urlsplit(path).path or "/")
        pattern = _decode_path(self.pattern)
        terminal = pattern.endswith("$")
        if terminal:
            pattern = pattern[:-1]
        expression = "^" + ".*".join(re.escape(part) for part in pattern.split("*"))
        if terminal:
            expression += "$"
        return re.match(expression, candidate, flags=re.DOTALL) is not None


@dataclass(frozen=True)
class RobotsRules:
    groups: dict[str, tuple[_Rule, ...]]

    def decide(self, path: str, *, user_agent: str = "Cho-Viego/1.0") -> RobotsDecision:
        product_token = user_agent.lower().split("/", 1)[0].split()[0]
        selected = self.groups.get(product_token) or self.groups.get("*")
        if selected is None:
            return RobotsDecision.UNKNOWN
        matches = [rule for rule in selected if rule.matches(path)]
        if not matches:
            return RobotsDecision.ALLOW
        winner = max(matches, key=lambda rule: (rule.length, rule.allow))
        return RobotsDecision.ALLOW if winner.allow else RobotsDecision.DISALLOW


def parse_robots(text: str | bytes, *, max_bytes: int = 500 * 1024) -> RobotsRules:
    if isinstance(text, bytes):
        if len(text) > max_bytes:
            raise ValueError("robots policy exceeds maximum size")
        try:
            source = text.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("robots policy is not valid UTF-8") from exc
    else:
        if len(text.encode("utf-8")) > max_bytes:
            raise ValueError("robots policy exceeds maximum size")
        source = text
    groups: dict[str, list[_Rule]] = {}
    agents: list[str] = []
    saw_rule = False
    saw_content = False
    for raw_line in source.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            agents = []
            saw_rule = False
            continue
        saw_content = True
        if ":" not in line:
            continue
        name, value = (part.strip() for part in line.split(":", 1))
        field = name.lower()
        if field == "user-agent":
            if saw_rule:
                agents = []
                saw_rule = False
            agent = value.lower().split("/", 1)[0].split()[0] if value else ""
            if not agent:
                raise ValueError("robots user-agent is empty")
            agents.append(agent)
            groups.setdefault(agent, [])
        elif field in {"allow", "disallow"} and agents:
            if value:
                rule = _Rule(field == "allow", value)
                for agent in agents:
                    groups[agent].append(rule)
            saw_rule = True
        else:
            continue
    if saw_content and not groups:
        raise ValueError("robots policy contains no user-agent group")
    return RobotsRules({key: tuple(value) for key, value in groups.items()})


def evaluate_robots_response(
    status_code: int,
    body: str | bytes | None,
    *,
    cache: RobotsCacheEntry | None = None,
    now: datetime | None = None,
) -> RobotsFetchResult:
    current = now or datetime.now(UTC)
    if status_code in {404, 410}:
        return RobotsFetchResult(RobotsDecision.ALLOW, None, "robots policy absent")
    if status_code in {401, 403}:
        return RobotsFetchResult(RobotsDecision.UNKNOWN, None, "robots access requires review")
    if status_code == 429 or status_code >= 500 or status_code <= 0:
        return RobotsFetchResult(RobotsDecision.DISALLOW, None, "robots retrieval failed")
    if cache is not None and cache.is_fresh(current):
        return RobotsFetchResult(RobotsDecision.ALLOW, cache.rules, "fresh cached policy")
    if status_code < 200 or status_code >= 300:
        return RobotsFetchResult(RobotsDecision.DISALLOW, None, "robots status is not approved")
    if body is None:
        return RobotsFetchResult(RobotsDecision.DISALLOW, None, "robots body missing")
    try:
        rules = parse_robots(body)
    except ValueError:
        return RobotsFetchResult(RobotsDecision.DISALLOW, None, "robots policy is unparseable")
    return RobotsFetchResult(RobotsDecision.ALLOW, rules, "robots policy parsed")


__all__ = [
    "RobotsCacheEntry",
    "RobotsChecker",
    "RobotsDecision",
    "RobotsFetchResult",
    "RobotsRules",
    "evaluate_robots_response",
    "parse_robots",
]
