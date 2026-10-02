"""Atomic local JSON graph store."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from tarel.file_lock import file_lock, state_write_lock
from tarel.graph.contracts import GraphDocument, GraphFailure
from tarel.graph.revision import graph_revision

if TYPE_CHECKING:
    from tarel.graph.selective import (
        GraphHeader,
        GraphObjectPage,
        GraphObjectSchemaHashes,
        GraphSlice,
    )

_GRAPH_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class GraphStore(Protocol):
    """Whole-document persistence boundary for local or shared graph stores."""

    def save(self, graph: GraphDocument) -> Path | str | None: ...

    def load(self, name: str) -> GraphDocument: ...

    def list(self) -> tuple[str, ...]: ...


class FileGraphStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path.cwd() / ".tarel" / "graphs"

    @contextmanager
    def _write_lock(self, name: str) -> Iterator[None]:
        try:
            with file_lock(self.path(name).with_name(".write.lock")):
                yield
        except TimeoutError as exc:
            raise GraphFailure("graph_busy", f"Graph is busy; retry: {name}") from exc
        except OSError as exc:
            raise GraphFailure("graph_save_failed", f"Could not write graph: {name}") from exc

    def save(self, graph: GraphDocument, *, expected_revision: str | None = None) -> Path:
        with self._write_lock(graph.name):
            if (
                expected_revision is not None
                and graph_revision(self.load(graph.name)) != expected_revision
            ):
                raise GraphFailure("graph_conflict", "Graph changed; reload before saving.")
            return self._save(graph)

    def create(self, graph: GraphDocument) -> Path:
        with self._write_lock(graph.name):
            if self.path(graph.name).exists():
                raise GraphFailure("graph_exists", f"Graph already exists: {graph.name}")
            return self._save(graph)

    def update(
        self, name: str, change: Callable[[GraphDocument], GraphDocument]
    ) -> tuple[GraphDocument, Path]:
        """Apply a short local transformation to the latest graph under its lock."""
        with self._write_lock(name):
            current = self.load(name)
            updated = change(current)
            if updated.name != name:
                raise GraphFailure("invalid_graph_name", "An update cannot rename a graph.")
            path = self.path(name) if updated == current else self._save(updated)
            return updated, path

    def _save(self, graph: GraphDocument) -> Path:
        path = self.path(graph.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(graph.to_dict(), indent=2, ensure_ascii=False, sort_keys=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=".graph-",
            suffix=".tmp",
            text=True,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.write("\n")
            with state_write_lock(self.root.parent):
                os.replace(temporary_path, path)
        except OSError as exc:
            temporary_path.unlink(missing_ok=True)
            raise GraphFailure("graph_save_failed", f"Could not save graph: {graph.name}") from exc
        return path

    def load(self, name: str) -> GraphDocument:
        path = self.path(name)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise GraphFailure("graph_not_found", f"Graph not found: {name}") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise GraphFailure("invalid_graph", f"Could not read graph: {name}") from exc
        if not isinstance(data, dict):
            raise GraphFailure("invalid_graph", f"Graph root must be an object: {name}")
        return GraphDocument.from_dict(data)

    def list(self) -> tuple[str, ...]:
        if not self.root.exists():
            return ()
        return tuple(
            sorted(path.parent.name for path in self.root.glob("*/graph.json") if path.is_file())
        )

    def header(self, name: str) -> GraphHeader:
        """Read graph identity without materializing nodes after a visible cold bootstrap."""
        from tarel.graph.selective import read_header

        return read_header(self, name)

    def read_slice(
        self,
        name: str,
        object_ids: tuple[str, ...],
        *,
        expected_revision: str | None = None,
        namespace: str | None = None,
        include_fields: bool = True,
    ) -> GraphSlice:
        from tarel.graph.selective import read_slice

        return read_slice(
            self,
            name,
            object_ids,
            expected_revision=expected_revision,
            namespace=namespace,
            include_fields=include_fields,
        )

    def list_objects(
        self,
        name: str,
        *,
        object_ids: tuple[str, ...] | None = None,
        namespace: str | None = None,
        offset: int = 0,
        limit: int = 100,
        expected_revision: str | None = None,
    ) -> GraphObjectPage:
        from tarel.graph.selective import list_objects

        return list_objects(
            self,
            name,
            object_ids=object_ids,
            namespace=namespace,
            offset=offset,
            limit=limit,
            expected_revision=expected_revision,
        )

    def rebuild_index(self, name: str) -> GraphHeader:
        """Explicitly replace a damaged or missing optional selective-read cache."""
        from tarel.graph.selective import rebuild_index

        return rebuild_index(self, name)

    def object_schema_hashes(
        self,
        name: str,
        object_ids: tuple[str, ...],
        *,
        expected_revision: str | None = None,
    ) -> GraphObjectSchemaHashes:
        from tarel.graph.selective import object_schema_hashes

        return object_schema_hashes(self, name, object_ids, expected_revision=expected_revision)

    def path(self, name: str) -> Path:
        if not _GRAPH_NAME.fullmatch(name):
            raise GraphFailure(
                "invalid_graph_name",
                "Graph names may contain letters, numbers, dots, underscores, and hyphens.",
            )
        return self.root / name / "graph.json"
