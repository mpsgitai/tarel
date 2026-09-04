"""Evidence-based promotion and policy-gated retrieval of logical join metadata."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from pathlib import Path

from tarel.discovery.contracts import DiscoveryCandidate, DiscoveryRun
from tarel.discovery.logical_program import LogicalJoinProgram
from tarel.graph.contracts import GraphDocument
from tarel.graph.revision import physical_graph_revision
from tarel.graph.store import FileGraphStore
from tarel.logical_joins.contracts import LOGICAL_JOIN_MODES, LogicalJoin, LogicalJoinFailure
from tarel.logical_joins.store import FileLogicalJoinStore
from tarel.runtime import TarelRuntime
from tarel.topology.endpoint_contracts import (
    LogicalEndpoint,
    LogicalEndpointFailure,
    ResolvedLogicalEndpoint,
)
from tarel.topology.endpoints import resolve_logical_endpoint_for_graph_use_case


@dataclass(frozen=True, slots=True)
class LogicalJoinMatch:
    join: LogicalJoin
    endpoints: tuple[ResolvedLogicalEndpoint, ...]

    @property
    def usage(self) -> str:
        return (
            "confirmed"
            if self.join.state == "reviewed"
            and all(item.usage == "confirmed" for item in self.endpoints)
            else "exploratory_only"
        )

    def to_dict(self) -> dict[str, object]:
        return {
            **logical_join_summary(self.join),
            "usage": self.usage,
            "requires_runtime_validation": self.usage != "confirmed",
            "endpoints": [item.to_dict() for item in self.endpoints],
        }


def logical_join_summary(join: LogicalJoin) -> dict[str, object]:
    return {
        "kind": "logical_join",
        "id": join.id,
        "graph": join.graph_name,
        "revision": join.revision,
        "state": join.state,
        "program": join.program.to_dict(),
        "evidence": [
            {
                "observation_id": item.id,
                "phase": item.phase,
                "status": item.status,
                "level": item.evidence_level,
                "metrics": item.metrics.to_dict() if item.metrics else None,
            }
            for item in join.observations
        ],
        "provenance": {
            "run_id": join.run_id,
            "run_revision": join.run_revision,
            "discovery_candidate_id": join.discovery_candidate_id,
        },
        "notice": "Logical join metadata only, never a physical edge or executable plan. "
        "Dependencies and their pinned review states must be current.",
    }


def promote_logical_join_use_case(
    run: DiscoveryRun,
    candidate: DiscoveryCandidate,
    graph: GraphDocument,
    *,
    reason: str,
    runtime: TarelRuntime | None = None,
) -> tuple[LogicalJoin, Path]:
    if (
        run.status != "completed"
        or candidate.state != "selected"
        or not isinstance(candidate.program, LogicalJoinProgram)
    ):
        raise LogicalJoinFailure(
            "invalid_logical_join_promotion", "Complete and select a logical join before promotion."
        )
    source_step = next(
        (
            step
            for step in run.steps
            if step.action == "propose_candidate" and step.candidate_id == candidate.id
        ),
        None,
    )
    join = LogicalJoin(
        id="logical-" + hashlib.sha256(f"{run.id}:{candidate.id}".encode()).hexdigest()[:32],
        graph_name=graph.name,
        graph_revision=physical_graph_revision(graph),
        program=candidate.program,
        observations=candidate.observations,
        run_id=run.id,
        run_revision=run.revision,
        discovery_candidate_id=candidate.id,
        producer=source_step.actor if source_step else "coding_agent",
        promotion_reason=reason,
    )
    LogicalJoin.from_dict(join.to_dict())
    _resolve(join, graph, mode="include_candidates", runtime=runtime)
    store = _store(runtime)
    if store.exists(join.id):
        current = store.load(join.id)
        if replace(current, state="candidate", review_reason=None) != join:
            raise LogicalJoinFailure("logical_join_exists", "Logical join identity already exists.")
        return current, store.path(current.id)
    return join, store.save(join)


def load_logical_join_use_case(
    join_id: str,
    *,
    runtime: TarelRuntime | None = None,
) -> LogicalJoin:
    """Load an audit record; find/review revalidate current dependencies."""
    return _store(runtime).load(join_id)


def list_logical_joins_use_case(
    *,
    graph_name: str | None = None,
    runtime: TarelRuntime | None = None,
) -> tuple[LogicalJoin, ...]:
    store = _store(runtime)
    return tuple(
        join
        for join in (store.load(item) for item in store.list())
        if graph_name is None or join.graph_name == graph_name
    )


def review_logical_join_use_case(
    join_id: str,
    *,
    decision: str,
    reason: str,
    expected_revision: str,
    runtime: TarelRuntime | None = None,
) -> LogicalJoin:
    join = load_logical_join_use_case(join_id, runtime=runtime)
    if expected_revision != join.revision:
        raise LogicalJoinFailure("stale_logical_join", "Reload the logical join before reviewing.")
    if join.state != "candidate":
        raise LogicalJoinFailure("logical_join_already_reviewed", "Review decisions are terminal.")
    if not isinstance(decision, str) or decision not in {"approve", "reject"}:
        raise LogicalJoinFailure("invalid_logical_join_review", "Choose approve or reject.")
    graph = _graphs(runtime).load(join.graph_name)
    # Human review of a rule is separate from the review of its dependencies. Approval is
    # allowed for audit, but confirmed retrieval never bypasses unreviewed dependencies.
    _resolve(join, graph, mode="include_candidates", runtime=runtime)
    if decision == "approve" and any(
        other.id != join.id
        and other.state == "reviewed"
        and other.graph_revision == join.graph_revision
        and other.program == join.program
        for other in list_logical_joins_use_case(graph_name=join.graph_name, runtime=runtime)
    ):
        raise LogicalJoinFailure(
            "logical_join_review_conflict",
            "Another reviewed logical join already owns this program.",
        )
    changed = replace(
        join, state="reviewed" if decision == "approve" else "rejected", review_reason=reason
    )
    LogicalJoin.from_dict(changed.to_dict())
    _store(runtime).save(changed)
    return changed


def find_logical_joins_use_case(
    graph_name: str,
    *,
    mode: str = "confirmed_only",
    endpoint: LogicalEndpoint | None = None,
    join_id: str | None = None,
    limit: int = 20,
    runtime: TarelRuntime | None = None,
) -> tuple[LogicalJoinMatch, ...]:
    if not isinstance(mode, str) or mode not in LOGICAL_JOIN_MODES:
        raise LogicalJoinFailure("invalid_logical_join_mode", "Unknown logical join policy.")
    if type(limit) is not int or not 1 <= limit <= 200:
        raise LogicalJoinFailure("invalid_logical_join_limit", "Logical join limit must be 1..200.")
    if endpoint is not None and not isinstance(endpoint, LogicalEndpoint):
        raise LogicalJoinFailure("invalid_logical_join_endpoint", "Expected a typed endpoint.")
    graph = _graphs(runtime).load(graph_name)
    physical_revision = physical_graph_revision(graph)
    matches: list[LogicalJoinMatch] = []
    candidates = list_logical_joins_use_case(graph_name=graph_name, runtime=runtime)
    if join_id is not None:
        requested = load_logical_join_use_case(join_id, runtime=runtime)
        if requested.graph_name != graph_name:
            return ()
        # Exact lookup narrows the result, never the review-policy authority. Inspect
        # matching-program siblings before filtering the requested ID or applying limits.
        candidates = tuple(item for item in candidates if item.program == requested.program)
    for join in candidates:
        if join.graph_name != graph_name:
            continue
        if join.state == "rejected" or (mode == "confirmed_only" and join.state != "reviewed"):
            continue
        if endpoint is not None and endpoint not in (
            *join.program.source_endpoints,
            *join.program.target_endpoints,
        ):
            continue
        if join.graph_revision != physical_revision:
            continue
        try:
            endpoints = _resolve(join, graph, mode=mode, runtime=runtime)
        except LogicalEndpointFailure as exc:
            if exc.code in {
                "stale_logical_endpoint",
                "logical_endpoint_policy_excluded",
                "logical_endpoint_not_found",
            }:
                continue
            raise
        matches.append(LogicalJoinMatch(join, endpoints))
    grouped: dict[LogicalJoinProgram, list[LogicalJoinMatch]] = {}
    for match in matches:
        grouped.setdefault(match.join.program, []).append(match)
    selected: list[LogicalJoinMatch] = []
    for group in grouped.values():
        confirmed = [item for item in group if item.usage == "confirmed"]
        if len(confirmed) > 1:
            raise LogicalJoinFailure(
                "ambiguous_logical_joins", "Multiple reviewed joins describe the same logical pair."
            )
        selected.extend(confirmed if mode == "confirmed_then_candidates" and confirmed else group)
    selected = [item for item in selected if join_id is None or item.join.id == join_id]
    return tuple(sorted(selected, key=lambda item: (item.usage != "confirmed", item.join.id)))[
        :limit
    ]


def _resolve(
    join: LogicalJoin,
    graph: GraphDocument,
    *,
    mode: str,
    runtime: TarelRuntime | None,
) -> tuple[ResolvedLogicalEndpoint, ...]:
    if join.graph_revision != physical_graph_revision(graph):
        raise LogicalJoinFailure("stale_logical_join", "Logical join physical graph changed.")
    return tuple(
        resolve_logical_endpoint_for_graph_use_case(graph, endpoint, mode=mode, runtime=runtime)
        for endpoint in (*join.program.source_endpoints, *join.program.target_endpoints)
    )


def _store(runtime: TarelRuntime | None) -> FileLogicalJoinStore:
    return FileLogicalJoinStore(runtime.root / "logical-joins" if runtime else None)


def _graphs(runtime: TarelRuntime | None) -> FileGraphStore:
    return runtime.graph_store() if runtime else FileGraphStore()
