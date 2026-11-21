"""`tarel grounding`: compile a harness grounding bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tarel.cli._args import (
    Subcommands,
    add_annotation_state_arguments,
    add_format_argument,
    add_logical_hint_arguments,
    add_workspace_retrieval_scope_arguments,
    require_graph_or_workspace,
)
from tarel.context.compiler import DEFAULT_MAX_CONTEXT_CHARACTERS
from tarel.context.grounding import GroundingBundle
from tarel.context.grounding_application import (
    compile_graph_grounding_use_case,
    compile_workspace_grounding_use_case,
)


def register(subcommands: Subcommands) -> None:
    """Add the `grounding` command group to the top-level parser."""
    grounding = subcommands.add_parser(
        "grounding",
        help="Compile agent-ready context with source, dialect, and optional lineage identity.",
    )
    grounding.add_argument("name", nargs="?", help="Graph name; omit it with --workspace NAME.")
    grounding.add_argument("query", help="Analytical question or compact search query.")
    grounding.add_argument("--namespace", "--schema", dest="namespace")
    grounding.add_argument("--lineage", action="append", dest="lineages")
    grounding.add_argument(
        "--source",
        action="append",
        dest="sources",
        help="Select a logical execution source; repeat for multi-graph context.",
    )
    grounding.add_argument("--trace", dest="trace_reference")
    grounding.add_argument("--lineage-limit", type=int, default=8)
    grounding.add_argument(
        "--lineage-mode",
        choices=("lexical", "bm25", "vector", "hybrid"),
        default="bm25",
    )
    grounding.add_argument(
        "--lineage-state",
        action="append",
        dest="lineage_states",
        choices=("draft", "review_required", "validated"),
    )
    grounding.add_argument("--seed-limit", type=int, default=3)
    grounding.add_argument("--max-objects", type=int, default=10)
    grounding.add_argument("--max-joins", type=int, default=12)
    grounding.add_argument("--max-hops", type=int, default=2)
    grounding.add_argument("--max-trace-hops", type=int, default=12)
    grounding.add_argument("--max-fields-per-object", type=int, default=12)
    grounding.add_argument(
        "--max-characters",
        type=int,
        default=DEFAULT_MAX_CONTEXT_CHARACTERS,
    )
    grounding.add_argument(
        "--mode",
        choices=("lexical", "bm25", "vector", "hybrid"),
        default="lexical",
    )
    grounding.add_argument("--model", type=Path, dest="model_path")
    grounding.add_argument("--threads", type=int, dest="n_threads")
    add_workspace_retrieval_scope_arguments(grounding)
    add_annotation_state_arguments(grounding)
    add_logical_hint_arguments(grounding)
    add_format_argument(grounding)



def dispatch(args: argparse.Namespace) -> int | None:
    """Run a parsed `grounding` command; return ``None`` for other commands."""
    if args.command != "grounding":
        return None
    grounding_arguments = {
        "logical_hints": args.logical_hints,
        "lineage_names": tuple(args.lineages or ()),
        "source_names": tuple(args.sources or ()),
        "trace_reference": args.trace_reference,
        "lineage_limit": args.lineage_limit,
        "lineage_mode": args.lineage_mode,
        "lineage_states": (frozenset(args.lineage_states) if args.lineage_states else None),
        "seed_limit": args.seed_limit,
        "max_objects": args.max_objects,
        "max_joins": args.max_joins,
        "max_hops": args.max_hops,
        "max_trace_hops": args.max_trace_hops,
        "max_fields_per_object": args.max_fields_per_object,
        "max_characters": args.max_characters,
        "mode": args.mode,
        "model_path": args.model_path,
        "n_threads": args.n_threads,
        "annotation_states": (
            frozenset(args.annotation_states) if args.annotation_states else None
        ),
        "validated_only": args.validated_only,
    }
    require_graph_or_workspace(args)
    if args.workspace:
        result = compile_workspace_grounding_use_case(
            args.workspace,
            args.query,
            systems=tuple(args.systems or ()),
            graphs=tuple(args.graphs or ()),
            areas=tuple(args.areas or ()),
            schemas=tuple(args.schemas or ()),
            zones=tuple(args.zones or ()),
            **grounding_arguments,
        )
    else:
        result = compile_graph_grounding_use_case(
            args.name,
            args.query,
            namespace=args.namespace,
            **grounding_arguments,
        )
    _render_grounding(result, output_format=args.format)
    return 0


def _render_grounding(result: GroundingBundle, *, output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return
    print(result.stable_prompt(), end="")
    print()
    print(result.dynamic_prompt(), end="")
