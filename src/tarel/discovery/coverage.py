"""Strict, value-free coverage for query-linked entity discovery."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any

QUERY_LINKED_COVERAGE_VERSION = "tarel.query-linked-entity-coverage.v0.1.experimental"
DISCOVERY_SCOPE_MODES = frozenset({"global_population", "query_linked_slice"})
QUERY_COMPONENT_STATUSES = frozenset(
    {
        "failed",
        "no_match",
        "promoted_confirmed",
        "promoted_exploratory",
        "proposed_and_rejected",
    }
)

_SUCCESSFUL_COMPONENT_STATUSES = QUERY_COMPONENT_STATUSES - {"failed"}
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@-]{0,511}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_COMPONENTS = 100_000


class QueryLinkedCoverageFailure(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class QueryCoverageExecutor:
    id: str
    version: str
    artifact_hash: str

    def to_dict(self) -> dict[str, str]:
        return {
            "artifact_hash": self.artifact_hash,
            "id": self.id,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QueryCoverageExecutor:
        _fields(data, {"artifact_hash", "id", "version"}, "coverage executor")
        return cls(
            id=_reference(data.get("id"), "executor id"),
            version=_reference(data.get("version"), "executor version"),
            artifact_hash=_sha256(data.get("artifact_hash"), "executor artifact_hash"),
        )


@dataclass(frozen=True, slots=True)
class QueryCoverageModel:
    provider: str
    name: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "provider": self.provider}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QueryCoverageModel:
        _fields(data, {"name", "provider"}, "coverage model")
        return cls(
            provider=_reference(data.get("provider"), "model provider"),
            name=_reference(data.get("name"), "model name"),
        )


@dataclass(frozen=True, slots=True)
class QueryLinkedComponent:
    id: str
    status: str
    discovery_candidate_refs: tuple[str, ...]
    entity_candidate_refs: tuple[str, ...]
    observation_refs: tuple[str, ...]
    reviewed_identity_count: int
    executor: QueryCoverageExecutor
    model: QueryCoverageModel | None
    error_category: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "discovery_candidate_refs": list(self.discovery_candidate_refs),
            "entity_candidate_refs": list(self.entity_candidate_refs),
            "error_category": self.error_category,
            "executor": self.executor.to_dict(),
            "id": self.id,
            "model": self.model.to_dict() if self.model else None,
            "observation_refs": list(self.observation_refs),
            "reviewed_identity_count": self.reviewed_identity_count,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QueryLinkedComponent:
        _fields(
            data,
            {
                "discovery_candidate_refs",
                "entity_candidate_refs",
                "error_category",
                "executor",
                "id",
                "model",
                "observation_refs",
                "reviewed_identity_count",
                "status",
            },
            "query-linked component",
        )
        executor = _object(data.get("executor"), "component executor")
        model_value = data.get("model")
        if model_value is not None and not isinstance(model_value, dict):
            raise QueryLinkedCoverageFailure(
                "invalid_query_linked_coverage", "Component model must be an object or null."
            )
        component = cls(
            id=_identifier(data.get("id"), "component id"),
            status=_choice(data.get("status"), "component status", QUERY_COMPONENT_STATUSES),
            discovery_candidate_refs=_reference_array(
                data.get("discovery_candidate_refs"), "discovery_candidate_refs"
            ),
            entity_candidate_refs=_reference_array(
                data.get("entity_candidate_refs"), "entity_candidate_refs"
            ),
            observation_refs=_reference_array(
                data.get("observation_refs"), "observation_refs"
            ),
            reviewed_identity_count=_integer(
                data.get("reviewed_identity_count"), "reviewed_identity_count"
            ),
            executor=QueryCoverageExecutor.from_dict(executor),
            model=(
                QueryCoverageModel.from_dict(model_value)
                if isinstance(model_value, dict)
                else None
            ),
            error_category=_optional_identifier(
                data.get("error_category"), "error_category"
            ),
        )
        _validate_component(component)
        return component


@dataclass(frozen=True, slots=True)
class QueryLinkedEntityCoverage:
    run_id: str
    run_revision: str
    graph_name: str
    graph_revision: str
    population_manifest_hash: str
    ranking_evidence_hash: str
    measure_reference: str
    sort_direction: str
    top_n: int
    slice_manifest_hash: str
    declared_component_count: int
    completed_component_count: int
    failed_component_count: int
    reviewed_identity_count: int
    inventory_coverage: float
    query_slice_coverage: float
    probe_coverage: float
    mapped_record_coverage: float
    components: tuple[QueryLinkedComponent, ...]
    contract_version: str = QUERY_LINKED_COVERAGE_VERSION

    @property
    def candidate_refs(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    *(ref for item in self.components for ref in item.discovery_candidate_refs),
                    *(ref for item in self.components for ref in item.entity_candidate_refs),
                }
            )
        )

    @property
    def observation_refs(self) -> tuple[str, ...]:
        return tuple(
            sorted({ref for item in self.components for ref in item.observation_refs})
        )

    @property
    def terminal_component_count(self) -> int:
        return len(self.components)

    @property
    def all_components_terminal(self) -> bool:
        return self.terminal_component_count == self.declared_component_count

    @property
    def revision(self) -> str:
        payload = json.dumps(
            self.to_dict(include_revision=False),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self, *, include_revision: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "candidate_refs": list(self.candidate_refs),
            "completed_component_count": self.completed_component_count,
            "components": [item.to_dict() for item in self.components],
            "contract_version": self.contract_version,
            "declared_component_count": self.declared_component_count,
            "failed_component_count": self.failed_component_count,
            "graph": {"name": self.graph_name, "revision": self.graph_revision},
            "inventory_coverage": self.inventory_coverage,
            "mapped_record_coverage": self.mapped_record_coverage,
            "measure": {
                "reference": self.measure_reference,
                "sort_direction": self.sort_direction,
            },
            "observation_refs": list(self.observation_refs),
            "population_manifest_hash": self.population_manifest_hash,
            "probe_coverage": self.probe_coverage,
            "query_slice_coverage": self.query_slice_coverage,
            "ranking_evidence_hash": self.ranking_evidence_hash,
            "reviewed_identity_count": self.reviewed_identity_count,
            "run_id": self.run_id,
            "run_revision": self.run_revision,
            "scope_mode": "query_linked_slice",
            "slice_manifest_hash": self.slice_manifest_hash,
            "top_n": self.top_n,
        }
        if include_revision:
            payload["revision"] = self.revision
        return payload

    def to_summary_dict(self) -> dict[str, object]:
        """Return the bounded, reference-free browser/retrieval summary."""
        statuses = {status: 0 for status in sorted(QUERY_COMPONENT_STATUSES)}
        for component in self.components:
            statuses[component.status] += 1
        promoted_statuses = {
            component.status
            for component in self.components
            if component.status.startswith("promoted_")
        }
        candidate_usage = (
            "exploratory_only"
            if "promoted_exploratory" in promoted_statuses
            else "confirmed"
            if "promoted_confirmed" in promoted_statuses
            else "no_promoted_candidate"
        )
        return {
            "candidate_usage": candidate_usage,
            "completed_component_count": self.completed_component_count,
            "declared_component_count": self.declared_component_count,
            "failed_component_count": self.failed_component_count,
            "graph": self.graph_name,
            "inventory_coverage": self.inventory_coverage,
            "mapped_record_coverage": self.mapped_record_coverage,
            "measure": {
                "reference": self.measure_reference,
                "sort_direction": self.sort_direction,
            },
            "probe_coverage": self.probe_coverage,
            "query_slice_coverage": self.query_slice_coverage,
            "reviewed_identity_count": self.reviewed_identity_count,
            "revision": self.revision,
            "run_id": self.run_id,
            "scope_mode": "query_linked_slice",
            "status_counts": statuses,
            "top_n": self.top_n,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QueryLinkedEntityCoverage:
        _fields(
            data,
            {
                "candidate_refs",
                "completed_component_count",
                "components",
                "contract_version",
                "declared_component_count",
                "failed_component_count",
                "graph",
                "inventory_coverage",
                "mapped_record_coverage",
                "measure",
                "observation_refs",
                "population_manifest_hash",
                "probe_coverage",
                "query_slice_coverage",
                "ranking_evidence_hash",
                "reviewed_identity_count",
                "run_id",
                "run_revision",
                "scope_mode",
                "slice_manifest_hash",
                "top_n",
            },
            "query-linked entity coverage",
            optional={"revision"},
        )
        if data.get("contract_version") != QUERY_LINKED_COVERAGE_VERSION:
            raise QueryLinkedCoverageFailure(
                "unsupported_query_linked_coverage",
                "Unsupported query-linked entity coverage contract.",
            )
        if data.get("scope_mode") != "query_linked_slice":
            raise QueryLinkedCoverageFailure(
                "invalid_query_linked_coverage",
                "Query-linked coverage requires scope_mode=query_linked_slice.",
            )
        graph = _object(data.get("graph"), "coverage graph")
        _fields(graph, {"name", "revision"}, "coverage graph")
        measure = _object(data.get("measure"), "coverage measure")
        _fields(measure, {"reference", "sort_direction"}, "coverage measure")
        components_value = data.get("components")
        if not isinstance(components_value, list) or any(
            not isinstance(item, dict) for item in components_value
        ):
            raise QueryLinkedCoverageFailure(
                "invalid_query_linked_coverage", "components must be an array of objects."
            )
        coverage = cls(
            run_id=_identifier(data.get("run_id"), "run_id"),
            run_revision=_sha256(data.get("run_revision"), "run_revision"),
            graph_name=_identifier(graph.get("name"), "graph name"),
            graph_revision=_sha256(graph.get("revision"), "graph revision"),
            population_manifest_hash=_sha256(
                data.get("population_manifest_hash"), "population_manifest_hash"
            ),
            ranking_evidence_hash=_sha256(
                data.get("ranking_evidence_hash"), "ranking_evidence_hash"
            ),
            measure_reference=_reference(measure.get("reference"), "measure reference"),
            sort_direction=_choice(
                measure.get("sort_direction"),
                "sort direction",
                frozenset({"ascending", "descending"}),
            ),
            top_n=_bounded_integer(data.get("top_n"), "top_n", 1, 100_000),
            slice_manifest_hash=_sha256(
                data.get("slice_manifest_hash"), "slice_manifest_hash"
            ),
            declared_component_count=_bounded_integer(
                data.get("declared_component_count"),
                "declared_component_count",
                1,
                _MAX_COMPONENTS,
            ),
            completed_component_count=_integer(
                data.get("completed_component_count"), "completed_component_count"
            ),
            failed_component_count=_integer(
                data.get("failed_component_count"), "failed_component_count"
            ),
            reviewed_identity_count=_integer(
                data.get("reviewed_identity_count"), "reviewed_identity_count"
            ),
            inventory_coverage=_rate(data.get("inventory_coverage"), "inventory_coverage"),
            query_slice_coverage=_rate(
                data.get("query_slice_coverage"), "query_slice_coverage"
            ),
            probe_coverage=_rate(data.get("probe_coverage"), "probe_coverage"),
            mapped_record_coverage=_rate(
                data.get("mapped_record_coverage"), "mapped_record_coverage"
            ),
            components=tuple(QueryLinkedComponent.from_dict(item) for item in components_value),
        )
        _validate_coverage(coverage, data)
        expected_revision = data.get("revision")
        if expected_revision is not None and expected_revision != coverage.revision:
            raise QueryLinkedCoverageFailure(
                "invalid_query_linked_coverage",
                "Query-linked coverage revision does not match its content.",
            )
        return coverage


def _validate_component(component: QueryLinkedComponent) -> None:
    if (component.status == "failed") != (component.error_category is not None):
        raise QueryLinkedCoverageFailure(
            "invalid_query_linked_coverage",
            "Only failed components require a sanitized error category.",
        )
    if component.status != "failed" and component.model is None:
        raise QueryLinkedCoverageFailure(
            "incomplete_query_linked_provenance",
            "Successfully reviewed components require model provenance.",
        )
    if component.status == "no_match" and (
        component.discovery_candidate_refs or component.entity_candidate_refs
    ):
        raise QueryLinkedCoverageFailure(
            "invalid_query_linked_coverage", "no_match components cannot reference candidates."
        )
    if component.status == "proposed_and_rejected" and (
        not component.discovery_candidate_refs or component.entity_candidate_refs
    ):
        raise QueryLinkedCoverageFailure(
            "invalid_query_linked_coverage",
            "proposed_and_rejected requires discovery candidates and no promoted candidates.",
        )
    if component.status.startswith("promoted_") and (
        not component.discovery_candidate_refs or not component.entity_candidate_refs
    ):
        raise QueryLinkedCoverageFailure(
            "invalid_query_linked_coverage",
            "Promoted components require discovery and entity candidate references.",
        )
    if component.status == "failed" and component.entity_candidate_refs:
        raise QueryLinkedCoverageFailure(
            "invalid_query_linked_coverage", "Failed components cannot claim promotion."
        )


def _validate_coverage(
    coverage: QueryLinkedEntityCoverage,
    raw: dict[str, Any],
) -> None:
    ids = [item.id for item in coverage.components]
    if len(ids) != len(set(ids)):
        raise QueryLinkedCoverageFailure(
            "invalid_query_linked_coverage", "Component IDs must be unique."
        )
    if len(coverage.components) > coverage.declared_component_count:
        raise QueryLinkedCoverageFailure(
            "invalid_query_linked_coverage",
            "Stored components cannot exceed declared_component_count.",
        )
    completed = sum(item.status in _SUCCESSFUL_COMPONENT_STATUSES for item in coverage.components)
    failed = sum(item.status == "failed" for item in coverage.components)
    reviewed = sum(item.reviewed_identity_count for item in coverage.components)
    expected_slice = completed / coverage.declared_component_count
    if (
        coverage.completed_component_count != completed
        or coverage.failed_component_count != failed
        or coverage.reviewed_identity_count != reviewed
        or not math.isclose(coverage.query_slice_coverage, expected_slice, abs_tol=1e-9)
    ):
        raise QueryLinkedCoverageFailure(
            "invalid_query_linked_coverage",
            "Coverage counts and query_slice_coverage must match terminal component statuses.",
        )
    if coverage.query_slice_coverage == 1.0 and (
        not coverage.all_components_terminal or coverage.failed_component_count
    ):
        raise QueryLinkedCoverageFailure(
            "invalid_query_linked_coverage",
            "query_slice_coverage=1.0 requires every component to finish without failure.",
        )
    declared_candidate_refs = _reference_array(raw.get("candidate_refs"), "candidate_refs")
    declared_observation_refs = _reference_array(
        raw.get("observation_refs"), "observation_refs"
    )
    if declared_candidate_refs != coverage.candidate_refs:
        raise QueryLinkedCoverageFailure(
            "invalid_query_linked_coverage",
            "candidate_refs must equal the component candidate-reference union.",
        )
    if declared_observation_refs != coverage.observation_refs:
        raise QueryLinkedCoverageFailure(
            "invalid_query_linked_coverage",
            "observation_refs must equal the component observation-reference union.",
        )


def _fields(
    data: dict[str, Any],
    required: set[str],
    label: str,
    *,
    optional: set[str] = frozenset(),
) -> None:
    if set(data) - optional != required or not set(data).issubset(required | optional):
        raise QueryLinkedCoverageFailure(
            "invalid_query_linked_coverage", f"{label} has unexpected or missing fields."
        )


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise QueryLinkedCoverageFailure(
            "invalid_query_linked_coverage", f"{label} must be an object."
        )
    return value


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise QueryLinkedCoverageFailure(
            "invalid_query_linked_coverage", f"{label} must be a bounded identifier."
        )
    return value


def _optional_identifier(value: object, label: str) -> str | None:
    return None if value is None else _identifier(value, label)


def _reference(value: object, label: str) -> str:
    if not isinstance(value, str) or not _REFERENCE.fullmatch(value):
        raise QueryLinkedCoverageFailure(
            "invalid_query_linked_coverage", f"{label} must be a bounded reference."
        )
    return value


def _reference_array(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > _MAX_COMPONENTS:
        raise QueryLinkedCoverageFailure(
            "invalid_query_linked_coverage", f"{label} must be a bounded reference array."
        )
    items = tuple(sorted(_reference(item, label) for item in value))
    if len(items) != len(set(items)):
        raise QueryLinkedCoverageFailure(
            "invalid_query_linked_coverage", f"{label} must contain unique references."
        )
    return items


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise QueryLinkedCoverageFailure(
            "invalid_query_linked_coverage", f"{label} must be a lowercase SHA-256."
        )
    return value


def _choice(value: object, label: str, choices: frozenset[str]) -> str:
    if not isinstance(value, str) or value not in choices:
        raise QueryLinkedCoverageFailure(
            "invalid_query_linked_coverage", f"{label} has an unsupported value."
        )
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise QueryLinkedCoverageFailure(
            "invalid_query_linked_coverage", f"{label} must be a non-negative integer."
        )
    return value


def _bounded_integer(value: object, label: str, minimum: int, maximum: int) -> int:
    parsed = _integer(value, label)
    if not minimum <= parsed <= maximum:
        raise QueryLinkedCoverageFailure(
            "invalid_query_linked_coverage",
            f"{label} must be between {minimum} and {maximum}.",
        )
    return parsed


def _rate(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise QueryLinkedCoverageFailure(
            "invalid_query_linked_coverage", f"{label} must be between zero and one."
        )
    parsed = float(value)
    if not math.isfinite(parsed) or not 0 <= parsed <= 1:
        raise QueryLinkedCoverageFailure(
            "invalid_query_linked_coverage", f"{label} must be between zero and one."
        )
    return parsed
