"""Strict contracts for bounded entity-resolution hypotheses."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, replace
from typing import Any

from tarel.discovery.contracts import DiscoveryExecution, DiscoveryProgram
from tarel.discovery.identity import EntityAliasGroup, IdentityFailure

ENTITY_RESOLUTION_CONTRACT_VERSION = "tarel.entity-resolution-candidate.v0.2"
ENTITY_RESOLUTION_LEGACY_CONTRACT_VERSION = "tarel.entity-resolution-candidate.v0.1"
ENTITY_RESOLUTION_CONTRACT_VERSIONS = frozenset(
    {ENTITY_RESOLUTION_CONTRACT_VERSION, ENTITY_RESOLUTION_LEGACY_CONTRACT_VERSION}
)
ENTITY_RESOLUTION_STATES = frozenset({"candidate", "rejected", "reviewed"})
ENTITY_RESOLUTION_EVIDENCE_LEVELS = frozenset(
    {"population_tested", "proposed", "sample_tested"}
)
ENTITY_RESOLUTION_MODES = frozenset(
    {"confirmed_only", "confirmed_then_candidates", "include_candidates"}
)
ENTITY_RESOLUTION_OPERATIONS = frozenset(
    {"casefold", "collapse_whitespace", "strip_punctuation", "trim", "unicode_nfkc"}
)
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_REASON_LENGTH = 1_000
_MAX_OPERATIONS = 8
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


class EntityResolutionFailure(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class EntityResolutionRule:
    kind: str
    operations: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {"kind": self.kind, "operations": list(self.operations)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EntityResolutionRule:
        _fields(data, {"kind", "operations"}, "entity-resolution rule")
        kind = _choice(data.get("kind"), "rule kind", frozenset({"normalized_exact"}))
        operations = _string_array(data.get("operations"), "rule operations")
        if not operations or len(operations) > _MAX_OPERATIONS:
            raise EntityResolutionFailure(
                "invalid_entity_resolution",
                f"A rule requires between 1 and {_MAX_OPERATIONS} operations.",
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
        _fields(
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
            level=_choice(
                data.get("level"),
                "evidence level",
                ENTITY_RESOLUTION_EVIDENCE_LEVELS,
            ),
            evaluated_count=_integer(data.get("evaluated_count"), "evaluated_count"),
            matched_count=_integer(data.get("matched_count"), "matched_count"),
            collision_count=_integer(data.get("collision_count"), "collision_count"),
            counterexample_count=_integer(
                data.get("counterexample_count"),
                "counterexample_count",
            ),
            coverage=_rate(data.get("coverage"), "coverage"),
            collision_rate=_rate(data.get("collision_rate"), "collision_rate"),
            confidence=_rate(data.get("confidence"), "confidence"),
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
        _fields(
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
            run_id=_identifier(data.get("run_id"), "run_id"),
            producer=_identifier(data.get("producer"), "producer"),
            discovery_candidate_id=(
                _identifier(
                    data.get("discovery_candidate_id"), "discovery_candidate_id"
                )
                if data.get("discovery_candidate_id") is not None
                else None
            ),
            discovery_run_revision=(
                _sha256(
                    data.get("discovery_run_revision"), "discovery_run_revision"
                )
                if data.get("discovery_run_revision") is not None
                else None
            ),
            observation_ids=_identifier_array(
                observation_ids, "observation_ids"
            ),
            promotion_reason=(
                _text(
                    data.get("promotion_reason"),
                    "promotion_reason",
                    limit=_MAX_REASON_LENGTH,
                )
                if data.get("promotion_reason") is not None
                else None
            ),
            supersedes_candidate_id=(
                _identifier(
                    data.get("supersedes_candidate_id"),
                    "supersedes_candidate_id",
                )
                if data.get("supersedes_candidate_id") is not None
                else None
            ),
            source_names=_identifier_array(
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
        _fields(
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
        warnings = _string_array(data.get("warnings"), "quality warnings")
        if len(warnings) != len(set(warnings)) or set(warnings) - _QUALITY_WARNINGS:
            raise EntityResolutionFailure(
                "invalid_entity_resolution",
                "Entity-resolution quality warnings must be unique allowlisted codes.",
            )
        quality = cls(
            score=_rate(data.get("score"), "quality score"),
            rating=_choice(
                data.get("rating"),
                "quality rating",
                frozenset({"insufficient", "moderate", "strong", "weak"}),
            ),
            support_observation_id=(
                _identifier(support, "support_observation_id")
                if support is not None
                else None
            ),
            challenge_observation_id=_identifier(
                data.get("challenge_observation_id"),
                "challenge_observation_id",
            ),
            failed_observation_count=_integer(
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
        _fields(
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
            object_id=_text(data.get("object_id"), "object_id"),
            record_key_field_id=_text(
                data.get("record_key_field_id"), "record_key_field_id"
            ),
            comparison_field_ids=_string_array(
                data.get("comparison_field_ids"), "comparison_field_ids"
            ),
            contradiction_field_ids=_string_array(
                data.get("contradiction_field_ids"), "contradiction_field_ids"
            ),
            pair_policy=_choice(
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
        _fields(data, {"decision", "reason", "source"}, "entity-resolution review")
        source = _text(data.get("source"), "review source")
        if source != "human":
            raise EntityResolutionFailure(
                "invalid_entity_resolution",
                "Entity-resolution review source must be human.",
            )
        return cls(
            decision=_choice(
                data.get("decision"),
                "review decision",
                frozenset({"approve", "reject"}),
            ),
            reason=_text(data.get("reason"), "review reason", limit=_MAX_REASON_LENGTH),
        )


@dataclass(frozen=True, slots=True)
class EntityResolutionCandidate:
    id: str
    graph_name: str
    graph_revision: str
    source_field_id: str
    target_field_id: str
    rule: EntityResolutionRule | None
    evidence: EntityResolutionEvidence
    provenance: EntityResolutionProvenance
    program: DiscoveryProgram | None = None
    execution: DiscoveryExecution | None = None
    quality: EntityResolutionQuality | None = None
    self_match: SelfEntityMatch | None = None
    identity_group: EntityAliasGroup | None = None
    state: str = "candidate"
    review: EntityResolutionReview | None = None
    contract_version: str = ENTITY_RESOLUTION_LEGACY_CONTRACT_VERSION

    @property
    def revision(self) -> str:
        payload = json.dumps(
            self.to_dict(include_revision=False),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @property
    def human_reviewed(self) -> bool:
        return self.review is not None

    def to_dict(
        self,
        *,
        include_revision: bool = True,
        include_identity_values: bool = True,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "contract_version": self.contract_version,
            "evidence": self.evidence.to_dict(),
            "graph": {"name": self.graph_name, "revision": self.graph_revision},
            "id": self.id,
            "provenance": self.provenance.to_dict(),
            "review": self.review.to_dict() if self.review else None,
            "source_field_id": self.source_field_id,
            "state": self.state,
            "target_field_id": self.target_field_id,
        }
        if self.contract_version == ENTITY_RESOLUTION_LEGACY_CONTRACT_VERSION:
            payload["rule"] = self.rule.to_dict() if self.rule else None
        else:
            payload["execution"] = self.execution.to_dict() if self.execution else None
            payload["program"] = self.program.to_dict() if self.program else None
            payload["quality"] = self.quality.to_dict() if self.quality else None
            if self.self_match is not None:
                payload["self_match"] = self.self_match.to_dict()
            if self.identity_group is not None:
                payload["identity_group"] = self.identity_group.to_dict(
                    include_members=include_identity_values
                )
        if include_revision:
            payload["revision"] = self.revision
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EntityResolutionCandidate:
        contract_version = data.get("contract_version")
        if contract_version not in ENTITY_RESOLUTION_CONTRACT_VERSIONS:
            raise EntityResolutionFailure(
                "unsupported_entity_resolution",
                "Unsupported TAREL entity-resolution candidate contract.",
            )
        common_fields = {
                "contract_version",
                "evidence",
                "graph",
                "id",
                "provenance",
                "review",
                "source_field_id",
                "state",
                "target_field_id",
        }
        version_fields = (
            {"rule"}
            if contract_version == ENTITY_RESOLUTION_LEGACY_CONTRACT_VERSION
            else {"execution", "program", "quality"}
        )
        _fields(
            data,
            common_fields | version_fields,
            "entity-resolution candidate",
            optional={"identity_group", "revision", "self_match"},
        )
        graph = _object(data.get("graph"), "candidate graph")
        _fields(graph, {"name", "revision"}, "candidate graph")
        review_value = data.get("review")
        if review_value is not None and not isinstance(review_value, dict):
            raise EntityResolutionFailure(
                "invalid_entity_resolution",
                "Entity-resolution review must be an object or null.",
            )
        program_value = data.get("program")
        execution_value = data.get("execution")
        quality_value = data.get("quality")
        self_match_value = data.get("self_match")
        if self_match_value is not None and not isinstance(self_match_value, dict):
            raise EntityResolutionFailure(
                "invalid_entity_resolution", "self_match must be an object or null."
            )
        identity_group_value = data.get("identity_group")
        if identity_group_value is not None and not isinstance(identity_group_value, dict):
            raise EntityResolutionFailure(
                "invalid_entity_resolution", "identity_group must be an object or null."
            )
        try:
            identity_group = (
                EntityAliasGroup.from_dict(identity_group_value)
                if isinstance(identity_group_value, dict)
                else None
            )
        except IdentityFailure as exc:
            raise EntityResolutionFailure("invalid_entity_resolution", str(exc)) from exc
        candidate = cls(
            id=_identifier(data.get("id"), "candidate id"),
            graph_name=_text(graph.get("name"), "graph name"),
            graph_revision=_sha256(graph.get("revision"), "graph revision"),
            source_field_id=_text(data.get("source_field_id"), "source_field_id"),
            target_field_id=_text(data.get("target_field_id"), "target_field_id"),
            rule=(
                EntityResolutionRule.from_dict(_object(data.get("rule"), "rule"))
                if contract_version == ENTITY_RESOLUTION_LEGACY_CONTRACT_VERSION
                else None
            ),
            evidence=EntityResolutionEvidence.from_dict(
                _object(data.get("evidence"), "evidence")
            ),
            provenance=EntityResolutionProvenance.from_dict(
                _object(data.get("provenance"), "provenance")
            ),
            program=(
                DiscoveryProgram.from_dict(_object(program_value, "program"))
                if program_value is not None
                else None
            ),
            execution=(
                DiscoveryExecution.from_dict(_object(execution_value, "execution"))
                if execution_value is not None
                else None
            ),
            quality=(
                EntityResolutionQuality.from_dict(_object(quality_value, "quality"))
                if quality_value is not None
                else None
            ),
            self_match=(
                SelfEntityMatch.from_dict(self_match_value)
                if isinstance(self_match_value, dict)
                else None
            ),
            identity_group=identity_group,
            state=_choice(data.get("state"), "candidate state", ENTITY_RESOLUTION_STATES),
            review=EntityResolutionReview.from_dict(review_value) if review_value else None,
            contract_version=str(contract_version),
        )
        validate_entity_resolution_candidate(candidate)
        expected_revision = data.get("revision")
        if expected_revision is not None and expected_revision != candidate.revision:
            raise EntityResolutionFailure(
                "invalid_entity_resolution",
                "Entity-resolution candidate revision does not match its content.",
            )
        return candidate


@dataclass(frozen=True, slots=True)
class EntityResolutionMatch:
    candidate: EntityResolutionCandidate
    source_reference: str
    target_reference: str

    @property
    def usage(self) -> str:
        return "confirmed" if self.candidate.state == "reviewed" else "exploratory_only"

    @property
    def requires_runtime_validation(self) -> bool:
        return self.candidate.state != "reviewed"

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate": self.candidate.to_dict(include_identity_values=False),
            "requires_runtime_validation": self.requires_runtime_validation,
            "scope": "self_object" if self.candidate.self_match else "cross_object",
            "source": self.source_reference,
            "target": self.target_reference,
            "usage": self.usage,
            "warning": (
                None
                if self.candidate.state == "reviewed"
                else "Unreviewed hypothesis; probe it at runtime before presenting a result."
            ),
        }


@dataclass(frozen=True, slots=True)
class EntityAliasMatch:
    candidate_id: str
    group: EntityAliasGroup
    state: str
    object_reference: str
    record_key_field: str

    @property
    def usage(self) -> str:
        return "confirmed" if self.state == "reviewed" else "exploratory_only"

    @property
    def requires_runtime_validation(self) -> bool:
        return self.state != "reviewed"

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "group": self.group.to_dict(),
            "object": self.object_reference,
            "record_key_field": self.record_key_field,
            "requires_runtime_validation": self.requires_runtime_validation,
            "state": self.state,
            "usage": self.usage,
            "warning": (
                None
                if self.state == "reviewed"
                else "Unreviewed alias group; validate it before presenting a result."
            ),
        }


def validate_entity_resolution_candidate(candidate: EntityResolutionCandidate) -> None:
    if candidate.contract_version not in ENTITY_RESOLUTION_CONTRACT_VERSIONS:
        raise EntityResolutionFailure(
            "unsupported_entity_resolution",
            "Unsupported TAREL entity-resolution candidate contract.",
        )
    _identifier(candidate.id, "candidate id")
    _text(candidate.graph_name, "graph name")
    _sha256(candidate.graph_revision, "graph revision")
    if candidate.source_field_id == candidate.target_field_id and candidate.self_match is None:
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            "Equal entity-resolution endpoints require explicit self-entity semantics.",
        )
    if candidate.contract_version == ENTITY_RESOLUTION_LEGACY_CONTRACT_VERSION:
        if (
            candidate.rule is None
            or candidate.program is not None
            or candidate.execution is not None
            or candidate.quality is not None
            or candidate.self_match is not None
            or candidate.identity_group is not None
        ):
            raise EntityResolutionFailure(
                "invalid_entity_resolution",
                "Legacy candidates require only the normalized-exact rule.",
            )
        EntityResolutionRule.from_dict(candidate.rule.to_dict())
    else:
        if (
            candidate.rule is not None
            or candidate.program is None
            or candidate.execution is None
            or candidate.quality is None
        ):
            raise EntityResolutionFailure(
                "invalid_entity_resolution",
                "Discovery-derived candidates require program, execution, and quality.",
            )
        DiscoveryProgram.from_dict(candidate.program.to_dict())
        DiscoveryExecution.from_dict(candidate.execution.to_dict())
        EntityResolutionQuality.from_dict(candidate.quality.to_dict())
        if candidate.program.kind != "entity_matching":
            raise EntityResolutionFailure(
                "invalid_entity_resolution",
                "Entity-resolution programs must use entity-matching semantics.",
            )
        if (
            candidate.program.source_fields[0] != candidate.source_field_id
            or candidate.program.target_fields[0] != candidate.target_field_id
        ):
            raise EntityResolutionFailure(
                "invalid_entity_resolution",
                "Primary entity-resolution endpoints must match the first program field pair.",
            )
        if (candidate.program.self_match is None) != (candidate.self_match is None):
            raise EntityResolutionFailure(
                "invalid_entity_resolution",
                "Discovery and entity-resolution self-match semantics must agree.",
            )
        if candidate.self_match is not None:
            SelfEntityMatch.from_dict(candidate.self_match.to_dict())
            comparison_indexes = tuple(
                index
                for index in range(len(candidate.program.source_fields))
                if index not in candidate.program.contradiction_field_indexes
            )
            expected_comparison = tuple(
                candidate.program.source_fields[index]
                for index in comparison_indexes
            )
            expected_contradictions = tuple(
                candidate.program.source_fields[index]
                for index in candidate.program.contradiction_field_indexes
            )
            if (
                candidate.source_field_id != candidate.target_field_id
                or candidate.self_match.record_key_field_id
                != candidate.program.self_match.record_key_field
                or candidate.self_match.comparison_field_ids != expected_comparison
                or candidate.self_match.contradiction_field_ids
                != expected_contradictions
                or candidate.self_match.pair_policy
                != candidate.program.self_match.pair_policy
            ):
                raise EntityResolutionFailure(
                    "invalid_entity_resolution",
                    "Self-entity projection does not match its discovery program.",
                )
        if candidate.identity_group is not None:
            try:
                EntityAliasGroup.from_dict(candidate.identity_group.to_dict())
            except IdentityFailure as exc:
                raise EntityResolutionFailure(
                    "invalid_entity_resolution", str(exc)
                ) from exc
            if (
                candidate.self_match is None
                or candidate.program.comparison != "llm_assessed"
                or candidate.identity_group.candidate_id
                != candidate.provenance.discovery_candidate_id
                or not candidate.provenance.source_names
            ):
                raise EntityResolutionFailure(
                    "invalid_entity_resolution",
                    "Persisted alias groups require their LLM-assessed Self-Entity candidate "
                    "and explicit source provenance.",
                )
        elif candidate.program.comparison == "llm_assessed":
            raise EntityResolutionFailure(
                "invalid_entity_resolution",
                "LLM-assessed Self-Entity candidates require one concrete alias group.",
            )
        provenance = candidate.provenance
        if (
            provenance.discovery_candidate_id is None
            or provenance.discovery_run_revision is None
            or not provenance.observation_ids
            or provenance.promotion_reason is None
        ):
            raise EntityResolutionFailure(
                "invalid_entity_resolution",
                "Discovery-derived provenance is incomplete.",
            )
    EntityResolutionEvidence.from_dict(candidate.evidence.to_dict())
    EntityResolutionProvenance.from_dict(candidate.provenance.to_dict())
    if candidate.provenance.supersedes_candidate_id is not None and (
        candidate.self_match is None
        or candidate.provenance.supersedes_candidate_id == candidate.id
    ):
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            "Only Self-Entity evidence may supersede a different candidate.",
        )
    if candidate.state == "candidate" and candidate.review is not None:
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            "An unreviewed candidate cannot contain a human review.",
        )
    expected_decision = {"reviewed": "approve", "rejected": "reject"}.get(candidate.state)
    if expected_decision is not None and (
        candidate.review is None or candidate.review.decision != expected_decision
    ):
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            f"State {candidate.state} requires a matching human review.",
        )
    if candidate.review is not None:
        EntityResolutionReview.from_dict(candidate.review.to_dict())


def review_candidate(
    candidate: EntityResolutionCandidate,
    *,
    decision: str,
    reason: str,
) -> EntityResolutionCandidate:
    if candidate.state != "candidate":
        raise EntityResolutionFailure(
            "entity_resolution_already_reviewed",
            f"Entity-resolution candidate is already {candidate.state}: {candidate.id}",
        )
    review = EntityResolutionReview.from_dict(
        {"decision": decision, "reason": reason, "source": "human"}
    )
    changed = replace(
        candidate,
        state="reviewed" if decision == "approve" else "rejected",
        review=review,
    )
    validate_entity_resolution_candidate(changed)
    return changed


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


def _fields(
    data: dict[str, Any],
    required: set[str],
    label: str,
    *,
    optional: set[str] | None = None,
) -> None:
    allowed = required | (optional or set())
    if set(data) - allowed or required - set(data):
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            f"{label} has unexpected or missing fields.",
        )


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            f"{label} must be an object.",
        )
    return value


def _text(value: object, label: str, *, limit: int = 256) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            f"{label} must be a non-empty string of at most {limit} characters.",
        )
    return value.strip()


def _identifier(value: object, label: str) -> str:
    clean = _text(value, label, limit=128)
    if not _IDENTIFIER.fullmatch(clean):
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            f"{label} may contain letters, numbers, dots, underscores, and hyphens.",
        )
    return clean


def _sha256(value: object, label: str) -> str:
    clean = _text(value, label, limit=64)
    if not _SHA256.fullmatch(clean):
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            f"{label} must be a lowercase SHA-256 value.",
        )
    return clean


def _choice(value: object, label: str, choices: frozenset[str]) -> str:
    clean = _text(value, label)
    if clean not in choices:
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            f"Unsupported {label}: {clean}",
        )
    return clean


def _string_array(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            f"{label} must be an array of strings.",
        )
    return tuple(_text(item, label) for item in value)


def _identifier_array(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            f"{label} must be an array of identifiers.",
        )
    identifiers = tuple(_identifier(item, label) for item in value)
    if len(identifiers) != len(set(identifiers)):
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            f"{label} must contain unique identifiers.",
        )
    return identifiers


def entity_resolution_quality_rating(score: float) -> str:
    if score >= 0.9:
        return "strong"
    if score >= 0.7:
        return "moderate"
    if score >= 0.4:
        return "weak"
    return "insufficient"


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            f"{label} must be a non-negative integer.",
        )
    return value


def _rate(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            f"{label} must be a number between 0 and 1.",
        )
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            f"{label} must be a finite number between 0 and 1.",
        )
    return result
