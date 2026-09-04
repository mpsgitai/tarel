"""Revision-pinned logical field references; resolution never executes source code."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tarel.graph.contracts import GraphDocument, GraphFailure, GraphNode
from tarel.graph.revision import physical_graph_revision
from tarel.graph.store import FileGraphStore
from tarel.runtime import TarelRuntime
from tarel.topology.endpoint_contracts import (
    LOGICAL_ENDPOINT_KINDS as LOGICAL_ENDPOINT_KINDS,
)
from tarel.topology.endpoint_contracts import (
    LOGICAL_ENDPOINT_MODES as LOGICAL_ENDPOINT_MODES,
)
from tarel.topology.endpoint_contracts import LogicalEndpoint as LogicalEndpoint
from tarel.topology.endpoint_contracts import LogicalEndpointFailure as LogicalEndpointFailure
from tarel.topology.endpoint_contracts import ResolvedLogicalEndpoint as ResolvedLogicalEndpoint

if TYPE_CHECKING:
    from tarel.object_families.contracts import ObjectFamily


def resolve_logical_endpoint_use_case(
    graph_name: str,
    endpoint: LogicalEndpoint,
    *,
    mode: str = "confirmed_only",
    runtime: TarelRuntime | None = None,
) -> ResolvedLogicalEndpoint:
    _validate_request(endpoint, mode)
    store = runtime.graph_store() if runtime else FileGraphStore()
    if endpoint.kind == "graph_field":
        header = store.header(graph_name)
        _require_revision(endpoint, header.physical_revision)
        try:
            graph = store.read_slice(
                graph_name, (endpoint.object_id,), expected_revision=header.revision
            ).graph
        except GraphFailure as exc:
            if exc.code != "graph_object_not_found":
                raise
            raise LogicalEndpointFailure(
                "logical_endpoint_not_found",
                "Endpoint must identify a field of its physical object.",
            ) from exc
        field = _field(graph, endpoint.field_id, endpoint.object_id)
        return _resolved_field(
            endpoint, field, "confirmed", (endpoint.object_id,),
            object_label=graph.node_by_id()[endpoint.object_id].label,
        )
    if endpoint.kind in {"family_field", "family_attribute"}:
        return _resolve_family_selectively(graph_name, endpoint, mode=mode, runtime=runtime)
    graph = store.load(graph_name)
    return resolve_logical_endpoint_for_graph_use_case(graph, endpoint, mode=mode, runtime=runtime)


def resolve_logical_endpoint_for_graph_use_case(
    graph: GraphDocument,
    endpoint: LogicalEndpoint,
    *,
    mode: str = "confirmed_only",
    runtime: TarelRuntime | None = None,
) -> ResolvedLogicalEndpoint:
    """Reuse an already loaded, caller-scoped graph while resolving several endpoints."""
    _validate_request(endpoint, mode)
    graph_name = graph.name
    if endpoint.kind == "graph_field":
        _require_revision(endpoint, physical_graph_revision(graph))
        field = _field(graph, endpoint.field_id, endpoint.object_id)
        return _resolved_field(
            endpoint, field, "confirmed", (endpoint.object_id,),
            object_label=graph.node_by_id()[endpoint.object_id].label,
        )
    if endpoint.kind == "derived_field":
        from tarel.topology.application import validate_logical_topology_against_graph
        from tarel.topology.store import FileLogicalTopologyStore

        topologies = runtime.logical_topology_store() if runtime else FileLogicalTopologyStore()
        document = topologies.load(graph_name)
        validate_logical_topology_against_graph(document, graph)
        _require_revision(endpoint, document.revision)
        relation = next(
            (item for item in document.derived_relations if item.id == endpoint.object_id), None
        )
        if relation is None:
            raise LogicalEndpointFailure(
                "logical_endpoint_not_found",
                "Derived relation not found.",
            )
        usage = _usage(relation.state, mode)
        field = next(
            (item for item in relation.output_schema if item.id == endpoint.field_id), None
        )
        if field is None:
            raise LogicalEndpointFailure("logical_endpoint_not_found", "Derived output not found.")
        return ResolvedLogicalEndpoint(
            endpoint,
            f"{relation.name}.{field.name}",
            field.data_type,
            field.nullable,
            usage,
            (relation.source.id,),
        )
    if endpoint.kind in {"family_field", "family_attribute"}:
        from tarel.object_families.application import (
            load_object_family_use_case,
            validate_object_family_against_graph,
        )

        family = load_object_family_use_case(graph_name, endpoint.object_id, runtime=runtime)
        _require_revision(endpoint, family.revision)
        validate_object_family_against_graph(family, graph)
        return _resolved_family(endpoint, family, mode)
    from tarel.reference_mapping.application import (
        find_reference_mapping_candidates_for_graph_use_case,
        load_reference_mapping_candidate_use_case,
    )

    candidate = load_reference_mapping_candidate_use_case(endpoint.object_id, runtime=runtime)
    if candidate.graph_name != graph_name or candidate.target_field_id != endpoint.field_id:
        raise LogicalEndpointFailure(
            "logical_endpoint_not_found",
            "Mapping endpoint does not match graph and target field.",
        )
    _require_revision(endpoint, candidate.revision)
    if candidate.graph_revision != physical_graph_revision(graph):
        raise LogicalEndpointFailure("stale_logical_endpoint", "Mapping physical source changed.")
    usage = _usage(candidate.state, mode)
    source, target = _field(graph, candidate.source_field_id), _field(graph, endpoint.field_id)
    nodes = graph.node_by_id()
    matches = find_reference_mapping_candidates_for_graph_use_case(
        graph,
        source=f"{nodes[source.metadata['object_id']].label}.{source.label}",
        target=f"{nodes[target.metadata['object_id']].label}.{target.label}",
        mode=mode,
        runtime=runtime,
    )
    if not any(match.candidate.id == candidate.id for match in matches):
        raise LogicalEndpointFailure(
            "logical_endpoint_policy_excluded",
            "Mapping is superseded by a reviewed candidate.",
        )
    return _resolved_field(
        endpoint,
        target,
        usage,
        tuple(
            sorted(
                {
                    str(source.metadata["object_id"]),
                    str(target.metadata["object_id"]),
                }
            )
        ),
        object_label=nodes[str(target.metadata["object_id"])].label,
    )


def _resolve_family_selectively(
    graph_name: str,
    endpoint: LogicalEndpoint,
    *,
    mode: str,
    runtime: TarelRuntime | None,
) -> ResolvedLogicalEndpoint:
    from tarel.object_families.application import (
        iter_family_metadata,
        load_object_family_use_case,
        validate_family_selectively,
    )
    from tarel.object_families.contracts import ObjectFamilyFailure

    store = runtime.graph_store() if runtime else FileGraphStore()
    header = store.header(graph_name)
    family = load_object_family_use_case(graph_name, endpoint.object_id, runtime=runtime)
    _require_revision(endpoint, family.revision)
    try:
        header = validate_family_selectively(family, runtime=runtime)
    except GraphFailure as exc:
        if exc.code != "graph_object_not_found":
            raise
        raise ObjectFamilyFailure(
            "object_family_member_not_found", "A member is not a physical table or view."
        ) from exc
    except ObjectFamilyFailure as exc:
        if exc.code == "object_family_schema_mismatch":
            # Preserve the eager validator's distinction between missing observed
            # schema and a known schema that disagrees with the declaration.
            schemas = store.object_schema_hashes(
                graph_name, family.member_ids, expected_revision=header.revision
            )
            if any(value is None for _object_id, value in schemas.hashes):
                raise ObjectFamilyFailure(
                    "object_family_schema_unavailable",
                    "Family members require typed nonempty physical schemas.",
                ) from exc
        raise
    # Validate every member's literal affixes, even if the requested field or
    # eventual routing result would use only one member. Fields stay unloaded.
    for _node in iter_family_metadata(family, header=header, runtime=runtime):
        pass
    return _resolved_family(endpoint, family, mode)


def _resolved_family(
    endpoint: LogicalEndpoint, family: ObjectFamily, mode: str
) -> ResolvedLogicalEndpoint:
    usage = _usage(family.state, mode)
    fields = family.schema if endpoint.kind == "family_field" else family.attributes
    field = next((item for item in fields if item.name == endpoint.field_id), None)
    if field is None:
        raise LogicalEndpointFailure("logical_endpoint_not_found", "Family endpoint not found.")
    return ResolvedLogicalEndpoint(
        endpoint,
        f"{family.name}.{field.name}",
        field.data_type if endpoint.kind == "family_field" else "string",
        field.nullable if endpoint.kind == "family_field" else False,
        usage,
        family.member_ids,
    )


def _validate_request(endpoint: LogicalEndpoint, mode: str) -> None:
    if not isinstance(mode, str) or mode not in LOGICAL_ENDPOINT_MODES:
        raise LogicalEndpointFailure("invalid_logical_endpoint_mode", "Unknown endpoint policy.")
    if not isinstance(endpoint, LogicalEndpoint):
        raise LogicalEndpointFailure("invalid_logical_endpoint", "Expected a LogicalEndpoint.")


def _field(graph: GraphDocument, field_id: str, object_id: str | None = None) -> GraphNode:
    nodes = graph.node_by_id()
    field = nodes.get(field_id)
    parent = nodes.get(str(field.metadata.get("object_id") or "")) if field else None
    if (
        field is None
        or field.type != "field"
        or parent is None
        or parent.type not in {"table", "view"}
        or (object_id is not None and parent.id != object_id)
    ):
        raise LogicalEndpointFailure(
            "logical_endpoint_not_found",
            "Endpoint must identify a field of its physical object.",
        )
    return field


def _resolved_field(
    endpoint: LogicalEndpoint,
    field: GraphNode,
    usage: str,
    physical_ids: tuple[str, ...],
    *,
    object_label: str,
) -> ResolvedLogicalEndpoint:
    data_type, nullable = field.metadata.get("data_type"), field.metadata.get("nullable")
    if not isinstance(data_type, str) or not isinstance(nullable, bool):
        raise LogicalEndpointFailure(
            "invalid_logical_endpoint_schema",
            "Endpoint requires an observed type and nullability.",
        )
    return ResolvedLogicalEndpoint(
        endpoint, f"{object_label}.{field.label}", data_type, nullable, usage, physical_ids
    )


def _require_revision(endpoint: LogicalEndpoint, revision: str) -> None:
    if endpoint.revision != revision:
        raise LogicalEndpointFailure(
            "stale_logical_endpoint",
            "Endpoint artifact changed; resolve and review it again.",
        )


def _usage(state: str, mode: str) -> str:
    if state == "rejected" or (mode == "confirmed_only" and state != "reviewed"):
        raise LogicalEndpointFailure(
            "logical_endpoint_policy_excluded",
            "Endpoint is excluded by its review policy.",
        )
    return "confirmed" if state == "reviewed" else "exploratory_only"
