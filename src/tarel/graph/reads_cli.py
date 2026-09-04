"""CLI adapter for optional lazy graph reads; JSON output includes actual read statistics."""

from __future__ import annotations

import argparse
import json

from tarel.graph.reads import (
    graph_header_use_case,
    graph_objects_use_case,
    graph_slice_use_case,
    rebuild_graph_index_use_case,
)


def add_graph_read_commands(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    for name in ("header", "objects", "slice", "rebuild-index"):
        parser = commands.add_parser(
            name, help=f"Selective graph {name}; graph.json stays authoritative."
        )
        parser.add_argument("name")
        parser.add_argument("--format", choices=("json", "text"), default="json")
        if name in {"objects", "slice"}:
            parser.add_argument(
                "--object", action="append", dest="object_ids", required=name == "slice"
            )
            parser.add_argument("--namespace")
            parser.add_argument("--revision")
        if name == "objects":
            parser.add_argument("--offset", type=int, default=0)
            parser.add_argument("--limit", type=int, default=100)


def dispatch_graph_read(args: argparse.Namespace) -> int | None:
    if args.command != "graph":
        return None
    command = args.graph_command
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
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0
