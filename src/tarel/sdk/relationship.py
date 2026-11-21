"""``tarel.relationship``: add, check, discover and review relationships."""

from __future__ import annotations

from pathlib import Path

from tarel.connectors.contracts import RelationshipPairProfile
from tarel.graph.contracts import GraphEdge
from tarel.relationships.application import (
    RelationshipChangeResult,
    RelationshipDiscoveryResult,
    add_relationship_use_case,
    check_relationship_use_case,
    decide_relationship_use_case,
    discover_relationships_use_case,
    list_relationships_use_case,
)
from tarel.sdk._base import RuntimeAPI


class RelationshipAPI(RuntimeAPI):
    """Add, check, discover and review join relationships inside one graph."""

    def list(self, graph: str) -> tuple[GraphEdge, ...]:
        return list_relationships_use_case(graph, runtime=self._runtime)

    def add(
        self,
        graph: str,
        *,
        source: str,
        target: str,
        reason: str,
        validated: bool = False,
    ) -> RelationshipChangeResult:
        return add_relationship_use_case(
            graph,
            from_reference=source,
            to_reference=target,
            reason=reason,
            validated=validated,
            runtime=self._runtime,
        )

    def check(
        self,
        graph: str,
        *,
        source: str,
        target: str,
        config: str | Path,
        row_limit: int = 10_000,
    ) -> RelationshipPairProfile:
        return check_relationship_use_case(
            graph,
            from_reference=source,
            to_reference=target,
            config_path=Path(config),
            row_limit=row_limit,
            runtime=self._runtime,
        )

    def discover(
        self,
        graph: str,
        *,
        object_reference: str,
        config: str | Path,
        field: str | None = None,
        max_pairs: int = 20,
        row_limit: int = 10_000,
        min_source_coverage: float = 0.85,
        min_overlap_count: int = 3,
        min_target_uniqueness: float = 0.9,
        persist: bool = True,
        focus: str | None = None,
        expand_one_hop: bool = False,
    ) -> RelationshipDiscoveryResult:
        return discover_relationships_use_case(
            graph,
            object_reference=object_reference,
            field_name=field,
            config_path=Path(config),
            max_pairs=max_pairs,
            row_limit=row_limit,
            min_source_coverage=min_source_coverage,
            min_overlap_count=min_overlap_count,
            min_target_uniqueness=min_target_uniqueness,
            persist=persist,
            focus_name=focus,
            expand_one_hop=expand_one_hop,
            runtime=self._runtime,
        )

    def decide(
        self,
        graph: str,
        edge_id: str,
        *,
        state: str,
        reason: str,
    ) -> RelationshipChangeResult:
        return decide_relationship_use_case(
            graph,
            edge_id=edge_id,
            state=state,
            reason=reason,
            runtime=self._runtime,
        )
