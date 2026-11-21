"""Contract versions, limits and strict JSON readers for runtime lineage documents."""

from __future__ import annotations

import math
import re
from typing import Any

from tarel.lineage.contracts import LineageFailure

INPUT_VERSION = "tarel.runtime-lineage-input.v0.1"


INPUT_VERSION_V2 = "tarel.runtime-lineage-input.v0.2"


INPUT_VERSION_V3 = "tarel.runtime-lineage-input.v0.3"


INPUT_VERSIONS = frozenset({INPUT_VERSION, INPUT_VERSION_V2, INPUT_VERSION_V3})


DOCUMENT_VERSION = "tarel.runtime-lineage.v0.1"


DOCUMENT_VERSION_V2 = "tarel.runtime-lineage.v0.2"


DOCUMENT_VERSION_V3 = "tarel.runtime-lineage.v0.3"


DOCUMENT_VERSIONS = frozenset({DOCUMENT_VERSION, DOCUMENT_VERSION_V2, DOCUMENT_VERSION_V3})


DIALECTS = frozenset({"duckdb", "postgresql", "sqlite", "sqlserver"})


SQL_STATUSES = frozenset({"failed", "succeeded"})


MONGO_OPERATIONS = frozenset({"aggregate", "find"})


MONGO_STATUSES = frozenset({"failed", "succeeded"})


FEDERATED_STATUSES = frozenset({"accepted", "failed", "succeeded"})


RECONCILIATION_STATUSES = frozenset({"matched", "mismatch", "not_run", "partial"})


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


SAFE_CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


MAX_EVENTS = 1_000


MAX_INPUTS = 512


MAX_COLUMNS = 256


MAX_TEXT_LENGTH = 256


def unique_object(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise LineageFailure("invalid_runtime_lineage", "Runtime JSON has duplicate keys.")
        result[key] = value
    return result


def require_fields(
    data: dict[str, Any],
    expected: set[str],
    label: str,
    *,
    optional: set[str] | None = None,
) -> None:
    allowed = expected | (optional or set())
    unknown = set(data) - allowed
    missing = expected - set(data)
    if unknown or missing:
        raise LineageFailure(
            "invalid_runtime_lineage",
            f"{label} has unexpected or missing fields.",
        )


def require_boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise LineageFailure("invalid_runtime_lineage", f"{label} must be a boolean.")
    return value


def require_object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LineageFailure("invalid_runtime_lineage", f"{label} must be an object.")
    return value


def require_objects(value: object, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise LineageFailure("invalid_runtime_lineage", f"{label} must be an array.")
    return [require_object(item, label) for item in value]


def require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_TEXT_LENGTH:
        raise LineageFailure(
            "invalid_runtime_lineage",
            f"{label} must be a non-empty string of at most {MAX_TEXT_LENGTH} characters.",
        )
    return value.strip()


def require_strings(value: object, label: str, *, limit: int) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > limit:
        raise LineageFailure(
            "invalid_runtime_lineage",
            f"{label} must be an array containing at most {limit} strings.",
        )
    return tuple(require_text(item, label) for item in value)


def require_integer(value: object, label: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise LineageFailure(
            "invalid_runtime_lineage",
            f"{label} must be an integer greater than or equal to {minimum}.",
        )
    return value


def require_rate(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LineageFailure(
            "invalid_runtime_lineage",
            f"{label} must be a number between 0 and 1.",
        )
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise LineageFailure(
            "invalid_runtime_lineage",
            f"{label} must be a finite number between 0 and 1.",
        )
    return result


def require_choice(value: object, label: str, choices: frozenset[str]) -> str:
    selected = require_text(value, label)
    if selected not in choices:
        raise LineageFailure(
            "invalid_runtime_lineage",
            f"{label} must be one of: {', '.join(sorted(choices))}.",
        )
    return selected


def require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
        raise LineageFailure(
            "invalid_runtime_lineage",
            f"{label} must be a lowercase SHA-256 value.",
        )
    return value


def require_safe_code(value: object, label: str) -> str:
    if not isinstance(value, str) or not SAFE_CODE_PATTERN.fullmatch(value):
        raise LineageFailure(
            "invalid_runtime_lineage",
            f"{label} must be a safe identifier, not a URL or free-form message.",
        )
    return value
