"""Application use cases for optional coding-agent discovery runs."""

from __future__ import annotations

import json
import math
import re
import secrets
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from tarel.discovery.contracts import (
    DISCOVERY_CONTRACT_VERSION,
    DISCOVERY_LOGICAL_JOIN_CONTRACT_VERSION,
    DISCOVERY_REFERENCE_MAPPING_CONTRACT_VERSION,
    DiscoveryCandidate,
    DiscoveryFailure,
    DiscoveryProgram,
    DiscoveryRun,
    ReferenceMappingProgram,
    allowed_discovery_actions,
    apply_discovery_action,
    discovery_program_from_dict,
)
from tarel.discovery.coverage import (
    DISCOVERY_SCOPE_MODES,
    QueryLinkedCoverageFailure,
    QueryLinkedEntityCoverage,
)
from tarel.discovery.identity import (
    IdentityFailure,
    IdentityInspection,
    IdentityInventoryManifest,
)
from tarel.discovery.logical_program import LogicalJoinProgram
from tarel.discovery.store import FileDiscoveryStore
from tarel.entity_resolution.application import (
    import_entity_resolution_candidate_use_case,
    load_entity_resolution_candidate_use_case,
)
from tarel.entity_resolution.contracts import (
    EntityResolutionCandidate,
    EntityResolutionFailure,
)
from tarel.entity_resolution.discovery import entity_candidate_from_discovery
from tarel.graph.contracts import GraphDocument, GraphEdge, GraphNode
from tarel.graph.revision import graph_revision
from tarel.graph.store import FileGraphStore
from tarel.logical_joins.contracts import LogicalJoin
from tarel.providers.contracts import Message, ProviderFailure, StructuredRequest
from tarel.providers.host import load_provider
from tarel.reference_mapping.application import (
    import_reference_mapping_candidate_use_case,
    reference_mapping_candidate_from_discovery,
)
from tarel.reference_mapping.contracts import (
    ReferenceMappingCandidate,
    ReferenceMappingFailure,
)
from tarel.relationships.core import (
    RelationshipFailure,
    add_manual_relationship_fields,
    resolve_field,
)
from tarel.retrieval.bm25 import rank_bm25
from tarel.retrieval.contracts import RetrievalDocument
from tarel.runtime import TarelRuntime
from tarel.sources.store import FileSourceStore
from tarel.topology.endpoint_contracts import LogicalEndpointFailure
from tarel.topology.endpoints import resolve_logical_endpoint_for_graph_use_case


@dataclass(frozen=True, slots=True)
class DiscoveryChangeResult:
    run: DiscoveryRun
    path: Path


@dataclass(frozen=True, slots=True)
class DiscoveryAdviceResult:
    run: DiscoveryRun
    path: Path
    provider: str
    proposed_count: int


@dataclass(frozen=True, slots=True)
class DiscoveryCoverageResult:
    coverage: QueryLinkedEntityCoverage
    path: Path
    created: bool


@dataclass(frozen=True, slots=True)
class DiscoveryPromotionResult:
    run: DiscoveryRun
    graph: GraphDocument
    edges: tuple[GraphEdge, ...]
    path: Path
    entity_candidates: tuple[EntityResolutionCandidate, ...] = ()
    reference_mapping_candidates: tuple[ReferenceMappingCandidate, ...] = ()
    logical_joins: tuple[LogicalJoin, ...] = ()


@dataclass(frozen=True, slots=True)
class DiscoveryTask:
    run_id: str
    revision: str
    kind: str
    goal: str
    allowed_actions: tuple[str, ...]
    candidates: tuple[dict[str, object], ...]
    probe_budget: int
    probes_used: int
    candidate_budget: int
    candidates_used: int
    field_hints: tuple[dict[str, object], ...] = ()
    probe_ladder: tuple[dict[str, str], ...] = ()
    raw_sample_access: str = "host_controlled"
    identity_inspection: dict[str, object] | None = None
    scope_mode: str = "global_population"

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed_actions": list(self.allowed_actions),
            "budget": {
                "candidate_budget": self.candidate_budget,
                "candidates_used": self.candidates_used,
                "probe_budget": self.probe_budget,
                "probes_used": self.probes_used,
            },
            "candidates": list(self.candidates),
            "goal": self.goal,
            "field_hints": list(self.field_hints),
            "kind": self.kind,
            "identity_inspection": self.identity_inspection,
            "probe_ladder": list(self.probe_ladder),
            "raw_sample_access": self.raw_sample_access,
            "revision": self.revision,
            "run_id": self.run_id,
            "scope_mode": self.scope_mode,
        }


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
    graph = _graph_store(runtime).load(graph_name)
    _validate_sources(graph_name, source_names, runtime=runtime)
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
    store = _discovery_store(runtime)
    if store.exists(run.id):
        raise DiscoveryFailure(
            "discovery_exists", f"Discovery run already exists: {run.id}"
        )
    return DiscoveryChangeResult(run=run, path=store.save(run))


def load_discovery_run_use_case(
    run_id: str, *, runtime: TarelRuntime | None = None
) -> DiscoveryRun:
    return _discovery_store(runtime).load(run_id)


def list_discovery_runs_use_case(
    *,
    graph_name: str | None = None,
    kind: str | None = None,
    runtime: TarelRuntime | None = None,
) -> tuple[DiscoveryRun, ...]:
    store = _discovery_store(runtime)
    runs = tuple(store.load(run_id) for run_id in store.list())
    if graph_name is not None:
        runs = tuple(run for run in runs if run.graph_name == graph_name)
    if kind is not None:
        runs = tuple(run for run in runs if run.kind == kind)
    return runs


def next_discovery_task_use_case(
    run_id: str, *, runtime: TarelRuntime | None = None
) -> DiscoveryTask:
    run = _discovery_store(runtime).load(run_id)
    graph = _validate_current_graph(run, runtime=runtime)
    return DiscoveryTask(
        run_id=run.id,
        revision=run.revision,
        kind=run.kind,
        goal=(
            run.question
            or (
                "Find concrete same-entity technical keys within one graph object."
                if run.identity_inspection is not None
                else _default_goal(run.kind)
            )
        ),
        allowed_actions=allowed_discovery_actions(run),
        candidates=tuple(_candidate_summary(item) for item in run.candidates),
        probe_budget=run.probe_budget,
        probes_used=run.probes_used,
        candidate_budget=run.candidate_budget,
        candidates_used=len(run.candidates),
        field_hints=(
            _entity_field_hints(
                graph, self_only=run.identity_inspection is not None
            )
            if run.kind == "entity_matching"
            else ()
        ),
        probe_ladder=_probe_ladder(run),
        raw_sample_access=_raw_sample_access(run, runtime=runtime),
        identity_inspection=_identity_inspection_summary(run),
        scope_mode=run.scope_mode or "global_population",
    )


def record_query_linked_coverage_use_case(
    run_id: str,
    payload: dict[str, Any],
    *,
    runtime: TarelRuntime | None = None,
) -> DiscoveryCoverageResult:
    """Persist one private, aggregate-only coverage document for a completed run."""
    store = _discovery_store(runtime)
    run = store.load(run_id)
    if run.status != "completed" or run.kind != "entity_matching":
        raise DiscoveryFailure(
            "invalid_query_linked_coverage",
            "Query-linked coverage requires one completed entity-matching run.",
        )
    if run.scope_mode != "query_linked_slice":
        raise DiscoveryFailure(
            "invalid_query_linked_coverage",
            "The discovery run was not declared as query_linked_slice.",
        )
    try:
        coverage = QueryLinkedEntityCoverage.from_dict(payload)
    except QueryLinkedCoverageFailure as exc:
        raise DiscoveryFailure(exc.code, str(exc)) from exc
    graph = _validate_current_graph(run, runtime=runtime)
    if (
        coverage.run_id != run.id
        or coverage.run_revision != run.revision
        or coverage.graph_name != run.graph_name
        or coverage.graph_revision != graph_revision(graph)
    ):
        raise DiscoveryFailure(
            "query_linked_coverage_binding_mismatch",
            "Coverage must bind the completed discovery run and current graph revision.",
        )
    _validate_query_linked_references(run, coverage, runtime=runtime)
    if store.coverage_exists(run.id):
        current = store.load_coverage(run.id)
        if current == coverage:
            return DiscoveryCoverageResult(
                coverage=current,
                path=store.coverage_path(run.id),
                created=False,
            )
        raise DiscoveryFailure(
            "query_linked_coverage_exists",
            "Query-linked coverage is create-only for one completed discovery run.",
        )
    return DiscoveryCoverageResult(
        coverage=coverage,
        path=store.save_coverage(coverage),
        created=True,
    )


def load_query_linked_coverage_use_case(
    run_id: str,
    *,
    runtime: TarelRuntime | None = None,
) -> QueryLinkedEntityCoverage:
    return _discovery_store(runtime).load_coverage(run_id)


def list_query_linked_coverages_use_case(
    *,
    graph_name: str | None = None,
    runtime: TarelRuntime | None = None,
) -> tuple[QueryLinkedEntityCoverage, ...]:
    store = _discovery_store(runtime)
    coverages = (
        store.load_coverage(run_id)
        for run_id in store.list()
        if store.coverage_exists(run_id)
    )
    return tuple(
        item
        for item in coverages
        if graph_name is None or item.graph_name == graph_name
    )


def submit_discovery_step_use_case(
    run_id: str,
    *,
    expected_revision: str,
    actor: str,
    action: str,
    payload: dict[str, Any],
    runtime: TarelRuntime | None = None,
) -> DiscoveryChangeResult:
    store = _discovery_store(runtime)
    run = store.load(run_id)
    if run.revision != expected_revision:
        raise DiscoveryFailure(
            "stale_discovery_run",
            "The discovery run changed after it was loaded. Reload discovery next.",
        )
    graph = _validate_current_graph(run, runtime=runtime)
    if action == "record_observation":
        _validate_observation_policy(run, runtime=runtime)
    if action == "register_identity_inventory":
        _validate_identity_inventory_policy(run, runtime=runtime)
        _validate_identity_inventory_bindings(graph, run, payload)
    if action == "record_entity_group":
        _validate_entity_alias_policy(run, runtime=runtime)
    if action == "propose_candidate":
        program = payload.get("program")
        if not isinstance(program, dict):
            raise DiscoveryFailure(
                "invalid_discovery", "propose_candidate requires a program object."
            )
        _validate_program_bindings(graph, program, runtime=runtime)
    changed = apply_discovery_action(run, action=action, actor=actor, payload=payload)
    return DiscoveryChangeResult(run=changed, path=store.save(changed))


def promote_discovery_candidates_use_case(
    run_id: str,
    *,
    candidate_ids: tuple[str, ...],
    reason: str,
    supersedes_candidate_id: str | None = None,
    runtime: TarelRuntime | None = None,
) -> DiscoveryPromotionResult:
    """Promote selected candidates into their existing bounded review path."""
    if not candidate_ids or len(candidate_ids) > 20 or len(candidate_ids) != len(
        set(candidate_ids)
    ):
        raise DiscoveryFailure(
            "invalid_discovery_promotion",
            "Promotion requires one to twenty unique candidate IDs.",
        )
    run = _discovery_store(runtime).load(run_id)
    if run.status != "completed":
        raise DiscoveryFailure(
            "invalid_discovery_promotion",
            "Complete the discovery run before promoting candidates.",
        )
    graph = _validate_current_graph(run, runtime=runtime)
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

    if run.kind == "entity_matching":
        if len(selected) != 1:
            raise DiscoveryFailure(
                "invalid_discovery_promotion",
                "Promote one entity-matching candidate at a time.",
            )
        if run.identity_inspection is not None:
            _validate_identity_promotion(run, selected[0])
        candidate = entity_candidate_from_discovery(
            run,
            selected[0],
            graph,
            reason=reason,
            supersedes_candidate_id=supersedes_candidate_id,
        )
        try:
            imported = import_entity_resolution_candidate_use_case(
                candidate,
                runtime=runtime,
            )
        except EntityResolutionFailure as exc:
            code = (
                exc.code
                if exc.code
                in {
                    "entity_resolution_supersede_required",
                    "invalid_entity_resolution_supersede",
                }
                else "discovery_promotion_failed"
            )
            raise DiscoveryFailure(code, str(exc)) from exc
        return DiscoveryPromotionResult(
            run=run,
            graph=graph,
            edges=(),
            entity_candidates=(imported.candidate,),
            path=imported.path,
        )

    if run.kind == "reference_mapping":
        if len(selected) != 1:
            raise DiscoveryFailure(
                "invalid_discovery_promotion",
                "Promote one reference-mapping candidate at a time.",
            )
        if supersedes_candidate_id is not None:
            raise DiscoveryFailure(
                "invalid_discovery_promotion",
                "Reference-mapping promotion does not accept entity supersede semantics.",
            )
        mapping_candidate = reference_mapping_candidate_from_discovery(
            run, selected[0], graph, reason=reason
        )
        try:
            imported_mapping = import_reference_mapping_candidate_use_case(
                mapping_candidate, runtime=runtime
            )
        except ReferenceMappingFailure as exc:
            raise DiscoveryFailure("discovery_promotion_failed", str(exc)) from exc
        return DiscoveryPromotionResult(
            run=run,
            graph=graph,
            edges=(),
            path=imported_mapping.path,
            reference_mapping_candidates=(imported_mapping.candidate,),
        )

    if supersedes_candidate_id is not None:
        raise DiscoveryFailure(
            "invalid_discovery_promotion",
            "Join promotion does not accept entity supersede semantics.",
        )

    if any(isinstance(candidate.program, LogicalJoinProgram) for candidate in selected):
        if len(selected) != 1 or not isinstance(selected[0].program, LogicalJoinProgram):
            raise DiscoveryFailure(
                "invalid_discovery_promotion",
                "Promote one logical join at a time, without physical joins.",
            )
        from tarel.logical_joins.application import promote_logical_join_use_case

        join, path = promote_logical_join_use_case(
            run, selected[0], graph, reason=reason, runtime=runtime,
        )
        return DiscoveryPromotionResult(
            run=run, graph=graph, edges=(), path=path, logical_joins=(join,),
        )

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
                candidate.program.source_transforms
                + candidate.program.target_transforms
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
                    "observation_ids": [
                        observation.id for observation in candidate.observations
                    ],
                    "run_id": run.id,
                    "run_revision": run.revision,
                },
            )
            promoted.append(edge)
    except RelationshipFailure as exc:
        raise DiscoveryFailure("discovery_promotion_failed", str(exc)) from exc
    path = _graph_store(runtime).save(updated)
    return DiscoveryPromotionResult(
        run=run,
        graph=updated,
        edges=tuple(promoted),
        entity_candidates=(),
        path=path,
    )


def _validate_identity_promotion(
    run: DiscoveryRun, candidate: DiscoveryCandidate
) -> None:
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
        manifest is None
        or not inspection.coverage_complete
        or group is None
        or support is None
        or challenge is None
        or support.query_hash == challenge.query_hash
        or reflection is None
        or reflection.decision
        not in {"accept_as_exploratory", "recommend_promotion"}
    ):
        raise DiscoveryFailure(
            "incomplete_identity_validation",
            "Identity promotion requires complete inventory coverage, one concrete key group, "
            "distinct successful support and challenge probes, and an accepting reflection.",
        )


def advise_discovery_run_use_case(
    run_id: str,
    *,
    expected_revision: str,
    count: int = 3,
    model: str | None = None,
    timeout: float = 120.0,
    runtime: TarelRuntime | None = None,
) -> DiscoveryAdviceResult:
    if not 1 <= count <= 10:
        raise DiscoveryFailure(
            "invalid_discovery", "Provider advice count must be between 1 and 10."
        )
    store = _discovery_store(runtime)
    run = store.load(run_id)
    if run.revision != expected_revision:
        raise DiscoveryFailure(
            "stale_discovery_run",
            "The discovery run changed after it was loaded. Reload discovery next.",
        )
    if run.actor_mode != "agent_with_provider_advisor" or run.advisor_provider is None:
        raise DiscoveryFailure(
            "discovery_provider_not_enabled",
            "This discovery run was not started with a provider advisor.",
        )
    if run.identity_inspection is not None:
        raise DiscoveryFailure(
            "identity_provider_orchestrator_required",
            "Identity inventory values stay ephemeral; a coding-agent or provider host must "
            "inspect them and submit structured groups through the normal discovery actions.",
        )
    if "propose_candidate" not in allowed_discovery_actions(run):
        raise DiscoveryFailure(
            "discovery_action_not_allowed",
            "The current discovery run cannot accept additional provider proposals.",
        )
    remaining = run.candidate_budget - len(run.candidates)
    requested = min(count, remaining)
    graph = _validate_current_graph(run, runtime=runtime)
    provider = load_provider(run.advisor_provider, timeout=timeout)
    raw = provider.generate_structured(
        StructuredRequest(
            messages=_advice_messages(run, graph, requested),
            schema_name="TarelDiscoveryAdvice",
            schema=_advice_schema(
                run.kind, requested,
                logical_endpoints=run.contract_version == DISCOVERY_LOGICAL_JOIN_CONTRACT_VERSION,
            ),
            model=model,
            temperature=0.0,
            max_output_tokens=4_000,
        )
    )
    if set(raw) != {"proposals"} or not isinstance(raw.get("proposals"), list):
        raise ProviderFailure(
            "invalid_provider_response",
            "Discovery advisor response must contain only a proposals array.",
        )
    proposals = raw["proposals"]
    if not 1 <= len(proposals) <= requested or any(
        not isinstance(item, dict) for item in proposals
    ):
        raise ProviderFailure(
            "invalid_provider_response",
            "Discovery advisor returned an invalid proposal count or shape.",
        )
    current = run
    for proposal in proposals:
        program = proposal.get("program")
        if not isinstance(program, dict):
            raise ProviderFailure(
                "invalid_provider_response",
                "Discovery advisor proposal requires a program object.",
            )
        _validate_program_bindings(graph, program, runtime=runtime)
        current = apply_discovery_action(
            current,
            action="propose_candidate",
            actor="provider",
            payload=proposal,
        )
    return DiscoveryAdviceResult(
        run=current,
        path=store.save(current),
        provider=provider.name,
        proposed_count=len(proposals),
    )


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
        current_graph = _graph_store(runtime).load(run.graph_name)
        current_revision = graph_revision(current_graph)
        if run.graph_revision != current_revision:
            continue
        for candidate in run.candidates:
            if isinstance(candidate.program, LogicalJoinProgram):
                try:
                    _validate_logical_program(current_graph, candidate.program, runtime=runtime)
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


def _validate_program_bindings(
    graph: GraphDocument, program: dict[str, Any], *, runtime: TarelRuntime | None = None,
) -> None:
    typed = discovery_program_from_dict(program)
    if isinstance(typed, LogicalJoinProgram):
        _validate_logical_program(graph, typed, runtime=runtime)
        return
    if isinstance(typed, ReferenceMappingProgram):
        field_references = (typed.source_field, typed.target_field)
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


def _validate_current_graph(
    run: DiscoveryRun, *, runtime: TarelRuntime | None
) -> GraphDocument:
    graph = _graph_store(runtime).load(run.graph_name)
    if graph_revision(graph) != run.graph_revision:
        raise DiscoveryFailure(
            "discovery_graph_revision_mismatch",
            "The discovery run does not match the current graph revision.",
        )
    for candidate in run.candidates:
        if isinstance(candidate.program, LogicalJoinProgram):
            _validate_logical_program(graph, candidate.program, runtime=runtime)
    return graph


def _validate_logical_program(
    graph: GraphDocument, program: LogicalJoinProgram, *, runtime: TarelRuntime | None,
) -> None:
    for endpoint in (*program.source_endpoints, *program.target_endpoints):
        resolve_logical_endpoint_for_graph_use_case(
            graph, endpoint, mode="include_candidates", runtime=runtime,
        )


def _validate_sources(
    graph_name: str,
    source_names: tuple[str, ...],
    *,
    runtime: TarelRuntime | None,
) -> None:
    if len(source_names) != len(set(source_names)):
        raise DiscoveryFailure("invalid_discovery", "Source names must be unique.")
    store = _source_store(runtime)
    for name in source_names:
        source = store.load(name)
        if graph_name not in source.graphs:
            raise DiscoveryFailure(
                "discovery_source_graph_mismatch",
                f"Source {name} is not bound to graph {graph_name}.",
            )


def _validate_observation_policy(
    run: DiscoveryRun, *, runtime: TarelRuntime | None
) -> None:
    store = _source_store(runtime)
    for name in run.source_names:
        source = store.load(name)
        if not source.allows_enrichment("aggregates"):
            raise DiscoveryFailure(
                "discovery_aggregates_not_allowed",
                f"Source {name} does not permit aggregate discovery observations.",
            )


def _validate_identity_inventory_policy(
    run: DiscoveryRun, *, runtime: TarelRuntime | None
) -> None:
    source = _source_store(runtime).load(run.source_names[0])
    if not source.allows_enrichment("entity_aliases"):
        raise DiscoveryFailure(
            "entity_aliases_not_allowed",
            f"Source {source.name} does not permit protected identity inspection.",
        )


def _validate_entity_alias_policy(
    run: DiscoveryRun, *, runtime: TarelRuntime | None
) -> None:
    source = _source_store(runtime).load(run.source_names[0])
    if not source.allows_enrichment("entity_aliases"):
        raise DiscoveryFailure(
            "entity_aliases_not_allowed",
            f"Source {source.name} does not permit durable entity alias keys.",
        )


def _validate_identity_inventory_bindings(
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


def _candidate_summary(candidate: DiscoveryCandidate) -> dict[str, object]:
    latest = candidate.observations[-1] if candidate.observations else None
    summary: dict[str, object] = {
        "generation": candidate.generation,
        "id": candidate.id,
        "latest_observation": latest.to_dict() if latest else None,
        "observation_count": len(candidate.observations),
        "parent_ids": list(candidate.parent_ids),
        "program": candidate.program.to_dict(),
        "state": candidate.state,
        "variation_operator": candidate.variation_operator,
    }
    if candidate.mapping_manifest is not None:
        summary["mapping_manifest"] = candidate.mapping_manifest.to_dict()
    return summary


def _identity_inspection_summary(run: DiscoveryRun) -> dict[str, object] | None:
    inspection = run.identity_inspection
    if inspection is None:
        return None
    manifest = inspection.manifest
    successful_indexes = {
        item.index for item in inspection.pages if item.status == "succeeded"
    }
    return {
        "alias_group_count": len(inspection.groups),
        "coverage_complete": inspection.coverage_complete,
        "covered_identities": inspection.covered_identities,
        "failed_pages": [
            {
                "error_category": item.error_category,
                "id": item.id,
                "index": item.index,
            }
            for item in inspection.pages
            if item.status == "failed"
        ],
        "identity_count": manifest.identity_count if manifest else None,
        "inventory_hash": manifest.inventory_hash if manifest else None,
        "label_field": manifest.label_field if manifest else None,
        "next_page_indexes": (
            [
                index
                for index in range(manifest.page_count)
                if index not in successful_indexes
            ]
            if manifest
            else []
        ),
        "object_reference": manifest.object_reference if manifest else None,
        "page_count": manifest.page_count if manifest else None,
        "phase": inspection.phase,
        "record_key_field": manifest.record_key_field if manifest else None,
        "reflection_count": len(inspection.reflections),
    }


def _entity_field_hints(
    graph: GraphDocument,
    *,
    self_only: bool = False,
) -> tuple[dict[str, object], ...]:
    nodes = graph.node_by_id()
    fields: list[tuple[GraphNode, GraphNode, set[str]]] = []
    self_hints: list[dict[str, object]] = []
    for field in graph.nodes:
        if field.type != "field" or not _textual_type(
            str(field.metadata.get("data_type") or "")
        ):
            continue
        parent = nodes.get(str(field.metadata.get("object_id") or ""))
        if parent is None or parent.type not in {"table", "view"}:
            continue
        tokens = set(_label_tokens(field.label))
        if tokens:
            fields.append((field, parent, tokens))
        primary_key = tuple(str(item) for item in parent.metadata.get("primary_key") or ())
        if primary_key and field.label not in primary_key:
            self_hints.append(
                {
                    "basis": "self_entity_text_field_with_declared_record_key",
                    "record_key_field": f"{parent.label}.{primary_key[0]}",
                    "source_field": f"{parent.label}.{field.label}",
                    "target_field": f"{parent.label}.{field.label}",
                }
            )
    ranked: list[tuple[int, str, str, str]] = []
    for index, (source, source_parent, source_tokens) in enumerate(fields):
        for target, target_parent, target_tokens in fields[index + 1 :]:
            if source_parent.id == target_parent.id:
                continue
            overlap = source_tokens & target_tokens
            if not overlap:
                continue
            source_reference = f"{source_parent.label}.{source.label}"
            target_reference = f"{target_parent.label}.{target.label}"
            score = len(overlap) * 10 - abs(len(source_tokens) - len(target_tokens))
            ranked.append(
                (
                    score,
                    source_reference,
                    target_reference,
                    ",".join(sorted(overlap)),
                )
            )
    ranked.sort(key=lambda item: (-item[0], item[1].casefold(), item[2].casefold()))
    cross_hints = tuple(
        {
            "basis": "compatible_text_fields_with_shared_name_tokens",
            "shared_tokens": shared,
            "source_field": source,
            "target_field": target,
        }
        for _score, source, target, shared in ranked
    )
    ordered_self = tuple(
        sorted(
            self_hints,
            key=lambda item: (
                str(item["source_field"]).casefold(),
                str(item["record_key_field"]).casefold(),
            ),
        )
    )
    if self_only:
        return ordered_self[:8]
    return (*ordered_self[:4], *cross_hints[: 8 - min(4, len(ordered_self))])


def _probe_ladder(run: DiscoveryRun) -> tuple[dict[str, str], ...]:
    if run.kind == "reference_mapping":
        return (
            {
                "code": "register_mapping_manifest",
                "purpose": "Bind the caller-owned mapping by SHA-256 and count, without values.",
            },
            {
                "code": "support_probe",
                "purpose": "Measure mapping coverage and cardinality risk with aggregates only.",
            },
            {
                "code": "challenge_probe",
                "purpose": "Use an independent probe to seek collisions and counterexamples.",
            },
            {
                "code": "assess",
                "purpose": "Select or reject only after the independent challenge.",
            },
        )
    if run.kind == "join_discovery":
        return (
            {
                "code": "exact_baseline",
                "purpose": "Measure an exact field-pair baseline before variations.",
            },
            {
                "code": "collision_challenge",
                "purpose": "Challenge coverage with collisions and row-expansion risk.",
            },
            {
                "code": "assess",
                "purpose": "Select or reject only after a successful challenge.",
            },
        )
    if run.identity_inspection is not None:
        return (
            {
                "code": "identity_inventory",
                "purpose": "Inspect the complete distinct key/label inventory ordered by label.",
            },
            {
                "code": "propose_group",
                "purpose": "Register only concrete same-entity key groups, not a global rule.",
            },
            {
                "code": "support_probe",
                "purpose": "Execute a bounded read-only SELECT supporting the suspected group.",
            },
            {
                "code": "challenge_probe",
                "purpose": "Use a different SELECT to seek contradictions and false merges.",
            },
            {
                "code": "reflect",
                "purpose": "Accept, revise, or reject the group with its confidence explicit.",
            },
        )
    return (
        {
            "code": "bounded_samples",
            "purpose": "Inspect at most ten ephemeral rows only when raw-sample access is granted.",
        },
        {
            "code": "normalized_exact_baseline",
            "purpose": "Measure normalized exact coverage before fuzzy comparison.",
        },
        {
            "code": "single_variation",
            "purpose": "Vary one comparator, threshold, transform, or guard at a time.",
        },
        {
            "code": "risk_challenge",
            "purpose": "Measure hard cases, collisions, counterexamples, and guard contradictions.",
        },
        {
            "code": "assess",
            "purpose": "Select or reject with runtime-validation status kept explicit.",
        },
    )


def _raw_sample_access(
    run: DiscoveryRun,
    *,
    runtime: TarelRuntime | None,
) -> str:
    if run.kind == "reference_mapping":
        return "not_used"
    if not run.source_names:
        return "host_controlled"
    store = _source_store(runtime)
    return (
        "granted"
        if all(
            store.load(name).allows_enrichment("raw_samples")
            for name in run.source_names
        )
        else "not_granted"
    )


def _textual_type(data_type: str) -> bool:
    lowered = data_type.casefold()
    return any(
        marker in lowered
        for marker in ("char", "clob", "string", "text")
    )


def _label_tokens(label: str) -> tuple[str, ...]:
    expanded = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", label)
    return tuple(
        token
        for token in re.findall(r"[A-Za-z0-9]+", expanded.casefold())
        if token not in {"code", "field", "id", "key"}
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


def _advice_messages(
    run: DiscoveryRun, graph: GraphDocument, count: int
) -> tuple[Message, ...]:
    nodes = graph.node_by_id()
    fields: list[dict[str, object]] = []
    for node in graph.nodes:
        if node.type != "field":
            continue
        parent = nodes.get(str(node.metadata.get("object_id") or ""))
        if parent is None:
            continue
        fields.append(
            {
                "data_type": node.metadata.get("data_type"),
                "is_primary_key": bool(node.metadata.get("is_primary_key")),
                "reference": f"{parent.label}.{node.label}",
            }
        )
    context = {
        "candidate_budget_remaining": run.candidate_budget - len(run.candidates),
        "current_candidates": [_candidate_summary(item) for item in run.candidates],
        "fields": fields,
        "graph": run.graph_name,
        "kind": run.kind,
        "proposal_count": count,
        "question": run.question,
    }
    mapping_instruction = (
        " Reference mappings are directed: choose source_field, target_field, and an explicit "
        "cardinality. Do not claim or invent a mapping manifest; the harness registers its "
        "hash and count separately."
        if run.kind == "reference_mapping"
        else ""
    )
    return (
        Message(
            role="system",
            content=(
                "Propose bounded TAREL discovery hypotheses from graph metadata and aggregate "
                "evidence only. Return the requested JSON shape. Do not include SQL, samples, "
                "rows, credentials, reasoning transcripts, or claims of executed evidence. "
                "Use only supplied field references and supported program operations. Equal "
                "field pairs require explicit self_match metadata with a separate record key."
                + mapping_instruction
            ),
        ),
        Message(
            role="user",
            content=json.dumps(context, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
        ),
    )


def _advice_schema(kind: str, count: int, *, logical_endpoints: bool = False) -> dict[str, object]:
    if kind == "reference_mapping":
        program: dict[str, object] = {
            "additionalProperties": False,
            "properties": {
                "cardinality": {
                    "enum": [
                        "many_to_many",
                        "many_to_one",
                        "one_to_many",
                        "one_to_one",
                    ]
                },
                "kind": {"enum": ["reference_mapping"]},
                "source_field": {"type": "string"},
                "target_field": {"type": "string"},
            },
            "required": ["cardinality", "kind", "source_field", "target_field"],
            "type": "object",
        }
        return _proposal_advice_schema(program, count)
    transform = {
        "additionalProperties": False,
        "properties": {
            "kind": {"enum": [
                "casefold",
                "collapse_whitespace",
                "fixed_segment",
                "strip_numeric_prefix",
                "strip_punctuation",
                "trim",
                "unicode_nfkc",
            ]},
            "length": {"type": ["integer", "null"], "minimum": 0},
            "start": {"type": ["integer", "null"], "minimum": 0},
        },
        "required": ["kind", "length", "start"],
        "type": "object",
    }
    program = {
        "additionalProperties": False,
        "properties": {
            "blocking_field_indexes": {
                "items": {"type": "integer", "minimum": 0}, "type": "array"
            },
            "comparison": {"enum": [
                "exact",
                "normalized_exact",
                "normalized_levenshtein_v1",
                "token_set_ratio_v1",
            ]},
            "kind": {"enum": ["entity_matching", "join_discovery"]},
            "contradiction_field_indexes": {
                "items": {"type": "integer", "minimum": 0}, "type": "array"
            },
            "source_fields": {
                "items": {"type": "string"}, "maxItems": 3, "minItems": 1, "type": "array"
            },
            "source_transforms": {
                "items": {"items": transform, "maxItems": 8, "type": "array"},
                "maxItems": 3,
                "minItems": 1,
                "type": "array",
            },
            "self_match": {
                "additionalProperties": False,
                "properties": {
                    "pair_policy": {"enum": ["distinct_unordered"]},
                    "record_key_field": {"type": "string"},
                },
                "required": ["pair_policy", "record_key_field"],
                "type": ["object", "null"],
            },
            "target_fields": {
                "items": {"type": "string"}, "maxItems": 3, "minItems": 1, "type": "array"
            },
            "target_transforms": {
                "items": {"items": transform, "maxItems": 8, "type": "array"},
                "maxItems": 3,
                "minItems": 1,
                "type": "array",
            },
            "threshold": {"type": ["number", "null"], "maximum": 1, "minimum": 0},
        },
        "required": [
            "blocking_field_indexes",
            "comparison",
            "contradiction_field_indexes",
            "kind",
            "source_fields",
            "source_transforms",
            "target_fields",
            "target_transforms",
            "threshold",
        ],
        "type": "object",
    }
    if logical_endpoints:
        endpoint = {
            "type": "object", "additionalProperties": False,
            "required": ["kind", "object_id", "field_id", "revision"],
            "properties": {
                "kind": {"enum": ["graph_field", "derived_field", "family_field",
                                  "family_attribute", "reference_mapping"]},
                "object_id": {"type": "string"}, "field_id": {"type": "string"},
                "revision": {"type": "string"},
            },
        }
        logical = {
            "type": "object", "additionalProperties": False,
            "required": ["kind", "comparison", "source_endpoints", "target_endpoints"],
            "properties": {"kind": {"enum": ["join_discovery"]}, "comparison": {"enum": ["exact"]},
                           "source_endpoints": {"type": "array", "items": endpoint,
                                                "minItems": 1, "maxItems": 3},
                           "target_endpoints": {"type": "array", "items": endpoint,
                                                "minItems": 1, "maxItems": 3}},
        }
        return _proposal_advice_schema({"anyOf": [program, logical]}, count)
    return _proposal_advice_schema(program, count)


def _proposal_advice_schema(
    program: dict[str, object], count: int
) -> dict[str, object]:
    return {
        "additionalProperties": False,
        "properties": {
            "proposals": {
                "items": {
                    "additionalProperties": False,
                    "properties": {
                        "candidate_id": {"type": "string"},
                        "parent_ids": {"items": {"type": "string"}, "type": "array"},
                        "program": program,
                        "variation_operator": {"type": "string"},
                    },
                    "required": [
                        "candidate_id", "parent_ids", "program", "variation_operator"
                    ],
                    "type": "object",
                },
                "maxItems": count,
                "minItems": 1,
                "type": "array",
            }
        },
        "required": ["proposals"],
        "type": "object",
    }


def _default_goal(kind: str) -> str:
    if kind == "reference_mapping":
        return "Discover directed, evidence-backed reference mappings in the current graph."
    if kind == "join_discovery":
        return "Discover bounded, evidence-backed join candidates in the current graph."
    return "Discover bounded, evidence-backed entity-matching candidates in the current graph."


def _validate_query_linked_references(
    run: DiscoveryRun,
    coverage: QueryLinkedEntityCoverage,
    *,
    runtime: TarelRuntime | None,
) -> None:
    discovery_candidates = {item.id: item for item in run.candidates}
    observations = {
        item.id: item
        for candidate in run.candidates
        for item in candidate.observations
    }
    referenced_observations = []
    for component in coverage.components:
        component_discovery = []
        for candidate_id in component.discovery_candidate_refs:
            candidate = discovery_candidates.get(candidate_id)
            if candidate is None:
                raise DiscoveryFailure(
                    "query_linked_reference_not_found",
                    f"Discovery candidate reference not found: {candidate_id}",
                )
            component_discovery.append(candidate)
        component_entities = []
        for candidate_id in component.entity_candidate_refs:
            try:
                candidate = load_entity_resolution_candidate_use_case(
                    candidate_id, runtime=runtime
                )
            except EntityResolutionFailure as exc:
                raise DiscoveryFailure(
                    "query_linked_reference_not_found",
                    f"Entity candidate reference not found: {candidate_id}",
                ) from exc
            if candidate.provenance.run_id != run.id:
                raise DiscoveryFailure(
                    "query_linked_coverage_binding_mismatch",
                    "Promoted entity candidates must originate from the coverage run.",
                )
            component_entities.append(candidate)
        component_observations = []
        for observation_id in component.observation_refs:
            observation = observations.get(observation_id)
            if observation is None:
                raise DiscoveryFailure(
                    "query_linked_reference_not_found",
                    f"Discovery observation reference not found: {observation_id}",
                )
            execution = observation.execution
            if execution is None or (
                execution.executor_id != component.executor.id
                or execution.executor_version != component.executor.version
                or execution.artifact_hash != component.executor.artifact_hash
            ):
                raise DiscoveryFailure(
                    "incomplete_query_linked_provenance",
                    "Referenced observations must match the component executor provenance.",
                )
            component_observations.append(observation)
            referenced_observations.append(observation)
        if component.status == "proposed_and_rejected" and any(
            item.state != "rejected" for item in component_discovery
        ):
            raise DiscoveryFailure(
                "invalid_query_linked_coverage",
                "proposed_and_rejected references must be rejected discovery candidates.",
            )
        if component.status.startswith("promoted_"):
            if any(item.state != "selected" for item in component_discovery):
                raise DiscoveryFailure(
                    "invalid_query_linked_coverage",
                    "Promoted components must reference selected discovery candidates.",
                )
            expected_state = (
                "reviewed"
                if component.status == "promoted_confirmed"
                else "candidate"
            )
            if any(item.state != expected_state for item in component_entities):
                raise DiscoveryFailure(
                    "invalid_query_linked_coverage",
                    "Promoted component status must match current entity review state.",
                )
            discovery_ids = {item.id for item in component_discovery}
            if any(
                item.provenance.discovery_candidate_id not in discovery_ids
                for item in component_entities
            ):
                raise DiscoveryFailure(
                    "query_linked_coverage_binding_mismatch",
                    "Promoted candidates must reference this component's discovery candidates.",
                )
        if component.status == "failed" and component_observations and any(
            item.status != "failed" for item in component_observations
        ):
            raise DiscoveryFailure(
                "invalid_query_linked_coverage",
                "Failed components may reference only failed observations.",
            )
    unique_observations = {item.id: item for item in referenced_observations}
    expected_probe_coverage = (
        sum(item.status == "succeeded" for item in unique_observations.values())
        / len(unique_observations)
        if unique_observations
        else 0.0
    )
    if not math.isclose(
        coverage.probe_coverage, expected_probe_coverage, abs_tol=1e-9
    ):
        raise DiscoveryFailure(
            "invalid_query_linked_coverage",
            "probe_coverage must equal successful referenced probes / all referenced probes.",
        )


def _graph_store(runtime: TarelRuntime | None) -> FileGraphStore:
    return FileGraphStore() if runtime is None else runtime.graph_store()


def _source_store(runtime: TarelRuntime | None) -> FileSourceStore:
    return FileSourceStore() if runtime is None else runtime.source_store()


def _discovery_store(runtime: TarelRuntime | None) -> FileDiscoveryStore:
    return FileDiscoveryStore() if runtime is None else runtime.discovery_store()
