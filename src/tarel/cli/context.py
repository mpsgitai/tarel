"""`tarel context`: compile, compare and describe context packets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from tarel.cli import context_expand
from tarel.cli._args import (
    Subcommands,
    add_annotation_state_arguments,
    add_format_argument,
    add_logical_hint_arguments,
    add_workspace_retrieval_scope_arguments,
    graph_scope_object_ids,
    require_graph_or_workspace,
)
from tarel.cli._output import print_json
from tarel.cli._pretty_catalog import render_context
from tarel.context.application import (
    compile_context_prefix_use_case,
    compile_context_use_case,
    compile_workspace_context_prefix_use_case,
    compile_workspace_context_use_case,
    context_packet_brief_use_case,
    context_packet_diff_views_use_case,
    context_packet_impact_use_case,
    describe_context_use_case,
)
from tarel.context.compiler import DEFAULT_MAX_CONTEXT_CHARACTERS, ContextResult
from tarel.context.guidance import ContextBrief, ContextDelta
from tarel.context.output import canonical_json


def register(subcommands: Subcommands) -> None:
    """Add the `context` command group to the top-level parser."""
    context = subcommands.add_parser(
        "context",
        help="Build and compare deterministic context packets.",
    )
    context_commands = context.add_subparsers(dest="context_command")
    context_expand.register(context_commands)
    context_build = context_commands.add_parser(
        "build",
        help="Compile bounded context from search and reviewed graph relationships.",
    )
    context_build.add_argument(
        "name",
        nargs="?",
        help="Graph name; omit it with --workspace NAME.",
    )
    context_build.add_argument("query", help="Analytical question or compact search query.")
    context_build.add_argument("--namespace", "--schema", dest="namespace")
    context_build.add_argument("--seed-limit", type=int, default=3)
    context_build.add_argument("--max-objects", type=int, default=10)
    context_build.add_argument("--max-joins", type=int, default=12)
    context_build.add_argument("--max-hops", type=int, default=2)
    context_build.add_argument("--max-fields-per-object", type=int, default=12)
    context_build.add_argument(
        "--max-characters",
        type=int,
        default=DEFAULT_MAX_CONTEXT_CHARACTERS,
        help="Maximum canonical characters in the complete context payload.",
    )
    context_build.add_argument(
        "--mode",
        choices=("lexical", "bm25", "vector", "hybrid"),
        default="lexical",
    )
    context_build.add_argument("--model", type=Path, dest="model_path")
    context_build.add_argument("--threads", type=int, dest="n_threads")
    context_build.add_argument(
        "--bm25-weight", type=float, help="Hybrid BM25 weight; default 1.0."
    )
    add_workspace_retrieval_scope_arguments(context_build)
    context_build.add_argument(
        "--object", action="append", dest="object_ids",
        help="Use an exact OBJECT_ID, or GRAPH:OBJECT_ID with --workspace; repeat as needed.",
    )
    add_annotation_state_arguments(context_build)
    add_logical_hint_arguments(context_build)
    context_build.add_argument(
        "--brief", action="store_true",
        help="Print only compact orientation, coverage, gaps, and continuity identity.",
    )
    add_format_argument(context_build, pretty=True)

    context_prefix = context_commands.add_parser(
        "prefix",
        help="Compile a query-independent graph or workspace scope for prompt caching.",
    )
    context_prefix.add_argument(
        "name",
        nargs="?",
        help="Graph name; omit it with --workspace NAME.",
    )
    context_prefix.add_argument("--namespace", "--schema", dest="namespace")
    context_prefix.add_argument("--max-objects", type=int, default=250)
    context_prefix.add_argument("--max-joins", type=int, default=500)
    context_prefix.add_argument("--max-fields-per-object", type=int, default=50)
    context_prefix.add_argument("--max-characters", type=int, default=500_000)
    add_workspace_retrieval_scope_arguments(context_prefix)
    add_annotation_state_arguments(context_prefix)
    add_logical_hint_arguments(context_prefix)
    context_prefix.add_argument(
        "--brief", action="store_true",
        help="Print only compact orientation, coverage, gaps, and continuity identity.",
    )
    add_format_argument(context_prefix)

    context_brief = context_commands.add_parser(
        "brief",
        help="Summarize one saved context packet for a continuing conversation.",
    )
    context_brief.add_argument("packet", type=Path)
    add_format_argument(context_brief)

    context_diff = context_commands.add_parser(
        "diff",
        help="Validate and compare two serialized context packets.",
    )
    context_diff.add_argument("left", type=Path)
    context_diff.add_argument("right", type=Path)
    add_format_argument(context_diff)

    context_impact = context_commands.add_parser(
        "impact",
        help="Check whether one saved context packet is affected by the latest graph refresh.",
    )
    context_impact.add_argument("packet", type=Path)
    context_impact.add_argument("--graph", required=True, help="Current local graph name.")
    add_format_argument(context_impact)



def dispatch(args: argparse.Namespace) -> int | None:
    """Run a parsed `context` command; return ``None`` for other commands."""
    result = context_expand.dispatch(args)
    if result is not None:
        return result
    if args.command != "context":
        return None
    command = args.context_command
    handler = _HANDLERS.get(command)
    if handler is not None:
        return handler(args)
    return None


def _render_context(
    result: ContextResult, *, output_format: str, brief_only: bool = False,
) -> None:
    if output_format == "pretty":
        render_context(result, describe_context_use_case(result))
        return
    if brief_only:
        _render_context_brief(describe_context_use_case(result), output_format=output_format)
        return
    if output_format == "json":
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return
    print("# TAREL Context")
    print(f"Contract: {result.contract_version}")
    print(f"Graph: {result.graph}")
    print(f"Revision: {result.graph_revision}")
    print(f"Stable hash: {result.stable_hash}")
    print(f"Scope: {result.scope.mode}; namespace={result.scope.namespace or '*'}")
    if result.scope.workspace:
        print(f"Workspace: {result.scope.workspace}")
        print(f"Scope hash: {result.scope.scope_hash}")
        print(f"Graphs: {', '.join(result.scope.graphs)}")
    for warning in result.scope.warnings:
        print(f"Scope warning: {warning}")
    print(f"Annotation states: {', '.join(sorted(result.annotation_states))}")

    print("\n## Stable objects")
    for item in sorted(result.objects, key=lambda candidate: candidate.id):
        state = f"; annotation={item.annotation_state}" if item.annotation_state else ""
        print(f"\n### {item.label} [{item.type}{state}]")
        if item.description:
            print(item.description)
        if item.role:
            print(f"Role: {item.role}")
        if item.tags:
            print(f"Tags: {', '.join(item.tags)}")
        if item.grain:
            print(f"Grain: {item.grain}")
        for warning in item.warnings:
            print(f"Warning: {warning}")
        for field in sorted(item.fields, key=lambda candidate: candidate.id):
            nullable = " nullable" if field.nullable else ""
            details = [value for value in (field.role, field.semantic_type) if value]
            detail = f" [{', '.join(details)}]" if details else ""
            print(f"- {field.name}: {field.data_type}{nullable}{detail}")
            if field.description:
                print(f"  {field.description}")
            if field.tags:
                print(f"  Tags: {', '.join(field.tags)}")

    print("\n## Stable joins")
    for join in sorted(result.joins, key=lambda candidate: candidate.id):
        print(
            f"- {join.from_object}({', '.join(join.from_fields)}) -> "
            f"{join.to_object}({', '.join(join.to_fields)}) "
            f"[{join.kind}; {join.state}]"
        )

    if result.logical_hints is not None:
        print("\n## Stable logical hints")
        print(canonical_json(result.logical_hints.stable_dict()))

    print("\n## Dynamic request")
    print(f"Dynamic hash: {result.dynamic_hash}")
    print(f"Packet hash: {result.packet_hash}")
    print(
        "Question: <none; query-independent prefix>"
        if result.retrieval_mode == "scope"
        else f"Question: {result.query}"
    )
    print(f"Retrieval: {result.retrieval_mode}")
    for warning in result.retrieval_warnings:
        print(f"Retrieval warning: {warning}")
    print(f"Terms: {', '.join(result.terms)}")
    print(
        f"Context characters: {result.context_characters}/{result.max_characters}; "
        f"stable={result.stable_characters}; "
        f"objects={len(result.objects)}/{result.max_objects}; "
        f"joins={len(result.joins)}/{result.max_joins}"
    )
    print("Selection:")
    for item in result.objects:
        score = f", score={item.search_score}" if item.search_score is not None else ""
        print(
            f"- {item.label}: {item.selection}, distance={item.distance}{score}, "
            f"omitted_fields={item.omitted_fields}"
        )
        for field in item.fields:
            print(f"  - {field.name}: {', '.join(field.reasons)}")
    omission_reasons = ", ".join(result.omissions.reasons) or "none"
    print(
        "Omissions: "
        f"objects={result.omissions.objects}, fields={result.omissions.fields}, "
        f"joins={result.omissions.joins}, paths={result.omissions.paths}; "
        f"reasons={omission_reasons}"
    )
    if result.logical_hints is not None:
        print("Logical hint omissions and warnings:")
        print(canonical_json(result.logical_hints.dynamic_dict()))
    if result.paths:
        print("Expansion paths:")
        for path in result.paths:
            print(f"- {' -> '.join(path.objects)}")


def _render_context_brief(result: ContextBrief, *, output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return
    print(result.text())
    for gap in result.gaps[:3]:
        print(f"- [{gap.category}] {gap.message} Next: {gap.action}")
    if len(result.gaps) > 3:
        print(f"- +{len(result.gaps) - 3} more gap types; use --format json for every action.")


def _render_context_diff(
    payload: dict[str, object], *, guidance: ContextDelta, output_format: str,
) -> None:
    if output_format == "json":
        print_json({**payload, "guidance": guidance.to_dict()})
        return
    print("# Context update")
    print(guidance.text())
    print("\n## Packet identity")
    print(f"Identical: {'yes' if payload['identical'] else 'no'}")
    print(f"Stable changed: {'yes' if payload['stable_changed'] else 'no'}")
    if "logical_hints_changed" in payload:
        print(f"Logical hints changed: {'yes' if payload['logical_hints_changed'] else 'no'}")
    print(f"Dynamic changed: {'yes' if payload['dynamic_changed'] else 'no'}")
    print(f"Graph revision changed: {'yes' if payload['graph_revision_changed'] else 'no'}")
    print(f"Scope changed: {'yes' if payload['scope_changed'] else 'no'}")
    print(f"Query changed: {'yes' if payload['query_changed'] else 'no'}")
    for section in ("objects", "joins"):
        changes = payload[section]
        if isinstance(changes, dict):
            for change in ("added", "removed", "changed"):
                values = changes.get(change, [])
                rendered = ", ".join(values) if isinstance(values, list) else ""
                print(f"{section.capitalize()} {change}: {rendered or '-'}")


def _render_context_impact(payload: dict[str, Any], *, output_format: str) -> None:
    if output_format == "json":
        print_json(payload)
        return
    print(f"Status: {payload['status']}")
    print(f"Affected: {payload['affected'] if payload['affected'] is not None else 'unknown'}")
    print(f"Exact: {'yes' if payload['exact'] else 'no'}")
    print(f"Reason: {payload['reason']}")
    changes = payload.get("matched_changes")
    if isinstance(changes, list):
        for change in changes:
            if isinstance(change, dict):
                print(f"- {change.get('kind')}: {change.get('reference')}")


def _run_build(args: argparse.Namespace) -> int:
    context_arguments = {
        "logical_hints": args.logical_hints,
        "seed_limit": args.seed_limit,
        "max_objects": args.max_objects,
        "max_joins": args.max_joins,
        "max_hops": args.max_hops,
        "max_fields_per_object": args.max_fields_per_object,
        "max_characters": args.max_characters,
        "mode": args.mode,
        "model_path": args.model_path,
        "n_threads": args.n_threads,
        "bm25_weight": args.bm25_weight,
        "annotation_states": (
            frozenset(args.annotation_states) if args.annotation_states else None
        ),
        "validated_only": args.validated_only,
        "object_ids": tuple(args.object_ids or ()),
    }
    require_graph_or_workspace(args)
    if args.workspace:
        result = compile_workspace_context_use_case(
            args.workspace,
            args.query,
            systems=tuple(args.systems or ()),
            graphs=tuple(args.graphs or ()),
            areas=tuple(args.areas or ()),
            schemas=tuple(args.schemas or ()),
            zones=tuple(args.zones or ()),
            focuses=tuple(args.focuses or ()),
            scope_objects=tuple(args.scope_objects or ()),
            **context_arguments,
        )
    else:
        result = compile_context_use_case(
            args.name,
            args.query,
            namespace=args.namespace,
            focuses=tuple(args.focuses or ()),
            scope_object_ids=graph_scope_object_ids(
                args.name, tuple(args.scope_objects or ())
            ),
            **context_arguments,
        )
    _render_context(result, output_format=args.format, brief_only=args.brief)
    return 0


def _run_prefix(args: argparse.Namespace) -> int:
    prefix_arguments = {
        "logical_hints": args.logical_hints,
        "max_objects": args.max_objects,
        "max_joins": args.max_joins,
        "max_fields_per_object": args.max_fields_per_object,
        "max_characters": args.max_characters,
        "annotation_states": (
            frozenset(args.annotation_states) if args.annotation_states else None
        ),
        "validated_only": args.validated_only,
    }
    require_graph_or_workspace(args)
    if args.workspace:
        result = compile_workspace_context_prefix_use_case(
            args.workspace,
            systems=tuple(args.systems or ()),
            graphs=tuple(args.graphs or ()),
            areas=tuple(args.areas or ()),
            schemas=tuple(args.schemas or ()),
            zones=tuple(args.zones or ()),
            focuses=tuple(args.focuses or ()),
            scope_objects=tuple(args.scope_objects or ()),
            **prefix_arguments,
        )
    else:
        result = compile_context_prefix_use_case(
            args.name,
            namespace=args.namespace,
            focuses=tuple(args.focuses or ()),
            scope_object_ids=graph_scope_object_ids(
                args.name, tuple(args.scope_objects or ())
            ),
            **prefix_arguments,
        )
    _render_context(result, output_format=args.format, brief_only=args.brief)
    return 0


def _run_brief(args: argparse.Namespace) -> int:
    result = context_packet_brief_use_case(args.packet)
    _render_context_brief(result, output_format=args.format)
    return 0


def _run_diff(args: argparse.Namespace) -> int:
    result, guidance = context_packet_diff_views_use_case(args.left, args.right)
    _render_context_diff(
        result.to_dict(), guidance=guidance, output_format=args.format,
    )
    return 0


def _run_impact(args: argparse.Namespace) -> int:
    result = context_packet_impact_use_case(args.packet, args.graph)
    _render_context_impact(result.to_dict(), output_format=args.format)
    return 0 if result.status != "unknown" else 1


_HANDLERS = {
    "build": _run_build,
    "prefix": _run_prefix,
    "brief": _run_brief,
    "diff": _run_diff,
    "impact": _run_impact,
}
