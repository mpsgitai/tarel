"""Search use cases: rank the objects of one graph or a workspace scope for a query."""

from __future__ import annotations

from dataclasses import replace
from fnmatch import fnmatchcase
from pathlib import Path

from tarel.annotations.states import selected_annotation_states
from tarel.focus.application import focus_object_allowlist
from tarel.graph.contracts import GraphDocument
from tarel.retrieval.application import (
    embedding_backend,
    embedding_model_sha256,
    resolved_embedding_model,
)
from tarel.retrieval.contracts import EmbeddingBackend
from tarel.retrieval.ranking import (
    search_retrieval,
    validate_bm25_weight,
)
from tarel.retrieval.rerank import candidate_limit, rerank_results
from tarel.retrieval.settings import snapshot_runtime
from tarel.runtime import TarelRuntime, resolve_runtime
from tarel.search import (
    SearchFailure,
    SearchFilters,
    SearchInventory,
    SearchResults,
    describe_search_results,
    filter_search_objects,
    role_coverage_warning,
    search_graph,
)
from tarel.workspaces.application import load_workspace_scope
from tarel.workspaces.retrieval import (
    DEFAULT_MAX_PER_GRAPH,
    cap_per_graph,
    combine_workspace_search,
    structural_signatures,
    validate_diversity,
)


def search_graph_use_case(
    name: str,
    query: str,
    *,
    limit: int = 20,
    namespace: str | None = None,
    mode: str = "lexical",
    model_path: Path | None = None,
    n_threads: int | None = None,
    bm25_weight: float | None = None,
    annotation_states: frozenset[str] | None = None,
    validated_only: bool = False,
    family_mode: str | None = "confirmed_only",
    filters: SearchFilters | None = None,
    focuses: tuple[str, ...] = (),
    scope_object_ids: tuple[str, ...] = (),
    runtime: TarelRuntime | None = None,
) -> SearchResults:
    runtime = snapshot_runtime(runtime, model_path=model_path)
    validate_bm25_weight(mode, bm25_weight)
    if not 1 <= limit <= 100:
        raise SearchFailure("invalid_limit", "Search limit must be between 1 and 100.")
    requested_limit = limit
    limit = candidate_limit(runtime, limit)
    graph = resolve_runtime(runtime).graph_store().load(name)
    selected_states = selected_annotation_states(
        annotation_states,
        validated_only=validated_only,
    )
    selected_ids, scoped, scope_warnings = resolve_graph_object_scope(
        source=graph, focuses=focuses, object_ids=scope_object_ids, runtime=runtime,
    )
    object_ids, inventory = filter_search_objects(
        graph,
        namespace=namespace,
        object_ids=frozenset(selected_ids) if scoped else None,
        filters=filters,
        annotation_states=selected_states,
    )
    results = _search_loaded_graph(
        graph,
        query,
        limit=limit,
        namespace=namespace,
        mode=mode,
        model_path=model_path,
        n_threads=n_threads,
        bm25_weight=bm25_weight,
        annotation_states=selected_states,
        object_ids=object_ids,
        runtime=runtime,
    )
    from tarel.object_families.search import family_name_hits, with_family_hits

    index_warnings = results.warnings
    results = describe_search_results(
        graph, results, annotation_states=selected_states,
        filters=filters, inventory=inventory,
    )
    role_warning = role_coverage_warning(filters, inventory)
    results = replace(
        results,
        warnings=(*scope_warnings, *index_warnings, *((role_warning,) if role_warning else ())),
    )
    results = with_family_hits(results, family_name_hits(
        graph, results, mode=family_mode, namespace=namespace,
        object_ids=object_ids, runtime=runtime,
    ), limit=limit)
    return rerank_results(
        results, (graph,), runtime=runtime, limit=requested_limit, n_threads=n_threads,
    )


def search_workspace_use_case(
    workspace_name: str,
    query: str,
    *,
    systems: tuple[str, ...] = (),
    graphs: tuple[str, ...] = (),
    areas: tuple[str, ...] = (),
    schemas: tuple[str, ...] = (),
    zones: tuple[str, ...] = (),
    focuses: tuple[str, ...] = (),
    scope_objects: tuple[str, ...] = (),
    limit: int = 20,
    mode: str = "lexical",
    model_path: Path | None = None,
    n_threads: int | None = None,
    bm25_weight: float | None = None,
    annotation_states: frozenset[str] | None = None,
    validated_only: bool = False,
    family_mode: str | None = "confirmed_only",
    filters: SearchFilters | None = None,
    exclude_graphs: tuple[str, ...] = (),
    diversity: str = "none",
    max_per_graph: int | None = None,
    collapse_duplicates: bool = False,
    runtime: TarelRuntime | None = None,
) -> SearchResults:
    runtime = snapshot_runtime(runtime, model_path=model_path)
    validate_bm25_weight(mode, bm25_weight)
    validate_diversity(diversity, max_per_graph)
    if not 1 <= limit <= 100:
        raise SearchFailure("invalid_limit", "Search limit must be between 1 and 100.")
    requested_limit = limit
    limit = candidate_limit(runtime, limit)
    _workspace, loaded, scope = load_workspace_scope(
        workspace_name,
        systems=systems,
        graphs=graphs,
        areas=areas,
        schemas=schemas,
        zones=zones,
        focuses=focuses,
        objects=scope_objects,
        runtime=runtime,
    )
    excluded = tuple(
        name for name in scope.graph_names
        if any(fnmatchcase(name, pattern) for pattern in exclude_graphs)
    )
    if excluded:
        scope = replace(
            scope,
            graph_names=tuple(name for name in scope.graph_names if name not in excluded),
            objects=tuple(item for item in scope.objects if item.graph not in excluded),
        )
    selected_states = selected_annotation_states(
        annotation_states,
        validated_only=validated_only,
    )
    resolved_model = (
        resolved_embedding_model(runtime, model_path) if mode in {"vector", "hybrid"} else None
    )
    model_sha256 = (
        embedding_model_sha256(runtime, resolved_model)
        if mode in {"vector", "hybrid"}
        else None
    )
    embedder = (
        embedding_backend(
            runtime, resolved_model, model_sha256=model_sha256, n_threads=n_threads,
        )
        if model_sha256 is not None
        else None
    )
    if embedder is not None:
        for name in scope.graph_names:
            resolve_runtime(runtime).retrieval_index().validate_selection(
                loaded[name], model_path=resolved_model, model_sha256=model_sha256,
                annotation_states=selected_states,
            )
    query_vector = embedder.embed_query(query) if embedder is not None else None
    results_list: list[SearchResults] = []
    inventories: list[SearchInventory] = []
    filtered_ids: dict[str, frozenset[str]] = {}
    search_warnings: list[tuple[str, ...]] = []
    for name in scope.graph_names:
        object_ids, inventory = filter_search_objects(
            loaded[name],
            object_ids=frozenset(
                item.object_id for item in scope.objects if item.graph == name
            ),
            filters=filters,
            annotation_states=selected_states,
        )
        assert object_ids is not None
        filtered_ids[name] = object_ids
        inventories.append(inventory)
        result = _search_loaded_graph(
            loaded[name], query, limit=100, object_ids=object_ids,
            mode=mode, bm25_weight=bm25_weight, resolved_model=resolved_model,
            model_sha256=model_sha256, embedder=embedder, query_vector=query_vector,
            annotation_states=selected_states, runtime=runtime,
        )
        search_warnings.append(result.warnings)
        results_list.append(describe_search_results(
            loaded[name], result, annotation_states=selected_states,
            source_graph=name, filters=filters, inventory=inventory,
        ))
    results = tuple(results_list)
    from tarel.object_families.search import family_name_hits, with_family_hits

    index_warnings = tuple(warning for result in search_warnings for warning in result)

    signatures = (
        {
            (result.graph, object_id): signature
            for result in results
            for object_id, signature in structural_signatures(
                loaded[result.graph], frozenset(hit.id for hit in result.hits),
            ).items()
        }
        if collapse_duplicates
        else None
    )
    combined = combine_workspace_search(
        scope, results, query=query, mode=mode, limit=limit, signatures=signatures,
        diversity=diversity, max_per_graph=max_per_graph,
    )
    type_counts: dict[str, int] = {}
    role_counts: dict[str, int] = {}
    for item in inventories:
        for key, value in item.types:
            type_counts[key] = type_counts.get(key, 0) + value
        for key, value in item.roles:
            role_counts[key] = role_counts.get(key, 0) + value
    inventory = SearchInventory(
        objects_in_scope=sum(item.objects_in_scope for item in inventories),
        objects_after_filters=sum(item.objects_after_filters for item in inventories),
        types=tuple(sorted(type_counts.items())), roles=tuple(sorted(role_counts.items())),
    )
    role_warning = role_coverage_warning(filters, inventory)
    combined = replace(
        combined,
        filters=filters or SearchFilters(),
        inventory=inventory,
        annotation_states=selected_states,
        warnings=(*combined.warnings, *index_warnings, *((role_warning,) if role_warning else ())),
        excluded_graphs=excluded,
    )
    families = tuple(
        hit for graph_name in scope.graph_names
        for hit in family_name_hits(
            loaded[graph_name], combined, mode=family_mode, scoped=True,
            object_ids=filtered_ids[graph_name], runtime=runtime,
        )
    )
    combined = with_family_hits(combined, families, limit=limit)
    if diversity == "per_graph" and families:
        # Family hits are prepended after the physical cap; cap the combined list again.
        capped, extra = cap_per_graph(list(combined.hits), max_per_graph or DEFAULT_MAX_PER_GRAPH)
        omitted = dict(combined.omitted_by_diversity)
        for graph, count in extra.items():
            omitted[graph] = omitted.get(graph, 0) + count
        combined = replace(
            combined, hits=tuple(capped), omitted_by_diversity=tuple(sorted(omitted.items())),
        )
    return rerank_results(
        combined, tuple(loaded[name] for name in scope.graph_names), runtime=runtime,
        limit=requested_limit, n_threads=n_threads,
    )


def _search_loaded_graph(
    graph: GraphDocument,
    query: str,
    *,
    limit: int,
    namespace: str | None = None,
    object_ids: frozenset[str] | None = None,
    mode: str,
    model_path: Path | None = None,
    resolved_model: Path | None = None,
    model_sha256: str | None = None,
    embedder: EmbeddingBackend | None = None,
    query_vector: tuple[float, ...] | None = None,
    n_threads: int | None = None,
    bm25_weight: float | None = None,
    annotation_states: frozenset[str],
    runtime: TarelRuntime | None = None,
) -> SearchResults:
    if mode == "lexical":
        return search_graph(
            graph,
            query,
            limit=limit,
            namespace=namespace,
            object_ids=object_ids,
            annotation_states=annotation_states,
        )
    if mode == "bm25":
        return search_retrieval(
            graph,
            query,
            mode=mode,
            limit=limit,
            namespace=namespace,
            object_ids=object_ids,
            annotation_states=annotation_states,
            bm25_weight=bm25_weight,
        )
    selected_model = resolved_model or resolved_embedding_model(runtime, model_path)
    selected_model_sha256 = model_sha256 or embedding_model_sha256(runtime, selected_model)
    selected_embedder = embedder or embedding_backend(
        runtime, selected_model, model_sha256=selected_model_sha256, n_threads=n_threads,
    )
    return search_retrieval(
        graph,
        query,
        mode=mode,
        limit=limit,
        namespace=namespace,
        object_ids=object_ids,
        embedder=selected_embedder,
        model_path=selected_model,
        annotation_states=annotation_states,
        bm25_weight=bm25_weight,
        store=resolve_runtime(runtime).retrieval_index(),
        query_vector=query_vector,
        model_sha256=selected_model_sha256,
    )


def project_graph_scope(
    graph: GraphDocument,
    object_ids: tuple[str, ...],
) -> GraphDocument:
    selected = frozenset(object_ids)
    known = {node.id for node in graph.nodes if node.type in {"table", "view"}}
    unknown = selected - known
    if unknown:
        raise SearchFailure(
            "object_outside_scope", f"Object is outside the graph scope: {sorted(unknown)[0]}"
        )
    nodes = tuple(
        node for node in graph.nodes
        if (node.type in {"table", "view"} and node.id in selected)
        or (node.type == "field" and node.metadata.get("object_id") in selected)
    )
    node_ids = {node.id for node in nodes}
    edges = tuple(
        edge for edge in graph.edges
        if edge.source_id in node_ids and edge.target_id in node_ids
    )
    return GraphDocument(
        name=graph.name,
        connector=graph.connector,
        source_type=graph.source_type,
        catalog=graph.catalog,
        dialect=graph.dialect,
        nodes=nodes,
        edges=edges,
    )


def resolve_graph_object_scope(
    *,
    source: GraphDocument,
    focuses: tuple[str, ...] = (),
    object_ids: tuple[str, ...] = (),
    runtime: TarelRuntime | None = None,
) -> tuple[tuple[str, ...], bool, tuple[str, ...]]:
    """Resolve explicit graph boundaries while preserving an intentionally empty scope."""
    known = {node.id for node in source.nodes if node.type in {"table", "view"}}
    requested = set(object_ids)
    unknown = requested - known
    if unknown:
        raise SearchFailure(
            "object_outside_scope", f"Object is outside the graph scope: {sorted(unknown)[0]}"
        )
    if focuses:
        allowed, warnings = focus_object_allowlist(
            focuses, graph_names=(source.name,), runtime=runtime,
        )
        selected = set(allowed[source.name])
        if object_ids:
            selected.intersection_update(requested)
    else:
        selected = requested
        warnings = ()
    return tuple(sorted(selected)), bool(focuses or object_ids), warnings


def resolve_graph_object_scope_use_case(
    name: str,
    *,
    focuses: tuple[str, ...] = (),
    object_ids: tuple[str, ...] = (),
    runtime: TarelRuntime | None = None,
) -> tuple[str, ...]:
    """Return every physical object allowed by one graph working scope."""
    graph = resolve_runtime(runtime).graph_store().load(name)
    selected, scoped, _warnings = resolve_graph_object_scope(
        source=graph, focuses=focuses, object_ids=object_ids, runtime=runtime,
    )
    if scoped:
        return selected
    return tuple(sorted(
        node.id for node in graph.nodes if node.type in {"table", "view"}
    ))
