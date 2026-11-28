"""Text and JSON renderers shared by several command groups."""

from __future__ import annotations

import json
from pathlib import Path

from tarel.annotations.contracts import AnnotationTask
from tarel.connectors.contracts import CatalogResult, ProbeResult
from tarel.graph.contracts import GraphDocument


def render_annotation_plan(
    tasks: tuple[AnnotationTask, ...],
    *,
    output_format: str,
) -> None:
    if output_format == "json":
        print_json({
                    "count": len(tasks),
                    "tasks": [
                        {
                            "context_documents": [
                                item.to_dict() for item in task.context_documents
                            ],
                            "field_names": list(task.field_names),
                            "graph_name": task.graph_name,
                            "id": task.id,
                            "include_object": task.include_object,
                            "mode": task.mode,
                            "target": task.target_label,
                            "target_id": task.target_id,
                        }
                        for task in tasks
                    ],
                })
        return
    print(f"Annotation tasks: {len(tasks)}")
    for task in tasks:
        scope = "object + fields" if task.include_object else f"{len(task.field_names)} fields"
        print(f"{task.id}  {task.graph_name}:{task.target_label}  [{task.mode}; {scope}]")


def render_catalog(result: CatalogResult, *, output_format: str) -> None:
    if output_format == "json":
        print_json(result.to_dict())
        return
    print(f"Connector: {result.connector}")
    print("Status: ok")
    print(f"Catalog: {result.catalog}")
    print(f"Dialect: {result.dialect or ''}")
    print(f"Objects: {len(result.objects)}")
    for item in result.objects:
        print(f"{item.namespace}.{item.name} [{item.kind}]")
        for field in item.fields:
            nullable = " nullable" if field.nullable else ""
            print(f"  {field.position}: {field.name} {field.data_type}{nullable}")


def render_graph_summary(
    graph: GraphDocument,
    *,
    output_format: str,
    path: Path | None = None,
) -> None:
    counts = {
        node_type: sum(node.type == node_type for node in graph.nodes)
        for node_type in sorted({node.type for node in graph.nodes})
    }
    payload = {
        "catalog": graph.catalog,
        "dialect": graph.dialect,
        "edges": len(graph.edges),
        "name": graph.name,
        "nodes": len(graph.nodes),
        "node_types": counts,
        "path": str(path) if path else None,
    }
    if output_format == "json":
        print_json(payload)
        return
    print(f"Graph: {graph.name}")
    print(f"Catalog: {graph.catalog}")
    print(f"Dialect: {graph.dialect or ''}")
    print(f"Nodes: {len(graph.nodes)}")
    print(f"Edges: {len(graph.edges)}")
    print("Node types: " + ", ".join(f"{key}={value}" for key, value in counts.items()))
    if path:
        print(f"Path: {path}")


def render_probe(result: ProbeResult, *, output_format: str) -> None:
    if output_format == "json":
        print_json(result.to_dict())
        return
    print(f"Connector: {result.connector}")
    print("Status: ok")
    print(f"Server: {result.server_name or ''}")
    print(f"Database: {result.database_name}")
    print(f"Version: {result.product_version or ''}")
    print(f"Level: {result.product_level or ''}")
    print(f"Edition: {result.edition or ''}")
    print(f"Capabilities: {', '.join(result.capabilities)}")
    print(f"Read only: {'yes' if result.read_only else 'no'}")


def print_json(payload: object, *, ensure_ascii: bool = True) -> None:
    """Print ``payload`` as every ``--format json`` command does: indented, keys sorted."""
    print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=ensure_ascii))


def render_compact(payload: dict[str, object], *, output_format: str) -> None:
    """Render a compact lineage or focus projection.

    JSON goes on one line without indentation: the compact view exists for readers that pay per
    byte, and indentation would cost more than the remaining structure.
    """
    if output_format == "json":
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
        return
    nodes = payload.get("nodes")
    kinds = (
        {key: value.get("kind") for key, value in nodes.items() if isinstance(value, dict)}
        if isinstance(nodes, dict)
        else {}
    )
    start = payload.get("start")
    if isinstance(start, str):
        print(f"Start: {start} [{kinds.get(start)}]")
    edges = payload.get("edges")
    for edge in edges if isinstance(edges, list) else ():
        if not isinstance(edge, dict):
            continue
        extras = [
            f"{key}={edge[key]}"
            for key in ("via", "role", "lin", "state", "ev", "edge_count")
            if key in edge
        ]
        detail = f"  ({'; '.join(extras)})" if extras else ""
        depth, relation = edge.get("d"), edge.get("rel")
        if edge.get("dir") == "down" or payload.get("direction") == "down":
            print(f"d{depth} {edge.get('from')} -{relation}-> {edge.get('to')}{detail}")
        else:
            print(f"d{depth} {edge.get('to')} <-{relation}- {edge.get('from')}{detail}")
    cycles = payload.get("cycles")
    for cycle in cycles if isinstance(cycles, list) else ():
        if isinstance(cycle, dict):
            members = cycle.get("members")
            rendered = ", ".join(str(item) for item in members) if isinstance(members, list) else ""
            print(f"cycle: {rendered} ({cycle.get('internal_edges')} internal edges folded)")
    if payload.get("self_loops_omitted"):
        print(f"self-loops omitted: {payload['self_loops_omitted']}")
    for key in ("origins", "impacts"):
        values = payload.get(key)
        if isinstance(values, list) and values:
            print(f"{key.capitalize()}: {', '.join(str(item) for item in values)}")
    resolution = payload.get("resolution")
    if isinstance(resolution, dict):
        print(
            f"Sources (auto): {len(resolution['lineages'])} lineages "
            f"[{resolution['lineages_from']}], {len(resolution['graphs'])} graphs "
            f"[{resolution['graphs_from']}]; --format json lists them"
        )
    freshness = payload.get("freshness")
    if isinstance(freshness, dict):
        observed = freshness.get("observed")
        parts = [f"{key}@{value}" for key, value in observed.items()] if isinstance(
            observed, dict
        ) else []
        missing = freshness.get("missing")
        if isinstance(missing, list) and missing:
            parts.append(f"no observation: {', '.join(missing)}")
        print(f"Freshness: {'; '.join(parts)} (stale: {freshness.get('stale')})")
    for key in ("limits", "warnings"):
        values = payload.get(key)
        for value in values if isinstance(values, list) else ():
            print(f"{key[:-1]}: {value}")
    if payload.get("truncated"):
        print("truncated: yes")
