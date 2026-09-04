"""Name-only family retrieval, without embedding member lists or changing physical search."""

from __future__ import annotations

from dataclasses import replace

from tarel.graph.contracts import GraphDocument, GraphNode
from tarel.object_families.application import project_families_for_graphs_use_case
from tarel.runtime import TarelRuntime
from tarel.search import FamilySearchReference, SearchHit, SearchResults, _score_object
from tarel.workspaces.projection import scoped_node_id


def family_name_hits(
    graph: GraphDocument,
    results: SearchResults,
    *,
    mode: str | None,
    namespace: str | None = None,
    object_ids: frozenset[str] | None = None,
    scoped: bool = False,
    runtime: TarelRuntime | None = None,
) -> tuple[SearchHit, ...]:
    if mode is None:
        return ()
    projection = project_families_for_graphs_use_case((graph,), mode=mode, runtime=runtime)
    visible = {
        node.id
        for node in graph.nodes
        if node.type in {"table", "view"}
        and (object_ids is None or node.id in object_ids)
        and (
            namespace is None
            or str(node.metadata.get("namespace", "")).casefold() == namespace.casefold()
        )
    }
    hits = []
    for family in projection.families:
        count = len(visible.intersection(family.member_ids))
        if not count:
            continue
        node = GraphNode(
            id=f"object_family:{family.id}",
            type="object_family",
            label=family.name,
            metadata={"name": family.name},
        )
        hit = _score_object(node, [], results.terms, annotation_states=frozenset())
        if hit is not None:
            hits.append(
                replace(
                    hit,
                    id=scoped_node_id(graph.name, hit.id) if scoped else hit.id,
                    label=f"{graph.name}:{hit.label}" if scoped else hit.label,
                    source_graph=graph.name,
                    reasons=("logical_family_name", *hit.reasons),
                    family=FamilySearchReference(family.id, family.revision, family.state, count),
                )
            )
    return tuple(hits)


def with_family_hits(
    results: SearchResults,
    families: tuple[SearchHit, ...],
    *,
    limit: int,
) -> SearchResults:
    if not families:
        return results
    # Scores from lexical, BM25 and vector retrieval are not comparable. Name-only
    # logical matches form an explicit first group; physical ranking is unchanged.
    ordered = sorted(families, key=lambda hit: (-hit.score, hit.label.casefold(), hit.id))
    return replace(results, hits=tuple((*ordered, *results.hits)[:limit]))
