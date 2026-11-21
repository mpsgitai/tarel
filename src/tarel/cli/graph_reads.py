"""CLI adapter for optional lazy graph reads; JSON output includes actual read statistics."""

from __future__ import annotations

import argparse

from tarel.cli._args import Subcommands, add_format_argument
from tarel.cli._output import print_json
from tarel.graph.reads import (
    graph_header_use_case,
    graph_objects_use_case,
    graph_slice_use_case,
    rebuild_graph_index_use_case,
)
from tarel.graph.selective import GraphHeader, GraphObjectPage, GraphSlice


def register(commands: Subcommands) -> None:
    """Add the selective read subcommands to `tarel graph`."""
    for name in ("header", "objects", "slice", "rebuild-index"):
        parser = commands.add_parser(
            name, help=f"Selective graph {name}; graph.json stays authoritative."
        )
        parser.add_argument("name")
        add_format_argument(parser)
        if name in {"objects", "slice"}:
            parser.add_argument(
                "--object", action="append", dest="object_ids", required=name == "slice",
                help="Object label (main.orders) or stable ID; repeatable.",
            )
            parser.add_argument("--namespace")
            parser.add_argument("--revision")
        if name == "objects":
            parser.add_argument("--offset", type=int, default=0)
            parser.add_argument("--limit", type=int, default=100)


def dispatch(args: argparse.Namespace) -> int | None:
    """Run a selective graph read; return ``None`` for other commands."""
    if args.command != "graph":
        return None
    command = args.graph_command
    result: GraphHeader | GraphObjectPage | GraphSlice
    if command == "header":
        result = graph_header_use_case(args.name)
    elif command == "rebuild-index":
        result = rebuild_graph_index_use_case(args.name)
    elif command == "objects":
        result = graph_objects_use_case(
            args.name,
            object_ids=tuple(args.object_ids) if args.object_ids else None,
            namespace=args.namespace,
            expected_revision=args.revision,
            offset=args.offset,
            limit=args.limit,
        )
    elif command == "slice":
        result = graph_slice_use_case(
            args.name,
            tuple(args.object_ids),
            namespace=args.namespace,
            expected_revision=args.revision,
        )
    else:
        return None
    if args.format == "json":
        print_json(result.to_dict(), ensure_ascii=False)
    else:
        _render_text(result)
    return 0


def _render_text(result: GraphHeader | GraphObjectPage | GraphSlice) -> None:
    header = result if isinstance(result, GraphHeader) else result.header
    print(f"Graph: {header.name} ({header.connector}, {header.catalog})")
    print(f"Revision: {header.revision}")
    print(f"Objects: {header.object_count}; nodes: {header.node_count}; edges: {header.edge_count}")
    if isinstance(result, GraphObjectPage):
        last = result.offset + len(result.objects)
        print(f"Page: {result.offset + 1}-{last} of {result.total_objects}")
        for node in result.objects:
            print(f"- {node.label} [{node.type}]")
        if result.next_offset is not None:
            print(f"Next offset: {result.next_offset}")
    elif isinstance(result, GraphSlice):
        nodes = result.graph.node_by_id()
        print(f"Slice: {len(result.graph.nodes)} nodes, {len(result.graph.edges)} edges")
        for object_id in result.object_ids:
            print(f"- {nodes[object_id].label}")
