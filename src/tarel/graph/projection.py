"""The compact projection of a graph slice: objects with their fields nested, no containment forest.

A full slice lists catalog and namespace nodes, one ``contains`` edge per field and every
annotation's audit trail. The compact view keeps what a reader needs to use the objects:

- each selected object once, with its fields nested under it (so ``object_id`` and the
  ``contains`` edges become redundant and are dropped);
- every field's technical metadata unchanged (type, nullability, keys, position, comment);
- annotations reduced to their meaning: description, role, state, synonyms, tags, warnings and
  confidence. ``confidence_reason``, ``evidence`` and ``provenance`` stay in ``view=full``;
- only edges that relate objects or fields (foreign keys and similar), never ``contains``.

Object metadata that only repeats the label (``catalog``, ``namespace`` and ``name`` when they
compose the label) is dropped. ``annotation_context_documents`` (which knowledge documents an
annotation run read) is listed once for the slice instead of on every node; which node used which
document stays in ``view=full``. Empty values are omitted.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import TYPE_CHECKING

from tarel.compact import omit_empty

if TYPE_CHECKING:
    from tarel.graph.contracts import GraphAnnotation, GraphNode
    from tarel.graph.selective import GraphSlice

_HOISTED = frozenset({"annotation_context_documents"})
_ANNOTATION_KEYS = ("confidence", "description", "role", "state", "synonyms", "tags", "warnings")


def compact_slice_dict(
    graph_slice: GraphSlice,
    *,
    freshness: Mapping[str, object] | None = None,
) -> dict[str, object]:
    header = graph_slice.header
    nodes = graph_slice.graph.node_by_id()
    fields: dict[str, list[GraphNode]] = {}
    for node in graph_slice.graph.nodes:
        parent = node.metadata.get("object_id")
        if node.type == "field" and isinstance(parent, str):
            fields.setdefault(parent, []).append(node)
    objects = [
        omit_empty(
            {
                "annotation": _annotation(nodes[item].annotation),
                "fields": [_field(field) for field in fields.get(item, ())],
                "id": item,
                "label": nodes[item].label,
                "meta": _object_metadata(nodes[item], header.catalog),
                "type": nodes[item].type,
            }
        )
        for item in graph_slice.object_ids
    ]
    edges = [
        omit_empty(
            {
                "from": edge.source_id,
                "meta": omit_empty(edge.metadata),
                "rel": edge.type,
                "to": edge.target_id,
            }
        )
        for edge in graph_slice.graph.edges
        if edge.type != "contains"
    ]
    payload: dict[str, object] = {
        "annotation_context_documents": _context_documents(graph_slice.graph.nodes) or None,
        "catalog": header.catalog,
        "edges": edges,
        "freshness": dict(freshness) if freshness else None,
        "graph": header.name,
        "next": {"full": "view=full"},
        "null_policy": "omitted",
        "object_count": header.object_count,
        "objects": objects,
        "revision": header.revision,
        "truncated": False,
        "view": "compact",
    }
    return {
        key: value
        for key, value in sorted(payload.items())
        if value is not None or key == "truncated"
    }


def _annotation(annotation: GraphAnnotation | None) -> dict[str, object] | None:
    if annotation is None:
        return None
    payload = annotation.to_dict()
    return omit_empty({key: payload.get(key) for key in _ANNOTATION_KEYS})


def _field(node: GraphNode) -> dict[str, object]:
    metadata = {
        key: value for key, value in node.metadata.items() if key not in _HOISTED | {"object_id"}
    }
    return omit_empty(
        {
            "annotation": _annotation(node.annotation),
            "id": node.id,
            "label": node.label,
            "meta": omit_empty(metadata),
        }
    )


def _object_metadata(node: GraphNode, catalog: str) -> dict[str, object]:
    metadata = {key: value for key, value in node.metadata.items() if key not in _HOISTED}
    if metadata.get("catalog") == catalog:
        metadata.pop("catalog")
    namespace, name = metadata.get("namespace"), metadata.get("name")
    if isinstance(namespace, str) and isinstance(name, str) and f"{namespace}.{name}" == node.label:
        metadata.pop("namespace")
        metadata.pop("name")
    return omit_empty(metadata)


def _context_documents(nodes: tuple[GraphNode, ...]) -> list[object]:
    """Each distinct context document named by any node, once, in first-seen order."""
    seen: dict[str, object] = {}
    for node in nodes:
        documents = node.metadata.get("annotation_context_documents")
        for item in documents if isinstance(documents, list) else ():
            seen.setdefault(json.dumps(item, sort_keys=True), item)
    return list(seen.values())
