"""Discovery runs: the revisioned record of executions, observations and candidates."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

from tarel.discovery._parse import (
    DIALECT_PATTERN,
    MAX_CANDIDATES,
    MAX_PARENTS,
    MAX_PROBES,
    bounded_integer,
    identifier_array,
    optional_identifier,
    optional_integer,
    optional_rate,
    optional_text,
    require_boolean,
    require_choice,
    require_fields,
    require_identifier,
    require_integer,
    require_object,
    require_pattern,
    require_rate,
    require_sha256,
    require_text,
)
from tarel.discovery.contracts import (
    DISCOVERY_ACTIONS,
    DISCOVERY_ACTORS,
    DISCOVERY_BLOCKING_STRATEGIES,
    DISCOVERY_CANDIDATE_STATES,
    DISCOVERY_CONTRACT_VERSION,
    DISCOVERY_CONTRACT_VERSIONS,
    DISCOVERY_EVIDENCE_LEVELS,
    DISCOVERY_KINDS,
    DISCOVERY_LOGICAL_JOIN_CONTRACT_VERSION,
    DISCOVERY_METRIC_BASES,
    DISCOVERY_OBSERVATION_PHASES,
    DISCOVERY_OBSERVATION_STATUSES,
    DISCOVERY_REFERENCE_MAPPING_CONTRACT_VERSION,
    DISCOVERY_STATUSES,
    DiscoveryFailure,
)
from tarel.discovery.coverage import DISCOVERY_SCOPE_MODES
from tarel.discovery.identity import (
    IDENTITY_ACTIONS,
    EntityGroupReflection,
    IdentityFailure,
    IdentityInspection,
)
from tarel.discovery.logical_program import LogicalJoinProgram
from tarel.discovery.programs import (
    DiscoveryProgram,
    DiscoveryProgramType,
    ReferenceMappingManifest,
    discovery_program_from_dict,
)


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
        require_fields(
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
            basis=require_choice(data.get("basis"), "metric basis", DISCOVERY_METRIC_BASES),
            evaluated_count=require_integer(data.get("evaluated_count"), "evaluated_count"),
            matched_count=require_integer(data.get("matched_count"), "matched_count"),
            distinct_source_count=require_integer(
                data.get("distinct_source_count"), "distinct_source_count"
            ),
            distinct_target_count=require_integer(
                data.get("distinct_target_count"), "distinct_target_count"
            ),
            collision_count=optional_integer(
                data.get("collision_count"), "collision_count"
            ),
            counterexample_count=optional_integer(
                data.get("counterexample_count"), "counterexample_count"
            ),
            coverage=require_rate(data.get("coverage"), "coverage"),
            collision_rate=optional_rate(data.get("collision_rate"), "collision_rate"),
            confidence=require_rate(data.get("confidence"), "confidence"),
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
        require_fields(
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
            executor_id=require_identifier(data.get("executor_id"), "executor_id"),
            executor_version=require_identifier(
                data.get("executor_version"), "executor_version"
            ),
            artifact_hash=require_sha256(data.get("artifact_hash"), "artifact_hash"),
            blocking_strategy=require_choice(
                data.get("blocking_strategy"),
                "blocking_strategy",
                DISCOVERY_BLOCKING_STRATEGIES,
            ),
            blocking_version=require_identifier(
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
        require_fields(
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
            id=require_identifier(data.get("id"), "observation id"),
            phase=require_choice(
                data.get("phase"), "observation phase", DISCOVERY_OBSERVATION_PHASES
            ),
            status=require_choice(
                data.get("status"), "observation status", DISCOVERY_OBSERVATION_STATUSES
            ),
            evidence_level=require_choice(
                data.get("evidence_level"),
                "evidence level",
                DISCOVERY_EVIDENCE_LEVELS,
            ),
            dialect=require_pattern(data.get("dialect"), "dialect", DIALECT_PATTERN),
            query_hash=require_sha256(data.get("query_hash"), "query_hash"),
            row_limit=bounded_integer(data.get("row_limit"), "row_limit", 1, 1_000_000),
            truncated=require_boolean(data.get("truncated"), "truncated"),
            duration_ms=bounded_integer(
                data.get("duration_ms"), "duration_ms", 0, 86_400_000
            ),
            metrics=DiscoveryMetrics.from_dict(metrics_value) if metrics_value else None,
            error_category=optional_identifier(
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
    program: DiscoveryProgramType
    state: str = "proposed"
    observations: tuple[DiscoveryObservation, ...] = ()
    assessment_reason: str | None = None
    mapping_manifest: ReferenceMappingManifest | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
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
        if self.mapping_manifest is not None:
            payload["mapping_manifest"] = self.mapping_manifest.to_dict()
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscoveryCandidate:
        require_fields(
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
            optional={"mapping_manifest"},
        )
        observations = data.get("observations")
        if not isinstance(observations, list) or any(
            not isinstance(item, dict) for item in observations
        ):
            raise DiscoveryFailure(
                "invalid_discovery", "candidate observations must be an array of objects."
            )
        mapping_manifest_value = data.get("mapping_manifest")
        if mapping_manifest_value is not None and not isinstance(
            mapping_manifest_value, dict
        ):
            raise DiscoveryFailure(
                "invalid_discovery", "mapping_manifest must be an object or null."
            )
        candidate = cls(
            id=require_identifier(data.get("id"), "candidate id"),
            kind=require_choice(data.get("kind"), "discovery kind", DISCOVERY_KINDS),
            generation=bounded_integer(data.get("generation"), "generation", 0, 10_000),
            parent_ids=identifier_array(data.get("parent_ids"), "parent_ids"),
            variation_operator=require_identifier(
                data.get("variation_operator"), "variation_operator"
            ),
            program=discovery_program_from_dict(
                require_object(data.get("program"), "program")
            ),
            mapping_manifest=(
                ReferenceMappingManifest.from_dict(mapping_manifest_value)
                if isinstance(mapping_manifest_value, dict)
                else None
            ),
            state=require_choice(
                data.get("state"), "candidate state", DISCOVERY_CANDIDATE_STATES
            ),
            observations=tuple(DiscoveryObservation.from_dict(item) for item in observations),
            assessment_reason=optional_text(
                data.get("assessment_reason"), "assessment_reason"
            ),
        )
        if candidate.kind != candidate.program.kind:
            raise DiscoveryFailure(
                "invalid_discovery", "Candidate and program discovery kinds must match."
            )
        if candidate.kind != "reference_mapping" and "mapping_manifest" in data:
            raise DiscoveryFailure(
                "invalid_discovery",
                "Only reference-mapping candidates accept a mapping manifest.",
            )
        if (
            candidate.kind == "reference_mapping"
            and candidate.observations
            and candidate.mapping_manifest is None
        ):
            raise DiscoveryFailure(
                "invalid_discovery",
                "Reference-mapping observations require a registered mapping manifest.",
            )
        if len(candidate.parent_ids) > MAX_PARENTS or len(candidate.parent_ids) != len(
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
        require_fields(
            data,
            {"action", "actor", "candidate_id", "note", "observation_id", "sequence"},
            "discovery step",
        )
        return cls(
            sequence=bounded_integer(data.get("sequence"), "sequence", 1, 100_000),
            actor=require_choice(data.get("actor"), "actor", DISCOVERY_ACTORS),
            action=require_choice(data.get("action"), "action", DISCOVERY_ACTIONS),
            candidate_id=optional_identifier(data.get("candidate_id"), "candidate_id"),
            observation_id=optional_identifier(
                data.get("observation_id"), "observation_id"
            ),
            note=optional_text(data.get("note"), "note"),
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
        require_fields(
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
        contract_version = data.get("contract_version")
        if contract_version not in DISCOVERY_CONTRACT_VERSIONS:
            raise DiscoveryFailure(
                "unsupported_discovery", "Unsupported TAREL discovery-run contract."
            )
        graph = require_object(data.get("graph"), "graph")
        require_fields(graph, {"name", "revision"}, "discovery graph")
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
            id=require_identifier(data.get("id"), "run id"),
            kind=require_choice(data.get("kind"), "discovery kind", DISCOVERY_KINDS),
            graph_name=require_text(graph.get("name"), "graph name"),
            graph_revision=require_sha256(graph.get("revision"), "graph revision"),
            source_names=identifier_array(data.get("source_names"), "source_names"),
            question=optional_text(data.get("question"), "question"),
            actor_mode=require_choice(
                data.get("actor_mode"),
                "actor mode",
                frozenset({"agent", "agent_with_provider_advisor"}),
            ),
            advisor_provider=optional_identifier(
                data.get("advisor_provider"), "advisor_provider"
            ),
            probe_budget=bounded_integer(
                data.get("probe_budget"), "probe_budget", 1, MAX_PROBES
            ),
            candidate_budget=bounded_integer(
                data.get("candidate_budget"), "candidate_budget", 1, MAX_CANDIDATES
            ),
            status=require_choice(data.get("status"), "run status", DISCOVERY_STATUSES),
            candidates=tuple(DiscoveryCandidate.from_dict(item) for item in candidates),
            steps=tuple(DiscoveryStep.from_dict(item) for item in steps),
            completion_reason=optional_text(
                data.get("completion_reason"), "completion_reason"
            ),
            identity_inspection=identity_inspection,
            scope_mode=(
                require_choice(data.get("scope_mode"), "scope_mode", DISCOVERY_SCOPE_MODES)
                if data.get("scope_mode") is not None
                else None
            ),
            contract_version=str(contract_version),
        )
        validate_discovery_run(run)
        expected_revision = data.get("revision")
        if expected_revision is not None and expected_revision != run.revision:
            raise DiscoveryFailure(
                "invalid_discovery", "Discovery run revision does not match its content."
            )
        return run


def validate_discovery_run(run: DiscoveryRun) -> None:
    """Raise ``DiscoveryFailure`` unless the run's settings, candidates and steps agree."""
    _validate_run_header(run)
    candidate_by_id = _validate_candidates(run)
    _validate_steps(run, candidate_by_id)
    _validate_completion(run)


def _validate_run_header(run: DiscoveryRun) -> None:
    """Contract version, kind and program, identity, scope and actor settings agree."""
    if run.contract_version not in DISCOVERY_CONTRACT_VERSIONS:
        raise DiscoveryFailure(
            "unsupported_discovery", "Unsupported TAREL discovery-run contract."
        )
    if (
        run.contract_version == DISCOVERY_CONTRACT_VERSION
        and run.kind == "reference_mapping"
    ):
        raise DiscoveryFailure(
            "unsupported_discovery",
            "Reference mapping requires the v0.2 discovery-run contract.",
        )
    if (
        run.contract_version == DISCOVERY_REFERENCE_MAPPING_CONTRACT_VERSION
        and run.kind != "reference_mapping"
    ):
        raise DiscoveryFailure(
            "unsupported_discovery",
            "The v0.2 discovery-run contract is reserved for reference mapping.",
        )
    if (
        run.contract_version == DISCOVERY_LOGICAL_JOIN_CONTRACT_VERSION
        and run.kind != "join_discovery"
    ):
        raise DiscoveryFailure("unsupported_discovery", "The v0.3 contract is for logical joins.")
    if any(isinstance(item.program, LogicalJoinProgram) for item in run.candidates) and (
        run.contract_version != DISCOVERY_LOGICAL_JOIN_CONTRACT_VERSION
    ):
        raise DiscoveryFailure(
            "unsupported_discovery", "Logical endpoints require an explicitly opted-in v0.3 run."
        )
    require_identifier(run.id, "run id")
    require_sha256(run.graph_revision, "graph revision")
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


def _validate_candidates(run: DiscoveryRun) -> dict[str, DiscoveryCandidate]:
    """Candidates are unique, within budget and consistent with the run's program."""
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
            validate_identity_candidate(run, candidate)
    if run.probes_used > run.probe_budget:
        raise DiscoveryFailure("invalid_discovery", "Discovery probe budget was exceeded.")
    return candidate_by_id


def _validate_steps(run: DiscoveryRun, candidate_by_id: dict[str, DiscoveryCandidate]) -> None:
    """Steps are numbered in order and only reference observations and inspections they may."""
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
            latest = latest_identity_reflection(run, candidate)
            decision = latest.decision if latest else None
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
        if (
            step.action == "register_mapping_manifest"
            and run.kind != "reference_mapping"
        ):
            raise DiscoveryFailure(
                "invalid_discovery",
                "Only reference-mapping runs accept mapping-manifest steps.",
            )
        if step.candidate_id is not None and step.candidate_id not in candidate_by_id:
            raise DiscoveryFailure(
                "invalid_discovery", "Discovery step references an unknown candidate."
            )
        if step.observation_id is not None and step.observation_id not in observation_ids:
            raise DiscoveryFailure(
                "invalid_discovery", "Discovery step references an unknown observation."
            )


def _validate_completion(run: DiscoveryRun) -> None:
    """Reference-mapping steps are complete and the completion reason matches the status."""
    if run.kind == "reference_mapping":
        _validate_reference_mapping_run_steps(run)
    if run.status == "completed" and not run.completion_reason:
        raise DiscoveryFailure(
            "invalid_discovery", "Completed runs require a completion reason."
        )
    if run.status != "completed" and run.completion_reason is not None:
        raise DiscoveryFailure(
            "invalid_discovery", "Only completed runs accept a completion reason."
        )


def _validate_reference_mapping_run_steps(run: DiscoveryRun) -> None:
    for step in run.steps:
        if step.actor == "provider" and step.action != "propose_candidate":
            raise DiscoveryFailure(
                "invalid_discovery",
                "Providers may only propose reference-mapping hypotheses.",
            )
        if step.action in IDENTITY_ACTIONS:
            raise DiscoveryFailure(
                "invalid_discovery",
                "Reference-mapping runs cannot contain entity-inspection actions.",
            )
    for candidate in run.candidates:
        proposals = [
            step
            for step in run.steps
            if step.action == "propose_candidate" and step.candidate_id == candidate.id
        ]
        if len(proposals) != 1:
            raise DiscoveryFailure(
                "invalid_discovery",
                "Each reference-mapping candidate requires one proposal step.",
            )
        registrations = [
            step
            for step in run.steps
            if step.action == "register_mapping_manifest"
            and step.candidate_id == candidate.id
        ]
        expected_registration_count = 1 if candidate.mapping_manifest is not None else 0
        if len(registrations) != expected_registration_count:
            raise DiscoveryFailure(
                "invalid_discovery",
                "Reference-mapping manifest state requires one matching registration step.",
            )
        if registrations and proposals[0].sequence >= registrations[0].sequence:
            raise DiscoveryFailure(
                "invalid_discovery",
                "Reference-mapping manifest registration must follow its proposal.",
            )
        observation_steps = [
            step
            for step in run.steps
            if step.action == "record_observation" and step.candidate_id == candidate.id
        ]
        expected_observations = {item.id for item in candidate.observations}
        observed_references = [step.observation_id for step in observation_steps]
        if (
            len(observed_references) != len(set(observed_references))
            or set(observed_references) != expected_observations
        ):
            raise DiscoveryFailure(
                "invalid_discovery",
                "Reference-mapping evidence requires one matching non-provider step per probe.",
            )
        if registrations and observation_steps and registrations[0].sequence >= min(
            step.sequence for step in observation_steps
        ):
            raise DiscoveryFailure(
                "invalid_discovery",
                "Reference-mapping evidence must follow manifest registration.",
            )
        assessments = [
            step
            for step in run.steps
            if step.action in {"reject_candidate", "select_candidate"}
            and step.candidate_id == candidate.id
        ]
        expected_action = {
            "rejected": "reject_candidate",
            "selected": "select_candidate",
        }.get(candidate.state)
        if expected_action is None and assessments:
            raise DiscoveryFailure(
                "invalid_discovery",
                "Only terminal reference-mapping candidates accept an assessment step.",
            )
        if expected_action is not None and (
            len(assessments) != 1 or assessments[0].action != expected_action
        ):
            raise DiscoveryFailure(
                "invalid_discovery",
                "Terminal reference-mapping state requires one matching assessment step.",
            )
        if assessments and observation_steps and assessments[0].sequence <= max(
            step.sequence for step in observation_steps
        ):
            raise DiscoveryFailure(
                "invalid_discovery",
                "Reference-mapping assessment must follow its evidence.",
            )


def validate_identity_candidate(
    run: DiscoveryRun, candidate: DiscoveryCandidate
) -> None:
    inspection = run.identity_inspection
    if inspection is None or inspection.manifest is None or not inspection.coverage_complete:
        raise DiscoveryFailure(
            "identity_inventory_incomplete",
            "LLM-assessed groups require a complete identity inventory.",
        )
    manifest = inspection.manifest
    program = candidate.program
    if not isinstance(program, DiscoveryProgram):
        raise DiscoveryFailure(
            "invalid_identity_candidate",
            "Identity inspection requires an entity-matching program.",
        )
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


def latest_identity_reflection(
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
