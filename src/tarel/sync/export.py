"""The allowlist deciding what of a local graph may leave a site.

Graph metadata is a free-form dictionary, so a new key must stay at home until someone lists it
here, and an allowed key must hold the kind of value it is allowed for. The receiver runs the same
check, because a package is not trusted to have applied it. Failures name only what this module
knows itself: whatever a sender chose can be what must not show, and they reach the central status.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from tarel.graph.build import (
    catalog_node_id,
    field_node_id,
    namespace_node_id,
    object_node_id,
)
from tarel.graph.contracts import GraphAnnotation, GraphDocument, GraphEdge, GraphNode
from tarel.sync.contracts import ExportScope, SyncFailure

_OBJECT_TYPES = frozenset({"table", "view"})
_NODE_METADATA = {
    "catalog": frozenset({"dialect", "source_type"}),
    "namespace": frozenset({"catalog"}),
    "table": frozenset({"catalog", "name", "namespace", "primary_key"}),
    "view": frozenset({"catalog", "name", "namespace", "primary_key"}),
    "field": frozenset({"data_type", "is_primary_key", "nullable", "object_id", "position"}),
}
_DESCRIBED_TYPES = frozenset({"table", "view", "field"})
_DESCRIPTION_METADATA = frozenset({"technical_description"})
_ANNOTATION_METADATA = frozenset({"grain", "semantic_type"})
_EDGE_METADATA = {
    "contains": frozenset(),
    "foreign_key": frozenset({"from_fields", "name", "to_fields"}),
    "foreign_key_field": frozenset({"relationship_id"}),
}
_KNOWN_NODE_METADATA = frozenset().union(
    *_NODE_METADATA.values(), _DESCRIPTION_METADATA, _ANNOTATION_METADATA,
)


def _is_text(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _is_optional_text(value: object) -> bool:
    """A source may have nothing to say: the builder writes ``None``, and ``""`` is still text."""
    return value is None or isinstance(value, str)


def _is_flag(value: object) -> bool:
    return isinstance(value, bool)


def _is_position(value: object) -> bool:
    # bool is a subclass of int, and True is no column position.
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _is_name_list(value: object) -> bool:
    """An object without a primary key has an empty list, so empty is fine here."""
    return isinstance(value, list) and all(_is_text(item) for item in value)


def _is_filled_name_list(value: object) -> bool:
    return _is_name_list(value) and bool(value)


_OBJECT_VALUES: dict[str, Callable[[object], bool]] = {
    "catalog": _is_text,
    "name": _is_text,
    "namespace": _is_text,
    "primary_key": _is_name_list,
    "technical_description": _is_optional_text,
    "grain": _is_optional_text,
    "semantic_type": _is_optional_text,
}
_NODE_VALUES: dict[str, dict[str, Callable[[object], bool]]] = {
    "catalog": {"dialect": _is_optional_text, "source_type": _is_text},
    "namespace": {"catalog": _is_text},
    "table": _OBJECT_VALUES,
    "view": _OBJECT_VALUES,
    "field": {
        "data_type": _is_text,
        "is_primary_key": _is_flag,
        "nullable": _is_flag,
        "object_id": _is_text,
        "position": _is_position,
        "technical_description": _is_optional_text,
        "grain": _is_optional_text,
        "semantic_type": _is_optional_text,
    },
}
_EDGE_VALUES: dict[str, dict[str, Callable[[object], bool]]] = {
    "contains": {},
    "foreign_key": {
        "from_fields": _is_filled_name_list,
        "name": _is_text,
        "to_fields": _is_filled_name_list,
    },
    "foreign_key_field": {"relationship_id": _is_text},
}


def export_graph(graph: GraphDocument, scope: ExportScope) -> GraphDocument:
    """Reduce ``graph`` to what ``scope`` approves. A listed namespace must actually exist."""
    _require_objects_in_every_namespace(graph, scope)
    by_id = graph.node_by_id()
    nodes = tuple(
        _export_node(node, scope) for node in graph.nodes if _node_in_scope(node, by_id, scope)
    )
    kept = {node.id for node in nodes}
    edges = tuple(
        _export_edge(edge)
        for edge in graph.edges
        if edge.type in _EDGE_METADATA and edge.source_id in kept and edge.target_id in kept
    )
    exported = replace(graph, nodes=nodes, edges=edges)
    check_exported_graph(exported, scope)
    return exported


def check_exported_graph(graph: GraphDocument, scope: ExportScope) -> None:
    """Reject anything an honest export under ``scope`` could not contain.

    Messages name only the kind of node, never an ID or a key the sender chose.
    """
    by_id = graph.node_by_id()
    fields_by_object: dict[str, set[str]] = {}
    for node in graph.nodes:
        if node.type == "field":
            fields_by_object.setdefault(str(node.metadata.get("object_id")), set()).add(node.label)
    for node in graph.nodes:
        _check_node(node, by_id, fields_by_object, graph.catalog, scope)
    foreign_keys = {edge.id for edge in graph.edges if edge.type == "foreign_key"}
    for edge in graph.edges:
        _check_edge(edge, by_id, fields_by_object, foreign_keys)
    _require_objects_in_every_namespace(graph, scope)


def _check_node(
    node: GraphNode,
    by_id: dict[str, GraphNode],
    fields_by_object: dict[str, set[str]],
    catalog: str,
    scope: ExportScope,
) -> None:
    allowed = _allowed_node_metadata(node.type, scope)
    if allowed is None:
        _violation("an unknown node type")
        return
    if not _node_in_scope(node, by_id, scope):
        _violation(f"a {node.type} node outside the scope")
    extra = set(node.metadata) - allowed
    known = sorted(extra & _KNOWN_NODE_METADATA)
    if known:
        _violation(f"metadata {known} on a {node.type} node")
    if extra:
        _violation(f"unexpected metadata on a {node.type} node")
    _check_values(node.metadata, _NODE_VALUES[node.type], f"a {node.type} node")
    if not _identity_is_consistent(node, by_id, catalog):
        _violation(f"a {node.type} node whose identity contradicts its name")
    if node.type in _OBJECT_TYPES and not set(node.metadata.get("primary_key") or ()) <= (
        fields_by_object.get(node.id, set())
    ):
        _violation(f"a primary key on a {node.type} node that names no field of it")
    if node.annotation is not None:
        if not scope.annotations:
            _violation(f"annotation on a {node.type} node")
        if any(item.value is not None for item in node.annotation.evidence):
            _violation(f"evidence value on a {node.type} node")


def _check_edge(
    edge: GraphEdge,
    by_id: dict[str, GraphNode],
    fields_by_object: dict[str, set[str]],
    foreign_keys: set[str],
) -> None:
    allowed = _EDGE_METADATA.get(edge.type)
    if allowed is None:
        _violation("an unknown edge type")
        return
    if set(edge.metadata) - allowed:
        _violation(f"unexpected metadata on a {edge.type} edge")
    _check_values(edge.metadata, _EDGE_VALUES[edge.type], f"a {edge.type} edge")
    if edge.type == "foreign_key":
        source = edge.metadata.get("from_fields") or []
        target = edge.metadata.get("to_fields") or []
        if (
            len(source) != len(target)
            or by_id[edge.source_id].type not in _OBJECT_TYPES
            or by_id[edge.target_id].type not in _OBJECT_TYPES
            or not set(source) <= fields_by_object.get(edge.source_id, set())
            or not set(target) <= fields_by_object.get(edge.target_id, set())
        ):
            _violation("a foreign_key edge that names no fields of its objects")
    if edge.type == "foreign_key_field" and (
        edge.metadata.get("relationship_id") not in foreign_keys
    ):
        _violation("a foreign_key_field edge without its foreign key")


def _check_values(
    metadata: dict[str, Any], rules: dict[str, Callable[[object], bool]], where: str,
) -> None:
    for key, value in metadata.items():
        if not rules[key](value):
            _violation(f"a malformed {key} on {where}")


def _require_objects_in_every_namespace(graph: GraphDocument, scope: ExportScope) -> None:
    """Sender and receiver alike. Without this a snapshot would read as "all of it was deleted".

    Each namespace is checked on its own, and only an object counts, not a bare namespace node. To
    empty a namespace on purpose, take it out of the scope under a new profile version.
    """
    present = {
        node.metadata.get("namespace") for node in graph.nodes if node.type in _OBJECT_TYPES
    }
    missing = sorted(set(scope.namespaces) - {item for item in present if isinstance(item, str)})
    if missing:
        raise SyncFailure(
            "scope_namespace_missing", f"No objects in approved namespaces: {', '.join(missing)}",
        )


def object_count(graph: GraphDocument) -> int:
    return sum(node.type in _OBJECT_TYPES for node in graph.nodes)


def _violation(detail: str) -> None:
    raise SyncFailure("export_not_allowed", f"Not allowed in this export: {detail}")


def _allowed_node_metadata(node_type: str, scope: ExportScope) -> frozenset[str] | None:
    """The one rule for both sides: the sender selects by it and the receiver refuses by it.

    It follows only what the file itself declares. What the receiving state would allow is checked
    separately, and a more generous grant there does not widen what this sender published.
    """
    allowed = _NODE_METADATA.get(node_type)
    if allowed is None:
        return None
    if scope.annotations and node_type in _DESCRIBED_TYPES:
        allowed |= _ANNOTATION_METADATA
    if scope.technical_descriptions and node_type in _DESCRIBED_TYPES:
        allowed |= _DESCRIPTION_METADATA
    return allowed


def _node_in_scope(node: GraphNode, by_id: dict[str, GraphNode], scope: ExportScope) -> bool:
    if node.type == "catalog":
        return True
    if node.type == "namespace":
        return node.label in scope.namespaces
    if node.type in _OBJECT_TYPES:
        return node.metadata.get("namespace") in scope.namespaces
    if node.type == "field":
        parent = by_id.get(str(node.metadata.get("object_id")))
        return (
            parent is not None
            and parent.type in _OBJECT_TYPES
            and parent.metadata.get("namespace") in scope.namespaces
        )
    return False


def _identity_is_consistent(node: GraphNode, by_id: dict[str, GraphNode], catalog: str) -> bool:
    """Does a node's ID say the same as its name, as a built graph always does?

    This catches a sloppy edit or a broken exporter, such as an ``hr`` object labelled ``dbo``. A
    careful sender who changes every place at once still passes: the central state cannot see the
    source, so consistency is all it can check.
    """
    metadata = node.metadata
    if node.type == "catalog":
        return node.id == catalog_node_id(catalog) and node.label == catalog
    if node.type == "namespace":
        return (
            node.id == namespace_node_id(catalog, node.label)
            and metadata.get("catalog") == catalog
        )
    if node.type in _OBJECT_TYPES:
        namespace, name = metadata.get("namespace"), metadata.get("name")
        if not isinstance(namespace, str) or not isinstance(name, str):
            return False
        return (
            metadata.get("catalog") == catalog
            and node.id == object_node_id(catalog, namespace, name)
            and node.label == f"{namespace}.{name}"
        )
    if node.type == "field":
        parent = by_id[str(metadata.get("object_id"))].metadata
        return node.id == field_node_id(
            catalog, str(parent.get("namespace")), str(parent.get("name")), node.label,
        )
    return False


def _export_node(node: GraphNode, scope: ExportScope) -> GraphNode:
    allowed = _allowed_node_metadata(node.type, scope) or frozenset()
    metadata: dict[str, Any] = {
        key: value for key, value in node.metadata.items() if key in allowed
    }
    annotation = _export_annotation(node.annotation) if scope.annotations else None
    return replace(node, metadata=metadata, annotation=annotation)


def _export_annotation(annotation: GraphAnnotation | None) -> GraphAnnotation | None:
    """Evidence names its source but drops the quoted value, which can hold sampled rows."""
    if annotation is None:
        return None
    return replace(
        annotation,
        evidence=tuple(replace(item, value=None) for item in annotation.evidence),
    )


def _export_edge(edge: GraphEdge) -> GraphEdge:
    allowed = _EDGE_METADATA[edge.type]
    return replace(
        edge, metadata={key: value for key, value in edge.metadata.items() if key in allowed}
    )
