"""Atomic private persistence for resumable discovery runs."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Protocol

from tarel.discovery.contracts import DiscoveryFailure, DiscoveryRun, validate_discovery_run

_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class DiscoveryStore(Protocol):
    def save(self, run: DiscoveryRun) -> Path | str | None: ...

    def load(self, run_id: str) -> DiscoveryRun: ...

    def list(self) -> tuple[str, ...]: ...

    def exists(self, run_id: str) -> bool: ...


class FileDiscoveryStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path.cwd() / ".tarel" / "discovery"

    def save(self, run: DiscoveryRun) -> Path:
        validate_discovery_run(run)
        path = self.path(run.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(run.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=".discovery-",
            suffix=".tmp",
            text=True,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.write("\n")
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise DiscoveryFailure(
                "discovery_save_failed", f"Could not save discovery run: {run.id}"
            ) from exc
        return path

    def load(self, run_id: str) -> DiscoveryRun:
        try:
            payload = json.loads(self.path(run_id).read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise DiscoveryFailure(
                "discovery_not_found", f"Discovery run not found: {run_id}"
            ) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise DiscoveryFailure(
                "invalid_discovery", f"Could not read discovery run: {run_id}"
            ) from exc
        if not isinstance(payload, dict):
            raise DiscoveryFailure("invalid_discovery", "Discovery run root must be an object.")
        run = DiscoveryRun.from_dict(payload)
        if run.id != run_id:
            raise DiscoveryFailure(
                "invalid_discovery", "Stored discovery run ID does not match its directory."
            )
        return run

    def list(self) -> tuple[str, ...]:
        if not self.root.exists():
            return ()
        return tuple(
            sorted(path.parent.name for path in self.root.glob("*/run.json") if path.is_file())
        )

    def exists(self, run_id: str) -> bool:
        return self.path(run_id).is_file()

    def path(self, run_id: str) -> Path:
        if not _RUN_ID.fullmatch(run_id):
            raise DiscoveryFailure(
                "invalid_discovery_id",
                "Discovery IDs may contain letters, numbers, dots, underscores, and hyphens.",
            )
        return self.root / run_id / "run.json"
