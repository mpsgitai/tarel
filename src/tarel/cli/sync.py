"""CLI surface for publishing metadata from a site and taking it over centrally."""

from __future__ import annotations

import argparse
from pathlib import Path

from tarel.cli._args import Subcommands, add_format_argument
from tarel.cli._output import print_json
from tarel.runtime import TarelRuntime
from tarel.sync.admin_application import (
    add_trust_use_case,
    inspect_publication_use_case,
    prune_revisions_use_case,
    revoke_key_use_case,
    set_trust_scope_use_case,
    sync_status_use_case,
    trust_key_use_case,
)
from tarel.sync.application import (
    apply_publication_use_case,
    plan_publication_use_case,
    recover_activations_use_case,
)
from tarel.sync.inbox import process_inbox_use_case
from tarel.sync.publish_application import (
    create_stream_use_case,
    init_publisher_use_case,
    publish_use_case,
    update_stream_use_case,
)
from tarel.sync.results import SyncPlan


def register(subcommands: Subcommands) -> None:
    sync = subcommands.add_parser(
        "sync", help="Publish approved metadata from a site and take it over centrally."
    )
    commands = sync.add_subparsers(dest="sync_command", required=True)

    init = commands.add_parser("init", help="Give this site its publisher identity once.")
    stream = commands.add_parser("stream-create", help="Name one export of one graph.")
    stream.add_argument("--graph", required=True)
    update = commands.add_parser(
        "stream-update", help="Replace what a stream approves under a new profile version."
    )
    for parser in (stream, update):
        parser.add_argument("--name", required=True)
        parser.add_argument(
            "--namespace",
            action="append",
            required=True,
            dest="namespaces",
            help="Approve this namespace for export (repeatable).",
        )
        parser.add_argument("--annotations", action="store_true", help="Also publish annotations.")
        parser.add_argument(
            "--technical-descriptions",
            action="store_true",
            help="Also publish descriptions read from the source; these are free text.",
        )
    publish = commands.add_parser("publish", help="Write one .tarelpub file for a stream.")
    publish.add_argument("--stream", required=True, help="Name of the stream to publish.")
    publish.add_argument("--output", required=True, type=Path, help="New .tarelpub file path.")
    publish.add_argument(
        "--observed-at",
        help="State the UTC read time yourself, ending in Z; default is this state's own record.",
    )
    publish.add_argument(
        "--completeness",
        choices=("complete", "partial"),
        help="State this together with --observed-at; a central state refuses partial files.",
    )
    publish.add_argument(
        "--signing-key",
        type=Path,
        help="Private key path, or its .pub file when the key is in an agent. It is not copied.",
    )
    publish.add_argument(
        "--unsigned-dev",
        action="store_true",
        help="Write an unsigned file. For local development only.",
    )
    inspect = commands.add_parser("inspect", help="Verify and describe a file; no state involved.")
    inspect.add_argument("path", type=Path)
    trust = commands.add_parser("trust-add", help="Allow one stream to write one local graph.")
    trust.add_argument("--publisher-id", required=True, help="The publisher allowed to write.")
    trust.add_argument("--stream-id", required=True, help="The one stream this entry allows.")
    trust.add_argument("--graph-id", required=True, help="The source graph that stream carries.")
    trust.add_argument("--local-graph", required=True, help="Central graph this stream may write.")
    trust.add_argument("--workspace", required=True)
    trust.add_argument("--system", required=True, help="Workspace system holding that graph.")
    scope = commands.add_parser("trust-scope", help="Replace what a trusted stream may publish.")
    scope.add_argument("--stream-id", required=True, help="The trusted stream to change.")
    for parser in (trust, scope):
        parser.add_argument(
            "--namespace",
            action="append",
            required=True,
            dest="namespaces",
            help="Allow this namespace (repeatable).",
        )
        parser.add_argument("--allow-annotations", action="store_true", help="Allow annotations.")
        parser.add_argument(
            "--allow-technical-descriptions",
            action="store_true",
            help="Allow free-text descriptions read from the source.",
        )
    key = commands.add_parser("trust-key", help="Accept one more signing key for a publisher.")
    key.add_argument("--publisher-id", required=True, help="The publisher using this key.")
    key.add_argument(
        "--public-key-file", required=True, type=Path, help="OpenSSH Ed25519 public key file."
    )
    key.add_argument("--not-after", help="Refuse this key after this UTC time, ending in Z.")
    revoke = commands.add_parser("revoke-key", help="Stop accepting a signing key in this state.")
    revoke.add_argument("--publisher-id", required=True, help="The publisher of the key.")
    revoke.add_argument("--fingerprint", required=True, help="The key's SHA256 fingerprint.")
    plan = commands.add_parser("plan", help="Show what applying a file would do; changes nothing.")
    plan.add_argument("path", type=Path)
    apply = commands.add_parser("apply", help="Check a file and activate it atomically.")
    apply.add_argument("path", type=Path)
    apply.add_argument("--plan-id", help="Refuse if anything changed since this plan.")
    recover = commands.add_parser(
        "recover", help="Finish activations a stopped process committed but did not complete."
    )
    inbox = commands.add_parser(
        "inbox", help="Run one pass over a directory of delivered files, with the same checks."
    )
    inbox.add_argument("--directory", required=True, type=Path, help="The directory to read.")
    inbox.add_argument(
        "--min-age-seconds",
        type=float,
        default=0,
        help="Leave files younger than this for the next pass.",
    )
    inbox.add_argument(
        "--allow-unsigned-dev",
        action="store_true",
        help="Accept unsigned files. For local development only.",
    )
    for parser in (plan, apply):
        parser.add_argument(
            "--allow-unsigned-dev",
            action="store_true",
            help="Accept an unsigned file. For local development only.",
        )
        parser.add_argument(
            "--accept-history-gap",
            action="store_true",
            help="Accept a file whose history no longer reaches the active publication.",
        )
    status = commands.add_parser("status", help="Show each origin's age, receipt and failures.")
    status.add_argument(
        "--max-age-hours", type=float, help="Mark an origin stale when its source read is older."
    )
    prune = commands.add_parser(
        "prune", help="Delete old revisions of a stream; the active view does not change."
    )
    prune.add_argument("--stream-id", required=True, help="The stream to clean up.")

    for parser in (
        init, stream, update, publish, trust, scope, key, revoke, plan, apply, recover, inbox,
        status, prune,
    ):
        parser.add_argument("--state", type=Path, default=Path(".tarel"), help="TAREL state root.")
    for parser in (
        init, stream, update, publish, inspect, trust, scope, key, revoke, plan, apply, recover,
        inbox, status, prune,
    ):
        add_format_argument(parser)


def dispatch(args: argparse.Namespace) -> int | None:
    if args.command != "sync":
        return None
    command = args.sync_command
    if command == "inspect":
        _render(inspect_publication_use_case(args.path).to_dict(), args.format)
        return 0
    runtime = TarelRuntime.local(args.state)
    if command == "init":
        _render({"publisher_id": init_publisher_use_case(runtime=runtime)}, args.format)
    elif command == "stream-create":
        stream = create_stream_use_case(
            args.name,
            graph=args.graph,
            namespaces=tuple(args.namespaces),
            annotations=args.annotations,
            technical_descriptions=args.technical_descriptions,
            runtime=runtime,
        )
        _render(stream.to_dict(), args.format)
    elif command == "stream-update":
        updated = update_stream_use_case(
            args.name,
            namespaces=tuple(args.namespaces),
            annotations=args.annotations,
            technical_descriptions=args.technical_descriptions,
            runtime=runtime,
        )
        _render(updated.to_dict(), args.format)
    elif command == "recover":
        _render({"finished": list(recover_activations_use_case(runtime=runtime))}, args.format)
    elif command == "inbox":
        passed = process_inbox_use_case(
            args.directory,
            min_age_seconds=args.min_age_seconds,
            allow_unsigned_dev=args.allow_unsigned_dev,
            runtime=runtime,
        )
        _render(passed.to_dict(), args.format)
        return 1 if passed.rejected else 0
    elif command == "prune":
        _render(prune_revisions_use_case(args.stream_id, runtime=runtime).to_dict(), args.format)
    elif command == "publish":
        result = publish_use_case(
            args.stream,
            output=args.output,
            observed_at=args.observed_at,
            completeness=args.completeness,
            signing_key=args.signing_key,
            unsigned_dev=args.unsigned_dev,
            runtime=runtime,
        )
        _render(result.to_dict(), args.format)
    elif command == "trust-add":
        entry = add_trust_use_case(
            publisher_id=args.publisher_id,
            stream_id=args.stream_id,
            graph_id=args.graph_id,
            local_graph=args.local_graph,
            workspace=args.workspace,
            system=args.system,
            namespaces=tuple(args.namespaces),
            annotations=args.allow_annotations,
            technical_descriptions=args.allow_technical_descriptions,
            runtime=runtime,
        )
        _render(entry.to_dict(), args.format)
    elif command == "trust-scope":
        changed = set_trust_scope_use_case(
            args.stream_id,
            namespaces=tuple(args.namespaces),
            annotations=args.allow_annotations,
            technical_descriptions=args.allow_technical_descriptions,
            runtime=runtime,
        )
        _render(changed.to_dict(), args.format)
    elif command == "trust-key":
        added = trust_key_use_case(
            args.publisher_id,
            public_key=args.public_key_file.read_text(encoding="utf-8"),
            not_after=args.not_after,
            runtime=runtime,
        )
        _render(added.to_dict(), args.format)
    elif command == "revoke-key":
        revoked = revoke_key_use_case(args.publisher_id, args.fingerprint, runtime=runtime)
        _render(revoked.to_dict(), args.format)
    elif command == "plan":
        planned = plan_publication_use_case(
            args.path,
            allow_unsigned_dev=args.allow_unsigned_dev,
            accept_history_gap=args.accept_history_gap,
            runtime=runtime,
        )
        if args.format == "json":
            print_json(planned.to_dict(), ensure_ascii=False)
        else:
            _render_plan(planned)
    elif command == "apply":
        applied = apply_publication_use_case(
            args.path,
            plan_id=args.plan_id,
            allow_unsigned_dev=args.allow_unsigned_dev,
            accept_history_gap=args.accept_history_gap,
            runtime=runtime,
        )
        if args.format == "json":
            print_json(applied.to_dict(), ensure_ascii=False)
        else:
            _render_plan(applied.plan)
            print(f"Applied: {'yes' if applied.applied else 'no change'}")
    else:
        statuses = sync_status_use_case(max_age_hours=args.max_age_hours, runtime=runtime)
        streams = [item.to_dict() for item in statuses]
        _render({"streams": streams}, args.format)
    return 0


def _render(payload: dict[str, object], output_format: str) -> None:
    if output_format == "json":
        print_json(payload, ensure_ascii=False)
        return
    for key, value in sorted(payload.items()):
        print(f"{key}: {value}")


def _render_plan(plan: SyncPlan) -> None:
    print(f"Plan: {plan.plan_id}")
    print(f"Action: {plan.action}")
    print(f"Stream: {plan.stream_id} -> graph {plan.local_graph}")
    previous = "none" if plan.previous_sequence is None else str(plan.previous_sequence)
    print(f"Sequence: {previous} -> {plan.sequence}")
    print(
        f"Objects: {len(plan.objects_added)} added, {len(plan.objects_changed)} changed, "
        f"{len(plan.objects_deleted)} deleted in the source, "
        f"{len(plan.objects_withdrawn)} withdrawn by the site"
    )
    for label, items in (
        ("+", plan.objects_added),
        ("~", plan.objects_changed),
        ("-", plan.objects_deleted),
        ("x", plan.objects_withdrawn),
    ):
        for item in items:
            print(f"  {label} {item}")
    print(f"Central claims needing review: {len(plan.affected_claims)}")
    print(f"Central references left without a target: {len(plan.dangling_references)}")
    for warning in plan.warnings:
        print(f"Warning: {warning}")
