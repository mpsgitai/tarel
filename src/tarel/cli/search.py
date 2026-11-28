"""`tarel search`: rank graph or workspace objects for a query."""

from __future__ import annotations

import argparse
from pathlib import Path

from tarel.cli._args import (
    Subcommands,
    add_annotation_state_arguments,
    add_format_argument,
    add_workspace_retrieval_scope_arguments,
    graph_scope_object_ids,
    require_graph_or_workspace,
)
from tarel.cli._output import print_json
from tarel.retrieval.search_application import search_graph_use_case, search_workspace_use_case
from tarel.search import SearchFailure, SearchFilters, SearchResults


def register(subcommands: Subcommands) -> None:
    """Add the `search` command group to the top-level parser."""
    search = subcommands.add_parser(
        "search",
        help="Search graph metadata with lexical, BM25, vector, or hybrid retrieval.",
    )
    search.add_argument("name", nargs="?", help="Graph name; omit it with --workspace NAME.")
    search.add_argument("query", help="Words describing the required analytical objects.")
    search.add_argument("--namespace", "--schema", dest="namespace")
    search.add_argument("--limit", type=int, default=20)
    search.add_argument(
        "--families", choices=("off", "confirmed_only", "include_candidates"),
        default="confirmed_only", help="Include logical family-name hits; never expand members.",
    )
    search.add_argument(
        "--mode",
        choices=("lexical", "bm25", "vector", "hybrid"),
        default="lexical",
    )
    search.add_argument("--model", type=Path, dest="model_path")
    search.add_argument("--threads", type=int, dest="n_threads")
    search.add_argument("--bm25-weight", type=float, help="Hybrid BM25 weight; default 1.0.")
    add_workspace_retrieval_scope_arguments(search)
    _add_search_filter_arguments(search)
    _add_workspace_result_arguments(search)
    add_annotation_state_arguments(search)
    add_format_argument(search)



def dispatch(args: argparse.Namespace) -> int | None:
    """Run a parsed `search` command; return ``None`` for other commands."""
    if args.command != "search":
        return None
    search_arguments = {
        "family_mode": None if args.families == "off" else args.families,
        "limit": args.limit,
        "mode": args.mode,
        "model_path": args.model_path,
        "n_threads": args.n_threads,
        "bm25_weight": args.bm25_weight,
        "annotation_states": (
            frozenset(args.annotation_states) if args.annotation_states else None
        ),
        "validated_only": args.validated_only,
        "filters": SearchFilters(
            types=tuple(args.object_types or ()),
            roles=tuple(args.roles or ()),
            required_fields=tuple(args.required_fields or ()),
        ),
    }
    require_graph_or_workspace(args)
    workspace_options = {
        "exclude_graphs": tuple(args.exclude_graphs or ()),
        "diversity": args.diversity,
        "max_per_graph": args.max_per_graph,
        "collapse_duplicates": args.collapse_duplicates,
    }
    if not args.workspace and (
        args.exclude_graphs or args.diversity != "none" or args.max_per_graph is not None
        or args.collapse_duplicates
    ):
        raise SearchFailure(
            "invalid_search_option",
            "--exclude, --diversity, --max-per-graph and --collapse-duplicates "
            "compare graphs and need --workspace.",
            hint="Search with --workspace NAME, or drop these options.",
            retryable=True,
        )
    if args.workspace:
        results = search_workspace_use_case(
            args.workspace,
            args.query,
            systems=tuple(args.systems or ()),
            graphs=tuple(args.graphs or ()),
            areas=tuple(args.areas or ()),
            schemas=tuple(args.schemas or ()),
            zones=tuple(args.zones or ()),
            focuses=tuple(args.focuses or ()),
            scope_objects=tuple(args.scope_objects or ()),
            **workspace_options,
            **search_arguments,
        )
    else:
        results = search_graph_use_case(
            args.name,
            args.query,
            namespace=args.namespace,
            focuses=tuple(args.focuses or ()),
            scope_object_ids=graph_scope_object_ids(
                args.name, tuple(args.scope_objects or ())
            ),
            **search_arguments,
        )
    _render_search_results(results, output_format=args.format)
    return 0


def _add_search_filter_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--type", action="append", dest="object_types", choices=("table", "view"))
    parser.add_argument("--role", action="append", dest="roles")
    parser.add_argument("--has-field", action="append", dest="required_fields")


def _add_workspace_result_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--exclude", action="append", dest="exclude_graphs", metavar="GLOB",
        help="Leave out graphs whose name matches this glob (e.g. 'ddl-*'); repeatable.",
    )
    parser.add_argument(
        "--diversity", choices=("none", "per_graph"), default="none",
        help="per_graph: at most --max-per-graph hits per graph (default 3); counts the rest.",
    )
    parser.add_argument("--max-per-graph", type=int)
    parser.add_argument(
        "--collapse-duplicates", action="store_true",
        help="Fold hits with the same object and column names (any case or punctuation) "
        "into the best-ranked one, which lists them under duplicates.",
    )


def _render_search_results(results: SearchResults, *, output_format: str) -> None:
    if output_format == "json":
        print_json(results.to_dict())
        return
    print(f"Search: {results.query}")
    if results.workspace:
        print(f"Workspace: {results.workspace}")
        print(f"Scope hash: {results.scope_hash}")
        print(f"Graphs: {', '.join(results.graphs)}")
    else:
        print(f"Graph: {results.graph}")
    print(f"Mode: {results.mode}")
    print(f"Annotation states: {', '.join(sorted(results.annotation_states))}")
    print(f"Terms: {', '.join(results.terms)}")
    for warning in results.warnings:
        print(f"Scope warning: {warning}")
    if results.inventory:
        print(
            "Objects: "
            f"{results.inventory.objects_after_filters}/{results.inventory.objects_in_scope} "
            "after filters"
        )
    for hit in results.hits:
        graph = f"; graph={hit.source_graph}" if hit.source_graph else ""
        print(f"- {hit.label} [{hit.type}{graph}] score={hit.score}")
        origin = " / ".join(value for value in (hit.source_graph, hit.namespace) if value)
        if origin:
            print(f"  Origin: {origin}")
        if hit.description:
            print(f"  Meaning: {hit.description}")
        details = [
            value for value in (
                f"role={hit.role}" if hit.role else None,
                f"grain={hit.grain}" if hit.grain else None,
                f"annotation={hit.annotation_state}" if hit.annotation_state else None,
            ) if value
        ]
        if details:
            print(f"  Metadata: {', '.join(details)}")
        if hit.reference:
            print(f"  Reference: {hit.reference}")
        print(f"  Reasons: {', '.join(hit.reasons)}")
        if hit.family is not None:
            family = hit.family.to_dict()
            print(f"  Family: {family['usage']}; {family['member_count']} scoped members; "
                  "not an executable table. Use family members at the returned revision.")
        if hit.fields:
            fields = ", ".join(f"{field.label} ({field.score})" for field in hit.fields)
            print(f"  Fields: {fields}")
        if hit.duplicates:
            print(f"  Duplicates folded: {', '.join(hit.duplicates)}")
    if results.excluded_graphs:
        print(f"Excluded graphs: {', '.join(results.excluded_graphs)}")
    if results.omitted_by_diversity:
        omitted = ", ".join(f"{name}={count}" for name, count in results.omitted_by_diversity)
        print(f"Omitted by diversity: {omitted}")
