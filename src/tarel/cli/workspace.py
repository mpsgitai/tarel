"""`tarel workspace`: organize graphs into systems, areas, schemas and zones."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

from tarel.cli._args import Subcommands, add_format_argument, add_scope_arguments
from tarel.cli._output import print_json
from tarel.workspaces.application import (
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
)
from tarel.workspaces.contracts import WorkspaceDocument
from tarel.workspaces.core import ResolvedZone
from tarel.workspaces.scope import ResolvedScope


def register(subcommands: Subcommands) -> None:
    """Add the `workspace` command group to the top-level parser."""
    workspace = subcommands.add_parser(
        "workspace",
        help="Organize graphs as systems, areas, schemas, and overlapping zones.",
    )
    workspace_commands = workspace.add_subparsers(dest="workspace_command")

    workspace_create = workspace_commands.add_parser(
        "create",
        help="Create an empty local workspace.",
    )
    workspace_create.add_argument("name")
    workspace_create.add_argument("--description")
    add_format_argument(workspace_create)

    workspace_list = workspace_commands.add_parser("list", help="List local workspaces.")
    add_format_argument(workspace_list)

    workspace_show = workspace_commands.add_parser("show", help="Show one workspace hierarchy.")
    workspace_show.add_argument("name")
    add_format_argument(workspace_show)

    workspace_scope = workspace_commands.add_parser(
        "scope",
        help="Resolve systems, areas, schemas, graphs, and zones to graph objects.",
    )
    workspace_scope.add_argument("name", help="Workspace name.")
    add_scope_arguments(workspace_scope)
    add_format_argument(workspace_scope)

    workspace_system = workspace_commands.add_parser(
        "system",
        help="Define logical systems over one or more graphs.",
    )
    workspace_system_commands = workspace_system.add_subparsers(dest="workspace_system_command")
    workspace_system_define = workspace_system_commands.add_parser(
        "define",
        help="Create or replace a system graph assignment.",
    )
    workspace_system_define.add_argument("workspace_name")
    workspace_system_define.add_argument("system_name")
    workspace_system_define.add_argument("--graph", action="append", required=True, dest="graphs")
    workspace_system_define.add_argument("--description")
    add_format_argument(workspace_system_define)

    workspace_area = workspace_commands.add_parser(
        "area",
        help="Group sibling schemas inside a system.",
    )
    workspace_area_commands = workspace_area.add_subparsers(dest="workspace_area_command")
    workspace_area_define = workspace_area_commands.add_parser(
        "define",
        help="Create or replace an area schema assignment.",
    )
    workspace_area_define.add_argument("workspace_name")
    workspace_area_define.add_argument("system_name")
    workspace_area_define.add_argument("area_name")
    workspace_area_define.add_argument(
        "--schema",
        action="append",
        required=True,
        dest="schemas",
        help="Schema reference as GRAPH:NAMESPACE.",
    )
    workspace_area_define.add_argument("--description")
    add_format_argument(workspace_area_define)

    workspace_zone = workspace_commands.add_parser(
        "zone",
        help="Define overlapping object sets across schemas and areas.",
    )
    workspace_zone_commands = workspace_zone.add_subparsers(dest="workspace_zone_command")
    workspace_zone_define = workspace_zone_commands.add_parser(
        "define",
        help="Create or replace an explicit zone membership.",
    )
    workspace_zone_define.add_argument("workspace_name")
    workspace_zone_define.add_argument("system_name")
    workspace_zone_define.add_argument("zone_name")
    workspace_zone_define.add_argument(
        "--object",
        action="append",
        required=True,
        dest="objects",
        help="Object reference as GRAPH:NAMESPACE.OBJECT.",
    )
    workspace_zone_define.add_argument("--description")
    add_format_argument(workspace_zone_define)

    workspace_zone_show = workspace_zone_commands.add_parser(
        "show",
        help="Resolve a zone to current graph objects and their areas.",
    )
    workspace_zone_show.add_argument("workspace_name")
    workspace_zone_show.add_argument("system_name")
    workspace_zone_show.add_argument("zone_name")
    add_format_argument(workspace_zone_show)

    workspace_relationship = workspace_commands.add_parser(
        "relationship",
        help="Manage explicit joins whose endpoints may belong to different graphs.",
    )
    workspace_relationship_commands = workspace_relationship.add_subparsers(
        dest="workspace_relationship_command"
    )
    workspace_relationship_add = workspace_relationship_commands.add_parser(
        "add",
        help="Add a human-authored cross-graph relationship candidate.",
    )
    workspace_relationship_add.add_argument("workspace_name")
    workspace_relationship_add.add_argument(
        "--from",
        required=True,
        dest="source_reference",
        help="Source field as GRAPH:NAMESPACE.OBJECT.FIELD.",
    )
    workspace_relationship_add.add_argument(
        "--to",
        required=True,
        dest="target_reference",
        help="Target field as GRAPH:NAMESPACE.OBJECT.FIELD.",
    )
    workspace_relationship_add.add_argument("--reason", required=True)
    workspace_relationship_add.add_argument(
        "--validated",
        action="store_true",
        help="Persist as human-validated instead of draft.",
    )
    add_format_argument(workspace_relationship_add)

    workspace_relationship_list = workspace_relationship_commands.add_parser(
        "list",
        help="List persisted workspace relationships.",
    )
    workspace_relationship_list.add_argument("workspace_name")
    add_format_argument(workspace_relationship_list)

    for decision in ("validate", "reject"):
        workspace_relationship_decide = workspace_relationship_commands.add_parser(
            decision,
            help=f"{decision.title()} a workspace relationship.",
        )
        workspace_relationship_decide.add_argument("workspace_name")
        workspace_relationship_decide.add_argument("relationship_id")
        workspace_relationship_decide.add_argument("--reason", required=True)
        add_format_argument(workspace_relationship_decide)



def dispatch(args: argparse.Namespace) -> int | None:
    """Run a parsed `workspace` command; return ``None`` for other commands."""
    if args.command != "workspace":
        return None
    command = args.workspace_command
    nested = getattr(args, f"workspace_{command}_command", None)
    handler = _HANDLERS.get(command) or _NESTED_HANDLERS.get((command, nested))
    return None if handler is None else handler(args)


def _render_workspace(workspace: WorkspaceDocument, *, output_format: str) -> None:
    if output_format == "json":
        print_json(workspace.to_dict(), ensure_ascii=False)
        return
    print(f"Workspace: {workspace.name}")
    if workspace.description:
        print(f"Description: {workspace.description}")
    for system in sorted(workspace.systems, key=lambda item: item.name):
        print(f"System: {system.name}")
        if system.description:
            print(f"  Description: {system.description}")
        print(f"  Graphs: {', '.join(sorted(system.graphs))}")
        for area in sorted(system.areas, key=lambda item: item.name):
            print(f"  Area: {area.name}")
            for schema in sorted(area.schemas, key=lambda item: (item.graph, item.namespace)):
                print(f"    Schema: {schema.graph}:{schema.namespace}")
        for zone in sorted(system.zones, key=lambda item: item.name):
            print(f"  Zone: {zone.name} ({len(zone.members)} objects)")
    if workspace.relationships:
        print(f"Workspace relationships: {len(workspace.relationships)}")
        for relationship in sorted(workspace.relationships, key=lambda item: item.id):
            print(f"  {relationship.id} [{relationship.state}]")


def _render_resolved_zone(zone: ResolvedZone, *, output_format: str) -> None:
    if output_format == "json":
        print_json(zone.to_dict(), ensure_ascii=False)
        return
    print(f"Workspace: {zone.workspace}")
    print(f"System: {zone.system}")
    print(f"Zone: {zone.zone}")
    if zone.description:
        print(f"Description: {zone.description}")
    print(f"Objects: {len(zone.objects)}")
    for item in zone.objects:
        print(f"  {item.graph}:{item.label} [{item.type}; area={item.area}]")


def _render_resolved_scope(scope: ResolvedScope, *, output_format: str) -> None:
    if output_format == "json":
        print_json(scope.to_dict(), ensure_ascii=False)
        return
    print(f"Workspace: {scope.workspace}")
    print(f"Scope hash: {scope.scope_hash}")
    print(f"Graphs: {', '.join(scope.graph_names)}")
    print(f"Objects: {len(scope.objects)}")
    for item in scope.objects:
        context = f"system={item.system}; area={item.area or '-'}"
        zones = f"; zones={','.join(item.zones)}" if item.zones else ""
        print(f"  {item.graph}:{item.label} [{item.type}; {context}{zones}]")


def _render_workspace_relationships(
    workspace_name: str,
    relationships: tuple[dict[str, object], ...],
    *,
    output_format: str,
) -> None:
    payload = {"relationships": list(relationships), "workspace": workspace_name}
    if output_format == "json":
        print_json(payload, ensure_ascii=False)
        return
    print(f"Workspace: {workspace_name}")
    print(f"Relationships: {len(relationships)}")
    for relationship in relationships:
        source = relationship["source"]
        target = relationship["target"]
        if not isinstance(source, dict) or not isinstance(target, dict):
            continue
        print(
            f"- {relationship['id']} [{relationship['state']}] "
            f"{source['graph']}:{source['object_id']}."
            f"{','.join(source['fields'])} -> "
            f"{target['graph']}:{target['object_id']}."
            f"{','.join(target['fields'])}"
        )
        print(f"  Reason: {relationship['reason']}")


def _run_create(args: argparse.Namespace) -> int:
    result = create_workspace_use_case(args.name, description=args.description)
    _render_workspace(result.workspace, output_format=args.format)
    return 0


def _run_list(args: argparse.Namespace) -> int:
    names = list_workspaces_use_case()
    if args.format == "json":
        print_json({"workspaces": list(names)})
    else:
        for name in names:
            print(name)
    return 0


def _run_show(args: argparse.Namespace) -> int:
    result = load_workspace_use_case(args.name)
    _render_workspace(result, output_format=args.format)
    return 0


def _run_scope(args: argparse.Namespace) -> int:
    result = resolve_workspace_scope_use_case(
        args.name,
        systems=tuple(args.systems or ()),
        graphs=tuple(args.graphs or ()),
        areas=tuple(args.areas or ()),
        schemas=tuple(args.schemas or ()),
        zones=tuple(args.zones or ()),
    )
    _render_resolved_scope(result, output_format=args.format)
    return 0


_HANDLERS = {
    "create": _run_create,
    "list": _run_list,
    "show": _run_show,
    "scope": _run_scope,
}


def _run_system_define(args: argparse.Namespace) -> int:
    result = define_workspace_system_use_case(
        args.workspace_name,
        args.system_name,
        graph_names=tuple(args.graphs),
        description=args.description,
    )
    _render_workspace(result.workspace, output_format=args.format)
    return 0


def _run_area_define(args: argparse.Namespace) -> int:
    result = define_workspace_area_use_case(
        args.workspace_name,
        args.system_name,
        args.area_name,
        schema_references=tuple(args.schemas),
        description=args.description,
    )
    _render_workspace(result.workspace, output_format=args.format)
    return 0


def _run_zone_define(args: argparse.Namespace) -> int:
    result = define_workspace_zone_use_case(
        args.workspace_name,
        args.system_name,
        args.zone_name,
        object_references=tuple(args.objects),
        description=args.description,
    )
    _render_workspace(result.workspace, output_format=args.format)
    return 0


def _run_zone_show(args: argparse.Namespace) -> int:
    result = show_workspace_zone_use_case(
        args.workspace_name,
        args.system_name,
        args.zone_name,
    )
    _render_resolved_zone(result, output_format=args.format)
    return 0


def _run_relationship_add(args: argparse.Namespace) -> int:
    result = add_workspace_relationship_use_case(
        args.workspace_name,
        source_reference=args.source_reference,
        target_reference=args.target_reference,
        reason=args.reason,
        validated=args.validated,
    )
    _render_workspace_relationships(
        result.workspace.name,
        (result.relationship.to_dict(),),
        output_format=args.format,
    )
    return 0


def _run_relationship_list(args: argparse.Namespace) -> int:
    workspace = load_workspace_use_case(args.workspace_name)
    _render_workspace_relationships(
        workspace.name,
        tuple(item.to_dict() for item in workspace.relationships),
        output_format=args.format,
    )
    return 0


def _run_relationship_decide(args: argparse.Namespace) -> int:
    result = decide_workspace_relationship_use_case(
        args.workspace_name,
        args.relationship_id,
        state=(
            "validated" if args.workspace_relationship_command == "validate" else "rejected"
        ),
        reason=args.reason,
    )
    if result.previous_state in {"validated", "rejected"} and (
        result.previous_state != result.relationship.state
    ):
        print(
            f"warning: decision changed from {result.previous_state} to "
            f"{result.relationship.state}",
            file=sys.stderr,
        )
    _render_workspace_relationships(
        result.workspace.name,
        (result.relationship.to_dict(),),
        output_format=args.format,
    )
    return 0


# `tarel workspace <group> <action>` subcommands.
_NESTED_HANDLERS: dict[tuple[str, str | None], Callable[[argparse.Namespace], int]] = {
    ("system", "define"): _run_system_define,
    ("area", "define"): _run_area_define,
    ("zone", "define"): _run_zone_define,
    ("zone", "show"): _run_zone_show,
    ("relationship", "add"): _run_relationship_add,
    ("relationship", "list"): _run_relationship_list,
    ("relationship", "reject"): _run_relationship_decide,
    ("relationship", "validate"): _run_relationship_decide,
}
