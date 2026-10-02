"""CLI surface for portable TAREL packages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tarel.packages.application import (
    PackageReport,
    inspect_package,
    pack_workspace,
    plan_workspace,
    unpack_package,
    verify_package,
)
from tarel.packages.contracts import SNAPSHOT_OMISSIONS


def add_package_commands(
    subcommands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    package = subcommands.add_parser(
        "package", help="Plan, pack, inspect, verify, and unpack portable .tarel metadata files."
    )
    commands = package.add_subparsers(dest="package_command", required=True)

    pack = commands.add_parser("pack", help="Create a deterministic package from local state.")
    pack.add_argument(
        "--state", required=True, type=Path, help="TAREL state root containing graphs/."
    )
    pack.add_argument("--workspace", required=True)
    pack.add_argument("--output", required=True, help="New .tarel package path.")
    pack.add_argument("--replace", action="store_true")
    plan = commands.add_parser("plan", help="Show the exact document selection before sharing.")
    plan.add_argument("--state", required=True, type=Path)
    plan.add_argument("--workspace", required=True)
    for parser in (pack, plan):
        parser.add_argument(
            "--lineage", action="append", default=[], help="Include this lineage (repeatable)."
        )
        parser.add_argument(
            "--knowledge",
            action="append",
            default=[],
            help="Include this knowledge document explicitly (repeatable).",
        )

    inspect = commands.add_parser("inspect", help="Read the package manifest without extraction.")
    inspect.add_argument("path")

    verify = commands.add_parser("verify", help="Verify checksums, contracts, and references.")
    verify.add_argument("path")

    unpack = commands.add_parser("unpack", help="Verify and unpack into a new state directory.")
    unpack.add_argument("path")
    unpack.add_argument(
        "--destination", required=True, help="New state root; it must not already exist."
    )

    for parser in (pack, plan, inspect, verify, unpack):
        parser.add_argument("--format", choices=("text", "json"), default="text")


def dispatch_package(args: argparse.Namespace) -> int | None:
    if args.command != "package":
        return None
    if args.package_command == "plan":
        plan = plan_workspace(
            args.state,
            args.workspace,
            lineage_names=tuple(args.lineage),
            knowledge_ids=tuple(args.knowledge),
        )
        if args.format == "json":
            print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(f"Workspace: {plan.workspace}")
            for entry in plan.entries:
                print(f"{entry.path} ({entry.size} bytes)")
            print("Global knowledge and lineage require explicit selection.")
            _render_snapshot_omissions()
        return 0
    if args.package_command == "pack":
        report = pack_workspace(
            args.state,
            args.workspace,
            Path(args.output),
            replace=args.replace,
            lineage_names=tuple(args.lineage),
            knowledge_ids=tuple(args.knowledge),
        )
    elif args.package_command == "inspect":
        report = inspect_package(Path(args.path))
    elif args.package_command == "verify":
        report = verify_package(Path(args.path))
    else:
        report = unpack_package(Path(args.path), Path(args.destination))
    _render(report, output_format=args.format)
    return 0


def _render(report: PackageReport, *, output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
        return
    state = "verified" if report.verified else "manifest only"
    kind_summary = ", ".join(f"{key}={value}" for key, value in report.kinds.items())
    print(f"Package: {report.path}")
    print(f"Workspace: {report.workspace}")
    print(f"Entries: {report.entries} ({kind_summary})")
    print(
        f"Size: {report.package_bytes} bytes package / {report.uncompressed_bytes} bytes metadata"
    )
    print(f"Revision: {report.package_revision}")
    print(f"Status: {state}")
    _render_snapshot_omissions()
    if report.destination is not None:
        print(f"Destination: {report.destination}")


def _render_snapshot_omissions() -> None:
    print(f"Snapshot omissions: {'; '.join(SNAPSHOT_OMISSIONS)} (not included).")
