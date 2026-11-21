"""Checks that bind a discovery run to the current graph, sources and run policies."""

from __future__ import annotations

from typing import Any

from tarel.discovery.contracts import DiscoveryFailure
from tarel.discovery.identity import IdentityFailure, IdentityInventoryManifest
from tarel.discovery.logical_program import LogicalJoinProgram
from tarel.discovery.programs import ReferenceMappingProgram, discovery_program_from_dict
from tarel.discovery.runs import DiscoveryRun
from tarel.graph.contracts import GraphDocument
from tarel.graph.revision import graph_revision
from tarel.relationships.core import RelationshipFailure, resolve_field
from tarel.runtime import TarelRuntime, resolve_runtime
from tarel.topology.endpoints import resolve_logical_endpoint_for_graph_use_case


def validate_program_bindings(
    graph: GraphDocument, program: dict[str, Any], *, runtime: TarelRuntime | None = None,
) -> None:
    typed = discovery_program_from_dict(program)
    if isinstance(typed, LogicalJoinProgram):
        validate_logical_program(graph, typed, runtime=runtime)
        return
    if isinstance(typed, ReferenceMappingProgram):
        field_references: tuple[str, ...] = (typed.source_field, typed.target_field)
    else:
        field_references = (*typed.source_fields, *typed.target_fields)
    resolved_fields = []
    for reference in field_references:
        try:
            resolved_fields.append(resolve_field(graph, reference))
        except RelationshipFailure as exc:
            raise DiscoveryFailure("discovery_field_not_found", str(exc)) from exc
    if isinstance(typed, ReferenceMappingProgram):
        if resolved_fields[0].field_node.id == resolved_fields[1].field_node.id:
            raise DiscoveryFailure(
                "invalid_discovery",
                "Reference-mapping endpoints must resolve to different physical fields.",
            )
        return
    if typed.self_match is None:
        return
    try:
        record_key = resolve_field(graph, typed.self_match.record_key_field)
        endpoints = tuple(
            resolve_field(graph, reference)
            for reference in (*typed.source_fields, *typed.target_fields)
        )
    except RelationshipFailure as exc:
        raise DiscoveryFailure("discovery_field_not_found", str(exc)) from exc
    object_ids = {item.object_node.id for item in endpoints}
    object_ids.add(record_key.object_node.id)
    if len(object_ids) != 1:
        raise DiscoveryFailure(
            "invalid_discovery",
            "Self-entity record key and comparison fields must belong to one graph object.",
        )


def validate_current_graph(
    run: DiscoveryRun, *, runtime: TarelRuntime | None
) -> GraphDocument:
    graph = resolve_runtime(runtime).graph_store().load(run.graph_name)
    if graph_revision(graph) != run.graph_revision:
        raise DiscoveryFailure(
            "discovery_graph_revision_mismatch",
            f"Graph {run.graph_name} changed after discovery run {run.id} started "
            "(refresh or annotation). Start a new run with `tarel discovery start`; "
            "promoted candidates of this run stay valid.",
        )
    for candidate in run.candidates:
        if isinstance(candidate.program, LogicalJoinProgram):
            validate_logical_program(graph, candidate.program, runtime=runtime)
    return graph


def validate_logical_program(
    graph: GraphDocument, program: LogicalJoinProgram, *, runtime: TarelRuntime | None,
) -> None:
    for endpoint in (*program.source_endpoints, *program.target_endpoints):
        resolve_logical_endpoint_for_graph_use_case(
            graph, endpoint, mode="include_candidates", runtime=runtime,
        )


def validate_sources(
    graph_name: str,
    source_names: tuple[str, ...],
    *,
    runtime: TarelRuntime | None,
) -> None:
    if len(source_names) != len(set(source_names)):
        raise DiscoveryFailure("invalid_discovery", "Source names must be unique.")
    store = resolve_runtime(runtime).source_store()
    for name in source_names:
        source = store.load(name)
        if graph_name not in source.graphs:
            raise DiscoveryFailure(
                "discovery_source_graph_mismatch",
                f"Source {name} is not bound to graph {graph_name}.",
            )


def validate_observation_policy(
    run: DiscoveryRun, *, runtime: TarelRuntime | None
) -> None:
    store = resolve_runtime(runtime).source_store()
    for name in run.source_names:
        source = store.load(name)
        if not source.allows_enrichment("aggregates"):
            raise DiscoveryFailure(
                "discovery_aggregates_not_allowed",
                f"Source {name} does not permit aggregate discovery observations.",
            )


def validate_identity_inventory_policy(
    run: DiscoveryRun, *, runtime: TarelRuntime | None
) -> None:
    source = resolve_runtime(runtime).source_store().load(run.source_names[0])
    if not source.allows_enrichment("entity_aliases"):
        raise DiscoveryFailure(
            "entity_aliases_not_allowed",
            f"Source {source.name} does not permit protected identity inspection.",
        )


def validate_entity_alias_policy(
    run: DiscoveryRun, *, runtime: TarelRuntime | None
) -> None:
    source = resolve_runtime(runtime).source_store().load(run.source_names[0])
    if not source.allows_enrichment("entity_aliases"):
        raise DiscoveryFailure(
            "entity_aliases_not_allowed",
            f"Source {source.name} does not permit durable entity alias keys.",
        )


def validate_identity_inventory_bindings(
    graph: GraphDocument,
    run: DiscoveryRun,
    payload: dict[str, Any],
) -> None:
    try:
        manifest = IdentityInventoryManifest.from_dict(payload)
    except IdentityFailure as exc:
        raise DiscoveryFailure(exc.code, str(exc)) from exc
    if manifest.source_name != run.source_names[0]:
        raise DiscoveryFailure(
            "discovery_source_graph_mismatch",
            "Identity inventory source must match its discovery run.",
        )
    if manifest.graph_name != run.graph_name or manifest.graph_revision != run.graph_revision:
        raise DiscoveryFailure(
            "discovery_graph_revision_mismatch",
            "Identity inventory must bind the discovery run graph and revision.",
        )
    try:
        fields = tuple(resolve_field(graph, item) for item in manifest.projected_fields)
    except RelationshipFailure as exc:
        raise DiscoveryFailure("discovery_field_not_found", str(exc)) from exc
    object_ids = {item.object_node.id for item in fields}
    if len(object_ids) != 1 or fields[0].object_node.label != manifest.object_reference:
        raise DiscoveryFailure(
            "invalid_identity_inventory",
            "Identity inventory key and label must belong to its object.",
        )
