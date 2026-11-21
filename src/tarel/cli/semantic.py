"""Thin CLI adapter for semantic-model imports."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from tarel.cli._args import add_format_argument
from tarel.cli._output import print_json
from tarel.semantics.application import (
    edit_semantic_source_use_case,
    import_semantic_use_case,
    list_semantic_imports_use_case,
    load_semantic_import_use_case,
    read_semantic_patch,
)


def register(
    subcommands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    semantic = subcommands.add_parser(
        "semantic",
        help="Import and inspect external semantic-layer models.",
    )
    commands = semantic.add_subparsers(dest="semantic_command")

    import_command = commands.add_parser(
        "import",
        help="Import a semantic model and bind supported constructs to one TAREL graph.",
    )
    import_command.add_argument("name")
    import_command.add_argument("--graph", required=True)
    import_command.add_argument("--source", required=True, type=Path)
    import_command.add_argument(
        "--source-format",
        dest="semantic_format",
        choices=("ossie", "apache-ossie", "sml", "cube", "cube-yaml"),
        default="ossie",
    )
    import_command.add_argument("--replace", action="store_true")
    add_format_argument(import_command)

    list_command = commands.add_parser("list", help="List saved semantic imports.")
    list_command.add_argument("--graph")
    add_format_argument(list_command)

    show = commands.add_parser("show", help="Show one normalized semantic import.")
    show.add_argument("name")
    show.add_argument("--include-source", action="store_true")
    add_format_argument(show)

    edit = commands.add_parser(
        "edit",
        help="Overlay description or synonym corrections without changing the source snapshot.",
    )
    edit.add_argument("name")
    edit.add_argument("target_id")
    edit.add_argument("--input", required=True, help="Patch JSON file or '-' for stdin.")
    edit.add_argument("--reason", required=True)
    edit.add_argument("--revision")
    add_format_argument(edit)


def dispatch(args: argparse.Namespace) -> int | None:
    if args.command != "semantic":
        return None
    command = args.semantic_command
    handler = _HANDLERS.get(command)
    if handler is not None:
        return handler(args)
    return 0


def _render(payload: dict[str, Any], *, output_format: str) -> None:
    if output_format == "json":
        print_json(payload)
        return
    if "imports" in payload:
        for item in payload["imports"]:
            if isinstance(item, dict):
                print(f"{item['name']}\t{item['graph_name']}\t{item['format_name']}")
        return
    if "name" in payload:
        print(f"Semantic import: {payload['name']}")
    if "graph_name" in payload:
        print(f"Graph: {payload['graph_name']}")
    if "format_name" in payload:
        print(f"Format: {payload['format_name']} {payload.get('format_version', '')}".rstrip())
    if "complete" in payload:
        print(f"Status: {'complete' if payload['complete'] else 'incomplete'}")
    if "diagnostics" in payload and isinstance(payload["diagnostics"], int):
        print(f"Diagnostics: {payload['diagnostics']}")
    if "changed" in payload:
        print(f"Changed: {'yes' if payload['changed'] else 'no'}")
    if "path" in payload:
        print(f"Path: {payload['path']}")
    if "contract_version" in payload:
        print_json(payload)


def _run_import(args: argparse.Namespace) -> int:
    result = import_semantic_use_case(
        args.name,
        graph_name=args.graph,
        source_path=args.source,
        format_name=args.semantic_format,
        replace_existing=args.replace,
    )
    payload = {
        **result.document.summary_dict(),
        "changed": result.changed,
        "path": str(result.path),
    }
    _render(payload, output_format=args.format)
    return 0 if result.document.complete else 1


def _run_list(args: argparse.Namespace) -> int:
    documents = list_semantic_imports_use_case(graph_name=args.graph)
    payload = {
        "count": len(documents),
        "imports": [item.summary_dict() for item in documents],
    }
    _render(payload, output_format=args.format)
    return 0


def _run_show(args: argparse.Namespace) -> int:
    document = load_semantic_import_use_case(args.name)
    _render(
        document.to_dict(include_source_content=args.include_source),
        output_format=args.format,
    )
    return 0 if document.complete else 1


def _run_edit(args: argparse.Namespace) -> int:
    result = edit_semantic_source_use_case(
        args.name,
        args.target_id,
        read_semantic_patch(args.input),
        reason=args.reason,
        expected_revision=args.revision,
    )
    payload = {
        **result.document.summary_dict(),
        "changed": result.changed,
        "path": str(result.path),
        "target_id": args.target_id,
    }
    _render(payload, output_format=args.format)
    return 0


_HANDLERS = {
    "import": _run_import,
    "list": _run_list,
    "show": _run_show,
    "edit": _run_edit,
}
