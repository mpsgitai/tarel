"""`tarel lineage find|upstream|trace|downstream|batch`: read lineage across documents.

Every command here chooses its sources the same way (see
:mod:`tarel.lineage.trace_application`): explicit ``--lineage``/``--graph``/``--source`` win,
``--workspace`` adds its graphs, and with no lineage named all local lineage documents are read
plus the graphs their qualified references name. ``--no-auto-catalog`` turns that last step off.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from tarel.cli._args import Subcommands, add_format_argument, add_view_argument
from tarel.cli._output import print_json, render_compact
from tarel.cli._pretty_lineage import render_batch, render_lineage
from tarel.graph.reads import graph_freshness_use_case
from tarel.lineage.application import find_lineage_references_use_case, trace_upstream_use_case
from tarel.lineage.directions import DIRECTIONS
from tarel.lineage.projection import compact_batch_dict, graph_names, trace_references
from tarel.lineage.trace_application import (
    ResolvedLineageSources,
    resolve_lineage_sources_use_case,
    trace_lineage_batch_use_case,
    trace_lineage_use_case,
)

_STATES = ("draft", "review_required", "validated")


def register(commands: Subcommands) -> None:
    """Add the lineage read commands to `tarel lineage`."""
    find = commands.add_parser(
        "find",
        help="Find report, semantic, procedure, table, or field references.",
    )
    find.add_argument("query")
    _add_source_arguments(find)
    find.add_argument("--limit", type=int, default=20)
    find.add_argument(
        "--mode",
        choices=("lexical", "bm25", "vector", "hybrid"),
        default="lexical",
    )
    find.add_argument("--model", type=Path, dest="model_path")
    find.add_argument("--threads", type=int, dest="n_threads")
    add_format_argument(find)

    upstream = commands.add_parser(
        "upstream",
        help="Trace one reference backwards through all selected lineage documents.",
    )
    upstream.add_argument("reference")
    _add_trace_arguments(upstream)
    add_view_argument(upstream)
    add_format_argument(upstream, pretty=True)

    trace = commands.add_parser(
        "trace",
        help="Trace one reference upstream, downstream (impact) or both; compact by default.",
    )
    trace.add_argument("reference")
    trace.add_argument("--direction", choices=DIRECTIONS, default="up")
    _add_trace_arguments(trace)
    _add_compact_view_argument(trace)
    add_format_argument(trace, pretty=True)

    downstream = commands.add_parser(
        "downstream",
        help="Shortcut for `lineage trace REF --direction down`: what this reference feeds.",
    )
    downstream.add_argument("reference")
    _add_trace_arguments(downstream)
    _add_compact_view_argument(downstream)
    add_format_argument(downstream, pretty=True)

    batch = commands.add_parser(
        "batch",
        help="Trace many references over one loaded network; one chain line per reference.",
    )
    batch.add_argument("references", nargs="+", metavar="REFERENCE")
    batch.add_argument("--direction", choices=DIRECTIONS, default="up")
    _add_trace_arguments(batch)
    add_format_argument(batch, pretty=True)


def dispatch(args: argparse.Namespace) -> int | None:
    """Run a parsed lineage read command; return ``None`` for other commands."""
    handler = _HANDLERS.get(args.lineage_command)
    return handler(args) if handler is not None else None


def _add_source_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--lineage", action="append", dest="lineages",
        help="Lineage document to read; repeatable. Default: all local lineage documents.",
    )
    parser.add_argument(
        "--graph", action="append", dest="graphs",
        help="Catalog graph to resolve references against; repeatable.",
    )
    parser.add_argument(
        "--source", action="append", dest="sources",
        help="A lineage or graph name, classified automatically; force with lineage:/graph:.",
    )
    parser.add_argument("--workspace", help="Add every graph of this workspace.")
    parser.add_argument(
        "--no-auto-catalog", action="store_false", dest="auto_catalog",
        help="Without --lineage/--graph, do not add the graphs the lineage documents name.",
    )


def _add_trace_arguments(parser: argparse.ArgumentParser) -> None:
    _add_source_arguments(parser)
    parser.add_argument("--max-hops", type=int, default=12)
    parser.add_argument("--state", action="append", choices=_STATES)


def _add_compact_view_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--view", choices=("compact", "full"), default="compact",
        help="compact (default): nodes once, short edge rows. full: complete JSON record.",
    )


def _resolve(args: argparse.Namespace) -> ResolvedLineageSources:
    return resolve_lineage_sources_use_case(
        sources=tuple(args.sources or ()),
        lineage_names=tuple(args.lineages or ()),
        graph_names=tuple(args.graphs or ()),
        workspace=args.workspace,
        auto_catalog=args.auto_catalog,
    )


def _auto_resolution(sources: ResolvedLineageSources) -> dict[str, object] | None:
    """Echo the sources only when TAREL chose them; an explicit caller already knows."""
    return sources.to_dict() if sources.auto else None


def _render_trace(payload: dict[str, object], *, output_format: str) -> None:
    if output_format == "pretty":
        render_lineage(payload)
    else:
        render_compact(payload, output_format=output_format)


def _states(args: argparse.Namespace) -> frozenset[str] | None:
    return frozenset(args.state) if args.state else None


def _run_find(args: argparse.Namespace) -> int:
    sources = _resolve(args)
    references = find_lineage_references_use_case(
        args.query,
        lineage_names=sources.lineage_names,
        graph_names=sources.graph_names,
        limit=args.limit,
        mode=args.mode,
        model_path=args.model_path,
        n_threads=args.n_threads,
    )
    payload: dict[str, Any] = {
        "mode": args.mode,
        "query": args.query,
        "references": [item.to_dict() for item in references],
    }
    if sources.auto:
        payload["resolution"] = sources.to_dict()
    _render_lineage_find(payload, output_format=args.format)
    return 0


def _run_upstream(args: argparse.Namespace) -> int:
    sources = _resolve(args)
    trace = trace_upstream_use_case(
        args.reference,
        lineage_names=sources.lineage_names,
        graph_names=sources.graph_names,
        max_hops=args.max_hops,
        states=_states(args),
    )
    if args.view == "compact" or args.format == "pretty":
        _render_trace(
            trace.to_compact_dict(
                resolution=_auto_resolution(sources),
                freshness=graph_freshness_use_case(
                    graph_names(trace_references(trace.start, trace.hops))
                ),
            ),
            output_format=args.format,
        )
        return 0
    payload = trace.to_dict()
    if sources.auto:
        payload["resolution"] = sources.to_dict()
    _render_upstream_trace(payload, output_format=args.format)
    return 0


def _run_trace(args: argparse.Namespace, *, direction: str | None = None) -> int:
    sources = _resolve(args)
    trace = trace_lineage_use_case(
        args.reference,
        lineage_names=sources.lineage_names,
        graph_names=sources.graph_names,
        direction=direction or args.direction,
        max_hops=args.max_hops,
        states=_states(args),
    )
    if args.view == "full" and args.format == "json":
        print_json({**trace.to_dict(), "resolution": sources.to_dict()})
        return 0
    _render_trace(
        trace.to_compact_dict(
            resolution=_auto_resolution(sources),
            freshness=graph_freshness_use_case(
                graph_names(trace_references(trace.start, (*trace.upstream, *trace.downstream)))
            ),
        ),
        output_format=args.format,
    )
    return 0


def _run_downstream(args: argparse.Namespace) -> int:
    return _run_trace(args, direction="down")


def _run_batch(args: argparse.Namespace) -> int:
    sources = _resolve(args)
    batch = trace_lineage_batch_use_case(
        tuple(args.references),
        lineage_names=sources.lineage_names,
        graph_names=sources.graph_names,
        direction=args.direction,
        max_hops=args.max_hops,
        states=_states(args),
    )
    payload = compact_batch_dict(
        batch,
        resolution=_auto_resolution(sources),
        freshness=graph_freshness_use_case(
            graph_names(
                node
                for trace in batch.traces
                for node in trace_references(trace.start, (*trace.upstream, *trace.downstream))
            )
        ),
    )
    if args.format == "json":
        render_compact(payload, output_format="json")
        return 0
    if args.format == "pretty":
        render_batch(payload)
        return 0
    chains = payload.get("chains")
    for reference, chain in (chains.items() if isinstance(chains, dict) else ()):
        print(f"{reference}: {chain}")
    errors = payload.get("errors")
    for reference, error in (errors.items() if isinstance(errors, dict) else ()):
        print(f"{reference}: error [{error['code']}] {error['message']}")
    print(f"summary: {payload['summary']}")
    return 0


def _render_lineage_find(payload: dict[str, Any], *, output_format: str) -> None:
    if output_format == "json":
        print_json(payload)
        return
    references = payload.get("references")
    if not isinstance(references, list):
        return
    print(f"Mode: {payload.get('mode', 'lexical')}")
    for item in references:
        if isinstance(item, dict):
            print(f"- {_reference_label(item)} [{item['kind']}; {item['source']}]")


def _reference_label(item: dict[str, Any]) -> str:
    """An unresolved name's ``name`` says which scope it belongs to; its reference cannot."""
    return str(item["name"] if item.get("kind") == "unresolved" else item["reference"])


def _render_upstream_trace(payload: dict[str, Any], *, output_format: str) -> None:
    if output_format == "json":
        print_json(payload)
        return
    start = payload.get("start")
    if isinstance(start, dict):
        print(f"Start: {_reference_label(start)} [{start['kind']}]")
    hops = payload.get("hops")
    if isinstance(hops, list):
        for hop in hops:
            if not isinstance(hop, dict):
                continue
            target = hop.get("target")
            if not isinstance(target, dict):
                continue
            indent = "  " * max(int(hop.get("depth", 1)) - 1, 0)
            detail = f" via {hop['via_definition']}" if hop.get("via_definition") else ""
            role = f"; role={hop['role']}" if hop.get("role") else ""
            granularity = (
                f"; granularity={hop['granularity_change']}"
                if hop.get("granularity_change")
                else ""
            )
            source = hop.get("source")
            if not isinstance(source, dict):
                continue
            print(
                f"{indent}<- {_reference_label(source)} "
                f"({hop['relation']}{detail}; {hop['state']}{role}{granularity})"
            )
            evidence = hop.get("evidence")
            if isinstance(evidence, dict) and evidence.get("reason"):
                print(f"{indent}   evidence: {evidence['reason']}")
            write_evidence = hop.get("write_evidence")
            if isinstance(write_evidence, dict) and write_evidence.get("reason"):
                print(f"{indent}   write evidence: {write_evidence['reason']}")
            description = source.get("description")
            description_kind = source.get("description_kind")
            annotation_state = source.get("annotation_state")
            if description:
                state = f" [{annotation_state}]" if annotation_state else ""
                label = {
                    "analysis_summary": "analysis",
                    "semantic_annotation": "semantic",
                    "technical_metadata": "technical",
                }.get(str(description_kind), "description")
                print(f"{indent}   {label}: {description}{state}")
            reviews = hop.get("reviews")
            if isinstance(reviews, list) and reviews:
                review = reviews[-1]
                if isinstance(review, dict):
                    print(
                        f"{indent}   review: {review['decision']} by "
                        f"{review['source']} - {review['reason']}"
                    )
    origins = payload.get("origins")
    if isinstance(origins, list) and origins:
        print(f"Origin view: {len(origins)} unique origins")
        for origin in origins:
            if isinstance(origin, dict):
                print(f"- {_reference_label(origin)} [{origin['kind']}]")
                roles, procedures = _origin_lineage_details(origin, hops)
                if roles:
                    print(f"  roles: {', '.join(roles)}")
                if procedures:
                    print(f"  procedures: {', '.join(procedures)}")
    warnings = payload.get("warnings")
    if isinstance(warnings, list):
        for warning in warnings:
            print(f"warning: {warning}")


def _origin_lineage_details(
    origin: dict[str, object],
    hops: object,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not isinstance(hops, list) or not isinstance(origin.get("id"), str):
        return (), ()
    downstream: dict[str, list[dict[str, object]]] = {}
    for hop in hops:
        if not isinstance(hop, dict):
            continue
        source = hop.get("source")
        if not isinstance(source, dict) or not isinstance(source.get("id"), str):
            continue
        downstream.setdefault(source["id"], []).append(hop)

    queue = [str(origin["id"])]
    seen = set(queue)
    roles: set[str] = set()
    procedures: set[str] = set()
    while queue:
        source_id = queue.pop(0)
        for hop in downstream.get(source_id, []):
            role = hop.get("role")
            if source_id == origin["id"] and isinstance(role, str) and role:
                roles.add(role)
            procedure = hop.get("via_definition")
            if isinstance(procedure, str) and procedure:
                procedures.add(procedure)
            target = hop.get("target")
            if not isinstance(target, dict):
                continue
            target_id = target.get("id")
            if isinstance(target_id, str) and target_id not in seen:
                seen.add(target_id)
                queue.append(target_id)
    return tuple(sorted(roles)), tuple(sorted(procedures))


_HANDLERS = {
    "batch": _run_batch,
    "downstream": _run_downstream,
    "find": _run_find,
    "trace": _run_trace,
    "upstream": _run_upstream,
}
