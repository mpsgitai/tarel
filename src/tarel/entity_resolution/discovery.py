"""Promotion from exploratory discovery into entity-resolution review."""

from __future__ import annotations

import hashlib

from tarel.discovery.contracts import (
    DiscoveryCandidate,
    DiscoveryFailure,
    DiscoveryMetrics,
    DiscoveryObservation,
    DiscoveryProgram,
    DiscoveryRun,
)
from tarel.entity_resolution.contracts import (
    ENTITY_RESOLUTION_CONTRACT_VERSION,
    EntityResolutionCandidate,
    EntityResolutionEvidence,
    EntityResolutionProvenance,
    EntityResolutionQuality,
    entity_resolution_quality_rating,
    validate_entity_resolution_candidate,
)
from tarel.graph.contracts import GraphDocument
from tarel.relationships.core import RelationshipFailure, resolve_field


def entity_candidate_from_discovery(
    run: DiscoveryRun,
    candidate: DiscoveryCandidate,
    graph: GraphDocument,
    *,
    reason: str,
) -> EntityResolutionCandidate:
    if run.kind != "entity_matching" or candidate.kind != "entity_matching":
        raise DiscoveryFailure(
            "invalid_discovery_promotion",
            "Only entity-matching candidates can enter entity-resolution review.",
        )
    if run.status != "completed" or candidate.state != "selected":
        raise DiscoveryFailure(
            "invalid_discovery_promotion",
            "Entity promotion requires a completed run and a selected candidate.",
        )
    support = _latest_success(candidate, "support")
    challenge = _latest_success(candidate, "challenge")
    if challenge is None or challenge.metrics is None or challenge.metrics.evaluated_count == 0:
        raise DiscoveryFailure(
            "incomplete_entity_evidence",
            "Entity promotion requires a non-empty successful challenge observation.",
        )
    if challenge.execution is None:
        raise DiscoveryFailure(
            "incomplete_entity_execution",
            "Entity promotion requires versioned executor and blocking metadata.",
        )
    if support is not None and support.execution is None:
        raise DiscoveryFailure(
            "incomplete_entity_execution",
            "Entity promotion requires executor metadata for support and challenge evidence.",
        )
    measured = support or challenge
    if measured.metrics is None:
        raise DiscoveryFailure(
            "incomplete_entity_evidence",
            "Entity promotion requires measured aggregate evidence.",
        )
    _require_measured_risk(measured.metrics)
    _require_measured_risk(challenge.metrics)
    quality = _quality(candidate, support=support, challenge=challenge)
    program = _program_with_field_ids(candidate.program, graph)
    producer = next(
        (
            step.actor
            for step in run.steps
            if step.action == "propose_candidate" and step.candidate_id == candidate.id
        ),
        "coding_agent",
    )
    entity_candidate = EntityResolutionCandidate(
        id=_promoted_id(run.id, candidate.id),
        graph_name=run.graph_name,
        graph_revision=run.graph_revision,
        source_field_id=program.source_fields[0],
        target_field_id=program.target_fields[0],
        rule=None,
        evidence=_evidence(measured, quality.score),
        provenance=EntityResolutionProvenance(
            run_id=run.id,
            producer=producer,
            discovery_candidate_id=candidate.id,
            discovery_run_revision=run.revision,
            observation_ids=tuple(item.id for item in candidate.observations),
            promotion_reason=reason,
        ),
        program=program,
        execution=challenge.execution,
        quality=quality,
        contract_version=ENTITY_RESOLUTION_CONTRACT_VERSION,
    )
    validate_entity_resolution_candidate(entity_candidate)
    return entity_candidate


def _latest_success(
    candidate: DiscoveryCandidate,
    phase: str,
) -> DiscoveryObservation | None:
    matches = [
        observation
        for observation in candidate.observations
        if observation.phase == phase
        and observation.status == "succeeded"
        and observation.metrics is not None
    ]
    return matches[-1] if matches else None


def _require_measured_risk(metrics: DiscoveryMetrics) -> None:
    if (
        metrics.collision_count is None
        or metrics.collision_rate is None
        or metrics.counterexample_count is None
    ):
        raise DiscoveryFailure(
            "incomplete_entity_evidence",
            "Entity promotion requires measured collisions and counterexamples.",
        )


def _metric_score(metrics: DiscoveryMetrics) -> float:
    collision_rate = metrics.collision_rate
    counterexamples = metrics.counterexample_count
    if collision_rate is None or counterexamples is None:
        return 0.0
    return max(
        0.0,
        min(
            1.0,
            metrics.coverage
            * (1.0 - collision_rate)
            * (
                1.0
                - counterexamples / max(1, metrics.evaluated_count)
            ),
        ),
    )


def _quality(
    candidate: DiscoveryCandidate,
    *,
    support: DiscoveryObservation | None,
    challenge: DiscoveryObservation,
) -> EntityResolutionQuality:
    observations = [item for item in (support, challenge) if item is not None]
    score = min(
        _metric_score(item.metrics)
        for item in observations
        if item.metrics is not None
    )
    warnings: set[str] = set()
    if support is None:
        warnings.add("support_missing")
    if any(item.status == "failed" for item in candidate.observations):
        warnings.add("failed_probes_present")
    if any(item.evidence_level == "sample_tested" for item in observations):
        warnings.add("sample_only")
    if any(
        item.metrics is not None and item.metrics.coverage < 0.8
        for item in observations
    ):
        warnings.add("low_coverage")
    if any(
        item.metrics is not None and (item.metrics.counterexample_count or 0) > 0
        for item in observations
    ):
        warnings.add("counterexamples_observed")
    executions = {
        (
            item.execution.executor_id,
            item.execution.executor_version,
            item.execution.artifact_hash,
            item.execution.blocking_strategy,
            item.execution.blocking_version,
        )
        for item in observations
        if item.execution is not None
    }
    if len(executions) > 1:
        warnings.add("mixed_executors")
    rating = entity_resolution_quality_rating(score)
    return EntityResolutionQuality.from_dict(
        {
            "challenge_observation_id": challenge.id,
            "failed_observation_count": sum(
                item.status == "failed" for item in candidate.observations
            ),
            "rating": rating,
            "score": score,
            "support_observation_id": support.id if support else None,
            "version": "tarel.entity-quality.v1",
            "warnings": sorted(warnings),
        }
    )


def _evidence(
    observation: DiscoveryObservation,
    quality_score: float,
) -> EntityResolutionEvidence:
    metrics = observation.metrics
    if (
        metrics is None
        or metrics.collision_count is None
        or metrics.collision_rate is None
        or metrics.counterexample_count is None
    ):
        raise DiscoveryFailure(
            "incomplete_entity_evidence",
            "Entity promotion requires measured aggregate evidence.",
        )
    return EntityResolutionEvidence.from_dict(
        {
            "collision_count": metrics.collision_count,
            "collision_rate": metrics.collision_rate,
            "confidence": quality_score,
            "counterexample_count": metrics.counterexample_count,
            "coverage": metrics.coverage,
            "evaluated_count": metrics.evaluated_count,
            "level": observation.evidence_level,
            "matched_count": metrics.matched_count,
        }
    )


def _program_with_field_ids(
    program: DiscoveryProgram,
    graph: GraphDocument,
) -> DiscoveryProgram:
    try:
        source_ids = [
            resolve_field(graph, reference).field_node.id
            for reference in program.source_fields
        ]
        target_ids = [
            resolve_field(graph, reference).field_node.id
            for reference in program.target_fields
        ]
    except RelationshipFailure as exc:
        raise DiscoveryFailure("discovery_promotion_failed", str(exc)) from exc
    payload = program.to_dict()
    payload["source_fields"] = source_ids
    payload["target_fields"] = target_ids
    return DiscoveryProgram.from_dict(payload)


def _promoted_id(run_id: str, candidate_id: str) -> str:
    readable = f"discovery.{run_id}.{candidate_id}"
    if len(readable) <= 128:
        return readable
    digest = hashlib.sha256(f"{run_id}:{candidate_id}".encode()).hexdigest()
    return f"discovery.{digest[:32]}"
