"""Graph use cases: build a graph from a source, import a catalog, refresh, list and load."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from tarel.annotations.application import save_provider_annotation
from tarel.annotations.contracts import AnnotationFailure, AnnotationRunResult
from tarel.annotations.runner import run_annotation_batch
from tarel.annotations.tasks import plan_annotation_delta_tasks
from tarel.connectors.application import discover_catalog_use_case
from tarel.connectors.catalog import validate_catalog_result
from tarel.connectors.contracts import CatalogResult
from tarel.errors import TarelError
from tarel.graph.build import build_graph_from_catalog
from tarel.graph.contracts import GraphDocument, GraphFailure
from tarel.graph.refresh import GraphRefreshReport, refresh_graph, unchanged_refresh_report
from tarel.graph.revision import graph_revision, technical_graph_fingerprint
from tarel.providers.host import load_provider
from tarel.runtime import TarelRuntime, resolve_runtime
from tarel.workspaces.impact import WorkspaceChangeImpact, workspace_change_impacts


@dataclass(frozen=True, slots=True)
class GraphBuildResult:
    graph: GraphDocument
    path: Path


@dataclass(frozen=True, slots=True)
class GraphRefreshResult:
    graph: GraphDocument
    path: Path
    change_report_path: Path | None
    report: GraphRefreshReport
    workspace_impacts: tuple[WorkspaceChangeImpact, ...]
    annotation_run: AnnotationRunResult | None = None

    @property
    def changed(self) -> bool:
        return bool(self.report.changes)

    @property
    def status(self) -> str:
        return "changed" if self.changed else "unchanged"


def build_graph_use_case(
    name: str,
    *,
    connector_name: str,
    config_path: Path | None = None,
    database: str | None = None,
    namespace: str | None = None,
    runtime: TarelRuntime | None = None,
) -> GraphBuildResult:
    store = resolve_runtime(runtime).graph_store()
    previous = store.load(name) if name in store.list() else None
    catalog = discover_catalog_use_case(
        connector_name,
        config_path=config_path,
        database=database,
        namespace=namespace,
    )
    graph = build_graph_from_catalog(name, catalog)
    path = (
        store.create(graph) if previous is None
        else store.save(graph, expected_revision=graph_revision(previous))
    )
    store.record_observation(name, namespace=namespace)
    return GraphBuildResult(graph=graph, path=path)


def import_catalog_use_case(
    name: str,
    catalog: CatalogResult,
    *,
    runtime: TarelRuntime | None = None,
) -> GraphBuildResult:
    store = resolve_runtime(runtime).graph_store()
    if name in store.list():
        raise GraphFailure(
            "graph_exists",
            f"Graph already exists: {name}. Catalog import never overwrites a graph.",
        )
    validate_catalog_result(catalog)
    graph = build_graph_from_catalog(name, catalog)
    path = store.create(graph)
    store.record_observation(name, namespace=None)
    return GraphBuildResult(graph=graph, path=path)


def refresh_graph_use_case(
    name: str,
    *,
    config_path: Path | None = None,
    namespace: str | None = None,
    annotate_new_provider: str | None = None,
    annotation_workers: int = 1,
    annotation_model: str | None = None,
    annotation_timeout: float = 120.0,
    runtime: TarelRuntime | None = None,
) -> GraphRefreshResult:
    store = resolve_runtime(runtime).graph_store()
    try:
        result, observed_namespace = _refresh_from_source(
            name, config_path=config_path, namespace=namespace, runtime=runtime,
        )
    except TarelError as exc:
        if name in store.list():
            store.record_failed_observation(name, exc.code, str(exc))
        raise
    store.record_observation(name, namespace=observed_namespace)
    return _annotate_new_refresh_gaps(
        result,
        provider_name=annotate_new_provider,
        workers=annotation_workers,
        model=annotation_model,
        timeout=annotation_timeout,
        runtime=runtime,
    )


def _refresh_from_source(
    name: str,
    *,
    config_path: Path | None,
    namespace: str | None,
    runtime: TarelRuntime | None,
) -> tuple[GraphRefreshResult, str | None]:
    store = resolve_runtime(runtime).graph_store()
    current = store.load(name)
    current_namespaces = {
        str(node.metadata.get("namespace"))
        for node in current.nodes
        if node.type in {"table", "view"} and node.metadata.get("namespace")
    }
    selected_namespace = (
        namespace
        if namespace is not None
        else next(iter(current_namespaces))
        if len(current_namespaces) == 1
        else None
    )
    catalog = discover_catalog_use_case(
        current.connector,
        config_path=config_path,
        database=current.catalog,
        namespace=selected_namespace,
    )
    discovered = build_graph_from_catalog(name, catalog)
    observed_fingerprint = technical_graph_fingerprint(current)
    report: GraphRefreshReport
    change_report_path: Path | None = None
    workspace_impacts: tuple[WorkspaceChangeImpact, ...] = ()

    def reconcile(latest: GraphDocument) -> GraphDocument:
        nonlocal report, change_report_path, workspace_impacts
        if technical_graph_fingerprint(latest) != observed_fingerprint:
            raise GraphFailure(
                "graph_conflict", "Graph schema changed during observation; retry refresh."
            )
        _validate_refresh_observation(latest, discovered, selected_namespace=selected_namespace)
        if technical_graph_fingerprint(latest) == technical_graph_fingerprint(discovered):
            report = unchanged_refresh_report(latest)
            return latest
        refreshed, report = refresh_graph(latest, discovered)
        workspace_store = resolve_runtime(runtime).workspace_store()
        workspace_impacts = tuple(
            impact
            for workspace_name in workspace_store.list()
            for impact in workspace_change_impacts(
                workspace_store.load(workspace_name), name, report,
            )
        )
        if report.before_revision != report.after_revision:
            change_report_path = resolve_runtime(runtime).graph_change_store().save(name, report)
        return refreshed

    refreshed, path = store.update(name, reconcile)
    result = GraphRefreshResult(
        graph=refreshed, path=path, change_report_path=change_report_path,
        report=report, workspace_impacts=workspace_impacts,
    )
    return result, selected_namespace


def _annotate_new_refresh_gaps(
    result: GraphRefreshResult,
    *,
    provider_name: str | None,
    workers: int,
    model: str | None,
    timeout: float,
    runtime: TarelRuntime | None,
) -> GraphRefreshResult:
    if provider_name is None:
        return result
    nodes = result.graph.node_by_id()
    object_ids = {
        change.target_id
        for change in result.report.changes
        if change.kind == "object_added"
    }
    fields_by_target: dict[str, list[str]] = {object_id: [] for object_id in object_ids}
    for change in result.report.changes:
        if change.kind != "field_added" or change.object_id is None:
            continue
        field = nodes.get(change.target_id)
        if field is not None:
            fields_by_target.setdefault(change.object_id, []).append(field.label)
    tasks = plan_annotation_delta_tasks(
        result.graph,
        {
            target_id: tuple(sorted(field_names, key=str.casefold))
            for target_id, field_names in fields_by_target.items()
        },
        include_object_targets=frozenset(object_ids),
    )
    if not tasks:
        return replace(
            result,
            annotation_run=AnnotationRunResult(planned=0, annotated=0, failed=0),
        )
    store = resolve_runtime(runtime).graph_store()
    provider = load_provider(provider_name, timeout=timeout)
    try:
        updated, run = run_annotation_batch(
            result.graph,
            tasks,
            provider,
            workers=workers,
            retry=0,
            retry_backoff=0,
            skip_errors=False,
            max_errors=None,
            model=model,
            apply_proposal=lambda envelope: save_provider_annotation(
                store, result.graph.name, envelope, provider.name, model or provider.default_model,
            ),
        )
    except AnnotationFailure:
        _align_refresh_report(result, store.load(result.graph.name), runtime=runtime)
        raise
    updated = store.load(result.graph.name)
    path = store.path(result.graph.name)
    aligned = _align_refresh_report(result, updated, runtime=runtime)
    return replace(aligned, graph=updated, path=path, annotation_run=run)


def _align_refresh_report(
    result: GraphRefreshResult,
    graph: GraphDocument,
    *,
    runtime: TarelRuntime | None,
) -> GraphRefreshResult:
    """Bind a source-change report to the graph revision persisted after annotation."""
    revision = graph_revision(graph)
    if result.report.after_revision == revision:
        return result
    report = replace(result.report, after_revision=revision)
    report_path = resolve_runtime(runtime).graph_change_store().save(graph.name, report)
    return replace(result, report=report, change_report_path=report_path)


def _validate_refresh_observation(
    current: GraphDocument,
    discovered: GraphDocument,
    *,
    selected_namespace: str | None,
) -> None:
    current_objects = tuple(
        node for node in current.nodes if node.type in {"table", "view"}
    )
    discovered_objects = tuple(
        node for node in discovered.nodes if node.type in {"table", "view"}
    )
    if current_objects and not discovered_objects:
        raise GraphFailure(
            "empty_refresh_observation",
            "Refresh returned no objects for a non-empty graph; the saved graph was not changed.",
        )
    if selected_namespace is None:
        return
    selected_identifier = selected_namespace.casefold()
    current_namespaces = {
        str(node.metadata.get("namespace")).casefold()
        for node in current_objects
        if node.metadata.get("namespace")
    }
    if current_namespaces - {selected_identifier}:
        raise GraphFailure(
            "partial_refresh_scope",
            "A namespace-scoped refresh cannot replace a graph that contains other namespaces.",
        )
    discovered_namespaces = {
        str(node.metadata.get("namespace")).casefold()
        for node in discovered_objects
        if node.metadata.get("namespace")
    }
    if discovered_namespaces != {selected_identifier}:
        raise GraphFailure(
            "refresh_scope_mismatch",
            "The connector observation did not match the requested namespace scope.",
        )


def list_graphs_use_case(*, runtime: TarelRuntime | None = None) -> tuple[str, ...]:
    return resolve_runtime(runtime).graph_store().list()


def load_graph_use_case(
    name: str,
    *,
    runtime: TarelRuntime | None = None,
) -> GraphDocument:
    return resolve_runtime(runtime).graph_store().load(name)
