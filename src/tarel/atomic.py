"""Crash-safe replacement of state files.

Every file store writes the same way: the new content goes to a temporary file in the target
directory, which is then renamed over the old file. Readers therefore see either the previous or
the new document, never a partial one, even if the process dies mid-write.
"""

from __future__ import annotations

import os
import tempfile
from contextlib import nullcontext
from pathlib import Path

from tarel.file_lock import state_write_lock


def sync_directory(directory: Path) -> None:
    """Make a finished rename survive power loss. Windows has no such call for directories."""
    if os.name == "nt":
        return
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_atomic(
    path: Path,
    text: str,
    *,
    prefix: str,
    durable: bool = False,
    lock_root: Path | None = None,
) -> None:
    """Replace ``path`` with ``text`` atomically.

    The temporary file is created with mode ``0600`` and named ``<prefix>*.tmp``. ``durable``
    flushes it and the directory entry to disk. ``lock_root`` holds that state root's write lock
    around the rename so concurrent writers serialize. On failure the temporary file is removed and
    the ``OSError`` propagates; callers translate it into their domain failure.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=prefix, suffix=".tmp")
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            if durable:
                handle.flush()
                os.fsync(handle.fileno())
        with state_write_lock(lock_root) if lock_root is not None else nullcontext():
            temporary.replace(path)
            if durable:
                sync_directory(path.parent)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
