"""``tarel.search``: rank graph or workspace objects for a query."""

from __future__ import annotations

from pathlib import Path

from tarel.retrieval.search_application import search_graph_use_case, search_workspace_use_case
from tarel.sdk._base import RuntimeAPI, optional_path
from tarel.sdk._scope import workspace_focuses, workspace_objects, workspace_scope_arguments
from tarel.search import SearchFilters, SearchResults
from tarel.workspaces.scope import ScopeSelection


class SearchAPI(RuntimeAPI):
    """Rank the objects of one graph or a workspace scope for a query."""

    def graph(
        self,
        name: str,
        query: str,
        *,
        limit: int = 20,
        namespace: str | None = None,
        mode: str = "lexical",
        model_path: str | Path | None = None,
        n_threads: int | None = None,
        bm25_weight: float | None = None,
        annotation_states: frozenset[str] | None = None,
        validated_only: bool = False,
        family_mode: str | None = "confirmed_only",
        filters: SearchFilters | None = None,
        focuses: tuple[str, ...] = (),
        scope_object_ids: tuple[str, ...] = (),
    ) -> SearchResults:
        return search_graph_use_case(
            name,
            query,
            limit=limit,
            namespace=namespace,
            mode=mode,
            model_path=optional_path(model_path),
            n_threads=n_threads,
            bm25_weight=bm25_weight,
            annotation_states=annotation_states,
            validated_only=validated_only,
            family_mode=family_mode,
            filters=filters,
            focuses=focuses,
            scope_object_ids=scope_object_ids,
            runtime=self._runtime,
        )

    def workspace(
        self,
        name: str,
        query: str,
        *,
        selection: ScopeSelection | None = None,
        systems: tuple[str, ...] = (),
        graphs: tuple[str, ...] = (),
        areas: tuple[str, ...] = (),
        schemas: tuple[str, ...] = (),
        zones: tuple[str, ...] = (),
        focuses: tuple[str, ...] = (),
        scope_objects: tuple[str, ...] = (),
        limit: int = 20,
        mode: str = "lexical",
        model_path: str | Path | None = None,
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
    ) -> SearchResults:
        focus_names = workspace_focuses(selection, focuses)
        systems, graphs, areas, schemas, zones = workspace_scope_arguments(
            selection,
            systems=systems,
            graphs=graphs,
            areas=areas,
            schemas=schemas,
            zones=zones,
        )
        return search_workspace_use_case(
            name,
            query,
            systems=systems,
            graphs=graphs,
            areas=areas,
            schemas=schemas,
            zones=zones,
            focuses=focus_names,
            scope_objects=workspace_objects(selection, scope_objects),
            limit=limit,
            mode=mode,
            model_path=optional_path(model_path),
            n_threads=n_threads,
            bm25_weight=bm25_weight,
            annotation_states=annotation_states,
            validated_only=validated_only,
            family_mode=family_mode,
            filters=filters,
            exclude_graphs=exclude_graphs,
            diversity=diversity,
            max_per_graph=max_per_graph,
            collapse_duplicates=collapse_duplicates,
            runtime=self._runtime,
        )
