"""Strict readers for browser request payloads; each raises ``UIFailure`` (HTTP 400)."""

from __future__ import annotations

from typing import Any

from tarel.ui.contracts import UIFailure


def require_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise UIFailure("invalid_request", f"UI field must be a non-empty string: {key}")
    return value.strip()


def optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise UIFailure("invalid_request", "Optional UI field must be a string or null.")
    return value.strip() or None


def require_object(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise UIFailure("invalid_request", f"UI field must be an object: {key}")
    return value


def string_list(payload: dict[str, Any], key: str) -> tuple[str, ...]:
    value = payload.get(key, [])
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise UIFailure("invalid_request", f"UI field must be an array of strings: {key}")
    return tuple(item.strip() for item in value)


def require_boolean(payload: dict[str, Any], key: str, *, default: bool) -> bool:
    value = payload.get(key, default)
    if not isinstance(value, bool):
        raise UIFailure("invalid_request", f"UI field must be a boolean: {key}")
    return value


def require_integer(
    payload: dict[str, Any],
    key: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise UIFailure("invalid_request", f"UI field is outside its allowed range: {key}")
    return value
