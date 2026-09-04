"""Read-only browser-shaped runtime projection, separate from reusable static ETL lineage."""

from __future__ import annotations

from tarel.lineage.runtime import (
    RuntimeLineageDocument,
    RuntimeMongoAttempt,
    RuntimeSQLAttempt,
    validate_runtime_lineage_document,
)
from tarel.lineage.runtime_logical import RuntimeLogicalOperation


def browser_runtime_lineage(document: RuntimeLineageDocument) -> dict[str, object]:
    validate_runtime_lineage_document(document)
    nodes: list[dict[str, object]] = []
    edges: list[dict[str, str]] = []
    origins: set[str] = set()
    for event in document.events:
        payload = event.to_dict()
        call_node_id = f"call::{event.call_id}"
        node: dict[str, object] = {
            "id": call_node_id,
            "type": "runtime_call",
            "call_id": event.call_id,
            "sequence": event.sequence,
            "kind": payload["kind"],
            "operation": payload["operation"],
            "status": event.status,
            "row_count": event.result.row_count if event.result else None,
            "result_sha256": event.result.sha256 if event.result else None,
            "truncated": event.result.truncated if event.result else None,
            "error_code": event.error_code,
        }
        for key in ("dialect", "engine", "tool_type", "executor", "analysis", "duration_ms"):
            if key in payload:
                node[key] = payload[key]
        if isinstance(event, RuntimeLogicalOperation):
            node["artifact_validation"] = event.artifact_validation
            node["dependency_refs"] = [item.to_dict() for item in event.dependency_refs]
        nodes.append(node)
        if isinstance(event, (RuntimeSQLAttempt, RuntimeMongoAttempt)):
            for origin in event.inputs:
                origin_id = f"source::{origin.node_id}"
                if origin_id not in origins:
                    origins.add(origin_id)
                    nodes.append(
                        {
                            "id": origin_id,
                            "type": "source_reference",
                            "node_id": origin.node_id,
                            "reference": origin.reference,
                        }
                    )
                edges.append({"source": origin_id, "target": call_node_id, "kind": "reads"})
        else:
            edges.extend(
                {"source": f"call::{source}", "target": call_node_id, "kind": "consumes"}
                for source in event.consumes
            )
    return {
        "runtime_lineage": document.name,
        "run_id": document.run_id,
        "graph": {"name": document.graph_name, "revision": document.graph_revision},
        "nodes": nodes,
        "edges": edges,
        "notice": "Caller-observed runtime use, not static ETL or artifact approval. "
        "Logical artifact revisions are caller_claimed; success never promotes a candidate.",
    }
