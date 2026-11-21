"""`tarel demo`: create the deterministic retail demo source."""

from __future__ import annotations

import argparse
from pathlib import Path

from tarel.cli._args import Subcommands, add_format_argument
from tarel.cli._output import print_json
from tarel.demo import create_demo_use_case


def register(subcommands: Subcommands) -> None:
    """Add the `demo` command group to the top-level parser."""
    demo = subcommands.add_parser(
        "demo",
        help="Create deterministic local sources for connector and graph walkthroughs.",
    )
    demo_commands = demo.add_subparsers(dest="demo_command")
    demo_create = demo_commands.add_parser(
        "create",
        help="Create a local demo source and its private connector configuration.",
    )
    demo_create.add_argument("name", choices=("retail-dwh",))
    demo_create.add_argument("--path", type=Path, help="SQLite target path.")
    demo_create.add_argument("--version", type=int, choices=(1, 2), default=1)
    demo_create.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing demo database and configuration.",
    )
    add_format_argument(demo_create)



def dispatch(args: argparse.Namespace) -> int | None:
    """Run a parsed `demo` command; return ``None`` for other commands."""
    if args.command != "demo":
        return None
    command = args.demo_command
    if command == "create":
        result = create_demo_use_case(
            args.name,
            path=args.path,
            version=args.version,
            force=args.force,
        )
        if args.format == "json":
            print_json(result.to_dict())
        else:
            print(f"Created demo: {result.name} v{result.version}")
            print(f"Database: {result.database_path}")
            print(f"Connector config: {result.config_path}")
            print(f"Next: tarel connector probe sqlite --config {result.config_path}")
        return 0

    return None
