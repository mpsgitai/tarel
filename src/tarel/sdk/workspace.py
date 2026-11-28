"""``tarel.workspace``: systems, areas, zones and cross-graph relationships."""

from __future__ import annotations

from tarel.sdk._base import RuntimeAPI
from tarel.sdk._scope import workspace_focuses, workspace_objects, workspace_scope_arguments
from tarel.workspaces.application import (
    WorkspaceChangeResult,
    WorkspaceRelationshipChangeResult,
    add_workspace_relationship_use_case,
    create_workspace_use_case,
    decide_workspace_relationship_use_case,
    define_workspace_area_use_case,
    define_workspace_system_use_case,
    define_workspace_zone_use_case,
    list_workspaces_use_case,
    load_workspace_use_case,
    resolve_workspace_scope_use_case,
    show_workspace_zone_use_case,
    workspace_overview_use_case,
)
from tarel.workspaces.contracts import WorkspaceDocument, WorkspaceRelationship
from tarel.workspaces.core import ResolvedZone
from tarel.workspaces.scope import ResolvedScope, ScopeSelection


class WorkspaceAPI(RuntimeAPI):
    """Organize graphs into systems, areas and zones and resolve scopes over them."""

    def create(
        self,
        name: str,
        *,
        description: str | None = None,
    ) -> WorkspaceChangeResult:
        return create_workspace_use_case(
            name,
            description=description,
            runtime=self._runtime,
        )

    def list(self) -> tuple[str, ...]:
        return list_workspaces_use_case(runtime=self._runtime)

    def load(self, name: str) -> WorkspaceDocument:
        return load_workspace_use_case(name, runtime=self._runtime)

    def overview(
        self, name: str, *, depth: str = "index", stats: bool = False,
    ) -> dict[str, object]:
        """``index``: systems and counts; ``zones``: adds areas and zones; ``full``: document."""
        return workspace_overview_use_case(
            name, depth=depth, include_stats=stats, runtime=self._runtime,
        )

    def define_system(
        self,
        name: str,
        system: str,
        *,
        graphs: tuple[str, ...],
        description: str | None = None,
    ) -> WorkspaceChangeResult:
        return define_workspace_system_use_case(
            name,
            system,
            graph_names=graphs,
            description=description,
            runtime=self._runtime,
        )

    def define_area(
        self,
        name: str,
        system: str,
        area: str,
        *,
        schemas: tuple[str, ...],
        description: str | None = None,
    ) -> WorkspaceChangeResult:
        return define_workspace_area_use_case(
            name,
            system,
            area,
            schema_references=schemas,
            description=description,
            runtime=self._runtime,
        )

    def define_zone(
        self,
        name: str,
        system: str,
        zone: str,
        *,
        objects: tuple[str, ...],
        description: str | None = None,
    ) -> WorkspaceChangeResult:
        return define_workspace_zone_use_case(
            name,
            system,
            zone,
            object_references=objects,
            description=description,
            runtime=self._runtime,
        )

    def zone(self, name: str, system: str, zone: str) -> ResolvedZone:
        return show_workspace_zone_use_case(
            name,
            system,
            zone,
            runtime=self._runtime,
        )

    def relationships(self, name: str) -> tuple[WorkspaceRelationship, ...]:
        return self.load(name).relationships

    def add_relationship(
        self,
        name: str,
        *,
        source: str,
        target: str,
        reason: str,
        validated: bool = False,
    ) -> WorkspaceRelationshipChangeResult:
        return add_workspace_relationship_use_case(
            name,
            source_reference=source,
            target_reference=target,
            reason=reason,
            validated=validated,
            runtime=self._runtime,
        )

    def decide_relationship(
        self,
        name: str,
        relationship_id: str,
        *,
        state: str,
        reason: str,
    ) -> WorkspaceRelationshipChangeResult:
        return decide_workspace_relationship_use_case(
            name,
            relationship_id,
            state=state,
            reason=reason,
            runtime=self._runtime,
        )

    def scope(
        self,
        name: str,
        *,
        selection: ScopeSelection | None = None,
        systems: tuple[str, ...] = (),
        graphs: tuple[str, ...] = (),
        areas: tuple[str, ...] = (),
        schemas: tuple[str, ...] = (),
        zones: tuple[str, ...] = (),
        focuses: tuple[str, ...] = (),
        objects: tuple[str, ...] = (),
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
            focuses=workspace_focuses(selection, focuses),
            objects=workspace_objects(selection, objects),
            runtime=self._runtime,
        )
