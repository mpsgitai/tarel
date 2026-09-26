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


def physical_schema_revision(fields: tuple[tuple[str, str, bool], ...]) -> str:
    """Exact typed field-schema identity, independent of graph and field ordering."""
    payload = json.dumps(
        sorted(fields, key=lambda item: item[0]),
        ensure_ascii=False,
        separators=(",", ":"),
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


def technical_graph_fingerprint(graph: GraphDocument) -> str:
    """Hash only connector-observed topology, including descriptions and declared keys.

    The fingerprint deliberately excludes annotations, discovery candidates, and other
    TAREL-authored semantics. It is therefore suitable for deciding whether a fresh catalog
    observation requires graph reconciliation without treating semantic edits as source drift.
    """
    nodes = []
    for node in sorted(graph.nodes, key=lambda item: item.id):
        if node.type in {"table", "view"}:
            metadata_keys = (
                "catalog",
                "name",
                "namespace",
                "primary_key",
                "technical_description",
            )
        elif node.type == "field":
            metadata_keys = (
                "data_type",
                "is_primary_key",
                "nullable",
                "object_id",
                "position",
                "technical_description",
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
    relationships = [
        {
            "id": edge.id,
            "metadata": {
                key: edge.metadata.get(key)
                for key in ("from_fields", "name", "to_fields")
            },
            "source_id": edge.source_id,
            "target_id": edge.target_id,
            "type": edge.type,
        }
        for edge in sorted(graph.edges, key=lambda item: item.id)
        if edge.type == "foreign_key"
    ]
    payload = json.dumps(
        {
            "catalog": graph.catalog,
            "connector": graph.connector,
            "dialect": graph.dialect,
            "name": graph.name,
            "nodes": nodes,
            "relationships": relationships,
            "source_type": graph.source_type,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
