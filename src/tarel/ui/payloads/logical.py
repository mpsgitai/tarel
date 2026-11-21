"""Logical layer: derived relations and reference mappings drawn over physical objects."""

from __future__ import annotations

from typing import Any

from tarel.graph.contracts import GraphDocument
from tarel.graph.revision import physical_graph_revision
from tarel.reference_mapping.contracts import (
    ReferenceMappingEvidence,
    ReferenceMappingFailure,
    ReferenceMappingMatch,
)
from tarel.topology.contracts import DerivationEvidence, LogicalTopologyDocument
from tarel.ui.payloads._ids import browser_id


def logical_topology_payloads(
    graph: GraphDocument,
    document: LogicalTopologyDocument,
    physical_objects: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes = graph.node_by_id()
    physical_by_id = {
        str(item["object_id"]): item
        for item in physical_objects
        if item.get("type") in {"table", "view"}
    }
    objects: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for relation in sorted(document.derived_relations, key=lambda item: (item.name, item.id)):
        source = nodes.get(relation.source.id)
        source_payload = physical_by_id.get(relation.source.id)
        if source is None or source_payload is None:
            continue
        field_names = {field.id: field.name for field in relation.output_schema}
        grain_names = tuple(
            field_names[field_id]
            for field_id in relation.grain.field_ids
            if field_id in field_names
        )
        object_id = f"logical_relation:{relation.id}"
        ui_id = browser_id(graph.name, object_id)
        usage = _reviewed_usage(relation.state)
        review = (
            {
                "decision": relation.review.decision,
                "source": relation.review.source,
            }
            if relation.review is not None
            else None
        )
        logical = {
            "document_revision": document.revision,
            "evidence": [
                _derivation_evidence_summary(item)
                for item in sorted(relation.evidence, key=lambda item: item.id)
            ],
            "grain_fields": list(grain_names),
            "plan_revision": relation.plan_revision,
            "requires_runtime_validation": relation.state == "candidate",
            "review": review,
            "source": str(source_payload["id"]),
            "source_object": source.label,
            "state": relation.state,
            "step_kinds": [step.kind for step in relation.steps],
            "usage": usage,
            "usable": relation.state == "reviewed",
        }
        namespace = source_payload.get("namespace")
        label = f"{namespace}.{relation.name}" if namespace else relation.name
        objects.append(
            {
                "annotation": None,
                "annotation_context_documents": [],
                "area": source_payload.get("area"),
                "area_ref": source_payload.get("area_ref"),
                "catalog": graph.catalog,
                "fields": [
                    {
                        "annotation": None,
                        "annotation_context_documents": [],
                        "data_type": field.data_type,
                        "id": browser_id(
                            graph.name,
                            f"logical_relation:{relation.id}:field:{field.id}",
                        ),
                        "is_nullable": field.nullable,
                        "kind": field.kind,
                        "label": field.name,
                        "position": position,
                        "review": None,
                        "semantic_type": None,
                        "source_semantics": [],
                    }
                    for position, field in enumerate(relation.output_schema, start=1)
                ],
                "grain": " + ".join(grain_names),
                "graph": graph.name,
                "id": ui_id,
                "label": label,
                "logical_topology": logical,
                "name": relation.name,
                "namespace": namespace,
                "object_id": object_id,
                "primary_key": list(grain_names),
                "reference": f"{graph.catalog}.{label}",
                "review": review,
                "schema_ref": source_payload.get("schema_ref"),
                "state": relation.state,
                "system": source_payload.get("system"),
                "technical_description": None,
                "type": "derived_relation",
                "usage": usage,
                "zones": list(source_payload.get("zones") or ()),
            }
        )
        edges.append(
            {
                "graph": graph.name,
                "id": browser_id(graph.name, f"derives:{relation.id}"),
                "metadata": {
                    "plan_revision": relation.plan_revision,
                    "state": relation.state,
                    "step_kinds": [step.kind for step in relation.steps],
                    "usage": usage,
                },
                "source": str(source_payload["id"]),
                "target": ui_id,
                "type": "derives",
            }
        )
    return objects, edges


def _derivation_evidence_summary(evidence: DerivationEvidence) -> dict[str, Any]:
    return {
        "error_count": evidence.error_count,
        "executor": {
            "name": evidence.executor.name,
            "version": evidence.executor.version,
        },
        "id": evidence.id,
        "input_count": evidence.input_count,
        "level": evidence.level,
        "output_count": evidence.output_count,
        "truncated": evidence.truncated,
    }


def reference_mapping_edge_payloads(
    graph: GraphDocument,
    matches: tuple[ReferenceMappingMatch, ...],
    *,
    visible_object_ids: set[str],
) -> list[dict[str, Any]]:
    nodes = graph.node_by_id()
    revision = physical_graph_revision(graph)
    payloads: list[dict[str, Any]] = []
    for match in sorted(matches, key=lambda item: item.candidate.id):
        candidate = match.candidate
        if candidate.graph_revision != revision:
            raise ReferenceMappingFailure(
                "reference_mapping_graph_revision_mismatch",
                "The reference-mapping candidate does not match the projected graph revision.",
            )
        source_field = nodes.get(candidate.source_field_id)
        target_field = nodes.get(candidate.target_field_id)
        if (
            source_field is None
            or source_field.type != "field"
            or target_field is None
            or target_field.type != "field"
        ):
            raise ReferenceMappingFailure(
                "reference_mapping_field_not_found",
                "A reference-mapping endpoint is not a current graph field.",
            )
        source_object_id = str(source_field.metadata.get("object_id") or "")
        target_object_id = str(target_field.metadata.get("object_id") or "")
        source_object = nodes.get(source_object_id)
        target_object = nodes.get(target_object_id)
        if (
            source_object is None
            or source_object.type not in {"table", "view"}
            or target_object is None
            or target_object.type not in {"table", "view"}
        ):
            raise ReferenceMappingFailure(
                "reference_mapping_field_not_found",
                "A reference-mapping field has no current graph object.",
            )
        if (
            source_object_id not in visible_object_ids
            or target_object_id not in visible_object_ids
        ):
            continue
        review = (
            {
                "decision": candidate.review.decision,
                "source": candidate.review.source,
            }
            if candidate.review is not None
            else None
        )
        payloads.append(
            {
                "graph": graph.name,
                "id": browser_id(graph.name, f"reference_mapping:{candidate.id}"),
                "metadata": {
                    "candidate_id": candidate.id,
                    "cardinality": candidate.cardinality,
                    "challenge": _reference_mapping_evidence_summary(
                        candidate.challenge_evidence
                    ),
                    "direction": "source_to_target",
                    "mapping_count": candidate.mapping_count,
                    "requires_runtime_validation": match.requires_runtime_validation,
                    "review": review,
                    "revision": candidate.revision,
                    "source_field": source_field.label,
                    "source_object": source_object.label,
                    "state": candidate.state,
                    "support": _reference_mapping_evidence_summary(
                        candidate.support_evidence
                    ),
                    "target_field": target_field.label,
                    "target_object": target_object.label,
                    "usage": match.usage,
                    "usable": candidate.state == "reviewed",
                },
                "source": browser_id(graph.name, source_object_id),
                "target": browser_id(graph.name, target_object_id),
                "type": "reference_mapping",
            }
        )
    return payloads


def _reference_mapping_evidence_summary(
    evidence: ReferenceMappingEvidence,
) -> dict[str, Any]:
    metrics = evidence.metrics
    return {
        "collision_count": metrics.collision_count,
        "collision_rate": metrics.collision_rate,
        "confidence": metrics.confidence,
        "counterexample_count": metrics.counterexample_count,
        "evaluated_count": metrics.evaluated_count,
        "executor": {
            "id": evidence.execution.executor_id,
            "version": evidence.execution.executor_version,
        },
        "level": evidence.level,
        "matched_count": metrics.matched_count,
        "coverage": metrics.coverage,
    }


def _reviewed_usage(state: str) -> str:
    if state == "reviewed":
        return "confirmed"
    if state == "rejected":
        return "rejected"
    return "exploratory_only"
