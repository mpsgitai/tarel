"""`tarel focus`: bounded lineage-anchored working sets."""

from __future__ import annotations

import argparse
from pathlib import Path

from tarel.cli._args import Subcommands, add_format_argument, add_view_argument
from tarel.cli._output import print_json, render_compact
from tarel.cli._pretty_lineage import render_focus
from tarel.focus.application import build_focus_use_case, list_focuses_use_case, load_focus_use_case
from tarel.focus.contracts import FocusDocument
from tarel.graph.reads import graph_freshness_use_case


def register(subcommands: Subcommands) -> None:
    """Add the `focus` command group to the top-level parser."""
    focus = subcommands.add_parser(
        "focus",
        help="Build reproducible report-to-source slices for demand-driven work.",
    )
    focus_commands = focus.add_subparsers(dest="focus_command")
    focus_build = focus_commands.add_parser(
        "build",
        help="Trace one seed upstream through explicitly selected sources.",
    )
    focus_build.add_argument("name")
    focus_build.add_argument("--seed", required=True)
    focus_build.add_argument("--lineage", action="append", dest="lineages")
    focus_build.add_argument("--graph", action="append", dest="graphs")
    focus_build.add_argument("--max-hops", type=int, default=12)
    focus_build.add_argument(
        "--state",
        action="append",
        choices=("draft", "review_required", "validated"),
    )
    add_format_argument(focus_build)

    focus_show = focus_commands.add_parser("show", help="Show one persisted focus snapshot.")
    focus_show.add_argument("name")
    add_view_argument(focus_show)
    add_format_argument(focus_show, pretty=True)

    focus_list = focus_commands.add_parser("list", help="List persisted focus snapshots.")
    add_format_argument(focus_list)



def dispatch(args: argparse.Namespace) -> int | None:
    """Run a parsed `focus` command; return ``None`` for other commands."""
    if args.command != "focus":
        return None
    command = args.focus_command
    handler = _HANDLERS.get(command)
    if handler is not None:
        return handler(args)
    return None


def _render_focus(
    focus: FocusDocument,
    *,
    output_format: str,
    path: Path | None = None,
) -> None:
    payload = focus.to_dict()
    if path is not None:
        payload["path"] = str(path)
    if output_format == "json":
        print_json(payload)
        return
    print(f"Focus: {focus.name}")
    print(f"Seed: {focus.seed}")
    print(f"Revision: {focus.revision}")
    print(f"Sources: {', '.join(f'{item.kind}:{item.name}' for item in focus.sources)}")
    print(
        f"Members: {len(focus.members)}; hops: {len(focus.hops)}; "
        f"truncated: {'yes' if focus.truncated else 'no'}"
    )
    print("Origins:")
    for item in focus.members:
        if item.origin:
            print(f"- {item.reference} [{item.kind}; {item.source}]")
    print("Scope:")
    for item in focus.members:
        reasons = ", ".join(item.reasons)
        print(f"- depth={item.depth} {item.reference} [{item.kind}; {reasons}]")
    for warning in focus.warnings:
        print(f"Warning: {warning}")
    if path is not None:
        print(f"Path: {path}")


def _run_build(args: argparse.Namespace) -> int:
    result = build_focus_use_case(
        args.name,
        seed=args.seed,
        lineage_names=tuple(args.lineages or ()),
        graph_names=tuple(args.graphs or ()),
        max_hops=args.max_hops,
        states=frozenset(args.state) if args.state else None,
    )
    _render_focus(result.focus, output_format=args.format, path=result.path)
    return 0


def _run_show(args: argparse.Namespace) -> int:
    focus = load_focus_use_case(args.name)
    if args.view == "compact" or args.format == "pretty":
        graphs = tuple(item.name for item in focus.sources if item.kind == "graph")
        payload = focus.to_compact_dict(freshness=graph_freshness_use_case(graphs))
        if args.format == "pretty":
            render_focus(payload)
        else:
            render_compact(payload, output_format=args.format)
        return 0
    _render_focus(focus, output_format=args.format)
    return 0


def _run_list(args: argparse.Namespace) -> int:
    names = list_focuses_use_case()
    if args.format == "json":
        print_json({"focuses": list(names)})
    else:
        for name in names:
            print(name)
    return 0


_HANDLERS = {
    "build": _run_build,
    "show": _run_show,
    "list": _run_list,
}
