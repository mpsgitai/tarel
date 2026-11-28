"""`tarel annotation`: plan, apply, review and edit semantic annotations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from tarel.annotations.application import (
    annotation_coverage_use_case,
    apply_annotation_use_case,
    decide_annotation_use_case,
    edit_annotation_use_case,
    list_annotation_reviews_use_case,
    plan_annotations_use_case,
    plan_focus_annotations_use_case,
    show_annotation_use_case,
)
from tarel.annotations.contracts import AnnotationFailure
from tarel.annotations.review import AnnotationReviewRecord
from tarel.cli._args import Subcommands, add_annotation_knowledge_arguments, add_format_argument
from tarel.cli._output import print_json, render_annotation_plan, render_compact
from tarel.cli._pretty_catalog import render_coverage


def register(subcommands: Subcommands) -> None:
    """Add the `annotation` command group to the top-level parser."""
    annotation = subcommands.add_parser(
        "annotation",
        help="Exchange annotation tasks with the current coding agent.",
    )
    annotation_commands = annotation.add_subparsers(dest="annotation_command")

    annotation_plan = annotation_commands.add_parser(
        "plan",
        help="List annotation tasks without calling an API provider.",
    )
    annotation_plan.add_argument("name", nargs="?", help="Graph name.")
    annotation_plan.add_argument("--focus", help="Plan only objects reached by this focus.")
    annotation_plan.add_argument("--namespace", "--schema", dest="namespace")
    annotation_plan.add_argument("--object", action="append", dest="objects")
    annotation_plan.add_argument("--limit", type=int)
    annotation_plan.add_argument(
        "--include-annotated",
        action="store_true",
        help="Plan complete objects instead of filling only missing annotations.",
    )
    add_annotation_knowledge_arguments(annotation_plan)
    add_format_argument(annotation_plan)

    annotation_next = annotation_commands.add_parser(
        "next",
        help="Return the next scoped annotation task as JSON for the coding agent.",
    )
    annotation_next.add_argument("name", nargs="?", help="Graph name.")
    annotation_next.add_argument("--focus", help="Return the next task inside this focus.")
    annotation_next.add_argument("--namespace", "--schema", dest="namespace")
    annotation_next.add_argument("--object", action="append", dest="objects")
    annotation_next.add_argument(
        "--include-annotated",
        action="store_true",
        help="Return a complete-object task instead of a missing-only delta.",
    )
    annotation_next.add_argument("--samples", type=int, default=0)
    annotation_next.add_argument("--profile-rows", type=int, default=0)
    annotation_next.add_argument(
        "--include-small-domain-values",
        action="store_true",
        help="Explicitly allow small-domain values in ephemeral annotation input.",
    )
    annotation_next.add_argument("--config", type=Path, help="Private connector configuration.")
    add_annotation_knowledge_arguments(annotation_next)
    add_format_argument(annotation_next, default="json")

    annotation_apply = annotation_commands.add_parser(
        "apply",
        help="Validate and apply one coding-agent proposal as a draft.",
    )
    annotation_apply.add_argument("name")
    annotation_apply.add_argument(
        "--input",
        required=True,
        help="Proposal JSON file or '-' for stdin.",
    )

    annotation_list = annotation_commands.add_parser(
        "list",
        help="List object and field annotation proposals for review.",
    )
    annotation_list.add_argument("name")
    annotation_list.add_argument(
        "--state",
        action="append",
        choices=("draft", "validated", "rejected", "deferred", "review_required"),
        help="Limit results to one or more review states.",
    )
    add_format_argument(annotation_list)

    coverage = annotation_commands.add_parser(
        "coverage",
        help="Annotation, role and grain coverage of a graph or workspace; what to annotate next.",
    )
    coverage.add_argument("--graph", dest="graph_name")
    coverage.add_argument("--workspace", dest="workspace_name")
    coverage.add_argument("--system", action="append", dest="systems")
    coverage.add_argument("--limit", type=int, default=50, help="Unannotated objects listed.")
    add_format_argument(coverage, pretty=True)

    annotation_show = annotation_commands.add_parser(
        "show",
        help="Show one object or field annotation and its review history.",
    )
    annotation_show.add_argument("name")
    annotation_show.add_argument("target", help="Object, field, or stable node ID.")
    add_format_argument(annotation_show)

    annotation_edit = annotation_commands.add_parser(
        "edit",
        help="Create or update one bounded object or field annotation.",
    )
    annotation_edit.add_argument("name")
    annotation_edit.add_argument("target", help="Object, field, or stable node ID.")
    annotation_edit.add_argument("--input", required=True, help="Patch JSON file or '-' for stdin.")
    annotation_edit.add_argument("--reason", required=True)
    add_format_argument(annotation_edit)

    for decision, state_label in (
        ("validate", "validated"),
        ("reject", "rejected"),
        ("defer", "deferred"),
    ):
        annotation_decision = annotation_commands.add_parser(
            decision,
            help=f"Mark one annotation as {state_label} by a human.",
        )
        annotation_decision.add_argument("name")
        annotation_decision.add_argument("target", help="Object, field, or stable node ID.")
        annotation_decision.add_argument("--reason", required=True)
        annotation_decision.add_argument(
            "--include-fields",
            action="store_true",
            help=(
                "Apply the decision to the selected table or view and to each of its "
                "fields that has a proposal; fields without a proposal stay unchanged."
            ),
        )
        add_format_argument(annotation_decision)



def dispatch(args: argparse.Namespace) -> int | None:
    """Run a parsed `annotation` command; return ``None`` for other commands."""
    if args.command != "annotation":
        return None
    command = args.annotation_command
    handler = _HANDLERS.get(command)
    if handler is not None:
        return handler(args)
    return None


def _require_graph_or_focus(graph_name: str | None, focus_name: str | None) -> None:
    if bool(graph_name) == bool(focus_name):
        raise AnnotationFailure(
            "invalid_annotation_scope",
            "Provide exactly one graph NAME or --focus FOCUS.",
        )


def _render_annotation_records(
    records: tuple[AnnotationReviewRecord, ...],
    *,
    output_format: str,
) -> None:
    if output_format == "json":
        print_json({"annotations": [record.to_dict() for record in records], "count": len(records)})
        return
    print(f"Annotations: {len(records)}")
    for record in records:
        annotation = record.node.annotation
        state = annotation.state if annotation else "missing"
        print(f"{record.reference}  [{record.node.type}; {state}]")


def _render_annotation_record(payload: dict[str, Any], *, output_format: str) -> None:
    if output_format == "json":
        print_json(payload)
        return
    print(f"Annotation: {payload['reference']}")
    print(f"Type: {payload['node_type']}")
    annotation = payload.get("annotation")
    if not isinstance(annotation, dict):
        print("State: missing")
        return
    print(f"State: {annotation['state']}")
    print(f"Description: {annotation['description']}")
    if annotation.get("role"):
        print(f"Role: {annotation['role']}")
    if payload.get("grain"):
        print(f"Grain: {payload['grain']}")
    if payload.get("semantic_type"):
        print(f"Semantic type: {payload['semantic_type']}")
    synonyms = annotation.get("synonyms")
    if isinstance(synonyms, list) and synonyms:
        print(f"Synonyms: {', '.join(str(item) for item in synonyms)}")
    tags = annotation.get("tags")
    if isinstance(tags, list) and tags:
        print(f"Tags: {', '.join(str(item) for item in tags)}")
    warnings = annotation.get("warnings")
    if isinstance(warnings, list) and warnings:
        print(f"Warnings: {', '.join(str(item) for item in warnings)}")
    review = payload.get("review")
    if isinstance(review, dict):
        events = review.get("events")
        if isinstance(events, list):
            print("Review:")
            for event in events:
                if isinstance(event, dict):
                    print(f"- {event.get('action')}: {event.get('reason')}")
    if payload.get("path"):
        print(f"Path: {payload['path']}")


def _render_annotation_change(
    records: tuple[AnnotationReviewRecord, ...],
    *,
    path: Path,
    output_format: str,
) -> None:
    if len(records) == 1:
        _render_annotation_record(
            {**records[0].to_dict(), "path": str(path)},
            output_format=output_format,
        )
        return
    payload = {
        "annotations": [record.to_dict() for record in records],
        "count": len(records),
        "path": str(path),
    }
    if output_format == "json":
        print_json(payload)
        return
    print(f"Reviewed annotations: {len(records)}")
    for record in records:
        annotation = record.node.annotation
        print(f"- {record.reference} [{annotation.state if annotation else 'missing'}]")
    print(f"Path: {path}")


def _read_json_object(path_value: str) -> dict[str, object]:
    try:
        raw = (
            sys.stdin.read() if path_value == "-" else Path(path_value).read_text(encoding="utf-8")
        )
        payload = json.loads(raw)
    except FileNotFoundError as exc:
        raise AnnotationFailure(
            "proposal_not_found",
            f"Proposal file not found: {path_value}",
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise AnnotationFailure("invalid_proposal", "Could not read proposal JSON.") from exc
    if not isinstance(payload, dict):
        raise AnnotationFailure("invalid_proposal", "Proposal JSON root must be an object.")
    return payload


def _run_plan(args: argparse.Namespace) -> int:
    _require_graph_or_focus(args.name, args.focus)
    if args.focus:
        tasks = plan_focus_annotations_use_case(
            args.focus,
            namespace=args.namespace,
            objects=set(args.objects or []),
            limit=args.limit,
            missing_only=not args.include_annotated,
            knowledge_mode=args.knowledge,
            knowledge_document_ids=tuple(args.knowledge_documents or ()),
            knowledge_workspace=args.knowledge_workspace,
            max_knowledge_characters=args.max_knowledge_characters,
        )
    else:
        tasks = plan_annotations_use_case(
            args.name,
            namespace=args.namespace,
            objects=set(args.objects or []),
            limit=args.limit,
            missing_only=not args.include_annotated,
            knowledge_mode=args.knowledge,
            knowledge_document_ids=tuple(args.knowledge_documents or ()),
            knowledge_workspace=args.knowledge_workspace,
            max_knowledge_characters=args.max_knowledge_characters,
        )
    render_annotation_plan(tasks, output_format=args.format)
    return 0


def _run_next(args: argparse.Namespace) -> int:
    _require_graph_or_focus(args.name, args.focus)
    if args.samples:
        print(
            f"warning: including up to {args.samples} sampled rows "
            "in the coding-agent task",
            file=sys.stderr,
        )
    if args.profile_rows:
        detail = (
            " with permission for complete small-domain values"
            if args.include_small_domain_values
            else ""
        )
        print(
            f"warning: bounded column profiles{detail} will be included in the "
            "coding-agent task",
            file=sys.stderr,
        )
    if args.knowledge == "scoped" or args.knowledge_documents:
        print(
            "warning: bounded knowledge documents will be included in the "
            "coding-agent task",
            file=sys.stderr,
        )
    if args.focus:
        tasks = plan_focus_annotations_use_case(
            args.focus,
            namespace=args.namespace,
            objects=set(args.objects or []),
            limit=1,
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
    else:
        tasks = plan_annotations_use_case(
            args.name,
            namespace=args.namespace,
            objects=set(args.objects or []),
            limit=1,
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
    if args.format == "json":
        print_json(tasks[0].to_dict() if tasks else {"status": "complete"})
    elif not tasks:
        print("No annotation task left.")
    else:
        task = tasks[0]
        print(f"Task: {task.id}")
        print(f"Target: {task.target_label} ({task.mode})")
        print(f"Fields: {', '.join(task.field_names) or '-'}")
        print(f"Submit: tarel annotation apply {task.graph_name} --input PROPOSAL.json")
    return 0


def _run_apply(args: argparse.Namespace) -> int:
    payload = _read_json_object(args.input)
    result = apply_annotation_use_case(args.name, payload)
    print(f"Applied draft annotation to {result.target_id}")
    print(f"Path: {result.path}")
    return 0


def _run_list(args: argparse.Namespace) -> int:
    states = frozenset(args.state) if args.state else None
    records = list_annotation_reviews_use_case(args.name, states=states)
    _render_annotation_records(records, output_format=args.format)
    return 0


def _run_show(args: argparse.Namespace) -> int:
    record = show_annotation_use_case(args.name, args.target)
    _render_annotation_record(record.to_dict(), output_format=args.format)
    return 0


def _run_edit(args: argparse.Namespace) -> int:
    patch = _read_json_object(args.input)
    result = edit_annotation_use_case(
        args.name,
        args.target,
        patch,
        reason=args.reason,
    )
    _render_annotation_record(
        {**result.record.to_dict(), "path": str(result.path)},
        output_format=args.format,
    )
    return 0


def _run_decide(args: argparse.Namespace) -> int:
    state = {
        "validate": "validated",
        "reject": "rejected",
        "defer": "deferred",
    }[args.annotation_command]
    result = decide_annotation_use_case(
        args.name,
        args.target,
        state=state,
        reason=args.reason,
        include_fields=args.include_fields,
    )
    _render_annotation_change(
        result.records,
        path=result.path,
        output_format=args.format,
    )
    return 0


def _run_coverage(args: argparse.Namespace) -> int:
    coverage = annotation_coverage_use_case(
        graph_name=args.graph_name,
        workspace_name=args.workspace_name,
        systems=tuple(args.systems or ()),
        limit=args.limit,
    )
    payload = coverage.to_dict()
    if args.format == "json":
        render_compact(payload, output_format="json")
    elif args.format == "pretty":
        render_coverage(payload)
    else:
        print(f"Coverage: {payload['scope']} ({payload['objects']} objects)")
        for key in ("annotated_pct", "role_coverage_pct", "grain_coverage_pct"):
            print(f"{key}: {payload.get(key, 'n/a')}")
        print("States: " + ", ".join(f"{k}={v}" for k, v in coverage.states))
        print(f"Unannotated: {coverage.unannotated_total}")
        for item in coverage.unannotated:
            rows = f"; rows={item.row_count}" if item.row_count is not None else ""
            print(f"- {item.graph}:{item.label} [{item.type}; fields={item.fields}{rows}]")
    return 0


_HANDLERS = {
    "coverage": _run_coverage,
    "plan": _run_plan,
    "next": _run_next,
    "apply": _run_apply,
    "list": _run_list,
    "show": _run_show,
    "edit": _run_edit,
    "defer": _run_decide,
    "reject": _run_decide,
    "validate": _run_decide,
}
