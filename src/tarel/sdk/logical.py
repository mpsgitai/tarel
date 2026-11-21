"""``tarel.logical_joins``, ``tarel.concepts`` and ``tarel.topology``: the logical layer."""

from __future__ import annotations

from tarel.graph.application import load_graph_use_case
from tarel.logical_joins.application import (
    LogicalJoinMatch,
    find_logical_joins_use_case,
    list_logical_joins_use_case,
    load_logical_join_use_case,
    review_logical_join_use_case,
)
from tarel.logical_joins.contracts import LogicalJoin
from tarel.sdk._base import RuntimeAPI
from tarel.semantic_concepts.application import (
    SemanticConceptMatch,
    find_semantic_concepts_use_case,
    load_semantic_concepts_use_case,
    review_semantic_concept_use_case,
    save_semantic_concepts_use_case,
)
from tarel.semantic_concepts.contracts import SemanticConceptDocument
from tarel.topology.application import (
    decide_derived_relation_use_case,
    list_logical_topologies_use_case,
    load_logical_topology_use_case,
    new_logical_topology_document,
    save_logical_topology_use_case,
)
from tarel.topology.contracts import DerivedRelation, LogicalTopologyDocument
from tarel.topology.endpoint_contracts import LogicalEndpoint


class LogicalJoinsAPI(RuntimeAPI):
    """Find and review logical joins between objects of different graphs."""

    def load(self, join_id: str) -> LogicalJoin:
        return load_logical_join_use_case(join_id, runtime=self._runtime)

    def list(self, *, graph: str | None = None) -> tuple[LogicalJoin, ...]:
        return list_logical_joins_use_case(graph_name=graph, runtime=self._runtime)

    def find(
        self, graph: str, *, mode: str = "confirmed_only", endpoint: LogicalEndpoint | None = None,
        join_id: str | None = None, limit: int = 20,
    ) -> tuple[LogicalJoinMatch, ...]:
        return find_logical_joins_use_case(
            graph, mode=mode, endpoint=endpoint, join_id=join_id, limit=limit,
            runtime=self._runtime,
        )

    def review(
        self, join_id: str, *, expected_revision: str, decision: str, reason: str,
    ) -> LogicalJoin:
        return review_logical_join_use_case(
            join_id, expected_revision=expected_revision, decision=decision, reason=reason,
            runtime=self._runtime,
        )


class ConceptsAPI(RuntimeAPI):
    """Optional reviewed concept representations and explicit parent hierarchies."""

    def import_document(
        self, document: SemanticConceptDocument, *, expected_revision: str | None = None,
    ) -> SemanticConceptDocument:
        return save_semantic_concepts_use_case(
            document, expected_revision=expected_revision, runtime=self._runtime,
        )

    def load(self, graph: str) -> SemanticConceptDocument:
        return load_semantic_concepts_use_case(graph, runtime=self._runtime)

    def find(
        self, graph: str, *, query: str | None = None, endpoint: LogicalEndpoint | None = None,
        mode: str = "confirmed_only", limit: int = 20, concept_id: str | None = None,
        allowed_object_ids: frozenset[str] | None = None,
    ) -> tuple[SemanticConceptMatch, ...]:
        return find_semantic_concepts_use_case(
            graph, query=query, endpoint=endpoint, mode=mode, limit=limit, concept_id=concept_id,
            allowed_object_ids=allowed_object_ids, runtime=self._runtime,
        )

    def review(
        self, graph: str, concept_id: str, *, expected_revision: str, decision: str, reason: str,
    ) -> SemanticConceptDocument:
        return review_semantic_concept_use_case(
            graph, concept_id, expected_revision=expected_revision, decision=decision,
            reason=reason, runtime=self._runtime,
        )


class TopologyAPI(RuntimeAPI):
    """Persist typed logical relations without executing their plans."""

    def document(
        self,
        graph: str,
        derived_relations: tuple[DerivedRelation, ...],
    ) -> LogicalTopologyDocument:
        return new_logical_topology_document(
            load_graph_use_case(graph, runtime=self._runtime),
            derived_relations,
        )

    def import_document(
        self,
        document: LogicalTopologyDocument,
        *,
        expected_revision: str | None = None,
    ) -> LogicalTopologyDocument:
        return save_logical_topology_use_case(
            document,
            expected_revision=expected_revision,
            runtime=self._runtime,
        )

    def load(self, graph: str) -> LogicalTopologyDocument:
        return load_logical_topology_use_case(graph, runtime=self._runtime)

    def list(self) -> tuple[LogicalTopologyDocument, ...]:
        return list_logical_topologies_use_case(runtime=self._runtime)

    def review(
        self,
        graph: str,
        relation_id: str,
        *,
        decision: str,
        reason: str,
        expected_revision: str,
    ) -> LogicalTopologyDocument:
        return decide_derived_relation_use_case(
            graph,
            relation_id,
            decision=decision,
            reason=reason,
            expected_revision=expected_revision,
            runtime=self._runtime,
        )
