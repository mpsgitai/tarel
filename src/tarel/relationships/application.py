"""Relationship use cases: add, check, discover and review join relationships in a graph."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from tarel.connectors.application import configured_connector
from tarel.connectors.contracts import (
    ConnectorFailure,
    RelationshipPair,
    RelationshipPairProfile,
    RelationshipProbeConnector,
    RelationshipProbeRequest,
)
from tarel.focus.application import load_current_focus
from tarel.focus.contracts import FocusFailure
from tarel.focus.core import expand_graph_objects_one_hop, graph_object_ids
from tarel.graph.contracts import GraphDocument, GraphEdge
from tarel.graph.revision import graph_revision
from tarel.relationships.core import (
    add_manual_relationship,
    add_profile_candidates,
    candidate_pairs,
    decide_relationship,
    relationship_candidates,
    relationship_pair,
)
from tarel.runtime import TarelRuntime, resolve_runtime


@dataclass(frozen=True, slots=True)
class RelationshipChangeResult:
    graph: GraphDocument
    path: Path
    edge: GraphEdge


@dataclass(frozen=True, slots=True)
class RelationshipDiscoveryResult:
    graph: GraphDocument
    path: Path | None
    profiles: tuple[RelationshipPairProfile, ...]
    candidates: tuple[GraphEdge, ...]


def add_relationship_use_case(
    name: str,
    *,
    from_reference: str,
    to_reference: str,
    reason: str,
    validated: bool,
    runtime: TarelRuntime | None = None,
) -> RelationshipChangeResult:
    store = resolve_runtime(runtime).graph_store()
    graph = store.load(name)
    pair = relationship_pair(graph, from_reference, to_reference)
    updated, edge = add_manual_relationship(
        graph,
        pair=pair,
        reason=reason,
        validated=validated,
    )
    path = store.save(updated, expected_revision=graph_revision(graph))
    return RelationshipChangeResult(graph=updated, path=path, edge=edge)


def check_relationship_use_case(
    name: str,
    *,
    from_reference: str,
    to_reference: str,
    config_path: Path | None,
    row_limit: int,
    runtime: TarelRuntime | None = None,
) -> RelationshipPairProfile:
    graph = resolve_runtime(runtime).graph_store().load(name)
    pair = relationship_pair(graph, from_reference, to_reference)
    return _probe_relationship_pairs(
        graph,
        (pair,),
        config_path=config_path,
        row_limit=row_limit,
    )[0]


def discover_relationships_use_case(
    name: str,
    *,
    object_reference: str,
    field_name: str | None,
    config_path: Path | None,
    max_pairs: int,
    row_limit: int,
    min_source_coverage: float,
    min_overlap_count: int,
    min_target_uniqueness: float,
    persist: bool,
    focus_name: str | None = None,
    expand_one_hop: bool = False,
    runtime: TarelRuntime | None = None,
) -> RelationshipDiscoveryResult:
    if expand_one_hop and focus_name is None:
        raise FocusFailure(
            "invalid_focus_scope",
            "--expand-one-hop requires --focus.",
        )
    store = resolve_runtime(runtime).graph_store()
    graph = store.load(name)
    allowed_object_ids = None
    if focus_name is not None:
        focus, _lineages, focus_graphs = load_current_focus(focus_name, runtime=runtime)
        focus_graph = focus_graphs.get(name)
        if focus_graph is None:
            raise FocusFailure(
                "graph_outside_focus",
                f"Graph is outside focus {focus_name}: {name}",
            )
        allowed_object_ids = graph_object_ids(focus, name)
        if expand_one_hop:
            allowed_object_ids = expand_graph_objects_one_hop(graph, allowed_object_ids)
    pairs = candidate_pairs(
        graph,
        object_reference=object_reference,
        field_name=field_name,
        max_pairs=max_pairs,
        allowed_object_ids=allowed_object_ids,
    )
    if not pairs:
        return RelationshipDiscoveryResult(graph=graph, path=None, profiles=(), candidates=())
    profiles = _probe_relationship_pairs(
        graph,
        pairs,
        config_path=config_path,
        row_limit=row_limit,
    )
    updated, candidates = add_profile_candidates(
        graph,
        profiles,
        min_source_coverage=min_source_coverage,
        min_overlap_count=min_overlap_count,
        min_target_uniqueness=min_target_uniqueness,
    )
    path = (
        store.save(updated, expected_revision=graph_revision(graph))
        if persist and candidates else None
    )
    return RelationshipDiscoveryResult(
        graph=updated,
        path=path,
        profiles=profiles,
        candidates=candidates,
    )


def list_relationships_use_case(
    name: str,
    *,
    runtime: TarelRuntime | None = None,
) -> tuple[GraphEdge, ...]:
    return relationship_candidates(resolve_runtime(runtime).graph_store().load(name))


def decide_relationship_use_case(
    name: str,
    *,
    edge_id: str,
    state: str,
    reason: str,
    runtime: TarelRuntime | None = None,
) -> RelationshipChangeResult:
    store = resolve_runtime(runtime).graph_store()
    graph = store.load(name)
    updated, edge = decide_relationship(
        graph,
        edge_id=edge_id,
        state=state,
        reason=reason,
    )
    path = store.save(updated, expected_revision=graph_revision(graph))
    return RelationshipChangeResult(graph=updated, path=path, edge=edge)


def _probe_relationship_pairs(
    graph: GraphDocument,
    pairs: tuple[RelationshipPair, ...],
    *,
    config_path: Path | None,
    row_limit: int,
) -> tuple[RelationshipPairProfile, ...]:
    source = configured_connector(graph.connector, config_path=config_path, database=graph.catalog)
    connector = source.connector
    if "probe_relationships" not in connector.manifest.capabilities or not hasattr(
        connector, "probe_relationships"
    ):
        raise ConnectorFailure(
            "unsupported_capability",
            f"Connector {graph.connector} does not support relationship probes.",
        )
    profiler = cast(RelationshipProbeConnector, connector)
    result = profiler.probe_relationships(
        RelationshipProbeRequest(
            url=source.url,
            database=source.database,
            pairs=pairs,
            row_limit=row_limit,
            credential=source.credential,
        )
    )
    return result.profiles
