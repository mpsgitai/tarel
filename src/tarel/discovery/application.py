"""Application use cases for optional coding-agent discovery runs."""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from tarel.discovery.contracts import (
    DISCOVERY_CONTRACT_VERSION,
    DiscoveryCandidate,
    DiscoveryFailure,
    DiscoveryRun,
    allowed_discovery_actions,
    apply_discovery_action,
)
from tarel.discovery.store import FileDiscoveryStore
from tarel.graph.contracts import GraphDocument, GraphEdge
from tarel.graph.revision import graph_revision
from tarel.graph.store import FileGraphStore
from tarel.providers.contracts import Message, ProviderFailure, StructuredRequest
from tarel.providers.host import load_provider
from tarel.relationships.core import (
    RelationshipFailure,
    add_manual_relationship_fields,
    resolve_field,
)
from tarel.retrieval.bm25 import rank_bm25
from tarel.retrieval.contracts import RetrievalDocument
from tarel.runtime import TarelRuntime
from tarel.sources.store import FileSourceStore


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
class DiscoveryPromotionResult:
    run: DiscoveryRun
    graph: GraphDocument
    edges: tuple[GraphEdge, ...]
    path: Path


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
            "kind": self.kind,
            "revision": self.revision,
            "run_id": self.run_id,
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
        return {
            "candidate": self.candidate.to_dict(),
            "graph": self.graph_name,
            "run_id": self.run_id,
            "run_revision": self.run_revision,
            "score": self.score,
            "usage": self.usage,
            "warning": (
                "Discovery selection is agent-assessed, not a human-reviewed TAREL relationship. "
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
    run_id: str | None = None,
    runtime: TarelRuntime | None = None,
) -> DiscoveryChangeResult:
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
            "contract_version": DISCOVERY_CONTRACT_VERSION,
            "graph": {"name": graph.name, "revision": graph_revision(graph)},
            "id": generated_id,
            "kind": kind,
            "probe_budget": probe_budget,
            "question": question,
            "source_names": list(source_names),
            "status": "open",
            "steps": [],
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
    _validate_current_graph(run, runtime=runtime)
    return DiscoveryTask(
        run_id=run.id,
        revision=run.revision,
        kind=run.kind,
        goal=run.question or _default_goal(run.kind),
        allowed_actions=allowed_discovery_actions(run),
        candidates=tuple(_candidate_summary(item) for item in run.candidates),
        probe_budget=run.probe_budget,
        probes_used=run.probes_used,
        candidate_budget=run.candidate_budget,
        candidates_used=len(run.candidates),
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
    if action == "propose_candidate":
        program = payload.get("program")
        if not isinstance(program, dict):
            raise DiscoveryFailure(
                "invalid_discovery", "propose_candidate requires a program object."
            )
        _validate_program_bindings(graph, program)
    changed = apply_discovery_action(run, action=action, actor=actor, payload=payload)
    return DiscoveryChangeResult(run=changed, path=store.save(changed))


def promote_discovery_candidates_use_case(
    run_id: str,
    *,
    candidate_ids: tuple[str, ...],
    reason: str,
    runtime: TarelRuntime | None = None,
) -> DiscoveryPromotionResult:
    """Atomically promote selected exact join programs into graph review drafts."""
    if not candidate_ids or len(candidate_ids) > 20 or len(candidate_ids) != len(
        set(candidate_ids)
    ):
        raise DiscoveryFailure(
            "invalid_discovery_promotion",
            "Promotion requires one to twenty unique candidate IDs.",
        )
    run = _discovery_store(runtime).load(run_id)
    if run.kind != "join_discovery":
        raise DiscoveryFailure(
            "invalid_discovery_promotion",
            "Only join-discovery candidates can enter relationship review.",
        )
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
        if candidate.program.comparison != "exact" or any(
            candidate.program.source_transforms + candidate.program.target_transforms
        ):
            raise DiscoveryFailure(
                "unsupported_discovery_promotion",
                "Only exact join candidates without transforms can enter graph review.",
            )
        selected.append(candidate)

    updated = graph
    promoted: list[GraphEdge] = []
    try:
        for candidate in selected:
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
        path=path,
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
            schema=_advice_schema(requested),
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
        _validate_program_bindings(graph, program)
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
        current_revision = graph_revision(_graph_store(runtime).load(run.graph_name))
        if run.graph_revision != current_revision:
            continue
        for candidate in run.candidates:
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


def _validate_program_bindings(graph: GraphDocument, program: dict[str, Any]) -> None:
    field_values: list[object] = []
    for key in ("source_fields", "target_fields"):
        value = program.get(key)
        if not isinstance(value, list):
            raise DiscoveryFailure("invalid_discovery", f"{key} must be an array.")
        field_values.extend(value)
    for reference in field_values:
        if not isinstance(reference, str):
            raise DiscoveryFailure(
                "invalid_discovery", "Discovery field references must be strings."
            )
        try:
            resolve_field(graph, reference)
        except RelationshipFailure as exc:
            raise DiscoveryFailure("discovery_field_not_found", str(exc)) from exc


def _validate_current_graph(
    run: DiscoveryRun, *, runtime: TarelRuntime | None
) -> GraphDocument:
    graph = _graph_store(runtime).load(run.graph_name)
    if graph_revision(graph) != run.graph_revision:
        raise DiscoveryFailure(
            "discovery_graph_revision_mismatch",
            "The discovery run does not match the current graph revision.",
        )
    return graph


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


def _candidate_summary(candidate: DiscoveryCandidate) -> dict[str, object]:
    latest = candidate.observations[-1] if candidate.observations else None
    return {
        "generation": candidate.generation,
        "id": candidate.id,
        "latest_observation": latest.to_dict() if latest else None,
        "observation_count": len(candidate.observations),
        "parent_ids": list(candidate.parent_ids),
        "program": candidate.program.to_dict(),
        "state": candidate.state,
        "variation_operator": candidate.variation_operator,
    }


def _retrieval_document(match: DiscoveryMatch) -> RetrievalDocument:
    candidate = match.candidate
    program = candidate.program
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
    return (
        Message(
            role="system",
            content=(
                "Propose bounded TAREL discovery hypotheses from graph metadata and aggregate "
                "evidence only. Return the requested JSON shape. Do not include SQL, samples, "
                "rows, credentials, reasoning transcripts, or claims of executed evidence. "
                "Use only supplied field references and supported program operations."
            ),
        ),
        Message(
            role="user",
            content=json.dumps(context, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
        ),
    )


def _advice_schema(count: int) -> dict[str, object]:
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
    if kind == "join_discovery":
        return "Discover bounded, evidence-backed join candidates in the current graph."
    return "Discover bounded, evidence-backed entity-matching candidates in the current graph."


def _graph_store(runtime: TarelRuntime | None) -> FileGraphStore:
    return FileGraphStore() if runtime is None else runtime.graph_store()


def _source_store(runtime: TarelRuntime | None) -> FileSourceStore:
    return FileSourceStore() if runtime is None else runtime.source_store()


def _discovery_store(runtime: TarelRuntime | None) -> FileDiscoveryStore:
    return FileDiscoveryStore() if runtime is None else runtime.discovery_store()
