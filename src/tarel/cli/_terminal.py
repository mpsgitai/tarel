"""Small, dependency-free terminal styling for interactive commands.

Colour appears only on a real terminal and never with ``NO_COLOR``. Symbols fall back to ASCII
when the console encoding cannot show them (old Windows code pages), so nothing ever crashes or
prints mojibake.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import TextIO

_SYMBOLS = {"ok": "✓", "fail": "✗", "pointer": "›", "rule": "─", "busy": "◦", "dot": "·"}
_ASCII = {"ok": "+", "fail": "x", "pointer": ">", "rule": "-", "busy": "*", "dot": "-"}


@dataclass(frozen=True)
class Style:
    color: bool
    unicode: bool
    live: bool

    @classmethod
    def for_stream(cls, stream: TextIO) -> Style:
        tty = stream.isatty()
        color = tty and "NO_COLOR" not in os.environ and _enable_windows_ansi()
        encoding = getattr(stream, "encoding", None) or "ascii"
        try:
            "".join(_SYMBOLS.values()).encode(encoding)
            unicode = True
        except (UnicodeEncodeError, LookupError):
            unicode = False
        return cls(color=color, unicode=unicode, live=tty)

    def symbol(self, name: str) -> str:
        return (_SYMBOLS if self.unicode else _ASCII)[name]

    def text(self, value: str) -> str:
        """Make arbitrary text printable, e.g. the ``·`` inside target labels."""
        return value if self.unicode else value.replace(_SYMBOLS["dot"], _ASCII["dot"])

    def _wrap(self, code: str, value: str) -> str:
        return f"\033[{code}m{value}\033[0m" if self.color else value

    def bold(self, value: str) -> str:
        return self._wrap("1", value)

    def dim(self, value: str) -> str:
        return self._wrap("2", value)

    def accent(self, value: str) -> str:
        return self._wrap("36", value)

    def good(self, value: str) -> str:
        return self._wrap("32", value)

    def bad(self, value: str) -> str:
        return self._wrap("31", value)


def _enable_windows_ansi() -> bool:
    # A sys.platform check (not os.name) lets mypy type ctypes.windll on every platform.
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except (AttributeError, OSError):
        return False


def is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()
