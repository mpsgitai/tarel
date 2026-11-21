"""``tarel.discovery``, ``tarel.reference_mapping`` and ``tarel.entity_resolution``."""

from __future__ import annotations

from typing import Any

from tarel.discovery.advice import (
    DiscoveryAdviceResult,
    advise_discovery_run_use_case,
)
from tarel.discovery.application import (
    DiscoveryChangeResult,
    DiscoveryMatch,
    find_discovery_candidates_use_case,
    list_discovery_runs_use_case,
    load_discovery_run_use_case,
    start_discovery_run_use_case,
    submit_discovery_step_use_case,
)
from tarel.discovery.coverage import QueryLinkedEntityCoverage
from tarel.discovery.coverage_application import (
    DiscoveryCoverageResult,
    load_query_linked_coverage_use_case,
    record_query_linked_coverage_use_case,
)
from tarel.discovery.promotion import (
    DiscoveryPromotionResult,
    promote_discovery_candidates_use_case,
)
from tarel.discovery.runs import (
    DiscoveryRun,
)
from tarel.discovery.tasks import (
    DiscoveryTask,
    next_discovery_task_use_case,
)
from tarel.entity_resolution.application import (
    EntityResolutionChangeResult,
    decide_entity_resolution_candidate_use_case,
    find_entity_resolution_candidates_use_case,
    import_entity_resolution_candidate_use_case,
    list_entity_resolution_candidates_use_case,
    load_entity_resolution_candidate_use_case,
    resolve_entity_aliases_use_case,
)
from tarel.entity_resolution.candidates import (
    EntityAliasMatch,
    EntityResolutionCandidate,
    EntityResolutionMatch,
)
from tarel.reference_mapping.application import (
    ReferenceMappingChangeResult,
    decide_reference_mapping_candidate_use_case,
    find_reference_mapping_candidates_use_case,
    import_reference_mapping_candidate_use_case,
    list_reference_mapping_candidates_use_case,
    load_reference_mapping_candidate_use_case,
)
from tarel.reference_mapping.contracts import ReferenceMappingCandidate, ReferenceMappingMatch
from tarel.sdk._base import RuntimeAPI


class DiscoveryAPI(RuntimeAPI):
    """Start and continue optional, bounded coding-agent discovery runs."""

    def start(
        self,
        kind: str,
        *,
        graph: str,
        sources: tuple[str, ...] = (),
        question: str | None = None,
        probe_budget: int = 40,
        candidate_budget: int = 20,
        advisor_provider: str | None = None,
        identity_inspection: bool = False,
        logical_endpoints: bool = False,
        scope_mode: str = "global_population",
        run_id: str | None = None,
    ) -> DiscoveryChangeResult:
        return start_discovery_run_use_case(
            kind,
            graph_name=graph,
            source_names=sources,
            question=question,
            probe_budget=probe_budget,
            candidate_budget=candidate_budget,
            advisor_provider=advisor_provider,
            identity_inspection=identity_inspection,
            logical_endpoints=logical_endpoints,
            scope_mode=scope_mode,
            run_id=run_id,
            runtime=self._runtime,
        )

    def load(self, run_id: str) -> DiscoveryRun:
        return load_discovery_run_use_case(run_id, runtime=self._runtime)

    def list(
        self,
        *,
        graph: str | None = None,
        kind: str | None = None,
    ) -> tuple[DiscoveryRun, ...]:
        return list_discovery_runs_use_case(
            graph_name=graph, kind=kind, runtime=self._runtime
        )

    def next(self, run_id: str) -> DiscoveryTask:
        return next_discovery_task_use_case(run_id, runtime=self._runtime)

    def submit(
        self,
        run_id: str,
        *,
        expected_revision: str,
        action: str,
        payload: dict[str, Any],
        actor: str = "coding_agent",
    ) -> DiscoveryChangeResult:
        return submit_discovery_step_use_case(
            run_id,
            expected_revision=expected_revision,
            actor=actor,
            action=action,
            payload=payload,
            runtime=self._runtime,
        )

    def advise(
        self,
        run_id: str,
        *,
        expected_revision: str,
        count: int = 3,
        model: str | None = None,
        timeout: float = 120.0,
    ) -> DiscoveryAdviceResult:
        return advise_discovery_run_use_case(
            run_id,
            expected_revision=expected_revision,
            count=count,
            model=model,
            timeout=timeout,
            runtime=self._runtime,
        )

    def promote(
        self,
        run_id: str,
        *,
        candidates: tuple[str, ...],
        reason: str,
        supersedes: str | None = None,
    ) -> DiscoveryPromotionResult:
        """Move a selected candidate into its bounded review path."""
        return promote_discovery_candidates_use_case(
            run_id,
            candidate_ids=candidates,
            reason=reason,
            supersedes_candidate_id=supersedes,
            runtime=self._runtime,
        )

    def find(
        self,
        *,
        graph: str | None = None,
        kind: str | None = None,
        include_exploratory: bool = False,
        query: str | None = None,
        limit: int = 20,
    ) -> tuple[DiscoveryMatch, ...]:
        return find_discovery_candidates_use_case(
            graph_name=graph,
            kind=kind,
            include_exploratory=include_exploratory,
            query=query,
            limit=limit,
            runtime=self._runtime,
        )

    def record_coverage(
        self,
        run_id: str,
        coverage: dict[str, Any],
    ) -> DiscoveryCoverageResult:
        """Record one value-free query-linked coverage document."""
        return record_query_linked_coverage_use_case(
            run_id,
            coverage,
            runtime=self._runtime,
        )

    def load_coverage(self, run_id: str) -> QueryLinkedEntityCoverage:
        return load_query_linked_coverage_use_case(run_id, runtime=self._runtime)


class ReferenceMappingAPI(RuntimeAPI):
    """Import, retrieve, and review directed physical-field mappings."""

    def import_candidate(
        self,
        candidate: ReferenceMappingCandidate,
    ) -> ReferenceMappingChangeResult:
        return import_reference_mapping_candidate_use_case(
            candidate,
            runtime=self._runtime,
        )

    def load(self, candidate_id: str) -> ReferenceMappingCandidate:
        return load_reference_mapping_candidate_use_case(
            candidate_id,
            runtime=self._runtime,
        )

    def list(
        self,
        *,
        graph: str | None = None,
    ) -> tuple[ReferenceMappingCandidate, ...]:
        return list_reference_mapping_candidates_use_case(
            graph_name=graph,
            runtime=self._runtime,
        )

    def find(
        self,
        graph: str,
        *,
        source: str | None = None,
        target: str | None = None,
        mode: str = "confirmed_then_candidates",
    ) -> tuple[ReferenceMappingMatch, ...]:
        return find_reference_mapping_candidates_use_case(
            graph,
            source=source,
            target=target,
            mode=mode,
            runtime=self._runtime,
        )

    def decide(
        self,
        candidate_id: str,
        *,
        decision: str,
        reason: str,
        expected_revision: str,
    ) -> ReferenceMappingChangeResult:
        return decide_reference_mapping_candidate_use_case(
            candidate_id,
            decision=decision,
            reason=reason,
            expected_revision=expected_revision,
            runtime=self._runtime,
        )


class EntityResolutionAPI(RuntimeAPI):
    """Import, retrieve, and review bounded entity-resolution hypotheses."""

    def import_candidate(
        self,
        candidate: EntityResolutionCandidate,
    ) -> EntityResolutionChangeResult:
        return import_entity_resolution_candidate_use_case(
            candidate,
            runtime=self._runtime,
        )

    def load(self, candidate_id: str) -> EntityResolutionCandidate:
        return load_entity_resolution_candidate_use_case(
            candidate_id,
            runtime=self._runtime,
        )

    def list(
        self,
        *,
        graph: str | None = None,
    ) -> tuple[EntityResolutionCandidate, ...]:
        return list_entity_resolution_candidates_use_case(
            graph_name=graph,
            runtime=self._runtime,
        )

    def find(
        self,
        graph: str,
        *,
        source: str | None = None,
        target: str | None = None,
        mode: str = "confirmed_then_candidates",
    ) -> tuple[EntityResolutionMatch, ...]:
        return find_entity_resolution_candidates_use_case(
            graph,
            source=source,
            target=target,
            mode=mode,
            runtime=self._runtime,
        )

    def decide(
        self,
        candidate_id: str,
        *,
        decision: str,
        reason: str,
        expected_revision: str | None = None,
    ) -> EntityResolutionChangeResult:
        return decide_entity_resolution_candidate_use_case(
            candidate_id,
            decision=decision,
            reason=reason,
            expected_revision=expected_revision,
            runtime=self._runtime,
        )

    def resolve(
        self,
        graph: str,
        *,
        object: str,
        key: str,
        mode: str = "confirmed_then_candidates",
    ) -> tuple[EntityAliasMatch, ...]:
        """Resolve one record key through protected same-object alias groups."""
        return resolve_entity_aliases_use_case(
            graph,
            object_reference=object,
            record_key=key,
            mode=mode,
            runtime=self._runtime,
        )
