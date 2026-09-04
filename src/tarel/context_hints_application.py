"""Read-only logical sidecar projection after physical context selection."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable

from tarel.context import ContextFailure, ContextResult, with_logical_context_hints
from tarel.context_hints import (
    LOGICAL_HINT_MODES,
    DerivationHintEvidence,
    DerivedRelationHint,
    LogicalContextHints,
    LogicalHint,
    LogicalHintField,
    MappingHintEndpoint,
    MappingHintEvidence,
    ObjectFamilyHint,
    ReferenceMappingHint,
)
from tarel.graph.contracts import GraphDocument
from tarel.graph.revision import physical_graph_revision
from tarel.object_families.application import validate_object_families_against_graph
from tarel.object_families.store import FileObjectFamilyStore
from tarel.reference_mapping.application import (
    find_reference_mapping_candidates_for_graph_use_case,
    list_reference_mapping_candidates_use_case,
)
from tarel.reference_mapping.contracts import ReferenceMappingFailure
from tarel.runtime import TarelRuntime
from tarel.topology.application import validate_logical_topology_against_graph
from tarel.topology.store import FileLogicalTopologyStore
from tarel.workspaces.projection import scoped_node_id


def add_logical_context_hints_use_case(
    packet: ContextResult,
    graphs: tuple[GraphDocument, ...],
    *,
    mode: str | None,
    projection: GraphDocument | None = None,
    runtime: TarelRuntime | None = None,
) -> ContextResult:
    """Never select new physical objects or turn a logical hint into a join."""
    if mode is None:
        return packet
    if mode not in LOGICAL_HINT_MODES:
        raise ContextFailure(
            "invalid_logical_hint_mode", f"Unsupported logical-hint policy: {mode}"
        )
    selected = {item.id for item in packet.objects}
    items: list[LogicalHint] = []
    omissions: Counter[str] = Counter()
    for graph in sorted(graphs, key=lambda item: item.name):

        def projected_id(node_id: str, graph_name: str = graph.name) -> str:
            return scoped_node_id(graph_name, node_id) if projection is not None else node_id

        selected_original = {
            node.id
            for node in graph.nodes
            if node.type in {"table", "view"} and projected_id(node.id) in selected
        }
        if not selected_original:
            continue
        allowed = {
            node.id
            for node in (projection or graph).nodes
            if node.type in {"table", "view"}
            and (
                packet.scope.namespace is None
                or str(node.metadata.get("namespace") or "").casefold()
                == packet.scope.namespace.casefold()
            )
        }
        items.extend(
            _derived_hints(graph, selected_original, projected_id, mode, omissions, runtime)
        )
        items.extend(
            _mapping_hints(
                graph, selected_original, allowed, projected_id, mode, omissions, runtime
            )
        )
        items.extend(
            _family_hints(
                graph,
                selected_original,
                allowed,
                projected_id,
                mode,
                omissions,
                runtime,
            )
        )
    # Preserve confirmed hints first under budget; do not invent relevance scores.
    items.sort(key=lambda item: item.state != "reviewed")
    return with_logical_context_hints(
        packet,
        LogicalContextHints(
            mode=mode,
            items=tuple(items),
            omissions=tuple(
                sorted((reason, count) for reason, count in omissions.items() if count)
            ),
        ),
    )


def _derived_hints(
    graph: GraphDocument,
    selected: set[str],
    projected_id: Callable[[str], str],
    mode: str,
    omissions: Counter[str],
    runtime: TarelRuntime | None,
) -> list[DerivedRelationHint]:
    store = runtime.logical_topology_store() if runtime else FileLogicalTopologyStore()
    if not store.exists(graph.name):
        return []
    document = store.load(graph.name)
    relations = [item for item in document.derived_relations if item.source.id in selected]
    if not relations:
        return []
    if document.graph_revision != physical_graph_revision(graph):
        omissions["stale"] += len(relations)
        return []
    validate_logical_topology_against_graph(document, graph)
    document_revision = document.revision
    result: list[DerivedRelationHint] = []
    for relation in sorted(relations, key=lambda item: item.id):
        if relation.state == "rejected":
            omissions["rejected"] += 1
            continue
        if mode == "confirmed_only" and relation.state != "reviewed":
            omissions["review_policy"] += 1
            continue
        # Latest evidence, not the most flattering probe in the artifact.
        evidence = relation.evidence[-1]
        fields = {field.id: field.name for field in relation.output_schema}
        result.append(
            DerivedRelationHint(
                graph=graph.name,
                relation_id=relation.id,
                document_revision=document_revision,
                source_object_id=projected_id(relation.source.id),
                name=relation.name,
                state=relation.state,
                operations=tuple(step.kind for step in relation.steps),
                output_fields=tuple(
                    LogicalHintField(field.name, field.data_type, field.nullable)
                    for field in relation.output_schema
                ),
                grain=tuple(fields[field_id] for field_id in relation.grain.field_ids),
                evidence=DerivationHintEvidence(
                    evidence.level,
                    evidence.input_count,
                    evidence.output_count,
                    evidence.error_count,
                    evidence.truncated,
                ),
            )
        )
    return result


def _family_hints(
    graph: GraphDocument,
    selected: set[str],
    allowed: set[str],
    projected_id: Callable[[str], str],
    mode: str,
    omissions: Counter[str],
    runtime: TarelRuntime | None,
) -> list[ObjectFamilyHint]:
    store = runtime.object_family_store() if runtime else FileObjectFamilyStore()
    result: list[ObjectFamilyHint] = []
    revision = physical_graph_revision(graph)
    relevant = []
    for family_id in store.list(graph.name):
        family = store.load(graph.name, family_id)
        selected_members = selected.intersection(family.member_ids)
        if not selected_members:
            continue
        if family.graph_revision != revision:
            omissions["stale"] += 1
            continue
        if family.state == "rejected":
            omissions["rejected"] += 1
            continue
        relevant.append(family)
    if relevant:
        validate_object_families_against_graph(tuple(relevant), graph)
    for family in relevant:
        selected_members = selected.intersection(family.member_ids)
        if mode == "confirmed_only" and family.state != "reviewed":
            omissions["review_policy"] += 1
            continue
        result.append(
            ObjectFamilyHint(
                graph=graph.name,
                family_id=family.id,
                revision=family.revision,
                name=family.name,
                state=family.state,
                member_count=sum(
                    projected_id(member_id) in allowed for member_id in family.member_ids
                ),
                source_object_ids=tuple(
                    sorted(projected_id(member_id) for member_id in selected_members)
                ),
                schema=tuple(
                    LogicalHintField(field.name, field.data_type, field.nullable)
                    for field in family.schema
                ),
                grain=family.grain,
                attributes=tuple(
                    (attribute.name, attribute.source) for attribute in family.attributes
                ),
            )
        )
    return result


def _mapping_hints(
    graph: GraphDocument,
    selected: set[str],
    allowed: set[str],
    projected_id: Callable[[str], str],
    mode: str,
    omissions: Counter[str],
    runtime: TarelRuntime | None,
) -> list[ReferenceMappingHint]:
    nodes = {node.id: node for node in graph.nodes}
    revision = physical_graph_revision(graph)
    relevant: set[str] = set()
    for candidate in list_reference_mapping_candidates_use_case(
        graph_name=graph.name, runtime=runtime
    ):
        parents = tuple(
            nodes[field_id].metadata.get("object_id") if field_id in nodes else None
            for field_id in (candidate.source_field_id, candidate.target_field_id)
        )
        if not any(parent in selected for parent in parents):
            continue
        if candidate.graph_revision != revision:
            omissions["stale"] += 1
        elif candidate.state == "rejected":
            omissions["rejected"] += 1
        elif any(
            not isinstance(parent, str)
            or parent not in nodes
            or nodes[parent].type not in {"table", "view"}
            for parent in parents
        ):
            raise ReferenceMappingFailure(
                "reference_mapping_field_not_found",
                "Logical mapping hints require fields with valid physical parent objects.",
            )
        elif any(projected_id(parent) not in allowed for parent in parents):
            omissions["out_of_scope"] += 1
        else:
            relevant.add(candidate.id)
    if not relevant:
        return []
    # The established retrieval path owns review precedence and conflict checks.
    matches = find_reference_mapping_candidates_for_graph_use_case(
        graph, mode=mode, runtime=runtime
    )
    result: list[ReferenceMappingHint] = []
    for match in matches:
        candidate = match.candidate
        if candidate.id not in relevant:
            continue
        endpoints = []
        for field_id, reference in (
            (candidate.source_field_id, match.source_reference),
            (candidate.target_field_id, match.target_reference),
        ):
            parent = nodes[field_id].metadata["object_id"]
            endpoints.append(
                MappingHintEndpoint(
                    object_id=projected_id(parent),
                    field_id=projected_id(field_id),
                    reference=reference,
                )
            )
        result.append(
            ReferenceMappingHint(
                graph=graph.name,
                candidate_id=candidate.id,
                candidate_revision=candidate.revision,
                state=candidate.state,
                source=endpoints[0],
                target=endpoints[1],
                cardinality=candidate.cardinality,
                mapping_count=candidate.mapping_count,
                support=MappingHintEvidence(
                    candidate.support_evidence.level, candidate.support_evidence.metrics
                ),
                challenge=MappingHintEvidence(
                    candidate.challenge_evidence.level, candidate.challenge_evidence.metrics
                ),
            )
        )
    omissions["review_policy"] += len(relevant) - len(result)
    return result
