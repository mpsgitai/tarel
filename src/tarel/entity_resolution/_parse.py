"""Strict readers for entity resolution JSON; each raises ``EntityResolutionFailure``."""

from __future__ import annotations

import math
import re
from typing import Any

from tarel.entity_resolution.contracts import EntityResolutionFailure

IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


MAX_REASON_LENGTH = 1_000


MAX_OPERATIONS = 8


def require_fields(
    data: dict[str, Any],
    required: set[str],
    label: str,
    *,
    optional: set[str] | None = None,
) -> None:
    allowed = required | (optional or set())
    if set(data) - allowed or required - set(data):
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            f"{label} has unexpected or missing fields.",
        )


def require_object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            f"{label} must be an object.",
        )
    return value


def require_text(value: object, label: str, *, limit: int = 256) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            f"{label} must be a non-empty string of at most {limit} characters.",
        )
    return value.strip()


def require_identifier(value: object, label: str) -> str:
    clean = require_text(value, label, limit=128)
    if not IDENTIFIER_PATTERN.fullmatch(clean):
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            f"{label} may contain letters, numbers, dots, underscores, and hyphens.",
        )
    return clean


def require_sha256(value: object, label: str) -> str:
    clean = require_text(value, label, limit=64)
    if not SHA256_PATTERN.fullmatch(clean):
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            f"{label} must be a lowercase SHA-256 value.",
        )
    return clean


def require_choice(value: object, label: str, choices: frozenset[str]) -> str:
    clean = require_text(value, label)
    if clean not in choices:
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            f"Unsupported {label}: {clean}",
        )
    return clean


def string_array(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            f"{label} must be an array of strings.",
        )
    return tuple(require_text(item, label) for item in value)


def identifier_array(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            f"{label} must be an array of identifiers.",
        )
    identifiers = tuple(require_identifier(item, label) for item in value)
    if len(identifiers) != len(set(identifiers)):
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            f"{label} must contain unique identifiers.",
        )
    return identifiers


def require_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            f"{label} must be a non-negative integer.",
        )
    return value


def require_rate(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            f"{label} must be a number between 0 and 1.",
        )
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            f"{label} must be a finite number between 0 and 1.",
        )
    return result
