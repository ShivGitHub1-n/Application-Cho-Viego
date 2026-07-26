from __future__ import annotations

import ipaddress


class HostnameValidationError(ValueError):
    """A hostname is not a safe canonical DNS name."""


def normalize_hostname(value: str, *, allow_ip: bool = False) -> str:
    if not isinstance(value, str) or not value or any(char.isspace() for char in value):
        raise HostnameValidationError("hostname must be a non-empty value without whitespace")
    if "*" in value or "/" in value or "@" in value or ":" in value:
        raise HostnameValidationError("hostname must be a concrete DNS name")
    candidate = value.rstrip(".").lower()
    if not candidate:
        raise HostnameValidationError("hostname must contain a label")
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        address = None
    if address is not None:
        if not allow_ip:
            raise HostnameValidationError("IP-literal hosts are not allowed")
        return address.compressed.lower()
    labels = candidate.split(".")
    if any(not label for label in labels):
        raise HostnameValidationError("hostname contains an empty label")
    try:
        ascii_labels = [label.encode("idna").decode("ascii") for label in labels]
    except UnicodeError as exc:
        raise HostnameValidationError("hostname is not valid IDNA") from exc
    if any(len(label) > 63 for label in ascii_labels) or len(".".join(ascii_labels)) > 253:
        raise HostnameValidationError("hostname exceeds DNS length limits")
    return ".".join(ascii_labels)


def hostname_is_same_or_subdomain(candidate: str, allowed: str) -> bool:
    normalized_candidate = normalize_hostname(candidate)
    normalized_allowed = normalize_hostname(allowed)
    return normalized_candidate == normalized_allowed or normalized_candidate.endswith(
        f".{normalized_allowed}"
    )


__all__ = ["HostnameValidationError", "hostname_is_same_or_subdomain", "normalize_hostname"]
