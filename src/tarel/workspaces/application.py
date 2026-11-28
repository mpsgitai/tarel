"""Workspace use cases: systems, areas, zones, cross-graph relationships and scopes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tarel.focus.application import focus_object_allowlist
from tarel.graph.contracts import GraphDocument
from tarel.graph.store import FileGraphStore
from tarel.runtime import TarelRuntime, resolve_runtime
from tarel.workspaces.contracts import (
    SchemaReference,
    WorkspaceDocument,
    WorkspaceFailure,
    WorkspaceRelationship,
)
from tarel.workspaces.core import (
    ResolvedZone,
    add_workspace_relationship,
    create_workspace,
    decide_workspace_relationship,
    define_area,
    define_system,
    define_zone,
    parse_schema_reference,
    require_system,
    resolve_zone,
)
from tarel.workspaces.overview import GraphStats, build_workspace_overview
from tarel.workspaces.scope import (
    ResolvedScope,
    ScopeSelection,
    intersect_scope_objects,
    resolve_scope,
)


@dataclass(frozen=True, slots=True)
class WorkspaceChangeResult:
    workspace: WorkspaceDocument
    path: Path


@dataclass(frozen=True, slots=True)
class WorkspaceRelationshipChangeResult:
    workspace: WorkspaceDocument
    path: Path
    relationship: WorkspaceRelationship
    previous_state: str | None = None


def create_workspace_use_case(
    name: str,
    *,
    description: str | None = None,
    runtime: TarelRuntime | None = None,
) -> WorkspaceChangeResult:
    store = resolve_runtime(runtime).workspace_store()
    if name in store.list():
        raise WorkspaceFailure("workspace_exists", f"Workspace already exists: {name}")
    workspace = create_workspace(name, description=description)
    return WorkspaceChangeResult(workspace=workspace, path=store.save(workspace))


def list_workspaces_use_case(*, runtime: TarelRuntime | None = None) -> tuple[str, ...]:
    return resolve_runtime(runtime).workspace_store().list()


def load_workspace_use_case(
    name: str,
    *,
    runtime: TarelRuntime | None = None,
) -> WorkspaceDocument:
    return resolve_runtime(runtime).workspace_store().load(name)


def workspace_overview_use_case(
    name: str,
    *,
    depth: str = "index",
    include_stats: bool = False,
    runtime: TarelRuntime | None = None,
) -> dict[str, object]:
    """A tiered overview (index, zones or full); ``include_stats`` reads object counts."""
    state = resolve_runtime(runtime)
    workspace = state.workspace_store().load(name)
    stats = None
    if include_stats and depth != "full":
        store = state.graph_store()
        graphs = sorted({graph for system in workspace.systems for graph in system.graphs})
        stats = {graph: _graph_stats(store, graph) for graph in graphs}
    return build_workspace_overview(workspace, depth=depth, stats=stats)


def _graph_stats(store: FileGraphStore, name: str) -> GraphStats:
    """Objects and objects carrying a non-rejected annotation, read page by page."""
    objects = annotated = 0
    offset: int | None = 0
    while offset is not None:
        page = store.list_objects(name, offset=offset, limit=1000)
        objects += len(page.objects)
        annotated += sum(
            item.annotation is not None and item.annotation.state != "rejected"
            for item in page.objects
        )
        offset = page.next_offset
    return GraphStats(objects, annotated)


def resolve_workspace_scope_use_case(
    workspace_name: str,
    *,
    systems: tuple[str, ...] = (),
    graphs: tuple[str, ...] = (),
    areas: tuple[str, ...] = (),
    schemas: tuple[str, ...] = (),
    zones: tuple[str, ...] = (),
    focuses: tuple[str, ...] = (),
    objects: tuple[str, ...] = (),
    runtime: TarelRuntime | None = None,
) -> ResolvedScope:
    _workspace, _loaded, scope = load_workspace_scope(
        workspace_name,
        systems=systems,
        graphs=graphs,
        areas=areas,
        schemas=schemas,
        zones=zones,
        focuses=focuses,
        objects=objects,
        runtime=runtime,
    )
    return scope


def load_workspace_scope(
    workspace_name: str,
    *,
    systems: tuple[str, ...] = (),
    graphs: tuple[str, ...] = (),
    areas: tuple[str, ...] = (),
    schemas: tuple[str, ...] = (),
    zones: tuple[str, ...] = (),
    focuses: tuple[str, ...] = (),
    objects: tuple[str, ...] = (),
    runtime: TarelRuntime | None = None,
) -> tuple[WorkspaceDocument, dict[str, GraphDocument], ResolvedScope]:
    workspace = resolve_runtime(runtime).workspace_store().load(workspace_name)
    graph_names = {
        graph_name
        for system in workspace.systems
        if not systems or system.name in systems
        for graph_name in system.graphs
    }
    graph_store = resolve_runtime(runtime).graph_store()
    loaded = {name: graph_store.load(name) for name in sorted(graph_names)}
    scope = resolve_scope(
        workspace,
        loaded,
        ScopeSelection(
            systems=systems,
            graphs=graphs,
            areas=areas,
            schemas=schemas,
            zones=zones,
            focuses=focuses,
            objects=objects,
        ),
    )
    if focuses:
        allowed, warnings = focus_object_allowlist(
            focuses, graph_names=scope.graph_names, runtime=runtime,
        )
        scope = intersect_scope_objects(scope, allowed, warnings=warnings)
    return workspace, loaded, scope


def load_workspace_scope_use_case(
    workspace_name: str,
    *,
    systems: tuple[str, ...] = (),
    graphs: tuple[str, ...] = (),
    areas: tuple[str, ...] = (),
    schemas: tuple[str, ...] = (),
    zones: tuple[str, ...] = (),
    runtime: TarelRuntime | None = None,
) -> tuple[WorkspaceDocument, dict[str, GraphDocument], ResolvedScope]:
    """Reuse the validated documents within one UI request, without a shared cache."""
    return load_workspace_scope(
        workspace_name, systems=systems, graphs=graphs, areas=areas,
        schemas=schemas, zones=zones, runtime=runtime,
    )


def define_workspace_system_use_case(
    workspace_name: str,
    system_name: str,
    *,
    graph_names: tuple[str, ...],
    description: str | None = None,
    runtime: TarelRuntime | None = None,
) -> WorkspaceChangeResult:
    workspace_store = resolve_runtime(runtime).workspace_store()
    graph_store = resolve_runtime(runtime).graph_store()
    workspace = workspace_store.load(workspace_name)
    graphs = {name: graph_store.load(name) for name in graph_names}
    updated = define_system(
        workspace,
        system_name,
        graph_names=graph_names,
        graphs=graphs,
        description=description,
    )
    return WorkspaceChangeResult(workspace=updated, path=workspace_store.save(updated))


def define_workspace_area_use_case(
    workspace_name: str,
    system_name: str,
    area_name: str,
    *,
    schema_references: tuple[str, ...],
    description: str | None = None,
    runtime: TarelRuntime | None = None,
) -> WorkspaceChangeResult:
    workspace_store = resolve_runtime(runtime).workspace_store()
    graph_store = resolve_runtime(runtime).graph_store()
    workspace = workspace_store.load(workspace_name)
    system = require_system(workspace, system_name)
    schemas: tuple[SchemaReference, ...] = tuple(
        parse_schema_reference(reference) for reference in schema_references
    )
    graphs = {name: graph_store.load(name) for name in system.graphs}
    updated = define_area(
        workspace,
        system_name,
        area_name,
        schemas=schemas,
        graphs=graphs,
        description=description,
    )
    return WorkspaceChangeResult(workspace=updated, path=workspace_store.save(updated))


def define_workspace_zone_use_case(
    workspace_name: str,
    system_name: str,
    zone_name: str,
    *,
    object_references: tuple[str, ...],
    description: str | None = None,
    runtime: TarelRuntime | None = None,
) -> WorkspaceChangeResult:
    workspace_store = resolve_runtime(runtime).workspace_store()
    graph_store = resolve_runtime(runtime).graph_store()
    workspace = workspace_store.load(workspace_name)
    system = require_system(workspace, system_name)
    graphs = {name: graph_store.load(name) for name in system.graphs}
    updated = define_zone(
        workspace,
        system_name,
        zone_name,
        object_references=object_references,
        graphs=graphs,
        description=description,
    )
    return WorkspaceChangeResult(workspace=updated, path=workspace_store.save(updated))


def add_workspace_relationship_use_case(
    workspace_name: str,
    *,
    source_reference: str,
    target_reference: str,
    reason: str,
    validated: bool = False,
    runtime: TarelRuntime | None = None,
) -> WorkspaceRelationshipChangeResult:
    workspace_store = resolve_runtime(runtime).workspace_store()
    graph_store = resolve_runtime(runtime).graph_store()
    workspace = workspace_store.load(workspace_name)
    graph_names = {name for system in workspace.systems for name in system.graphs}
    graphs = {name: graph_store.load(name) for name in sorted(graph_names)}
    updated, relationship = add_workspace_relationship(
        workspace,
        source_reference=source_reference,
        target_reference=target_reference,
        graphs=graphs,
        reason=reason,
        validated=validated,
    )
    return WorkspaceRelationshipChangeResult(
        workspace=updated,
        path=workspace_store.save(updated),
        relationship=relationship,
    )


def decide_workspace_relationship_use_case(
    workspace_name: str,
    relationship_id: str,
    *,
    state: str,
    reason: str,
    runtime: TarelRuntime | None = None,
) -> WorkspaceRelationshipChangeResult:
    workspace_store = resolve_runtime(runtime).workspace_store()
    workspace = workspace_store.load(workspace_name)
    previous_state = next(
        (item.state for item in workspace.relationships if item.id == relationship_id), None
    )
    updated, relationship = decide_workspace_relationship(
        workspace,
        relationship_id,
        state=state,
        reason=reason,
    )
    return WorkspaceRelationshipChangeResult(
        workspace=updated,
        path=workspace_store.save(updated),
        relationship=relationship,
        previous_state=previous_state,
    )


def show_workspace_zone_use_case(
    workspace_name: str,
    system_name: str,
    zone_name: str,
    *,
    runtime: TarelRuntime | None = None,
) -> ResolvedZone:
    workspace = resolve_runtime(runtime).workspace_store().load(workspace_name)
    system = require_system(workspace, system_name)
    graph_store = resolve_runtime(runtime).graph_store()
    graphs = {name: graph_store.load(name) for name in system.graphs}
    return resolve_zone(
        workspace,
        system_name,
        zone_name,
        graphs=graphs,
    )
