"""Discovery run use cases: start, load, list, submit steps and find candidates."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from tarel.discovery.actions import apply_discovery_action
from tarel.discovery.checks import (
    validate_current_graph,
    validate_entity_alias_policy,
    validate_identity_inventory_bindings,
    validate_identity_inventory_policy,
    validate_logical_program,
    validate_observation_policy,
    validate_program_bindings,
    validate_sources,
)
from tarel.discovery.contracts import (
    DISCOVERY_CONTRACT_VERSION,
    DISCOVERY_LOGICAL_JOIN_CONTRACT_VERSION,
    DISCOVERY_REFERENCE_MAPPING_CONTRACT_VERSION,
    DiscoveryFailure,
)
from tarel.discovery.coverage import DISCOVERY_SCOPE_MODES
from tarel.discovery.identity import IdentityInspection
from tarel.discovery.logical_program import LogicalJoinProgram
from tarel.discovery.programs import ReferenceMappingProgram
from tarel.discovery.runs import DiscoveryCandidate, DiscoveryRun
from tarel.graph.revision import graph_revision
from tarel.retrieval.bm25 import rank_bm25
from tarel.retrieval.contracts import RetrievalDocument
from tarel.runtime import TarelRuntime, resolve_runtime
from tarel.topology.endpoint_contracts import LogicalEndpointFailure


@dataclass(frozen=True, slots=True)
class DiscoveryChangeResult:
    run: DiscoveryRun
    path: Path


@dataclass(frozen=True, slots=True)
class DiscoveryMatch:
    run_id: str
    run_revision: str
    graph_name: str
    candidate: DiscoveryCandidate
    question: str | None
    score: float | None = None

    @property
    def usage(self) -> str:
        return "exploratory_selected" if self.candidate.state == "selected" else "exploratory_only"

    def to_dict(self) -> dict[str, object]:
        subject = {
            "entity_matching": "entity-matching rule",
            "reference_mapping": "reference mapping",
        }.get(self.candidate.kind, "relationship")
        return {
            "candidate": self.candidate.to_dict(),
            "graph": self.graph_name,
            "run_id": self.run_id,
            "run_revision": self.run_revision,
            "score": self.score,
            "usage": self.usage,
            "warning": (
                f"Discovery selection is agent-assessed, not a human-reviewed TAREL {subject}. "
                "Revalidate it at runtime before using it in an answer."
            ),
        }


def start_discovery_run_use_case(
    kind: str,
    *,
    graph_name: str,
    source_names: tuple[str, ...] = (),
    question: str | None = None,
    probe_budget: int = 40,
    candidate_budget: int = 20,
    advisor_provider: str | None = None,
    identity_inspection: bool = False,
    logical_endpoints: bool = False,
    scope_mode: str = "global_population",
    run_id: str | None = None,
    runtime: TarelRuntime | None = None,
) -> DiscoveryChangeResult:
    if type(logical_endpoints) is not bool or (logical_endpoints and kind != "join_discovery"):
        raise DiscoveryFailure("invalid_discovery", "Logical endpoints are an opt-in join mode.")
    if identity_inspection and (kind != "entity_matching" or len(source_names) != 1):
        raise DiscoveryFailure(
            "invalid_discovery",
            "Identity inspection requires entity matching and exactly one configured source.",
        )
    if scope_mode not in DISCOVERY_SCOPE_MODES:
        raise DiscoveryFailure(
            "invalid_discovery", f"Unsupported discovery scope mode: {scope_mode}"
        )
    if scope_mode == "query_linked_slice" and (
        kind != "entity_matching" or identity_inspection
    ):
        raise DiscoveryFailure(
            "invalid_discovery",
            "Query-linked scope requires entity matching without key-persisting "
            "identity inspection.",
        )
    graph = resolve_runtime(runtime).graph_store().load(graph_name)
    validate_sources(graph_name, source_names, runtime=runtime)
    prefix = kind.replace("_discovery", "").replace("_matching", "")
    generated_id = run_id or f"{prefix}-{secrets.token_hex(6)}"
    run = DiscoveryRun.from_dict(
        {
            "actor_mode": "agent_with_provider_advisor" if advisor_provider else "agent",
            "advisor_provider": advisor_provider,
            "candidate_budget": candidate_budget,
            "candidates": [],
            "completion_reason": None,
            "contract_version": (
                DISCOVERY_LOGICAL_JOIN_CONTRACT_VERSION
                if logical_endpoints else
                DISCOVERY_REFERENCE_MAPPING_CONTRACT_VERSION
                if kind == "reference_mapping"
                else DISCOVERY_CONTRACT_VERSION
            ),
            "graph": {"name": graph.name, "revision": graph_revision(graph)},
            "id": generated_id,
            "kind": kind,
            "probe_budget": probe_budget,
            "question": question,
            "scope_mode": scope_mode,
            "source_names": list(source_names),
            "status": "open",
            "steps": [],
            **(
                {"identity_inspection": IdentityInspection().to_dict()}
                if identity_inspection
                else {}
            ),
        }
    )
    store = resolve_runtime(runtime).discovery_store()
    if store.exists(run.id):
        raise DiscoveryFailure(
            "discovery_exists", f"Discovery run already exists: {run.id}"
        )
    return DiscoveryChangeResult(run=run, path=store.save(run))


def load_discovery_run_use_case(
    run_id: str, *, runtime: TarelRuntime | None = None
) -> DiscoveryRun:
    return resolve_runtime(runtime).discovery_store().load(run_id)


def list_discovery_runs_use_case(
    *,
    graph_name: str | None = None,
    kind: str | None = None,
    runtime: TarelRuntime | None = None,
) -> tuple[DiscoveryRun, ...]:
    store = resolve_runtime(runtime).discovery_store()
    runs = tuple(store.load(run_id) for run_id in store.list())
    if graph_name is not None:
        runs = tuple(run for run in runs if run.graph_name == graph_name)
    if kind is not None:
        runs = tuple(run for run in runs if run.kind == kind)
    return runs


def submit_discovery_step_use_case(
    run_id: str,
    *,
    expected_revision: str,
    actor: str,
    action: str,
    payload: dict[str, Any],
    runtime: TarelRuntime | None = None,
) -> DiscoveryChangeResult:
    store = resolve_runtime(runtime).discovery_store()
    run = store.load(run_id)
    if run.revision != expected_revision:
        raise DiscoveryFailure(
            "stale_discovery_run",
            "The discovery run changed after it was loaded. Reload discovery next.",
        )
    graph = validate_current_graph(run, runtime=runtime)
    if action == "record_observation":
        validate_observation_policy(run, runtime=runtime)
    if action == "register_identity_inventory":
        validate_identity_inventory_policy(run, runtime=runtime)
        validate_identity_inventory_bindings(graph, run, payload)
    if action == "record_entity_group":
        validate_entity_alias_policy(run, runtime=runtime)
    if action == "propose_candidate":
        program = payload.get("program")
        if not isinstance(program, dict):
            raise DiscoveryFailure(
                "invalid_discovery", "propose_candidate requires a program object."
            )
        validate_program_bindings(graph, program, runtime=runtime)
    changed = apply_discovery_action(run, action=action, actor=actor, payload=payload)
    return DiscoveryChangeResult(run=changed, path=store.save(changed))


def find_discovery_candidates_use_case(
    *,
    graph_name: str | None = None,
    kind: str | None = None,
    include_exploratory: bool = False,
    query: str | None = None,
    limit: int = 20,
    runtime: TarelRuntime | None = None,
) -> tuple[DiscoveryMatch, ...]:
    if not 1 <= limit <= 200:
        raise DiscoveryFailure(
            "invalid_discovery", "Discovery retrieval limit must be between 1 and 200."
        )
    matches: list[DiscoveryMatch] = []
    for run in list_discovery_runs_use_case(
        graph_name=graph_name, kind=kind, runtime=runtime
    ):
        current_graph = resolve_runtime(runtime).graph_store().load(run.graph_name)
        current_revision = graph_revision(current_graph)
        if run.graph_revision != current_revision:
            continue
        for candidate in run.candidates:
            if isinstance(candidate.program, LogicalJoinProgram):
                try:
                    validate_logical_program(current_graph, candidate.program, runtime=runtime)
                except LogicalEndpointFailure as exc:
                    if exc.code in {"stale_logical_endpoint", "logical_endpoint_policy_excluded",
                                    "logical_endpoint_not_found"}:
                        continue
                    raise
            if candidate.state == "selected" or (
                include_exploratory and candidate.state != "rejected"
            ):
                matches.append(
                    DiscoveryMatch(
                        run_id=run.id,
                        run_revision=run.revision,
                        graph_name=run.graph_name,
                        candidate=candidate,
                        question=run.question,
                    )
                )
    ordered = tuple(sorted(matches, key=lambda item: (item.run_id, item.candidate.id)))
    if not query:
        return ordered[:limit]
    documents = tuple(_retrieval_document(match) for match in ordered)
    ranked = rank_bm25(documents, query, limit=limit)
    by_id = {
        f"{match.run_id}:{match.candidate.id}": match
        for match in ordered
    }
    return tuple(
        replace(by_id[item.document.id], score=round(item.score, 6))
        for item in ranked
    )


def _retrieval_document(match: DiscoveryMatch) -> RetrievalDocument:
    candidate = match.candidate
    program = candidate.program
    if isinstance(program, LogicalJoinProgram):
        text = "\n".join((
            "Logical join discovery", match.question or "", candidate.state,
            *(f"{item.kind} {item.object_id} {item.field_id}"
              for item in (*program.source_endpoints, *program.target_endpoints)),
            *(f"{item.phase} {item.evidence_level} coverage "
              f"{item.metrics.coverage if item.metrics else 'unknown'}"
              for item in candidate.observations),
        ))
        return RetrievalDocument(
            id=f"{match.run_id}:{candidate.id}", object_id=match.run_id,
            field_id=None, namespace=match.graph_name, label=candidate.id, text=text,
        )
    if isinstance(program, ReferenceMappingProgram):
        evidence = [
            (
                f"{observation.phase} {observation.status} {observation.evidence_level} "
                f"coverage {observation.metrics.coverage if observation.metrics else 'unknown'} "
                f"confidence {observation.metrics.confidence if observation.metrics else 'unknown'}"
            )
            for observation in candidate.observations
        ]
        text = "\n".join(
            (
                f"Discovery kind: {candidate.kind}",
                f"Question: {match.question or ''}",
                f"State: {candidate.state}",
                f"Variation: {candidate.variation_operator}",
                f"Direction: {program.source_field} -> {program.target_field}",
                f"Cardinality: {program.cardinality}",
                *evidence,
            )
        )
        return RetrievalDocument(
            id=f"{match.run_id}:{candidate.id}",
            object_id=match.run_id,
            field_id=None,
            namespace=match.graph_name,
            label=candidate.id,
            text=text,
        )
    transforms = [
        transform.kind
        for field_transforms in (*program.source_transforms, *program.target_transforms)
        for transform in field_transforms
    ]
    evidence = [
        (
            f"{observation.phase} {observation.status} {observation.evidence_level} "
            f"coverage {observation.metrics.coverage if observation.metrics else 'unknown'} "
            f"confidence {observation.metrics.confidence if observation.metrics else 'unknown'}"
        )
        for observation in candidate.observations
    ]
    text = "\n".join(
        (
            f"Discovery kind: {candidate.kind}",
            f"Question: {match.question or ''}",
            f"State: {candidate.state}",
            f"Variation: {candidate.variation_operator}",
            f"Comparison: {program.comparison}",
            f"Source fields: {', '.join(program.source_fields)}",
            f"Target fields: {', '.join(program.target_fields)}",
            f"Entity scope: {'self_object' if program.self_match else 'cross_object'}",
            f"Record key: {program.self_match.record_key_field if program.self_match else ''}",
            f"Pair policy: {program.self_match.pair_policy if program.self_match else ''}",
            f"Transforms: {', '.join(sorted(set(transforms)))}",
            *evidence,
        )
    )
    return RetrievalDocument(
        id=f"{match.run_id}:{candidate.id}",
        object_id=match.run_id,
        field_id=None,
        namespace=match.graph_name,
        label=candidate.id,
        text=text,
    )
