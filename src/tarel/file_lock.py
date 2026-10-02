"""Small process locks for cooperating local file writers.

Lock files stay in place: unlinking one while a waiter has it open would create
two independent locks. The OS releases the lock when its process exits.
"""

from __future__ import annotations

import errno
import os
import time
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path


@contextmanager
def file_lock(path: Path, *, timeout: float = 30.0) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(descriptor, "r+b") as handle:
        deadline = time.monotonic() + timeout
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                    raise
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Timed out waiting for file lock: {path}") from exc
                time.sleep(0.01)
        try:
            # Windows permits a range past EOF. Initialize only after acquiring
            # it, so two first-time writers cannot write into each other's lock.
            if os.fstat(handle.fileno()).st_size == 0:
                handle.write(b"\0")
                handle.flush()
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def state_write_lock(state_root: Path) -> AbstractContextManager[None]:
    """Serialize document publication and package snapshot capture, not generation."""
    return file_lock(state_root / ".state.lock")
