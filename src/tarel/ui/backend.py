"""The browser backend: one session's scope, its bootstrap payload and its API routes."""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from tarel.annotations.application import decide_annotation_use_case, edit_annotation_use_case
from tarel.annotations.contracts import AnnotationFailure
from tarel.discovery.coverage_application import list_query_linked_coverages_use_case
from tarel.entity_resolution.application import find_entity_resolution_candidates_for_graph_use_case
from tarel.focus.application import list_focuses_use_case, load_focus_use_case
from tarel.focus.contracts import FocusDocument, FocusFailure
from tarel.focus.core import require_current_focus
from tarel.graph.application import load_graph_use_case
from tarel.graph.contracts import GraphDocument, GraphFailure
from tarel.graph.revision import graph_revision
from tarel.knowledge.application import list_knowledge_documents_use_case
from tarel.knowledge.contracts import KnowledgeContext, KnowledgeFailure
from tarel.knowledge.core import resolve_knowledge
from tarel.lineage.application import (
    add_manual_hop_use_case,
    add_manual_job_use_case,
    decide_lineage_item_use_case,
    load_lineage_use_case,
    trace_upstream_use_case,
)
from tarel.lineage.contracts import LineageDocument, LineageFailure
from tarel.lineage.revision import lineage_revision
from tarel.object_families.application import (
    project_families_for_graphs_use_case,
    resolve_family_members_use_case,
)
from tarel.providers.config import list_provider_names
from tarel.reference_mapping.application import find_reference_mapping_candidates_for_graph_use_case
from tarel.retrieval.application import (
    build_retrieval_index_use_case,
    build_retrieval_workspace_indexes_use_case,
    download_embedding_model_use_case,
    retrieval_index_status_use_case,
    retrieval_workspace_status_use_case,
)
from tarel.retrieval.catalog import list_models
from tarel.retrieval.contracts import IndexStatus, ModelCatalog, WorkspaceIndexStatus
from tarel.retrieval.settings import RetrievalSettings, load_settings, save_settings, settings_path
from tarel.runtime import TarelRuntime, resolve_runtime
from tarel.semantics.application import (
    edit_semantic_source_use_case,
    list_semantic_imports_use_case,
    load_semantic_import_use_case,
)
from tarel.topology.application import project_logical_topologies_for_graphs_use_case
from tarel.ui._parse import (
    optional_string,
    require_boolean,
    require_integer,
    require_object,
    require_string,
    string_list,
)
from tarel.ui.architecture_store import ArchitectureFailure, ArchitectureStore
from tarel.ui.contracts import UIConfig, UIFailure
from tarel.ui.logical_metadata import logical_metadata_use_case
from tarel.ui.optional_metadata import optional_object_metadata
from tarel.ui.payloads.families import (
    family_view_scope_revision,
    family_view_scope_revision_from_revisions,
)
from tarel.ui.payloads.focus import (
    browser_focus_catalog,
    browser_focus_selection,
    focus_physical_objects,
)
from tarel.ui.payloads.graph import (
    browser_graph,
    browser_workspace,
    summarize_review,
    workspace_revision,
)
from tarel.ui.payloads.lineage import (
    browser_lineages,
)
from tarel.ui.payloads.lineage_flows import LineageFlowModel
from tarel.ui.query_tools import (
    UIQueryScope,
    preview_context,
    preview_expansion,
    query_scope_snapshot,
    search_metadata,
)
from tarel.workspaces.application import (
    create_workspace_use_case,
    define_workspace_area_use_case,
    define_workspace_system_use_case,
    define_workspace_zone_use_case,
    list_workspaces_use_case,
    load_workspace_scope_use_case,
    load_workspace_use_case,
    resolve_workspace_scope_use_case,
)
from tarel.workspaces.contracts import WorkspaceDocument

_OPTIONAL_KINDS = ("identity", "mappings", "coverage", "imports")


class TarelUIBackend:
    def __init__(self, config: UIConfig, *, runtime: TarelRuntime | None = None) -> None:
        self.config = config
        self.runtime = runtime
        self._lineages = list(config.lineages)
        self._flow_objects: list[dict[str, Any]] | None = None
        self._flow_cache: tuple[object, LineageFlowModel] | None = None
        self._flow_lock = threading.Lock()
        self.architecture = None
        if config.architecture_edit and not config.architecture_file:
            raise UIFailure("architecture_required", "--architecture-edit requires a sidecar.")
        if config.architecture_file:
            if not config.workspace or any((config.systems, config.graphs, config.areas,
                                            config.schemas, config.zones, config.focuses)):
                raise UIFailure(
                    "architecture_scope", "Architecture requires an unfiltered workspace.",
                )
            self.architecture = ArchitectureStore(
                config.architecture_file, workspace=config.workspace,
                editable=config.architecture_edit,
            )

    def bootstrap(self) -> dict[str, Any]:
        payload = self._bootstrap(self.config.family_mode)
        if self.architecture and self.config.workspace:
            snapshot = self.architecture.snapshot()
            workspace = load_workspace_use_case(self.config.workspace, runtime=self.runtime)
            # The object projection intentionally omits empty catalogs. The
            # authoritative workspace retains them and defines this boundary.
            observed = {
                (system.name, name) for system in workspace.systems for name in system.graphs
            }
            recorded = {(item["system"], item["graph"]) for item in snapshot["document"]["nodes"]}
            if recorded != observed:
                raise ArchitectureFailure(
                    "Architecture source inventory or graph/system assignments differ "
                    "from the workspace. "
                    "Refresh the sidecar before using this view.", 409,
                )
            payload["architecture"] = snapshot
        return payload

    def _bootstrap(
        self, family_mode: str | None, focus_names: tuple[str, ...] | None = None,
        *, derived: bool = False,
    ) -> dict[str, Any]:
        names = self.config.focuses if focus_names is None else focus_names
        fallback_reason = "workspace_requires_full_projection"
        if family_mode is not None and not self.config.workspace and not derived:
            from tarel.ui.lazy_family_view import try_lazy_family_graph_view_use_case

            attempted = try_lazy_family_graph_view_use_case(
                self._single_graph(), family_mode=family_mode,
                workspaces=tuple(
                    load_workspace_use_case(name, runtime=self.runtime)
                    for name in list_workspaces_use_case(runtime=self.runtime)
                ),
                lineage_documents=tuple(
                    load_lineage_use_case(name, runtime=self.runtime)
                    for name in self._lineages
                ),
                editable=self.config.editable,
                has_focus=bool(names) or bool(self._focus_documents()),
                runtime=self.runtime,
            )
            if attempted.payload is not None:
                payload = attempted.payload
                payload.update(focuses=[], focus_selection=None, knowledge_documents=[])
                payload.update(
                    optional_metadata={"state": "not_loaded", "kinds": list(_OPTIONAL_KINDS)},
                    scope_revision=payload["object_families"]["scope_revision"],
                    derived_enabled=False,
                )
                for record in payload["review"]:
                    record["available_context_document_ids"] = []
                self._flow_objects = payload["objects"]
                return payload
            fallback_reason = attempted.fallback_reason or "full_projection_required"
        workspace = None
        scope = None
        if self.config.workspace:
            workspace, loaded_graphs, scope = load_workspace_scope_use_case(
                self.config.workspace, systems=self.config.systems,
                graphs=self.config.graphs, areas=self.config.areas,
                schemas=self.config.schemas, zones=self.config.zones,
                runtime=self.runtime,
            )
            graphs = tuple(loaded_graphs[name] for name in scope.graph_names)
        else:
            graph = load_graph_use_case(self._single_graph(), runtime=self.runtime)
            loaded_graphs = {graph.name: graph}
            graphs = (graph,)
        focus_documents = self._focus_documents(graph_names=tuple(item.name for item in graphs))
        selected_focuses = self._selected_focus_documents(
            names, documents=focus_documents, loaded_graphs=loaded_graphs,
        ) if names else ()
        documents = tuple(
            load_lineage_use_case(name, runtime=self.runtime) for name in self._lineages
        )
        if workspace is not None and scope is not None:
            families = (
                project_families_for_graphs_use_case(
                    graphs, mode=family_mode, runtime=self.runtime,
                )
                if family_mode is not None else None
            )
            logical_topology_projection = project_logical_topologies_for_graphs_use_case(
                graphs, runtime=self.runtime,
            ) if family_mode is not None or derived else None
            semantic_imports = tuple(
                item
                for graph in graphs
                for item in list_semantic_imports_use_case(
                    graph_name=graph.name, runtime=self.runtime,
                )
            ) if family_mode is not None else ()
            payload = browser_workspace(
                graphs,
                scope,
                workspace=workspace,
                editable=self.config.editable,
                lineage_documents=documents,
                semantic_imports=semantic_imports,
                entity_resolution_matches=tuple(
                    match
                    for graph in graphs
                    for match in find_entity_resolution_candidates_for_graph_use_case(
                        graph, runtime=self.runtime,
                    )
                ) if family_mode is not None else (),
                query_linked_coverages=tuple(
                    coverage
                    for graph in graphs
                    for coverage in list_query_linked_coverages_use_case(
                        graph_name=graph.name, runtime=self.runtime,
                    )
                ) if family_mode is not None else (),
                logical_topologies=(
                    logical_topology_projection.documents if logical_topology_projection else ()
                ),
                logical_topology_stale_graphs=(
                    logical_topology_projection.stale_graphs if logical_topology_projection else ()
                ),
                reference_mapping_matches=tuple(
                    match
                    for graph in graphs
                    for match in find_reference_mapping_candidates_for_graph_use_case(
                        graph,
                        mode="confirmed_then_candidates",
                        runtime=self.runtime,
                    )
                ) if family_mode is not None else (),
                family_mode=family_mode,
                object_families=families.families if families else (),
                object_family_stale_graphs=families.stale_graphs if families else (),
                focus_documents=selected_focuses if family_mode is not None else (),
            )
        else:
            families = (
                project_families_for_graphs_use_case(
                    graphs, mode=family_mode, runtime=self.runtime,
                )
                if family_mode is not None else None
            )
            logical_topology_projection = project_logical_topologies_for_graphs_use_case(
                graphs, runtime=self.runtime,
            ) if family_mode is not None or derived else None
            workspaces = tuple(
                load_workspace_use_case(name, runtime=self.runtime)
                for name in list_workspaces_use_case(runtime=self.runtime)
            )
            payload = browser_graph(
                graph,
                workspaces=workspaces,
                editable=self.config.editable,
                lineage_documents=documents,
                semantic_imports=(
                    list_semantic_imports_use_case(
                        graph_name=graph.name, runtime=self.runtime,
                    )
                    if family_mode is not None else ()
                ),
                entity_resolution_matches=find_entity_resolution_candidates_for_graph_use_case(
                    graph, runtime=self.runtime,
                ) if family_mode is not None else (),
                query_linked_coverages=list_query_linked_coverages_use_case(
                    graph_name=graph.name, runtime=self.runtime,
                ) if family_mode is not None else (),
                logical_topologies=(
                    logical_topology_projection.documents if logical_topology_projection else ()
                ),
                logical_topology_stale_graphs=(
                    logical_topology_projection.stale_graphs if logical_topology_projection else ()
                ),
                reference_mapping_matches=find_reference_mapping_candidates_for_graph_use_case(
                    graph,
                    mode="confirmed_then_candidates",
                    runtime=self.runtime,
                ) if family_mode is not None else (),
                family_mode=family_mode,
                object_families=families.families if families else (),
                object_family_stale_graphs=families.stale_graphs if families else (),
                focus_documents=selected_focuses if family_mode is not None else (),
            )
        payload["focuses"] = browser_focus_catalog(
            focus_documents,
            stale_reasons=self._focus_stale_reasons(
                focus_documents, loaded_graphs=loaded_graphs,
                loaded_lineages={item.name: item for item in documents},
            ),
        )
        if "focus_selection" not in payload:
            payload["focus_selection"] = (
                browser_focus_selection(selected_focuses) if names else None
            )
        if selected_focuses and family_mode is None:
            # The canvas may retain surrounding nodes; review follows the explicit report scope.
            focused = focus_physical_objects(selected_focuses)
            payload["review"] = [
                record for record in payload["review"]
                if (record["graph"], record["object_id"]) in focused
            ]
            allowed = {(record["graph"], record["object_id"]) for record in payload["review"]}
            payload["review_summary"] = summarize_review(graphs, allowed)
        payload.update(
            optional_metadata={"state": "not_loaded", "kinds": list(_OPTIONAL_KINDS)},
            scope_revision=family_view_scope_revision_from_revisions(
                payload["revisions"], selected_focuses, scope,
            ),
            derived_enabled=derived,
        )
        # Evidence documents belong to the explicit Review workflow, not object navigation.
        payload["knowledge_documents"] = []
        for record in payload["review"]:
            record["available_context_document_ids"] = []
        if family_mode is not None:
            from tarel.ui.lazy_family_view import full_family_projection_storage

            payload["storage"] = full_family_projection_storage(fallback_reason)
        self._flow_objects = payload["objects"]
        return payload

    def _optional_scope(
        self, payload: dict[str, Any],
    ) -> tuple[GraphDocument, frozenset[str], str]:
        """Resolve physical ownership before touching any optional artifact store."""
        graph_name = self._payload_graph(payload)
        scope = self._scope() if self.config.workspace else None
        graphs = tuple(load_graph_use_case(name, runtime=self.runtime) for name in (
            scope.graph_names if scope else (self._single_graph(),)
        ))
        graph = next(item for item in graphs if item.name == graph_name)
        allowed = frozenset(node.id for node in graph.nodes if node.type in {"table", "view"})
        if scope:
            allowed &= frozenset(
                item.object_id for item in scope.objects if item.graph == graph_name
            )
        names = string_list(payload, "focuses") if "focuses" in payload else self.config.focuses
        focuses = self._selected_focus_documents(names) if names else ()
        if focuses:
            allowed &= frozenset(
                identifier for owner, identifier in focus_physical_objects(focuses)
                if owner == graph_name
            )
        revision = family_view_scope_revision(graphs, focuses, scope)
        if (
            payload.get("revision") != graph_revision(graph)
            or payload.get("scope_revision") != revision
        ):
            raise UIFailure(
                "stale_optional_scope", "Reload the changed object or report scope.", status=409,
            )
        if require_string(payload, "object_id") not in allowed:
            raise UIFailure(
                "optional_object_outside_scope", "The physical object is outside this scope.",
            )
        return graph, allowed, revision

    def _optional_details(self, payload: dict[str, Any]) -> dict[str, Any]:
        if set(payload) - {
            "graph", "object_id", "kind", "revision", "scope_revision", "focuses", "limit",
        } or not isinstance(payload.get("kind"), str) or payload["kind"] not in _OPTIONAL_KINDS:
            raise UIFailure("invalid_optional_request", "Unsupported optional detail request.")
        limit = require_integer(payload, "limit", default=20, minimum=1, maximum=20)
        graph, allowed, revision = self._optional_scope(payload)
        result = optional_object_metadata(
            graph, require_string(payload, "object_id"), allowed_object_ids=allowed,
            kind=payload["kind"], limit=limit, runtime=self.runtime,
        )
        # Discard results if source ownership/revisions changed while loading sidecars.
        self._optional_scope(payload)
        return {**result, "revision": graph_revision(graph), "scope_revision": revision}

    def _attach_review_knowledge(
        self, payload: dict[str, Any], graphs: tuple[GraphDocument, ...],
        workspace: WorkspaceDocument | None,
    ) -> None:
        knowledge_documents = list_knowledge_documents_use_case(runtime=self.runtime)
        payload["knowledge_documents"] = [
            item.to_dict(include_content=False)
            for item in knowledge_documents
        ]
        graph_by_name = {item.name: item for item in graphs}
        # Review rows already carry authoritative physical IDs. Index each graph
        # once instead of resolving every label through all objects and fields.
        nodes_by_graph = {item.name: item.node_by_id() for item in graphs}
        for record in payload["review"]:
            if not isinstance(record, dict):
                continue
            try:
                record_graph = graph_by_name[str(record["graph"])]
                node = nodes_by_graph[record_graph.name][str(record["object_id"])]
                context = resolve_knowledge(
                    knowledge_documents,
                    record_graph,
                    node,
                    workspace=workspace,
                    mode="scoped",
                )
            except (AnnotationFailure, KeyError, KnowledgeFailure):
                context = KnowledgeContext()
            record["available_context_document_ids"] = [
                item.id for item in context.references
            ]

    def _review_view(self, names: tuple[str, ...]) -> dict[str, Any]:
        """Review physical objects on demand, never the collapsed visual projection."""
        focuses = self._selected_focus_documents(names) if names else ()
        workspace = None
        if self.config.workspace:
            scope = self._scope()
            graphs = tuple(
                load_graph_use_case(name, runtime=self.runtime) for name in scope.graph_names
            )
            workspace = load_workspace_use_case(
                self.config.workspace, runtime=self.runtime,
            )
            projection = browser_workspace(
                graphs, scope, workspace=workspace, editable=self.config.editable,
                focus_documents=focuses,
            )
        else:
            graphs = (load_graph_use_case(self._single_graph(), runtime=self.runtime),)
            projection = browser_graph(
                graphs[0], editable=self.config.editable, focus_documents=focuses,
            )
        self._attach_review_knowledge(projection, graphs, workspace)
        return {
            key: projection[key] for key in (
                "review", "review_summary", "revisions", "knowledge_documents", "editable",
            )
        } | {"focuses": list(names)}

    def mutate(self, route: str, payload: dict[str, Any]) -> Mapping[str, object]:
        handler = _POST_ROUTES.get(route)
        if handler is not None:
            return handler(self, payload)
        if route.startswith("/api/architecture/"):
            if not self.architecture:
                raise UIFailure(
                    "architecture_unavailable", "No architecture sidecar configured.", status=404,
                )
            return self.architecture.mutate(route.removeprefix("/api/architecture/"), payload)
        if route in {
            "/api/query/scope", "/api/search", "/api/context/preview",
            "/api/context/expand",
        }:
            scope = UIQueryScope(
                graph=self.config.graph, workspace=self.config.workspace,
                systems=self.config.systems, graphs=self.config.graphs,
                areas=self.config.areas, schemas=self.config.schemas, zones=self.config.zones,
                focuses=self.config.focuses, search_mode=self.config.search_mode,
                model_path=self._retrieval_model_path(),
                n_threads=self.config.n_threads,
            )
            if route == "/api/query/scope":
                if set(payload) - {"scope_objects"}:
                    raise UIFailure("invalid_query_request", "Project scope is server-owned.")
                objects = (
                    string_list(payload, "scope_objects") if "scope_objects" in payload else ()
                )
                return query_scope_snapshot(
                    scope, scope_objects=objects, runtime=self.runtime,
                )
            if route == "/api/search":
                return search_metadata(scope, payload, runtime=self.runtime)
            if route == "/api/context/preview":
                return preview_context(scope, payload, runtime=self.runtime)
            return preview_expansion(scope, payload, runtime=self.runtime)

        self._require_editable()
        handler = _EDIT_ROUTES.get(route)
        if handler is not None:
            return handler(self, payload)
        raise UIFailure("route_not_found", "Unknown UI API route.", status=404)

    def _post_retrieval_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        if set(payload) != {"settings", "search_mode"} or not isinstance(
            payload["settings"], dict,
        ):
            raise UIFailure("invalid_retrieval_settings", "Invalid retrieval selection.")
        mode = payload["search_mode"]
        if mode not in {"lexical", "bm25", "vector", "hybrid"}:
            raise UIFailure("invalid_retrieval_settings", "Invalid search mode.")
        selected = RetrievalSettings.from_dict(payload["settings"])
        save_settings(self.runtime, selected)
        self.config = replace(self.config, search_mode=mode, model_path=None)
        return self._retrieval_settings()


    def _post_retrieval_models(self, payload: dict[str, Any]) -> ModelCatalog:
        if set(payload) != {"provider", "task"}:
            raise UIFailure("invalid_retrieval_settings", "Select provider and model task.")
        return list_models(
            provider=require_string(payload, "provider"), task=require_string(payload, "task")
        )


    def _post_retrieval_download(self, payload: dict[str, Any]) -> dict[str, Any]:
        if set(payload) != {"model"}:
            raise UIFailure("invalid_retrieval_settings", "Select a registered local model.")
        result = download_embedding_model_use_case(name=require_string(payload, "model"))
        return {"model": result.spec.name, "reused": result.reused}


    def _post_optional_details(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._optional_details(payload)


    def _post_optional_view(self, payload: dict[str, Any]) -> dict[str, Any]:
        if set(payload) - {"kind", "enabled", "mode", "focuses"} or (
            payload.get("kind") != "derived_relations"
            or not isinstance(payload.get("enabled"), bool)
        ):
            raise UIFailure("invalid_optional_request", "Invalid optional view request.")
        mode = optional_string(payload.get("mode"))
        if mode not in {None, "confirmed_only", "include_candidates"}:
            raise UIFailure("invalid_optional_request", "Unsupported family policy.")
        names = string_list(payload, "focuses") if "focuses" in payload else None
        return self._bootstrap(mode, names, derived=payload["enabled"])


    def _post_index_build(self, payload: dict[str, Any]) -> Mapping[str, object]:
        if payload:
            raise UIFailure("invalid_index_request", "Index update size is server-owned.")
        if self.config.workspace:
            return build_retrieval_workspace_indexes_use_case(
                self.config.workspace, systems=self.config.systems,
                graphs=self.config.graphs, areas=self.config.areas,
                schemas=self.config.schemas, zones=self.config.zones,
                model_path=self._retrieval_model_path(), n_threads=self.config.n_threads,
                max_graphs=1, runtime=self.runtime,
            )
        result = build_retrieval_index_use_case(
            self._single_graph(), model_path=self._retrieval_model_path(),
            n_threads=self.config.n_threads, runtime=self.runtime,
        )
        return {
            "graph": result.metadata.graph,
            "embedded_documents": result.embedded_documents,
            "reused_documents": result.reused_documents,
            "removed_documents": result.removed_documents,
            "status": self._index_status(),
        }


    def _post_review_view(self, payload: dict[str, Any]) -> dict[str, Any]:
        names = string_list(payload, "focuses") if "focuses" in payload else self.config.focuses
        return self._review_view(names)


    def _post_logical_metadata(self, payload: dict[str, Any]) -> dict[str, Any]:
        graph_name = self._payload_graph(payload)
        scope = self._scope() if self.config.workspace else None
        allowed = (frozenset(item.object_id for item in scope.objects
                             if item.graph == graph_name) if scope else None)
        names = string_list(payload, "focuses") if "focuses" in payload else self.config.focuses
        focuses = self._selected_focus_documents(names) if names else ()
        if focuses:
            focused = frozenset(
                identifier for graph, identifier in focus_physical_objects(focuses)
                if graph == graph_name
            )
            allowed = focused if allowed is None else allowed & focused
        expected = optional_string(payload.get("scope_revision"))
        if expected is not None:
            actual = family_view_scope_revision(
                tuple(load_graph_use_case(name, runtime=self.runtime) for name in (
                    scope.graph_names if scope else (self._single_graph(),)
                )), focuses, scope,
            )
            if actual != expected:
                raise UIFailure(
                    "stale_logical_metadata_scope", "Reload the changed metadata scope.",
                    status=409,
                )
        return logical_metadata_use_case(
            graph_name, string_list(payload, "object_ids"), allowed_object_ids=allowed,
            mode=optional_string(payload.get("mode")) or "include_candidates",
            runtime=self.runtime,
        )


    def _post_families_view(self, payload: dict[str, Any]) -> dict[str, Any]:
        mode = optional_string(payload.get("mode"))
        if mode not in {None, "confirmed_only", "include_candidates"}:
            raise UIFailure("invalid_object_family_mode", "Unsupported family policy.")
        names = string_list(payload, "focuses") if "focuses" in payload else None
        derived = payload.get("derived", False)
        if not isinstance(derived, bool):
            raise UIFailure("invalid_optional_request", "Derived view must be a boolean.")
        return self._bootstrap(mode, names, derived=derived)


    def _post_families_members(self, payload: dict[str, Any]) -> dict[str, Any]:
        graph_name = self._payload_graph(payload)
        scope = self._scope() if self.config.workspace else None
        allowed_ids = (
            frozenset(
                item.object_id for item in scope.objects
                if item.graph == graph_name
            )
            if scope is not None else None
        )
        names = string_list(payload, "focuses") if "focuses" in payload else self.config.focuses
        focuses = self._selected_focus_documents(names) if names else ()
        if focuses:
            focused_ids = frozenset(
                object_id for graph, object_id in focus_physical_objects(focuses)
                if graph == graph_name
            )
            allowed_ids = focused_ids if allowed_ids is None else allowed_ids & focused_ids
        if scope is None and not focuses:
            header = resolve_runtime(self.runtime).graph_store().header(self._single_graph())
            revision = family_view_scope_revision_from_revisions({header.name: header.revision})
        else:
            revision = family_view_scope_revision(
                tuple(load_graph_use_case(name, runtime=self.runtime) for name in (
                    scope.graph_names if scope else (self._single_graph(),)
                )), focuses, scope,
            )
        expected_scope = optional_string(payload.get("scope_revision"))
        if (focuses or expected_scope is not None) and expected_scope != revision:
            raise UIFailure(
                "stale_object_family_scope",
                "The report/cube or workspace scope changed; reload the family view.",
                status=409,
            )
        page = resolve_family_members_use_case(
            graph_name,
            require_string(payload, "family_id"),
            expected_revision=require_string(payload, "revision"),
            mode=require_string(payload, "mode"),
            offset=require_integer(payload, "offset", default=0, minimum=0, maximum=10_000_000),
            limit=require_integer(payload, "limit", default=50, minimum=1, maximum=100),
            allowed_object_ids=allowed_ids,
            runtime=self.runtime,
        ).to_dict()
        page["scope_revision"] = revision
        return page


    def _post_focus_select(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._select_focuses(string_list(payload, "focuses"))


    def _lineage_flow_model(self) -> LineageFlowModel:
        """The joined flow for the current scope, rebuilt only when a source really changed."""
        if self._flow_objects is None:
            self.bootstrap()
        store = resolve_runtime(self.runtime).lineage_store()
        signatures = tuple(_file_signature(store.path(name)) for name in self._lineages)
        key = (id(self._flow_objects), signatures)
        with self._flow_lock:
            if self._flow_cache is None or self._flow_cache[0] != key:
                documents = tuple(
                    load_lineage_use_case(name, runtime=self.runtime) for name in self._lineages
                )
                self._flow_cache = (key, LineageFlowModel(documents, self._flow_objects or ()))
            return self._flow_cache[1]

    def _lineage_edge(self, edge_id: str) -> dict[str, Any]:
        if not edge_id:
            raise UIFailure("invalid_request", "Choose a lineage edge.")
        detail = self._lineage_flow_model().edge_detail(
            edge_id,
            roots=(Path.cwd(), resolve_runtime(self.runtime).root.parent),
        )
        if detail is None:
            raise UIFailure("lineage_edge_not_found", "This lineage edge is gone.", status=404)
        return {"editable": self.config.editable, **detail}

    def _post_lineage_neighbourhood(self, payload: dict[str, Any]) -> dict[str, Any]:
        direction = require_string(payload, "direction")
        if direction not in {"upstream", "downstream", "both"}:
            raise UIFailure("invalid_request", "Direction must be upstream, downstream or both.")
        result = self._lineage_flow_model().neighbourhood(
            require_string(payload, "reference"),
            direction=direction,
            hops=require_integer(payload, "hops", default=3, minimum=1, maximum=40),
        )
        if result is None:
            raise UIFailure(
                "lineage_reference_not_found",
                "No object in the selected lineage matches this reference.",
                status=404,
            )
        return result

    def _post_lineage_upstream(self, payload: dict[str, Any]) -> dict[str, Any]:
        names = string_list(payload, "lineages") or tuple(self._lineages)
        if not names:
            raise UIFailure("lineage_required", "Select at least one lineage document.")
        trace = trace_upstream_use_case(
            require_string(payload, "reference"),
            lineage_names=names,
            graph_names=self._graph_names(),
            max_hops=require_integer(payload, "max_hops", default=12, minimum=1, maximum=100),
            states=frozenset(string_list(payload, "states")) or None,
            runtime=self.runtime,
        )
        return trace.to_dict()


    def _post_annotation_edit(self, payload: dict[str, Any]) -> dict[str, Any]:
        graph_name = self._check_graph_revision(payload)
        patch = require_object(payload, "patch")
        result = edit_annotation_use_case(
            graph_name,
            require_string(payload, "reference"),
            patch,
            reason=require_string(payload, "reason"),
            runtime=self.runtime,
        )
        return {"record": result.record.to_dict(), "revision": graph_revision(result.graph)}


    def _post_semantic_edit(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = require_string(payload, "import_name")
        document = load_semantic_import_use_case(name, runtime=self.runtime)
        if document.graph_name not in self._graph_names():
            raise UIFailure(
                "semantic_import_outside_scope",
                f"Semantic import is outside the UI scope: {name}",
            )
        result = edit_semantic_source_use_case(
            name,
            require_string(payload, "target_id"),
            require_object(payload, "patch"),
            reason=require_string(payload, "reason"),
            expected_revision=require_string(payload, "revision"),
            runtime=self.runtime,
        )
        return {
            "import_name": name,
            "revision": result.document.revision,
            "target_id": require_string(payload, "target_id"),
        }


    def _post_annotation_decision(self, payload: dict[str, Any]) -> dict[str, Any]:
        graph_name = self._check_graph_revision(payload)
        result = decide_annotation_use_case(
            graph_name,
            require_string(payload, "reference"),
            state=require_string(payload, "state"),
            reason=require_string(payload, "reason"),
            include_fields=require_boolean(payload, "include_fields", default=False),
            runtime=self.runtime,
        )
        return {
            "records": [record.to_dict() for record in result.records],
            "revision": graph_revision(result.graph),
        }


    def _post_lineage_decision(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = decide_lineage_item_use_case(
            require_string(payload, "lineage"),
            require_string(payload, "item_id"),
            decision=require_string(payload, "decision"),
            reason=require_string(payload, "reason"),
            expected_revision=require_string(payload, "revision"),
            runtime=self.runtime,
        )
        answer: dict[str, Any] = {
            "item": result.item.to_dict(),
            "revision": lineage_revision(result.document),
        }
        edge = payload.get("edge")
        if isinstance(edge, str) and edge:
            # Asked here rather than by loading the edge: its removal is an outcome, not an error.
            answer["edge_exists"] = edge in self._lineage_flow_model().edges
        return answer


    def _post_manual_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = require_string(payload, "lineage")
        result = add_manual_job_use_case(
            name,
            kind=require_string(payload, "kind"),
            job_name=require_string(payload, "job_name"),
            qualified_name=require_string(payload, "qualified_name"),
            language=require_string(payload, "language"),
            source_reference=require_string(payload, "source_reference"),
            description=require_string(payload, "description"),
            expected_revision=optional_string(payload.get("revision")),
            runtime=self.runtime,
        )
        if name not in self._lineages:
            self._lineages.append(name)
        return {"lineage": browser_lineages((result.document,))[0]}


    def _post_manual_hop(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = require_string(payload, "lineage")
        result = add_manual_hop_use_case(
            name,
            job_reference=require_string(payload, "job"),
            source=require_string(payload, "source"),
            target=require_string(payload, "target"),
            operation=require_string(payload, "operation"),
            role=require_string(payload, "role"),
            evidence_reference=require_string(payload, "evidence_reference"),
            reason=require_string(payload, "reason"),
            line_start=require_integer(
                payload,
                "line_start",
                default=1,
                minimum=1,
                maximum=1_000_000,
            ),
            line_end=require_integer(
                payload,
                "line_end",
                default=1,
                minimum=1,
                maximum=1_000_000,
            ),
            expected_revision=require_string(payload, "revision"),
            runtime=self.runtime,
        )
        return {
            "item": result.item.to_dict(),
            "revision": lineage_revision(result.document),
        }


    def _post_zone_save(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._save_zone(payload)

    def _focus_documents(
        self, *, graph_names: tuple[str, ...] | None = None,
    ) -> tuple[FocusDocument, ...]:
        allowed_graphs = set(self._graph_names() if graph_names is None else graph_names)
        documents: list[FocusDocument] = []
        for name in list_focuses_use_case(runtime=self.runtime):
            document = load_focus_use_case(name, runtime=self.runtime)
            required = {item.name for item in document.sources if item.kind == "graph"}
            if required and required <= allowed_graphs:
                documents.append(document)
        return tuple(documents)

    def _select_focuses(self, names: tuple[str, ...]) -> dict[str, Any]:
        focuses = self._selected_focus_documents(names)
        scope = self._scope() if self.config.workspace else None
        graphs = tuple(load_graph_use_case(name, runtime=self.runtime) for name in (
            scope.graph_names if scope else (self._single_graph(),)
        ))
        return {
            **browser_focus_selection(focuses),
            "scope_revision": family_view_scope_revision(graphs, focuses, scope),
        }

    def _selected_focus_documents(
        self, names: tuple[str, ...], *, documents: tuple[FocusDocument, ...] | None = None,
        loaded_graphs: Mapping[str, GraphDocument] | None = None,
    ) -> tuple[FocusDocument, ...]:
        if len(names) != len(set(names)):
            raise UIFailure("duplicate_focus", "Select every focus at most once.")
        allowed = {item.name: item for item in (
            self._focus_documents() if documents is None else documents
        )}
        outside = sorted(set(names) - set(allowed))
        if outside:
            raise UIFailure(
                "focus_outside_scope",
                f"Focus is outside the UI scope: {', '.join(outside)}",
            )
        documents = tuple(allowed[name] for name in names)
        stale = self._focus_stale_reasons(documents, loaded_graphs=loaded_graphs)
        if stale:
            name = sorted(stale)[0]
            raise FocusFailure("focus_stale", stale[name])
        return documents

    def _focus_stale_reasons(
        self,
        documents: tuple[FocusDocument, ...],
        *,
        loaded_graphs: Mapping[str, GraphDocument] | None = None,
        loaded_lineages: Mapping[str, LineageDocument] | None = None,
    ) -> dict[str, str]:
        graph_names = sorted(
            {
                item.name
                for document in documents
                for item in document.sources
                if item.kind == "graph"
            }
        )
        lineage_names = sorted(
            {
                item.name
                for document in documents
                for item in document.sources
                if item.kind == "lineage"
            }
        )
        graphs: dict[str, GraphDocument] = {}
        lineages: dict[str, LineageDocument] = {}
        missing: dict[tuple[str, str], str] = {}
        for name in graph_names:
            try:
                graphs[name] = (
                    loaded_graphs[name] if loaded_graphs is not None and name in loaded_graphs
                    else load_graph_use_case(name, runtime=self.runtime)
                )
            except GraphFailure:
                missing[("graph", name)] = f"Missing graph source: {name}"
        for name in lineage_names:
            try:
                lineages[name] = (
                    loaded_lineages[name]
                    if loaded_lineages is not None and name in loaded_lineages
                    else load_lineage_use_case(name, runtime=self.runtime)
                )
            except LineageFailure:
                missing[("lineage", name)] = f"Missing lineage source: {name}"
        stale: dict[str, str] = {}
        for document in documents:
            missing_reasons = [
                missing[(item.kind, item.name)]
                for item in document.sources
                if (item.kind, item.name) in missing
            ]
            if missing_reasons:
                stale[document.name] = f"Focus {document.name} is stale; {missing_reasons[0]}."
                continue
            try:
                require_current_focus(
                    document,
                    lineages=lineages,
                    graphs=graphs,
                )
            except FocusFailure as exc:
                stale[document.name] = str(exc)
        return stale

    def read(
        self, route: str, query: Mapping[str, list[str]] | None = None,
    ) -> Mapping[str, object]:
        if route == "/api/lineage/edge":
            return self._lineage_edge((query or {}).get("id", [""])[0])
        if route == "/api/retrieval/settings":
            return self._retrieval_settings()
        if route == "/api/architecture" and self.architecture:
            return self.architecture.snapshot()
        if route == "/api/bootstrap":
            return self.bootstrap()
        if route == "/api/index/status":
            return self._index_status()
        raise UIFailure("route_not_found", "Unknown UI API route.", status=404)

    def _index_status(self) -> IndexStatus | WorkspaceIndexStatus:
        if self.config.workspace:
            return retrieval_workspace_status_use_case(
                self.config.workspace, systems=self.config.systems,
                graphs=self.config.graphs, areas=self.config.areas,
                schemas=self.config.schemas, zones=self.config.zones,
                model_path=self._retrieval_model_path(),
                runtime=self.runtime,
            )
        return retrieval_index_status_use_case(
            self._single_graph(), model_path=self._retrieval_model_path(),
            runtime=self.runtime,
        )

    def _require_editable(self) -> None:
        if not self.config.editable:
            raise UIFailure("read_only", "Restart TAREL UI with --edit to change data.", status=403)

    def _retrieval_settings(self) -> dict[str, Any]:
        return {"settings": load_settings(self.runtime).to_dict(),
                "providers": [name for name in list_provider_names() if name != "local"],
                "search_mode": self.config.search_mode}

    def _retrieval_model_path(self) -> Path | None:
        if settings_path(self.runtime).is_file() or (
            self.runtime is not None and self.runtime.retrieval_settings is not None
        ):
            return None
        return self.config.model_path


    def _check_graph_revision(self, payload: dict[str, Any]) -> str:
        graph_name = self._payload_graph(payload)
        expected = require_string(payload, "revision")
        current = graph_revision(load_graph_use_case(graph_name, runtime=self.runtime))
        if expected != current:
            raise UIFailure(
                "stale_graph",
                "The graph changed after this page was loaded. Reload before saving.",
                status=409,
            )
        return graph_name

    def _scope(self):
        if not self.config.workspace:
            raise UIFailure("workspace_required", "A workspace is required for scoped UI mode.")
        return resolve_workspace_scope_use_case(
            self.config.workspace,
            systems=self.config.systems,
            graphs=self.config.graphs,
            areas=self.config.areas,
            schemas=self.config.schemas,
            zones=self.config.zones,
            runtime=self.runtime,
        )

    def _graph_names(self) -> tuple[str, ...]:
        if self.config.workspace:
            return self._scope().graph_names
        return (self._single_graph(),)

    def _single_graph(self) -> str:
        if self.config.graph:
            return self.config.graph
        raise UIFailure(
            "ui_source_required",
            "Choose a graph or pass --workspace for a multi-graph view.",
        )

    def _payload_graph(self, payload: dict[str, Any]) -> str:
        value = optional_string(payload.get("graph"))
        names = self._graph_names()
        if value is None:
            if len(names) == 1:
                return names[0]
            raise UIFailure(
                "graph_required",
                "Choose the graph that owns the object before saving.",
            )
        if value not in names:
            raise UIFailure("graph_outside_scope", f"Graph is outside the UI scope: {value}")
        return value

    def _save_zone(self, payload: dict[str, Any]) -> dict[str, Any]:
        workspace_name = require_string(payload, "workspace")
        system_name = require_string(payload, "system")
        area_name = require_string(payload, "area")
        zone_name = require_string(payload, "zone")
        description = optional_string(payload.get("description"))
        members = payload.get("members", [])
        if not isinstance(members, list) or not members:
            raise UIFailure("empty_zone", "A zone requires at least one table or view.")

        existing_names = set(list_workspaces_use_case(runtime=self.runtime))
        if workspace_name in existing_names:
            workspace = load_workspace_use_case(workspace_name, runtime=self.runtime)
            expected = payload.get("workspace_revision")
            if expected is not None and expected != workspace_revision(workspace):
                raise UIFailure(
                    "stale_workspace",
                    "The workspace changed after this page was loaded. Reload before saving.",
                    status=409,
                )
        else:
            create_workspace_use_case(
                workspace_name,
                description="Created by the local TAREL UI.",
                runtime=self.runtime,
            )
            workspace = load_workspace_use_case(workspace_name, runtime=self.runtime)

        system = next((item for item in workspace.systems if item.name == system_name), None)
        member_refs = self._zone_member_references(members)
        member_graphs = tuple(sorted({item[0] for item in member_refs}))
        if system is None:
            define_workspace_system_use_case(
                workspace_name,
                system_name,
                graph_names=member_graphs,
                description="Local TAREL UI system.",
                runtime=self.runtime,
            )
        elif not set(member_graphs) <= set(system.graphs):
            define_workspace_system_use_case(
                workspace_name,
                system_name,
                graph_names=tuple(sorted(set(system.graphs) | set(member_graphs))),
                description=system.description,
                runtime=self.runtime,
            )

        workspace = load_workspace_use_case(workspace_name, runtime=self.runtime)
        system = next(item for item in workspace.systems if item.name == system_name)
        assigned = {
            (schema.graph, schema.namespace)
            for area in system.areas
            for schema in area.schemas
        }
        required = {
            (graph_name, namespace)
            for graph_name, _label, namespace in member_refs
        }
        unassigned = required - assigned
        if unassigned:
            area = next((item for item in system.areas if item.name == area_name), None)
            references = {
                f"{schema.graph}:{schema.namespace}"
                for schema in area.schemas
            } if area else set()
            references.update(f"{graph_name}:{namespace}" for graph_name, namespace in unassigned)
            define_workspace_area_use_case(
                workspace_name,
                system_name,
                area_name,
                schema_references=tuple(sorted(references)),
                description=area.description if area else "Schemas assigned by the local TAREL UI.",
                runtime=self.runtime,
            )

        result = define_workspace_zone_use_case(
            workspace_name,
            system_name,
            zone_name,
            object_references=tuple(
                f"{graph_name}:{label}" for graph_name, label, _namespace in member_refs
            ),
            description=description,
            runtime=self.runtime,
        )
        return {
            "workspace": result.workspace.to_dict(),
            "workspace_revision": workspace_revision(result.workspace),
        }

    def _zone_member_references(
        self,
        members: list[object],
    ) -> tuple[tuple[str, str, str], ...]:
        references: list[tuple[str, str, str]] = []
        reference: str | None
        for value in members:
            if isinstance(value, str):
                graph_name = self._payload_graph({})
                reference = value
                object_id = None
            elif isinstance(value, dict):
                graph_name = require_string(value, "graph")
                if graph_name not in self._graph_names():
                    raise UIFailure(
                        "graph_outside_scope",
                        f"Graph is outside the UI scope: {graph_name}",
                    )
                reference = optional_string(value.get("label"))
                object_id = optional_string(value.get("object_id"))
                if reference is None and object_id is None:
                    raise UIFailure(
                        "invalid_request",
                        "Zone members require label or object_id.",
                    )
            else:
                raise UIFailure("invalid_request", "Zone members must be strings or objects.")

            graph = load_graph_use_case(graph_name, runtime=self.runtime)
            matches = [
                node
                for node in graph.nodes
                if node.type in {"table", "view"}
                and (node.id == object_id or node.label == reference)
            ]
            if len(matches) != 1:
                shown = reference or object_id or "unknown"
                raise UIFailure("zone_object_not_found", f"Unknown graph object: {shown}")
            node = matches[0]
            references.append(
                (graph_name, node.label, str(node.metadata.get("namespace") or ""))
            )
        return tuple(sorted(set(references)))


def _file_signature(path: Path) -> tuple[int, int]:
    """Saves replace the file, so its time and size tell whether a document changed."""
    try:
        status = path.stat()
    except OSError:
        return (0, 0)
    return (status.st_mtime_ns, status.st_size)


# POST routes that only read state or change view and retrieval settings.
_POST_ROUTES: dict[str, Callable[[TarelUIBackend, dict[str, Any]], Mapping[str, object]]] = {
    "/api/retrieval/settings": TarelUIBackend._post_retrieval_settings,
    "/api/retrieval/models": TarelUIBackend._post_retrieval_models,
    "/api/retrieval/download": TarelUIBackend._post_retrieval_download,
    "/api/optional/details": TarelUIBackend._post_optional_details,
    "/api/optional/view": TarelUIBackend._post_optional_view,
    "/api/index/build": TarelUIBackend._post_index_build,
    "/api/review/view": TarelUIBackend._post_review_view,
    "/api/logical/metadata": TarelUIBackend._post_logical_metadata,
    "/api/families/view": TarelUIBackend._post_families_view,
    "/api/families/members": TarelUIBackend._post_families_members,
    "/api/focus/select": TarelUIBackend._post_focus_select,
    "/api/lineage/upstream": TarelUIBackend._post_lineage_upstream,
    "/api/lineage/neighbourhood": TarelUIBackend._post_lineage_neighbourhood,
}


# POST routes that change stored knowledge; they require the browser's edit mode.
_EDIT_ROUTES: dict[str, Callable[[TarelUIBackend, dict[str, Any]], Mapping[str, object]]] = {
    "/api/annotation/edit": TarelUIBackend._post_annotation_edit,
    "/api/semantic/edit": TarelUIBackend._post_semantic_edit,
    "/api/annotation/decision": TarelUIBackend._post_annotation_decision,
    "/api/lineage/decision": TarelUIBackend._post_lineage_decision,
    "/api/manual/job": TarelUIBackend._post_manual_job,
    "/api/manual/hop": TarelUIBackend._post_manual_hop,
    "/api/zone/save": TarelUIBackend._post_zone_save,
}
