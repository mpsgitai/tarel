"""What an activation took away, and which central statements that left without an object.

A record belongs to one activated revision, so it can never disagree with ``head.json``: until the
head moves, the old record stays the valid one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tarel.graph.contracts import GraphDocument, GraphFailure
from tarel.graph.refresh import GraphRefreshReport, StaleClaim
from tarel.runtime import TarelRuntime
from tarel.sync.contracts import ExportScope, StreamHead
from tarel.workspaces.contracts import WorkspaceDocument, WorkspaceFailure
from tarel.workspaces.core import dangling_references, referenced_graphs

REASON_DELETED = "source_deleted"
REASON_WITHDRAWN = "withdrawn"
_REASON_SUPERSEDED = "superseded"


@dataclass(frozen=True, slots=True)
class ActiveImpacts:
    removals: tuple[dict[str, str], ...] = ()
    retired_claims: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {"removals": list(self.removals), "retired_claims": list(self.retired_claims)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActiveImpacts:
        return cls(tuple(data["removals"]), tuple(data["retired_claims"]))

    def retired_annotations(self) -> dict[str, dict[str, Any]]:
        return {
            str(item["target_id"]): item
            for item in self.retired_claims
            if item["claim_type"] == "annotation"
        }


def scope_change(
    head: StreamHead | None, scope: ExportScope, version: int,
) -> dict[str, Any] | None:
    """What changed in what the site approves, or None when nothing did."""
    if head is None or head.scope.digest == scope.digest:
        return None
    before, after = set(head.scope.namespaces), set(scope.namespaces)
    return {
        "annotations": [head.scope.annotations, scope.annotations],
        "from_version": head.profile_version,
        "namespaces_added": sorted(after - before),
        "namespaces_removed": sorted(before - after),
        "technical_descriptions": [head.scope.technical_descriptions, scope.technical_descriptions],
        "to_version": version,
    }


def next_impacts(
    previous: ActiveImpacts,
    report: GraphRefreshReport,
    current: GraphDocument,
    merged: GraphDocument,
    scope: ExportScope,
    publication_id: str,
    restored: tuple[str, ...],
) -> ActiveImpacts:
    """Carry the record forward: new removals join it, anything that came back leaves it."""
    present = {node.id for node in merged.nodes}
    removals = {
        item["object_id"]: item for item in previous.removals if item["object_id"] not in present
    }
    for change in report.changes:
        if change.kind == "object_removed":
            removals[change.target_id] = {
                "object_id": change.target_id,
                "publication_id": publication_id,
                "reason": (
                    REASON_DELETED if change.namespace in scope.namespaces else REASON_WITHDRAWN
                ),
                "reference": change.reference,
            }
    retired = {
        (str(item["claim_type"]), str(item["target_id"])): item
        for item in previous.retired_claims
        if str(item["target_id"]) not in restored
    }
    for claim in report.stale_claims:
        if not claim.present:
            retired[(claim.claim_type, claim.target_id)] = {
                **claim.to_dict(),
                "reason": _claim_reason(claim, current, scope),
                "retired_by": publication_id,
            }
    return ActiveImpacts(
        removals=tuple(removals[key] for key in sorted(removals)),
        retired_claims=tuple(retired[key] for key in sorted(retired)),
    )


def load_workspaces(runtime: TarelRuntime) -> tuple[WorkspaceDocument, ...]:
    """Every readable workspace. One that cannot be read holds no reference this can report."""
    store = runtime.workspace_store()
    found = []
    for name in store.list():
        try:
            found.append(store.load(name))
        except WorkspaceFailure:
            continue
    return tuple(found)


def dangling_for_graph(
    runtime: TarelRuntime,
    local_graph: str,
    removals: tuple[dict[str, str], ...],
    replacement: GraphDocument | None = None,
    workspaces: tuple[WorkspaceDocument, ...] | None = None,
) -> tuple[dict[str, str], ...]:
    """Central references to ``local_graph`` that point at nothing, with why if that is known.

    Only this one graph has to be read, and only if something refers to it. Nothing is kept beyond
    the call, so an edit made since the last call shows. A caller asking about many graphs passes
    the workspaces once, which keeps a status call linear in the number of streams.
    """
    relevant = [
        workspace
        for workspace in (load_workspaces(runtime) if workspaces is None else workspaces)
        if local_graph in referenced_graphs(workspace)
    ]
    if not relevant:
        return ()
    graph = replacement
    if graph is None:
        try:
            graph = runtime.graph_store().load(local_graph)
        except GraphFailure:
            return ()
    reasons = {item["object_id"]: item["reason"] for item in removals}
    return tuple(
        {**item.to_dict(), "reason": reasons.get(item.object_id, "unknown")}
        for workspace in relevant
        for item in dangling_references(workspace, {local_graph: graph})
    )


def _claim_reason(claim: StaleClaim, current: GraphDocument, scope: ExportScope) -> str:
    if "superseded_by_declared_relationship" in claim.reasons:
        return _REASON_SUPERSEDED
    namespaces = _target_namespaces(claim.target_id, current)
    return REASON_WITHDRAWN if namespaces - set(scope.namespaces) else REASON_DELETED


def _target_namespaces(target_id: str, graph: GraphDocument) -> set[str]:
    nodes = graph.node_by_id()
    edge = next((item for item in graph.edges if item.id == target_id), None)
    targets = (edge.source_id, edge.target_id) if edge is not None else (target_id,)
    namespaces: set[str] = set()
    for identifier in targets:
        node = nodes.get(identifier)
        if node is None:
            continue
        parent = nodes.get(str(node.metadata.get("object_id"))) if node.type == "field" else node
        namespace = parent.metadata.get("namespace") if parent is not None else None
        if namespace:
            namespaces.add(str(namespace))
    return namespaces
