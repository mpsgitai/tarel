"""The Space canvas: objects, fields, edges, review state and workspace structure."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any

from tarel.discovery.coverage import QueryLinkedEntityCoverage
from tarel.entity_resolution.candidates import EntityResolutionMatch
from tarel.entity_resolution.projection import project_entity_resolution_edges
from tarel.focus.contracts import FocusDocument
from tarel.graph.contracts import GraphDocument, GraphEdge, GraphNode
from tarel.graph.revision import graph_revision
from tarel.lineage.contracts import LineageDocument
from tarel.object_families.contracts import ObjectFamily, ObjectFamilyFailure
from tarel.reference_mapping.contracts import ReferenceMappingMatch
from tarel.semantics.contracts import SemanticImportDocument
from tarel.semantics.projection import (
    semantic_edge_bindings,
    semantic_import_catalog,
    semantic_model_catalog,
    semantic_node_bindings,
)
from tarel.topology.application import validate_logical_topology_against_graph
from tarel.topology.contracts import LogicalTopologyDocument
from tarel.ui.payloads._ids import browser_id, combined_revision
from tarel.ui.payloads.families import (
    compact_family_focus_selection,
    compact_family_workspace_members,
    family_view_scope_revision_from_revisions,
    object_family_payloads,
)
from tarel.ui.payloads.focus import browser_focus_selection, focus_physical_objects
from tarel.ui.payloads.lineage import browser_lineages
from tarel.ui.payloads.lineage_flows import LineageFlowModel
from tarel.ui.payloads.logical import logical_topology_payloads, reference_mapping_edge_payloads
from tarel.ui.payloads.signals import attach_object_signals, extract_observed_rows
from tarel.workspaces.contracts import WorkspaceDocument
from tarel.workspaces.scope import ResolvedScope

_PENDING_ANNOTATION_STATES = frozenset({"draft", "review_required", "deferred"})


def browser_graph(
    graph: GraphDocument,
    *,
    workspaces: Iterable[WorkspaceDocument] = (),
    lineage_names: tuple[str, ...] = (),
    editable: bool = False,
    lineage_documents: Iterable[LineageDocument] = (),
    semantic_imports: Iterable[SemanticImportDocument] = (),
    entity_resolution_matches: Iterable[EntityResolutionMatch] = (),
    query_linked_coverages: Iterable[QueryLinkedEntityCoverage] = (),
    logical_topologies: Iterable[LogicalTopologyDocument] = (),
    logical_topology_stale_graphs: Iterable[str] = (),
    reference_mapping_matches: Iterable[ReferenceMappingMatch] = (),
    family_mode: str | None = None,
    object_families: Iterable[ObjectFamily] = (),
    object_family_stale_graphs: Iterable[str] = (),
    focus_documents: Iterable[FocusDocument] = (),
) -> dict[str, Any]:
    return _browser_payload(
        (graph,),
        workspaces=tuple(workspaces),
        lineage_names=lineage_names,
        editable=editable,
        lineage_documents=tuple(lineage_documents),
        semantic_imports=tuple(semantic_imports),
        entity_resolution_matches=tuple(entity_resolution_matches),
        query_linked_coverages=tuple(query_linked_coverages),
        logical_topologies=tuple(logical_topologies),
        logical_topology_stale_graphs=tuple(logical_topology_stale_graphs),
        reference_mapping_matches=tuple(reference_mapping_matches),
        family_mode=family_mode,
        object_families=tuple(object_families),
        object_family_stale_graphs=tuple(object_family_stale_graphs),
        focus_documents=tuple(focus_documents),
    )


def browser_workspace(
    graphs: Iterable[GraphDocument],
    scope: ResolvedScope,
    *,
    workspace: WorkspaceDocument,
    editable: bool = False,
    lineage_documents: Iterable[LineageDocument] = (),
    semantic_imports: Iterable[SemanticImportDocument] = (),
    entity_resolution_matches: Iterable[EntityResolutionMatch] = (),
    query_linked_coverages: Iterable[QueryLinkedEntityCoverage] = (),
    logical_topologies: Iterable[LogicalTopologyDocument] = (),
    logical_topology_stale_graphs: Iterable[str] = (),
    reference_mapping_matches: Iterable[ReferenceMappingMatch] = (),
    family_mode: str | None = None,
    object_families: Iterable[ObjectFamily] = (),
    object_family_stale_graphs: Iterable[str] = (),
    focus_documents: Iterable[FocusDocument] = (),
) -> dict[str, Any]:
    payload = _browser_payload(
        tuple(graphs),
        workspaces=(workspace,),
        editable=editable,
        lineage_documents=tuple(lineage_documents),
        semantic_imports=tuple(semantic_imports),
        entity_resolution_matches=tuple(entity_resolution_matches),
        query_linked_coverages=tuple(query_linked_coverages),
        logical_topologies=tuple(logical_topologies),
        logical_topology_stale_graphs=tuple(logical_topology_stale_graphs),
        reference_mapping_matches=tuple(reference_mapping_matches),
        family_mode=family_mode,
        object_families=tuple(object_families),
        object_family_stale_graphs=tuple(object_family_stale_graphs),
        focus_documents=tuple(focus_documents),
        scope=scope,
    )
    objects = payload["objects"]
    edges = payload["edges"]
    if isinstance(objects, list) and isinstance(edges, list):
        workspace_edges = _workspace_relationship_payloads(workspace, objects)
        if workspace_edges:
            edges.extend(workspace_edges)
            edges.sort(key=lambda item: str(item["id"]))
            attach_object_signals(payload, lineage_loaded=bool(payload.get("lineage_documents")))
    return payload


def _browser_payload(
    graphs: tuple[GraphDocument, ...],
    *,
    workspaces: tuple[WorkspaceDocument, ...],
    editable: bool,
    lineage_documents: tuple[LineageDocument, ...],
    semantic_imports: tuple[SemanticImportDocument, ...],
    entity_resolution_matches: tuple[EntityResolutionMatch, ...],
    query_linked_coverages: tuple[QueryLinkedEntityCoverage, ...],
    logical_topologies: tuple[LogicalTopologyDocument, ...],
    logical_topology_stale_graphs: tuple[str, ...],
    reference_mapping_matches: tuple[ReferenceMappingMatch, ...],
    family_mode: str | None,
    object_families: tuple[ObjectFamily, ...],
    object_family_stale_graphs: tuple[str, ...],
    focus_documents: tuple[FocusDocument, ...],
    lineage_names: tuple[str, ...] = (),
    scope: ResolvedScope | None = None,
) -> dict[str, Any]:
    if not graphs:
        raise ValueError("Browser projection requires at least one graph.")
    if family_mode not in {None, "confirmed_only", "include_candidates"}:
        raise ObjectFamilyFailure("invalid_object_family_mode", "Unsupported family policy.")
    selected = (
        {(item.graph, item.object_id): item for item in scope.objects}
        if scope is not None
        else None
    )
    focus_objects = focus_physical_objects(focus_documents) if focus_documents else None
    object_payloads: list[dict[str, Any]] = []
    edge_payloads: list[dict[str, Any]] = []
    graph_names = {graph.name for graph in graphs}
    imports = tuple(
        item for item in semantic_imports if item.graph_name in graph_names
    )
    topology_by_graph: dict[str, LogicalTopologyDocument] = {}
    for document in logical_topologies:
        if document.graph_name not in graph_names:
            continue
        if document.graph_name in topology_by_graph:
            raise ValueError(
                "Browser projection received multiple logical topologies for "
                f"{document.graph_name}."
            )
        topology_by_graph[document.graph_name] = document
    node_semantics = semantic_node_bindings(imports)
    edge_semantics = semantic_edge_bindings(imports)
    collapsed: set[tuple[str, str]] = set()
    collapsed_fields: set[tuple[str, str]] = set()
    visible_fields: set[tuple[str, str]] = set()
    allowed_objects: set[tuple[str, str]] = set()
    observed_rows_by_id: dict[str, int | None] = {}
    for graph in sorted(graphs, key=lambda item: item.name):
        nodes = graph.node_by_id()
        objects = [
            node
            for node in graph.nodes
            if node.type in {"table", "view"}
            and (selected is None or (graph.name, node.id) in selected)
            and (focus_objects is None or (graph.name, node.id) in focus_objects)
        ]
        object_ids = {node.id for node in objects}
        allowed_objects.update((graph.name, object_id) for object_id in object_ids)
        if family_mode is not None:
            family_payloads, hidden_ids = object_family_payloads(
                graph, object_families, object_ids, family_mode,
                topology_by_graph.get(graph.name), reference_mapping_matches,
                entity_resolution_matches,
            )
            object_payloads.extend(family_payloads)
            collapsed.update((graph.name, object_id) for object_id in hidden_ids)
            collapsed_fields.update(
                (graph.name, node.id) for node in graph.nodes
                if node.type == "field" and node.metadata.get("object_id") in hidden_ids
            )
            objects = [node for node in objects if node.id not in hidden_ids]
            object_ids -= hidden_ids
        fields_by_object: dict[str, list[GraphNode]] = {node.id: [] for node in objects}
        for node in graph.nodes:
            if node.type == "field":
                parent = str(node.metadata.get("object_id") or "")
                if parent in fields_by_object:
                    fields_by_object[parent].append(node)
                    visible_fields.add((graph.name, node.id))
        for node in objects:
            observed_rows_by_id[browser_id(graph.name, node.id)] = extract_observed_rows(
                node.metadata
            )
        physical_payloads = [
            _object_payload(
                node,
                fields_by_object[node.id],
                graph=graph,
                semantic_bindings=node_semantics,
                scope_object=selected.get((graph.name, node.id)) if selected else None,
            )
            for node in sorted(objects, key=lambda item: (item.label.casefold(), item.id))
        ]
        object_payloads.extend(physical_payloads)
        edge_payloads.extend(
            payload
            for edge in sorted(graph.edges, key=lambda item: item.id)
            if edge.source_id in object_ids and edge.target_id in object_ids
            if (
                payload := edge_payload(
                    edge,
                    nodes,
                    graph.name,
                    source_semantics=edge_semantics.get((graph.name, edge.id), ()),
                )
            ) is not None
        )
        topology = topology_by_graph.get(graph.name)
        if topology is not None:
            validate_logical_topology_against_graph(topology, graph)
            logical_objects, derivation_edges = logical_topology_payloads(
                graph,
                topology,
                physical_payloads,
            )
            object_payloads.extend(logical_objects)
            edge_payloads.extend(derivation_edges)
        graph_mapping_matches = tuple(
            match
            for match in reference_mapping_matches
            if match.candidate.graph_name == graph.name
        )
        edge_payloads.extend(
            reference_mapping_edge_payloads(
                graph,
                graph_mapping_matches,
                visible_object_ids=object_ids,
            )
        )
        graph_entity_matches = tuple(
            item
            for item in entity_resolution_matches
            if item.candidate.graph_name == graph.name
        )
        edge_payloads.extend(
            payload
            for edge in project_entity_resolution_edges(graph, graph_entity_matches)
            if family_mode is None
            or (edge.source_id in object_ids and edge.target_id in object_ids)
            if (
                payload := edge_payload(
                    edge,
                    nodes,
                    graph.name,
                )
            ) is not None
        )

    documents = tuple(lineage_documents)
    selected_lineages = tuple(item.name for item in documents) or lineage_names
    lineage_model = LineageFlowModel(documents, object_payloads)
    full_lineage_edges = tuple(
        (edge.source, edge.target) for edge in lineage_model.edges.values()
    )
    revisions = {graph.name: graph_revision(graph) for graph in graphs}
    revision = (
        next(iter(revisions.values()))
        if len(revisions) == 1
        else combined_revision(revisions)
    )
    graph_payloads = [
        {
            "catalog": graph.catalog,
            "connector": graph.connector,
            "dialect": graph.dialect,
            "name": graph.name,
            "revision": revisions[graph.name],
            "source_type": graph.source_type,
        }
        for graph in sorted(graphs, key=lambda item: item.name)
    ]
    first = sorted(graphs, key=lambda item: item.name)[0]
    payload = {
        "catalog": first.catalog if len(graphs) == 1 else None,
        "connector": first.connector if len(graphs) == 1 else None,
        "dialect": first.dialect if len(graphs) == 1 else None,
        "editable": editable,
        "edges": sorted(edge_payloads, key=lambda item: str(item["id"])),
        "entity_resolution": [
            item.to_dict()
            for item in sorted(
                entity_resolution_matches,
                key=lambda match: (match.candidate.graph_name, match.candidate.id),
            )
            if not any(
                (item.candidate.graph_name, endpoint) in collapsed_fields
                for endpoint in (
                    item.candidate.source_field_id,
                    item.candidate.target_field_id,
                )
            )
            and (not focus_documents or all(
                (item.candidate.graph_name, endpoint) in visible_fields
                for endpoint in (
                    item.candidate.source_field_id, item.candidate.target_field_id
                )
            ))
        ],
        "graph": first.name,
        "graphs": graph_payloads,
        "lineage_documents": browser_lineages(documents),
        "lineage_flows": lineage_model.payload(),
        "lineages": list(selected_lineages),
        "logical_topology_notices": [
            {
                "code": "logical_topology_graph_revision_mismatch",
                "graph": graph_name,
                "message": (
                    "The physical graph changed; its stale logical-topology sidecar "
                    "was not projected."
                ),
            }
            for graph_name in sorted(set(logical_topology_stale_graphs) & graph_names)
        ],
        "objects": object_payloads,
        "query_linked_coverages": [
            query_linked_coverage_summary(item, entity_resolution_matches)
            for item in sorted(query_linked_coverages, key=lambda coverage: coverage.run_id)
            if item.graph_name in graph_names
        ],
        "review": _review_queue(object_payloads),
        # A family is a visual summary, not a decision about its member annotations.
        # Count the authorized physical scope without serializing hidden member IDs.
        "review_summary": summarize_review(graphs, allowed_objects),
        "revision": revision,
        "revisions": revisions,
        "scope": scope.to_dict() if scope else None,
        "semantic_imports": semantic_import_catalog(imports),
        "semantic_models": semantic_model_catalog(imports),
        "source_type": first.source_type if len(graphs) == 1 else "workspace",
        "title": scope.workspace if scope else first.name,
        "view_modes": ["space", "lineage"],
        "workspaces": [
            _workspace_payload_for_graphs(workspace, {graph.name for graph in graphs})
            for workspace in sorted(workspaces, key=lambda item: item.name)
            if any(
                graph.name in system.graphs
                for graph in graphs
                for system in workspace.systems
            )
        ],
    }
    if family_mode is not None:
        payload["object_families"] = {
            "mode": family_mode,
            "scope_revision": family_view_scope_revision_from_revisions(
                revisions, focus_documents, scope,
            ),
            "collapsed_member_count": len(collapsed),
            "stale_graphs": sorted(set(object_family_stale_graphs) & graph_names),
            "notice": (
                "Families summarize compatible schemas, not union or join correctness. "
                "Members load on demand. Disable families to inspect member annotations, "
                "relationships, derivations, zones and lineage. "
                "Annotation review loads the physical scope separately."
            ),
        }
        if scope is not None:
            payload["scope"] = {
                "graphs": list(scope.graph_names),
                "object_count": sum(
                    focus_objects is None or (item.graph, item.object_id) in focus_objects
                    for item in scope.objects
                ),
                "scope_hash": scope.scope_hash,
                "selection": scope.selection.to_dict(),
                "workspace": scope.workspace,
            }
        compact_family_workspace_members(payload, collapsed)
    if focus_documents:
        selection = browser_focus_selection(focus_documents)
        payload["focus_selection"] = (
            compact_family_focus_selection(
                selection, object_payloads, object_families, allowed_objects
            )
            if family_mode is not None else selection
        )
    attach_object_signals(
        payload,
        observed_rows_by_id=observed_rows_by_id,
        lineage_loaded=bool(documents),
        lineage_edges=full_lineage_edges,
    )
    return payload


def query_linked_coverage_summary(
    coverage: QueryLinkedEntityCoverage,
    matches: tuple[EntityResolutionMatch, ...],
) -> dict[str, Any]:
    summary = coverage.to_summary_dict()
    current_usages = {
        match.usage
        for match in matches
        if match.candidate.id in coverage.candidate_refs
    }
    if "exploratory_only" in current_usages:
        summary["candidate_usage"] = "exploratory_only"
    elif "confirmed" in current_usages:
        summary["candidate_usage"] = "confirmed"
    return summary


def workspace_revision(workspace: WorkspaceDocument) -> str:
    payload = json.dumps(
        workspace.to_dict(),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _object_payload(
    node: GraphNode,
    fields: list[GraphNode],
    *,
    graph: GraphDocument,
    semantic_bindings: dict[tuple[str, str], list[dict[str, Any]]],
    scope_object: object | None = None,
) -> dict[str, Any]:
    annotation = node.annotation.to_dict() if node.annotation else None
    area = getattr(scope_object, "area", None)
    system = getattr(scope_object, "system", None)
    zones = tuple(getattr(scope_object, "zones", ()))
    return {
        "annotation": annotation,
        "annotation_context_documents": node.metadata.get(
            "annotation_context_documents", []
        ),
        "area": area,
        "area_ref": f"{system}:{area}" if system and area else None,
        "catalog": graph.catalog,
        "fields": [
            _field_payload(
                field,
                graph.name,
                parent_label=node.label,
                source_semantics=semantic_bindings.get((graph.name, field.id), ()),
            )
            for field in sorted(
                fields,
                key=lambda item: (int(item.metadata.get("position") or 999999), item.id),
            )
        ],
        "grain": node.metadata.get("grain"),
        "graph": graph.name,
        "id": browser_id(graph.name, node.id),
        "label": node.label,
        "name": node.metadata.get("name") or node.label,
        "namespace": node.metadata.get("namespace"),
        "object_id": node.id,
        "primary_key": list(node.metadata.get("primary_key") or ()),
        "reference": f"{graph.catalog}.{node.label}",
        "review": node.metadata.get("annotation_review"),
        "source_change": node.metadata.get("source_change"),
        "system": system,
        "schema_ref": f"{graph.name}:{node.metadata.get('namespace')}",
        "source_semantics": semantic_bindings.get((graph.name, node.id), ()),
        "technical_description": node.metadata.get("technical_description"),
        "type": node.type,
        "zones": list(zones),
    }


def _field_payload(
    node: GraphNode,
    graph_name: str,
    *,
    parent_label: str,
    source_semantics: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    return {
        "annotation": node.annotation.to_dict() if node.annotation else None,
        "annotation_context_documents": node.metadata.get(
            "annotation_context_documents", []
        ),
        "data_type": node.metadata.get("data_type"),
        "id": browser_id(graph_name, node.id),
        "is_nullable": node.metadata.get("is_nullable"),
        "label": node.label,
        "position": node.metadata.get("position"),
        "reference": f"{parent_label}.{node.label}",
        "review": node.metadata.get("annotation_review"),
        "semantic_type": node.metadata.get("semantic_type"),
        "source_change": node.metadata.get("source_change"),
        "source_semantics": list(source_semantics),
    }


def edge_payload(
    edge: GraphEdge,
    nodes: dict[str, GraphNode],
    graph_name: str,
    *,
    source_semantics: Iterable[dict[str, Any]] = (),
) -> dict[str, Any] | None:
    if edge.type not in {
        "entity_resolution_candidate",
        "foreign_key",
        "relationship_candidate",
    }:
        return None
    source = nodes.get(edge.source_id)
    target = nodes.get(edge.target_id)
    if edge.type in {"entity_resolution_candidate", "relationship_candidate"}:
        if source is not None and source.type == "field":
            source = nodes.get(str(source.metadata.get("object_id") or ""))
        if target is not None and target.type == "field":
            target = nodes.get(str(target.metadata.get("object_id") or ""))
    if source is None or target is None or source.type not in {"table", "view"}:
        return None
    if target.type not in {"table", "view"}:
        return None
    return {
        "graph": graph_name,
        "id": browser_id(graph_name, edge.id),
        "metadata": edge.metadata,
        "source_semantics": list(source_semantics),
        "source": browser_id(graph_name, source.id),
        "target": browser_id(graph_name, target.id),
        "type": edge.type,
    }


def _workspace_relationship_payloads(
    workspace: WorkspaceDocument,
    objects: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_reference = {
        (str(item["graph"]), str(item["object_id"])): str(item["id"])
        for item in objects
    }
    payloads = []
    for relationship in workspace.relationships:
        source = by_reference.get(
            (relationship.source.graph, relationship.source.object_id)
        )
        target = by_reference.get(
            (relationship.target.graph, relationship.target.object_id)
        )
        if source is None or target is None:
            continue
        payloads.append(
            {
                "graph": None,
                "id": f"workspace::{workspace.name}::{relationship.id}",
                "metadata": {
                    "from_field": relationship.source.fields[0],
                    "origin": relationship.origin,
                    "reason": relationship.reason,
                    "state": relationship.state,
                    "to_field": relationship.target.fields[0],
                    "workspace": workspace.name,
                },
                "source": source,
                "target": target,
                "type": "relationship_candidate",
            }
        )
    return payloads


def _review_queue(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rank = {"draft": 0, "review_required": 1, "deferred": 2, "missing": 3,
            "validated": 4, "rejected": 5}
    records = []
    for item in objects:
        if item.get("type") not in {"table", "view"}:
            continue
        annotation = item["annotation"]
        state = str(annotation["state"]) if isinstance(annotation, dict) else "missing"
        fields = item["fields"]
        pending_fields = sum(
            isinstance(field.get("annotation"), dict)
            and field["annotation"].get("state") in _PENDING_ANNOTATION_STATES
            for field in fields
        )
        pending_table = int(state in _PENDING_ANNOTATION_STATES)
        records.append({
            "annotation": annotation,
            "context_documents": item.get("annotation_context_documents", []),
            "field_count": len(fields),
            "graph": item["graph"],
            "grain": item["grain"],
            "has_pending": bool(pending_table or pending_fields),
            "id": item["id"],
            "label": item["label"],
            "missing_field_count": sum(field.get("annotation") is None for field in fields),
            "namespace": item.get("namespace"),
            "object_id": item["object_id"],
            "pending_field_count": pending_fields,
            "pending_table_count": pending_table,
            "review": item["review"],
            "schema_ref": item.get("schema_ref"),
            "state": state,
            "type": item["type"],
        })
    return sorted(records, key=lambda item: (rank.get(str(item["state"]), 99), str(item["label"])))


def summarize_review(
    graphs: tuple[GraphDocument, ...],
    allowed_objects: set[tuple[str, str]],
) -> dict[str, Any]:
    """Aggregate review work before visual collapse, never outside the physical scope."""
    pending_tables = pending_fields = missing_tables = missing_fields = 0
    pending_objects: set[tuple[str, str]] = set()
    for graph in graphs:
        for node in graph.nodes:
            if node.type in {"table", "view"}:
                reference = (graph.name, node.id)
            elif node.type == "field":
                reference = (graph.name, str(node.metadata.get("object_id") or ""))
            else:
                continue
            if reference not in allowed_objects:
                continue
            is_field = node.type == "field"
            if node.annotation is None:
                missing_fields += int(is_field)
                missing_tables += int(not is_field)
            elif node.annotation.state in _PENDING_ANNOTATION_STATES:
                pending_fields += int(is_field)
                pending_tables += int(not is_field)
                pending_objects.add(reference)
    return {
        "known": True,
        "missing_fields": missing_fields,
        "missing_tables": missing_tables,
        "pending_fields": pending_fields,
        "pending_tables": pending_tables,
        "review_objects": len(pending_objects),
        "total_objects": len(allowed_objects),
    }


def _workspace_payload(workspace: WorkspaceDocument, graph_name: str) -> dict[str, Any] | None:
    systems = []
    for system in workspace.systems:
        if graph_name not in system.graphs:
            continue
        systems.append({
            "areas": [item.to_dict() for item in system.areas],
            "description": system.description,
            "name": system.name,
            "zones": [item.to_dict() for item in system.zones],
        })
    if not systems:
        return None
    return {
        "description": workspace.description,
        "name": workspace.name,
        "revision": workspace_revision(workspace),
        "systems": systems,
    }


def _workspace_payload_for_graphs(
    workspace: WorkspaceDocument,
    graph_names: set[str],
) -> dict[str, Any]:
    systems = [
        system.to_dict()
        for system in workspace.systems
        if graph_names.intersection(system.graphs)
    ]
    return {
        "description": workspace.description,
        "name": workspace.name,
        "revision": workspace_revision(workspace),
        "systems": systems,
    }
