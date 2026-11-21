"""Provider advice for a discovery run: a bounded structured review of its candidates."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from tarel.discovery.actions import allowed_discovery_actions, apply_discovery_action
from tarel.discovery.checks import validate_current_graph, validate_program_bindings
from tarel.discovery.contracts import DISCOVERY_LOGICAL_JOIN_CONTRACT_VERSION, DiscoveryFailure
from tarel.discovery.runs import DiscoveryRun
from tarel.discovery.tasks import candidate_summary
from tarel.graph.contracts import GraphDocument
from tarel.providers.contracts import Message, ProviderFailure, StructuredRequest
from tarel.providers.host import load_provider
from tarel.runtime import TarelRuntime, resolve_runtime


@dataclass(frozen=True, slots=True)
class DiscoveryAdviceResult:
    run: DiscoveryRun
    path: Path
    provider: str
    proposed_count: int


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
    store = resolve_runtime(runtime).discovery_store()
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
    graph = validate_current_graph(run, runtime=runtime)
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
    proposals: list[object] = raw["proposals"]
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
        validate_program_bindings(graph, program, runtime=runtime)
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
        "current_candidates": [candidate_summary(item) for item in run.candidates],
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
