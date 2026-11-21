"""Base class and small helpers shared by the SDK facades."""

from __future__ import annotations

from pathlib import Path

from tarel.runtime import TarelRuntime


class RuntimeAPI:
    """A facade bound to one :class:`TarelRuntime`; every use case it calls gets that runtime."""

    __slots__ = ("_runtime",)

    def __init__(self, runtime: TarelRuntime) -> None:
        self._runtime = runtime


def optional_path(value: str | Path | None) -> Path | None:
    """Accept ``str`` paths from SDK callers without turning ``None`` into ``Path("None")``."""
    return None if value is None else Path(value)
