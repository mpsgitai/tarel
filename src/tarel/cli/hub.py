"""`tarel hub`: discover, inspect, suggest, and explicitly install TAREL Hub extensions."""

from __future__ import annotations

import argparse
import shlex
from collections.abc import Callable
from pathlib import Path

from tarel.cli._args import Subcommands, add_format_argument
from tarel.cli._output import print_json
from tarel.hub.application import (
    install_hub_extension_use_case,
    list_hub_extensions_use_case,
    search_hub_extensions_use_case,
    show_hub_extension_use_case,
    suggest_hub_extensions_use_case,
)
from tarel.hub.contracts import HubExtension, HubInstallResult, HubSuggestion


def register(subcommands: Subcommands) -> None:
    """Add the `hub` command group to the top-level parser."""
    hub = subcommands.add_parser(
        "hub",
        help="Discover, inspect, suggest, and install TAREL Hub extensions.",
    )
    hub_commands = hub.add_subparsers(dest="hub_command")

    list_cmd = hub_commands.add_parser(
        "list",
        help="List TAREL Hub extensions and their local installation status.",
    )
    list_cmd.add_argument(
        "--kind",
        choices=("connector", "lineage", "retrieval", "importer"),
        help="Filter extensions by kind.",
    )
    installed_group = list_cmd.add_mutually_exclusive_group()
    installed_group.add_argument(
        "--installed",
        action="store_true",
        help="Show only extensions already installed in this environment.",
    )
    installed_group.add_argument(
        "--available",
        action="store_true",
        help="Show only extensions not yet installed in this environment.",
    )
    list_cmd.add_argument(
        "--include-planned",
        action="store_true",
        help="Include planned (not yet installable) catalog entries.",
    )
    _add_catalog_arguments(list_cmd)
    add_format_argument(list_cmd)

    show_cmd = hub_commands.add_parser(
        "show",
        help="Show full metadata, security notes, and install command for one Hub extension.",
    )
    show_cmd.add_argument(
        "name",
        help=(
            "Extension id, package name, or entry-point name "
            "(for example postgres or connector-postgres)."
        ),
    )
    show_cmd.add_argument(
        "--config-template",
        action="store_true",
        help="Print only the minimal safe configuration or usage template.",
    )
    _add_catalog_arguments(show_cmd)
    add_format_argument(show_cmd)

    search_cmd = hub_commands.add_parser(
        "search",
        help="Search TAREL Hub extensions by name, dialect, capability, or evidence.",
    )
    search_cmd.add_argument("query", help="Search term, for example postgres or lineage.")
    search_cmd.add_argument(
        "--kind",
        choices=("connector", "lineage", "retrieval", "importer"),
        help="Limit search results to one extension kind.",
    )
    search_cmd.add_argument(
        "--include-planned",
        action="store_true",
        help="Include planned catalog entries in search results.",
    )
    _add_catalog_arguments(search_cmd)
    add_format_argument(search_cmd)

    suggest_cmd = hub_commands.add_parser(
        "suggest",
        help="Statically inspect a project directory and suggest matching Hub extensions.",
    )
    suggest_cmd.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Project directory to inspect (defaults to the current working directory).",
    )
    suggest_cmd.add_argument(
        "--hub-url",
        help="Override the Hub catalog JSON URL or local file path.",
    )
    suggest_cmd.add_argument(
        "--online",
        action="store_true",
        help="Fetch the live Hub catalog instead of using the bundled offline snapshot.",
    )
    add_format_argument(suggest_cmd)

    install_cmd = hub_commands.add_parser(
        "install",
        help="Plan or execute installation of one verified TAREL Hub extension.",
    )
    install_cmd.add_argument(
        "name",
        help="Extension id, package name, or entry-point name (for example connector-postgres).",
    )
    install_cmd.add_argument(
        "--extra",
        help="Optional package extra declared by the extension (for example binary).",
    )
    install_cmd.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved install plan without executing pip/uv.",
    )
    install_cmd.add_argument(
        "--yes",
        action="store_true",
        help="Explicitly execute the package installation in the active Python environment.",
    )
    _add_catalog_arguments(install_cmd)
    add_format_argument(install_cmd)


def dispatch(args: argparse.Namespace) -> int | None:
    """Run a parsed `hub` command; return ``None`` for other commands."""
    if args.command != "hub":
        return None
    handler = _HANDLERS.get(args.hub_command)
    if handler is not None:
        return handler(args)
    return None


def _add_catalog_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--hub-url",
        help=(
            "Override the Hub catalog JSON URL or local file path "
            "(default: TAREL_HUB_URL or official Hub)."
        ),
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use the bundled offline Hub catalog snapshot without network access.",
    )


def _handle_list(args: argparse.Namespace) -> int:
    installed_filter: bool | None = None
    if args.installed:
        installed_filter = True
    elif args.available:
        installed_filter = False
    extensions = list_hub_extensions_use_case(
        kind=args.kind,
        installed=installed_filter,
        include_planned=bool(args.include_planned),
        hub_url=args.hub_url,
        offline=bool(args.offline),
    )
    _render_list(extensions, output_format=args.format)
    return 0


def _handle_show(args: argparse.Namespace) -> int:
    ext = show_hub_extension_use_case(
        args.name,
        hub_url=args.hub_url,
        offline=bool(args.offline),
    )
    if args.config_template:
        if args.format == "json":
            print_json(
                {
                    "config_template": ext.config_template,
                    "extension_id": ext.id,
                }
            )
            return 0
        if ext.config_template:
            print(ext.config_template, end="" if ext.config_template.endswith("\n") else "\n")
        else:
            print(f"No configuration template available for {ext.id}.")
        return 0
    _render_show(ext, output_format=args.format)
    return 0


def _handle_search(args: argparse.Namespace) -> int:
    extensions = search_hub_extensions_use_case(
        args.query,
        kind=args.kind,
        include_planned=bool(args.include_planned),
        hub_url=args.hub_url,
        offline=bool(args.offline),
    )
    _render_list(extensions, output_format=args.format)
    return 0


def _handle_suggest(args: argparse.Namespace) -> int:
    suggestions = suggest_hub_extensions_use_case(
        args.path,
        hub_url=args.hub_url,
        offline=not bool(args.online) and not bool(args.hub_url),
    )
    _render_suggestions(suggestions, output_format=args.format)
    return 0


def _handle_install(args: argparse.Namespace) -> int:
    result = install_hub_extension_use_case(
        args.name,
        extra=args.extra,
        dry_run=bool(args.dry_run),
        yes=bool(args.yes),
        hub_url=args.hub_url,
        offline=bool(args.offline),
    )
    _render_install(result, output_format=args.format)
    return 0


def _render_list(extensions: tuple[HubExtension, ...], *, output_format: str) -> None:
    if output_format == "json":
        print_json({"extensions": [item.to_dict() for item in extensions]})
        return
    if not extensions:
        print("Hub extensions: none")
        return
    print(f"Hub extensions: {len(extensions)}")
    for ext in extensions:
        state = "installed" if ext.installed else "available"
        compat = "" if ext.compatible else " [incompatible]"
        extras = f" extras=[{','.join(ext.extras)}]" if ext.extras else ""
        print(f"- {ext.id} ({ext.kind}, {ext.status}): {state}{compat}{extras}")
        if not ext.installed and ext.recommended_cli_install:
            print(f"  install: {ext.recommended_cli_install}")


def _render_show(ext: HubExtension, *, output_format: str) -> None:
    if output_format == "json":
        print_json(ext.to_dict())
        return
    print(f"Extension: {ext.id}")
    print(f"Kind: {ext.kind}")
    print(f"Status: {ext.status}")
    print(f"Installed: {'yes' if ext.installed else 'no'}")
    print(f"Host compatible: {'yes' if ext.compatible else 'no'}")
    if ext.package:
        print(f"Package: {ext.package}")
    if ext.entry_points:
        eps = ", ".join(f"{ep.group}:{ep.name}" for ep in ext.entry_points)
        print(f"Entry points: {eps}")
    if ext.dependencies:
        print(f"Dependencies: {', '.join(ext.dependencies)}")
    if ext.extras:
        print(f"Extras: {', '.join(ext.extras)}")
    if ext.license:
        print(f"License: {ext.license}")
    if ext.real_source_evidence:
        print(f"Evidence: {ext.real_source_evidence}")
    if ext.recommended_cli_install:
        print(f"CLI install: {ext.recommended_cli_install}")
    if ext.config_template:
        print("Config template:")
        for line in ext.config_template.rstrip().splitlines():
            print(f"  {line}")


def _render_suggestions(suggestions: tuple[HubSuggestion, ...], *, output_format: str) -> None:
    if output_format == "json":
        print_json({"suggestions": [item.to_dict() for item in suggestions]})
        return
    if not suggestions:
        print("Hub suggestions: none")
        return
    print(f"Hub suggestions: {len(suggestions)}")
    for item in suggestions:
        state = "installed" if item.installed else "not installed"
        print(f"- {item.extension_id} ({item.kind}, {item.confidence} confidence, {state})")
        for reason in item.reasons:
            print(f"  reason: {reason}")
        if not item.installed and item.install_command:
            print(f"  install: {item.install_command}")


def _render_install(result: HubInstallResult, *, output_format: str) -> None:
    if output_format == "json":
        print_json(result.to_dict())
        return
    cmd_str = shlex.join(result.command)
    print(f"Extension: {result.extension_id}")
    if result.package:
        print(f"Package: {result.package}")
    if result.extra:
        print(f"Extra: {result.extra}")
    if result.dependencies:
        print(f"Dependencies: {', '.join(result.dependencies)}")
    if result.license:
        print(f"License: {result.license}")
    print(f"Command: {cmd_str}")
    if result.dry_run:
        print("Status: planned (pass --yes to execute installation)")
        return
    print(f"Status: installed (verified={'yes' if result.verified else 'no'})")


_HANDLERS: dict[str | None, Callable[[argparse.Namespace], int]] = {
    "install": _handle_install,
    "list": _handle_list,
    "search": _handle_search,
    "show": _handle_show,
    "suggest": _handle_suggest,
}
