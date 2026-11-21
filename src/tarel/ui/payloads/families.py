"""Object-family layer: families, their members and the scope revision a page belongs to."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any

from tarel.entity_resolution.candidates import EntityResolutionMatch
from tarel.focus.contracts import FocusDocument
from tarel.graph.contracts import GraphDocument
from tarel.graph.revision import graph_revision, physical_graph_revision
from tarel.object_families.application import family_summary, validate_object_families_against_graph
from tarel.object_families.contracts import ObjectFamily, ObjectFamilyFailure
from tarel.reference_mapping.contracts import ReferenceMappingMatch
from tarel.topology.contracts import LogicalTopologyDocument
from tarel.ui.payloads._ids import browser_id
from tarel.workspaces.scope import ResolvedScope


def object_family_payloads(
    graph: GraphDocument,
    families: tuple[ObjectFamily, ...],
    allowed_ids: set[str],
    mode: str,
    topology: LogicalTopologyDocument | None,
    mappings: tuple[ReferenceMappingMatch, ...],
    entities: tuple[EntityResolutionMatch, ...],
) -> tuple[list[dict[str, Any]], set[str]]:
    """Collapse metadata only; a member edge never becomes a family-wide edge."""
    objects: list[dict[str, Any]] = []
    hidden: set[str] = set()
    nodes = graph.node_by_id()
    revision = physical_graph_revision(graph)
    eligible = tuple(
        family for family in families
        if family.graph_name == graph.name and family.graph_revision == revision
        and family.state != "rejected"
        and (mode != "confirmed_only" or family.state == "reviewed")
        and allowed_ids.intersection(family.member_ids)
    )
    validate_object_families_against_graph(eligible, graph)
    details: dict[str, dict[str, set[str]]] = {
        kind: {} for kind in (
            "physical_relationships", "derived_relations", "reference_mappings", "entity_candidates"
        )
    }

    def record_detail(kind: str, reference: str, endpoints: tuple[str, ...]) -> None:
        if all(endpoint in allowed_ids for endpoint in endpoints):
            for endpoint in endpoints:
                details[kind].setdefault(endpoint, set()).add(reference)

    for edge in graph.edges:
        record_detail("physical_relationships", edge.id, (edge.source_id, edge.target_id))
    for relation in topology.derived_relations if topology else ():
        record_detail("derived_relations", relation.id, (relation.source.id,))
    for kind, matches in (("reference_mappings", mappings), ("entity_candidates", entities)):
        for match in matches:
            candidate = match.candidate
            if candidate.graph_name != graph.name:
                continue
            endpoints = tuple(
                str(nodes[field_id].metadata.get("object_id") or "")
                if field_id in nodes else ""
                for field_id in (candidate.source_field_id, candidate.target_field_id)
            )
            record_detail(kind, candidate.id, endpoints)
    for family in sorted(eligible, key=lambda item: (item.name, item.id)):
        member_ids = set(family.member_ids) & allowed_ids
        if member_ids & hidden:
            raise ObjectFamilyFailure(
                "object_family_overlap", "Active families overlap within the browser scope."
            )
        hidden.update(member_ids)
        summary = family_summary(family, member_count=len(member_ids))
        summary["hidden_details"] = {
            kind: len({reference for member_id in member_ids
                       for reference in references.get(member_id, ())})
            for kind, references in details.items()
        }
        summary["namespace_count"] = len({
            str(nodes[member_id].metadata.get("namespace") or "") for member_id in member_ids
        })
        objects.append(family_object_payload(graph.name, graph.catalog, family, summary))
    return objects, hidden


def family_object_payload(
    graph_name: str,
    catalog: str,
    family: ObjectFamily,
    summary: dict[str, Any],
) -> dict[str, Any]:
    """Render an already validated family without inventing physical-table semantics."""
    object_id = f"object_family:{family.id}"
    return {
            "annotation": None,
            "annotation_context_documents": [],
            "area": None,
            "area_ref": None,
            "catalog": catalog,
            "fields": [
                {
                    "annotation": None,
                    "data_type": field.data_type,
                    "id": browser_id(graph_name, f"{object_id}:field:{index}"),
                    "is_nullable": field.nullable,
                    "kind": "family_field",
                    "label": field.name,
                    "position": index,
                    "source_semantics": [],
                }
                for index, field in enumerate(family.schema, start=1)
            ],
            "grain": " + ".join(family.grain),
            "graph": graph_name,
            "id": browser_id(graph_name, object_id),
            "label": family.name,
            "name": family.name,
            "namespace": "Logical families",
            "object_family": summary,
            "object_id": object_id,
            "primary_key": [],
            "reference": None,
            "review": None,
            "schema_ref": f"{graph_name}:Logical families",
            "source_semantics": [],
            "state": family.state,
            "system": None,
            "technical_description": None,
            "type": "object_family",
            "usage": summary["usage"],
            "zones": [],
        }


def compact_family_workspace_members(
    payload: dict[str, Any], collapsed: set[tuple[str, str]]
) -> None:
    # Zone editing is disabled in family view: sending a truncated member list to
    # the existing replace-style zone API would remove hidden members.
    visible = {
        (item["graph"], item["object_id"]) for item in payload["objects"]
        if item["type"] in {"table", "view"}
    }
    for workspace in payload["workspaces"]:
        for system in workspace["systems"]:
            for zone in system["zones"]:
                members = zone["members"]
                zone["members"] = [
                    item for item in members
                    if (item["graph"], item["object_id"]) in visible
                ]
                zone["collapsed_member_count"] = sum(
                    (item["graph"], item["object_id"]) in collapsed for item in members
                )


def family_view_scope_revision(
    graphs: Iterable[GraphDocument],
    documents: Iterable[FocusDocument],
    scope: ResolvedScope | None = None,
) -> str:
    """Bind member pages to the server-resolved physical and report/cube scope."""
    return family_view_scope_revision_from_revisions(
        {item.name: graph_revision(item) for item in graphs}, documents, scope,
    )


def family_view_scope_revision_from_revisions(
    revisions: dict[str, str],
    documents: Iterable[FocusDocument] = (),
    scope: ResolvedScope | None = None,
) -> str:
    """Identical view identity from verified full-source headers, not subset hashes."""
    payload = {
        "graphs": revisions,
        "focuses": {item.name: item.revision for item in documents},
        "workspace_scope": scope.scope_hash if scope else None,
    }
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode()).hexdigest()


def compact_family_focus_selection(
    selection: dict[str, Any],
    objects: list[dict[str, Any]],
    families: tuple[ObjectFamily, ...],
    allowed_objects: set[tuple[str, str]],
) -> dict[str, Any]:
    """Keep focus provenance without leaking or relabelling collapsed member hops."""
    visible_ids = {item["id"] for item in objects}
    allowed_ids = {browser_id(graph, object_id) for graph, object_id in allowed_objects}
    members = [
        item for item in selection["members"]
        if item["graph"] is None or item["id"] in allowed_ids
    ]
    physical = {
        item["id"]: item for item in members
        if item["graph"] is not None and item["id"] in allowed_ids
    }
    retained = [item for item in members if item["graph"] is None or item["id"] in visible_ids]
    by_family = {(item.graph_name, item.id): item for item in families}
    for item in objects:
        if item["type"] != "object_family":
            continue
        family = by_family[(item["graph"], item["object_family"]["id"])]
        included = [
            physical[identifier]
            for member_id in family.member_ids
            if (identifier := browser_id(family.graph_name, member_id)) in physical
        ]
        if not included:
            continue
        retained.append({
            "annotation_state": None,
            "depth": min(member["depth"] for member in included),
            "focuses": sorted({name for member in included for name in member["focuses"]}),
            "graph": item["graph"], "id": item["id"], "kind": "object_family",
            "label": item["name"], "origin": False,
            "reasons": ["contains_focus_members"], "reference": None,
            "source": f"graph:{item['graph']}",
        })
    kept_ids = {item["id"] for item in retained}
    scoped_ids = {item["id"] for item in members}
    scoped_edges = [
        edge for edge in selection["edges"]
        if edge["source"] in scoped_ids and edge["target"] in scoped_ids
    ]
    edges = [
        edge for edge in scoped_edges
        if edge["source"] in kept_ids and edge["target"] in kept_ids
    ]
    return {
        **selection,
        "members": sorted(retained, key=lambda item: item["id"]),
        "object_ids": sorted(visible_ids),
        "origins": [item for item in retained if item["origin"]],
        "edges": edges,
        "hidden_member_count": len(members) - sum(item["id"] in kept_ids for item in members),
        "hidden_edge_count": len(scoped_edges) - len(edges),
        "warnings": sorted({*selection["warnings"],
            "Collapsed physical focus members and their lineage hops are hidden; "
            "no family-wide relationship is inferred."}),
    }
