"""Strict, value-free contracts for directed reference mappings."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from typing import Any

from tarel.discovery.contracts import (
    REFERENCE_MAPPING_CARDINALITIES,
    DiscoveryExecution,
    DiscoveryFailure,
    DiscoveryMetrics,
)
from tarel.discovery.contracts import ReferenceMappingProgram as ReferenceMappingProgram

REFERENCE_MAPPING_CONTRACT_VERSION = (
    "tarel.reference-mapping-candidate.v0.1.experimental"
)
REFERENCE_MAPPING_STATES = frozenset({"candidate", "rejected", "reviewed"})
REFERENCE_MAPPING_MODES = frozenset(
    {"confirmed_only", "confirmed_then_candidates", "include_candidates"}
)
_DISCOVERY_ACTORS = frozenset({"coding_agent", "human", "provider"})
_EVIDENCE_LEVELS = frozenset({"population_tested", "sample_tested"})
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_TEXT = 1_000


class ReferenceMappingFailure(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ReferenceMappingEvidence:
    phase: str
    observation_id: str
    level: str
    query_hash: str
    metrics: DiscoveryMetrics
    execution: DiscoveryExecution

    def to_dict(self) -> dict[str, object]:
        return {
            "execution": self.execution.to_dict(),
            "level": self.level,
            "metrics": self.metrics.to_dict(),
            "observation_id": self.observation_id,
            "phase": self.phase,
            "query_hash": self.query_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReferenceMappingEvidence:
        _fields(
            data,
            {
                "execution",
                "level",
                "metrics",
                "observation_id",
                "phase",
                "query_hash",
            },
            "reference-mapping evidence",
        )
        try:
            metrics = DiscoveryMetrics.from_dict(_object(data.get("metrics"), "metrics"))
            execution = DiscoveryExecution.from_dict(
                _object(data.get("execution"), "execution")
            )
        except DiscoveryFailure as exc:
            raise ReferenceMappingFailure(
                "invalid_reference_mapping", str(exc)
            ) from exc
        evidence = cls(
            phase=_choice(
                data.get("phase"), "evidence phase", frozenset({"challenge", "support"})
            ),
            observation_id=_identifier(
                data.get("observation_id"), "observation_id"
            ),
            level=_choice(data.get("level"), "evidence level", _EVIDENCE_LEVELS),
            query_hash=_sha256(data.get("query_hash"), "query_hash"),
            metrics=metrics,
            execution=execution,
        )
        if evidence.metrics.evaluated_count == 0:
            raise ReferenceMappingFailure(
                "invalid_reference_mapping",
                "Reference-mapping evidence must evaluate a non-empty population.",
            )
        if (
            evidence.metrics.collision_count is None
            or evidence.metrics.collision_rate is None
            or evidence.metrics.counterexample_count is None
        ):
            raise ReferenceMappingFailure(
                "invalid_reference_mapping",
                "Reference-mapping evidence requires measured collisions and counterexamples.",
            )
        return evidence


@dataclass(frozen=True, slots=True)
class ReferenceMappingProvenance:
    run_id: str
    run_revision: str
    discovery_candidate_id: str
    producer: str
    promotion_reason: str
    source_names: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "discovery_candidate_id": self.discovery_candidate_id,
            "producer": self.producer,
            "promotion_reason": self.promotion_reason,
            "run_id": self.run_id,
            "run_revision": self.run_revision,
            "source_names": list(self.source_names),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReferenceMappingProvenance:
        _fields(
            data,
            {
                "discovery_candidate_id",
                "producer",
                "promotion_reason",
                "run_id",
                "run_revision",
                "source_names",
            },
            "reference-mapping provenance",
        )
        return cls(
            run_id=_identifier(data.get("run_id"), "run_id"),
            run_revision=_sha256(data.get("run_revision"), "run_revision"),
            discovery_candidate_id=_identifier(
                data.get("discovery_candidate_id"), "discovery_candidate_id"
            ),
            producer=_choice(data.get("producer"), "producer", _DISCOVERY_ACTORS),
            promotion_reason=_text(
                data.get("promotion_reason"), "promotion_reason"
            ),
            source_names=_identifier_array(data.get("source_names"), "source_names"),
        )


@dataclass(frozen=True, slots=True)
class ReferenceMappingReview:
    decision: str
    reason: str
    source: str = "human"

    def to_dict(self) -> dict[str, str]:
        return {
            "decision": self.decision,
            "reason": self.reason,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReferenceMappingReview:
        _fields(data, {"decision", "reason", "source"}, "reference-mapping review")
        source = _text(data.get("source"), "review source")
        if source != "human":
            raise ReferenceMappingFailure(
                "invalid_reference_mapping",
                "Reference-mapping review source must be human.",
            )
        return cls(
            decision=_choice(
                data.get("decision"),
                "review decision",
                frozenset({"approve", "reject"}),
            ),
            reason=_text(data.get("reason"), "review reason"),
        )


@dataclass(frozen=True, slots=True)
class ReferenceMappingCandidate:
    id: str
    graph_name: str
    graph_revision: str
    source_field_id: str
    target_field_id: str
    cardinality: str
    mapping_manifest_hash: str
    mapping_count: int
    support_evidence: ReferenceMappingEvidence
    challenge_evidence: ReferenceMappingEvidence
    provenance: ReferenceMappingProvenance
    state: str = "candidate"
    review: ReferenceMappingReview | None = None
    contract_version: str = REFERENCE_MAPPING_CONTRACT_VERSION

    @property
    def revision(self) -> str:
        encoded = json.dumps(
            self.to_dict(include_revision=False),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def to_dict(self, *, include_revision: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "cardinality": self.cardinality,
            "challenge_evidence": self.challenge_evidence.to_dict(),
            "contract_version": self.contract_version,
            "graph": {"name": self.graph_name, "revision": self.graph_revision},
            "id": self.id,
            "mapping_count": self.mapping_count,
            "mapping_manifest_hash": self.mapping_manifest_hash,
            "provenance": self.provenance.to_dict(),
            "review": self.review.to_dict() if self.review else None,
            "source_field_id": self.source_field_id,
            "state": self.state,
            "support_evidence": self.support_evidence.to_dict(),
            "target_field_id": self.target_field_id,
        }
        if include_revision:
            payload["revision"] = self.revision
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReferenceMappingCandidate:
        _fields(
            data,
            {
                "cardinality",
                "challenge_evidence",
                "contract_version",
                "graph",
                "id",
                "mapping_count",
                "mapping_manifest_hash",
                "provenance",
                "review",
                "source_field_id",
                "state",
                "support_evidence",
                "target_field_id",
            },
            "reference-mapping candidate",
            optional={"revision"},
        )
        if data.get("contract_version") != REFERENCE_MAPPING_CONTRACT_VERSION:
            raise ReferenceMappingFailure(
                "unsupported_reference_mapping",
                "Unsupported TAREL reference-mapping candidate contract.",
            )
        graph = _object(data.get("graph"), "candidate graph")
        _fields(graph, {"name", "revision"}, "candidate graph")
        review_value = data.get("review")
        if review_value is not None and not isinstance(review_value, dict):
            raise ReferenceMappingFailure(
                "invalid_reference_mapping", "review must be an object or null."
            )
        candidate = cls(
            id=_identifier(data.get("id"), "candidate id"),
            graph_name=_text(graph.get("name"), "graph name"),
            graph_revision=_sha256(graph.get("revision"), "graph revision"),
            source_field_id=_text(data.get("source_field_id"), "source_field_id"),
            target_field_id=_text(data.get("target_field_id"), "target_field_id"),
            cardinality=_choice(
                data.get("cardinality"),
                "cardinality",
                REFERENCE_MAPPING_CARDINALITIES,
            ),
            mapping_manifest_hash=_sha256(
                data.get("mapping_manifest_hash"), "mapping_manifest_hash"
            ),
            mapping_count=_bounded_integer(
                data.get("mapping_count"), "mapping_count", 1, 1_000_000_000
            ),
            support_evidence=ReferenceMappingEvidence.from_dict(
                _object(data.get("support_evidence"), "support_evidence")
            ),
            challenge_evidence=ReferenceMappingEvidence.from_dict(
                _object(data.get("challenge_evidence"), "challenge_evidence")
            ),
            provenance=ReferenceMappingProvenance.from_dict(
                _object(data.get("provenance"), "provenance")
            ),
            state=_choice(
                data.get("state"), "state", REFERENCE_MAPPING_STATES
            ),
            review=(
                ReferenceMappingReview.from_dict(review_value)
                if isinstance(review_value, dict)
                else None
            ),
        )
        validate_reference_mapping_candidate(candidate)
        expected_revision = data.get("revision")
        if expected_revision is not None and expected_revision != candidate.revision:
            raise ReferenceMappingFailure(
                "invalid_reference_mapping",
                "Reference-mapping candidate revision does not match its content.",
            )
        return candidate


@dataclass(frozen=True, slots=True)
class ReferenceMappingMatch:
    candidate: ReferenceMappingCandidate
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
            "candidate": self.candidate.to_dict(),
            "direction": "source_to_target",
            "requires_runtime_validation": self.requires_runtime_validation,
            "source": self.source_reference,
            "target": self.target_reference,
            "usage": self.usage,
            "warning": (
                None
                if self.candidate.state == "reviewed"
                else "Unreviewed reference mapping; validate it at runtime before use."
            ),
        }


def validate_reference_mapping_candidate(candidate: ReferenceMappingCandidate) -> None:
    if candidate.contract_version != REFERENCE_MAPPING_CONTRACT_VERSION:
        raise ReferenceMappingFailure(
            "unsupported_reference_mapping",
            "Unsupported TAREL reference-mapping candidate contract.",
        )
    _identifier(candidate.id, "candidate id")
    _text(candidate.graph_name, "graph name")
    _sha256(candidate.graph_revision, "graph revision")
    _text(candidate.source_field_id, "source_field_id")
    _text(candidate.target_field_id, "target_field_id")
    if candidate.source_field_id == candidate.target_field_id:
        raise ReferenceMappingFailure(
            "invalid_reference_mapping",
            "Reference mappings require different directed source and target fields.",
        )
    _choice(candidate.cardinality, "cardinality", REFERENCE_MAPPING_CARDINALITIES)
    _sha256(candidate.mapping_manifest_hash, "mapping_manifest_hash")
    _bounded_integer(candidate.mapping_count, "mapping_count", 1, 1_000_000_000)
    support = ReferenceMappingEvidence.from_dict(candidate.support_evidence.to_dict())
    challenge = ReferenceMappingEvidence.from_dict(candidate.challenge_evidence.to_dict())
    if support.phase != "support" or challenge.phase != "challenge":
        raise ReferenceMappingFailure(
            "invalid_reference_mapping",
            "Reference mappings require distinct support and challenge evidence.",
        )
    if (
        support.observation_id == challenge.observation_id
        or support.query_hash == challenge.query_hash
    ):
        raise ReferenceMappingFailure(
            "invalid_reference_mapping",
            "Support and challenge must be independent observations.",
        )
    ReferenceMappingProvenance.from_dict(candidate.provenance.to_dict())
    if candidate.state == "candidate" and candidate.review is not None:
        raise ReferenceMappingFailure(
            "invalid_reference_mapping",
            "An unreviewed reference-mapping candidate cannot contain a review.",
        )
    expected_decision = {"reviewed": "approve", "rejected": "reject"}.get(
        candidate.state
    )
    if expected_decision is not None and (
        candidate.review is None or candidate.review.decision != expected_decision
    ):
        raise ReferenceMappingFailure(
            "invalid_reference_mapping",
            f"State {candidate.state} requires a matching human review.",
        )
    if candidate.review is not None:
        ReferenceMappingReview.from_dict(candidate.review.to_dict())


def review_reference_mapping_candidate(
    candidate: ReferenceMappingCandidate,
    *,
    decision: str,
    reason: str,
) -> ReferenceMappingCandidate:
    if candidate.state != "candidate":
        raise ReferenceMappingFailure(
            "reference_mapping_already_reviewed",
            f"Reference-mapping candidate is already {candidate.state}: {candidate.id}",
        )
    review = ReferenceMappingReview.from_dict(
        {"decision": decision, "reason": reason, "source": "human"}
    )
    changed = replace(
        candidate,
        state="reviewed" if review.decision == "approve" else "rejected",
        review=review,
    )
    validate_reference_mapping_candidate(changed)
    return changed


def _fields(
    data: dict[str, Any],
    required: set[str],
    label: str,
    *,
    optional: set[str] | None = None,
) -> None:
    allowed = required | (optional or set())
    if set(data) - allowed or required - set(data):
        raise ReferenceMappingFailure(
            "invalid_reference_mapping", f"{label} has unexpected or missing fields."
        )


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReferenceMappingFailure(
            "invalid_reference_mapping", f"{label} must be an object."
        )
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > _MAX_TEXT:
        raise ReferenceMappingFailure(
            "invalid_reference_mapping",
            f"{label} must be a non-empty string of at most {_MAX_TEXT} characters.",
        )
    return value.strip()


def _choice(value: object, label: str, choices: frozenset[str]) -> str:
    if not isinstance(value, str) or value not in choices:
        raise ReferenceMappingFailure(
            "invalid_reference_mapping", f"Unsupported {label}."
        )
    return value


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ReferenceMappingFailure(
            "invalid_reference_mapping", f"{label} has an invalid identifier."
        )
    return value


def _identifier_array(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ReferenceMappingFailure(
            "invalid_reference_mapping", f"{label} must be an array."
        )
    result = tuple(_identifier(item, label) for item in value)
    if len(result) != len(set(result)):
        raise ReferenceMappingFailure(
            "invalid_reference_mapping", f"{label} must contain unique identifiers."
        )
    return result


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ReferenceMappingFailure(
            "invalid_reference_mapping", f"{label} must be a lowercase SHA-256 hash."
        )
    return value


def _bounded_integer(value: object, label: str, minimum: int, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        raise ReferenceMappingFailure(
            "invalid_reference_mapping",
            f"{label} must be between {minimum} and {maximum}.",
        )
    return value
