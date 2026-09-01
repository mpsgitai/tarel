"""Application use cases for directed, value-free reference mappings."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from tarel.discovery.contracts import (
    DiscoveryCandidate,
    DiscoveryFailure,
    DiscoveryObservation,
    DiscoveryRun,
    ReferenceMappingProgram,
)
from tarel.graph.contracts import GraphDocument, GraphNode
from tarel.graph.revision import graph_revision, physical_graph_revision
from tarel.graph.store import FileGraphStore
from tarel.reference_mapping.contracts import (
    REFERENCE_MAPPING_MODES,
    ReferenceMappingCandidate,
    ReferenceMappingEvidence,
    ReferenceMappingFailure,
    ReferenceMappingMatch,
    ReferenceMappingProvenance,
    review_reference_mapping_candidate,
    validate_reference_mapping_candidate,
)
from tarel.reference_mapping.store import FileReferenceMappingStore
from tarel.relationships.core import RelationshipFailure, resolve_field
from tarel.runtime import TarelRuntime


@dataclass(frozen=True, slots=True)
class ReferenceMappingChangeResult:
    candidate: ReferenceMappingCandidate
    path: Path
    changed: bool


def reference_mapping_candidate_from_discovery(
    run: DiscoveryRun,
    candidate: DiscoveryCandidate,
    graph: GraphDocument,
    *,
    reason: str,
) -> ReferenceMappingCandidate:
    if run.kind != "reference_mapping" or candidate.kind != "reference_mapping":
        raise DiscoveryFailure(
            "invalid_discovery_promotion",
            "Only reference-mapping candidates can enter reference-mapping review.",
        )
    if run.status != "completed" or candidate.state != "selected":
        raise DiscoveryFailure(
            "invalid_discovery_promotion",
            "Reference-mapping promotion requires a completed run and selected candidate.",
        )
    if graph.name != run.graph_name or graph_revision(graph) != run.graph_revision:
        raise DiscoveryFailure(
            "discovery_graph_revision_mismatch",
            "Reference-mapping promotion requires the run's current graph revision.",
        )
    if not isinstance(candidate.program, ReferenceMappingProgram):
        raise DiscoveryFailure(
            "invalid_discovery_promotion",
            "Reference-mapping promotion requires its dedicated program contract.",
        )
    manifest = candidate.mapping_manifest
    if manifest is None:
        raise DiscoveryFailure(
            "incomplete_reference_mapping_manifest",
            "Reference-mapping promotion requires a registered value-free manifest.",
        )
    support = _latest_success(candidate, "support")
    challenge = _latest_success(candidate, "challenge")
    if support is None or challenge is None:
        raise DiscoveryFailure(
            "incomplete_reference_mapping_evidence",
            "Reference-mapping promotion requires successful support and challenge probes.",
        )
    if support.query_hash == challenge.query_hash:
        raise DiscoveryFailure(
            "incomplete_reference_mapping_evidence",
            "Support and challenge must use independent queries.",
        )
    support_evidence = _evidence_from_observation(support)
    challenge_evidence = _evidence_from_observation(challenge)
    try:
        source = resolve_field(graph, candidate.program.source_field).field_node
        target = resolve_field(graph, candidate.program.target_field).field_node
    except RelationshipFailure as exc:
        raise DiscoveryFailure("discovery_promotion_failed", str(exc)) from exc
    producer = next(
        (
            step.actor
            for step in run.steps
            if step.action == "propose_candidate" and step.candidate_id == candidate.id
        ),
        "coding_agent",
    )
    promoted = ReferenceMappingCandidate(
        id=_promoted_id(run.id, candidate.id),
        graph_name=run.graph_name,
        graph_revision=physical_graph_revision(graph),
        source_field_id=source.id,
        target_field_id=target.id,
        cardinality=candidate.program.cardinality,
        mapping_manifest_hash=manifest.mapping_manifest_hash,
        mapping_count=manifest.mapping_count,
        support_evidence=support_evidence,
        challenge_evidence=challenge_evidence,
        provenance=ReferenceMappingProvenance.from_dict(
            {
                "discovery_candidate_id": candidate.id,
                "producer": producer,
                "promotion_reason": reason,
                "run_id": run.id,
                "run_revision": run.revision,
                "source_names": list(run.source_names),
            }
        ),
    )
    try:
        validate_reference_mapping_candidate(promoted)
    except ReferenceMappingFailure as exc:
        raise DiscoveryFailure(exc.code, str(exc)) from exc
    return promoted


def import_reference_mapping_candidate_use_case(
    candidate: ReferenceMappingCandidate,
    *,
    runtime: TarelRuntime | None = None,
) -> ReferenceMappingChangeResult:
    validate_reference_mapping_candidate(candidate)
    if candidate.state != "candidate" or candidate.review is not None:
        raise ReferenceMappingFailure(
            "invalid_reference_mapping_import",
            "New reference-mapping imports must be unreviewed candidates.",
        )
    graph = _graph_store(runtime).load(candidate.graph_name)
    _validate_candidate_binding(candidate, graph)
    store = _mapping_store(runtime)
    if store.exists(candidate.id):
        current = store.load(candidate.id)
        if current == candidate:
            return ReferenceMappingChangeResult(
                candidate=current,
                path=store.path(candidate.id),
                changed=False,
            )
        raise ReferenceMappingFailure(
            "reference_mapping_exists",
            f"Reference-mapping candidate already exists: {candidate.id}",
        )
    return ReferenceMappingChangeResult(
        candidate=candidate,
        path=store.save(candidate),
        changed=True,
    )


def load_reference_mapping_candidate_use_case(
    candidate_id: str,
    *,
    runtime: TarelRuntime | None = None,
) -> ReferenceMappingCandidate:
    return _mapping_store(runtime).load(candidate_id)


def list_reference_mapping_candidates_use_case(
    *,
    graph_name: str | None = None,
    runtime: TarelRuntime | None = None,
) -> tuple[ReferenceMappingCandidate, ...]:
    store = _mapping_store(runtime)
    candidates = tuple(store.load(candidate_id) for candidate_id in store.list())
    if graph_name is not None:
        candidates = tuple(item for item in candidates if item.graph_name == graph_name)
    return candidates


def find_reference_mapping_candidates_use_case(
    graph_name: str,
    *,
    source: str | None = None,
    target: str | None = None,
    mode: str = "confirmed_then_candidates",
    runtime: TarelRuntime | None = None,
) -> tuple[ReferenceMappingMatch, ...]:
    graph = _graph_store(runtime).load(graph_name)
    return find_reference_mapping_candidates_for_graph_use_case(
        graph,
        source=source,
        target=target,
        mode=mode,
        runtime=runtime,
    )


def find_reference_mapping_candidates_for_graph_use_case(
    graph: GraphDocument,
    *,
    source: str | None = None,
    target: str | None = None,
    mode: str = "confirmed_then_candidates",
    runtime: TarelRuntime | None = None,
) -> tuple[ReferenceMappingMatch, ...]:
    if mode not in REFERENCE_MAPPING_MODES:
        raise ReferenceMappingFailure(
            "invalid_reference_mapping_mode",
            f"Unsupported reference-mapping retrieval mode: {mode}",
        )
    source_id = _resolve_optional_field(graph, source)
    target_id = _resolve_optional_field(graph, target)
    candidates = [
        item
        for item in list_reference_mapping_candidates_use_case(
            graph_name=graph.name, runtime=runtime
        )
        if item.graph_revision == physical_graph_revision(graph)
        and item.state != "rejected"
        and (source_id is None or item.source_field_id == source_id)
        and (target_id is None or item.target_field_id == target_id)
    ]
    reviewed_pairs: dict[tuple[str, str], int] = {}
    for item in candidates:
        if item.state != "reviewed":
            continue
        pair = (item.source_field_id, item.target_field_id)
        reviewed_pairs[pair] = reviewed_pairs.get(pair, 0) + 1
    if any(count > 1 for count in reviewed_pairs.values()):
        raise ReferenceMappingFailure(
            "reference_mapping_review_conflict",
            "Multiple reviewed reference mappings target the same directed field pair.",
        )
    if mode == "confirmed_only":
        candidates = [item for item in candidates if item.state == "reviewed"]
    elif mode == "confirmed_then_candidates":
        confirmed_pairs = {
            (item.source_field_id, item.target_field_id)
            for item in candidates
            if item.state == "reviewed"
        }
        candidates = [
            item
            for item in candidates
            if item.state == "reviewed"
            or (item.source_field_id, item.target_field_id) not in confirmed_pairs
        ]
    return tuple(
        _match(graph, item) for item in sorted(candidates, key=lambda item: item.id)
    )


def decide_reference_mapping_candidate_use_case(
    candidate_id: str,
    *,
    decision: str,
    reason: str,
    expected_revision: str | None = None,
    runtime: TarelRuntime | None = None,
) -> ReferenceMappingChangeResult:
    store = _mapping_store(runtime)
    candidate = store.load(candidate_id)
    if expected_revision is None:
        raise ReferenceMappingFailure(
            "expected_reference_mapping_revision_required",
            "Reviewing a reference-mapping candidate requires its current revision.",
        )
    if candidate.revision != expected_revision:
        raise ReferenceMappingFailure(
            "stale_reference_mapping_candidate",
            "The reference-mapping candidate changed after it was loaded. Reload it first.",
        )
    graph = _graph_store(runtime).load(candidate.graph_name)
    _validate_candidate_binding(candidate, graph)
    if decision == "approve" and any(
        item.id != candidate.id
        and item.graph_revision == candidate.graph_revision
        and item.state == "reviewed"
        and item.source_field_id == candidate.source_field_id
        and item.target_field_id == candidate.target_field_id
        for item in list_reference_mapping_candidates_use_case(
            graph_name=candidate.graph_name,
            runtime=runtime,
        )
    ):
        raise ReferenceMappingFailure(
            "reference_mapping_review_conflict",
            "Another reviewed reference mapping already targets this directed field pair.",
        )
    changed = review_reference_mapping_candidate(
        candidate, decision=decision, reason=reason
    )
    return ReferenceMappingChangeResult(
        candidate=changed,
        path=store.save(changed),
        changed=True,
    )


def _latest_success(
    candidate: DiscoveryCandidate, phase: str
) -> DiscoveryObservation | None:
    matches = [
        observation
        for observation in candidate.observations
        if observation.phase == phase
        and observation.status == "succeeded"
        and observation.metrics is not None
        and observation.execution is not None
    ]
    return matches[-1] if matches else None


def _evidence_from_observation(
    observation: DiscoveryObservation,
) -> ReferenceMappingEvidence:
    if observation.metrics is None or observation.execution is None:
        raise DiscoveryFailure(
            "incomplete_reference_mapping_evidence",
            "Reference-mapping evidence requires aggregate metrics and executor metadata.",
        )
    try:
        return ReferenceMappingEvidence.from_dict(
            {
                "execution": observation.execution.to_dict(),
                "level": observation.evidence_level,
                "metrics": observation.metrics.to_dict(),
                "observation_id": observation.id,
                "phase": observation.phase,
                "query_hash": observation.query_hash,
            }
        )
    except ReferenceMappingFailure as exc:
        raise DiscoveryFailure(
            "incomplete_reference_mapping_evidence", str(exc)
        ) from exc


def _validate_candidate_binding(
    candidate: ReferenceMappingCandidate,
    graph: GraphDocument,
) -> None:
    if candidate.graph_revision != physical_graph_revision(graph):
        raise ReferenceMappingFailure(
            "reference_mapping_graph_revision_mismatch",
            "The reference-mapping candidate does not match the current graph revision.",
        )
    source = _field_by_id(graph, candidate.source_field_id)
    target = _field_by_id(graph, candidate.target_field_id)
    _object_for_field(graph, source)
    _object_for_field(graph, target)
    if source.id == target.id:
        raise ReferenceMappingFailure(
            "invalid_reference_mapping",
            "Reference mappings require different directed source and target fields.",
        )


def _match(
    graph: GraphDocument, candidate: ReferenceMappingCandidate
) -> ReferenceMappingMatch:
    return ReferenceMappingMatch(
        candidate=candidate,
        source_reference=_field_reference(graph, candidate.source_field_id),
        target_reference=_field_reference(graph, candidate.target_field_id),
    )


def _field_by_id(graph: GraphDocument, field_id: str) -> GraphNode:
    node = graph.node_by_id().get(field_id)
    if node is None or node.type != "field":
        raise ReferenceMappingFailure(
            "reference_mapping_field_not_found",
            f"Reference-mapping endpoint is not a current graph field: {field_id}",
        )
    return node


def _field_reference(graph: GraphDocument, field_id: str) -> str:
    field = _field_by_id(graph, field_id)
    parent = _object_for_field(graph, field)
    return f"{parent.label}.{field.label}"


def _object_for_field(graph: GraphDocument, field: GraphNode) -> GraphNode:
    parent = graph.node_by_id().get(str(field.metadata.get("object_id") or ""))
    if parent is None or parent.type not in {"table", "view"}:
        raise ReferenceMappingFailure(
            "reference_mapping_field_not_found",
            f"Reference-mapping field has no current graph object: {field.id}",
        )
    return parent


def _resolve_optional_field(graph: GraphDocument, reference: str | None) -> str | None:
    if reference is None:
        return None
    try:
        return resolve_field(graph, reference).field_node.id
    except RelationshipFailure as exc:
        raise ReferenceMappingFailure(
            "reference_mapping_field_not_found", str(exc)
        ) from exc


def _promoted_id(run_id: str, candidate_id: str) -> str:
    readable = f"discovery.{run_id}.{candidate_id}"
    if len(readable) <= 128:
        return readable
    digest = hashlib.sha256(f"{run_id}:{candidate_id}".encode()).hexdigest()
    return f"discovery.{digest[:32]}"


def _graph_store(runtime: TarelRuntime | None) -> FileGraphStore:
    return FileGraphStore() if runtime is None else runtime.graph_store()


def _mapping_store(runtime: TarelRuntime | None) -> FileReferenceMappingStore:
    return (
        FileReferenceMappingStore()
        if runtime is None
        else runtime.reference_mapping_store()
    )
