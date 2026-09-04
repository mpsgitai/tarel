"""CLI adapters for logical relationship audit, review and policy-gated lookup."""

from __future__ import annotations

import argparse
import json

from tarel.logical_joins.application import (
    find_logical_joins_use_case,
    list_logical_joins_use_case,
    load_logical_join_use_case,
    logical_join_summary,
    review_logical_join_use_case,
)
from tarel.logical_joins.contracts import LOGICAL_JOIN_MODES


def add_logical_join_commands(
    subcommands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subcommands.add_parser(
        "logical-join", help="Inspect and review logical join sidecars."
    )
    commands = parser.add_subparsers(dest="logical_join_command", required=True)
    listing = commands.add_parser("list", help="List audit summaries, including inactive records.")
    listing.add_argument("--graph")
    show = commands.add_parser("show", help="Show one full logical join audit artifact.")
    show.add_argument("join_id")
    review = commands.add_parser("review", help="Record a revision-pinned human decision.")
    review.add_argument("join_id")
    review.add_argument("--decision", choices=("approve", "reject"), required=True)
    review.add_argument("--reason", required=True)
    review.add_argument("--revision", required=True)
    find = commands.add_parser("find", help="Find only current policy-eligible logical joins.")
    find.add_argument("graph")
    find.add_argument("--join-id", help="Narrow to a current policy-eligible artifact ID.")
    find.add_argument("--mode", choices=tuple(sorted(LOGICAL_JOIN_MODES)), default="confirmed_only")
    find.add_argument("--limit", type=int, default=20)
    for command in (listing, show, review, find):
        command.add_argument("--format", choices=("text", "json"), default="text")


def dispatch_logical_join(args: argparse.Namespace) -> int | None:
    if args.command != "logical-join":
        return None
    if args.logical_join_command == "list":
        payload = {
            "logical_joins": [
                logical_join_summary(item)
                for item in list_logical_joins_use_case(graph_name=args.graph)
            ]
        }
    elif args.logical_join_command == "show":
        payload = load_logical_join_use_case(args.join_id).to_dict()
    elif args.logical_join_command == "review":
        payload = review_logical_join_use_case(
            args.join_id,
            decision=args.decision,
            reason=args.reason,
            expected_revision=args.revision,
        ).to_dict()
    else:
        payload = {
            "logical_joins": [
                item.to_dict()
                for item in find_logical_joins_use_case(
                    args.graph,
                    mode=args.mode,
                    join_id=args.join_id,
                    limit=args.limit,
                )
            ]
        }
    if args.format == "json":
        print(json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2))
    elif "logical_joins" in payload:
        for item in payload["logical_joins"]:
            print(f"{item['id']} [{item['state']}] {item.get('usage', 'audit_only')}")
        print(f"Logical joins: {len(payload['logical_joins'])}; no physical graph expansion.")
    else:
        print(f"{payload['id']} [{payload['state']}] revision={payload['revision']}")
    return 0
