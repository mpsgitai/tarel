"""A directory as a transport: whatever delivers files there, one pass takes them over.

This only moves files. Every decision about trust, history and activation stays in the same use
case a person calls by hand, so a transport can neither skip a check nor settle a conflict. A file
counts as delivered once it has its final name: uploaders write under another name and rename last.
A truncated file that arrives anyway fails its checks like any other damaged file.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from tarel.errors import TarelError
from tarel.file_lock import file_lock
from tarel.runtime import TarelRuntime, resolve_runtime
from tarel.sync.application import apply_publication_use_case, recover_activations_use_case
from tarel.sync.contracts import SyncFailure
from tarel.sync.envelope import PUBLICATION_SUFFIX
from tarel.sync.results import InboxItem, InboxResult

_DONE = "done"
_REJECTED = "rejected"
# Nothing is wrong with these files, so they wait for the next pass.
_RETRY_LATER = frozenset({"graph_busy", "signature_tool_missing", "sync_busy"})


def process_inbox_use_case(
    directory: Path,
    *,
    min_age_seconds: float = 0,
    allow_unsigned_dev: bool = False,
    runtime: TarelRuntime | None = None,
) -> InboxResult:
    """Run one pass. A scheduler, if any, belongs to whoever calls this."""
    resolved = resolve_runtime(runtime)
    directory = Path(directory)
    if not directory.is_dir():
        raise SyncFailure("inbox_not_found", f"Inbox directory not found: {directory}")
    try:
        with file_lock(directory / ".inbox.lock"):
            recover_activations_use_case(runtime=resolved)
            items = tuple(
                _take(path, min_age_seconds, allow_unsigned_dev, resolved)
                for path in _delivered(directory)
            )
    except TimeoutError as exc:
        raise SyncFailure("sync_busy", f"Another pass is reading {directory}.") from exc
    return InboxResult(tuple(item for item in items if item is not None))


def _delivered(directory: Path) -> tuple[Path, ...]:
    return tuple(
        sorted(
            path
            for path in directory.iterdir()
            if path.name.endswith(PUBLICATION_SUFFIX) and not path.name.startswith(".")
        )
    )


def _take(
    path: Path, min_age_seconds: float, allow_unsigned_dev: bool, runtime: TarelRuntime,
) -> InboxItem | None:
    if path.is_symlink() or not path.is_file():
        return _refuse(path, "invalid_package", "Only regular files are taken from an inbox.")
    if time.time() - path.stat().st_mtime < min_age_seconds:
        return None
    try:
        result = apply_publication_use_case(
            path, allow_unsigned_dev=allow_unsigned_dev, runtime=runtime,
        )
    except TarelError as exc:
        if exc.code in _RETRY_LATER:
            return InboxItem(path.name, "deferred", code=exc.code, message=str(exc))
        return _refuse(path, exc.code, str(exc))
    _move(path, path.parent / _DONE)
    outcome = "applied" if result.applied else "no_change"
    return InboxItem(path.name, outcome, action=result.plan.action)


def _refuse(path: Path, code: str, message: str) -> InboxItem:
    target = _move(path, path.parent / _REJECTED)
    target.with_name(f"{target.name}.reason.json").write_text(
        json.dumps({"code": code, "message": message}, indent=2) + "\n", encoding="utf-8",
    )
    return InboxItem(path.name, "rejected", code=code, message=message)


def _move(path: Path, directory: Path) -> Path:
    directory.mkdir(exist_ok=True)
    target = directory / path.name
    number = 0
    while target.exists():
        number += 1
        target = directory / f"{path.stem}.{number}{path.suffix}"
    path.replace(target)
    return target
