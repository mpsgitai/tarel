"""`tarel provider`: configure and test structured-generation providers."""

from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path

from tarel.cli._args import Subcommands, add_format_argument
from tarel.cli._output import print_json
from tarel.providers.application import (
    check_provider_use_case,
    configure_provider_use_case,
    list_provider_names_use_case,
    scaffold_provider_use_case,
    test_provider_use_case,
)
from tarel.providers.config import BUILTIN_PROVIDER_ADAPTERS
from tarel.providers.contracts import ProviderCheck, ProviderFailure


def register(subcommands: Subcommands) -> None:
    """Add the `provider` command group to the top-level parser."""
    provider = subcommands.add_parser("provider", help="Configure optional annotation providers.")
    provider_commands = provider.add_subparsers(dest="provider_command")

    provider_list = provider_commands.add_parser("list", help="List supported providers.")
    add_format_argument(provider_list)

    provider_check = provider_commands.add_parser(
        "check",
        help="Show redacted provider configuration status.",
    )
    provider_check.add_argument("name")
    add_format_argument(provider_check)

    provider_configure = provider_commands.add_parser(
        "configure",
        help="Store provider configuration in the private user config.",
    )
    provider_configure.add_argument("name")
    provider_configure.add_argument(
        "--adapter",
        help=(
            "Adapter: openrouter, openai-compatible, or an installed tarel.providers entry point."
        ),
    )
    provider_credentials = provider_configure.add_mutually_exclusive_group()
    provider_credentials.add_argument(
        "--from-env",
        action="store_true",
        help="Read the API key from a supported provider environment variable.",
    )
    provider_credentials.add_argument(
        "--no-api-key",
        action="store_true",
        help="Configure an unauthenticated endpoint, normally a loopback server.",
    )
    provider_configure.add_argument("--model", help="Default provider model.")
    provider_configure.add_argument("--base-url", help="Provider API base URL.")
    provider_configure.add_argument(
        "--reasoning-effort",
        choices=("none", "minimal", "low", "medium", "high", "xhigh"),
        help="Default reasoning mode for this provider profile.",
    )
    provider_configure.add_argument(
        "--structured-mode",
        choices=("json_schema", "tool"),
        help="Structured-output mechanism for OpenAI-compatible endpoints.",
    )

    provider_test = provider_commands.add_parser(
        "test",
        help="Make one small structured-generation provider request.",
    )
    provider_test.add_argument("name")
    provider_test.add_argument("--timeout", type=float, default=120.0)
    add_format_argument(provider_test)

    provider_scaffold = provider_commands.add_parser(
        "scaffold",
        help="Create an isolated provider-adapter candidate for review.",
    )
    provider_scaffold.add_argument("name")
    provider_scaffold.add_argument(
        "--output",
        type=Path,
        help="Target directory (default: .tarel/providers/NAME).",
    )



def dispatch(args: argparse.Namespace) -> int | None:
    """Run a parsed `provider` command; return ``None`` for other commands."""
    if args.command != "provider":
        return None
    command = args.provider_command
    handler = _HANDLERS.get(command)
    if handler is not None:
        return handler(args)
    return None


def _provider_api_key(name: str, *, adapter: str, from_env: bool) -> str:
    if from_env:
        profile_name = name.upper().replace("-", "_")
        candidates = [
            os.getenv(f"TAREL_PROVIDER_{profile_name}_API_KEY"),
            os.getenv("TAREL_PROVIDER_API_KEY"),
        ]
        if adapter == "openrouter":
            candidates.extend(
                [os.getenv("TAREL_OPENROUTER_API_KEY"), os.getenv("OPENROUTER_API_KEY")]
            )
        elif name == "openai":
            candidates.append(os.getenv("OPENAI_API_KEY"))
        value = next((candidate for candidate in candidates if candidate), None)
        if not value:
            raise ProviderFailure(
                "missing_api_key",
                f"No API key for provider profile {name} was found in the environment.",
            )
        return value
    return getpass.getpass(f"API key for provider profile {name}: ").strip()


def _render_provider_checks(
    results: tuple[ProviderCheck, ...],
    *,
    output_format: str,
) -> None:
    if output_format == "json":
        print_json([result.to_dict() for result in results])
        return
    for result in results:
        print(f"Provider: {result.name}")
        print(f"Adapter: {result.adapter or ''}")
        print(f"Status: {'configured' if result.configured else 'not configured'}")
        print(f"Model: {result.model or ''}")
        print(f"Base URL: {result.base_url or ''}")
        print(f"Config: {result.config_path}")


def _run_list(args: argparse.Namespace) -> int:
    results = tuple(
        check_provider_use_case(name) for name in list_provider_names_use_case()
    )
    _render_provider_checks(results, output_format=args.format)
    return 0


def _run_check(args: argparse.Namespace) -> int:
    result = check_provider_use_case(args.name)
    _render_provider_checks((result,), output_format=args.format)
    return 0 if result.configured else 1


def _run_configure(args: argparse.Namespace) -> int:
    adapter = args.adapter or BUILTIN_PROVIDER_ADAPTERS.get(args.name)
    api_key = None
    if args.from_env:
        api_key = _provider_api_key(
            args.name,
            adapter=adapter or "",
            from_env=True,
        )
    elif not args.no_api_key and adapter in {
        "openai-compatible",
        "openrouter",
    }:
        api_key = _provider_api_key(
            args.name,
            adapter=adapter,
            from_env=False,
        )
    path = configure_provider_use_case(
        args.name,
        adapter=adapter,
        api_key=api_key,
        model=args.model,
        base_url=args.base_url,
        reasoning_effort=args.reasoning_effort,
        structured_mode=args.structured_mode,
        allow_no_api_key=args.no_api_key,
    )
    print(f"Configured provider {args.name}: {path}")
    return 0


def _run_test(args: argparse.Namespace) -> int:
    result = test_provider_use_case(args.name, timeout=args.timeout)
    if args.format == "json":
        print_json(result)
    else:
        print(f"Provider: {result['name']}")
        print("Status: ok")
    return 0


def _run_scaffold(args: argparse.Namespace) -> int:
    result = scaffold_provider_use_case(args.name, output=args.output)
    print(f"Created provider adapter candidate: {result.path}")
    print("Next: read PROVIDER_TASK.md, implement, test, and review before installation.")
    return 0


_HANDLERS = {
    "list": _run_list,
    "check": _run_check,
    "configure": _run_configure,
    "test": _run_test,
    "scaffold": _run_scaffold,
}
