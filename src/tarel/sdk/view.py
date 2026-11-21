"""``tarel.view`` and ``tarel.ui``: browser payloads and the local browser server."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from tarel.discovery.coverage_application import (
    list_query_linked_coverages_use_case,
)
from tarel.entity_resolution.application import find_entity_resolution_candidates_for_graph_use_case
from tarel.focus.application import current_focus_use_case
from tarel.graph.application import load_graph_use_case
from tarel.lineage.application import (
    load_lineage_use_case,
)
from tarel.object_families.application import FamilyProjection, project_families_for_graphs_use_case
from tarel.reference_mapping.application import find_reference_mapping_candidates_for_graph_use_case
from tarel.sdk._base import RuntimeAPI
from tarel.sdk._scope import resolve_workspace_scope
from tarel.semantics.application import list_semantic_imports_use_case
from tarel.topology.application import project_logical_topologies_for_graphs_use_case
from tarel.ui.payloads.graph import (
    browser_graph,
    browser_workspace,
)
from tarel.workspaces.application import list_workspaces_use_case, load_workspace_use_case
from tarel.workspaces.scope import ScopeSelection


class ViewAPI(RuntimeAPI):
    """Build the combined payload used by Space and Lineage canvases."""

    def graph(
        self,
        name: str,
        *,
        lineages: tuple[str, ...] = (),
        editable: bool = False,
        family_mode: str | None = None,
        focuses: tuple[str, ...] = (),
    ) -> dict[str, object]:
        fallback_reason = "full_projection_required"
        if family_mode is not None:
            from tarel.ui.lazy_family_view import try_lazy_family_graph_view_use_case

            attempted = try_lazy_family_graph_view_use_case(
                name, family_mode=family_mode,
                workspaces=tuple(load_workspace_use_case(item, runtime=self._runtime)
                                 for item in list_workspaces_use_case(runtime=self._runtime)),
                lineage_documents=tuple(load_lineage_use_case(item, runtime=self._runtime)
                                        for item in lineages),
                editable=editable, has_focus=bool(focuses), runtime=self._runtime,
            )
            if attempted.payload is not None:
                return attempted.payload
            fallback_reason = attempted.fallback_reason or fallback_reason
        graph = load_graph_use_case(name, runtime=self._runtime)
        documents = tuple(load_lineage_use_case(item, runtime=self._runtime) for item in lineages)
        workspaces = tuple(
            load_workspace_use_case(item, runtime=self._runtime)
            for item in list_workspaces_use_case(runtime=self._runtime)
        )
        semantic_imports = list_semantic_imports_use_case(
            graph_name=name,
            runtime=self._runtime,
        )
        entity_matches = find_entity_resolution_candidates_for_graph_use_case(
            graph,
            mode="confirmed_then_candidates",
            runtime=self._runtime,
        )
        query_linked_coverages = list_query_linked_coverages_use_case(
            graph_name=name,
            runtime=self._runtime,
        )
        logical_topology_projection = project_logical_topologies_for_graphs_use_case(
            (graph,),
            runtime=self._runtime,
        )
        reference_mapping_matches = find_reference_mapping_candidates_for_graph_use_case(
            graph,
            mode="confirmed_then_candidates",
            runtime=self._runtime,
        )
        families = (
            project_families_for_graphs_use_case((graph,), mode=family_mode, runtime=self._runtime)
            if family_mode is not None else FamilyProjection((), ())
        )
        payload = browser_graph(
            graph,
            workspaces=workspaces,
            editable=editable,
            lineage_documents=documents,
            semantic_imports=semantic_imports,
            entity_resolution_matches=entity_matches,
            query_linked_coverages=query_linked_coverages,
            logical_topologies=logical_topology_projection.documents,
            logical_topology_stale_graphs=logical_topology_projection.stale_graphs,
            reference_mapping_matches=reference_mapping_matches,
            family_mode=family_mode,
            object_families=families.families,
            object_family_stale_graphs=families.stale_graphs,
            focus_documents=tuple(current_focus_use_case(item, runtime=self._runtime)
                                  for item in focuses),
        )
        if family_mode is not None:
            from tarel.ui.lazy_family_view import full_family_projection_storage

            payload["storage"] = full_family_projection_storage(fallback_reason)
        return payload

    def workspace(
        self,
        name: str,
        *,
        lineages: tuple[str, ...] = (),
        selection: ScopeSelection | None = None,
        systems: tuple[str, ...] = (),
        graphs: tuple[str, ...] = (),
        areas: tuple[str, ...] = (),
        schemas: tuple[str, ...] = (),
        zones: tuple[str, ...] = (),
        editable: bool = False,
        family_mode: str | None = None,
        focuses: tuple[str, ...] = (),
    ) -> dict[str, object]:
        scope = resolve_workspace_scope(
            self._runtime,
            name,
            selection=selection,
            systems=systems,
            graphs=graphs,
            areas=areas,
            schemas=schemas,
            zones=zones,
        )
        workspace = load_workspace_use_case(name, runtime=self._runtime)
        graph_documents = tuple(
            load_graph_use_case(item, runtime=self._runtime) for item in scope.graph_names
        )
        lineage_documents = tuple(
            load_lineage_use_case(item, runtime=self._runtime) for item in lineages
        )
        semantic_imports = tuple(
            item
            for graph_name in scope.graph_names
            for item in list_semantic_imports_use_case(
                graph_name=graph_name,
                runtime=self._runtime,
            )
        )
        entity_matches = tuple(
            match
            for graph in graph_documents
            for match in find_entity_resolution_candidates_for_graph_use_case(
                graph,
                mode="confirmed_then_candidates",
                runtime=self._runtime,
            )
        )
        query_linked_coverages = tuple(
            coverage
            for graph_name in scope.graph_names
            for coverage in list_query_linked_coverages_use_case(
                graph_name=graph_name,
                runtime=self._runtime,
            )
        )
        logical_topology_projection = project_logical_topologies_for_graphs_use_case(
            graph_documents,
            runtime=self._runtime,
        )
        reference_mapping_matches = tuple(
            match
            for graph in graph_documents
            for match in find_reference_mapping_candidates_for_graph_use_case(
                graph,
                mode="confirmed_then_candidates",
                runtime=self._runtime,
            )
        )
        families = (
            project_families_for_graphs_use_case(
                graph_documents, mode=family_mode, runtime=self._runtime,
            ) if family_mode is not None else FamilyProjection((), ())
        )
        payload = browser_workspace(
            graph_documents,
            scope,
            workspace=workspace,
            editable=editable,
            lineage_documents=lineage_documents,
            semantic_imports=semantic_imports,
            entity_resolution_matches=entity_matches,
            query_linked_coverages=query_linked_coverages,
            logical_topologies=logical_topology_projection.documents,
            logical_topology_stale_graphs=logical_topology_projection.stale_graphs,
            reference_mapping_matches=reference_mapping_matches,
            family_mode=family_mode,
            object_families=families.families,
            object_family_stale_graphs=families.stale_graphs,
            focus_documents=tuple(current_focus_use_case(item, runtime=self._runtime)
                                  for item in focuses),
        )
        if family_mode is not None:
            from tarel.ui.lazy_family_view import full_family_projection_storage

            payload["storage"] = full_family_projection_storage(
                "workspace_requires_full_projection"
            )
        return payload


class UIAPI(RuntimeAPI):
    """Serve TAREL's loopback browser against this client's explicit state root."""

    def serve(
        self,
        graph: str | None = None,
        *,
        workspace: str | None = None,
        systems: tuple[str, ...] = (),
        graphs: tuple[str, ...] = (),
        areas: tuple[str, ...] = (),
        schemas: tuple[str, ...] = (),
        zones: tuple[str, ...] = (),
        lineages: tuple[str, ...] = (),
        focuses: tuple[str, ...] = (),
        editable: bool = False,
        family_mode: str | None = None,
        architecture_file: Path | None = None,
        architecture_edit: bool = False,
        port: int = 0,
        open_browser: bool = True,
        search_mode: str = "bm25",
        model_path: Path | None = None,
        n_threads: int | None = None,
        on_ready: Callable[[str], None] | None = None,
    ) -> int:
        from tarel.ui.server import (
            run_ui,
        )

        return run_ui(
            graph,
            workspace=workspace,
            systems=systems,
            graphs=graphs,
            areas=areas,
            schemas=schemas,
            zones=zones,
            lineages=lineages,
            focuses=focuses,
            editable=editable,
            family_mode=family_mode,
            architecture_file=architecture_file,
            architecture_edit=architecture_edit,
            port=port,
            open_browser=open_browser,
            search_mode=search_mode,
            model_path=model_path,
            n_threads=n_threads,
            runtime=self._runtime,
            on_ready=on_ready,
        )
