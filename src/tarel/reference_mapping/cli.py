"""Thin CLI adapter for directed reference-mapping candidates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tarel.reference_mapping.application import (
    decide_reference_mapping_candidate_use_case,
    find_reference_mapping_candidates_use_case,
    import_reference_mapping_candidate_use_case,
    list_reference_mapping_candidates_use_case,
    load_reference_mapping_candidate_use_case,
)
from tarel.reference_mapping.contracts import (
    REFERENCE_MAPPING_MODES,
    ReferenceMappingCandidate,
    ReferenceMappingFailure,
)


def add_reference_mapping_commands(
    subcommands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    mapping = subcommands.add_parser(
        "reference-mapping",
        help="Import, retrieve, and review directed reference mappings.",
    )
    commands = mapping.add_subparsers(dest="reference_mapping_command")

    import_command = commands.add_parser(
        "import",
        help="Import one sanitized physical-field mapping candidate.",
    )
    import_command.add_argument("--source", required=True, help="JSON path or '-' for stdin.")
    _output_format(import_command)

    list_command = commands.add_parser("list", help="List mapping candidates and audit history.")
    list_command.add_argument("--graph")
    list_command.add_argument(
        "--state",
        action="append",
        choices=("candidate", "reviewed", "rejected"),
        dest="states",
    )
    _output_format(list_command)

    show = commands.add_parser("show", help="Show one stored reference-mapping candidate.")
    show.add_argument("candidate_id")
    _output_format(show)

    find = commands.add_parser(
        "find",
        help="Offer confirmed mappings or explicitly labelled candidates.",
    )
    find.add_argument("graph")
    find.add_argument("--source-field")
    find.add_argument("--target-field")
    find.add_argument(
        "--mode",
        choices=tuple(sorted(REFERENCE_MAPPING_MODES)),
        default="confirmed_then_candidates",
    )
    _output_format(find)

    review = commands.add_parser(
        "review",
        help="Record one explicit human approval or rejection.",
    )
    review.add_argument("candidate_id")
    review.add_argument("--decision", choices=("approve", "reject"), required=True)
    review.add_argument("--reason", required=True)
    review.add_argument("--revision", required=True)
    _output_format(review)


def dispatch_reference_mapping(args: argparse.Namespace) -> int | None:
    if args.command != "reference-mapping":
        return None
    if args.reference_mapping_command == "import":
        candidate = ReferenceMappingCandidate.from_dict(_read_json(args.source))
        result = import_reference_mapping_candidate_use_case(candidate)
        _render(
            {
                "candidate": result.candidate.to_dict(),
                "changed": result.changed,
                "path": str(result.path),
            },
            output_format=args.output_format,
        )
        return 0
    if args.reference_mapping_command == "list":
        candidates = list_reference_mapping_candidates_use_case(graph_name=args.graph)
        if args.states:
            states = frozenset(args.states)
            candidates = tuple(item for item in candidates if item.state in states)
        _render(
            {
                "candidates": [item.to_dict() for item in candidates],
                "count": len(candidates),
            },
            output_format=args.output_format,
        )
        return 0
    if args.reference_mapping_command == "show":
        _render(
            load_reference_mapping_candidate_use_case(args.candidate_id).to_dict(),
            output_format=args.output_format,
        )
        return 0
    if args.reference_mapping_command == "find":
        matches = find_reference_mapping_candidates_use_case(
            args.graph,
            source=args.source_field,
            target=args.target_field,
            mode=args.mode,
        )
        _render(
            {
                "count": len(matches),
                "graph": args.graph,
                "matches": [item.to_dict() for item in matches],
                "mode": args.mode,
            },
            output_format=args.output_format,
        )
        return 0
    if args.reference_mapping_command == "review":
        result = decide_reference_mapping_candidate_use_case(
            args.candidate_id,
            decision=args.decision,
            reason=args.reason,
            expected_revision=args.revision,
        )
        _render(
            {"candidate": result.candidate.to_dict(), "path": str(result.path)},
            output_format=args.output_format,
        )
        return 0
    return 0


def _read_json(path_value: str) -> dict[str, object]:
    try:
        raw = sys.stdin.read() if path_value == "-" else Path(path_value).read_text("utf-8")
        payload = json.loads(raw, object_pairs_hook=_unique_object)
    except FileNotFoundError as exc:
        raise ReferenceMappingFailure(
            "reference_mapping_source_not_found",
            f"Reference-mapping source not found: {path_value}",
        ) from exc
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ReferenceMappingFailure(
            "invalid_reference_mapping",
            "Could not read reference-mapping candidate JSON.",
        ) from exc
    if not isinstance(payload, dict):
        raise ReferenceMappingFailure(
            "invalid_reference_mapping",
            "Reference-mapping candidate JSON root must be an object.",
        )
    return payload


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def _output_format(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=("text", "json"),
        default="text",
    )


def _render(payload: dict[str, object], *, output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    matches = payload.get("matches")
    if isinstance(matches, list):
        print(f"Reference mappings: {len(matches)}")
        for item in matches:
            if isinstance(item, dict):
                print(
                    f"- {item.get('source')} -> {item.get('target')} "
                    f"[{item.get('usage')}]"
                )
        return
    candidates = payload.get("candidates")
    if isinstance(candidates, list):
        print(f"Reference-mapping candidates: {len(candidates)}")
        for item in candidates:
            if isinstance(item, dict):
                print(f"- {item.get('id')} [{item.get('state')}]")
        return
    candidate = payload.get("candidate")
    if isinstance(candidate, dict):
        print(f"Reference mapping: {candidate.get('id')}")
        print(f"State: {candidate.get('state')}")
        if "path" in payload:
            print(f"Path: {payload['path']}")
        return
    if "contract_version" in payload:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
