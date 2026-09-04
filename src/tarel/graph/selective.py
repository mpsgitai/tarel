"""Experimental, rebuildable selective reads of authoritative JSON graphs.

The SQLite file is an optional derived cache, never a second source of graph truth.
Source and cache filesystem identities are checked around every read. This detects
out-of-band edits without reading every source byte on each warm request.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from tarel.graph.contracts import GraphDocument, GraphEdge, GraphFailure, GraphNode
from tarel.graph.revision import graph_revision, physical_graph_revision, physical_schema_revision

if TYPE_CHECKING:
    from tarel.graph.store import FileGraphStore

_CACHE_VERSION = "tarel.graph.selective-cache.v0.1.experimental"
_MAX_PAGE = 1000


@dataclass(frozen=True, slots=True)
class GraphReadStats:
    mode: str
    full_document_read: bool
    loaded_node_count: int = 0
    loaded_edge_count: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "full_document_read": self.full_document_read,
            "loaded_node_count": self.loaded_node_count,
            "loaded_edge_count": self.loaded_edge_count,
        }


@dataclass(frozen=True, slots=True)
class GraphHeader:
    name: str
    connector: str
    source_type: str
    catalog: str
    dialect: str | None
    contract_version: str
    revision: str
    physical_revision: str
    node_count: int
    edge_count: int
    object_count: int
    read_stats: GraphReadStats

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "connector": self.connector,
            "source_type": self.source_type,
            "catalog": self.catalog,
            "dialect": self.dialect,
            "contract_version": self.contract_version,
            "revision": self.revision,
            "physical_revision": self.physical_revision,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "object_count": self.object_count,
            "storage": self.read_stats.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class GraphSlice:
    header: GraphHeader
    graph: GraphDocument
    object_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.header.to_dict(),
            "object_ids": list(self.object_ids),
            "graph": self.graph.to_dict(),
            "notice": "Selected subgraph only; source revisions describe the complete graph.",
        }


@dataclass(frozen=True, slots=True)
class GraphObjectPage:
    header: GraphHeader
    objects: tuple[GraphNode, ...]
    offset: int
    limit: int
    total_objects: int
    next_offset: int | None

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.header.to_dict(),
            "objects": [node.to_dict() for node in self.objects],
            "offset": self.offset,
            "limit": self.limit,
            "total_objects": self.total_objects,
            "next_offset": self.next_offset,
        }


@dataclass(frozen=True, slots=True)
class GraphObjectSchemaHashes:
    header: GraphHeader
    hashes: tuple[tuple[str, str | None], ...]


def object_schema_hashes(
    store: FileGraphStore,
    name: str,
    object_ids: tuple[str, ...],
    *,
    expected_revision: str | None = None,
) -> GraphObjectSchemaHashes:
    if object_ids is None:
        raise GraphFailure(
            "invalid_graph_selection", "An explicit tuple of object IDs is required."
        )
    _validate_selection(object_ids, None)
    with _open_index(store, name) as (connection, stats):
        header = _header(connection, name, stats)
        _check_revision(header, expected_revision)
        _request_ids(connection, object_ids)
        hashes = tuple(
            connection.execute(
                "SELECT s.object_id,s.sha256 FROM object_schemas s "
                "JOIN requested r ON r.id=s.object_id ORDER BY s.object_id"
            )
        )
        if len(hashes) != len(object_ids):
            raise GraphFailure(
                "graph_object_not_found", "Every selected ID must be a physical object."
            )
        return GraphObjectSchemaHashes(header, hashes)


def read_header(store: FileGraphStore, name: str) -> GraphHeader:
    with _open_index(store, name) as (connection, stats):
        return _header(connection, name, stats)


def read_slice(
    store: FileGraphStore,
    name: str,
    object_ids: tuple[str, ...],
    *,
    expected_revision: str | None = None,
    namespace: str | None = None,
    include_fields: bool = True,
) -> GraphSlice:
    if object_ids is None:
        raise GraphFailure(
            "invalid_graph_selection", "An explicit tuple of object IDs is required."
        )
    _validate_selection(object_ids, namespace)
    if type(include_fields) is not bool:
        raise GraphFailure("invalid_graph_selection", "include_fields must be a boolean.")
    with _open_index(store, name) as (connection, stats):
        header = _header(connection, name, stats)
        _check_revision(header, expected_revision)
        _request_ids(connection, object_ids)
        actual = connection.execute(
            "SELECT n.id FROM nodes n JOIN requested r ON r.id=n.id "
            "WHERE n.type IN ('table','view') AND (? IS NULL OR n.namespace=?)",
            (namespace, namespace),
        ).fetchall()
        if len(actual) != len(object_ids):
            raise GraphFailure(
                "graph_object_not_found",
                "Every selected object must be a physical table or view within the scope.",
            )
        # Include fields and actual containment ancestors, never neighbouring tables
        # merely because they have a foreign key to a selected object.
        connection.execute(
            "CREATE TEMP TABLE selected AS WITH RECURSIVE closure(id) AS ("
            "SELECT id FROM requested UNION "
            "SELECT n.id FROM nodes n JOIN requested r ON r.id=n.object_id "
            "WHERE n.type='field' AND ? UNION "
            "SELECT e.source_id FROM edges e JOIN closure c ON e.target_id=c.id "
            "JOIN nodes p ON p.id=e.source_id WHERE e.type='contains' AND "
            "(p.type IN ('catalog','namespace') OR p.id IN (SELECT id FROM requested))) "
            "SELECT id FROM closure",
            (include_fields,),
        )
        nodes = tuple(
            GraphNode.from_dict(json.loads(row[0]))
            for row in connection.execute(
                "SELECT n.payload FROM nodes n JOIN selected s ON s.id=n.id ORDER BY n.ordinal"
            )
        )
        edges = tuple(
            GraphEdge.from_dict(json.loads(row[0]))
            for row in connection.execute(
                "SELECT e.payload FROM edges e "
                "JOIN selected s ON s.id=e.source_id JOIN selected t ON t.id=e.target_id "
                "ORDER BY e.ordinal"
            )
        )
        graph = GraphDocument(
            name=header.name,
            connector=header.connector,
            source_type=header.source_type,
            catalog=header.catalog,
            dialect=header.dialect,
            contract_version=header.contract_version,
            nodes=nodes,
            edges=edges,
        )
        return GraphSlice(
            header=_with_loaded_counts(header, len(nodes), len(edges)),
            graph=graph,
            object_ids=object_ids,
        )


def list_objects(
    store: FileGraphStore,
    name: str,
    *,
    object_ids: tuple[str, ...] | None = None,
    namespace: str | None = None,
    offset: int = 0,
    limit: int = 100,
    expected_revision: str | None = None,
) -> GraphObjectPage:
    _validate_selection(object_ids, namespace)
    if (
        type(offset) is not int
        or offset < 0
        or type(limit) is not int
        or not 1 <= limit <= _MAX_PAGE
    ):
        raise GraphFailure("invalid_graph_page", "Offset must be non-negative; limit is 1–1000.")
    with _open_index(store, name) as (connection, stats):
        header = _header(connection, name, stats)
        _check_revision(header, expected_revision)
        join = ""
        if object_ids is not None:
            _request_ids(connection, object_ids)
            join = " JOIN requested r ON r.id=n.id"
        predicate = " WHERE n.type IN ('table','view') AND (? IS NULL OR n.namespace=?)"
        parameters = (namespace, namespace)
        total = connection.execute(
            "SELECT COUNT(*) FROM nodes n" + join + predicate,
            parameters,
        ).fetchone()[0]
        objects = tuple(
            GraphNode.from_dict(json.loads(row[0]))
            for row in connection.execute(
                "SELECT n.payload FROM nodes n"
                + join
                + predicate
                + " ORDER BY n.id LIMIT ? OFFSET ?",
                (*parameters, limit, offset),
            )
        )
        next_offset = offset + len(objects) if offset + len(objects) < total else None
        return GraphObjectPage(
            _with_loaded_counts(header, len(objects), 0),
            objects,
            offset,
            limit,
            total,
            next_offset,
        )


def rebuild_index(store: FileGraphStore, name: str) -> GraphHeader:
    path = store.path(name)
    source_fingerprint = _source_fingerprint(path, name)
    _build_index(store, name, source_fingerprint)
    with _open_index(store, name) as (connection, _stats):
        return _header(connection, name, GraphReadStats("cache_rebuilt", True))


@contextmanager
def _open_index(
    store: FileGraphStore,
    name: str,
) -> Iterator[tuple[sqlite3.Connection, GraphReadStats]]:
    source = store.path(name)
    cache, descriptor = _cache_paths(source)
    source_fingerprint = _source_fingerprint(source, name)
    mode = "warm"
    metadata = _descriptor(descriptor) if descriptor.exists() else None
    if metadata is None or metadata.get("source_fingerprint") != source_fingerprint:
        mode = "cache_rebuilt" if cache.exists() or metadata is not None else "cache_built"
        _build_index(store, name, source_fingerprint)
        metadata = _descriptor(descriptor)
    try:
        descriptor_fingerprint = _fingerprint(descriptor)
        cache_fingerprint = _fingerprint(cache)
    except OSError as exc:
        raise _invalid_cache() from exc
    if (
        metadata.get("contract_version") != _CACHE_VERSION
        or metadata.get("cache_fingerprint") != cache_fingerprint
    ):
        raise _invalid_cache()
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(cache.resolve().as_uri() + "?mode=ro", uri=True)
        yield connection, GraphReadStats(mode, mode != "warm")
        if _source_fingerprint(source, name) != source_fingerprint:
            raise GraphFailure(
                "graph_changed_during_read", "Graph changed; retry with its revision."
            )
        if (
            _fingerprint(cache) != cache_fingerprint
            or _fingerprint(descriptor) != descriptor_fingerprint
        ):
            raise GraphFailure(
                "graph_cache_changed_during_read", "Graph cache changed; retry the read."
            )
    except (OSError, sqlite3.Error, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise _invalid_cache() from exc
    finally:
        if connection is not None:
            connection.close()


def _build_index(store: FileGraphStore, name: str, source_fingerprint: list[int]) -> None:
    source = store.path(name)
    graph = store.load(name)
    if graph.name != name:
        raise GraphFailure("invalid_graph", "Stored graph name differs from the requested name.")
    if _source_fingerprint(source, name) != source_fingerprint:
        raise GraphFailure(
            "graph_changed_during_read", "Graph changed during cache creation; retry."
        )
    cache, descriptor = _cache_paths(source)
    temporary: Path | None = None
    connection: sqlite3.Connection | None = None
    try:
        handle, temporary_name = tempfile.mkstemp(
            dir=source.parent, prefix=".selective-", suffix=".tmp"
        )
        os.close(handle)
        temporary = Path(temporary_name)
        connection = sqlite3.connect(temporary)
        connection.executescript(
            "CREATE TABLE header(payload TEXT NOT NULL);"
            "CREATE TABLE nodes(id TEXT PRIMARY KEY, ordinal INTEGER NOT NULL, type TEXT NOT NULL, "
            "object_id TEXT, namespace TEXT, payload TEXT NOT NULL);"
            "CREATE TABLE edges(ordinal INTEGER PRIMARY KEY, source_id TEXT NOT NULL, "
            "target_id TEXT NOT NULL, type TEXT NOT NULL, payload TEXT NOT NULL);"
            "CREATE INDEX node_object ON nodes(object_id);"
            "CREATE INDEX node_scope ON nodes(type,namespace,id);"
            "CREATE INDEX edge_source ON edges(source_id);"
            "CREATE INDEX edge_target ON edges(target_id,type);"
            "CREATE TABLE object_schemas(object_id TEXT PRIMARY KEY, sha256 TEXT);"
        )
        header = GraphHeader(
            name=graph.name,
            connector=graph.connector,
            source_type=graph.source_type,
            catalog=graph.catalog,
            dialect=graph.dialect,
            contract_version=graph.contract_version,
            revision=graph_revision(graph),
            physical_revision=physical_graph_revision(graph),
            node_count=len(graph.nodes),
            edge_count=len(graph.edges),
            object_count=sum(node.type in {"table", "view"} for node in graph.nodes),
            read_stats=GraphReadStats("cache_built", True),
        ).to_dict()
        header.pop("storage")
        connection.execute("INSERT INTO header VALUES (?)", (_json(header),))
        connection.executemany(
            "INSERT INTO nodes VALUES (?,?,?,?,?,?)",
            (
                (
                    node.id,
                    ordinal,
                    node.type,
                    _metadata_text(node, "object_id"),
                    _metadata_text(node, "namespace"),
                    _json(node.to_dict()),
                )
                for ordinal, node in enumerate(graph.nodes)
            ),
        )
        connection.executemany(
            "INSERT INTO edges VALUES (?,?,?,?,?)",
            (
                (ordinal, edge.source_id, edge.target_id, edge.type, _json(edge.to_dict()))
                for ordinal, edge in enumerate(graph.edges)
            ),
        )
        connection.executemany("INSERT INTO object_schemas VALUES (?,?)", _schema_hashes(graph))
        connection.commit()
        connection.close()
        connection = None
        if _source_fingerprint(source, name) != source_fingerprint:
            raise GraphFailure(
                "graph_changed_during_read", "Graph changed during cache creation; retry."
            )
        os.replace(temporary, cache)
        _write_descriptor(
            descriptor,
            {
                "contract_version": _CACHE_VERSION,
                "source_fingerprint": source_fingerprint,
                "cache_fingerprint": _fingerprint(cache),
            },
        )
    except (OSError, sqlite3.Error) as exc:
        raise GraphFailure(
            "graph_cache_build_failed", "Could not build the selective graph cache."
        ) from exc
    finally:
        if connection is not None:
            connection.close()
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _header(connection: sqlite3.Connection, name: str, stats: GraphReadStats) -> GraphHeader:
    rows = connection.execute("SELECT payload FROM header").fetchall()
    if len(rows) != 1:
        raise _invalid_cache()
    header = GraphHeader(**json.loads(rows[0][0]), read_stats=stats)
    if header.name != name or header.contract_version != "tarel.graph.v0.1":
        raise _invalid_cache()
    if stats.full_document_read:
        header = replace(
            header,
            read_stats=replace(
                stats,
                loaded_node_count=header.node_count,
                loaded_edge_count=header.edge_count,
            ),
        )
    return header


def _with_loaded_counts(header: GraphHeader, nodes: int, edges: int) -> GraphHeader:
    if header.read_stats.full_document_read:
        return header
    return replace(
        header,
        read_stats=replace(
            header.read_stats,
            loaded_node_count=nodes,
            loaded_edge_count=edges,
        ),
    )


def _request_ids(connection: sqlite3.Connection, ids: tuple[str, ...]) -> None:
    # A private TEMP table avoids SQLite's platform-dependent host-parameter limit.
    # The derived main database is opened read-only throughout.
    connection.execute("CREATE TEMP TABLE requested(id TEXT PRIMARY KEY)")
    connection.executemany("INSERT INTO requested VALUES (?)", ((item,) for item in ids))


def _validate_selection(object_ids: tuple[str, ...] | None, namespace: str | None) -> None:
    if object_ids is not None and (
        not isinstance(object_ids, tuple)
        or any(not isinstance(item, str) or not item for item in object_ids)
        or len(set(object_ids)) != len(object_ids)
    ):
        raise GraphFailure("invalid_graph_selection", "Object IDs must be a tuple of distinct IDs.")
    if namespace is not None and (not isinstance(namespace, str) or not namespace):
        raise GraphFailure("invalid_graph_selection", "Namespace must be a non-empty string.")


def _check_revision(header: GraphHeader, expected: str | None) -> None:
    if expected is not None and expected != header.revision:
        raise GraphFailure(
            "graph_revision_mismatch", "Graph revision changed; refresh the selection."
        )


def _metadata_text(node: GraphNode, key: str) -> str | None:
    value = node.metadata.get(key)
    return value if isinstance(value, str) else None


def _schema_hashes(graph: GraphDocument) -> tuple[tuple[str, str | None], ...]:
    schemas: dict[str, list[tuple[str, str, bool]]] = {
        node.id: [] for node in graph.nodes if node.type in {"table", "view"}
    }
    unavailable: set[str] = set()
    for node in graph.nodes:
        parent = node.metadata.get("object_id")
        if node.type != "field" or not isinstance(parent, str) or parent not in schemas:
            continue
        data_type, nullable = node.metadata.get("data_type"), node.metadata.get("nullable")
        if not isinstance(data_type, str) or type(nullable) is not bool:
            unavailable.add(parent)
        else:
            schemas[parent].append((node.label, data_type, nullable))
    return tuple(
        (
            parent,
            physical_schema_revision(tuple(fields))
            if fields and parent not in unavailable
            else None,
        )
        for parent, fields in schemas.items()
    )


def _cache_paths(source: Path) -> tuple[Path, Path]:
    return source.with_name("graph.selective.sqlite"), source.with_name("graph.selective.json")


def _source_fingerprint(path: Path, name: str) -> list[int]:
    try:
        return _fingerprint(path)
    except FileNotFoundError as exc:
        raise GraphFailure("graph_not_found", f"Graph not found: {name}") from exc
    except OSError as exc:
        raise GraphFailure("invalid_graph", f"Could not inspect graph: {name}") from exc


def _fingerprint(path: Path) -> list[int]:
    value = path.stat()
    return [value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns]


def _descriptor(path: Path) -> dict[str, object]:
    try:
        before = _fingerprint(path)
        if before[2] > 4096:
            raise _invalid_cache()
        data = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(data, dict)
            or set(data) != {"contract_version", "source_fingerprint", "cache_fingerprint"}
            or data["contract_version"] != _CACHE_VERSION
            or any(
                not isinstance(data[key], list)
                or len(data[key]) != 5
                or any(type(value) is not int or value < 0 for value in data[key])
                for key in ("source_fingerprint", "cache_fingerprint")
            )
            or before != _fingerprint(path)
        ):
            raise _invalid_cache()
        return data
    except (OSError, json.JSONDecodeError) as exc:
        raise _invalid_cache() from exc


def _write_descriptor(path: Path, data: dict[str, object]) -> None:
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=".selective-", suffix=".tmp")
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(_json(data))
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _json(data: dict[str, object]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _invalid_cache() -> GraphFailure:
    return GraphFailure(
        "invalid_graph_cache",
        "Selective graph cache is invalid; explicitly rebuild the graph index.",
    )
