"""Thin public CLI for explicit, metadata-only object families."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tarel.object_families.application import (
    FAMILY_MODES,
    family_summary,
    import_object_family_use_case,
    list_object_families_use_case,
    load_object_family_use_case,
    propose_object_family_use_case,
    resolve_family_members_use_case,
    review_object_family_use_case,
)
from tarel.object_families.contracts import FamilyAttribute, ObjectFamily, ObjectFamilyFailure
from tarel.object_families.proposals_cli import (
    add_family_proposal_commands,
    dispatch_family_proposal,
)


def add_family_commands(subcommands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    family = subcommands.add_parser("family", help="Declare and resolve logical table families.")
    commands = family.add_subparsers(dest="family_command", required=True)
    add_family_proposal_commands(commands)
    propose = commands.add_parser(
        "propose", help="Validate and store an explicit candidate family."
    )
    propose.add_argument("graph")
    propose.add_argument("family_id")
    propose.add_argument("--name", required=True)
    propose.add_argument("--member", action="append", dest="members", required=True)
    propose.add_argument("--grain", action="append", required=True)
    propose.add_argument(
        "--attribute", action="append", default=[], help="JSON metadata attribute."
    )
    propose.add_argument("--producer", default="coding_agent")
    listing = commands.add_parser("list", help="List summaries without member lists.")
    listing.add_argument("graph")
    show = commands.add_parser("show", help="Show one family summary, including freshness.")
    export = commands.add_parser("export", help="Export a complete audit artifact.")
    review = commands.add_parser("review", help="Record a human review at a pinned revision.")
    members = commands.add_parser("members", help="Resolve a bounded page of physical members.")
    for parser in (show, export, review, members):
        parser.add_argument("graph")
        parser.add_argument("family_id")
    review.add_argument("--decision", choices=("approve", "reject"), required=True)
    review.add_argument("--reason", required=True)
    review.add_argument("--revision", required=True)
    members.add_argument("--revision", required=True)
    members.add_argument("--mode", choices=FAMILY_MODES, default="confirmed_only")
    members.add_argument("--offset", type=int, default=0)
    members.add_argument("--limit", type=int, default=50)
    members.add_argument("--where", action="append", default=[], help="Exact attribute NAME=VALUE.")
    members.add_argument("--namespace")
    importing = commands.add_parser("import", help="Import a strict candidate artifact.")
    importing.add_argument("--source", required=True, help="JSON file or '-' for stdin.")
    for parser in (propose, listing, show, export, review, members, importing):
        parser.add_argument("--format", choices=("text", "json"), default="text")


def dispatch_family(args: argparse.Namespace) -> int | None:
    if args.command != "family":
        return None
    proposal_result = dispatch_family_proposal(args)
    if proposal_result is not None:
        return proposal_result
    command = args.family_command
    payload: object
    if command == "propose":
        attributes = tuple(
            FamilyAttribute.from_dict(
                {
                    "prefix": "",
                    "suffix": "",
                    "data_type": "string",
                    **_json_object(raw),
                }
            )
            for raw in args.attribute
        )
        result = propose_object_family_use_case(
            args.graph,
            args.family_id,
            name=args.name,
            members=tuple(args.members),
            grain=tuple(args.grain),
            attributes=attributes,
            producer=args.producer,
        )
        payload = family_summary(result)
    elif command == "list":
        payload = {"graph": args.graph, "families": list(list_object_families_use_case(args.graph))}
    elif command == "show":
        summaries = list_object_families_use_case(args.graph)
        payload = next((item for item in summaries if item["id"] == args.family_id), None)
        if payload is None:
            raise ObjectFamilyFailure("object_family_not_found", "Object family does not exist.")
    elif command == "export":
        payload = load_object_family_use_case(args.graph, args.family_id).to_dict()
    elif command == "review":
        payload = family_summary(
            review_object_family_use_case(
                args.graph,
                args.family_id,
                decision=args.decision,
                reason=args.reason,
                expected_revision=args.revision,
            )
        )
    elif command == "members":
        filters: dict[str, str] = {}
        for value in args.where:
            name, separator, target = value.partition("=")
            if not separator or not name or name in filters:
                raise ObjectFamilyFailure(
                    "invalid_object_family_filter", "Use one NAME=VALUE filter per attribute."
                )
            filters[name] = target
        payload = resolve_family_members_use_case(
            args.graph,
            args.family_id,
            expected_revision=args.revision,
            mode=args.mode,
            offset=args.offset,
            limit=args.limit,
            filters=filters,
            namespace=args.namespace,
        ).to_dict()
    elif command == "import":
        try:
            raw = sys.stdin.read() if args.source == "-" else Path(args.source).read_text("utf-8")
        except (OSError, UnicodeError) as exc:
            raise ObjectFamilyFailure(
                "object_family_source_unreadable", "Could not read the family import document."
            ) from exc
        payload = family_summary(
            import_object_family_use_case(ObjectFamily.from_dict(_json_object(raw)))
        )
    else:
        raise ObjectFamilyFailure("invalid_object_family_command", "Unsupported family command.")
    if args.format == "json" or command == "export":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _render_text(payload)
    return 0


def _render_text(payload: object) -> None:
    if not isinstance(payload, dict):
        return
    if "families" in payload:
        print(f"Graph: {payload['graph']}")
        for summary in payload["families"]:
            _render_text(summary)
    elif "members" in payload:
        print(f"Family: {payload['family_id']} [{payload['usage']}]")
        print(f"Revision: {payload['revision']}")
        print(f"Members: {payload['matched_members']}/{payload['total_members']} in scope")
        for member in payload["members"]:
            print(
                f"- {member['reference']}: {json.dumps(member['attributes'], ensure_ascii=False)}"
            )
        print(f"Next offset: {payload['next_offset']}")
    else:
        print(f"{payload['name']} ({payload['id']}) [{payload['usage']}]")
        print(f"Members: {payload['member_count']}; grain: {', '.join(payload['grain'])}")
        print(f"Revision: {payload['revision']}; stale: {payload.get('stale', False)}")
        print(payload["notice"])


def _json_object(raw: str) -> dict[str, object]:
    try:
        payload = json.loads(raw, object_pairs_hook=_unique_object)
    except ValueError as exc:
        raise ObjectFamilyFailure(
            "invalid_object_family", "Invalid or duplicate-key family JSON."
        ) from exc
    if not isinstance(payload, dict):
        raise ObjectFamilyFailure("invalid_object_family", "Family input must be a JSON object.")
    return payload


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("Duplicate JSON field")
        result[name] = value
    return result
