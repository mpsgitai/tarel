"""Thin CLI adapters for discovery runs and coding-agent setup."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tarel.agents import setup_agent_skill_use_case
from tarel.discovery.application import (
    advise_discovery_run_use_case,
    find_discovery_candidates_use_case,
    list_discovery_runs_use_case,
    load_discovery_run_use_case,
    next_discovery_task_use_case,
    promote_discovery_candidates_use_case,
    start_discovery_run_use_case,
    submit_discovery_step_use_case,
)
from tarel.discovery.contracts import DISCOVERY_ACTIONS, DISCOVERY_ACTORS, DiscoveryFailure

_PRESETS = {
    "quick": (12, 8),
    "balanced": (40, 20),
    "deep": (160, 60),
}


def add_discovery_commands(
    subcommands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    discovery = subcommands.add_parser(
        "discovery", help="Run optional, resumable join or entity discovery loops."
    )
    commands = discovery.add_subparsers(dest="discovery_command")

    start = commands.add_parser("start", help="Start one bounded discovery run.")
    start.add_argument("kind", choices=("joins", "entities"))
    start.add_argument("--graph", required=True)
    start.add_argument("--source", action="append", dest="sources")
    start.add_argument("--question")
    start.add_argument("--preset", choices=tuple(_PRESETS), default="balanced")
    start.add_argument("--probe-budget", type=int)
    start.add_argument("--candidate-budget", type=int)
    start.add_argument("--advisor-provider")
    start.add_argument("--id", dest="run_id")
    _format(start)

    next_task = commands.add_parser("next", help="Get the current bounded agent task.")
    next_task.add_argument("run_id")
    _format(next_task)

    submit = commands.add_parser("submit", help="Submit one structured discovery action.")
    submit.add_argument("run_id")
    submit.add_argument("--expected-revision", required=True)
    submit.add_argument("--actor", choices=tuple(sorted(DISCOVERY_ACTORS)), default="coding_agent")
    submit.add_argument("--action", choices=tuple(sorted(DISCOVERY_ACTIONS)), required=True)
    submit.add_argument("--source", required=True, help="Action JSON path or '-' for stdin.")
    _format(submit)

    advise = commands.add_parser(
        "advise", help="Ask the configured provider for metadata-only hypotheses."
    )
    advise.add_argument("run_id")
    advise.add_argument("--expected-revision", required=True)
    advise.add_argument("--count", type=int, default=3)
    advise.add_argument("--model")
    advise.add_argument("--timeout", type=float, default=120.0)
    _format(advise)

    promote = commands.add_parser(
        "promote",
        help="Promote selected joins or one entity match into the corresponding review store.",
    )
    promote.add_argument("run_id")
    promote.add_argument(
        "--candidate", action="append", required=True, dest="candidate_ids"
    )
    promote.add_argument("--reason", required=True)
    _format(promote)

    show = commands.add_parser("show", help="Show one complete sanitized run document.")
    show.add_argument("run_id")
    _format(show)

    list_command = commands.add_parser("list", help="List stored discovery runs.")
    list_command.add_argument("--graph")
    list_command.add_argument(
        "--kind", choices=("join_discovery", "entity_matching")
    )
    _format(list_command)

    find = commands.add_parser(
        "find", help="Retrieve selected or explicitly exploratory discovery candidates."
    )
    find.add_argument("--graph")
    find.add_argument("--kind", choices=("join_discovery", "entity_matching"))
    find.add_argument("--include-exploratory", action="store_true")
    find.add_argument("--query")
    find.add_argument("--limit", type=int, default=20)
    _format(find)

    agent = subcommands.add_parser("agent", help="Install optional coding-agent resources.")
    agent_commands = agent.add_subparsers(dest="agent_command")
    setup = agent_commands.add_parser("setup", help="Install the TAREL discovery skill.")
    setup.add_argument("agent", choices=("codex",))
    setup.add_argument("--target", type=Path, default=Path.cwd())
    setup.add_argument("--force", action="store_true")
    _format(setup)


def dispatch_discovery(args: argparse.Namespace) -> int | None:
    if args.command == "agent" and args.agent_command == "setup":
        result = setup_agent_skill_use_case(
            args.agent, target=args.target, force=args.force
        )
        _render(
            {"agent": result.agent, "changed": result.changed, "path": str(result.path)},
            output_format=args.output_format,
        )
        return 0
    if args.command != "discovery":
        return None
    if args.discovery_command == "start":
        preset_probe, preset_candidate = _PRESETS[args.preset]
        result = start_discovery_run_use_case(
            "join_discovery" if args.kind == "joins" else "entity_matching",
            graph_name=args.graph,
            source_names=tuple(args.sources or ()),
            question=args.question,
            probe_budget=args.probe_budget or preset_probe,
            candidate_budget=args.candidate_budget or preset_candidate,
            advisor_provider=args.advisor_provider,
            run_id=args.run_id,
        )
        _render(
            {"path": str(result.path), "run": result.run.to_dict()},
            output_format=args.output_format,
        )
        return 0
    if args.discovery_command == "next":
        _render(
            next_discovery_task_use_case(args.run_id).to_dict(),
            output_format=args.output_format,
        )
        return 0
    if args.discovery_command == "submit":
        result = submit_discovery_step_use_case(
            args.run_id,
            expected_revision=args.expected_revision,
            actor=args.actor,
            action=args.action,
            payload=_read_json(args.source),
        )
        _render(
            {"path": str(result.path), "run": result.run.to_dict()},
            output_format=args.output_format,
        )
        return 0
    if args.discovery_command == "advise":
        result = advise_discovery_run_use_case(
            args.run_id,
            expected_revision=args.expected_revision,
            count=args.count,
            model=args.model,
            timeout=args.timeout,
        )
        _render(
            {
                "path": str(result.path),
                "proposed_count": result.proposed_count,
                "provider": result.provider,
                "run": result.run.to_dict(),
            },
            output_format=args.output_format,
        )
        return 0
    if args.discovery_command == "promote":
        result = promote_discovery_candidates_use_case(
            args.run_id,
            candidate_ids=tuple(args.candidate_ids),
            reason=args.reason,
        )
        _render(
            {
                "edges": [edge.to_dict() for edge in result.edges],
                "entity_candidates": [
                    candidate.to_dict()
                    for candidate in result.entity_candidates
                ],
                "graph": result.graph.name,
                "path": str(result.path),
                "run_id": result.run.id,
            },
            output_format=args.output_format,
        )
        return 0
    if args.discovery_command == "show":
        _render(
            load_discovery_run_use_case(args.run_id).to_dict(),
            output_format=args.output_format,
        )
        return 0
    if args.discovery_command == "list":
        runs = list_discovery_runs_use_case(graph_name=args.graph, kind=args.kind)
        _render(
            {"count": len(runs), "runs": [run.to_dict() for run in runs]},
            output_format=args.output_format,
        )
        return 0
    if args.discovery_command == "find":
        matches = find_discovery_candidates_use_case(
            graph_name=args.graph,
            kind=args.kind,
            include_exploratory=args.include_exploratory,
            query=args.query,
            limit=args.limit,
        )
        _render(
            {"count": len(matches), "matches": [item.to_dict() for item in matches]},
            output_format=args.output_format,
        )
        return 0
    return 0


def _read_json(path_value: str) -> dict[str, object]:
    try:
        raw = sys.stdin.read() if path_value == "-" else Path(path_value).read_text("utf-8")
        payload = json.loads(raw)
    except FileNotFoundError as exc:
        raise DiscoveryFailure(
            "discovery_source_not_found", f"Discovery action source not found: {path_value}"
        ) from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DiscoveryFailure(
            "invalid_discovery", "Could not read discovery action JSON."
        ) from exc
    if not isinstance(payload, dict):
        raise DiscoveryFailure(
            "invalid_discovery", "Discovery action JSON root must be an object."
        )
    return payload


def _format(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--format", dest="output_format", choices=("text", "json"), default="text"
    )


def _render(payload: dict[str, object], *, output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    run = payload.get("run")
    if isinstance(run, dict):
        print(f"Discovery run: {run.get('id')}")
        print(f"Kind: {run.get('kind')}")
        print(f"Status: {run.get('status')}")
        print(f"Revision: {run.get('revision')}")
        if payload.get("path"):
            print(f"Path: {payload['path']}")
        return
    matches = payload.get("matches")
    if isinstance(matches, list):
        print(f"Discovery candidates: {len(matches)}")
        for item in matches:
            if isinstance(item, dict) and isinstance(item.get("candidate"), dict):
                candidate = item["candidate"]
                print(f"- {candidate.get('id')} [{candidate.get('state')}; {item.get('usage')}]")
        return
    runs = payload.get("runs")
    if isinstance(runs, list):
        print(f"Discovery runs: {len(runs)}")
        for item in runs:
            if isinstance(item, dict):
                print(f"- {item.get('id')} [{item.get('kind')}; {item.get('status')}]")
        return
    if "allowed_actions" in payload:
        print(f"Discovery run: {payload.get('run_id')}")
        print(f"Goal: {payload.get('goal')}")
        print(f"Allowed actions: {', '.join(payload.get('allowed_actions', []))}")
        print(f"Raw sample access: {payload.get('raw_sample_access')}")
        hints = payload.get("field_hints")
        if isinstance(hints, list) and hints:
            print("Suggested field pairs:")
            for hint in hints:
                if isinstance(hint, dict):
                    print(
                        f"- {hint.get('source_field')} -> "
                        f"{hint.get('target_field')} "
                        f"[shared: {hint.get('shared_tokens')}]"
                    )
        ladder = payload.get("probe_ladder")
        if isinstance(ladder, list) and ladder:
            print("Probe ladder:")
            for step in ladder:
                if isinstance(step, dict):
                    print(f"- {step.get('code')}: {step.get('purpose')}")
        print(f"Revision: {payload.get('revision')}")
        return
    if "agent" in payload:
        print(f"Installed TAREL discovery skill for {payload['agent']}: {payload['path']}")
        return
    promoted = payload.get("edges")
    entity_candidates = payload.get("entity_candidates")
    if isinstance(promoted, list) and isinstance(entity_candidates, list):
        if entity_candidates:
            print(f"Promoted entity candidates: {len(entity_candidates)}")
            print(f"Graph: {payload.get('graph')}")
            for candidate in entity_candidates:
                if isinstance(candidate, dict):
                    quality = candidate.get("quality")
                    rating = (
                        quality.get("rating")
                        if isinstance(quality, dict)
                        else "unknown"
                    )
                    print(
                        f"- {candidate.get('id')} "
                        f"[{candidate.get('state')}; quality={rating}]"
                    )
            print(f"Path: {payload.get('path')}")
            return
        print(f"Promoted discovery candidates: {len(promoted)}")
        print(f"Graph: {payload.get('graph')}")
        for edge in promoted:
            if not isinstance(edge, dict):
                continue
            metadata = edge.get("metadata")
            if not isinstance(metadata, dict):
                continue
            print(
                f"- {metadata.get('from_namespace')}.{metadata.get('from_object')}"
                f"({', '.join(metadata.get('from_fields', []))}) -> "
                f"{metadata.get('to_namespace')}.{metadata.get('to_object')}"
                f"({', '.join(metadata.get('to_fields', []))}) [draft]"
            )
        print(f"Path: {payload.get('path')}")
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
