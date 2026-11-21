"""`tarel graph`: build, refresh, inspect and annotate TAREL graphs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tarel.annotations.application import plan_annotations_use_case, run_annotation_batch_use_case
from tarel.cli import graph_reads
from tarel.cli._args import (
    Subcommands,
    add_annotation_knowledge_arguments,
    add_format_argument,
    add_refresh_annotation_arguments,
)
from tarel.cli._output import print_json, render_annotation_plan, render_graph_summary
from tarel.connectors.catalog import load_catalog_result
from tarel.graph.application import (
    build_graph_use_case,
    import_catalog_use_case,
    list_graphs_use_case,
    load_graph_use_case,
    refresh_graph_use_case,
)


def register(subcommands: Subcommands) -> None:
    """Add the `graph` command group to the top-level parser."""
    graph = subcommands.add_parser("graph", help="Build and inspect local TAREL graphs.")
    graph_commands = graph.add_subparsers(dest="graph_command")
    graph_reads.register(graph_commands)

    graph_build = graph_commands.add_parser(
        "build",
        help="Discover a source and persist its technical graph.",
    )
    graph_build.add_argument("name", help="Local graph name.")
    graph_build.add_argument("--connector", required=True, help="Source connector name.")
    graph_build.add_argument("--config", type=Path, help="Private connector configuration.")
    graph_build.add_argument("--database", help="Override the configured database.")
    graph_build.add_argument("--namespace", "--schema", dest="namespace")
    add_format_argument(graph_build)

    graph_refresh = graph_commands.add_parser(
        "refresh",
        help="Rediscover technical structure while preserving reviewed knowledge.",
    )
    graph_refresh.add_argument("name", help="Existing local graph name.")
    graph_refresh.add_argument("--config", type=Path, help="Private connector configuration.")
    graph_refresh.add_argument("--namespace", "--schema", dest="namespace")
    add_refresh_annotation_arguments(graph_refresh)
    add_format_argument(graph_refresh)

    graph_import = graph_commands.add_parser(
        "import-catalog",
        help="Persist an already observed catalog without running discovery again.",
    )
    graph_import.add_argument("name", help="New local graph name.")
    graph_import.add_argument(
        "--source",
        type=Path,
        required=True,
        help="CatalogResult JSON produced by a trusted caller or connector discovery.",
    )
    add_format_argument(graph_import)

    graph_list = graph_commands.add_parser("list", help="List local graphs.")
    add_format_argument(graph_list)

    graph_show = graph_commands.add_parser("show", help="Show one local graph.")
    graph_show.add_argument("name")
    add_format_argument(graph_show)

    graph_annotate = graph_commands.add_parser(
        "annotate",
        help="Run provider-backed annotation tasks, optionally in parallel.",
    )
    graph_annotate.add_argument("name")
    graph_annotate.add_argument("--provider", required=True)
    graph_annotate.add_argument("--namespace", "--schema", dest="namespace")
    graph_annotate.add_argument("--object", action="append", dest="objects")
    graph_annotate.add_argument("--limit", type=int)
    graph_annotate.add_argument("--workers", type=int, default=1)
    graph_annotate.add_argument("--retry", type=int, default=0)
    graph_annotate.add_argument("--retry-backoff", type=float, default=2.0)
    graph_annotate.add_argument("--skip-errors", action="store_true")
    graph_annotate.add_argument("--max-errors", type=int)
    graph_annotate.add_argument("--model")
    graph_annotate.add_argument("--timeout", type=float, default=120.0)
    graph_annotate.add_argument("--samples", type=int, default=0)
    graph_annotate.add_argument("--profile-rows", type=int, default=0)
    graph_annotate.add_argument(
        "--include-small-domain-values",
        action="store_true",
        help="Explicitly allow small-domain values in ephemeral annotation input.",
    )
    graph_annotate.add_argument("--config", type=Path, help="Private connector configuration.")
    graph_annotate.add_argument(
        "--include-annotated",
        action="store_true",
        help="Re-annotate complete objects instead of filling only missing annotations.",
    )
    graph_annotate.add_argument("--dry-run", action="store_true")
    add_annotation_knowledge_arguments(graph_annotate)
    add_format_argument(graph_annotate)


def dispatch(args: argparse.Namespace) -> int | None:
    """Run a parsed `graph` command; return ``None`` for other commands."""
    result = graph_reads.dispatch(args)
    if result is not None:
        return result
    if args.command != "graph":
        return None
    command = args.graph_command
    handler = _HANDLERS.get(command)
    if handler is not None:
        return handler(args)
    return None


def _print_annotation_progress(index: int, total: int, target: str, status: str) -> None:
    print(f"[{index}/{total}] {status} {target}", file=sys.stderr)


def _run_build(args: argparse.Namespace) -> int:
    result = build_graph_use_case(
        args.name,
        connector_name=args.connector,
        config_path=args.config,
        database=args.database,
        namespace=args.namespace,
    )
    render_graph_summary(result.graph, output_format=args.format, path=result.path)
    return 0


def _run_import_catalog(args: argparse.Namespace) -> int:
    result = import_catalog_use_case(
        args.name,
        load_catalog_result(args.source),
    )
    render_graph_summary(result.graph, output_format=args.format, path=result.path)
    return 0


def _run_refresh(args: argparse.Namespace) -> int:
    result = refresh_graph_use_case(
        args.name,
        config_path=args.config,
        namespace=args.namespace,
        annotate_new_provider=args.annotate_new,
        annotation_workers=args.annotation_workers,
        annotation_model=args.annotation_model,
        annotation_timeout=args.annotation_timeout,
    )
    payload = {
        "annotation": (
            result.annotation_run.to_dict()
            if result.annotation_run is not None
            else None
        ),
        "change_report_path": (
            str(result.change_report_path) if result.change_report_path else None
        ),
        "graph": result.graph.name,
        "path": str(result.path),
        "refresh": result.report.to_dict(),
        "status": result.status,
        "workspace_impacts": [impact.to_dict() for impact in result.workspace_impacts],
    }
    if args.format == "json":
        print_json(payload)
    else:
        print(f"Refreshed graph: {result.graph.name} ({result.status})")
        print(f"Changes: {len(result.report.changes)}")
        if result.annotation_run is not None:
            print(
                "Delta annotations: "
                f"{result.annotation_run.annotated}/{result.annotation_run.planned}"
            )
        for change in result.report.changes:
            values = ""
            if change.before is not None or change.after is not None:
                values = f" ({change.before!r} -> {change.after!r})"
            print(f"- {change.kind}: {change.reference} [{change.severity}]{values}")
        print(
            "Review required: "
            f"annotations={result.report.review_required_annotations}, "
            f"relationships={result.report.review_required_relationships}"
        )
        print(f"Preserved stale claims: {len(result.report.stale_claims)}")
        for impact in result.workspace_impacts:
            print(
                f"Workspace impact: {impact.workspace}/{impact.system}; "
                f"areas={', '.join(impact.areas) or '-'}; "
                f"zones={', '.join(impact.zones) or '-'}"
            )
        print(f"Path: {result.path}")
        report_path = result.change_report_path or "not written (no revision change)"
        print(f"Change report: {report_path}")
    return 0


def _run_list(args: argparse.Namespace) -> int:
    names = list_graphs_use_case()
    if args.format == "json":
        print_json({"graphs": list(names)})
    else:
        for name in names:
            print(name)
    return 0


def _run_show(args: argparse.Namespace) -> int:
    graph_document = load_graph_use_case(args.name)
    if args.format == "json":
        print_json(graph_document.to_dict())
    else:
        render_graph_summary(graph_document, output_format="text")
    return 0


def _run_annotate(args: argparse.Namespace) -> int:
    objects = set(args.objects or [])
    if args.dry_run:
        tasks = plan_annotations_use_case(
            args.name,
            namespace=args.namespace,
            objects=objects,
            limit=args.limit,
            missing_only=not args.include_annotated,
            sample_limit=args.samples,
            profile_row_limit=args.profile_rows,
            include_small_domain_values=args.include_small_domain_values,
            config_path=args.config,
            knowledge_mode=args.knowledge,
            knowledge_document_ids=tuple(args.knowledge_documents or ()),
            knowledge_workspace=args.knowledge_workspace,
            max_knowledge_characters=args.max_knowledge_characters,
        )
        render_annotation_plan(tasks, output_format=args.format)
        return 0
    if args.samples:
        print(
            f"warning: up to {args.samples} sampled rows per object will be "
            f"sent to provider profile {args.provider}",
            file=sys.stderr,
        )
    if args.profile_rows:
        detail = (
            " with permission for complete small-domain values"
            if args.include_small_domain_values
            else ""
        )
        print(
            f"warning: bounded column profiles{detail} will be sent to "
            f"provider profile {args.provider}",
            file=sys.stderr,
        )
    if args.knowledge == "scoped" or args.knowledge_documents:
        print(
            "warning: bounded knowledge documents will be sent to "
            f"provider profile {args.provider}",
            file=sys.stderr,
        )
    result = run_annotation_batch_use_case(
        args.name,
        provider_name=args.provider,
        namespace=args.namespace,
        objects=objects,
        limit=args.limit,
        missing_only=not args.include_annotated,
        workers=args.workers,
        retry=args.retry,
        retry_backoff=args.retry_backoff,
        skip_errors=args.skip_errors,
        max_errors=args.max_errors,
        model=args.model,
        timeout=args.timeout,
        sample_limit=args.samples,
        profile_row_limit=args.profile_rows,
        include_small_domain_values=args.include_small_domain_values,
        config_path=args.config,
        knowledge_mode=args.knowledge,
        knowledge_document_ids=tuple(args.knowledge_documents or ()),
        knowledge_workspace=args.knowledge_workspace,
        max_knowledge_characters=args.max_knowledge_characters,
        progress=_print_annotation_progress,
    )
    payload = {**result.run.to_dict(), "graph": result.graph.name, "path": str(result.path)}
    if args.format == "json":
        print_json(payload)
    else:
        print(
            f"Annotated {result.run.annotated}/{result.run.planned} objects "
            f"({result.run.failed} failed)."
        )
        print(f"Path: {result.path}")
    return 0


_HANDLERS = {
    "build": _run_build,
    "import-catalog": _run_import_catalog,
    "refresh": _run_refresh,
    "list": _run_list,
    "show": _run_show,
    "annotate": _run_annotate,
}
