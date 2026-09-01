"""Deterministic revision identifiers for complete graph documents."""

from __future__ import annotations

import hashlib
import json

from tarel.graph.contracts import GraphDocument


def graph_revision(graph: GraphDocument) -> str:
    payload = json.dumps(
        graph.to_dict(),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def physical_graph_revision(graph: GraphDocument) -> str:
    """Hash physical object/field identity without annotations or inferred edges."""
    nodes = []
    for node in sorted(graph.nodes, key=lambda item: item.id):
        if node.type in {"table", "view"}:
            metadata_keys = ("catalog", "name", "namespace", "primary_key")
        elif node.type == "field":
            metadata_keys = (
                "data_type",
                "is_primary_key",
                "nullable",
                "object_id",
                "position",
            )
        else:
            continue
        nodes.append(
            {
                "id": node.id,
                "label": node.label,
                "metadata": {key: node.metadata.get(key) for key in metadata_keys},
                "type": node.type,
            }
        )
    payload = json.dumps(
        {
            "catalog": graph.catalog,
            "connector": graph.connector,
            "dialect": graph.dialect,
            "name": graph.name,
            "nodes": nodes,
            "source_type": graph.source_type,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
