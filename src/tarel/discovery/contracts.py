"""Experimental contracts for bounded, agent-driven discovery loops."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, replace
from typing import Any

from tarel.discovery.coverage import DISCOVERY_SCOPE_MODES
from tarel.discovery.identity import (
    IDENTITY_ACTIONS,
    EntityGroupReflection,
    IdentityFailure,
    IdentityInspection,
    add_group,
    add_manifest,
    add_page,
    add_reflection,
)

DISCOVERY_CONTRACT_VERSION = "tarel.discovery-run.v0.1.experimental"
DISCOVERY_KINDS = frozenset({"entity_matching", "join_discovery"})
DISCOVERY_STATUSES = frozenset({"completed", "open", "paused"})
DISCOVERY_ACTORS = frozenset({"coding_agent", "human", "provider"})
DISCOVERY_ACTIONS = frozenset(
    {
        "complete_run",
        "pause_run",
        "propose_candidate",
        "record_observation",
        "reject_candidate",
        "resume_run",
        "select_candidate",
        *IDENTITY_ACTIONS,
    }
)
DISCOVERY_CANDIDATE_STATES = frozenset(
    {"challenged", "proposed", "rejected", "selected", "tested"}
)
DISCOVERY_COMPARISONS = frozenset(
    {
        "exact",
        "llm_assessed",
        "normalized_exact",
        "normalized_levenshtein_v1",
        "token_set_ratio_v1",
    }
)
DISCOVERY_TRANSFORMS = frozenset(
    {
        "casefold",
        "collapse_whitespace",
        "fixed_segment",
        "strip_numeric_prefix",
        "strip_punctuation",
        "trim",
        "unicode_nfkc",
    }
)
DISCOVERY_EVIDENCE_LEVELS = frozenset({"population_tested", "sample_tested"})
DISCOVERY_OBSERVATION_PHASES = frozenset({"challenge", "support"})
DISCOVERY_OBSERVATION_STATUSES = frozenset({"failed", "succeeded"})
DISCOVERY_METRIC_BASES = frozenset({"pairs", "population", "source_distinct"})
DISCOVERY_BLOCKING_STRATEGIES = frozenset(
    {
        "exact_value",
        "full_scan_bounded",
        "ngram",
        "normalized_prefix",
        "phonetic",
        "token_prefix",
    }
)
DISCOVERY_SELF_PAIR_POLICIES = frozenset({"distinct_unordered"})

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DIALECT = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_MAX_TEXT = 1_000
_MAX_FIELDS = 3
_MAX_TRANSFORMS = 8
_MAX_PARENTS = 4
_MAX_CANDIDATES = 200
_MAX_PROBES = 1_000


class DiscoveryFailure(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class DiscoveryTransform:
    kind: str
    start: int | None = None
    length: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {"kind": self.kind, "length": self.length, "start": self.start}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscoveryTransform:
        _fields(data, {"kind", "length", "start"}, "discovery transform")
        transform = cls(
            kind=_choice(data.get("kind"), "transform kind", DISCOVERY_TRANSFORMS),
            start=_optional_integer(data.get("start"), "transform start"),
            length=_optional_integer(data.get("length"), "transform length"),
        )
        if transform.kind == "fixed_segment":
            if transform.start is None or transform.length is None or transform.length < 1:
                raise DiscoveryFailure(
                    "invalid_discovery",
                    "fixed_segment requires a non-negative start and a positive length.",
                )
        elif transform.start is not None or transform.length is not None:
            raise DiscoveryFailure(
                "invalid_discovery",
                "Only fixed_segment accepts start and length parameters.",
            )
        return transform


@dataclass(frozen=True, slots=True)
class DiscoverySelfMatch:
    """Record identity semantics for comparisons within one graph object."""

    record_key_field: str
    pair_policy: str = "distinct_unordered"

    def to_dict(self) -> dict[str, str]:
        return {
            "pair_policy": self.pair_policy,
            "record_key_field": self.record_key_field,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscoverySelfMatch:
        _fields(data, {"pair_policy", "record_key_field"}, "self-match program")
        return cls(
            record_key_field=_text(data.get("record_key_field"), "record_key_field"),
            pair_policy=_choice(
                data.get("pair_policy"),
                "self-match pair policy",
                DISCOVERY_SELF_PAIR_POLICIES,
            ),
        )


@dataclass(frozen=True, slots=True)
class DiscoveryProgram:
    kind: str
    source_fields: tuple[str, ...]
    target_fields: tuple[str, ...]
    source_transforms: tuple[tuple[DiscoveryTransform, ...], ...]
    target_transforms: tuple[tuple[DiscoveryTransform, ...], ...]
    comparison: str
    blocking_field_indexes: tuple[int, ...]
    contradiction_field_indexes: tuple[int, ...]
    threshold: float | None = None
    self_match: DiscoverySelfMatch | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "blocking_field_indexes": list(self.blocking_field_indexes),
            "comparison": self.comparison,
            "contradiction_field_indexes": list(self.contradiction_field_indexes),
            "kind": self.kind,
            "source_fields": list(self.source_fields),
            "source_transforms": [
                [transform.to_dict() for transform in transforms]
                for transforms in self.source_transforms
            ],
            "target_fields": list(self.target_fields),
            "target_transforms": [
                [transform.to_dict() for transform in transforms]
                for transforms in self.target_transforms
            ],
            "threshold": self.threshold,
        }
        if self.self_match is not None:
            payload["self_match"] = self.self_match.to_dict()
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscoveryProgram:
        _fields(
            data,
            {
                "blocking_field_indexes",
                "comparison",
                "contradiction_field_indexes",
                "kind",
                "source_fields",
                "source_transforms",
                "target_fields",
                "target_transforms",
                "threshold",
            },
            "discovery program",
            optional={"self_match"},
        )
        self_match = data.get("self_match")
        if self_match is not None and not isinstance(self_match, dict):
            raise DiscoveryFailure(
                "invalid_discovery", "self_match must be an object or null."
            )
        program = cls(
            kind=_choice(data.get("kind"), "discovery kind", DISCOVERY_KINDS),
            source_fields=_string_array(data.get("source_fields"), "source_fields"),
            target_fields=_string_array(data.get("target_fields"), "target_fields"),
            source_transforms=_transform_matrix(
                data.get("source_transforms"), "source_transforms"
            ),
            target_transforms=_transform_matrix(
                data.get("target_transforms"), "target_transforms"
            ),
            comparison=_choice(
                data.get("comparison"), "comparison", DISCOVERY_COMPARISONS
            ),
            blocking_field_indexes=_integer_array(
                data.get("blocking_field_indexes"), "blocking_field_indexes"
            ),
            contradiction_field_indexes=_integer_array(
                data.get("contradiction_field_indexes"),
                "contradiction_field_indexes",
            ),
            threshold=_optional_rate(data.get("threshold"), "threshold"),
            self_match=(
                DiscoverySelfMatch.from_dict(self_match)
                if isinstance(self_match, dict)
                else None
            ),
        )
        validate_discovery_program(program)
        return program


@dataclass(frozen=True, slots=True)
class DiscoveryMetrics:
    basis: str
    evaluated_count: int
    matched_count: int
    distinct_source_count: int
    distinct_target_count: int
    collision_count: int | None
    counterexample_count: int | None
    coverage: float
    collision_rate: float | None
    confidence: float

    def to_dict(self) -> dict[str, object]:
        return {
            "basis": self.basis,
            "collision_count": self.collision_count,
            "collision_rate": self.collision_rate,
            "confidence": self.confidence,
            "counterexample_count": self.counterexample_count,
            "coverage": self.coverage,
            "distinct_source_count": self.distinct_source_count,
            "distinct_target_count": self.distinct_target_count,
            "evaluated_count": self.evaluated_count,
            "matched_count": self.matched_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscoveryMetrics:
        _fields(
            data,
            {
                "basis",
                "collision_count",
                "collision_rate",
                "confidence",
                "counterexample_count",
                "coverage",
                "distinct_source_count",
                "distinct_target_count",
                "evaluated_count",
                "matched_count",
            },
            "discovery metrics",
        )
        metrics = cls(
            basis=_choice(data.get("basis"), "metric basis", DISCOVERY_METRIC_BASES),
            evaluated_count=_integer(data.get("evaluated_count"), "evaluated_count"),
            matched_count=_integer(data.get("matched_count"), "matched_count"),
            distinct_source_count=_integer(
                data.get("distinct_source_count"), "distinct_source_count"
            ),
            distinct_target_count=_integer(
                data.get("distinct_target_count"), "distinct_target_count"
            ),
            collision_count=_optional_integer(
                data.get("collision_count"), "collision_count"
            ),
            counterexample_count=_optional_integer(
                data.get("counterexample_count"), "counterexample_count"
            ),
            coverage=_rate(data.get("coverage"), "coverage"),
            collision_rate=_optional_rate(data.get("collision_rate"), "collision_rate"),
            confidence=_rate(data.get("confidence"), "confidence"),
        )
        if metrics.matched_count > metrics.evaluated_count:
            raise DiscoveryFailure(
                "invalid_discovery", "matched_count cannot exceed evaluated_count."
            )
        if (
            metrics.collision_count is not None
            and metrics.collision_count > metrics.matched_count
        ):
            raise DiscoveryFailure(
                "invalid_discovery", "collision_count cannot exceed matched_count."
            )
        if (
            metrics.counterexample_count is not None
            and metrics.counterexample_count > metrics.evaluated_count
        ):
            raise DiscoveryFailure(
                "invalid_discovery", "counterexample_count cannot exceed evaluated_count."
            )
        expected_coverage = metrics.matched_count / max(1, metrics.evaluated_count)
        expected_collision_rate = (
            metrics.collision_count / max(1, metrics.matched_count)
            if metrics.collision_count is not None
            else None
        )
        if not math.isclose(metrics.coverage, expected_coverage, abs_tol=1e-6):
            raise DiscoveryFailure(
                "invalid_discovery",
                "coverage does not match matched_count / evaluated_count.",
            )
        if (metrics.collision_rate is None) != (expected_collision_rate is None) or (
            metrics.collision_rate is not None
            and expected_collision_rate is not None
            and not math.isclose(
                metrics.collision_rate, expected_collision_rate, abs_tol=1e-6
            )
        ):
            raise DiscoveryFailure(
                "invalid_discovery",
                "collision_rate does not match collision_count / matched_count.",
            )
        return metrics


@dataclass(frozen=True, slots=True)
class DiscoveryExecution:
    executor_id: str
    executor_version: str
    artifact_hash: str
    blocking_strategy: str
    blocking_version: str

    def to_dict(self) -> dict[str, str]:
        return {
            "artifact_hash": self.artifact_hash,
            "blocking_strategy": self.blocking_strategy,
            "blocking_version": self.blocking_version,
            "executor_id": self.executor_id,
            "executor_version": self.executor_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscoveryExecution:
        _fields(
            data,
            {
                "artifact_hash",
                "blocking_strategy",
                "blocking_version",
                "executor_id",
                "executor_version",
            },
            "discovery execution",
        )
        return cls(
            executor_id=_identifier(data.get("executor_id"), "executor_id"),
            executor_version=_identifier(
                data.get("executor_version"), "executor_version"
            ),
            artifact_hash=_sha256(data.get("artifact_hash"), "artifact_hash"),
            blocking_strategy=_choice(
                data.get("blocking_strategy"),
                "blocking_strategy",
                DISCOVERY_BLOCKING_STRATEGIES,
            ),
            blocking_version=_identifier(
                data.get("blocking_version"), "blocking_version"
            ),
        )


@dataclass(frozen=True, slots=True)
class DiscoveryObservation:
    id: str
    phase: str
    status: str
    evidence_level: str
    dialect: str
    query_hash: str
    row_limit: int
    truncated: bool
    duration_ms: int
    metrics: DiscoveryMetrics | None = None
    error_category: str | None = None
    execution: DiscoveryExecution | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "dialect": self.dialect,
            "duration_ms": self.duration_ms,
            "error_category": self.error_category,
            "evidence_level": self.evidence_level,
            "id": self.id,
            "metrics": self.metrics.to_dict() if self.metrics else None,
            "phase": self.phase,
            "query_hash": self.query_hash,
            "row_limit": self.row_limit,
            "status": self.status,
            "truncated": self.truncated,
        }
        if self.execution is not None:
            payload["execution"] = self.execution.to_dict()
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscoveryObservation:
        _fields(
            data,
            {
                "dialect",
                "duration_ms",
                "error_category",
                "evidence_level",
                "id",
                "metrics",
                "phase",
                "query_hash",
                "row_limit",
                "status",
                "truncated",
            },
            "discovery observation",
            optional={"execution"},
        )
        metrics_value = data.get("metrics")
        if metrics_value is not None and not isinstance(metrics_value, dict):
            raise DiscoveryFailure("invalid_discovery", "metrics must be an object or null.")
        execution_value = data.get("execution")
        if execution_value is not None and not isinstance(execution_value, dict):
            raise DiscoveryFailure(
                "invalid_discovery", "execution must be an object or null."
            )
        observation = cls(
            id=_identifier(data.get("id"), "observation id"),
            phase=_choice(
                data.get("phase"), "observation phase", DISCOVERY_OBSERVATION_PHASES
            ),
            status=_choice(
                data.get("status"), "observation status", DISCOVERY_OBSERVATION_STATUSES
            ),
            evidence_level=_choice(
                data.get("evidence_level"),
                "evidence level",
                DISCOVERY_EVIDENCE_LEVELS,
            ),
            dialect=_pattern(data.get("dialect"), "dialect", _DIALECT),
            query_hash=_sha256(data.get("query_hash"), "query_hash"),
            row_limit=_bounded_integer(data.get("row_limit"), "row_limit", 1, 1_000_000),
            truncated=_boolean(data.get("truncated"), "truncated"),
            duration_ms=_bounded_integer(
                data.get("duration_ms"), "duration_ms", 0, 86_400_000
            ),
            metrics=DiscoveryMetrics.from_dict(metrics_value) if metrics_value else None,
            error_category=_optional_identifier(
                data.get("error_category"), "error_category"
            ),
            execution=(
                DiscoveryExecution.from_dict(execution_value)
                if execution_value is not None
                else None
            ),
        )
        if observation.status == "succeeded" and observation.metrics is None:
            raise DiscoveryFailure(
                "invalid_discovery", "Successful observations require aggregate metrics."
            )
        if observation.status == "succeeded" and observation.error_category is not None:
            raise DiscoveryFailure(
                "invalid_discovery", "Successful observations cannot contain an error category."
            )
        if observation.status == "failed" and observation.error_category is None:
            raise DiscoveryFailure(
                "invalid_discovery", "Failed observations require a sanitized error category."
            )
        if observation.status == "failed" and observation.metrics is not None:
            raise DiscoveryFailure(
                "invalid_discovery", "Failed observations cannot claim aggregate metrics."
            )
        if observation.truncated and observation.evidence_level == "population_tested":
            raise DiscoveryFailure(
                "invalid_discovery",
                "Truncated observations cannot claim population-tested evidence.",
            )
        return observation


@dataclass(frozen=True, slots=True)
class DiscoveryCandidate:
    id: str
    kind: str
    generation: int
    parent_ids: tuple[str, ...]
    variation_operator: str
    program: DiscoveryProgram
    state: str = "proposed"
    observations: tuple[DiscoveryObservation, ...] = ()
    assessment_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "assessment_reason": self.assessment_reason,
            "generation": self.generation,
            "id": self.id,
            "kind": self.kind,
            "observations": [item.to_dict() for item in self.observations],
            "parent_ids": list(self.parent_ids),
            "program": self.program.to_dict(),
            "state": self.state,
            "variation_operator": self.variation_operator,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscoveryCandidate:
        _fields(
            data,
            {
                "assessment_reason",
                "generation",
                "id",
                "kind",
                "observations",
                "parent_ids",
                "program",
                "state",
                "variation_operator",
            },
            "discovery candidate",
        )
        observations = data.get("observations")
        if not isinstance(observations, list) or any(
            not isinstance(item, dict) for item in observations
        ):
            raise DiscoveryFailure(
                "invalid_discovery", "candidate observations must be an array of objects."
            )
        candidate = cls(
            id=_identifier(data.get("id"), "candidate id"),
            kind=_choice(data.get("kind"), "discovery kind", DISCOVERY_KINDS),
            generation=_bounded_integer(data.get("generation"), "generation", 0, 10_000),
            parent_ids=_identifier_array(data.get("parent_ids"), "parent_ids"),
            variation_operator=_identifier(
                data.get("variation_operator"), "variation_operator"
            ),
            program=DiscoveryProgram.from_dict(_object(data.get("program"), "program")),
            state=_choice(
                data.get("state"), "candidate state", DISCOVERY_CANDIDATE_STATES
            ),
            observations=tuple(DiscoveryObservation.from_dict(item) for item in observations),
            assessment_reason=_optional_text(
                data.get("assessment_reason"), "assessment_reason"
            ),
        )
        if candidate.kind != candidate.program.kind:
            raise DiscoveryFailure(
                "invalid_discovery", "Candidate and program discovery kinds must match."
            )
        if len(candidate.parent_ids) > _MAX_PARENTS or len(candidate.parent_ids) != len(
            set(candidate.parent_ids)
        ):
            raise DiscoveryFailure(
                "invalid_discovery", "Candidates accept at most four unique parents."
            )
        observation_ids = [item.id for item in candidate.observations]
        if len(observation_ids) != len(set(observation_ids)):
            raise DiscoveryFailure(
                "invalid_discovery", "Candidate observation IDs must be unique."
            )
        has_support = any(item.phase == "support" for item in candidate.observations)
        has_challenge = any(item.phase == "challenge" for item in candidate.observations)
        if candidate.state == "proposed" and candidate.observations:
            raise DiscoveryFailure(
                "invalid_discovery", "Proposed candidates cannot contain observations."
            )
        if candidate.state == "tested" and not has_support:
            raise DiscoveryFailure(
                "invalid_discovery", "Tested candidates require a support observation."
            )
        if candidate.state in {"challenged", "selected", "rejected"} and not has_challenge:
            raise DiscoveryFailure(
                "invalid_discovery", "Assessed candidates require a challenge observation."
            )
        if candidate.state in {"selected", "rejected"} and not candidate.assessment_reason:
            raise DiscoveryFailure(
                "invalid_discovery", "Terminal candidates require an assessment reason."
            )
        if candidate.state == "selected" and not any(
            item.phase == "challenge" and item.status == "succeeded"
            for item in candidate.observations
        ):
            raise DiscoveryFailure(
                "invalid_discovery", "Selected candidates require a successful challenge probe."
            )
        return candidate


@dataclass(frozen=True, slots=True)
class DiscoveryStep:
    sequence: int
    actor: str
    action: str
    candidate_id: str | None
    observation_id: str | None
    note: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action,
            "actor": self.actor,
            "candidate_id": self.candidate_id,
            "note": self.note,
            "observation_id": self.observation_id,
            "sequence": self.sequence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscoveryStep:
        _fields(
            data,
            {"action", "actor", "candidate_id", "note", "observation_id", "sequence"},
            "discovery step",
        )
        return cls(
            sequence=_bounded_integer(data.get("sequence"), "sequence", 1, 100_000),
            actor=_choice(data.get("actor"), "actor", DISCOVERY_ACTORS),
            action=_choice(data.get("action"), "action", DISCOVERY_ACTIONS),
            candidate_id=_optional_identifier(data.get("candidate_id"), "candidate_id"),
            observation_id=_optional_identifier(
                data.get("observation_id"), "observation_id"
            ),
            note=_optional_text(data.get("note"), "note"),
        )


@dataclass(frozen=True, slots=True)
class DiscoveryRun:
    id: str
    kind: str
    graph_name: str
    graph_revision: str
    source_names: tuple[str, ...]
    question: str | None
    actor_mode: str
    advisor_provider: str | None
    probe_budget: int
    candidate_budget: int
    status: str = "open"
    candidates: tuple[DiscoveryCandidate, ...] = ()
    steps: tuple[DiscoveryStep, ...] = ()
    completion_reason: str | None = None
    identity_inspection: IdentityInspection | None = None
    scope_mode: str | None = None
    contract_version: str = DISCOVERY_CONTRACT_VERSION

    @property
    def probes_used(self) -> int:
        return sum(len(candidate.observations) for candidate in self.candidates)

    @property
    def revision(self) -> str:
        encoded = json.dumps(
            self.to_dict(include_revision=False),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def to_dict(
        self,
        *,
        include_revision: bool = True,
        include_identity_values: bool = True,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "actor_mode": self.actor_mode,
            "advisor_provider": self.advisor_provider,
            "candidate_budget": self.candidate_budget,
            "candidates": [item.to_dict() for item in self.candidates],
            "completion_reason": self.completion_reason,
            "contract_version": self.contract_version,
            "graph": {"name": self.graph_name, "revision": self.graph_revision},
            "id": self.id,
            "kind": self.kind,
            "probe_budget": self.probe_budget,
            "question": self.question,
            "source_names": list(self.source_names),
            "status": self.status,
            "steps": [item.to_dict() for item in self.steps],
        }
        if include_revision:
            payload["revision"] = self.revision
        if self.identity_inspection is not None:
            payload["identity_inspection"] = self.identity_inspection.to_dict(
                include_values=include_identity_values
            )
        if self.scope_mode is not None:
            payload["scope_mode"] = self.scope_mode
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscoveryRun:
        _fields(
            data,
            {
                "actor_mode",
                "advisor_provider",
                "candidate_budget",
                "candidates",
                "completion_reason",
                "contract_version",
                "graph",
                "id",
                "kind",
                "probe_budget",
                "question",
                "source_names",
                "status",
                "steps",
            },
            "discovery run",
            optional={"identity_inspection", "revision", "scope_mode"},
        )
        if data.get("contract_version") != DISCOVERY_CONTRACT_VERSION:
            raise DiscoveryFailure(
                "unsupported_discovery", "Unsupported TAREL discovery-run contract."
            )
        graph = _object(data.get("graph"), "graph")
        _fields(graph, {"name", "revision"}, "discovery graph")
        candidates = data.get("candidates")
        steps = data.get("steps")
        if not isinstance(candidates, list) or any(
            not isinstance(item, dict) for item in candidates
        ):
            raise DiscoveryFailure(
                "invalid_discovery", "run candidates must be an array of objects."
            )
        if not isinstance(steps, list) or any(not isinstance(item, dict) for item in steps):
            raise DiscoveryFailure(
                "invalid_discovery", "run steps must be an array of objects."
            )
        inspection_value = data.get("identity_inspection")
        if inspection_value is not None and not isinstance(inspection_value, dict):
            raise DiscoveryFailure(
                "invalid_discovery", "identity_inspection must be an object or null."
            )
        try:
            identity_inspection = (
                IdentityInspection.from_dict(inspection_value)
                if isinstance(inspection_value, dict)
                else None
            )
        except IdentityFailure as exc:
            raise DiscoveryFailure(exc.code, str(exc)) from exc
        run = cls(
            id=_identifier(data.get("id"), "run id"),
            kind=_choice(data.get("kind"), "discovery kind", DISCOVERY_KINDS),
            graph_name=_text(graph.get("name"), "graph name"),
            graph_revision=_sha256(graph.get("revision"), "graph revision"),
            source_names=_identifier_array(data.get("source_names"), "source_names"),
            question=_optional_text(data.get("question"), "question"),
            actor_mode=_choice(
                data.get("actor_mode"),
                "actor mode",
                frozenset({"agent", "agent_with_provider_advisor"}),
            ),
            advisor_provider=_optional_identifier(
                data.get("advisor_provider"), "advisor_provider"
            ),
            probe_budget=_bounded_integer(
                data.get("probe_budget"), "probe_budget", 1, _MAX_PROBES
            ),
            candidate_budget=_bounded_integer(
                data.get("candidate_budget"), "candidate_budget", 1, _MAX_CANDIDATES
            ),
            status=_choice(data.get("status"), "run status", DISCOVERY_STATUSES),
            candidates=tuple(DiscoveryCandidate.from_dict(item) for item in candidates),
            steps=tuple(DiscoveryStep.from_dict(item) for item in steps),
            completion_reason=_optional_text(
                data.get("completion_reason"), "completion_reason"
            ),
            identity_inspection=identity_inspection,
            scope_mode=(
                _choice(data.get("scope_mode"), "scope_mode", DISCOVERY_SCOPE_MODES)
                if data.get("scope_mode") is not None
                else None
            ),
        )
        validate_discovery_run(run)
        expected_revision = data.get("revision")
        if expected_revision is not None and expected_revision != run.revision:
            raise DiscoveryFailure(
                "invalid_discovery", "Discovery run revision does not match its content."
            )
        return run


def validate_discovery_program(program: DiscoveryProgram) -> None:
    if not 1 <= len(program.source_fields) <= _MAX_FIELDS:
        raise DiscoveryFailure(
            "invalid_discovery", "Discovery programs require between one and three fields."
        )
    if len(program.source_fields) != len(program.target_fields):
        raise DiscoveryFailure(
            "invalid_discovery", "Source and target field counts must match."
        )
    if len(program.source_fields) != len(program.source_transforms) or len(
        program.target_fields
    ) != len(program.target_transforms):
        raise DiscoveryFailure(
            "invalid_discovery", "Each field requires one transform list."
        )
    if len(set(program.source_fields)) != len(program.source_fields) or len(
        set(program.target_fields)
    ) != len(program.target_fields):
        raise DiscoveryFailure("invalid_discovery", "Program field references must be unique.")
    indexes = set(range(len(program.source_fields)))
    blocking = set(program.blocking_field_indexes)
    contradictions = set(program.contradiction_field_indexes)
    if not blocking.issubset(indexes) or not contradictions.issubset(indexes):
        raise DiscoveryFailure(
            "invalid_discovery", "Program field indexes must reference supplied field pairs."
        )
    if blocking & contradictions:
        raise DiscoveryFailure(
            "invalid_discovery", "Blocking and contradiction field indexes must be disjoint."
        )
    if program.kind == "join_discovery" and (blocking or contradictions):
        raise DiscoveryFailure(
            "invalid_discovery", "Join programs do not accept entity blocking or guards."
        )
    if program.kind == "join_discovery" and program.self_match is not None:
        raise DiscoveryFailure(
            "invalid_discovery", "Join programs do not accept self-entity semantics."
        )
    if program.kind == "join_discovery" and program.source_fields == program.target_fields:
        raise DiscoveryFailure(
            "invalid_discovery", "Join programs require different source and target fields."
        )
    if program.kind == "entity_matching":
        comparison_indexes = indexes - contradictions
        if not comparison_indexes:
            raise DiscoveryFailure(
                "invalid_discovery", "Entity programs require at least one comparison field."
            )
        if not blocking or not blocking.issubset(comparison_indexes):
            raise DiscoveryFailure(
                "invalid_discovery",
                "Entity programs require blocking indexes over comparison fields.",
            )
        if program.self_match is None and any(
            source == target
            for source, target in zip(
                program.source_fields, program.target_fields, strict=True
            )
        ):
            raise DiscoveryFailure(
                "invalid_discovery",
                "Equal entity field pairs require an explicit self_match program.",
            )
        if program.self_match is not None:
            if program.source_fields != program.target_fields:
                raise DiscoveryFailure(
                    "invalid_discovery",
                    "Self-entity programs require identical ordered source and target fields.",
                )
            if program.source_transforms != program.target_transforms:
                raise DiscoveryFailure(
                    "invalid_discovery",
                    "Self-entity programs require identical source and target transforms.",
                )
            if program.self_match.record_key_field in program.source_fields:
                raise DiscoveryFailure(
                    "invalid_discovery",
                    "The self-entity record key must be separate from comparison fields.",
                )
    for transforms in (*program.source_transforms, *program.target_transforms):
        if len(transforms) > _MAX_TRANSFORMS:
            raise DiscoveryFailure(
                "invalid_discovery", "A field accepts at most eight transforms."
            )
        if len([item.kind for item in transforms]) != len(
            set(item.kind for item in transforms)
        ):
            raise DiscoveryFailure(
                "invalid_discovery", "A field cannot repeat a transform kind."
            )
    fuzzy = {"normalized_levenshtein_v1", "token_set_ratio_v1"}
    if program.comparison in fuzzy:
        if program.kind != "entity_matching" or program.threshold is None:
            raise DiscoveryFailure(
                "invalid_discovery",
                "Fuzzy comparisons are entity-matching programs and require a threshold.",
            )
    elif program.threshold is not None:
        raise DiscoveryFailure(
            "invalid_discovery", "Exact comparisons do not accept a threshold."
        )
    if program.comparison == "llm_assessed":
        if program.kind != "entity_matching" or program.self_match is None:
            raise DiscoveryFailure(
                "invalid_discovery",
                "LLM-assessed identity groups require explicit Self-Entity semantics.",
            )
        if any((*program.source_transforms, *program.target_transforms)):
            raise DiscoveryFailure(
                "invalid_discovery",
                "LLM-assessed groups describe concrete keys, not an executable transform rule.",
            )
    if program.kind == "join_discovery" and program.comparison not in {
        "exact",
        "normalized_exact",
    }:
        raise DiscoveryFailure(
            "invalid_discovery", "Join discovery does not accept fuzzy equality semantics."
        )


def validate_discovery_run(run: DiscoveryRun) -> None:
    if run.contract_version != DISCOVERY_CONTRACT_VERSION:
        raise DiscoveryFailure(
            "unsupported_discovery", "Unsupported TAREL discovery-run contract."
        )
    _identifier(run.id, "run id")
    _sha256(run.graph_revision, "graph revision")
    if run.identity_inspection is not None and (
        run.kind != "entity_matching" or len(run.source_names) != 1
    ):
        raise DiscoveryFailure(
            "invalid_discovery",
            "Identity inspection requires one entity-matching run bound to exactly one source.",
        )
    if run.scope_mode == "query_linked_slice" and (
        run.kind != "entity_matching" or run.identity_inspection is not None
    ):
        raise DiscoveryFailure(
            "invalid_discovery",
            "Query-linked scope requires entity matching without key-persisting "
            "identity inspection.",
        )
    if run.actor_mode == "agent_with_provider_advisor" and run.advisor_provider is None:
        raise DiscoveryFailure(
            "invalid_discovery", "Provider-advisor mode requires an advisor provider name."
        )
    if run.actor_mode == "agent" and run.advisor_provider is not None:
        raise DiscoveryFailure(
            "invalid_discovery", "Agent-only mode cannot name an advisor provider."
        )
    candidate_ids = [item.id for item in run.candidates]
    if len(candidate_ids) != len(set(candidate_ids)) or len(candidate_ids) > run.candidate_budget:
        raise DiscoveryFailure(
            "invalid_discovery", "Candidate IDs must be unique and remain within budget."
        )
    candidate_by_id = {item.id: item for item in run.candidates}
    for candidate in run.candidates:
        if candidate.kind != run.kind:
            raise DiscoveryFailure(
                "invalid_discovery", "All candidates must match the run discovery kind."
            )
        if candidate.id in candidate.parent_ids or any(
            parent not in candidate_by_id for parent in candidate.parent_ids
        ):
            raise DiscoveryFailure(
                "invalid_discovery", "Candidate parents must reference other run candidates."
            )
        expected_generation = (
            0
            if not candidate.parent_ids
            else max(candidate_by_id[parent].generation for parent in candidate.parent_ids) + 1
        )
        if candidate.generation != expected_generation:
            raise DiscoveryFailure(
                "invalid_discovery", "Candidate generation does not match its parents."
            )
        if run.identity_inspection is not None:
            _validate_identity_candidate(run, candidate)
    if run.probes_used > run.probe_budget:
        raise DiscoveryFailure("invalid_discovery", "Discovery probe budget was exceeded.")
    sequences = [item.sequence for item in run.steps]
    if sequences != list(range(1, len(run.steps) + 1)):
        raise DiscoveryFailure(
            "invalid_discovery", "Discovery step sequences must be contiguous."
        )
    observation_ids = {
        observation.id
        for candidate in run.candidates
        for observation in candidate.observations
    }
    inspection = run.identity_inspection
    if inspection is not None:
        observation_ids.update(item.id for item in inspection.pages)
        observation_ids.update(item.id for item in inspection.groups)
        observation_ids.update(item.id for item in inspection.reflections)
        for group in inspection.groups:
            if group.candidate_id not in candidate_by_id:
                raise DiscoveryFailure(
                    "invalid_identity_inspection",
                    "Entity alias groups must reference a candidate from the same run.",
                )
        for reflection in inspection.reflections:
            candidate = candidate_by_id.get(reflection.candidate_id)
            if candidate is None or reflection.observation_id not in {
                item.id for item in candidate.observations
            }:
                raise DiscoveryFailure(
                    "invalid_identity_inspection",
                    "Entity reflections must reference their candidate's observation.",
                )
        for candidate in run.candidates:
            if candidate.state not in {"rejected", "selected"}:
                continue
            reflection = _latest_identity_reflection(run, candidate)
            decision = reflection.decision if reflection else None
            expected = (
                {"accept_as_exploratory", "recommend_promotion"}
                if candidate.state == "selected"
                else {"reject_group"}
            )
            if decision not in expected:
                raise DiscoveryFailure(
                    "invalid_identity_inspection",
                    "Terminal identity candidates require a matching group reflection.",
                )
    for step in run.steps:
        if step.candidate_id is not None and step.candidate_id not in candidate_by_id:
            raise DiscoveryFailure(
                "invalid_discovery", "Discovery step references an unknown candidate."
            )
        if step.observation_id is not None and step.observation_id not in observation_ids:
            raise DiscoveryFailure(
                "invalid_discovery", "Discovery step references an unknown observation."
            )
    if run.status == "completed" and not run.completion_reason:
        raise DiscoveryFailure(
            "invalid_discovery", "Completed runs require a completion reason."
        )
    if run.status != "completed" and run.completion_reason is not None:
        raise DiscoveryFailure(
            "invalid_discovery", "Only completed runs accept a completion reason."
        )


def allowed_discovery_actions(run: DiscoveryRun) -> tuple[str, ...]:
    if run.status == "completed":
        return ()
    if run.status == "paused":
        return ("resume_run",)
    inspection = run.identity_inspection
    if inspection is not None:
        if inspection.manifest is None:
            return ("register_identity_inventory", "pause_run")
        if not inspection.coverage_complete:
            return ("record_inventory_page", "pause_run")
    actions: list[str] = []
    if len(run.candidates) < run.candidate_budget:
        actions.append("propose_candidate")
    active = [item for item in run.candidates if item.state not in {"selected", "rejected"}]
    if inspection is None:
        if active and run.probes_used < run.probe_budget:
            actions.append("record_observation")
        if any(item.state == "challenged" for item in active):
            actions.extend(("select_candidate", "reject_candidate"))
    else:
        missing_groups = [
            item for item in active if inspection.group_for_candidate(item.id) is None
        ]
        if missing_groups:
            actions.append("record_entity_group")
        if any(
            inspection.group_for_candidate(item.id) is not None for item in active
        ) and run.probes_used < run.probe_budget:
            actions.append("record_observation")
        challenged = [item for item in active if item.state == "challenged"]
        if any(_latest_identity_reflection(run, item) is None for item in challenged):
            actions.append("record_entity_reflection")
        decisions = {
            item.id: (
                reflection.decision
                if (reflection := _latest_identity_reflection(run, item))
                else None
            )
            for item in challenged
        }
        if any(
            decision in {"accept_as_exploratory", "recommend_promotion"}
            for decision in decisions.values()
        ):
            actions.append("select_candidate")
        if any(decision == "reject_group" for decision in decisions.values()):
            actions.append("reject_candidate")
    actions.append("pause_run")
    if (
        inspection is None
        and (run.candidates or run.scope_mode == "query_linked_slice")
    ) or (
        inspection is not None
        and (
            not run.candidates
            or any(item.state in {"rejected", "selected"} for item in run.candidates)
        )
    ):
        actions.append("complete_run")
    return tuple(actions)


def apply_discovery_action(
    run: DiscoveryRun,
    *,
    action: str,
    actor: str,
    payload: dict[str, Any],
) -> DiscoveryRun:
    action = _choice(action, "action", DISCOVERY_ACTIONS)
    actor = _choice(actor, "actor", DISCOVERY_ACTORS)
    if action not in allowed_discovery_actions(run):
        raise DiscoveryFailure(
            "discovery_action_not_allowed",
            f"Action {action} is not allowed for the current discovery state.",
        )
    if actor == "provider" and action not in {
        "propose_candidate",
        "record_entity_group",
        "record_entity_reflection",
    }:
        raise DiscoveryFailure(
            "discovery_action_not_allowed",
            "Providers may propose hypotheses, but cannot report evidence or make decisions.",
        )
    if action in IDENTITY_ACTIONS:
        return _apply_identity_action(run, action=action, actor=actor, payload=payload)
    if action == "propose_candidate":
        updated, candidate_id = _propose_candidate(run, payload)
        return _append_step(updated, actor, action, candidate_id=candidate_id)
    if action == "record_observation":
        updated, candidate_id, observation_id = _record_observation(run, payload)
        return _append_step(
            updated,
            actor,
            action,
            candidate_id=candidate_id,
            observation_id=observation_id,
        )
    if action in {"select_candidate", "reject_candidate"}:
        updated, candidate_id, reason = _assess_candidate(run, action, payload)
        return _append_step(
            updated, actor, action, candidate_id=candidate_id, note=reason
        )
    _fields(payload, {"reason"}, f"{action} payload")
    reason = _text(payload.get("reason"), "reason")
    if action == "pause_run":
        return _append_step(replace(run, status="paused"), actor, action, note=reason)
    if action == "resume_run":
        return _append_step(replace(run, status="open"), actor, action, note=reason)
    return _append_step(
        replace(run, status="completed", completion_reason=reason),
        actor,
        action,
        note=reason,
    )


def _apply_identity_action(
    run: DiscoveryRun,
    *,
    action: str,
    actor: str,
    payload: dict[str, Any],
) -> DiscoveryRun:
    inspection = run.identity_inspection
    if inspection is None:
        raise DiscoveryFailure(
            "discovery_action_not_allowed",
            "This discovery run did not enable identity inspection.",
        )
    if actor == "provider" and action in {
        "record_inventory_page",
        "register_identity_inventory",
    }:
        raise DiscoveryFailure(
            "discovery_action_not_allowed",
            "Providers cannot attest inventory coverage or source execution.",
        )
    try:
        if action == "register_identity_inventory":
            changed_inspection = add_manifest(inspection, payload)
            candidate_id = None
            reference = None
        elif action == "record_inventory_page":
            changed_inspection = add_page(inspection, payload)
            candidate_id = None
            reference = changed_inspection.pages[-1].id
        elif action == "record_entity_group":
            changed_inspection = add_group(inspection, payload)
            group = changed_inspection.groups[-1]
            _candidate(run, group.candidate_id)
            candidate_id = group.candidate_id
            reference = group.id
        else:
            reflection = EntityGroupReflection.from_dict(payload)
            candidate = _candidate(run, reflection.candidate_id)
            challenge = next(
                (
                    item
                    for item in candidate.observations
                    if item.id == reflection.observation_id
                    and item.phase == "challenge"
                    and item.status == "succeeded"
                ),
                None,
            )
            if candidate.state != "challenged" or challenge is None:
                raise DiscoveryFailure(
                    "invalid_entity_reflection",
                    "Entity reflection requires a successful challenge observation.",
                )
            changed_inspection = add_reflection(inspection, payload)
            candidate_id = reflection.candidate_id
            reference = reflection.id
    except IdentityFailure as exc:
        raise DiscoveryFailure(exc.code, str(exc)) from exc
    return _append_step(
        replace(run, identity_inspection=changed_inspection),
        actor,
        action,
        candidate_id=candidate_id,
        observation_id=reference,
    )


def _propose_candidate(
    run: DiscoveryRun, payload: dict[str, Any]
) -> tuple[DiscoveryRun, str]:
    _fields(
        payload,
        {"candidate_id", "parent_ids", "program", "variation_operator"},
        "propose_candidate payload",
    )
    candidate_id = _identifier(payload.get("candidate_id"), "candidate_id")
    if any(item.id == candidate_id for item in run.candidates):
        raise DiscoveryFailure(
            "discovery_candidate_exists", f"Discovery candidate already exists: {candidate_id}"
        )
    parent_ids = _identifier_array(payload.get("parent_ids"), "parent_ids")
    parents = {item.id: item for item in run.candidates}
    if any(parent not in parents for parent in parent_ids):
        raise DiscoveryFailure(
            "invalid_discovery", "Candidate parent does not exist in the current run."
        )
    generation = 0 if not parent_ids else max(parents[item].generation for item in parent_ids) + 1
    candidate = DiscoveryCandidate(
        id=candidate_id,
        kind=run.kind,
        generation=generation,
        parent_ids=parent_ids,
        variation_operator=_identifier(
            payload.get("variation_operator"), "variation_operator"
        ),
        program=DiscoveryProgram.from_dict(_object(payload.get("program"), "program")),
    )
    if candidate.program.kind != run.kind:
        raise DiscoveryFailure(
            "invalid_discovery", "Candidate program does not match the run kind."
        )
    if run.identity_inspection is not None:
        _validate_identity_candidate(run, candidate)
    return replace(run, candidates=(*run.candidates, candidate)), candidate.id


def _record_observation(
    run: DiscoveryRun, payload: dict[str, Any]
) -> tuple[DiscoveryRun, str, str]:
    _fields(payload, {"candidate_id", "observation"}, "record_observation payload")
    candidate_id = _identifier(payload.get("candidate_id"), "candidate_id")
    observation = DiscoveryObservation.from_dict(
        _object(payload.get("observation"), "observation")
    )
    candidate = _candidate(run, candidate_id)
    if candidate.state in {"selected", "rejected"}:
        raise DiscoveryFailure(
            "discovery_action_not_allowed", "Terminal candidates cannot receive observations."
        )
    if (
        run.identity_inspection is not None
        and run.identity_inspection.group_for_candidate(candidate_id) is None
    ):
        raise DiscoveryFailure(
            "entity_alias_group_required",
            "Register the concrete entity alias group before executing probes.",
        )
    if (
        candidate.program.self_match is not None
        and observation.status == "succeeded"
        and observation.metrics is not None
        and observation.metrics.basis != "pairs"
    ):
        raise DiscoveryFailure(
            "invalid_discovery",
            "Self-entity observations must report canonical distinct-record pairs.",
        )
    if any(
        observation.id == current.id
        for current_candidate in run.candidates
        for current in current_candidate.observations
    ):
        raise DiscoveryFailure(
            "discovery_observation_exists",
            f"Discovery observation already exists: {observation.id}",
        )
    state = "challenged" if observation.phase == "challenge" else "tested"
    if candidate.state == "challenged" and observation.phase == "support":
        state = "challenged"
    changed = replace(
        candidate,
        state=state,
        observations=(*candidate.observations, observation),
    )
    return _replace_candidate(run, changed), candidate_id, observation.id


def _assess_candidate(
    run: DiscoveryRun, action: str, payload: dict[str, Any]
) -> tuple[DiscoveryRun, str, str]:
    _fields(payload, {"candidate_id", "reason"}, f"{action} payload")
    candidate_id = _identifier(payload.get("candidate_id"), "candidate_id")
    reason = _text(payload.get("reason"), "reason")
    candidate = _candidate(run, candidate_id)
    if candidate.state != "challenged":
        raise DiscoveryFailure(
            "discovery_action_not_allowed",
            "Candidates must receive a challenge observation before assessment.",
        )
    if action == "select_candidate" and not any(
        item.phase == "challenge" and item.status == "succeeded"
        for item in candidate.observations
    ):
        raise DiscoveryFailure(
            "discovery_action_not_allowed",
            "Selection requires one successful challenge observation.",
        )
    if run.identity_inspection is not None:
        reflection = _latest_identity_reflection(run, candidate)
        decision = reflection.decision if reflection else None
        allowed = (
            {"accept_as_exploratory", "recommend_promotion"}
            if action == "select_candidate"
            else {"reject_group"}
        )
        if decision not in allowed:
            raise DiscoveryFailure(
                "discovery_action_not_allowed",
                "Candidate assessment must follow its latest structured entity reflection.",
            )
    changed = replace(
        candidate,
        state="selected" if action == "select_candidate" else "rejected",
        assessment_reason=reason,
    )
    return _replace_candidate(run, changed), candidate_id, reason


def _validate_identity_candidate(
    run: DiscoveryRun, candidate: DiscoveryCandidate
) -> None:
    inspection = run.identity_inspection
    manifest = inspection.manifest if inspection else None
    if manifest is None or not inspection.coverage_complete:
        raise DiscoveryFailure(
            "identity_inventory_incomplete",
            "LLM-assessed groups require a complete identity inventory.",
        )
    program = candidate.program
    if program.comparison != "llm_assessed" or program.self_match is None:
        raise DiscoveryFailure(
            "invalid_identity_candidate",
            "Identity-inspection candidates must be LLM-assessed Self-Entity groups.",
        )
    expected_fields = (manifest.label_field,)
    if (
        program.self_match.record_key_field != manifest.record_key_field
        or program.source_fields != expected_fields
        or program.target_fields != expected_fields
        or program.contradiction_field_indexes
    ):
        raise DiscoveryFailure(
            "invalid_identity_candidate",
            "Candidate key and label must match its identity inventory.",
        )


def _latest_identity_reflection(
    run: DiscoveryRun, candidate: DiscoveryCandidate
) -> EntityGroupReflection | None:
    inspection = run.identity_inspection
    if inspection is None:
        return None
    challenge = next(
        (
            item
            for item in reversed(candidate.observations)
            if item.phase == "challenge" and item.status == "succeeded"
        ),
        None,
    )
    if challenge is None:
        return None
    return next(
        (
            item
            for item in reversed(inspection.reflections)
            if item.candidate_id == candidate.id
            and item.observation_id == challenge.id
        ),
        None,
    )


def _append_step(
    run: DiscoveryRun,
    actor: str,
    action: str,
    *,
    candidate_id: str | None = None,
    observation_id: str | None = None,
    note: str | None = None,
) -> DiscoveryRun:
    changed = replace(
        run,
        steps=(
            *run.steps,
            DiscoveryStep(
                sequence=len(run.steps) + 1,
                actor=actor,
                action=action,
                candidate_id=candidate_id,
                observation_id=observation_id,
                note=note,
            ),
        ),
    )
    validate_discovery_run(changed)
    return changed


def _candidate(run: DiscoveryRun, candidate_id: str) -> DiscoveryCandidate:
    candidate = next((item for item in run.candidates if item.id == candidate_id), None)
    if candidate is None:
        raise DiscoveryFailure(
            "discovery_candidate_not_found", f"Discovery candidate not found: {candidate_id}"
        )
    return candidate


def _replace_candidate(run: DiscoveryRun, candidate: DiscoveryCandidate) -> DiscoveryRun:
    return replace(
        run,
        candidates=tuple(
            candidate if item.id == candidate.id else item for item in run.candidates
        ),
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
        raise DiscoveryFailure(
            "invalid_discovery", f"{label} has unexpected or missing fields."
        )


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DiscoveryFailure("invalid_discovery", f"{label} must be an object.")
    return value


def _text(value: object, label: str, *, limit: int = _MAX_TEXT) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise DiscoveryFailure(
            "invalid_discovery",
            f"{label} must be a non-empty string of at most {limit} characters.",
        )
    return value.strip()


def _optional_text(value: object, label: str) -> str | None:
    return None if value is None else _text(value, label)


def _identifier(value: object, label: str) -> str:
    return _pattern(value, label, _IDENTIFIER)


def _optional_identifier(value: object, label: str) -> str | None:
    return None if value is None else _identifier(value, label)


def _pattern(value: object, label: str, pattern: re.Pattern[str]) -> str:
    clean = _text(value, label, limit=128)
    if not pattern.fullmatch(clean):
        raise DiscoveryFailure("invalid_discovery", f"{label} has an invalid format.")
    return clean


def _sha256(value: object, label: str) -> str:
    return _pattern(value, label, _SHA256)


def _choice(value: object, label: str, choices: frozenset[str]) -> str:
    clean = _text(value, label, limit=128)
    if clean not in choices:
        raise DiscoveryFailure("invalid_discovery", f"Unsupported {label}: {clean}")
    return clean


def _string_array(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise DiscoveryFailure("invalid_discovery", f"{label} must be an array of strings.")
    return tuple(_text(item, label, limit=256) for item in value)


def _identifier_array(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise DiscoveryFailure("invalid_discovery", f"{label} must be an array.")
    result = tuple(_identifier(item, label) for item in value)
    if len(result) != len(set(result)):
        raise DiscoveryFailure("invalid_discovery", f"{label} must contain unique values.")
    return result


def _integer_array(value: object, label: str) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise DiscoveryFailure("invalid_discovery", f"{label} must be an array.")
    result = tuple(_integer(item, label) for item in value)
    if len(result) != len(set(result)):
        raise DiscoveryFailure("invalid_discovery", f"{label} must contain unique values.")
    return result


def _transform_matrix(value: object, label: str) -> tuple[tuple[DiscoveryTransform, ...], ...]:
    if not isinstance(value, list) or any(not isinstance(item, list) for item in value):
        raise DiscoveryFailure(
            "invalid_discovery", f"{label} must be an array of transform arrays."
        )
    rows: list[tuple[DiscoveryTransform, ...]] = []
    for row in value:
        if any(not isinstance(item, dict) for item in row):
            raise DiscoveryFailure(
                "invalid_discovery", f"{label} entries must be transform objects."
            )
        rows.append(tuple(DiscoveryTransform.from_dict(item) for item in row))
    return tuple(rows)


def _integer(value: object, label: str) -> int:
    return _bounded_integer(value, label, 0, 2**63 - 1)


def _optional_integer(value: object, label: str) -> int | None:
    return None if value is None else _integer(value, label)


def _bounded_integer(value: object, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise DiscoveryFailure(
            "invalid_discovery", f"{label} must be an integer between {minimum} and {maximum}."
        )
    return value


def _rate(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DiscoveryFailure(
            "invalid_discovery", f"{label} must be a number between 0 and 1."
        )
    result = float(value)
    if not math.isfinite(result) or not 0 <= result <= 1:
        raise DiscoveryFailure(
            "invalid_discovery", f"{label} must be a finite number between 0 and 1."
        )
    return result


def _optional_rate(value: object, label: str) -> float | None:
    return None if value is None else _rate(value, label)


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise DiscoveryFailure("invalid_discovery", f"{label} must be a boolean.")
    return value
