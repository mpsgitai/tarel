"""`tarel relationship`: add, check, discover and review graph relationships."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from tarel.cli._args import Subcommands, add_format_argument
from tarel.cli._output import print_json
from tarel.connectors.contracts import RelationshipPairProfile
from tarel.relationships.application import (
    add_relationship_use_case,
    check_relationship_use_case,
    decide_relationship_use_case,
    discover_relationships_use_case,
    list_relationships_use_case,
)


def register(subcommands: Subcommands) -> None:
    """Add the `relationship` command group to the top-level parser."""
    relationship = subcommands.add_parser(
        "relationship",
        help="Add or inspect possible joins without treating them as foreign keys.",
    )
    relationship_commands = relationship.add_subparsers(dest="relationship_command")

    relationship_add = relationship_commands.add_parser(
        "add",
        help="Add a human-defined relationship candidate.",
    )
    relationship_add.add_argument("name", help="Local graph name.")
    relationship_add.add_argument("--from", dest="from_reference", required=True)
    relationship_add.add_argument("--to", dest="to_reference", required=True)
    relationship_add.add_argument("--reason", required=True)
    relationship_add.add_argument("--validated", action="store_true")
    add_format_argument(relationship_add)

    relationship_check = relationship_commands.add_parser(
        "check",
        help="Run one bounded aggregate probe for a selected field pair.",
    )
    relationship_check.add_argument("name", help="Local graph name.")
    relationship_check.add_argument("--from", dest="from_reference", required=True)
    relationship_check.add_argument("--to", dest="to_reference", required=True)
    relationship_check.add_argument("--config", type=Path, required=True)
    relationship_check.add_argument("--row-limit", type=int, default=10_000)
    add_format_argument(relationship_check)

    relationship_discover = relationship_commands.add_parser(
        "discover",
        help="Search a bounded neighborhood around one object for possible joins.",
    )
    relationship_discover.add_argument("name", help="Local graph name.")
    relationship_discover.add_argument("--object", dest="object_reference", required=True)
    relationship_discover.add_argument("--field", dest="field_name")
    relationship_discover.add_argument("--config", type=Path, required=True)
    relationship_discover.add_argument("--max-pairs", type=int, default=20)
    relationship_discover.add_argument("--row-limit", type=int, default=10_000)
    relationship_discover.add_argument("--min-source-coverage", type=float, default=0.85)
    relationship_discover.add_argument("--min-overlap-count", type=int, default=3)
    relationship_discover.add_argument("--min-target-uniqueness", type=float, default=0.9)
    relationship_discover.add_argument("--dry-run", action="store_true")
    relationship_discover.add_argument(
        "--focus",
        help="Restrict candidate pairs to objects reached by this focus.",
    )
    relationship_discover.add_argument(
        "--expand-one-hop",
        action="store_true",
        help="Also include objects connected by one observed foreign-key hop.",
    )
    add_format_argument(relationship_discover)

    relationship_list = relationship_commands.add_parser(
        "list",
        help="List stored human and inferred relationship candidates.",
    )
    relationship_list.add_argument("name", help="Local graph name.")
    add_format_argument(relationship_list)

    for decision, state_label in (("validate", "validated"), ("reject", "rejected")):
        relationship_decision = relationship_commands.add_parser(
            decision,
            help=f"Mark one inferred relationship as {state_label} by a human.",
        )
        relationship_decision.add_argument("name", help="Local graph name.")
        relationship_decision.add_argument("edge_id", help="Relationship candidate ID.")
        relationship_decision.add_argument("--reason", required=True)
        add_format_argument(relationship_decision)


def dispatch(args: argparse.Namespace) -> int | None:
    """Run a parsed `relationship` command; return ``None`` for other commands."""
    if args.command != "relationship":
        return None
    command = args.relationship_command
    handler = _HANDLERS.get(command)
    if handler is not None:
        return handler(args)
    return None


def _render_relationship_profile(
    profile: RelationshipPairProfile,
    *,
    output_format: str,
) -> None:
    if output_format == "json":
        print_json(profile.to_dict())
        return
    pair = profile.pair
    print(
        f"Pair: {pair.from_namespace}.{pair.from_object}.{pair.from_field} -> "
        f"{pair.to_namespace}.{pair.to_object}.{pair.to_field}"
    )
    print(f"Profile row limit: {profile.profile_row_limit}")
    print(f"Overlap count: {profile.overlap_count}")
    print(f"Source coverage: {profile.source_coverage:.1%}")
    print(f"Target coverage: {profile.target_coverage:.1%}")
    print(f"Target uniqueness: {profile.target_uniqueness:.1%}")


def _render_relationship_payload(payload: dict[str, Any], *, output_format: str) -> None:
    if output_format == "json":
        print_json(payload)
        return
    candidates = payload.get("candidates")
    if isinstance(candidates, list):
        print(f"Candidates: {len(candidates)}")
        for candidate in candidates:
            if isinstance(candidate, dict):
                metadata = candidate.get("metadata", {})
                if isinstance(metadata, dict):
                    from_fields = metadata.get("from_fields")
                    to_fields = metadata.get("to_fields")
                    if not isinstance(from_fields, list):
                        from_fields = [metadata.get("from_field")]
                    if not isinstance(to_fields, list):
                        to_fields = [metadata.get("to_field")]
                    print(
                        f"- {metadata.get('from_namespace')}.{metadata.get('from_object')}"
                        f"({', '.join(str(item) for item in from_fields)}) -> "
                        f"{metadata.get('to_namespace')}.{metadata.get('to_object')}"
                        f"({', '.join(str(item) for item in to_fields)}) "
                        f"[{metadata.get('state')}]"
                    )
        if "probed_pairs" in payload:
            print(f"Probed pairs: {payload['probed_pairs']}")
        if payload.get("dry_run"):
            print("Dry run: graph was not changed.")
        elif payload.get("path"):
            print(f"Path: {payload['path']}")
        return
    edge = payload.get("edge")
    if isinstance(edge, dict):
        metadata = edge.get("metadata", {})
        if isinstance(metadata, dict):
            print(f"Relationship: {edge.get('id')}")
            print(f"State: {metadata.get('state')}")
        print(f"Path: {payload.get('path')}")


def _run_add(args: argparse.Namespace) -> int:
    result = add_relationship_use_case(
        args.name,
        from_reference=args.from_reference,
        to_reference=args.to_reference,
        reason=args.reason,
        validated=args.validated,
    )
    payload = {
        "edge": result.edge.to_dict(),
        "graph": result.graph.name,
        "path": str(result.path),
    }
    _render_relationship_payload(payload, output_format=args.format)
    return 0


def _run_check(args: argparse.Namespace) -> int:
    profile = check_relationship_use_case(
        args.name,
        from_reference=args.from_reference,
        to_reference=args.to_reference,
        config_path=args.config,
        row_limit=args.row_limit,
    )
    _render_relationship_profile(profile, output_format=args.format)
    return 0


def _run_discover(args: argparse.Namespace) -> int:
    result = discover_relationships_use_case(
        args.name,
        object_reference=args.object_reference,
        field_name=args.field_name,
        config_path=args.config,
        max_pairs=args.max_pairs,
        row_limit=args.row_limit,
        min_source_coverage=args.min_source_coverage,
        min_overlap_count=args.min_overlap_count,
        min_target_uniqueness=args.min_target_uniqueness,
        persist=not args.dry_run,
        focus_name=args.focus,
        expand_one_hop=args.expand_one_hop,
    )
    payload = {
        "candidates": [edge.to_dict() for edge in result.candidates],
        "dry_run": args.dry_run,
        "graph": result.graph.name,
        "path": str(result.path) if result.path else None,
        "probed_pairs": len(result.profiles),
    }
    _render_relationship_payload(payload, output_format=args.format)
    return 0


def _run_list(args: argparse.Namespace) -> int:
    edges = list_relationships_use_case(args.name)
    payload = {"candidates": [edge.to_dict() for edge in edges], "graph": args.name}
    _render_relationship_payload(payload, output_format=args.format)
    return 0


def _run_decide(args: argparse.Namespace) -> int:
    state = "validated" if args.relationship_command == "validate" else "rejected"
    result = decide_relationship_use_case(
        args.name,
        edge_id=args.edge_id,
        state=state,
        reason=args.reason,
    )
    payload = {
        "edge": result.edge.to_dict(),
        "graph": result.graph.name,
        "path": str(result.path),
    }
    _render_relationship_payload(payload, output_format=args.format)
    return 0


_HANDLERS = {
    "add": _run_add,
    "check": _run_check,
    "discover": _run_discover,
    "list": _run_list,
    "reject": _run_decide,
    "validate": _run_decide,
}
