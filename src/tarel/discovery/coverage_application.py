"""Query-linked entity coverage use cases: record, load and list coverage reports."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tarel.discovery.checks import validate_current_graph
from tarel.discovery.contracts import DiscoveryFailure
from tarel.discovery.coverage import QueryLinkedCoverageFailure, QueryLinkedEntityCoverage
from tarel.discovery.runs import DiscoveryRun
from tarel.entity_resolution.application import load_entity_resolution_candidate_use_case
from tarel.entity_resolution.contracts import (
    EntityResolutionFailure,
)
from tarel.graph.revision import graph_revision
from tarel.runtime import TarelRuntime, resolve_runtime


@dataclass(frozen=True, slots=True)
class DiscoveryCoverageResult:
    coverage: QueryLinkedEntityCoverage
    path: Path
    created: bool


def record_query_linked_coverage_use_case(
    run_id: str,
    payload: dict[str, Any],
    *,
    runtime: TarelRuntime | None = None,
) -> DiscoveryCoverageResult:
    """Persist one private, aggregate-only coverage document for a completed run."""
    store = resolve_runtime(runtime).discovery_store()
    run = store.load(run_id)
    if run.status != "completed" or run.kind != "entity_matching":
        raise DiscoveryFailure(
            "invalid_query_linked_coverage",
            "Query-linked coverage requires one completed entity-matching run.",
        )
    if run.scope_mode != "query_linked_slice":
        raise DiscoveryFailure(
            "invalid_query_linked_coverage",
            "The discovery run was not declared as query_linked_slice.",
        )
    try:
        coverage = QueryLinkedEntityCoverage.from_dict(payload)
    except QueryLinkedCoverageFailure as exc:
        raise DiscoveryFailure(exc.code, str(exc)) from exc
    graph = validate_current_graph(run, runtime=runtime)
    if (
        coverage.run_id != run.id
        or coverage.run_revision != run.revision
        or coverage.graph_name != run.graph_name
        or coverage.graph_revision != graph_revision(graph)
    ):
        raise DiscoveryFailure(
            "query_linked_coverage_binding_mismatch",
            "Coverage must bind the completed discovery run and current graph revision.",
        )
    _validate_query_linked_references(run, coverage, runtime=runtime)
    if store.coverage_exists(run.id):
        current = store.load_coverage(run.id)
        if current == coverage:
            return DiscoveryCoverageResult(
                coverage=current,
                path=store.coverage_path(run.id),
                created=False,
            )
        raise DiscoveryFailure(
            "query_linked_coverage_exists",
            "Query-linked coverage is create-only for one completed discovery run.",
        )
    return DiscoveryCoverageResult(
        coverage=coverage,
        path=store.save_coverage(coverage),
        created=True,
    )


def load_query_linked_coverage_use_case(
    run_id: str,
    *,
    runtime: TarelRuntime | None = None,
) -> QueryLinkedEntityCoverage:
    return resolve_runtime(runtime).discovery_store().load_coverage(run_id)


def list_query_linked_coverages_use_case(
    *,
    graph_name: str | None = None,
    runtime: TarelRuntime | None = None,
) -> tuple[QueryLinkedEntityCoverage, ...]:
    store = resolve_runtime(runtime).discovery_store()
    coverages = (
        store.load_coverage(run_id)
        for run_id in store.list()
        if store.coverage_exists(run_id)
    )
    return tuple(
        item
        for item in coverages
        if graph_name is None or item.graph_name == graph_name
    )


def _validate_query_linked_references(
    run: DiscoveryRun,
    coverage: QueryLinkedEntityCoverage,
    *,
    runtime: TarelRuntime | None,
) -> None:
    discovery_candidates = {item.id: item for item in run.candidates}
    observations = {
        item.id: item
        for candidate in run.candidates
        for item in candidate.observations
    }
    referenced_observations = []
    for component in coverage.components:
        component_discovery = []
        for candidate_id in component.discovery_candidate_refs:
            candidate = discovery_candidates.get(candidate_id)
            if candidate is None:
                raise DiscoveryFailure(
                    "query_linked_reference_not_found",
                    f"Discovery candidate reference not found: {candidate_id}",
                )
            component_discovery.append(candidate)
        component_entities = []
        for candidate_id in component.entity_candidate_refs:
            try:
                entity_candidate = load_entity_resolution_candidate_use_case(
                    candidate_id, runtime=runtime
                )
            except EntityResolutionFailure as exc:
                raise DiscoveryFailure(
                    "query_linked_reference_not_found",
                    f"Entity entity_candidate reference not found: {candidate_id}",
                ) from exc
            if entity_candidate.provenance.run_id != run.id:
                raise DiscoveryFailure(
                    "query_linked_coverage_binding_mismatch",
                    "Promoted entity candidates must originate from the coverage run.",
                )
            component_entities.append(entity_candidate)
        component_observations = []
        for observation_id in component.observation_refs:
            observation = observations.get(observation_id)
            if observation is None:
                raise DiscoveryFailure(
                    "query_linked_reference_not_found",
                    f"Discovery observation reference not found: {observation_id}",
                )
            execution = observation.execution
            if execution is None or (
                execution.executor_id != component.executor.id
                or execution.executor_version != component.executor.version
                or execution.artifact_hash != component.executor.artifact_hash
            ):
                raise DiscoveryFailure(
                    "incomplete_query_linked_provenance",
                    "Referenced observations must match the component executor provenance.",
                )
            component_observations.append(observation)
            referenced_observations.append(observation)
        if component.status == "proposed_and_rejected" and any(
            item.state != "rejected" for item in component_discovery
        ):
            raise DiscoveryFailure(
                "invalid_query_linked_coverage",
                "proposed_and_rejected references must be rejected discovery candidates.",
            )
        if component.status.startswith("promoted_"):
            if any(item.state != "selected" for item in component_discovery):
                raise DiscoveryFailure(
                    "invalid_query_linked_coverage",
                    "Promoted components must reference selected discovery candidates.",
                )
            expected_state = (
                "reviewed"
                if component.status == "promoted_confirmed"
                else "candidate"
            )
            if any(item.state != expected_state for item in component_entities):
                raise DiscoveryFailure(
                    "invalid_query_linked_coverage",
                    "Promoted component status must match current entity review state.",
                )
            discovery_ids = {item.id for item in component_discovery}
            if any(
                item.provenance.discovery_candidate_id not in discovery_ids
                for item in component_entities
            ):
                raise DiscoveryFailure(
                    "query_linked_coverage_binding_mismatch",
                    "Promoted candidates must reference this component's discovery candidates.",
                )
        if component.status == "failed" and component_observations and any(
            item.status != "failed" for item in component_observations
        ):
            raise DiscoveryFailure(
                "invalid_query_linked_coverage",
                "Failed components may reference only failed observations.",
            )
    unique_observations = {item.id: item for item in referenced_observations}
    expected_probe_coverage = (
        sum(item.status == "succeeded" for item in unique_observations.values())
        / len(unique_observations)
        if unique_observations
        else 0.0
    )
    if not math.isclose(
        coverage.probe_coverage, expected_probe_coverage, abs_tol=1e-9
    ):
        raise DiscoveryFailure(
            "invalid_query_linked_coverage",
            "probe_coverage must equal successful referenced probes / all referenced probes.",
        )
