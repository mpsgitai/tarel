"""`tarel ui`: serve the local browser."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tarel.cli._args import Subcommands, add_scope_arguments


def register(subcommands: Subcommands) -> None:
    """Add the `ui` command group to the top-level parser."""
    ui = subcommands.add_parser(
        "ui",
        help="Open the optional local graph, lineage, and annotation browser.",
    )
    ui.add_argument("graph", nargs="?", help="Single local graph to inspect.")
    ui.add_argument("--workspace", help="Open a workspace across one or more graphs.")
    ui.add_argument(
        "--state-root",
        type=Path,
        help="Explicit private TAREL state root; defaults to .tarel in the current directory.",
    )
    add_scope_arguments(ui)
    ui.add_argument(
        "--lineage",
        action="append",
        dest="lineages",
        help="Lineage document to include; repeat for multiple documents.",
    )
    ui.add_argument(
        "--focus",
        action="append",
        dest="focuses",
        help="Open one saved report or cube focus; repeat to combine focuses.",
    )
    ui.add_argument(
        "--edit",
        action="store_true",
        help="Allow explicit annotation, lineage, relationship, and zone changes.",
    )
    ui.add_argument("--port", type=int, default=0, help="Loopback port; 0 selects a free port.")
    ui.add_argument("--no-open", action="store_true", help="Do not open the browser automatically.")
    ui.add_argument("--families", choices=("confirmed_only", "include_candidates"))
    ui.add_argument(
        "--search-mode", choices=("lexical", "bm25", "vector", "hybrid"),
        default="bm25", help="Local metadata search mode; BM25 needs no model index.",
    )
    ui.add_argument("--model", type=Path, dest="model_path")
    ui.add_argument("--threads", type=int, dest="n_threads")
    ui.add_argument(
        "--architecture-file", type=Path, help="Experimental local architecture sidecar.",
    )
    ui.add_argument(
        "--architecture-edit", action="store_true",
        help="Edit architecture only, not graph annotations.",
    )



def dispatch(args: argparse.Namespace) -> int | None:
    """Run a parsed `ui` command; return ``None`` for other commands."""
    if args.command != "ui":
        return None
    from tarel.runtime import TarelRuntime
    from tarel.ui.contracts import (
        UIFailure,
    )
    from tarel.ui.server import (
        run_ui,
    )

    try:
        return run_ui(
            args.graph,
            workspace=args.workspace,
            systems=tuple(args.systems or ()),
            graphs=tuple(args.graphs or ()),
            areas=tuple(args.areas or ()),
            schemas=tuple(args.schemas or ()),
            zones=tuple(args.zones or ()),
            lineages=tuple(args.lineages or ()),
            focuses=tuple(args.focuses or ()),
            editable=args.edit,
            architecture_file=args.architecture_file,
            architecture_edit=args.architecture_edit,
            family_mode=args.families,
            search_mode=args.search_mode,
            model_path=args.model_path,
            n_threads=args.n_threads,
            port=args.port,
            open_browser=not args.no_open,
            runtime=(
                TarelRuntime.local(args.state_root)
                if args.state_root is not None
                else None
            ),
        )
    except UIFailure as exc:
        print(f"error [{exc.code}]: {exc}", file=sys.stderr)
        return 2
