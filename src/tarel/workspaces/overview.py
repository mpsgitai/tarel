"""Tiered workspace overviews: ``index`` to orient, ``zones`` to choose, ``full`` to edit.

A full workspace document lists every zone member, so for a large estate it is far bigger than
the question "which systems exist and where do I look". The tiers answer that question first:

- ``index``: the workspace and each system with its graphs and area/zone/member counts;
- ``zones``: additionally each system's areas (with their schemas) and zones (with member counts,
  never the member lists);
- ``full``: the unchanged stored document.

Only stored facts appear. Nothing here guesses which lineage belongs to which system; optional
``stats`` count objects and annotations from the graphs themselves.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from tarel.compact import omit_empty
from tarel.errors import unknown_name_error
from tarel.workspaces.contracts import WorkspaceDocument, WorkspaceFailure, WorkspaceSystem

DEPTHS = ("index", "zones", "full")


@dataclass(frozen=True, slots=True)
class GraphStats:
    objects: int
    annotated: int


def build_workspace_overview(
    workspace: WorkspaceDocument,
    *,
    depth: str = "index",
    stats: Mapping[str, GraphStats] | None = None,
    systems: tuple[str, ...] = (),
) -> dict[str, object]:
    if depth not in DEPTHS:
        raise WorkspaceFailure(
            "invalid_workspace_depth",
            f"Unsupported workspace depth: {depth}",
            hint="Use one of: index, zones, full.",
            retryable=True,
            details={"accepted_preview": list(DEPTHS), "param": "depth", "value": depth},
        )
    if depth == "full":
        return workspace.to_dict()
    known = {item.name for item in workspace.systems}
    for name in systems:
        if name not in known:
            raise unknown_name_error(
                WorkspaceFailure, "system_not_found", f"System not found: {name}",
                param="systems", value=name, accepted=known, noun="system",
            )
    selected = [
        _system(item, depth=depth, stats=stats)
        for item in sorted(workspace.systems, key=lambda value: value.name)
        if not systems or item.name in systems
    ]
    return omit_empty(
        {
            "depth": depth,
            "depth_available": list(DEPTHS),
            "description": workspace.description,
            "graph_count": len({name for item in workspace.systems for name in item.graphs}),
            "name": workspace.name,
            "next": {"zones": "depth=zones", "full": "depth=full"}
            if depth == "index"
            else {"full": "depth=full"},
            "relationship_count": len(workspace.relationships),
            "system_count": len(workspace.systems),
            "systems": selected,
            "systems_filter": list(systems),
            "truncated": False,
        }
    )


def _system(
    system: WorkspaceSystem,
    *,
    depth: str,
    stats: Mapping[str, GraphStats] | None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "area_count": len(system.areas),
        "description": system.description,
        "graph_count": len(system.graphs),
        "graphs": sorted(system.graphs),
        "name": system.name,
        "zone_count": len(system.zones),
        "zone_member_count": sum(len(zone.members) for zone in system.zones),
    }
    if stats is not None:
        objects = sum(stats[name].objects for name in system.graphs if name in stats)
        annotated = sum(stats[name].annotated for name in system.graphs if name in stats)
        payload["objects"] = objects
        payload["annotated_pct"] = round(100 * annotated / objects, 1) if objects else None
    if depth == "zones":
        payload["areas"] = [
            omit_empty(
                {
                    "description": area.description,
                    "name": area.name,
                    "schemas": sorted(f"{item.graph}:{item.namespace}" for item in area.schemas),
                }
            )
            for area in sorted(system.areas, key=lambda value: value.name)
        ]
        payload["zones"] = [
            omit_empty(
                {
                    "description": zone.description,
                    "member_count": len(zone.members),
                    "name": zone.name,
                }
            )
            for zone in sorted(system.zones, key=lambda value: value.name)
        ]
    return omit_empty(payload)
