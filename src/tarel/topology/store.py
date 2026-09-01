"""Atomic dependency-free persistence for logical-topology documents."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Protocol

from tarel.topology.contracts import (
    LogicalTopologyDocument,
    LogicalTopologyFailure,
    validate_logical_topology,
)

_GRAPH_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class LogicalTopologyStore(Protocol):
    def save(self, document: LogicalTopologyDocument) -> Path | str | None: ...

    def load(self, graph_name: str) -> LogicalTopologyDocument: ...

    def list(self) -> tuple[str, ...]: ...

    def exists(self, graph_name: str) -> bool: ...


class FileLogicalTopologyStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path.cwd() / ".tarel" / "logical-topology"

    def save(self, document: LogicalTopologyDocument) -> Path:
        validate_logical_topology(document)
        path = self.path(document.graph_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            document.to_dict(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=".logical-topology-",
            suffix=".tmp",
            text=True,
        )
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise LogicalTopologyFailure(
                "logical_topology_save_failed",
                f"Could not save logical topology for graph: {document.graph_name}",
            ) from exc
        return path

    def load(self, graph_name: str) -> LogicalTopologyDocument:
        try:
            payload = json.loads(
                self.path(graph_name).read_text(encoding="utf-8"),
                object_pairs_hook=_unique_object,
            )
        except FileNotFoundError as exc:
            raise LogicalTopologyFailure(
                "logical_topology_not_found",
                f"Logical topology not found for graph: {graph_name}",
            ) from exc
        except (OSError, ValueError) as exc:
            raise LogicalTopologyFailure(
                "invalid_logical_topology",
                f"Could not read logical topology for graph: {graph_name}",
            ) from exc
        if not isinstance(payload, dict):
            raise LogicalTopologyFailure(
                "invalid_logical_topology", "Logical-topology root must be an object."
            )
        document = LogicalTopologyDocument.from_dict(payload)
        if document.graph_name != graph_name:
            raise LogicalTopologyFailure(
                "invalid_logical_topology",
                "Stored logical-topology graph name does not match its directory.",
            )
        return document

    def list(self) -> tuple[str, ...]:
        if not self.root.exists():
            return ()
        return tuple(
            sorted(
                path.parent.name
                for path in self.root.glob("*/topology.json")
                if path.is_file()
            )
        )

    def exists(self, graph_name: str) -> bool:
        return self.path(graph_name).is_file()

    def path(self, graph_name: str) -> Path:
        if not _GRAPH_NAME.fullmatch(graph_name):
            raise LogicalTopologyFailure(
                "invalid_logical_topology_graph_name",
                "Graph names may contain letters, numbers, dots, underscores, and hyphens.",
            )
        return self.root / graph_name / "topology.json"


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result
