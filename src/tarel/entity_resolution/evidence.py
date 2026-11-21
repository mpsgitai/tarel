"""What supports an entity match: rules, evidence, provenance, quality and review."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from tarel.entity_resolution._parse import (
    MAX_OPERATIONS,
    MAX_REASON_LENGTH,
    identifier_array,
    require_choice,
    require_fields,
    require_identifier,
    require_integer,
    require_rate,
    require_sha256,
    require_text,
    string_array,
)
from tarel.entity_resolution.contracts import (
    ENTITY_RESOLUTION_EVIDENCE_LEVELS,
    ENTITY_RESOLUTION_OPERATIONS,
    EntityResolutionFailure,
)

_QUALITY_WARNINGS = frozenset(
    {
        "counterexamples_observed",
        "failed_probes_present",
        "low_coverage",
        "mixed_executors",
        "sample_only",
        "support_missing",
    }
)


@dataclass(frozen=True, slots=True)
class EntityResolutionRule:
    kind: str
    operations: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {"kind": self.kind, "operations": list(self.operations)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EntityResolutionRule:
        require_fields(data, {"kind", "operations"}, "entity-resolution rule")
        kind = require_choice(data.get("kind"), "rule kind", frozenset({"normalized_exact"}))
        operations = string_array(data.get("operations"), "rule operations")
        if not operations or len(operations) > MAX_OPERATIONS:
            raise EntityResolutionFailure(
                "invalid_entity_resolution",
                f"A rule requires between 1 and {MAX_OPERATIONS} operations.",
            )
        if len(operations) != len(set(operations)):
            raise EntityResolutionFailure(
                "invalid_entity_resolution",
                "Entity-resolution rule operations must be unique.",
            )
        unknown = set(operations) - ENTITY_RESOLUTION_OPERATIONS
        if unknown:
            raise EntityResolutionFailure(
                "invalid_entity_resolution",
                "Unsupported entity-resolution rule operation: " + sorted(unknown)[0],
            )
        return cls(kind=kind, operations=operations)


@dataclass(frozen=True, slots=True)
class EntityResolutionEvidence:
    level: str
    evaluated_count: int
    matched_count: int
    collision_count: int
    counterexample_count: int
    coverage: float
    collision_rate: float
    confidence: float

    def to_dict(self) -> dict[str, object]:
        return {
            "collision_count": self.collision_count,
            "collision_rate": self.collision_rate,
            "confidence": self.confidence,
            "counterexample_count": self.counterexample_count,
            "coverage": self.coverage,
            "evaluated_count": self.evaluated_count,
            "level": self.level,
            "matched_count": self.matched_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EntityResolutionEvidence:
        require_fields(
            data,
            {
                "collision_count",
                "collision_rate",
                "confidence",
                "counterexample_count",
                "coverage",
                "evaluated_count",
                "level",
                "matched_count",
            },
            "entity-resolution evidence",
        )
        evidence = cls(
            level=require_choice(
                data.get("level"),
                "evidence level",
                ENTITY_RESOLUTION_EVIDENCE_LEVELS,
            ),
            evaluated_count=require_integer(data.get("evaluated_count"), "evaluated_count"),
            matched_count=require_integer(data.get("matched_count"), "matched_count"),
            collision_count=require_integer(data.get("collision_count"), "collision_count"),
            counterexample_count=require_integer(
                data.get("counterexample_count"),
                "counterexample_count",
            ),
            coverage=require_rate(data.get("coverage"), "coverage"),
            collision_rate=require_rate(data.get("collision_rate"), "collision_rate"),
            confidence=require_rate(data.get("confidence"), "confidence"),
        )
        _validate_evidence(evidence)
        return evidence


@dataclass(frozen=True, slots=True)
class EntityResolutionProvenance:
    run_id: str
    producer: str
    discovery_candidate_id: str | None = None
    discovery_run_revision: str | None = None
    observation_ids: tuple[str, ...] = ()
    promotion_reason: str | None = None
    supersedes_candidate_id: str | None = None
    source_names: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {"producer": self.producer, "run_id": self.run_id}
        if self.discovery_candidate_id is not None:
            payload["discovery_candidate_id"] = self.discovery_candidate_id
        if self.discovery_run_revision is not None:
            payload["discovery_run_revision"] = self.discovery_run_revision
        if self.observation_ids:
            payload["observation_ids"] = list(self.observation_ids)
        if self.promotion_reason is not None:
            payload["promotion_reason"] = self.promotion_reason
        if self.supersedes_candidate_id is not None:
            payload["supersedes_candidate_id"] = self.supersedes_candidate_id
        if self.source_names:
            payload["source_names"] = list(self.source_names)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EntityResolutionProvenance:
        require_fields(
            data,
            {"producer", "run_id"},
            "entity-resolution provenance",
            optional={
                "discovery_candidate_id",
                "discovery_run_revision",
                "observation_ids",
                "promotion_reason",
                "supersedes_candidate_id",
                "source_names",
            },
        )
        observation_ids = data.get("observation_ids", [])
        return cls(
            run_id=require_identifier(data.get("run_id"), "run_id"),
            producer=require_identifier(data.get("producer"), "producer"),
            discovery_candidate_id=(
                require_identifier(
                    data.get("discovery_candidate_id"), "discovery_candidate_id"
                )
                if data.get("discovery_candidate_id") is not None
                else None
            ),
            discovery_run_revision=(
                require_sha256(
                    data.get("discovery_run_revision"), "discovery_run_revision"
                )
                if data.get("discovery_run_revision") is not None
                else None
            ),
            observation_ids=identifier_array(
                observation_ids, "observation_ids"
            ),
            promotion_reason=(
                require_text(
                    data.get("promotion_reason"),
                    "promotion_reason",
                    limit=MAX_REASON_LENGTH,
                )
                if data.get("promotion_reason") is not None
                else None
            ),
            supersedes_candidate_id=(
                require_identifier(
                    data.get("supersedes_candidate_id"),
                    "supersedes_candidate_id",
                )
                if data.get("supersedes_candidate_id") is not None
                else None
            ),
            source_names=identifier_array(
                data.get("source_names", []), "source_names"
            ),
        )


@dataclass(frozen=True, slots=True)
class EntityResolutionQuality:
    score: float
    rating: str
    support_observation_id: str | None
    challenge_observation_id: str
    failed_observation_count: int
    warnings: tuple[str, ...]
    version: str = "tarel.entity-quality.v1"

    def to_dict(self) -> dict[str, object]:
        return {
            "challenge_observation_id": self.challenge_observation_id,
            "failed_observation_count": self.failed_observation_count,
            "rating": self.rating,
            "score": self.score,
            "support_observation_id": self.support_observation_id,
            "version": self.version,
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EntityResolutionQuality:
        require_fields(
            data,
            {
                "challenge_observation_id",
                "failed_observation_count",
                "rating",
                "score",
                "support_observation_id",
                "version",
                "warnings",
            },
            "entity-resolution quality",
        )
        if data.get("version") != "tarel.entity-quality.v1":
            raise EntityResolutionFailure(
                "unsupported_entity_resolution",
                "Unsupported entity-resolution quality calculation.",
            )
        support = data.get("support_observation_id")
        warnings = string_array(data.get("warnings"), "quality warnings")
        if len(warnings) != len(set(warnings)) or set(warnings) - _QUALITY_WARNINGS:
            raise EntityResolutionFailure(
                "invalid_entity_resolution",
                "Entity-resolution quality warnings must be unique allowlisted codes.",
            )
        quality = cls(
            score=require_rate(data.get("score"), "quality score"),
            rating=require_choice(
                data.get("rating"),
                "quality rating",
                frozenset({"insufficient", "moderate", "strong", "weak"}),
            ),
            support_observation_id=(
                require_identifier(support, "support_observation_id")
                if support is not None
                else None
            ),
            challenge_observation_id=require_identifier(
                data.get("challenge_observation_id"),
                "challenge_observation_id",
            ),
            failed_observation_count=require_integer(
                data.get("failed_observation_count"),
                "failed_observation_count",
            ),
            warnings=warnings,
        )
        expected_rating = entity_resolution_quality_rating(quality.score)
        if quality.rating != expected_rating:
            raise EntityResolutionFailure(
                "invalid_entity_resolution",
                "Entity-resolution quality rating does not match its score.",
            )
        return quality


@dataclass(frozen=True, slots=True)
class SelfEntityMatch:
    """Graph-bound identity semantics for distinct records of one object."""

    object_id: str
    record_key_field_id: str
    comparison_field_ids: tuple[str, ...]
    contradiction_field_ids: tuple[str, ...]
    pair_policy: str = "distinct_unordered"

    def to_dict(self) -> dict[str, object]:
        return {
            "comparison_field_ids": list(self.comparison_field_ids),
            "contradiction_field_ids": list(self.contradiction_field_ids),
            "object_id": self.object_id,
            "pair_policy": self.pair_policy,
            "record_key_field_id": self.record_key_field_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SelfEntityMatch:
        require_fields(
            data,
            {
                "comparison_field_ids",
                "contradiction_field_ids",
                "object_id",
                "pair_policy",
                "record_key_field_id",
            },
            "self-entity match",
        )
        self_match = cls(
            object_id=require_text(data.get("object_id"), "object_id"),
            record_key_field_id=require_text(
                data.get("record_key_field_id"), "record_key_field_id"
            ),
            comparison_field_ids=string_array(
                data.get("comparison_field_ids"), "comparison_field_ids"
            ),
            contradiction_field_ids=string_array(
                data.get("contradiction_field_ids"), "contradiction_field_ids"
            ),
            pair_policy=require_choice(
                data.get("pair_policy"),
                "pair_policy",
                frozenset({"distinct_unordered"}),
            ),
        )
        if not self_match.comparison_field_ids:
            raise EntityResolutionFailure(
                "invalid_entity_resolution",
                "Self-entity matching requires comparison fields.",
            )
        fields = (
            self_match.record_key_field_id,
            *self_match.comparison_field_ids,
            *self_match.contradiction_field_ids,
        )
        if len(fields) != len(set(fields)):
            raise EntityResolutionFailure(
                "invalid_entity_resolution",
                "Self-entity record, comparison, and contradiction fields must be distinct.",
            )
        return self_match


@dataclass(frozen=True, slots=True)
class EntityResolutionReview:
    decision: str
    reason: str
    source: str = "human"

    def to_dict(self) -> dict[str, str]:
        return {"decision": self.decision, "reason": self.reason, "source": self.source}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EntityResolutionReview:
        require_fields(data, {"decision", "reason", "source"}, "entity-resolution review")
        source = require_text(data.get("source"), "review source")
        if source != "human":
            raise EntityResolutionFailure(
                "invalid_entity_resolution",
                "Entity-resolution review source must be human.",
            )
        return cls(
            decision=require_choice(
                data.get("decision"),
                "review decision",
                frozenset({"approve", "reject"}),
            ),
            reason=require_text(data.get("reason"), "review reason", limit=MAX_REASON_LENGTH),
        )


def _validate_evidence(evidence: EntityResolutionEvidence) -> None:
    if evidence.matched_count > evidence.evaluated_count:
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            "matched_count cannot exceed evaluated_count.",
        )
    if evidence.collision_count > evidence.matched_count:
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            "collision_count cannot exceed matched_count.",
        )
    if evidence.counterexample_count > evidence.evaluated_count:
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            "counterexample_count cannot exceed evaluated_count.",
        )
    if evidence.level == "proposed":
        if any(
            value != 0
            for value in (
                evidence.evaluated_count,
                evidence.matched_count,
                evidence.collision_count,
                evidence.counterexample_count,
                evidence.coverage,
                evidence.collision_rate,
            )
        ):
            raise EntityResolutionFailure(
                "invalid_entity_resolution",
                "Proposed evidence cannot claim evaluated rows or measured rates.",
            )
        return
    if evidence.evaluated_count == 0:
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            "Tested entity-resolution evidence requires evaluated rows.",
        )
    expected_coverage = evidence.matched_count / evidence.evaluated_count
    expected_collision_rate = (
        evidence.collision_count / evidence.matched_count
        if evidence.matched_count
        else 0.0
    )
    if not math.isclose(evidence.coverage, expected_coverage, abs_tol=1e-6):
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            "coverage does not match matched_count / evaluated_count.",
        )
    if not math.isclose(evidence.collision_rate, expected_collision_rate, abs_tol=1e-6):
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            "collision_rate does not match collision_count / matched_count.",
        )


def entity_resolution_quality_rating(score: float) -> str:
    if score >= 0.9:
        return "strong"
    if score >= 0.7:
        return "moderate"
    if score >= 0.4:
        return "weak"
    return "insufficient"
