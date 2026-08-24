"""Graph-edge projection for entity-resolution candidates."""

from __future__ import annotations

from tarel.entity_resolution.contracts import EntityResolutionFailure, EntityResolutionMatch
from tarel.graph.contracts import GraphDocument, GraphEdge


def project_entity_resolution_edges(
    graph: GraphDocument,
    matches: tuple[EntityResolutionMatch, ...],
) -> tuple[GraphEdge, ...]:
    nodes = graph.node_by_id()
    edges = []
    for match in matches:
        candidate = match.candidate
        source = nodes.get(candidate.source_field_id)
        target = nodes.get(candidate.target_field_id)
        if source is None or source.type != "field" or target is None or target.type != "field":
            raise EntityResolutionFailure(
                "entity_resolution_field_not_found",
                f"Could not project current entity-resolution endpoints: {candidate.id}",
            )
        evidence = candidate.evidence
        if candidate.program is not None:
            rule_kind = candidate.program.comparison
            operations = sorted(
                {
                    transform.kind
                    for transforms in (
                        *candidate.program.source_transforms,
                        *candidate.program.target_transforms,
                    )
                    for transform in transforms
                }
            )
            threshold = candidate.program.threshold
            blocking_fields = [
                candidate.program.source_fields[index]
                for index in candidate.program.blocking_field_indexes
            ]
            contradiction_fields = [
                candidate.program.source_fields[index]
                for index in candidate.program.contradiction_field_indexes
            ]
        else:
            rule_kind = candidate.rule.kind if candidate.rule else "unknown"
            operations = list(candidate.rule.operations) if candidate.rule else []
            threshold = None
            blocking_fields = []
            contradiction_fields = []
        quality = candidate.quality
        execution = candidate.execution
        edges.append(
            GraphEdge(
                id=f"entity_resolution_candidate:{candidate.id}",
                source_id=source.id,
                target_id=target.id,
                type="entity_resolution_candidate",
                metadata={
                    "candidate_id": candidate.id,
                    "collision_rate": evidence.collision_rate,
                    "confidence": evidence.confidence,
                    "counterexample_count": evidence.counterexample_count,
                    "coverage": evidence.coverage,
                    "evaluated_count": evidence.evaluated_count,
                    "evidence_level": evidence.level,
                    "human_reviewed": candidate.human_reviewed,
                    "operations": operations,
                    "producer": candidate.provenance.producer,
                    "requires_runtime_validation": match.requires_runtime_validation,
                    "rule_kind": rule_kind,
                    "threshold": threshold,
                    "blocking_fields": blocking_fields,
                    "contradiction_fields": contradiction_fields,
                    "quality_rating": quality.rating if quality else None,
                    "quality_score": quality.score if quality else evidence.confidence,
                    "quality_warnings": list(quality.warnings) if quality else [],
                    "executor_id": execution.executor_id if execution else None,
                    "executor_version": execution.executor_version if execution else None,
                    "blocking_strategy": (
                        execution.blocking_strategy if execution else None
                    ),
                    "run_id": candidate.provenance.run_id,
                    "source_field": source.label,
                    "state": candidate.state,
                    "target_field": target.label,
                    "usage": match.usage,
                },
            )
        )
    return tuple(edges)
