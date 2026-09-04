"""Bounded lazy single-graph family views; richer projections explicitly retain full validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tarel.discovery.application import list_query_linked_coverages_use_case
from tarel.entity_resolution.application import list_entity_resolution_candidates_use_case
from tarel.graph.contracts import GraphFailure
from tarel.lineage.contracts import LineageDocument
from tarel.object_families.application import (
    _attribute_values,
    _families,
    _graphs,
    _require_mode,
    family_summary,
    validate_family_selectively,
)
from tarel.object_families.contracts import ObjectFamily, ObjectFamilyFailure
from tarel.reference_mapping.application import list_reference_mapping_candidates_use_case
from tarel.runtime import TarelRuntime
from tarel.semantics.application import list_semantic_imports_use_case
from tarel.topology.store import FileLogicalTopologyStore
from tarel.ui.presentation import (
    _compact_family_workspace_members,
    _family_object_payload,
    browser_graph,
    family_view_scope_revision_from_revisions,
)
from tarel.workspaces.contracts import WorkspaceDocument


@dataclass(frozen=True, slots=True)
class LazyFamilyGraphView:
    payload: dict[str, object] | None
    fallback_reason: str | None = None


def try_lazy_family_graph_view_use_case(
    graph_name: str,
    *,
    family_mode: str,
    workspaces: tuple[WorkspaceDocument, ...] = (),
    lineage_documents: tuple[LineageDocument, ...] = (),
    editable: bool = False,
    has_focus: bool = False,
    runtime: TarelRuntime | None = None,
) -> LazyFamilyGraphView:
    _require_mode(family_mode)
    if has_focus:
        return LazyFamilyGraphView(None, "focus_requires_full_projection")
    reason = _rich_sidecar_reason(graph_name, runtime)
    if reason is not None:
        return LazyFamilyGraphView(None, reason)
    store = _graphs(runtime)
    header = store.header(graph_name)
    current_families, stale = _current_families(graph_name, header.physical_revision, runtime)
    families = tuple(
        family
        for family in current_families
        if family_mode == "include_candidates" or family.state == "reviewed"
    )
    if not families:
        return LazyFamilyGraphView(None, "no_eligible_families")
    stats = [header.read_stats]
    object_ids: list[str] = []
    offset = 0
    while True:
        page = store.list_objects(
            graph_name, offset=offset, limit=1000, expected_revision=header.revision
        )
        stats.append(page.header.read_stats)
        object_ids.extend(node.id for node in page.objects)
        if page.next_offset is None:
            break
        offset = page.next_offset
    metadata = store.read_slice(
        graph_name, tuple(object_ids), expected_revision=header.revision, include_fields=False
    )
    stats.append(metadata.header.read_stats)
    nodes = metadata.graph.node_by_id()
    for family in current_families:
        for member in family.member_ids:
            _attribute_values(family.attributes, nodes[member])
    all_objects = set(object_ids)
    hidden: set[str] = set()
    rendered: list[dict[str, object]] = []
    for family in families:
        current = validate_family_selectively(family, runtime=runtime)
        if current.revision != header.revision:
            raise GraphFailure(
                "graph_changed_during_read", "Graph changed during family projection."
            )
        members = set(family.member_ids)
        hidden.update(members)
        summary = family_summary(family)
        summary["hidden_details"] = {
            "physical_relationships": len(
                {
                    edge.id
                    for edge in metadata.graph.edges
                    if edge.source_id in all_objects
                    and edge.target_id in all_objects
                    and (edge.source_id in members or edge.target_id in members)
                }
            ),
            "derived_relations": 0,
            "reference_mappings": 0,
            "entity_candidates": 0,
        }
        summary["namespace_count"] = len(
            {str(nodes[item].metadata.get("namespace") or "") for item in members}
        )
        rendered.append(_family_object_payload(graph_name, header.catalog, family, summary))
    visible = store.read_slice(
        graph_name, tuple(sorted(all_objects - hidden)), expected_revision=header.revision
    )
    stats.append(visible.header.read_stats)
    payload = browser_graph(
        visible.graph, workspaces=workspaces, lineage_documents=lineage_documents, editable=editable
    )
    payload["objects"] = rendered + payload["objects"]
    # The UI identifies its authoritative source. The actual subset GraphDocument
    # retains its own identity; no subset hash is relabelled or persisted as a full graph.
    payload["revision"] = header.revision
    payload["revisions"] = {graph_name: header.revision}
    payload["graphs"][0]["revision"] = header.revision
    payload["object_families"] = {
        "mode": family_mode,
        "scope_revision": family_view_scope_revision_from_revisions({graph_name: header.revision}),
        "collapsed_member_count": len(hidden),
        "stale_graphs": [graph_name] if stale else [],
        "notice": "Families summarize compatible schemas, not union or join correctness. "
        "Members load on demand. Disable families to inspect member annotations, "
        "relationships, derivations, review queues, zones and lineage.",
    }
    _compact_family_workspace_members(payload, {(graph_name, item) for item in hidden})
    payload["storage"] = {
        "mode": "selective_family_projection",
        "full_document_read": any(item.full_document_read for item in stats),
        "source_revision": header.revision,
        "source_node_count": header.node_count,
        "source_edge_count": header.edge_count,
        "loaded_node_count": sum(item.loaded_node_count for item in stats),
        "loaded_edge_count": sum(item.loaded_edge_count for item in stats),
        "notice": "Object metadata and exact schema hashes are read; "
        "collapsed fields are not hydrated. "
        "Cold bootstrap reads the complete source once.",
    }
    return LazyFamilyGraphView(payload)


def full_family_projection_storage(reason: str) -> dict[str, object]:
    return {
        "mode": "full_projection",
        "full_document_read": True,
        "reason": reason,
        "notice": "This view retains complete graph loading "
        "to preserve existing scope and sidecar validation.",
    }


def _current_families(
    graph_name: str,
    revision: str,
    runtime: TarelRuntime | None,
) -> tuple[tuple[ObjectFamily, ...], bool]:
    store = _families(runtime)
    families: list[ObjectFamily] = []
    stale = False
    owned: set[str] = set()
    names: set[str] = set()
    for family_id in store.list(graph_name):
        family = store.load(graph_name, family_id)
        if family.state == "rejected":
            continue
        if family.graph_revision != revision:
            stale = True
            continue
        validate_family_selectively(family, runtime=runtime)
        if owned.intersection(family.member_ids) or family.name in names:
            raise ObjectFamilyFailure(
                "object_family_overlap", "Active family declarations overlap."
            )
        owned.update(family.member_ids)
        names.add(family.name)
        families.append(family)
    return tuple(sorted(families, key=lambda item: (item.name, item.id))), stale


def _rich_sidecar_reason(graph_name: str, runtime: TarelRuntime | None) -> str | None:
    from tarel.application import list_knowledge_documents_use_case

    topology = runtime.logical_topology_store() if runtime else FileLogicalTopologyStore()
    if topology.exists(graph_name):
        return "logical_topology_requires_full_projection"
    if list_entity_resolution_candidates_use_case(graph_name=graph_name, runtime=runtime):
        return "entity_resolution_requires_full_projection"
    if list_reference_mapping_candidates_use_case(graph_name=graph_name, runtime=runtime):
        return "reference_mapping_requires_full_projection"
    if list_semantic_imports_use_case(graph_name=graph_name, runtime=runtime):
        return "semantic_import_requires_full_projection"
    if list_query_linked_coverages_use_case(graph_name=graph_name, runtime=runtime):
        return "query_coverage_requires_full_projection"
    if list_knowledge_documents_use_case(runtime=runtime):
        return "knowledge_requires_full_projection"
    root = runtime.root if runtime else Path.cwd() / ".tarel"
    # These opt-in sidecars are projected separately by the full browser path.
    # Presence is enough to choose that validated path; do not inspect private payloads here.
    for name in ("object-bindings", "semantic-concepts", "logical-discovery"):
        if (root / name / graph_name).exists():
            return "logical_sidecar_requires_full_projection"
    return None
