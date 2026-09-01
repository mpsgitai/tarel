"""Thin CLI adapter for graph-bound logical-topology overlays."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tarel.topology.application import (
    decide_derived_relation_use_case,
    load_logical_topology_use_case,
    save_logical_topology_use_case,
)
from tarel.topology.contracts import LogicalTopologyDocument, LogicalTopologyFailure


def add_topology_commands(
    subcommands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    topology = subcommands.add_parser(
        "topology",
        help="Import and review typed logical relations without executing them.",
    )
    commands = topology.add_subparsers(dest="topology_command")

    import_command = commands.add_parser(
        "import",
        help="Import one strict graph-bound logical-topology document.",
    )
    import_command.add_argument("--source", required=True, help="JSON path or '-' for stdin.")
    import_command.add_argument("--expected-revision")
    _output_format(import_command)

    show = commands.add_parser("show", help="Show the current logical topology for one graph.")
    show.add_argument("graph")
    _output_format(show)

    review = commands.add_parser(
        "review",
        help="Record one human approval or rejection of a derived relation.",
    )
    review.add_argument("graph")
    review.add_argument("relation_id")
    review.add_argument("--decision", choices=("approve", "reject"), required=True)
    review.add_argument("--reason", required=True)
    review.add_argument("--revision", required=True)
    _output_format(review)


def dispatch_topology(args: argparse.Namespace) -> int | None:
    if args.command != "topology":
        return None
    if args.topology_command == "import":
        document = LogicalTopologyDocument.from_dict(_read_json(args.source))
        saved = save_logical_topology_use_case(
            document,
            expected_revision=args.expected_revision,
        )
        _render(saved, output_format=args.output_format)
        return 0
    if args.topology_command == "show":
        _render(
            load_logical_topology_use_case(args.graph),
            output_format=args.output_format,
        )
        return 0
    if args.topology_command == "review":
        reviewed = decide_derived_relation_use_case(
            args.graph,
            args.relation_id,
            decision=args.decision,
            reason=args.reason,
            expected_revision=args.revision,
        )
        _render(reviewed, output_format=args.output_format)
        return 0
    return 0


def _read_json(path_value: str) -> dict[str, object]:
    try:
        raw = sys.stdin.read() if path_value == "-" else Path(path_value).read_text("utf-8")
        payload = json.loads(raw, object_pairs_hook=_unique_object)
    except FileNotFoundError as exc:
        raise LogicalTopologyFailure(
            "logical_topology_source_not_found",
            f"Logical-topology source not found: {path_value}",
        ) from exc
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise LogicalTopologyFailure(
            "invalid_logical_topology",
            "Could not read logical-topology JSON.",
        ) from exc
    if not isinstance(payload, dict):
        raise LogicalTopologyFailure(
            "invalid_logical_topology",
            "Logical-topology JSON root must be an object.",
        )
    return payload


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def _output_format(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=("text", "json"),
        default="text",
    )


def _render(document: LogicalTopologyDocument, *, output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(document.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
        return
    print(f"Logical topology: {document.graph_name}")
    print(f"Revision: {document.revision}")
    for relation in document.derived_relations:
        operations = " -> ".join(step.kind for step in relation.steps)
        print(
            f"- {relation.name} [{relation.state}]; "
            f"operations={operations}; fields={len(relation.output_schema)}"
        )
