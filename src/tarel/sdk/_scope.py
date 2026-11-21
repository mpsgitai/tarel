"""Workspace scope arguments shared by the search, context, lineage and view facades."""

from __future__ import annotations

from tarel.runtime import TarelRuntime
from tarel.workspaces.application import resolve_workspace_scope_use_case
from tarel.workspaces.contracts import WorkspaceFailure
from tarel.workspaces.scope import ResolvedScope, ScopeSelection


def resolve_workspace_scope(
    runtime: TarelRuntime,
    name: str,
    *,
    selection: ScopeSelection | None,
    systems: tuple[str, ...],
    graphs: tuple[str, ...],
    areas: tuple[str, ...],
    schemas: tuple[str, ...],
    zones: tuple[str, ...],
) -> ResolvedScope:
    systems, graphs, areas, schemas, zones = workspace_scope_arguments(
        selection,
        systems=systems,
        graphs=graphs,
        areas=areas,
        schemas=schemas,
        zones=zones,
    )
    return resolve_workspace_scope_use_case(
        name,
        systems=systems,
        graphs=graphs,
        areas=areas,
        schemas=schemas,
        zones=zones,
        runtime=runtime,
    )


def workspace_scope_arguments(
    selection: ScopeSelection | None,
    *,
    systems: tuple[str, ...],
    graphs: tuple[str, ...],
    areas: tuple[str, ...],
    schemas: tuple[str, ...],
    zones: tuple[str, ...],
) -> tuple[
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
]:
    if selection is None:
        return systems, graphs, areas, schemas, zones
    if any((systems, graphs, areas, schemas, zones)):
        raise WorkspaceFailure(
            "conflicting_workspace_scope",
            "Pass either one WorkspaceScope selection or individual workspace filters.",
        )
    return (
        selection.systems,
        selection.graphs,
        selection.areas,
        selection.schemas,
        selection.zones,
    )


def workspace_focuses(
    selection: ScopeSelection | None,
    focuses: tuple[str, ...],
) -> tuple[str, ...]:
    if selection is None:
        return focuses
    if focuses:
        raise WorkspaceFailure(
            "conflicting_workspace_scope",
            "Pass focus names either in WorkspaceScope or as individual workspace filters.",
        )
    return selection.focuses


def workspace_objects(
    selection: ScopeSelection | None,
    objects: tuple[str, ...],
) -> tuple[str, ...]:
    if selection is None:
        return objects
    if objects:
        raise WorkspaceFailure(
            "conflicting_workspace_scope",
            "Pass object scope either in WorkspaceScope or as individual workspace filters.",
        )
    return selection.objects
