"""CLI adapter for metadata expansion; private handle contents come only from stdin."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tarel.context_packets import load_context_packet
from tarel.expansion.application import expand_context_use_case
from tarel.expansion.contracts import ContextExpansionFailure, ExpansionInput, ExpansionTarget


def add_expansion_command(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = commands.add_parser(
        "expand", help="Expand pinned metadata using an existing context scope."
    )
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument(
        "--requests", required=True, help="Typed target JSON array, file or '-' for stdin."
    )
    parser.add_argument(
        "--inputs-stdin", action="store_true", help="Private handle values, never saved."
    )
    parser.add_argument(
        "--mode", choices=("confirmed_only", "include_candidates"), default="confirmed_only"
    )
    parser.add_argument("--max-characters", type=int, default=24_000)
    parser.add_argument("--format", choices=("json", "text"), default="json")


def dispatch_expansion(args: argparse.Namespace) -> int | None:
    if args.command != "context" or args.context_command != "expand":
        return None
    if args.inputs_stdin and args.requests == "-":
        raise ContextExpansionFailure(
            "invalid_expansion_stdin", "Use a request file with private stdin inputs."
        )
    targets = _read(args.requests)
    if not isinstance(targets, list):
        raise ContextExpansionFailure("invalid_context_expansion", "Requests must be a JSON array.")
    inputs = _read("-") if args.inputs_stdin else {}
    if not isinstance(inputs, dict):
        raise ContextExpansionFailure(
            "invalid_context_expansion", "Inputs must map handles to selections."
        )
    result = expand_context_use_case(
        load_context_packet(args.packet),
        tuple(ExpansionTarget.from_dict(item) for item in targets),
        inputs={key: ExpansionInput.from_dict(value) for key, value in inputs.items()},
        mode=args.mode,
        max_characters=args.max_characters,
    )
    if args.format == "json":
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Context expansion: {'partial' if result.omissions else 'completed'}; "
              f"{len(result.items)} metadata items")
        for item in result.items:
            print(f"- {item.target.graph}:{item.target.id} [{item.target.kind}; {item.usage}]")
        for index, code in result.omissions:
            print(f"- target {index}: omitted ({code})")
    return 1 if result.omissions else 0


def _read(source: str) -> object:
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    try:
        text = sys.stdin.read(2_000_001) if source == "-" else Path(source).read_text("utf-8")
        if len(text) > 2_000_000:
            raise ValueError("Input too large")
        return json.loads(text, object_pairs_hook=unique)
    except (ValueError, OSError) as exc:
        raise ContextExpansionFailure(
            "invalid_expansion_input", "Cannot read bounded expansion JSON."
        ) from exc
