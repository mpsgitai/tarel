"""Pure browser projections over TAREL graph and workspace contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable

from tarel.discovery.coverage import QueryLinkedEntityCoverage
from tarel.entity_resolution.contracts import EntityResolutionMatch
from tarel.entity_resolution.projection import project_entity_resolution_edges
from tarel.focus.contracts import FocusDocument, FocusMember
from tarel.graph.contracts import GraphDocument, GraphEdge, GraphNode
from tarel.graph.revision import graph_revision, physical_graph_revision
from tarel.lineage.contracts import LineageDocument
from tarel.lineage.revision import lineage_revision
from tarel.object_families.application import (
    family_summary,
    validate_object_families_against_graph,
)
from tarel.object_families.contracts import ObjectFamily, ObjectFamilyFailure
from tarel.reference_mapping.contracts import (
    ReferenceMappingEvidence,
    ReferenceMappingFailure,
    ReferenceMappingMatch,
)
from tarel.semantics.contracts import SemanticImportDocument
from tarel.semantics.projection import (
    semantic_edge_bindings,
    semantic_import_catalog,
    semantic_model_catalog,
    semantic_node_bindings,
)
from tarel.topology.application import validate_logical_topology_against_graph
from tarel.topology.contracts import DerivationEvidence, LogicalTopologyDocument
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
) -> dict[str, object]:
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
) -> dict[str, object]:
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
        edges.extend(_workspace_relationship_payloads(workspace, objects))
        edges.sort(key=lambda item: str(item["id"]))
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
) -> dict[str, object]:
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
    object_payloads: list[dict[str, object]] = []
    edge_payloads: list[dict[str, object]] = []
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
            family_payloads, hidden_ids = _object_family_payloads(
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
                payload := _edge_payload(
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
            logical_objects, derivation_edges = _logical_topology_payloads(
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
            _reference_mapping_edge_payloads(
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
                payload := _edge_payload(
                    edge,
                    nodes,
                    graph.name,
                )
            ) is not None
        )

    documents = tuple(lineage_documents)
    selected_lineages = tuple(item.name for item in documents) or lineage_names
    revisions = {graph.name: graph_revision(graph) for graph in graphs}
    revision = (
        next(iter(revisions.values()))
        if len(revisions) == 1
        else _combined_revision(revisions)
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
        "lineage_flows": browser_lineage_flows(documents, object_payloads),
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
            _query_linked_coverage_summary(item, entity_resolution_matches)
            for item in sorted(query_linked_coverages, key=lambda coverage: coverage.run_id)
            if item.graph_name in graph_names
        ],
        "review": _review_queue(object_payloads),
        # A family is a visual summary, not a decision about its member annotations.
        # Count the authorized physical scope without serializing hidden member IDs.
        "review_summary": _review_summary(graphs, allowed_objects),
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
            "scope_revision": family_view_scope_revision(graphs, focus_documents, scope),
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
        _compact_family_workspace_members(payload, collapsed)
    if focus_documents:
        selection = browser_focus_selection(focus_documents)
        payload["focus_selection"] = (
            _compact_family_focus_selection(
                selection, object_payloads, object_families, allowed_objects
            )
            if family_mode is not None else selection
        )
    return payload


def _object_family_payloads(
    graph: GraphDocument,
    families: tuple[ObjectFamily, ...],
    allowed_ids: set[str],
    mode: str,
    topology: LogicalTopologyDocument | None,
    mappings: tuple[ReferenceMappingMatch, ...],
    entities: tuple[EntityResolutionMatch, ...],
) -> tuple[list[dict[str, object]], set[str]]:
    """Collapse metadata only; a member edge never becomes a family-wide edge."""
    objects: list[dict[str, object]] = []
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
        objects.append(_family_object_payload(graph.name, graph.catalog, family, summary))
    return objects, hidden


def _family_object_payload(
    graph_name: str,
    catalog: str,
    family: ObjectFamily,
    summary: dict[str, object],
) -> dict[str, object]:
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
                    "id": _ui_id(graph_name, f"{object_id}:field:{index}"),
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
            "id": _ui_id(graph_name, object_id),
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


def _compact_family_workspace_members(
    payload: dict[str, object], collapsed: set[tuple[str, str]]
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


def _query_linked_coverage_summary(
    coverage: QueryLinkedEntityCoverage,
    matches: tuple[EntityResolutionMatch, ...],
) -> dict[str, object]:
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


def browser_lineages(documents: Iterable[LineageDocument]) -> list[dict[str, object]]:
    payload = []
    for document in sorted(documents, key=lambda item: item.name):
        definitions = document.definition_by_id()
        descriptions = {item.definition_id: item.summary for item in document.analyses}
        jobs = [
            {
                "description": descriptions.get(item.id),
                "id": item.id,
                "kind": item.kind,
                "language": item.language,
                "name": item.name,
                "qualified_name": item.qualified_name,
                "source_reference": item.source_reference,
            }
            for item in sorted(
                document.definitions,
                key=lambda item: item.qualified_name.casefold(),
            )
        ]
        hops = []
        for unit in sorted(document.write_units, key=lambda item: item.id):
            definition = definitions[unit.definition_id]
            for source in unit.sources:
                hops.append(
                    {
                        "evidence": source.evidence.to_dict(),
                        "item_id": unit.id,
                        "job": definition.qualified_name,
                        "operation": unit.operation,
                        "reviews": [item.to_dict() for item in unit.reviews],
                        "role": source.role,
                        "source": source.target,
                        "state": unit.state,
                        "target": unit.target,
                    }
                )
        payload.append(
            {
                "hops": hops,
                "jobs": jobs,
                "manual": document.source_kind == "manual",
                "name": document.name,
                "revision": lineage_revision(document),
                "source_kind": document.source_kind,
            }
        )
    return payload


def browser_lineage_flows(
    documents: Iterable[LineageDocument],
    objects: list[dict[str, object]],
) -> dict[str, object]:
    aliases: dict[str, list[str]] = {}
    for item in objects:
        for alias in (
            str(item["id"]),
            str(item["object_id"]),
            str(item["label"]),
            str(item["reference"]),
        ):
            aliases.setdefault(_normalize_reference(alias), []).append(str(item["id"]))

    nodes: dict[str, dict[str, object]] = {}
    edges: dict[str, dict[str, object]] = {}

    def reference_node(reference: str) -> str:
        matches = sorted(set(aliases.get(_normalize_reference(reference), ())))
        if len(matches) == 1:
            return matches[0]
        identifier = "lineage-ref::" + hashlib.sha256(
            _normalize_reference(reference).encode()
        ).hexdigest()[:20]
        nodes.setdefault(
            identifier,
            {
                "graph": None,
                "id": identifier,
                "kind": "asset",
                "label": _display_reference(reference),
                "reference": reference,
            },
        )
        return identifier

    for document in sorted(documents, key=lambda item: item.name):
        definitions = document.definition_by_id()
        job_ids: dict[str, str] = {}
        for definition in document.definitions:
            identifier = f"lineage-job::{document.name}::{definition.id}"
            job_ids[definition.id] = identifier
            nodes[identifier] = {
                "description": next(
                    (
                        analysis.summary
                        for analysis in document.analyses
                        if analysis.definition_id == definition.id
                    ),
                    None,
                ),
                "graph": None,
                "id": identifier,
                "kind": definition.kind,
                "label": definition.name,
                "lineage": document.name,
                "reference": definition.qualified_name,
            }
            for alias in (definition.id, definition.name, definition.qualified_name):
                aliases.setdefault(_normalize_reference(alias), []).append(identifier)

        for claim in sorted(document.claims, key=lambda item: item.id):
            if claim.operation != "read":
                continue
            source = reference_node(claim.target)
            target = job_ids[claim.definition_id]
            identifier = f"lineage-edge::{document.name}::{claim.id}"
            edges[identifier] = {
                "id": identifier,
                "job": definitions[claim.definition_id].qualified_name,
                "lineage": document.name,
                "relation": "read",
                "source": source,
                "state": claim.state,
                "target": target,
            }

        for unit in sorted(document.write_units, key=lambda item: item.id):
            job = job_ids[unit.definition_id]
            for position, source in enumerate(unit.sources, start=1):
                identifier = f"lineage-edge::{document.name}::{unit.id}::source::{position}"
                edges[identifier] = {
                    "id": identifier,
                    "job": definitions[unit.definition_id].qualified_name,
                    "lineage": document.name,
                    "relation": source.role,
                    "source": reference_node(source.target),
                    "state": unit.state,
                    "target": job,
                }
            identifier = f"lineage-edge::{document.name}::{unit.id}::target"
            edges[identifier] = {
                "id": identifier,
                "job": definitions[unit.definition_id].qualified_name,
                "lineage": document.name,
                "relation": unit.operation,
                "source": job,
                "state": unit.state,
                "target": reference_node(unit.target),
            }

        steps = {item.id: item for item in document.steps}
        for step in document.steps:
            target = job_ids[step.definition_id]
            for dependency in step.depends_on:
                source_step = steps.get(dependency)
                if source_step is None:
                    continue
                identifier = f"process-edge::{document.name}::{dependency}::{step.id}"
                edges[identifier] = {
                    "id": identifier,
                    "job": None,
                    "lineage": document.name,
                    "relation": "precedes",
                    "source": job_ids[source_step.definition_id],
                    "state": "observed",
                    "target": target,
                    "type": "process",
                }

    return {
        "edges": [edges[key] for key in sorted(edges)],
        "nodes": [nodes[key] for key in sorted(nodes)],
    }


def browser_focus_catalog(
    documents: Iterable[FocusDocument],
    *,
    stale_reasons: dict[str, str] | None = None,
) -> list[dict[str, object]]:
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


def _compact_family_focus_selection(
    selection: dict[str, object],
    objects: list[dict[str, object]],
    families: tuple[ObjectFamily, ...],
    allowed_objects: set[tuple[str, str]],
) -> dict[str, object]:
    """Keep focus provenance without leaking or relabelling collapsed member hops."""
    visible_ids = {item["id"] for item in objects}
    allowed_ids = {_ui_id(graph, object_id) for graph, object_id in allowed_objects}
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
            if (identifier := _ui_id(family.graph_name, member_id)) in physical
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


def browser_focus_selection(documents: Iterable[FocusDocument]) -> dict[str, object]:
    selected = tuple(sorted(documents, key=lambda item: item.name.casefold()))
    members: dict[str, dict[str, object]] = {}
    edges: dict[tuple[str, ...], dict[str, object]] = {}
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
    return _ui_id(graph, item.id.removeprefix(prefix)) if graph else f"focus::{item.id}"


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
    semantic_bindings: dict[tuple[str, str], list[dict[str, object]]],
    scope_object: object | None = None,
) -> dict[str, object]:
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
                source_semantics=semantic_bindings.get((graph.name, field.id), ()),
            )
            for field in sorted(
                fields,
                key=lambda item: (int(item.metadata.get("position") or 999999), item.id),
            )
        ],
        "grain": node.metadata.get("grain"),
        "graph": graph.name,
        "id": _ui_id(graph.name, node.id),
        "label": node.label,
        "name": node.metadata.get("name") or node.label,
        "namespace": node.metadata.get("namespace"),
        "object_id": node.id,
        "primary_key": list(node.metadata.get("primary_key") or ()),
        "reference": f"{graph.catalog}.{node.label}",
        "review": node.metadata.get("annotation_review"),
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
    source_semantics: Iterable[dict[str, object]] = (),
) -> dict[str, object]:
    return {
        "annotation": node.annotation.to_dict() if node.annotation else None,
        "annotation_context_documents": node.metadata.get(
            "annotation_context_documents", []
        ),
        "data_type": node.metadata.get("data_type"),
        "id": _ui_id(graph_name, node.id),
        "is_nullable": node.metadata.get("is_nullable"),
        "label": node.label,
        "position": node.metadata.get("position"),
        "review": node.metadata.get("annotation_review"),
        "semantic_type": node.metadata.get("semantic_type"),
        "source_semantics": list(source_semantics),
    }


def _logical_topology_payloads(
    graph: GraphDocument,
    document: LogicalTopologyDocument,
    physical_objects: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    nodes = graph.node_by_id()
    physical_by_id = {
        str(item["object_id"]): item
        for item in physical_objects
        if item.get("type") in {"table", "view"}
    }
    objects: list[dict[str, object]] = []
    edges: list[dict[str, object]] = []
    for relation in sorted(document.derived_relations, key=lambda item: (item.name, item.id)):
        source = nodes.get(relation.source.id)
        source_payload = physical_by_id.get(relation.source.id)
        if source is None or source_payload is None:
            continue
        field_names = {field.id: field.name for field in relation.output_schema}
        grain_names = tuple(
            field_names[field_id]
            for field_id in relation.grain.field_ids
            if field_id in field_names
        )
        object_id = f"logical_relation:{relation.id}"
        ui_id = _ui_id(graph.name, object_id)
        usage = _reviewed_usage(relation.state)
        review = (
            {
                "decision": relation.review.decision,
                "source": relation.review.source,
            }
            if relation.review is not None
            else None
        )
        logical = {
            "document_revision": document.revision,
            "evidence": [
                _derivation_evidence_summary(item)
                for item in sorted(relation.evidence, key=lambda item: item.id)
            ],
            "grain_fields": list(grain_names),
            "plan_revision": relation.plan_revision,
            "requires_runtime_validation": relation.state == "candidate",
            "review": review,
            "source": str(source_payload["id"]),
            "source_object": source.label,
            "state": relation.state,
            "step_kinds": [step.kind for step in relation.steps],
            "usage": usage,
            "usable": relation.state == "reviewed",
        }
        namespace = source_payload.get("namespace")
        label = f"{namespace}.{relation.name}" if namespace else relation.name
        objects.append(
            {
                "annotation": None,
                "annotation_context_documents": [],
                "area": source_payload.get("area"),
                "area_ref": source_payload.get("area_ref"),
                "catalog": graph.catalog,
                "fields": [
                    {
                        "annotation": None,
                        "annotation_context_documents": [],
                        "data_type": field.data_type,
                        "id": _ui_id(
                            graph.name,
                            f"logical_relation:{relation.id}:field:{field.id}",
                        ),
                        "is_nullable": field.nullable,
                        "kind": field.kind,
                        "label": field.name,
                        "position": position,
                        "review": None,
                        "semantic_type": None,
                        "source_semantics": [],
                    }
                    for position, field in enumerate(relation.output_schema, start=1)
                ],
                "grain": " + ".join(grain_names),
                "graph": graph.name,
                "id": ui_id,
                "label": label,
                "logical_topology": logical,
                "name": relation.name,
                "namespace": namespace,
                "object_id": object_id,
                "primary_key": list(grain_names),
                "reference": f"{graph.catalog}.{label}",
                "review": review,
                "schema_ref": source_payload.get("schema_ref"),
                "state": relation.state,
                "system": source_payload.get("system"),
                "technical_description": None,
                "type": "derived_relation",
                "usage": usage,
                "zones": list(source_payload.get("zones") or ()),
            }
        )
        edges.append(
            {
                "graph": graph.name,
                "id": _ui_id(graph.name, f"derives:{relation.id}"),
                "metadata": {
                    "plan_revision": relation.plan_revision,
                    "state": relation.state,
                    "step_kinds": [step.kind for step in relation.steps],
                    "usage": usage,
                },
                "source": str(source_payload["id"]),
                "target": ui_id,
                "type": "derives",
            }
        )
    return objects, edges


def _derivation_evidence_summary(evidence: DerivationEvidence) -> dict[str, object]:
    return {
        "error_count": evidence.error_count,
        "executor": {
            "name": evidence.executor.name,
            "version": evidence.executor.version,
        },
        "id": evidence.id,
        "input_count": evidence.input_count,
        "level": evidence.level,
        "output_count": evidence.output_count,
        "truncated": evidence.truncated,
    }


def _reference_mapping_edge_payloads(
    graph: GraphDocument,
    matches: tuple[ReferenceMappingMatch, ...],
    *,
    visible_object_ids: set[str],
) -> list[dict[str, object]]:
    nodes = graph.node_by_id()
    revision = physical_graph_revision(graph)
    payloads: list[dict[str, object]] = []
    for match in sorted(matches, key=lambda item: item.candidate.id):
        candidate = match.candidate
        if candidate.graph_revision != revision:
            raise ReferenceMappingFailure(
                "reference_mapping_graph_revision_mismatch",
                "The reference-mapping candidate does not match the projected graph revision.",
            )
        source_field = nodes.get(candidate.source_field_id)
        target_field = nodes.get(candidate.target_field_id)
        if (
            source_field is None
            or source_field.type != "field"
            or target_field is None
            or target_field.type != "field"
        ):
            raise ReferenceMappingFailure(
                "reference_mapping_field_not_found",
                "A reference-mapping endpoint is not a current graph field.",
            )
        source_object_id = str(source_field.metadata.get("object_id") or "")
        target_object_id = str(target_field.metadata.get("object_id") or "")
        source_object = nodes.get(source_object_id)
        target_object = nodes.get(target_object_id)
        if (
            source_object is None
            or source_object.type not in {"table", "view"}
            or target_object is None
            or target_object.type not in {"table", "view"}
        ):
            raise ReferenceMappingFailure(
                "reference_mapping_field_not_found",
                "A reference-mapping field has no current graph object.",
            )
        if (
            source_object_id not in visible_object_ids
            or target_object_id not in visible_object_ids
        ):
            continue
        review = (
            {
                "decision": candidate.review.decision,
                "source": candidate.review.source,
            }
            if candidate.review is not None
            else None
        )
        payloads.append(
            {
                "graph": graph.name,
                "id": _ui_id(graph.name, f"reference_mapping:{candidate.id}"),
                "metadata": {
                    "candidate_id": candidate.id,
                    "cardinality": candidate.cardinality,
                    "challenge": _reference_mapping_evidence_summary(
                        candidate.challenge_evidence
                    ),
                    "direction": "source_to_target",
                    "mapping_count": candidate.mapping_count,
                    "requires_runtime_validation": match.requires_runtime_validation,
                    "review": review,
                    "revision": candidate.revision,
                    "source_field": source_field.label,
                    "source_object": source_object.label,
                    "state": candidate.state,
                    "support": _reference_mapping_evidence_summary(
                        candidate.support_evidence
                    ),
                    "target_field": target_field.label,
                    "target_object": target_object.label,
                    "usage": match.usage,
                    "usable": candidate.state == "reviewed",
                },
                "source": _ui_id(graph.name, source_object_id),
                "target": _ui_id(graph.name, target_object_id),
                "type": "reference_mapping",
            }
        )
    return payloads


def _reference_mapping_evidence_summary(
    evidence: ReferenceMappingEvidence,
) -> dict[str, object]:
    metrics = evidence.metrics
    return {
        "collision_count": metrics.collision_count,
        "collision_rate": metrics.collision_rate,
        "confidence": metrics.confidence,
        "counterexample_count": metrics.counterexample_count,
        "evaluated_count": metrics.evaluated_count,
        "executor": {
            "id": evidence.execution.executor_id,
            "version": evidence.execution.executor_version,
        },
        "level": evidence.level,
        "matched_count": metrics.matched_count,
        "coverage": metrics.coverage,
    }


def _reviewed_usage(state: str) -> str:
    if state == "reviewed":
        return "confirmed"
    if state == "rejected":
        return "rejected"
    return "exploratory_only"


def _edge_payload(
    edge: GraphEdge,
    nodes: dict[str, GraphNode],
    graph_name: str,
    *,
    source_semantics: Iterable[dict[str, object]] = (),
) -> dict[str, object] | None:
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
        "id": _ui_id(graph_name, edge.id),
        "metadata": edge.metadata,
        "source_semantics": list(source_semantics),
        "source": _ui_id(graph_name, source.id),
        "target": _ui_id(graph_name, target.id),
        "type": edge.type,
    }


def _workspace_relationship_payloads(
    workspace: WorkspaceDocument,
    objects: list[dict[str, object]],
) -> list[dict[str, object]]:
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


def _review_queue(objects: list[dict[str, object]]) -> list[dict[str, object]]:
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


def _review_summary(
    graphs: tuple[GraphDocument, ...],
    allowed_objects: set[tuple[str, str]],
) -> dict[str, object]:
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


def _workspace_payload(workspace: WorkspaceDocument, graph_name: str) -> dict[str, object] | None:
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
) -> dict[str, object]:
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


def _ui_id(graph_name: str, item_id: str) -> str:
    return f"{graph_name}::{item_id}"


def _combined_revision(revisions: dict[str, str]) -> str:
    return hashlib.sha256(
        json.dumps(revisions, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def _normalize_reference(value: str) -> str:
    return "".join(
        character for character in value.strip() if character not in "[]`\""
    ).casefold()


def _display_reference(value: str) -> str:
    clean = "".join(character for character in value if character not in "[]`\"")
    parts = [part for part in clean.split(".") if part]
    return ".".join(parts[-2:]) if len(parts) > 1 else clean
