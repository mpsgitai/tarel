"""Focus layer: the catalog of focuses and the physical objects a selection covers."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Any

from tarel.focus.contracts import FocusDocument, FocusMember
from tarel.ui.payloads._ids import browser_id


def browser_focus_catalog(
    documents: Iterable[FocusDocument],
    *,
    stale_reasons: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    stale = stale_reasons or {}
    return [
        {
            "current": document.name not in stale,
            "graph_objects": sum(
                item.kind in {"table", "view"} and item.source.startswith("graph:")
                for item in document.members
            ),
            "members": len(document.members),
            "name": document.name,
            "origins": sum(item.origin for item in document.members),
            "revision": document.revision,
            "seed": document.seed,
            "sources": [f"{item.kind}:{item.name}" for item in document.sources],
            "stale_reason": stale.get(document.name),
            "truncated": document.truncated,
            "warnings": list(document.warnings),
        }
        for document in sorted(documents, key=lambda item: item.name.casefold())
    ]


def focus_physical_objects(
    documents: Iterable[FocusDocument],
) -> frozenset[tuple[str, str]]:
    """Union physical focus members; caller intersects its own workspace scope."""
    return frozenset(
        (graph, item.id.removeprefix(f"graph:{graph}:"))
        for document in documents
        for item in document.members
        if item.kind in {"table", "view"}
        if (graph := _focus_member_graph(item)) is not None
    )


def browser_focus_selection(documents: Iterable[FocusDocument]) -> dict[str, Any]:
    selected = tuple(sorted(documents, key=lambda item: item.name.casefold()))
    members: dict[str, dict[str, Any]] = {}
    edges: dict[tuple[str, ...], dict[str, Any]] = {}
    for document in selected:
        by_id = {item.id: item for item in document.members}
        for item in document.members:
            identifier = _focus_member_ui_id(item)
            existing = members.get(identifier)
            focus_names = sorted(
                {*(existing.get("focuses", []) if existing else []), document.name}
            )
            reasons = sorted({*(existing.get("reasons", []) if existing else []), *item.reasons})
            members[identifier] = {
                "annotation_state": item.annotation_state,
                "depth": min(int(existing["depth"]), item.depth) if existing else item.depth,
                "focuses": focus_names,
                "graph": _focus_member_graph(item),
                "id": identifier,
                "kind": item.kind,
                "label": item.name,
                "origin": bool(item.origin or (existing and existing["origin"])),
                "reasons": reasons,
                "reference": item.reference,
                "source": item.source,
            }
        for hop in document.hops:
            source = _focus_member_ui_id(by_id[hop.source_id])
            target = _focus_member_ui_id(by_id[hop.target_id])
            key = (hop.id, hop.lineage or "", source, target, hop.relation, hop.state)
            existing = edges.get(key)
            edges[key] = {
                "depth": min(int(existing["depth"]), hop.depth) if existing else hop.depth,
                "focuses": sorted(
                    {*(existing.get("focuses", []) if existing else []), document.name}
                ),
                "id": "focus-edge::" + hashlib.sha256("\0".join(key).encode()).hexdigest()[:20],
                "lineage": hop.lineage,
                "relation": hop.relation,
                "source": source,
                "state": hop.state,
                "target": target,
                "type": "lineage",
            }
    ordered_members = [members[key] for key in sorted(members)]
    return {
        "edges": sorted(edges.values(), key=lambda item: str(item["id"])),
        "focuses": [item.name for item in selected],
        "members": ordered_members,
        "object_ids": sorted(
            str(item["id"])
            for item in ordered_members
            if item["graph"] is not None and item["kind"] in {"table", "view"}
        ),
        "origins": [
            item for item in ordered_members if bool(item["origin"])
        ],
        "warnings": sorted({warning for item in selected for warning in item.warnings}),
    }


def _focus_member_graph(item: FocusMember) -> str | None:
    if not item.source.startswith("graph:"):
        return None
    return item.source.removeprefix("graph:")


def _focus_member_ui_id(item: FocusMember) -> str:
    graph = _focus_member_graph(item)
    prefix = f"graph:{graph}:" if graph else ""
    return browser_id(graph, item.id.removeprefix(prefix)) if graph else f"focus::{item.id}"
