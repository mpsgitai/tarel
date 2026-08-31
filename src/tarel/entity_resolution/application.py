"""Application use cases for auditable entity-resolution candidates."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from tarel.discovery.contracts import DiscoveryFailure
from tarel.discovery.store import FileDiscoveryStore
from tarel.entity_resolution.contracts import (
    ENTITY_RESOLUTION_MODES,
    EntityAliasMatch,
    EntityResolutionCandidate,
    EntityResolutionFailure,
    EntityResolutionMatch,
    review_candidate,
    validate_entity_resolution_candidate,
)
from tarel.entity_resolution.store import FileEntityResolutionStore
from tarel.graph.contracts import GraphDocument, GraphNode
from tarel.graph.revision import graph_revision
from tarel.graph.store import FileGraphStore
from tarel.relationships.core import RelationshipFailure, resolve_field
from tarel.runtime import TarelRuntime
from tarel.sources.store import FileSourceStore


@dataclass(frozen=True, slots=True)
class EntityResolutionChangeResult:
    candidate: EntityResolutionCandidate
    path: Path
    changed: bool


def import_entity_resolution_candidate_use_case(
    candidate: EntityResolutionCandidate,
    *,
    runtime: TarelRuntime | None = None,
) -> EntityResolutionChangeResult:
    validate_entity_resolution_candidate(candidate)
    if candidate.state != "candidate" or candidate.review is not None:
        raise EntityResolutionFailure(
            "invalid_entity_resolution_import",
            "New entity-resolution imports must be unreviewed candidates.",
        )
    graph = _graph_store(runtime).load(candidate.graph_name)
    _validate_candidate_binding(candidate, graph)
    _validate_alias_policy(candidate, runtime=runtime)
    store = _entity_store(runtime)
    _validate_self_supersede(candidate, store)
    if store.exists(candidate.id):
        current = store.load(candidate.id)
        if current == candidate:
            return EntityResolutionChangeResult(
                candidate=current,
                path=store.path(candidate.id),
                changed=False,
            )
        raise EntityResolutionFailure(
            "entity_resolution_exists",
            f"Entity-resolution candidate already exists: {candidate.id}",
        )
    return EntityResolutionChangeResult(
        candidate=candidate,
        path=store.save(candidate),
        changed=True,
    )


def load_entity_resolution_candidate_use_case(
    candidate_id: str,
    *,
    runtime: TarelRuntime | None = None,
) -> EntityResolutionCandidate:
    return _entity_store(runtime).load(candidate_id)


def list_entity_resolution_candidates_use_case(
    *,
    graph_name: str | None = None,
    runtime: TarelRuntime | None = None,
) -> tuple[EntityResolutionCandidate, ...]:
    store = _entity_store(runtime)
    candidates = tuple(store.load(candidate_id) for candidate_id in store.list())
    if graph_name is not None:
        candidates = tuple(item for item in candidates if item.graph_name == graph_name)
    return candidates


def find_entity_resolution_candidates_use_case(
    graph_name: str,
    *,
    source: str | None = None,
    target: str | None = None,
    mode: str = "confirmed_then_candidates",
    runtime: TarelRuntime | None = None,
) -> tuple[EntityResolutionMatch, ...]:
    graph = _graph_store(runtime).load(graph_name)
    return find_entity_resolution_candidates_for_graph_use_case(
        graph,
        source=source,
        target=target,
        mode=mode,
        runtime=runtime,
    )


def find_entity_resolution_candidates_for_graph_use_case(
    graph: GraphDocument,
    *,
    source: str | None = None,
    target: str | None = None,
    mode: str = "confirmed_then_candidates",
    runtime: TarelRuntime | None = None,
) -> tuple[EntityResolutionMatch, ...]:
    if mode not in ENTITY_RESOLUTION_MODES:
        raise EntityResolutionFailure(
            "invalid_entity_resolution_mode",
            f"Unsupported entity-resolution retrieval mode: {mode}",
        )
    source_id = _resolve_optional_field(graph, source)
    target_id = _resolve_optional_field(graph, target)
    stored_candidates = list_entity_resolution_candidates_use_case(
        graph_name=graph.name,
        runtime=runtime,
    )
    superseded_ids = {
        item.provenance.supersedes_candidate_id
        for item in stored_candidates
        if item.provenance.supersedes_candidate_id is not None
    }
    candidates = [
        item
        for item in stored_candidates
        if item.graph_revision == graph_revision(graph)
        and item.state != "rejected"
        and item.id not in superseded_ids
        and (source_id is None or item.source_field_id == source_id)
        and (target_id is None or item.target_field_id == target_id)
    ]
    if mode == "confirmed_only":
        candidates = [item for item in candidates if item.state == "reviewed"]
    elif mode == "confirmed_then_candidates":
        reviewed_pairs = {
            _field_pair(item)
            for item in candidates
            if item.state == "reviewed"
        }
        candidates = [
            item
            for item in candidates
            if item.state == "reviewed"
            or _field_pair(item) not in reviewed_pairs
        ]
    return tuple(
        _match(graph, item, runtime=runtime)
        for item in sorted(candidates, key=lambda candidate: candidate.id)
    )


def resolve_entity_aliases_use_case(
    graph_name: str,
    *,
    object_reference: str,
    record_key: str,
    mode: str = "confirmed_then_candidates",
    runtime: TarelRuntime | None = None,
) -> tuple[EntityAliasMatch, ...]:
    if mode not in ENTITY_RESOLUTION_MODES:
        raise EntityResolutionFailure(
            "invalid_entity_resolution_mode",
            f"Unsupported entity-resolution retrieval mode: {mode}",
        )
    if not record_key:
        raise EntityResolutionFailure(
            "invalid_entity_resolution", "Entity alias lookup requires a record key."
        )
    graph = _graph_store(runtime).load(graph_name)
    object_node = next(
        (
            node
            for node in graph.nodes
            if node.type in {"table", "view"}
            and (node.id == object_reference or node.label == object_reference)
        ),
        None,
    )
    if object_node is None:
        raise EntityResolutionFailure(
            "entity_resolution_object_not_found",
            f"Entity-resolution object not found: {object_reference}",
        )
    bound_candidates = [
        item
        for item in list_entity_resolution_candidates_use_case(
            graph_name=graph_name, runtime=runtime
        )
        if item.graph_revision == graph_revision(graph)
        and item.state != "rejected"
        and item.self_match is not None
        and item.self_match.object_id == object_node.id
        and item.identity_group is not None
    ]
    for candidate in bound_candidates:
        _validate_alias_policy(candidate, runtime=runtime)
    candidates = [
        item
        for item in bound_candidates
        if item.identity_group is not None
        and record_key in item.identity_group.member_keys
    ]
    if mode == "confirmed_only":
        candidates = [item for item in candidates if item.state == "reviewed"]
    elif mode == "confirmed_then_candidates":
        reviewed = [item for item in candidates if item.state == "reviewed"]
        if reviewed:
            candidates = reviewed
    matches = []
    for candidate in sorted(candidates, key=lambda item: item.id):
        assert candidate.self_match is not None
        assert candidate.identity_group is not None
        matches.append(
            EntityAliasMatch(
                candidate_id=candidate.id,
                group=candidate.identity_group,
                state=candidate.state,
                object_reference=object_node.label,
                record_key_field=_field_reference(
                    graph, candidate.self_match.record_key_field_id
                ),
            )
        )
    return tuple(matches)


def decide_entity_resolution_candidate_use_case(
    candidate_id: str,
    *,
    decision: str,
    reason: str,
    expected_revision: str | None = None,
    runtime: TarelRuntime | None = None,
) -> EntityResolutionChangeResult:
    store = _entity_store(runtime)
    candidate = store.load(candidate_id)
    if any(
        store.load(current_id).provenance.supersedes_candidate_id == candidate_id
        for current_id in store.list()
    ):
        raise EntityResolutionFailure(
            "entity_resolution_superseded",
            "The candidate is immutable audit history; review its active successor.",
        )
    if expected_revision is not None and candidate.revision != expected_revision:
        raise EntityResolutionFailure(
            "stale_entity_resolution_candidate",
            "The candidate changed after it was loaded. Reload it before reviewing.",
        )
    graph = _graph_store(runtime).load(candidate.graph_name)
    _validate_candidate_binding(candidate, graph)
    _validate_alias_policy(candidate, runtime=runtime)
    changed = review_candidate(candidate, decision=decision, reason=reason)
    return EntityResolutionChangeResult(
        candidate=changed,
        path=store.save(changed),
        changed=True,
    )


def _validate_candidate_binding(
    candidate: EntityResolutionCandidate,
    graph: GraphDocument,
) -> None:
    if candidate.graph_revision != graph_revision(graph):
        raise EntityResolutionFailure(
            "entity_resolution_graph_revision_mismatch",
            "The entity-resolution candidate does not match the current graph revision.",
        )
    source = _field_by_id(graph, candidate.source_field_id)
    target = _field_by_id(graph, candidate.target_field_id)
    if source.id == target.id and candidate.self_match is None:
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            "Equal entity-resolution endpoints require explicit self-entity semantics.",
        )
    if candidate.self_match is not None:
        self_match = candidate.self_match
        object_node = graph.node_by_id().get(self_match.object_id)
        if object_node is None or object_node.type not in {"table", "view"}:
            raise EntityResolutionFailure(
                "entity_resolution_object_not_found",
                "Self-entity matching requires one current graph object.",
            )
        bound_fields = (
            self_match.record_key_field_id,
            *self_match.comparison_field_ids,
            *self_match.contradiction_field_ids,
        )
        for field_id in bound_fields:
            field = _field_by_id(graph, field_id)
            if str(field.metadata.get("object_id") or "") != object_node.id:
                raise EntityResolutionFailure(
                    "invalid_entity_resolution",
                    "Self-entity record, comparison, and contradiction fields must belong "
                    "to the declared object.",
                )
    if candidate.program is not None:
        for source_field_id, target_field_id in zip(
            candidate.program.source_fields,
            candidate.program.target_fields,
            strict=True,
        ):
            _field_by_id(graph, source_field_id)
            _field_by_id(graph, target_field_id)
            if source_field_id == target_field_id and candidate.self_match is None:
                raise EntityResolutionFailure(
                    "invalid_entity_resolution",
                    "Entity-resolution program field pairs must use different fields.",
                )


def _match(
    graph: GraphDocument,
    candidate: EntityResolutionCandidate,
    *,
    runtime: TarelRuntime | None,
) -> EntityResolutionMatch:
    coverage = None
    discovery_store = _discovery_store(runtime)
    run_id = candidate.provenance.run_id
    if discovery_store.coverage_exists(run_id):
        try:
            stored = discovery_store.load_coverage(run_id)
        except DiscoveryFailure as exc:
            raise EntityResolutionFailure(exc.code, str(exc)) from exc
        if candidate.id in stored.candidate_refs:
            coverage = stored
    return EntityResolutionMatch(
        candidate=candidate,
        source_reference=_field_reference(graph, candidate.source_field_id),
        target_reference=_field_reference(graph, candidate.target_field_id),
        query_linked_coverage=coverage,
    )


def _field_pair(candidate: EntityResolutionCandidate) -> tuple[str, ...]:
    first, second = sorted((candidate.source_field_id, candidate.target_field_id))
    if candidate.identity_group is not None:
        return (
            first,
            second,
            json.dumps(
                candidate.identity_group.member_keys,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
    return first, second


def _validate_self_supersede(
    candidate: EntityResolutionCandidate,
    store: FileEntityResolutionStore,
) -> None:
    if candidate.self_match is None:
        return
    existing = tuple(store.load(candidate_id) for candidate_id in store.list())
    superseded_ids = {
        item.provenance.supersedes_candidate_id
        for item in existing
        if item.provenance.supersedes_candidate_id is not None
    }
    equivalent = tuple(
        item
        for item in existing
        if item.id != candidate.id
        and item.state == "candidate"
        and item.id not in superseded_ids
        and _self_semantic_key(item) == _self_semantic_key(candidate)
    )
    supersedes = candidate.provenance.supersedes_candidate_id
    if supersedes is None:
        if equivalent:
            ids = ", ".join(item.id for item in equivalent)
            raise EntityResolutionFailure(
                "entity_resolution_supersede_required",
                "Equivalent self-entity evidence already exists; explicitly supersede one "
                f"candidate: {ids}",
            )
        return
    target = next((item for item in equivalent if item.id == supersedes), None)
    if target is None:
        raise EntityResolutionFailure(
            "invalid_entity_resolution_supersede",
            "A self-entity candidate may supersede only one active, unreviewed, "
            "semantically equivalent candidate.",
        )


def _self_semantic_key(candidate: EntityResolutionCandidate) -> str | None:
    if candidate.self_match is None or candidate.program is None:
        return None
    execution = candidate.execution
    payload = {
        "graph_name": candidate.graph_name,
        "graph_revision": candidate.graph_revision,
        "program": candidate.program.to_dict(),
        "self_match": candidate.self_match.to_dict(),
        "identity_group": (
            list(candidate.identity_group.member_keys)
            if candidate.identity_group is not None
            else None
        ),
        "blocking_strategy": execution.blocking_strategy if execution else None,
        "blocking_version": execution.blocking_version if execution else None,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _validate_alias_policy(
    candidate: EntityResolutionCandidate,
    *,
    runtime: TarelRuntime | None,
) -> None:
    if candidate.identity_group is None:
        return
    if not candidate.provenance.source_names:
        raise EntityResolutionFailure(
            "entity_aliases_not_allowed",
            "Durable entity aliases require explicit source provenance.",
        )
    store = _source_store(runtime)
    for source_name in candidate.provenance.source_names:
        source = store.load(source_name)
        if (
            candidate.graph_name not in source.graphs
            or not source.allows_enrichment("entity_aliases")
        ):
            raise EntityResolutionFailure(
                "entity_aliases_not_allowed",
                f"Source {source_name} does not permit durable entity alias keys.",
            )


def _field_by_id(graph: GraphDocument, field_id: str) -> GraphNode:
    node = graph.node_by_id().get(field_id)
    if node is None or node.type != "field":
        raise EntityResolutionFailure(
            "entity_resolution_field_not_found",
            f"Entity-resolution endpoint is not a current graph field: {field_id}",
        )
    return node


def _field_reference(graph: GraphDocument, field_id: str) -> str:
    field = _field_by_id(graph, field_id)
    parent = graph.node_by_id().get(str(field.metadata.get("object_id") or ""))
    if parent is None or parent.type not in {"table", "view"}:
        raise EntityResolutionFailure(
            "entity_resolution_field_not_found",
            f"Entity-resolution field has no current graph object: {field_id}",
        )
    return f"{parent.label}.{field.label}"


def _resolve_optional_field(graph: GraphDocument, reference: str | None) -> str | None:
    if reference is None:
        return None
    try:
        return resolve_field(graph, reference).field_node.id
    except RelationshipFailure as exc:
        raise EntityResolutionFailure(
            "entity_resolution_field_not_found",
            str(exc),
        ) from exc


def _graph_store(runtime: TarelRuntime | None) -> FileGraphStore:
    return FileGraphStore() if runtime is None else runtime.graph_store()


def _entity_store(runtime: TarelRuntime | None) -> FileEntityResolutionStore:
    return FileEntityResolutionStore() if runtime is None else runtime.entity_resolution_store()


def _discovery_store(runtime: TarelRuntime | None) -> FileDiscoveryStore:
    return FileDiscoveryStore() if runtime is None else runtime.discovery_store()


def _source_store(runtime: TarelRuntime | None) -> FileSourceStore:
    return FileSourceStore() if runtime is None else runtime.source_store()
