"""`tarel connector`: run source connectors directly against a configuration file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tarel.cli._args import Subcommands, add_format_argument
from tarel.cli._output import print_json, render_catalog, render_probe
from tarel.connectors.application import (
    check_connector_use_case,
    discover_catalog_use_case,
    probe_connector_use_case,
    profile_connector_use_case,
    sample_connector_use_case,
    scaffold_connector_use_case,
)
from tarel.connectors.contracts import ConnectorCheck, ObjectProfileResult, SampleResult


def register(subcommands: Subcommands) -> None:
    """Add the `connector` command group to the top-level parser."""
    connector = subcommands.add_parser("connector", help="Inspect and run source connectors.")
    connector_commands = connector.add_subparsers(dest="connector_command")

    check = connector_commands.add_parser(
        "check",
        help="Validate a connector and its dependencies.",
    )
    check.add_argument("name", help="Connector name, for example sqlserver.")
    add_format_argument(check)

    probe = connector_commands.add_parser("probe", help="Run a bounded read-only connection probe.")
    probe.add_argument("name", help="Connector name, for example sqlserver.")
    probe.add_argument("--config", type=Path, help="Private TOML configuration file.")
    probe.add_argument("--database", help="Override the configured database.")
    add_format_argument(probe)

    discover = connector_commands.add_parser(
        "discover",
        help="Read schemas, tables, views, and fields from a source.",
    )
    discover.add_argument("name", help="Connector name, for example sqlserver.")
    discover.add_argument("--config", type=Path, help="Private TOML configuration file.")
    discover.add_argument("--database", help="Override the configured database.")
    discover.add_argument(
        "--namespace",
        "--schema",
        dest="namespace",
        help="Limit discovery to one namespace or database schema.",
    )
    add_format_argument(discover)

    scaffold = connector_commands.add_parser(
        "scaffold",
        help="Create an isolated connector candidate for an agent or human.",
    )
    scaffold.add_argument("name", help="New connector name, for example postgres.")
    scaffold.add_argument("--output", type=Path, help="Target directory (default: connector name).")

    sample = connector_commands.add_parser(
        "sample",
        help="Explicitly read a bounded sample from one object.",
    )
    sample.add_argument("name", help="Connector name, for example sqlserver.")
    sample.add_argument("--config", type=Path, required=True, help="Private TOML configuration.")
    sample.add_argument("--database", help="Override the configured database.")
    sample.add_argument("--namespace", "--schema", dest="namespace", required=True)
    sample.add_argument("--object", dest="object_name", required=True)
    sample.add_argument("--limit", type=int, default=3)
    add_format_argument(sample)

    profile = connector_commands.add_parser(
        "profile",
        help="Read bounded aggregate column profiles from one object.",
    )
    profile.add_argument("name", help="Connector name, for example sqlserver.")
    profile.add_argument("--config", type=Path, required=True, help="Private TOML configuration.")
    profile.add_argument("--database", help="Override the configured database.")
    profile.add_argument("--namespace", "--schema", dest="namespace", required=True)
    profile.add_argument("--object", dest="object_name", required=True)
    profile.add_argument("--row-limit", type=int, default=10_000)
    profile.add_argument("--small-domain-limit", type=int, default=20)
    profile.add_argument(
        "--include-values",
        action="store_true",
        help="Explicitly allow values for complete small domains in this ephemeral result.",
    )
    add_format_argument(profile)



def dispatch(args: argparse.Namespace) -> int | None:
    """Run a parsed `connector` command; return ``None`` for other commands."""
    if args.command != "connector":
        return None
    command = args.connector_command
    handler = _HANDLERS.get(command)
    if handler is not None:
        return handler(args)
    return None


def _render_check(result: ConnectorCheck, *, output_format: str) -> None:
    if output_format == "json":
        print_json(result.to_dict())
        return
    print(f"Connector: {result.name}")
    print(f"Status: {'available' if result.available else 'unavailable'}")
    print(f"Capabilities: {', '.join(result.capabilities)}")
    print(f"Permissions: {', '.join(result.permissions)}")
    print(f"Dialect: {result.dialect or ''}")
    if result.references:
        print(f"References: {', '.join(result.references)}")
    if result.missing_dependencies:
        print(f"Missing dependencies: {', '.join(result.missing_dependencies)}")
        print(f"Install: pip install tarel[{result.extra}]")


def _render_sample(result: SampleResult, *, output_format: str) -> None:
    if output_format == "json":
        print_json(result.to_dict())
        return
    print(f"Object: {result.namespace}.{result.object_name}")
    print(f"Rows: {len(result.rows)}")
    print(f"Selected fields: {', '.join(result.selected_fields)}")
    print(f"Omitted fields: {', '.join(result.omitted_fields)}")
    print(f"Ordered by: {', '.join(result.ordered_by) if result.ordered_by else 'unordered'}")
    print(f"Truncated values: {'yes' if result.truncated_values else 'no'}")
    for row in result.rows:
        print(json.dumps(row, ensure_ascii=False, sort_keys=True))


def _render_profile(result: ObjectProfileResult, *, output_format: str) -> None:
    if output_format == "json":
        print_json(result.to_dict())
        return
    print(f"Object: {result.namespace}.{result.object_name}")
    print(f"Rows profiled: {result.rows_profiled}")
    print(f"Complete: {'yes' if result.complete else 'no'}")
    print(f"Ordered by: {', '.join(result.ordered_by)}")
    print(f"Values included: {'yes' if result.includes_values else 'no'}")
    for column in result.columns:
        if column.status != "profiled":
            print(f"{column.name} [{column.data_type}]: omitted ({column.reason})")
            continue
        print(
            f"{column.name} [{column.data_type}]: non-null={column.non_null_count}, "
            f"null={column.null_count}, distinct={column.distinct_count}, "
            f"min={column.min_value!r}, max={column.max_value!r}"
        )
        if column.values:
            rendered = ", ".join(f"{item.value!r} ({item.count})" for item in column.values)
            print(f"  values: {rendered}")


def _run_check(args: argparse.Namespace) -> int:
    result = check_connector_use_case(args.name)
    _render_check(result, output_format=args.format)
    return 0 if result.available else 1


def _run_probe(args: argparse.Namespace) -> int:
    result = probe_connector_use_case(
        args.name,
        config_path=args.config,
        database=args.database,
    )
    render_probe(result, output_format=args.format)
    return 0


def _run_discover(args: argparse.Namespace) -> int:
    result = discover_catalog_use_case(
        args.name,
        config_path=args.config,
        database=args.database,
        namespace=args.namespace,
    )
    render_catalog(result, output_format=args.format)
    return 0


def _run_scaffold(args: argparse.Namespace) -> int:
    result = scaffold_connector_use_case(args.name, output=args.output)
    print(f"Created connector candidate: {result.path}")
    print("Next: read CONNECTOR_TASK.md and implement probe plus discover_catalog.")
    return 0


def _run_sample(args: argparse.Namespace) -> int:
    result = sample_connector_use_case(
        args.name,
        config_path=args.config,
        database=args.database,
        namespace=args.namespace,
        object_name=args.object_name,
        limit=args.limit,
    )
    _render_sample(result, output_format=args.format)
    return 0


def _run_profile(args: argparse.Namespace) -> int:
    result = profile_connector_use_case(
        args.name,
        config_path=args.config,
        database=args.database,
        namespace=args.namespace,
        object_name=args.object_name,
        row_limit=args.row_limit,
        small_domain_limit=args.small_domain_limit,
        include_values=args.include_values,
    )
    _render_profile(result, output_format=args.format)
    return 0


_HANDLERS = {
    "check": _run_check,
    "probe": _run_probe,
    "discover": _run_discover,
    "scaffold": _run_scaffold,
    "sample": _run_sample,
    "profile": _run_profile,
}
