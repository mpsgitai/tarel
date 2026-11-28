"""Pure aggregation of per-graph retrieval results for one workspace scope.

Two optional, deterministic passes run after ranking and before the limit:

- ``signatures`` folds structural duplicates (the same object name and column names, compared
  without case and punctuation, as in the same schema exported to several SQL dialects) into
  the best-ranked copy, which lists the others in ``duplicates``. Only copies from *other*
  graphs fold, at most one per graph: inside one graph, ``raw.Sales`` and ``mart.Sales`` with
  equal columns are usually source and target, not copies;
- ``diversity="per_graph"`` keeps at most ``max_per_graph`` hits per graph and reports how many
  it left out per graph, so one large graph cannot fill the whole result.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import replace

from tarel.graph.contracts import GraphDocument
from tarel.search import FieldSearchHit, SearchFailure, SearchHit, SearchResults
from tarel.workspaces.projection import scoped_node_id, workspace_graph_name
from tarel.workspaces.scope import ResolvedScope


def combine_workspace_search(
    scope: ResolvedScope,
    results: tuple[SearchResults, ...],
    *,
    query: str,
    mode: str,
    limit: int,
    signatures: Mapping[tuple[str, str], str] | None = None,
    diversity: str = "none",
    max_per_graph: int | None = None,
) -> SearchResults:
    allowed = {(item.graph, item.object_id) for item in scope.objects}
    hits: list[SearchHit] = []
    for result in results:
        graph_name = result.graph
        for hit in result.hits:
            if (graph_name, hit.id) not in allowed:
                continue
            hits.append(
                SearchHit(
                    id=scoped_node_id(graph_name, hit.id),
                    label=f"{graph_name}:{hit.label}",
                    type=hit.type,
                    score=hit.score,
                    matched_terms=hit.matched_terms,
                    reasons=hit.reasons,
                    fields=tuple(
                        FieldSearchHit(
                            id=(
                                scoped_node_id(graph_name, field.id)
                                if field.id
                                else ""
                            ),
                            label=field.label,
                            score=field.score,
                            reasons=field.reasons,
                        )
                        for field in hit.fields
                    ),
                    source_graph=graph_name,
                    namespace=hit.namespace,
                    description=hit.description,
                    role=hit.role,
                    grain=hit.grain,
                    annotation_state=hit.annotation_state,
                    reference=f"{graph_name}:{hit.id}",
                )
            )
    ordered = sorted(hits, key=lambda item: (-item.score, item.label.casefold(), item.id))
    collapsed = 0
    if signatures is not None:
        ordered, collapsed = _collapse_duplicates(ordered, signatures)
    omitted: dict[str, int] = {}
    if diversity == "per_graph":
        ordered, omitted = _per_graph(ordered, max_per_graph or DEFAULT_MAX_PER_GRAPH)
    ranked = tuple(ordered[:limit])
    terms = tuple(sorted({term for result in results for term in result.terms}))
    return SearchResults(
        graph=workspace_graph_name(scope.workspace),
        query=query,
        terms=terms,
        hits=ranked,
        mode=mode,
        workspace=scope.workspace,
        graphs=scope.graph_names,
        scope_hash=scope.scope_hash,
        warnings=scope.warnings,
        diversity=None if diversity == "none" else diversity,
        omitted_by_diversity=tuple(sorted(omitted.items())),
        duplicates_collapsed=collapsed,
    )


DEFAULT_MAX_PER_GRAPH = 3
DIVERSITY_MODES = ("none", "per_graph")


def validate_diversity(diversity: str, max_per_graph: int | None) -> None:
    if diversity not in DIVERSITY_MODES:
        raise SearchFailure(
            "invalid_search_diversity",
            f"Unsupported diversity mode: {diversity}",
            hint="Use one of: none, per_graph.",
            retryable=True,
        )
    if max_per_graph is not None and (diversity != "per_graph" or max_per_graph < 1):
        raise SearchFailure(
            "invalid_search_diversity",
            "max_per_graph needs diversity=per_graph and a value of at least 1.",
            hint="Add --diversity per_graph, or drop --max-per-graph.",
            retryable=True,
        )


def structural_signatures(
    graph: GraphDocument, object_ids: frozenset[str],
) -> dict[str, str]:
    """Object name plus sorted column names, lowercased and stripped of non-alphanumerics."""
    columns: dict[str, list[str]] = {item: [] for item in object_ids}
    names: dict[str, str] = {}
    for node in graph.nodes:
        if node.id in columns:
            name = node.metadata.get("name")
            names[node.id] = _normalized(name if isinstance(name, str) else node.label)
        parent = node.metadata.get("object_id")
        if node.type == "field" and isinstance(parent, str) and parent in columns:
            columns[parent].append(_normalized(node.label))
    return {
        item: "|".join((names[item], *sorted(columns[item])))
        for item in object_ids
        if item in names
    }


def _normalized(value: str) -> str:
    return re.sub(r"[^0-9a-z]", "", value.casefold())


def _collapse_duplicates(
    hits: list[SearchHit], signatures: Mapping[tuple[str, str], str],
) -> tuple[list[SearchHit], int]:
    kept: list[SearchHit] = []
    groups: dict[str, tuple[int, set[str]]] = {}
    collapsed = 0
    for hit in hits:
        assert hit.source_graph is not None and hit.reference is not None
        signature = signatures.get((hit.source_graph, hit.reference.split(":", 1)[1]))
        group = groups.get(signature) if signature is not None else None
        if group is None or hit.source_graph in group[1]:
            if signature is not None and group is None:
                groups[signature] = (len(kept), {hit.source_graph})
            kept.append(hit)
            continue
        index, graphs = group
        graphs.add(hit.source_graph)
        kept[index] = replace(kept[index], duplicates=(*kept[index].duplicates, hit.reference))
        collapsed += 1
    return kept, collapsed


def _per_graph(hits: list[SearchHit], cap: int) -> tuple[list[SearchHit], dict[str, int]]:
    counts: dict[str, int] = {}
    omitted: dict[str, int] = {}
    kept = []
    for hit in hits:
        graph = hit.source_graph or ""
        counts[graph] = counts.get(graph, 0) + 1
        if counts[graph] > cap:
            omitted[graph] = omitted.get(graph, 0) + 1
        else:
            kept.append(hit)
    return kept, omitted
