"""Thin command-line adapter for write-centred static lineage."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from tarel.cli import lineage_trace
from tarel.cli._args import add_format_argument
from tarel.cli._output import print_json
from tarel.lineage.analysis_application import (
    run_lineage_analysis_use_case,
)
from tarel.lineage.application import (
    LineageChangeResult,
    add_manual_hop_use_case,
    add_manual_job_use_case,
    apply_lineage_proposal_use_case,
    build_lineage_use_case,
    decide_lineage_item_use_case,
    import_dbt_lineage_use_case,
    lineage_status_use_case,
    list_lineage_items_use_case,
    load_lineage_use_case,
    next_lineage_task_use_case,
    process_lineage_view_use_case,
    table_lineage_view_use_case,
)
from tarel.lineage.contracts import LineageFailure
from tarel.lineage.revision import lineage_revision
from tarel.lineage.runtime import (
    load_runtime_lineage_input,
)
from tarel.lineage.runtime_application import (
    import_runtime_lineage_use_case,
    list_runtime_lineages_use_case,
    load_runtime_lineage_use_case,
    trace_runtime_lineage_use_case,
)
from tarel.lineage.status import lineage_status


def register(subcommands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    lineage = subcommands.add_parser(
        "lineage",
        help="Build and review direct process and table lineage.",
    )
    commands = lineage.add_subparsers(dest="lineage_command")

    build = commands.add_parser(
        "build",
        help="Create or refresh lineage from a canonical input file.",
    )
    build.add_argument("name")
    build.add_argument("--source", required=True, type=Path)
    add_format_argument(build)

    import_dbt = commands.add_parser(
        "import-dbt",
        help="Import declared dbt manifest v12 dependencies without SQL analysis.",
    )
    import_dbt.add_argument("name")
    import_dbt.add_argument("--manifest", required=True, type=Path)
    import_dbt.add_argument(
        "--catalog-map",
        action="append",
        default=[],
        metavar="FROM=TO",
        help="Explicit database/catalog name mapping; repeat for multiple catalogs.",
    )
    add_format_argument(import_dbt)

    show = commands.add_parser(
        "show",
        help="Show the document, process, table, or coverage projection.",
    )
    show.add_argument("name")
    show.add_argument(
        "--view",
        choices=("document", "process", "status", "tables"),
        default="document",
    )
    add_format_argument(show)

    import_runtime = commands.add_parser(
        "import-runtime",
        help="Import one immutable, sanitized runtime query run.",
    )
    import_runtime.add_argument("name", help="New local runtime-lineage name.")
    import_runtime.add_argument("--source", required=True, type=Path)
    add_format_argument(import_runtime)

    show_runtime = commands.add_parser(
        "show-runtime",
        help="Show one sanitized runtime-lineage run.",
    )
    show_runtime.add_argument("name")
    add_format_argument(show_runtime)

    list_runtime = commands.add_parser(
        "list-runtime",
        help="List sanitized runtime-lineage runs.",
    )
    add_format_argument(list_runtime)

    trace_runtime = commands.add_parser(
        "trace-runtime",
        help="Trace a successful runtime call to its graph-bound source inputs.",
    )
    trace_runtime.add_argument("name")
    trace_runtime.add_argument("call_id")
    add_format_argument(trace_runtime)

    next_task = commands.add_parser(
        "next",
        help="Return the next source-analysis task for the current coding agent.",
    )
    next_task.add_argument("name")
    next_task.add_argument("--source", required=True, type=Path)

    apply = commands.add_parser("apply", help="Apply one coding-agent workfile as draft lineage.")
    apply.add_argument("name")
    apply.add_argument("--source", required=True, type=Path)
    apply.add_argument("--input", required=True, help="Proposal JSON file or '-' for stdin.")
    add_format_argument(apply)

    analyze = commands.add_parser(
        "analyze",
        help="Analyze complete definitions with a provider or optional local SQLGlot.",
    )
    analyze.add_argument("name")
    analyze.add_argument("--source", required=True, type=Path)
    analyze.add_argument(
        "--analyzer",
        choices=("auto", "llm", "sqlglot"),
        default="llm",
        help="Use the provider, optional SQLGlot, or SQLGlot with provider fallback.",
    )
    analyze.add_argument("--provider")
    analyze.add_argument(
        "--dialect",
        help="Explicit SQLGlot dialect for definitions whose language is ambiguous.",
    )
    analyze.add_argument("--model")
    analyze.add_argument("--timeout", type=float, default=180.0)
    analyze.add_argument("--retry", type=int, default=1)
    analyze.add_argument("--review-passes", type=int, default=1)
    analyze.add_argument("--limit", type=int)
    analyze.add_argument(
        "--definition",
        action="append",
        dest="definitions",
        help="Analyze only this exact definition ID, external ID, name, or qualified name.",
    )
    analyze.add_argument("--max-output-tokens", type=int)
    analyze.add_argument(
        "--reasoning-effort",
        choices=("none", "minimal", "low", "medium", "high", "xhigh"),
    )
    add_format_argument(analyze)

    review = commands.add_parser("review", help="List or decide draft lineage items.")
    review.add_argument("name")
    review.add_argument("item_id", nargs="?")
    review.add_argument("--decision", choices=("validate", "reject"))
    review.add_argument("--reason")
    review.add_argument(
        "--state",
        action="append",
        choices=("draft", "review_required", "validated", "rejected"),
    )
    add_format_argument(review)

    lineage_trace.register(commands)

    add_job = commands.add_parser(
        "add-job",
        help="Add a human-authored procedure or script to a manual lineage overlay.",
    )
    add_job.add_argument("name", help="Manual lineage overlay name; created if missing.")
    add_job.add_argument("--kind", required=True, choices=("procedure", "script"))
    add_job.add_argument("--job-name", required=True)
    add_job.add_argument("--qualified-name", required=True)
    add_job.add_argument("--language", required=True)
    add_job.add_argument("--source-reference", required=True)
    add_job.add_argument("--description", required=True)
    add_format_argument(add_job)

    add_hop = commands.add_parser(
        "add-hop",
        help="Add a human-authored source-to-target hop through a manual job.",
    )
    add_hop.add_argument("name", help="Existing manual lineage overlay name.")
    add_hop.add_argument("--job", required=True, help="Job ID or qualified name.")
    add_hop.add_argument("--source", required=True)
    add_hop.add_argument("--target", required=True)
    add_hop.add_argument(
        "--operation",
        required=True,
        choices=("delete", "insert", "merge", "select_into", "truncate", "update"),
    )
    add_hop.add_argument(
        "--role",
        default="business_data",
        choices=(
            "audit",
            "business_data",
            "control",
            "deduplication",
            "filter",
            "lookup",
            "unknown",
        ),
    )
    add_hop.add_argument("--evidence-reference", required=True)
    add_hop.add_argument("--reason", required=True)
    add_hop.add_argument("--line-start", type=int, default=1)
    add_hop.add_argument("--line-end", type=int, default=1)
    add_format_argument(add_hop)


def dispatch(args: argparse.Namespace) -> int | None:
    if args.command != "lineage":
        return None
    command = args.lineage_command
    handler = _HANDLERS.get(command)
    if handler is not None:
        return handler(args)
    result = lineage_trace.dispatch(args)
    return 0 if result is None else result


def _review(args: argparse.Namespace) -> int:
    deciding = args.item_id is not None or args.decision is not None or args.reason is not None
    if deciding:
        if not args.item_id or not args.decision or not args.reason or args.state:
            raise LineageFailure(
                "invalid_lineage_review",
                "A decision requires ITEM_ID, --decision, and --reason without --state.",
            )
        result = decide_lineage_item_use_case(
            args.name,
            args.item_id,
            decision=args.decision,
            reason=args.reason,
        )
        payload: object = {"item": result.item.to_dict(), "path": str(result.path)}
    else:
        states = frozenset(args.state) if args.state else None
        payload = {
            "items": [
                item.to_dict() for item in list_lineage_items_use_case(args.name, states=states)
            ]
        }
    _render_view(payload, "review", output_format=args.format)
    return 0


def _read_json_object(location: str) -> dict[str, Any]:
    try:
        raw = sys.stdin.read() if location == "-" else Path(location).read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise LineageFailure("invalid_lineage_proposal", "Could not read proposal JSON.") from exc
    if not isinstance(payload, dict):
        raise LineageFailure("invalid_lineage_proposal", "Proposal JSON must be an object.")
    return payload


def _document_change_payload(result: LineageChangeResult) -> dict[str, object]:
    payload: dict[str, object] = {
        "lineage": result.document.to_dict(),
        "path": str(result.path),
        "status": lineage_status(result.document).to_dict(),
    }
    if result.report is not None:
        payload["change_report"] = result.report.to_dict()
        payload["change_report_path"] = str(result.report_path)
    return payload


def _render_document_change(payload: dict[str, Any], *, output_format: str) -> None:
    if output_format == "json":
        print_json(payload)
        return
    lineage = payload["lineage"]
    if isinstance(lineage, dict):
        print(f"Lineage: {lineage['name']}")
        print(f"Definitions: {len(lineage['definitions'])}")
        print(f"Steps: {len(lineage['steps'])}")
        print(f"Claims: {len(lineage['claims'])}")
        print(f"Materializations: {len(lineage['materializations'])}")
        print(f"Write units: {len(lineage['write_units'])}")
    status = payload.get("status")
    if isinstance(status, dict):
        coverage = status.get("analysis_coverage")
        if isinstance(coverage, dict):
            print(
                "Analysis: "
                f"{coverage['complete']} complete, {coverage['failed']} failed, "
                f"{coverage['pending']} pending"
            )
    report = payload.get("change_report")
    if isinstance(report, dict):
        print(
            f"Refresh: {len(report['changes'])} changes; "
            f"{len(report['stale_items'])} stale items"
        )
        print(f"Change report: {payload['change_report_path']}")
    print(f"Path: {payload['path']}")


def _render_runtime(payload: dict[str, Any], *, output_format: str) -> None:
    if output_format == "json":
        print_json(payload)
        return
    document = payload.get("runtime_lineage")
    if not isinstance(document, dict):
        return
    graph = document["graph"]
    print(f"Runtime lineage: {document['name']}")
    print(f"Run: {document['run_id']}")
    print(f"Graph: {graph['name']}@{graph['revision']}")
    print(f"Runtime events: {len(document['events'])}")
    if payload.get("path") is not None:
        print(f"Path: {payload['path']}")


def _render_document_summary(document: dict[str, Any]) -> None:
    print(f"Lineage: {document['name']}")
    print(f"Source: {document['source_name']} ({document['source_kind']})")
    print(f"Workflow: {document['workflow_name']}")
    for key in ("definitions", "steps", "analyses", "claims", "write_units", "materializations"):
        print(f"{key.replace('_', ' ').capitalize()}: {len(document.get(key, []))}")
    print("Use --view process, tables or status for details, or --format json for everything.")


def _render_view(payload: object, view: str, *, output_format: str) -> None:
    if output_format == "json":
        print_json(payload)
        return
    if not isinstance(payload, dict):
        return
    if view == "document":
        _render_document_summary(payload)
        return
    if view == "manual job":
        definition = payload.get("definition")
        if isinstance(definition, dict):
            print(f"Added manual job: {definition['qualified_name']}")
            print(f"Lineage: {payload['lineage']}; revision: {payload['revision']}")
        return
    if view == "manual hop":
        item = payload.get("item")
        if isinstance(item, dict):
            source = item["sources"][0]["target"]
            print(f"Added manual hop: {source} -> {item['target']} [{item['state']}]")
            print(f"Lineage: {payload['lineage']}; revision: {payload['revision']}")
        return
    if view == "status":
        _render_status(payload)
        return
    rows = payload.get(view)
    if not isinstance(rows, list):
        rows = payload.get("items")
    if not isinstance(rows, list):
        item = payload.get("item")
        rows = [item] if isinstance(item, dict) else []
    for row in rows:
        if view == "process":
            dependencies = ", ".join(row["depends_on"]) or "-"
            print(f"- {row['name']}: {row['definition']} (after: {dependencies})")
        elif view == "tables":
            print(
                f"- {row['source']} -> {row['target']} via {row['via_definition']} [{row['state']}]"
            )
        else:
            operation = row.get("operation") or f"materialize:{row.get('mode')}"
            print(f"- {row['id']}: {operation} {row['target']} [{row['state']}]")


def _render_status(payload: dict[str, Any]) -> None:
    coverage = payload.get("analysis_coverage")
    if isinstance(coverage, dict):
        print(f"Lineage: {payload['lineage']}")
        print(
            "Analysis: "
            f"{coverage['complete']} complete, {coverage['failed']} failed, "
            f"{coverage['pending']} pending / {coverage['total']} total"
        )
    definitions = payload.get("definitions")
    if not isinstance(definitions, list):
        return
    for item in definitions:
        if not isinstance(item, dict):
            continue
        claims = item["claims"]
        materializations = item["materializations"]
        writes = item["write_units"]
        failure = item.get("failure")
        failure_text = (
            f" [{failure['code']}]" if isinstance(failure, dict) else ""
        )
        print(
            f"- {item['definition_name']}: {item['analysis_state']}{failure_text}; "
            f"observations={claims['total']}; materializations={materializations['total']}; "
            f"writes={writes['total']} "
            f"(draft={writes['draft']}, review_required={writes['review_required']}, "
            f"validated={writes['validated']}, rejected={writes['rejected']})"
        )


def _run_import_dbt(args: argparse.Namespace) -> int:
    mappings = {}
    for value in args.catalog_map:
        source, separator, target = value.partition("=")
        if not separator or not source or not target or source in mappings:
            raise LineageFailure(
                "invalid_dbt_mapping", "Use unique --catalog-map FROM=TO entries."
            )
        mappings[source] = target
    result = import_dbt_lineage_use_case(
        args.name,
        manifest_path=args.manifest,
        catalog_map=mappings,
    )
    _render_document_change(_document_change_payload(result), output_format=args.format)
    return 0


def _run_build(args: argparse.Namespace) -> int:
    result = build_lineage_use_case(args.name, source_path=args.source)
    payload = _document_change_payload(result)
    _render_document_change(payload, output_format=args.format)
    return 0


def _run_show(args: argparse.Namespace) -> int:
    if args.view == "document":
        payload: object = load_lineage_use_case(args.name).to_dict()
    elif args.view == "process":
        payload = {
            "process": [item.to_dict() for item in process_lineage_view_use_case(args.name)]
        }
    elif args.view == "tables":
        payload = {
            "tables": [item.to_dict() for item in table_lineage_view_use_case(args.name)]
        }
    else:
        payload = lineage_status_use_case(args.name).to_dict()
    _render_view(payload, args.view, output_format=args.format)
    return 0


def _run_import_runtime(args: argparse.Namespace) -> int:
    result = import_runtime_lineage_use_case(
        args.name,
        load_runtime_lineage_input(args.source),
    )
    _render_runtime(
        {"path": str(result.path), "runtime_lineage": result.document.to_dict()},
        output_format=args.format,
    )
    return 0


def _run_show_runtime(args: argparse.Namespace) -> int:
    _render_runtime(
        {"runtime_lineage": load_runtime_lineage_use_case(args.name).to_dict()},
        output_format=args.format,
    )
    return 0


def _run_list_runtime(args: argparse.Namespace) -> int:
    payload = {"runtime_lineages": list(list_runtime_lineages_use_case())}
    if args.format == "json":
        print_json(payload)
    else:
        for name in payload["runtime_lineages"]:
            print(name)
    return 0


def _run_trace_runtime(args: argparse.Namespace) -> int:
    payload: dict[str, Any] = trace_runtime_lineage_use_case(args.name, args.call_id).to_dict()
    if args.format == "json":
        print_json(payload)
    else:
        print(f"Runtime lineage: {payload['runtime_lineage']}")
        print(f"Start call: {payload['start_call_id']}")
        for origin in payload["origins"]:
            print(f"- {origin['reference']} [{origin['kind']}]")
    return 0


def _run_next(args: argparse.Namespace) -> int:
    task = next_lineage_task_use_case(args.name, source_path=args.source)
    payload = {"status": "complete"} if task is None else task.to_dict()
    print_json(payload)
    return 0


def _run_apply(args: argparse.Namespace) -> int:
    result = apply_lineage_proposal_use_case(
        args.name,
        source_path=args.source,
        payload=_read_json_object(args.input),
    )
    payload = _document_change_payload(result)
    _render_document_change(payload, output_format=args.format)
    return 0


def _run_analyze(args: argparse.Namespace) -> int:
    if args.analyzer in {"auto", "llm"} and args.provider:
        print(
            f"warning: unresolved complete source definitions will be sent to provider "
            f"profile {args.provider}",
            file=sys.stderr,
        )
    result = run_lineage_analysis_use_case(
        args.name,
        source_path=args.source,
        analyzer=args.analyzer,
        provider_name=args.provider,
        dialect=args.dialect,
        model=args.model,
        timeout=args.timeout,
        retry=args.retry,
        limit=args.limit,
        definition_references=tuple(args.definitions or ()),
        review_passes=args.review_passes,
        max_output_tokens=args.max_output_tokens,
        reasoning_effort=args.reasoning_effort,
        progress=lambda message: print(message, file=sys.stderr),
    )
    payload = {
        "analyzer": result.analyzer,
        "applied": result.applied,
        "cache_hits": result.cache_hits,
        "fallback_definitions": list(result.fallback_definitions),
        "lineage": result.document.name,
        "model": result.model,
        "path": str(result.path),
        "planned": result.planned,
        "provider": result.provider,
        "provider_requests": result.provider_requests,
        "sqlglot_applied": result.sqlglot_applied,
        "unresolved_definitions": list(result.unresolved_definitions),
        "write_units": len(result.document.write_units),
    }
    if args.format == "json":
        print_json(payload)
    else:
        print(f"Analyzed {result.applied}/{result.planned} definitions.")
        print(f"Analyzer: {result.analyzer}")
        if result.provider is not None:
            print(f"Provider: {result.provider}; model: {result.model}")
        print(
            f"SQLGlot: {result.sqlglot_applied}; provider fallback: "
            f"{len(result.fallback_definitions)}; unresolved: "
            f"{len(result.unresolved_definitions)}"
        )
        print(
            f"Cache hits: {result.cache_hits}; provider requests: "
            f"{result.provider_requests}"
        )
        print(f"Write units: {len(result.document.write_units)}")
        print(f"Path: {result.path}")
    return 0


def _run_review(args: argparse.Namespace) -> int:
    return _review(args)


def _run_add_job(args: argparse.Namespace) -> int:
    result = add_manual_job_use_case(
        args.name,
        kind=args.kind,
        job_name=args.job_name,
        qualified_name=args.qualified_name,
        language=args.language,
        source_reference=args.source_reference,
        description=args.description,
    )
    _render_view(
        {
            "definition": result.definition.to_dict(),
            "lineage": result.document.name,
            "path": str(result.path),
            "revision": lineage_revision(result.document),
        },
        "manual job",
        output_format=args.format,
    )
    return 0


def _run_add_hop(args: argparse.Namespace) -> int:
    result = add_manual_hop_use_case(
        args.name,
        job_reference=args.job,
        source=args.source,
        target=args.target,
        operation=args.operation,
        role=args.role,
        evidence_reference=args.evidence_reference,
        reason=args.reason,
        line_start=args.line_start,
        line_end=args.line_end,
    )
    _render_view(
        {
            "item": result.item.to_dict(),
            "lineage": result.document.name,
            "path": str(result.path),
            "revision": lineage_revision(result.document),
        },
        "manual hop",
        output_format=args.format,
    )
    return 0


_HANDLERS = {
    "import-dbt": _run_import_dbt,
    "build": _run_build,
    "show": _run_show,
    "import-runtime": _run_import_runtime,
    "show-runtime": _run_show_runtime,
    "list-runtime": _run_list_runtime,
    "trace-runtime": _run_trace_runtime,
    "next": _run_next,
    "apply": _run_apply,
    "analyze": _run_analyze,
    "review": _run_review,
    "add-job": _run_add_job,
    "add-hop": _run_add_hop,
}
