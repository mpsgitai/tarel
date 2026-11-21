"""The next task of a discovery run: what the harness should probe, observe or propose."""

from __future__ import annotations

import re
from dataclasses import dataclass

from tarel.discovery.actions import allowed_discovery_actions
from tarel.discovery.checks import validate_current_graph
from tarel.discovery.runs import DiscoveryCandidate, DiscoveryRun
from tarel.graph.contracts import GraphDocument, GraphNode
from tarel.runtime import TarelRuntime, resolve_runtime


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


def next_discovery_task_use_case(
    run_id: str, *, runtime: TarelRuntime | None = None
) -> DiscoveryTask:
    run = resolve_runtime(runtime).discovery_store().load(run_id)
    graph = validate_current_graph(run, runtime=runtime)
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
        candidates=tuple(candidate_summary(item) for item in run.candidates),
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


def candidate_summary(candidate: DiscoveryCandidate) -> dict[str, object]:
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
    store = resolve_runtime(runtime).source_store()
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


def _default_goal(kind: str) -> str:
    if kind == "reference_mapping":
        return "Discover directed, evidence-backed reference mappings in the current graph."
    if kind == "join_discovery":
        return "Discover bounded, evidence-backed join candidates in the current graph."
    return "Discover bounded, evidence-backed entity-matching candidates in the current graph."
