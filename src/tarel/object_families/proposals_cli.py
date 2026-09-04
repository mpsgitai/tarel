"""Small opt-in CLI adapters for the metadata-only family proposal runner."""

from __future__ import annotations

import argparse
import json

from tarel.object_families.proposals import (
    load_family_proposals_use_case,
    plan_family_proposals_use_case,
    run_family_proposals_use_case,
)


def add_family_proposal_commands(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    plan = commands.add_parser("plan", help="Plan bounded LLM family suggestions from schema only.")
    plan.add_argument("graph")
    plan.add_argument("run_id")
    plan.add_argument("--provider", required=True)
    plan.add_argument("--model")
    plan.add_argument("--objects-per-batch", type=int, default=50)
    plan.add_argument("--max-input-chars", type=int, default=40_000)
    plan.add_argument("--max-objects", type=int, default=1_000)
    run = commands.add_parser("run", help="Generate unreviewed family candidates; never read rows.")
    run.add_argument("run_id")
    run.add_argument("--workers", type=int, default=1)
    run.add_argument("--resume", action="store_true")
    run.add_argument("--timeout", type=float, default=120.0)
    show = commands.add_parser("run-show", help="Inspect aggregate proposal progress and failures.")
    show.add_argument("run_id")
    for parser in (plan, run, show):
        parser.add_argument("--format", choices=("text", "json"), default="text")


def dispatch_family_proposal(args: argparse.Namespace) -> int | None:
    if args.command != "family":
        return None
    if args.family_command == "plan":
        result = plan_family_proposals_use_case(
            args.graph,
            args.run_id,
            provider_name=args.provider,
            model=args.model,
            objects_per_batch=args.objects_per_batch,
            max_input_chars=args.max_input_chars,
            max_objects=args.max_objects,
        )
    elif args.family_command == "run":
        result = run_family_proposals_use_case(
            args.run_id,
            workers=args.workers,
            resume=args.resume,
            timeout=args.timeout,
        )
    elif args.family_command == "run-show":
        result = load_family_proposals_use_case(args.run_id)
    else:
        return None
    payload = result.to_dict()
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Family proposal run: {result.id} [{result.status}]")
        print(
            f"Objects: {payload['planned_objects']}/{result.total_objects}; "
            f"saved unreviewed candidates: {payload['saved_candidates']}"
        )
        print(f"Omissions: {json.dumps(dict(result.omissions), sort_keys=True)}")
        for index, batch in enumerate(result.batches, start=1):
            failures = [item.error_code for item in batch.outcomes if item.error_code]
            print(
                f"Batch {index}: {batch.status}; unassigned={batch.unassigned_count}; "
                f"errors={json.dumps([batch.error_code] if batch.error_code else failures)}"
            )
    return 2 if args.family_command == "run" and result.status != "completed" else 0
