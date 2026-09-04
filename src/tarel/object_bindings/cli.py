"""Thin object-binding CLI; private resolution values are accepted through stdin only."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tarel.object_bindings.application import (
    _unique,
    find_object_bindings_use_case,
    load_object_binding_use_case,
    resolve_object_binding_use_case,
    review_object_binding_use_case,
    save_object_binding_use_case,
)
from tarel.object_bindings.contracts import ObjectBindingFailure, ObjectValueBinding


def add_binding_commands(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = commands.add_parser(
        "binding", help="Metadata-only field-value to object-family binding."
    )
    sub = parser.add_subparsers(dest="binding_command", required=True)
    importing = sub.add_parser("import")
    importing.add_argument("--source", required=True, help="Candidate JSON path or '-' for stdin.")
    find = sub.add_parser("find")
    find.add_argument("graph")
    find.add_argument(
        "--mode", choices=("confirmed_only", "include_candidates"), default="confirmed_only"
    )
    show = sub.add_parser("show")
    review = sub.add_parser("review")
    resolve = sub.add_parser("resolve")
    for item in (show, review, resolve):
        item.add_argument("graph")
        item.add_argument("id")
    for item in (review, resolve):
        item.add_argument("--revision", required=True)
    review.add_argument("--decision", choices=("approve", "reject"), required=True)
    review.add_argument("--reason", required=True)
    resolve.add_argument(
        "--values-stdin",
        action="store_true",
        required=True,
        help="Read an ephemeral JSON string array; never echo/persist it.",
    )
    resolve.add_argument("--limit", type=int, default=100)
    resolve.add_argument("--namespace")
    resolve.add_argument(
        "--mode", choices=("confirmed_only", "include_candidates"), default="confirmed_only"
    )
    for item in (importing, find, show, review, resolve):
        item.add_argument("--format", choices=("text", "json"), default="json")


def dispatch_binding(args: argparse.Namespace) -> int | None:
    if args.command != "binding":
        return None
    command = args.binding_command
    if command == "import":
        payload = save_object_binding_use_case(
            ObjectValueBinding.from_dict(_read(args.source))
        ).to_dict()
    elif command == "find":
        payload = {"bindings": list(find_object_bindings_use_case(args.graph, mode=args.mode))}
    elif command == "show":
        payload = load_object_binding_use_case(args.graph, args.id).to_dict()
    elif command == "review":
        payload = review_object_binding_use_case(
            args.graph,
            args.id,
            expected_revision=args.revision,
            decision=args.decision,
            reason=args.reason,
        ).to_dict()
    else:
        values = _read("-")
        if not isinstance(values, list):
            raise ObjectBindingFailure(
                "invalid_binding_values", "Expected a private JSON string array."
            )
        payload = resolve_object_binding_use_case(
            args.graph,
            args.id,
            values=tuple(values),
            expected_revision=args.revision,
            mode=args.mode,
            namespace=args.namespace,
            limit=args.limit,
        ).to_dict()
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    elif command == "resolve":
        print(f"Object binding: {payload['binding_id']} [{payload['usage']}]")
        print(f"Matched members: {payload['matched_member_count']}; "
              f"unmatched inputs: {payload['unmatched_input_count']}; "
              f"truncated: {payload['truncated']}")
        for item in payload["objects"]:
            print(f"- {item['reference']}")
    elif command == "find":
        for item in payload["bindings"]:
            print(f"{item['id']} [{item.get('usage', 'unusable')}; "
                  f"{item.get('error_code', item.get('state'))}]")
    else:
        print(f"{payload['id']} [{payload['state']}] revision={payload['revision']}")
    return 0


def _read(source: str) -> object:
    try:
        raw = sys.stdin.read(2_000_001) if source == "-" else Path(source).read_text("utf-8")
        if len(raw) > 2_000_000:
            raise ValueError("Input limit")
        return json.loads(raw, object_pairs_hook=_unique)
    except (OSError, ValueError) as exc:
        raise ObjectBindingFailure(
            "invalid_binding_input", "Cannot read bounded binding JSON."
        ) from exc
