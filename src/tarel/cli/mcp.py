"""`tarel mcp`: serve the standardized TAREL MCP metadata interface."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from tarel.cli._args import Subcommands
from tarel.mcp.contracts import VALID_PROFILES, VALID_TRANSPORTS, McpFailure, McpServerConfig


def register(subcommands: Subcommands) -> None:
    """Add the `mcp` command group to the top-level parser."""
    mcp_parser = subcommands.add_parser(
        "mcp",
        help="Serve the standardized TAREL metadata MCP interface.",
    )
    mcp_sub = mcp_parser.add_subparsers(dest="mcp_command")
    serve = mcp_sub.add_parser(
        "serve",
        help="Run the TAREL MCP server bound to an explicit state root.",
    )
    serve.add_argument(
        "--state-root",
        type=Path,
        default=None,
        help=(
            "Explicit TAREL state directory (required unless TAREL_STATE_ROOT is set; "
            "never falls back implicitly to CWD .tarel)."
        ),
    )
    serve.add_argument(
        "--transport",
        choices=tuple(sorted(VALID_TRANSPORTS)),
        default="stdio",
        help="MCP transport protocol (default: stdio).",
    )
    serve.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind host for streamable-http transport (default: 127.0.0.1).",
    )
    serve.add_argument(
        "--port",
        type=int,
        default=8770,
        help="Bind port for streamable-http transport (default: 8770).",
    )
    serve.add_argument(
        "--profile",
        choices=tuple(sorted(VALID_PROFILES)),
        default="meta",
        help="Tool profile: read-only `meta` (default) or `meta-write` (adds draft annotations).",
    )
    serve.add_argument(
        "--workspace",
        default=None,
        help="Optional default workspace name for scoped search, context, and grounding calls.",
    )


def resolve_explicit_state_root(cli_state_root: Path | None) -> Path:
    """Resolve an explicit state root from CLI argument or TAREL_STATE_ROOT env var."""
    if cli_state_root is not None:
        return cli_state_root.expanduser().resolve()
    env_root = os.environ.get("TAREL_STATE_ROOT", "").strip()
    if env_root:
        return Path(env_root).expanduser().resolve()
    raise McpFailure(
        "missing_state_root",
        "An explicit state root is required for `tarel mcp serve`.",
        hint=(
            "Pass `--state-root /path/to/.tarel` or set the `TAREL_STATE_ROOT` "
            "environment variable."
        ),
    )


def dispatch(args: argparse.Namespace) -> int | None:
    """Run a parsed `mcp` command; return ``None`` for other commands."""
    if args.command != "mcp":
        return None
    if getattr(args, "mcp_command", None) != "serve":
        return None

    from tarel.mcp.server import serve_mcp

    state_root = resolve_explicit_state_root(args.state_root)
    config = McpServerConfig(
        state_root=state_root,
        profile=args.profile,
        workspace=args.workspace,
        transport=args.transport,
        host=args.host,
        port=args.port,
    )
    return serve_mcp(config)
