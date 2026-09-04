"""Shared CLI/SDK concept import, review and conservative metadata retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from tarel.graph.contracts import GraphDocument
from tarel.graph.revision import physical_graph_revision
from tarel.graph.store import FileGraphStore
from tarel.runtime import TarelRuntime
from tarel.semantic_concepts.contracts import (
    ConceptReview,
    SemanticConcept,
    SemanticConceptDocument,
    SemanticConceptFailure,
)
from tarel.semantic_concepts.store import FileSemanticConceptStore
from tarel.topology.endpoint_contracts import (
    LOGICAL_ENDPOINT_MODES,
    LogicalEndpoint,
    LogicalEndpointFailure,
    ResolvedLogicalEndpoint,
)
from tarel.topology.endpoints import resolve_logical_endpoint_for_graph_use_case


@dataclass(frozen=True, slots=True)
class SemanticConceptMatch:
    graph_name: str
    document_revision: str
    concept: SemanticConcept
    usage: str
    resolved_bindings: tuple[ResolvedLogicalEndpoint, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "semantic_concept",
            "artifact": {
                "kind": "semantic_concepts",
                "graph": self.graph_name,
                "id": self.concept.id,
                "revision": self.document_revision,
            },
            "name": self.concept.name,
            "description": self.concept.description,
            "state": self.concept.state,
            "usage": self.usage,
            "requires_runtime_validation": self.usage != "confirmed",
            "parent_ids": sorted(self.concept.parent_ids),
            "bindings": [
                {**resolved.to_dict(), "representation": binding.representation}
                for binding, resolved in zip(
                    self.concept.bindings, self.resolved_bindings, strict=True
                )
            ],
            "evidence_count": len(self.concept.evidence_hashes),
            "producer": self.concept.producer,
            "notice": "Concept representation is metadata, not equality, a join or a rollup rule.",
        }


def save_semantic_concepts_use_case(
    document: SemanticConceptDocument,
    *,
    expected_revision: str | None = None,
    runtime: TarelRuntime | None = None,
) -> SemanticConceptDocument:
    if not isinstance(document, SemanticConceptDocument):
        raise SemanticConceptFailure("invalid_semantic_concepts", "Expected a typed document.")
    document = SemanticConceptDocument.from_dict(document.to_dict())
    graph = _graph(document.graph_name, runtime)
    _require_graph(document, graph)
    store = _store(runtime)
    previous = store.load(document.graph_name) if store.exists(document.graph_name) else None
    if (previous is not None and expected_revision != previous.revision) or (
        previous is None and expected_revision is not None
    ):
        raise SemanticConceptFailure(
            "stale_semantic_concepts",
            "Replacing concepts requires their current document revision.",
        )
    if previous is not None and previous.graph_revision != document.graph_revision:
        raise SemanticConceptFailure(
            "semantic_concepts_rebase_forbidden",
            "Concept audit records cannot be rebound to a graph.",
        )
    old = {item.id: item for item in previous.concepts} if previous else {}
    new = {item.id: item for item in document.concepts}
    changed: list[SemanticConcept] = []
    for identifier, concept in new.items():
        if concept == old.get(identifier):
            continue
        if identifier in old and old[identifier].state != "candidate":
            raise SemanticConceptFailure(
                "immutable_semantic_concept",
                "Reviewed/rejected concepts are immutable audit records.",
            )
        if concept.state != "candidate":
            raise SemanticConceptFailure(
                "invalid_semantic_concepts_import",
                "New and changed concepts must be candidates.",
            )
        changed.append(concept)
    if any(item.state != "candidate" and identifier not in new for identifier, item in old.items()):
        raise SemanticConceptFailure(
            "immutable_semantic_concept",
            "Imports cannot remove reviewed/rejected audit records.",
        )
    # Unchanged audit records may describe old endpoint revisions. They remain inspectable,
    # but only changed declarations can enter current use through this import.
    dependencies = _dependency_order(new, {item.id for item in changed})
    if any(new[identifier].state == "rejected" for identifier in dependencies):
        raise SemanticConceptFailure(
            "semantic_concept_policy_excluded",
            "A parent concept has been rejected.",
        )
    _resolve_bindings(graph, tuple(new[identifier] for identifier in dependencies), runtime)
    store.save(document)
    return document


def load_semantic_concepts_use_case(
    graph_name: str,
    *,
    runtime: TarelRuntime | None = None,
) -> SemanticConceptDocument:
    """Load the audit artifact; use find for current, policy-filtered context."""
    return _store(runtime).load(graph_name)


def review_semantic_concept_use_case(
    graph_name: str,
    concept_id: str,
    *,
    decision: str,
    reason: str,
    expected_revision: str,
    runtime: TarelRuntime | None = None,
) -> SemanticConceptDocument:
    if not isinstance(concept_id, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", concept_id
    ):
        raise SemanticConceptFailure("invalid_semantic_concept_query", "Invalid concept ID.")
    document = load_semantic_concepts_use_case(graph_name, runtime=runtime)
    if document.revision != expected_revision:
        raise SemanticConceptFailure("stale_semantic_concepts", "Reload concepts before review.")
    graph = _graph(graph_name, runtime)
    _require_graph(document, graph)
    by_id = {item.id: item for item in document.concepts}
    concept = by_id.get(concept_id)
    if concept is None:
        raise SemanticConceptFailure("semantic_concept_not_found", "Concept not found.")
    if concept.state != "candidate":
        raise SemanticConceptFailure(
            "semantic_concept_already_reviewed", "Concept is already reviewed."
        )
    review = ConceptReview(decision, reason)
    if decision == "approve":
        dependencies = _dependency_order(by_id, {concept_id})
        _resolve_bindings(graph, tuple(by_id[identifier] for identifier in dependencies), runtime)
        if any(by_id[identifier].state == "rejected" for identifier in dependencies):
            raise SemanticConceptFailure(
                "semantic_concept_policy_excluded",
                "A parent concept has been rejected.",
            )
    by_id[concept_id] = replace(
        concept,
        state="reviewed" if decision == "approve" else "rejected",
        review=review,
    )
    changed = replace(document, concepts=tuple(by_id.values()))
    _store(runtime).save(changed)
    return changed


def find_semantic_concepts_use_case(
    graph_name: str,
    *,
    query: str | None = None,
    concept_id: str | None = None,
    endpoint: LogicalEndpoint | None = None,
    allowed_object_ids: frozenset[str] | None = None,
    object_ids: frozenset[str] | None = None,
    mode: str = "confirmed_only",
    limit: int = 20,
    runtime: TarelRuntime | None = None,
) -> tuple[SemanticConceptMatch, ...]:
    if not isinstance(mode, str) or mode not in LOGICAL_ENDPOINT_MODES:
        raise SemanticConceptFailure("invalid_semantic_concept_mode", "Unknown concept policy.")
    if concept_id is not None and (
        not isinstance(concept_id, str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", concept_id)
    ):
        raise SemanticConceptFailure("invalid_semantic_concept_query", "Invalid concept ID.")
    if (
        (query is not None and (not isinstance(query, str) or len(query) > 1000))
        or (endpoint is not None and not isinstance(endpoint, LogicalEndpoint))
        or (
            allowed_object_ids is not None
            and (
                not isinstance(allowed_object_ids, frozenset)
                or any(not isinstance(identifier, str) for identifier in allowed_object_ids)
            )
        )
        or (
            object_ids is not None
            and (
                not isinstance(object_ids, frozenset)
                or any(not isinstance(identifier, str) for identifier in object_ids)
            )
        )
        or type(limit) is not int
        or not 1 <= limit <= 100
    ):
        raise SemanticConceptFailure(
            "invalid_semantic_concept_query", "Invalid bounded concept query."
        )
    store = _store(runtime)
    if not store.exists(graph_name):
        return ()
    document = store.load(graph_name)
    graph = _graph(graph_name, runtime)
    _require_graph(document, graph)
    by_id = {item.id: item for item in document.concepts}
    selected = {
        item.id
        for item in document.concepts
        if item.state != "rejected"
        and (concept_id is None or item.id == concept_id)
        and (mode != "confirmed_only" or item.state == "reviewed")
        and (
            not query or query.casefold() in f"{item.id} {item.name} {item.description}".casefold()
        )
        and (endpoint is None or any(binding.endpoint == endpoint for binding in item.bindings))
    }
    usage: dict[str, str | None] = {}
    bindings: dict[str, tuple[ResolvedLogicalEndpoint, ...]] = {}
    cache: dict[LogicalEndpoint, ResolvedLogicalEndpoint] = {}
    for identifier in _dependency_order(by_id, selected):
        concept = by_id[identifier]
        if concept.state == "rejected" or any(
            usage[parent] is None for parent in concept.parent_ids
        ):
            usage[identifier] = None
            continue
        try:
            resolved = _resolve_bindings(graph, (concept,), runtime, cache)[identifier]
        except LogicalEndpointFailure as exc:
            if exc.code != "logical_endpoint_policy_excluded":
                raise
            usage[identifier] = None
            continue
        if allowed_object_ids is not None and any(
            not set(item.physical_object_ids) <= allowed_object_ids for item in resolved
        ):
            usage[identifier] = None
            continue
        bindings[identifier] = resolved
        usage[identifier] = (
            "confirmed"
            if (
                concept.state == "reviewed"
                and all(item.usage == "confirmed" for item in resolved)
                and all(usage[parent] == "confirmed" for parent in concept.parent_ids)
            )
            else "exploratory_only"
        )
    return tuple(
        SemanticConceptMatch(
            graph_name,
            document.revision,
            by_id[identifier],
            usage[identifier],
            bindings[identifier],
        )
        for identifier in sorted(selected)
        if usage[identifier] is not None
        and (mode != "confirmed_only" or usage[identifier] == "confirmed")
        and (
            object_ids is None
            or any(
                object_ids.intersection(item.physical_object_ids) for item in bindings[identifier]
            )
        )
    )[:limit]


def _dependency_order(concepts: dict[str, SemanticConcept], selected: set[str]) -> tuple[str, ...]:
    needed: set[str] = set()
    queue = list(selected)
    while queue:
        identifier = queue.pop()
        if identifier in needed:
            continue
        needed.add(identifier)
        queue.extend(concepts[identifier].parent_ids)
    pending = {identifier: len(concepts[identifier].parent_ids) for identifier in needed}
    children: dict[str, list[str]] = {identifier: [] for identifier in needed}
    for identifier in needed:
        for parent in concepts[identifier].parent_ids:
            children[parent].append(identifier)
    queue = [identifier for identifier, count in pending.items() if not count]
    ordered: list[str] = []
    while queue:
        identifier = queue.pop()
        ordered.append(identifier)
        for child in children[identifier]:
            pending[child] -= 1
            if not pending[child]:
                queue.append(child)
    return tuple(ordered)


def _resolve_bindings(
    graph: GraphDocument,
    concepts: tuple[SemanticConcept, ...],
    runtime: TarelRuntime | None,
    cache: dict[LogicalEndpoint, ResolvedLogicalEndpoint] | None = None,
) -> dict[str, tuple[ResolvedLogicalEndpoint, ...]]:
    resolved = {} if cache is None else cache
    result: dict[str, tuple[ResolvedLogicalEndpoint, ...]] = {}
    for concept in concepts:
        for binding in concept.bindings:
            if binding.endpoint not in resolved:
                resolved[binding.endpoint] = resolve_logical_endpoint_for_graph_use_case(
                    graph,
                    binding.endpoint,
                    mode="include_candidates",
                    runtime=runtime,
                )
        result[concept.id] = tuple(resolved[binding.endpoint] for binding in concept.bindings)
    return result


def _require_graph(document: SemanticConceptDocument, graph: GraphDocument) -> None:
    if document.graph_name != graph.name or document.graph_revision != physical_graph_revision(
        graph
    ):
        raise SemanticConceptFailure(
            "semantic_concepts_graph_revision_mismatch",
            "Concept physical graph changed.",
        )


def _graph(graph_name: str, runtime: TarelRuntime | None) -> GraphDocument:
    return (runtime.graph_store() if runtime else FileGraphStore()).load(graph_name)


def _store(runtime: TarelRuntime | None) -> FileSemanticConceptStore:
    return FileSemanticConceptStore(runtime.root / "semantic-concepts" if runtime else None)
