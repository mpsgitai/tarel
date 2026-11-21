"""Strict readers for JSON discovery documents; each raises ``DiscoveryFailure`` on bad input."""

from __future__ import annotations

import math
import re
from typing import Any

from tarel.discovery.contracts import DiscoveryFailure

IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


DIALECT_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


MAX_TEXT = 1_000


MAX_FIELDS = 3


MAX_TRANSFORMS = 8


MAX_PARENTS = 4


MAX_CANDIDATES = 200


MAX_PROBES = 1_000


def require_fields(
    data: dict[str, Any],
    required: set[str],
    label: str,
    *,
    optional: set[str] | None = None,
) -> None:
    allowed = required | (optional or set())
    if set(data) - allowed or required - set(data):
        raise DiscoveryFailure(
            "invalid_discovery", f"{label} has unexpected or missing fields."
        )


def require_object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DiscoveryFailure("invalid_discovery", f"{label} must be an object.")
    return value


def require_text(value: object, label: str, *, limit: int = MAX_TEXT) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise DiscoveryFailure(
            "invalid_discovery",
            f"{label} must be a non-empty string of at most {limit} characters.",
        )
    return value.strip()


def optional_text(value: object, label: str) -> str | None:
    return None if value is None else require_text(value, label)


def require_identifier(value: object, label: str) -> str:
    return require_pattern(value, label, IDENTIFIER_PATTERN)


def optional_identifier(value: object, label: str) -> str | None:
    return None if value is None else require_identifier(value, label)


def require_pattern(value: object, label: str, pattern: re.Pattern[str]) -> str:
    clean = require_text(value, label, limit=128)
    if not pattern.fullmatch(clean):
        raise DiscoveryFailure("invalid_discovery", f"{label} has an invalid format.")
    return clean


def require_sha256(value: object, label: str) -> str:
    return require_pattern(value, label, SHA256_PATTERN)


def require_choice(value: object, label: str, choices: frozenset[str]) -> str:
    clean = require_text(value, label, limit=128)
    if clean not in choices:
        raise DiscoveryFailure("invalid_discovery", f"Unsupported {label}: {clean}")
    return clean


def string_array(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise DiscoveryFailure("invalid_discovery", f"{label} must be an array of strings.")
    return tuple(require_text(item, label, limit=256) for item in value)


def identifier_array(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise DiscoveryFailure("invalid_discovery", f"{label} must be an array.")
    result = tuple(require_identifier(item, label) for item in value)
    if len(result) != len(set(result)):
        raise DiscoveryFailure("invalid_discovery", f"{label} must contain unique values.")
    return result


def integer_array(value: object, label: str) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise DiscoveryFailure("invalid_discovery", f"{label} must be an array.")
    result = tuple(require_integer(item, label) for item in value)
    if len(result) != len(set(result)):
        raise DiscoveryFailure("invalid_discovery", f"{label} must contain unique values.")
    return result


def require_integer(value: object, label: str) -> int:
    return bounded_integer(value, label, 0, 2**63 - 1)


def optional_integer(value: object, label: str) -> int | None:
    return None if value is None else require_integer(value, label)


def bounded_integer(value: object, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise DiscoveryFailure(
            "invalid_discovery", f"{label} must be an integer between {minimum} and {maximum}."
        )
    return value


def require_rate(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DiscoveryFailure(
            "invalid_discovery", f"{label} must be a number between 0 and 1."
        )
    result = float(value)
    if not math.isfinite(result) or not 0 <= result <= 1:
        raise DiscoveryFailure(
            "invalid_discovery", f"{label} must be a finite number between 0 and 1."
        )
    return result


def optional_rate(value: object, label: str) -> float | None:
    return None if value is None else require_rate(value, label)


def require_boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise DiscoveryFailure("invalid_discovery", f"{label} must be a boolean.")
    return value
