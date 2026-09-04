"""Thin concept CLI; public SDK and CLI use the same application functions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tarel.semantic_concepts.application import (
    find_semantic_concepts_use_case,
    load_semantic_concepts_use_case,
    review_semantic_concept_use_case,
    save_semantic_concepts_use_case,
)
from tarel.semantic_concepts.contracts import SemanticConceptDocument, SemanticConceptFailure
from tarel.semantic_concepts.store import unique_object
from tarel.topology.endpoint_contracts import LOGICAL_ENDPOINT_MODES, LogicalEndpoint


def add_concept_commands(subcommands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    concept = subcommands.add_parser("concept", help="Import, review and find value-free concepts.")
    commands = concept.add_subparsers(dest="concept_command", required=True)
    importing = commands.add_parser("import", help="Import a strict candidate concept document.")
    importing.add_argument("--source", required=True, help="JSON file or '-' for stdin.")
    importing.add_argument("--expected-revision")
    show = commands.add_parser("show", help="Export one complete concept audit document.")
    show.add_argument("graph")
    review = commands.add_parser("review", help="Record one revision-pinned human concept review.")
    review.add_argument("graph")
    review.add_argument("concept_id")
    review.add_argument("--decision", choices=("approve", "reject"), required=True)
    review.add_argument("--reason", required=True)
    review.add_argument("--revision", required=True)
    find = commands.add_parser("find", help="Find current concepts with dependency review closure.")
    find.add_argument("graph")
    find.add_argument("query", nargs="?")
    find.add_argument("--concept-id", help="Resolve this exact concept ID, without name matching.")
    find.add_argument("--endpoint", help="Strict logical endpoint JSON; no source values.")
    find.add_argument("--mode", choices=sorted(LOGICAL_ENDPOINT_MODES), default="confirmed_only")
    find.add_argument("--limit", type=int, default=20)
    for parser in (importing, show, review, find):
        parser.add_argument("--format", choices=("text", "json"), default="text")


def dispatch_concept(args: argparse.Namespace) -> int | None:
    if args.command != "concept":
        return None
    command = args.concept_command
    if command == "import":
        try:
            raw = sys.stdin.read() if args.source == "-" else Path(args.source).read_text("utf-8")
        except (OSError, UnicodeError) as exc:
            raise SemanticConceptFailure(
                "semantic_concepts_source_not_found",
                "Could not read concept input.",
            ) from exc
        document = SemanticConceptDocument.from_dict(_json_object(raw))
        payload = save_semantic_concepts_use_case(
            document,
            expected_revision=args.expected_revision,
        ).to_dict()
    elif command == "show":
        payload = load_semantic_concepts_use_case(args.graph).to_dict()
    elif command == "review":
        payload = review_semantic_concept_use_case(
            args.graph,
            args.concept_id,
            decision=args.decision,
            reason=args.reason,
            expected_revision=args.revision,
        ).to_dict()
    else:
        endpoint = LogicalEndpoint.from_dict(_json_object(args.endpoint)) if args.endpoint else None
        payload = {
            "graph": args.graph,
            "matches": [
                item.to_dict()
                for item in (
                    find_semantic_concepts_use_case(
                        args.graph,
                        query=args.query,
                        concept_id=args.concept_id,
                        endpoint=endpoint,
                        mode=args.mode,
                        limit=args.limit,
                    )
                )
            ],
        }
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    elif "matches" in payload:
        for match in payload["matches"]:
            print(f"{match['artifact']['id']}\t{match['name']}\t{match['usage']}")
    else:
        print(
            f"{payload['graph_name']}\t{len(payload['concepts'])} concepts\t{payload['revision']}"
        )
    return 0


def _json_object(raw: str) -> dict[str, object]:
    try:
        payload = json.loads(raw, object_pairs_hook=unique_object)
    except ValueError as exc:
        raise SemanticConceptFailure("invalid_semantic_concepts", "Invalid concept JSON.") from exc
    if not isinstance(payload, dict):
        raise SemanticConceptFailure("invalid_semantic_concepts", "Concept JSON must be an object.")
    return payload
