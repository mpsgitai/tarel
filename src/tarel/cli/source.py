"""`tarel source`: named logical sources with explicit read permissions."""

from __future__ import annotations

import argparse
import json
import sys

from tarel.cli._args import Subcommands, add_format_argument, add_refresh_annotation_arguments
from tarel.cli._output import print_json, render_catalog, render_graph_summary, render_probe
from tarel.sources.application import (
    SourceCheck,
    SourceEnrichmentResult,
    build_source_graph_use_case,
    check_source_use_case,
    configure_source_use_case,
    discover_source_use_case,
    enrich_source_use_case,
    list_sources_use_case,
    load_source_use_case,
    probe_source_use_case,
    refresh_source_graph_use_case,
)
from tarel.sources.contracts import SourceProfile


def register(subcommands: Subcommands) -> None:
    """Add the `source` command group to the top-level parser."""
    source = subcommands.add_parser(
        "source",
        help="Manage private logical sources and their connector-backed graphs.",
    )
    source_commands = source.add_subparsers(dest="source_command")
    source_configure = source_commands.add_parser(
        "configure",
        help="Create or explicitly replace a non-secret logical source profile.",
    )
    source_configure.add_argument("name")
    source_configure.add_argument("--connector", required=True)
    source_configure.add_argument(
        "--config-ref",
        dest="config_reference",
        help="env:VARIABLE or state:relative/path.toml; never a connection URL.",
    )
    source_configure.add_argument("--database")
    source_configure.add_argument("--namespace", "--schema", dest="namespace")
    source_configure.add_argument("--graph", action="append", dest="graphs")
    source_configure.add_argument(
        "--allow-aggregates",
        action="store_true",
        help="Permit bounded aggregate column profiles for this source.",
    )
    source_configure.add_argument(
        "--allow-small-domains",
        action="store_true",
        help="Permit complete small-domain counts; requires aggregate permission.",
    )
    source_configure.add_argument(
        "--allow-raw-samples",
        action="store_true",
        help="Permit ephemeral raw samples of at most ten rows per object.",
    )
    source_configure.add_argument(
        "--allow-entity-aliases",
        action="store_true",
        help="Permit protected complete identity inspection and durable key groups.",
    )
    source_configure.add_argument("--replace", action="store_true")
    add_format_argument(source_configure)

    source_list = source_commands.add_parser("list", help="List configured logical sources.")
    add_format_argument(source_list)

    source_show = source_commands.add_parser("show", help="Show one logical source profile.")
    source_show.add_argument("name")
    add_format_argument(source_show)

    source_check = source_commands.add_parser(
        "check",
        help="Check connector availability and whether the config reference resolves.",
    )
    source_check.add_argument("name")
    add_format_argument(source_check)

    source_probe = source_commands.add_parser(
        "probe",
        help="Resolve the private config reference and run a bounded read-only probe.",
    )
    source_probe.add_argument("name")
    source_probe.add_argument("--database")
    add_format_argument(source_probe)

    source_discover = source_commands.add_parser(
        "discover",
        help="Discover source metadata through the configured connector.",
    )
    source_discover.add_argument("name")
    source_discover.add_argument("--database")
    source_discover.add_argument("--namespace", "--schema", dest="namespace")
    add_format_argument(source_discover)

    source_build = source_commands.add_parser(
        "build",
        help="Build a graph and bind it to this logical source.",
    )
    source_build.add_argument("name")
    source_build.add_argument("graph_name")
    source_build.add_argument("--database")
    source_build.add_argument("--namespace", "--schema", dest="namespace")
    add_format_argument(source_build)

    source_refresh = source_commands.add_parser(
        "refresh",
        help="Refresh a bound graph through this logical source.",
    )
    source_refresh.add_argument("name")
    source_refresh.add_argument("graph_name")
    source_refresh.add_argument("--namespace", "--schema", dest="namespace")
    add_refresh_annotation_arguments(source_refresh)
    add_format_argument(source_refresh)

    source_enrich = source_commands.add_parser(
        "enrich",
        help="Profile every graph object under the source enrichment policy.",
    )
    source_enrich.add_argument("name")
    source_enrich.add_argument("graph_name")
    source_enrich.add_argument("--profile-row-limit", type=int, default=10_000)
    source_enrich.add_argument(
        "--sample-limit",
        type=int,
        default=10,
        help="Raw rows per object when allowed; maximum 10 (default: 10).",
    )
    source_enrich.add_argument(
        "--persist-join-candidates",
        action="store_true",
        help="Persist aggregate transformed-join evidence, never sample rows.",
    )
    add_format_argument(source_enrich)



def dispatch(args: argparse.Namespace) -> int | None:
    """Run a parsed `source` command; return ``None`` for other commands."""
    if args.command != "source":
        return None
    command = args.source_command
    handler = _HANDLERS.get(command)
    if handler is not None:
        return handler(args)
    return None


def _render_source(source: SourceProfile, *, output_format: str) -> None:
    payload = {**source.to_dict(), "revision": source.revision}
    if output_format == "json":
        print_json(payload)
        return
    print(f"Source: {source.name}")
    print(f"Connector: {source.connector}")
    print(f"Config reference: {source.config_reference or 'connector environment'}")
    print(f"Database: {source.database or 'connector default'}")
    print(f"Namespace: {source.namespace or 'all'}")
    print(f"Graphs: {', '.join(source.graphs) or 'none'}")
    print(
        "Enrichment permissions: "
        f"{', '.join(source.enrichment_permissions) or 'none'}"
    )
    print("Read only: yes")
    print(f"Revision: {source.revision}")


def _render_source_enrichment(
    result: SourceEnrichmentResult,
    *,
    output_format: str,
) -> None:
    if output_format == "json":
        print_json(result.to_dict(), ensure_ascii=False)
        return
    workfile = result.workfile
    print(f"Source: {workfile.source}")
    print(f"Graph: {workfile.graph}")
    print(f"Permissions: {', '.join(workfile.permissions)}")
    print(f"Objects: {len(workfile.objects)}")
    print(f"Complete: {'yes' if workfile.complete else 'no'}")
    for item in workfile.objects:
        print(f"- {item.label}")
        if item.profile is not None:
            print(
                f"  profile: {item.profile.rows_profiled} rows, "
                f"{len(item.profile.columns)} columns"
            )
            for column in item.profile.columns:
                if column.status != "profiled":
                    print(
                        f"    {column.name}: omitted "
                        f"({column.reason or 'unsupported'})"
                    )
                    continue
                print(
                    f"    {column.name}: distinct={column.distinct_count}, "
                    f"min={column.min_value!r}, max={column.max_value!r}"
                )
                if column.values:
                    values = ", ".join(
                        f"{value.value!r} ({value.count})" for value in column.values
                    )
                    print(f"      values: {values}")
        if item.sample is not None:
            print(f"  sample: {len(item.sample.rows)} rows")
            for row in item.sample.rows:
                print(f"    {json.dumps(row, ensure_ascii=False, sort_keys=True)}")
        for pattern in item.key_patterns:
            print(
                f"  pattern: {pattern.field} = {pattern.pattern} "
                f"(coverage {pattern.coverage:.1%})"
            )
        for failure in item.failures:
            print(f"  failure [{failure.operation}/{failure.code}]: {failure.message}")
    print(
        "Transformed join candidates: "
        f"{len(workfile.transformed_join_candidates)}"
    )
    print(f"Persisted candidates: {len(result.persisted_candidates)}")


def _render_source_check(result: SourceCheck, *, output_format: str) -> None:
    if output_format == "json":
        print_json(result.to_dict())
        return
    print(f"Source: {result.source.name}")
    print(f"Connector: {result.connector.name}")
    print(f"Connector available: {'yes' if result.connector.available else 'no'}")
    print(f"Config status: {result.config_status}")
    print(f"Available: {'yes' if result.available else 'no'}")


def _run_configure(args: argparse.Namespace) -> int:
    result = configure_source_use_case(
        args.name,
        connector=args.connector,
        config_reference=args.config_reference,
        database=args.database,
        namespace=args.namespace,
        graphs=tuple(args.graphs or ()),
        enrichment_permissions=tuple(
            permission
            for permission, allowed in (
                ("aggregates", args.allow_aggregates),
                ("small_domains", args.allow_small_domains),
                ("raw_samples", args.allow_raw_samples),
                ("entity_aliases", args.allow_entity_aliases),
            )
            if allowed
        ),
        replace=args.replace,
    )
    _render_source(result.source, output_format=args.format)
    return 0


def _run_list(args: argparse.Namespace) -> int:
    names = list_sources_use_case()
    if args.format == "json":
        print_json({"sources": list(names)})
    else:
        for name in names:
            print(name)
    return 0


def _run_show(args: argparse.Namespace) -> int:
    _render_source(load_source_use_case(args.name), output_format=args.format)
    return 0


def _run_check(args: argparse.Namespace) -> int:
    result = check_source_use_case(args.name)
    _render_source_check(result, output_format=args.format)
    return 0 if result.available else 1


def _run_probe(args: argparse.Namespace) -> int:
    result = probe_source_use_case(args.name, database=args.database)
    render_probe(result, output_format=args.format)
    return 0


def _run_discover(args: argparse.Namespace) -> int:
    result = discover_source_use_case(
        args.name,
        database=args.database,
        namespace=args.namespace,
    )
    render_catalog(result, output_format=args.format)
    return 0


def _run_build(args: argparse.Namespace) -> int:
    result = build_source_graph_use_case(
        args.name,
        args.graph_name,
        database=args.database,
        namespace=args.namespace,
    )
    render_graph_summary(result.graph, output_format=args.format, path=result.path)
    return 0


def _run_refresh(args: argparse.Namespace) -> int:
    result = refresh_source_graph_use_case(
        args.name,
        args.graph_name,
        namespace=args.namespace,
        annotate_new_provider=args.annotate_new,
        annotation_workers=args.annotation_workers,
        annotation_model=args.annotation_model,
        annotation_timeout=args.annotation_timeout,
    )
    if args.format == "json":
        print_json({
                    "graph": result.graph.to_dict(),
                    "path": str(result.path),
                    "refresh": result.report.to_dict(),
                    "annotation": (
                        result.annotation_run.to_dict()
                        if result.annotation_run is not None
                        else None
                    ),
                    "status": result.status,
                })
    else:
        render_graph_summary(result.graph, output_format="text", path=result.path)
        print(f"Status: {result.status}")
        print(f"Changes: {len(result.report.changes)}")
        if result.annotation_run is not None:
            print(
                "Delta annotations: "
                f"{result.annotation_run.annotated}/{result.annotation_run.planned}"
            )
    return 0


def _run_enrich(args: argparse.Namespace) -> int:
    result = enrich_source_use_case(
        args.name,
        args.graph_name,
        profile_row_limit=args.profile_row_limit,
        sample_limit=args.sample_limit,
        persist_join_candidates=args.persist_join_candidates,
    )
    _render_source_enrichment(result, output_format=args.format)
    if result.workfile.samples_present:
        print(
            "note: raw sample rows were emitted only in this output "
            "and were not persisted.",
            file=sys.stderr,
        )
    return 0 if result.workfile.complete else 1


_HANDLERS = {
    "configure": _run_configure,
    "list": _run_list,
    "show": _run_show,
    "check": _run_check,
    "probe": _run_probe,
    "discover": _run_discover,
    "build": _run_build,
    "refresh": _run_refresh,
    "enrich": _run_enrich,
}
