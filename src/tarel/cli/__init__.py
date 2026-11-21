"""The ``tarel`` command line.

Every command group lives in its own module with the same two functions::

    def register(subcommands: Subcommands) -> None   # add the argparse subtree
    def dispatch(args: argparse.Namespace) -> int | None   # run it, or None if not ours

``COMMANDS`` lists the groups in the order they appear in ``tarel --help``. To add a group,
write a module with that shape and append it here. Command modules only translate arguments
into application use cases and render the result; they hold no domain logic.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from tarel import __version__
from tarel.cli import (
    annotation,
    binding,
    concept,
    connector,
    context,
    demo,
    discovery,
    entity,
    family,
    focus,
    graph,
    grounding,
    index,
    knowledge,
    lineage,
    logical_join,
    model,
    package,
    provider,
    reference_mapping,
    relationship,
    retrieval,
    search,
    semantic,
    source,
    sync,
    topology,
    ui,
    workspace,
)
from tarel.errors import TarelError

COMMANDS = (
    package,
    sync,
    demo,
    workspace,
    source,
    connector,
    knowledge,
    provider,
    model,
    index,
    graph,
    ui,
    lineage,
    semantic,
    entity,
    discovery,
    topology,
    family,
    binding,
    concept,
    logical_join,
    reference_mapping,
    focus,
    search,
    context,
    grounding,
    annotation,
    relationship,
    retrieval,
)

_CONTEXT_SUBCOMMANDS = {"build", "prefix", "brief", "diff", "impact", "expand", "-h", "--help"}


def build_parser() -> argparse.ArgumentParser:
    """Assemble the complete ``tarel`` argument parser."""
    parser = argparse.ArgumentParser(
        prog="tarel",
        description="Compile trusted analytics context for coding agents.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subcommands = parser.add_subparsers(dest="command")
    subcommands.add_parser("version", help="Print the installed TAREL version.")
    for command in COMMANDS:
        command.register(subcommands)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one ``tarel`` invocation and return its process exit status."""
    parser = build_parser()
    arguments = list(sys.argv[1:] if argv is None else argv)
    # `tarel context GRAPH QUERY` is shorthand for `tarel context build GRAPH QUERY`.
    if arguments[:1] == ["context"] and arguments[1:2] and arguments[1] not in _CONTEXT_SUBCOMMANDS:
        arguments.insert(1, "build")
    args = parser.parse_args(arguments)

    if args.command == "version":
        print(__version__)
        return 0
    try:
        for command in COMMANDS:
            result = command.dispatch(args)
            if result is not None:
                return result
    except TarelError as exc:
        print(f"error [{exc.code}]: {exc}", file=sys.stderr)
        return 2
    parser.print_help()
    return 0
