"""The exception hierarchy shared by every TAREL package.

Domain packages raise a subclass of :class:`TarelError` (``GraphFailure``, ``LineageFailure``,
...) with a stable machine-readable ``code`` and a human-readable message. Entry adapters catch
the base class once: the CLI prints ``error [code]: message`` (or, with ``--format json``, the
:meth:`TarelError.to_dict` payload) to stderr and exits with status 2, the SDK lets the exception
propagate to the caller, and the browser maps it to an HTTP error.

A failure that the caller can repair by changing its arguments is ``retryable`` and should carry
the repair in ``hint`` and ``details``, so an agent needs one retry instead of a search.
"""

from __future__ import annotations

import difflib
from collections.abc import Iterable
from typing import Any, TypeVar

_PREVIEW_LIMIT = 5


class TarelError(RuntimeError):
    """A rejected TAREL operation with a stable error ``code``."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        hint: str | None = None,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.hint = hint
        self.retryable = retryable
        self.details: dict[str, Any] = dict(details) if details is not None else {}

    def to_dict(self) -> dict[str, object]:
        """``{"error": {...}}`` as the CLI prints it for ``--format json``; empty fields omitted."""
        error: dict[str, object] = {
            "code": self.code,
            "message": str(self),
            "retryable": self.retryable,
        }
        if self.hint:
            error["hint"] = self.hint
        if self.details:
            error["details"] = self.details
        return {"error": error}


ErrorT = TypeVar("ErrorT", bound=TarelError)


def unknown_name_error(
    error_type: type[ErrorT],
    code: str,
    message: str,
    *,
    param: str,
    value: str,
    accepted: Iterable[str],
    noun: str,
) -> ErrorT:
    """A retryable "name not found" failure that previews the names that would be accepted."""
    names = sorted(set(accepted))
    similar = _similar(value, names)
    preview = name_preview(value, names)
    if similar:
        hint = f"Did you mean {', '.join(repr(item) for item in similar)}?"
    elif names:
        more = f" and {len(names) - len(preview)} more" if len(names) > len(preview) else ""
        hint = f"Known {noun} names: {', '.join(preview)}{more}."
    else:
        hint = f"No {noun} exists in this TAREL state yet."
    return error_type(
        code,
        message,
        hint=hint,
        retryable=True,
        details={
            "accepted_count": len(names),
            "accepted_preview": preview,
            "param": param,
            "value": value,
        },
    )


def name_preview(value: str, accepted: Iterable[str]) -> list[str]:
    """At most five accepted names: close spellings of ``value`` first, then sorted order."""
    names = sorted(set(accepted))
    similar = _similar(value, names)
    return [*similar, *(item for item in names if item not in similar)][:_PREVIEW_LIMIT]


def _similar(value: str, names: list[str]) -> list[str]:
    return difflib.get_close_matches(value, names, n=_PREVIEW_LIMIT, cutoff=0.6)
