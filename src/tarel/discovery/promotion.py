"""Promotion of accepted discovery candidates into draft graph knowledge."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tarel.discovery.checks import validate_current_graph
from tarel.discovery.contracts import DiscoveryFailure
from tarel.discovery.logical_program import LogicalJoinProgram
from tarel.discovery.programs import DiscoveryProgram
from tarel.discovery.runs import DiscoveryCandidate, DiscoveryRun
from tarel.entity_resolution.application import import_entity_resolution_candidate_use_case
from tarel.entity_resolution.candidates import (
    EntityResolutionCandidate,
)
from tarel.entity_resolution.contracts import (
    EntityResolutionFailure,
)
from tarel.entity_resolution.discovery import entity_candidate_from_discovery
from tarel.graph.contracts import GraphDocument, GraphEdge
from tarel.logical_joins.contracts import LogicalJoin
from tarel.reference_mapping.application import (
    import_reference_mapping_candidate_use_case,
    reference_mapping_candidate_from_discovery,
)
from tarel.reference_mapping.contracts import ReferenceMappingCandidate, ReferenceMappingFailure
from tarel.relationships.core import RelationshipFailure, add_manual_relationship_fields
from tarel.runtime import TarelRuntime, resolve_runtime


@dataclass(frozen=True, slots=True)
class DiscoveryPromotionResult:
    run: DiscoveryRun
    graph: GraphDocument
    edges: tuple[GraphEdge, ...]
    path: Path
    entity_candidates: tuple[EntityResolutionCandidate, ...] = ()
    reference_mapping_candidates: tuple[ReferenceMappingCandidate, ...] = ()
    logical_joins: tuple[LogicalJoin, ...] = ()


def promote_discovery_candidates_use_case(
    run_id: str,
    *,
    candidate_ids: tuple[str, ...],
    reason: str,
    supersedes_candidate_id: str | None = None,
    runtime: TarelRuntime | None = None,
) -> DiscoveryPromotionResult:
    """Promote selected candidates into their existing bounded review path.

    Entity matches and reference mappings become review candidates of their own kind, a logical
    join becomes a logical-join document, and exact physical joins become draft graph edges.
    """
    if not candidate_ids or len(candidate_ids) > 20 or len(candidate_ids) != len(
        set(candidate_ids)
    ):
        raise DiscoveryFailure(
            "invalid_discovery_promotion",
            "Promotion requires one to twenty unique candidate IDs.",
        )
    run = resolve_runtime(runtime).discovery_store().load(run_id)
    if run.status != "completed":
        raise DiscoveryFailure(
            "invalid_discovery_promotion",
            "Complete the discovery run before promoting candidates.",
        )
    graph = validate_current_graph(run, runtime=runtime)
    selected = _selected_candidates(run, candidate_ids)
    if run.kind == "entity_matching":
        return _promote_entity_match(
            run, _only(selected, "entity-matching"), graph, reason, supersedes_candidate_id, runtime
        )
    if supersedes_candidate_id is not None:
        raise DiscoveryFailure(
            "invalid_discovery_promotion",
            "Only entity-matching promotion accepts supersede semantics.",
        )
    if run.kind == "reference_mapping":
        return _promote_reference_mapping(
            run, _only(selected, "reference-mapping"), graph, reason, runtime
        )
    if any(isinstance(candidate.program, LogicalJoinProgram) for candidate in selected):
        from tarel.logical_joins.application import promote_logical_join_use_case

        if len(selected) != 1 or not isinstance(selected[0].program, LogicalJoinProgram):
            raise DiscoveryFailure(
                "invalid_discovery_promotion",
                "Promote one logical join at a time, without physical joins.",
            )
        join, path = promote_logical_join_use_case(
            run, selected[0], graph, reason=reason, runtime=runtime,
        )
        return DiscoveryPromotionResult(
            run=run, graph=graph, edges=(), path=path, logical_joins=(join,),
        )
    return _promote_join_edges(run, selected, graph, reason, runtime)


def _selected_candidates(
    run: DiscoveryRun, candidate_ids: tuple[str, ...]
) -> list[DiscoveryCandidate]:
    candidates_by_id = {candidate.id: candidate for candidate in run.candidates}
    selected: list[DiscoveryCandidate] = []
    for candidate_id in candidate_ids:
        candidate = candidates_by_id.get(candidate_id)
        if candidate is None:
            raise DiscoveryFailure(
                "discovery_candidate_not_found",
                f"Discovery candidate not found: {candidate_id}",
            )
        if candidate.state != "selected":
            raise DiscoveryFailure(
                "invalid_discovery_promotion",
                f"Discovery candidate is not selected: {candidate_id}",
            )
        selected.append(candidate)
    return selected


def _only(selected: list[DiscoveryCandidate], kind: str) -> DiscoveryCandidate:
    if len(selected) != 1:
        raise DiscoveryFailure(
            "invalid_discovery_promotion", f"Promote one {kind} candidate at a time."
        )
    return selected[0]


def _promote_entity_match(
    run: DiscoveryRun,
    candidate: DiscoveryCandidate,
    graph: GraphDocument,
    reason: str,
    supersedes_candidate_id: str | None,
    runtime: TarelRuntime | None,
) -> DiscoveryPromotionResult:
    if run.identity_inspection is not None:
        _validate_identity_promotion(run, candidate)
    entity_candidate = entity_candidate_from_discovery(
        run, candidate, graph, reason=reason, supersedes_candidate_id=supersedes_candidate_id,
    )
    try:
        imported = import_entity_resolution_candidate_use_case(entity_candidate, runtime=runtime)
    except EntityResolutionFailure as exc:
        passthrough = {
            "entity_resolution_supersede_required",
            "invalid_entity_resolution_supersede",
        }
        code = exc.code if exc.code in passthrough else "discovery_promotion_failed"
        raise DiscoveryFailure(code, str(exc)) from exc
    return DiscoveryPromotionResult(
        run=run,
        graph=graph,
        edges=(),
        entity_candidates=(imported.candidate,),
        path=imported.path,
    )


def _promote_reference_mapping(
    run: DiscoveryRun,
    candidate: DiscoveryCandidate,
    graph: GraphDocument,
    reason: str,
    runtime: TarelRuntime | None,
) -> DiscoveryPromotionResult:
    mapping_candidate = reference_mapping_candidate_from_discovery(
        run, candidate, graph, reason=reason
    )
    try:
        imported = import_reference_mapping_candidate_use_case(mapping_candidate, runtime=runtime)
    except ReferenceMappingFailure as exc:
        raise DiscoveryFailure("discovery_promotion_failed", str(exc)) from exc
    return DiscoveryPromotionResult(
        run=run,
        graph=graph,
        edges=(),
        path=imported.path,
        reference_mapping_candidates=(imported.candidate,),
    )


def _promote_join_edges(
    run: DiscoveryRun,
    selected: list[DiscoveryCandidate],
    graph: GraphDocument,
    reason: str,
    runtime: TarelRuntime | None,
) -> DiscoveryPromotionResult:
    """Exact, transform-free join candidates become draft relationships in the graph."""
    updated = graph
    promoted: list[GraphEdge] = []
    try:
        for candidate in selected:
            if not isinstance(candidate.program, DiscoveryProgram):
                raise DiscoveryFailure(
                    "invalid_discovery_promotion",
                    "Join promotion requires a join-discovery program.",
                )
            if candidate.program.comparison != "exact" or any(
                candidate.program.source_transforms + candidate.program.target_transforms
            ):
                raise DiscoveryFailure(
                    "unsupported_discovery_promotion",
                    "Only exact join candidates without transforms can enter graph review.",
                )
            updated, edge = add_manual_relationship_fields(
                updated,
                from_references=candidate.program.source_fields,
                to_references=candidate.program.target_fields,
                reason=reason,
                validated=False,
                origin="discovery_run",
                provenance={
                    "candidate_generation": candidate.generation,
                    "candidate_id": candidate.id,
                    "observation_ids": [observation.id for observation in candidate.observations],
                    "run_id": run.id,
                    "run_revision": run.revision,
                },
            )
            promoted.append(edge)
    except RelationshipFailure as exc:
        raise DiscoveryFailure("discovery_promotion_failed", str(exc)) from exc
    path = resolve_runtime(runtime).graph_store().save(updated)
    return DiscoveryPromotionResult(
        run=run,
        graph=updated,
        edges=tuple(promoted),
        entity_candidates=(),
        path=path,
    )


def _validate_identity_promotion(run: DiscoveryRun, candidate: DiscoveryCandidate) -> None:
    inspection = run.identity_inspection
    manifest = inspection.manifest if inspection else None
    group = inspection.group_for_candidate(candidate.id) if inspection else None
    support = next(
        (
            item
            for item in reversed(candidate.observations)
            if item.phase == "support" and item.status == "succeeded"
        ),
        None,
    )
    challenge = next(
        (
            item
            for item in reversed(candidate.observations)
            if item.phase == "challenge" and item.status == "succeeded"
        ),
        None,
    )
    reflection = next(
        (
            item
            for item in reversed(inspection.reflections if inspection else ())
            if challenge is not None
            and item.candidate_id == candidate.id
            and item.observation_id == challenge.id
        ),
        None,
    )
    if (
        inspection is None
        or manifest is None
        or not inspection.coverage_complete
        or group is None
        or support is None
        or challenge is None
        or support.query_hash == challenge.query_hash
        or reflection is None
        or reflection.decision not in {"accept_as_exploratory", "recommend_promotion"}
    ):
        raise DiscoveryFailure(
            "incomplete_identity_validation",
            "Identity promotion requires complete inventory coverage, one concrete key group, "
            "distinct successful support and challenge probes, and an accepting reflection.",
        )
