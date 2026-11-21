"""The exception hierarchy shared by every TAREL package.

Domain packages raise a subclass of :class:`TarelError` (``GraphFailure``, ``LineageFailure``,
...) with a stable machine-readable ``code`` and a human-readable message. Entry adapters catch
the base class once: the CLI prints ``error [code]: message`` and exits with status 2, the SDK lets
the exception propagate to the caller, and the browser maps it to an HTTP error.
"""

from __future__ import annotations


class TarelError(RuntimeError):
    """A rejected TAREL operation with a stable error ``code``."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
