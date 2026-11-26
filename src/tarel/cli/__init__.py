"""The ``tarel`` command line.

Every command group lives in its own module with the same two functions::

    def register(subcommands: Subcommands) -> None   # add the argparse subtree
    def dispatch(args: argparse.Namespace) -> int | None   # run it, or None if not ours

``_COMMAND_MODULES`` lists the groups in the order they appear in ``tarel --help``. Modules are
imported lazily on dispatch so single commands (especially ``tarel version``) do not pay to import
every domain package. Command modules only translate arguments into application use cases and
render the result; they hold no domain logic.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Sequence
from types import ModuleType

from tarel import __version__
from tarel.errors import TarelError

# Order defines `tarel --help`. Each entry is (module_name, (subcommand_names...)).
_COMMAND_SPECS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("package", ("package",)),
    ("bundle", ("bundle",)),
    ("sync", ("sync",)),
    ("demo", ("demo",)),
    ("workspace", ("workspace",)),
    ("source", ("source",)),
    ("connector", ("connector",)),
    ("hub", ("hub",)),
    ("knowledge", ("knowledge",)),
    ("provider", ("provider",)),
    ("model", ("model",)),
    ("index", ("index",)),
    ("graph", ("graph",)),
    ("ui", ("ui",)),
    ("lineage", ("lineage",)),
    ("semantic", ("semantic",)),
    ("entity", ("entity",)),
    ("discovery", ("discovery", "agent")),
    ("topology", ("topology",)),
    ("family", ("family",)),
    ("binding", ("binding",)),
    ("concept", ("concept",)),
    ("logical_join", ("logical-join",)),
    ("reference_mapping", ("reference-mapping",)),
    ("focus", ("focus",)),
    ("search", ("search",)),
    ("context", ("context",)),
    ("grounding", ("grounding",)),
    ("annotation", ("annotation",)),
    ("relationship", ("relationship",)),
    ("retrieval", ("retrieval",)),
)

_COMMAND_TO_MODULE: dict[str, str] = {
    command_name: module_name
    for module_name, command_names in _COMMAND_SPECS
    for command_name in command_names
}

_CONTEXT_SUBCOMMANDS = {"build", "prefix", "brief", "diff", "impact", "expand", "-h", "--help"}


def _load_command_module(module_name: str) -> ModuleType:
    return importlib.import_module(f"tarel.cli.{module_name}")


def _new_root_parser() -> tuple[
    argparse.ArgumentParser,
    argparse._SubParsersAction[argparse.ArgumentParser],
]:
    parser = argparse.ArgumentParser(
        prog="tarel",
        description="Compile trusted analytics context for coding agents.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subcommands = parser.add_subparsers(dest="command")
    subcommands.add_parser("version", help="Print the installed TAREL version.")
    return parser, subcommands


def build_parser() -> argparse.ArgumentParser:
    """Assemble the complete ``tarel`` argument parser."""
    parser, subcommands = _new_root_parser()
    for module_name, _ in _COMMAND_SPECS:
        _load_command_module(module_name).register(subcommands)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one ``tarel`` invocation and return its process exit status."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    # `tarel context GRAPH QUERY` is shorthand for `tarel context build GRAPH QUERY`.
    if arguments[:1] == ["context"] and arguments[1:2] and arguments[1] not in _CONTEXT_SUBCOMMANDS:
        arguments.insert(1, "build")

    if arguments == ["version"]:
        print(__version__)
        return 0
    if arguments == ["--version"]:
        print(f"tarel {__version__}")
        return 0

    first = arguments[0] if arguments else None
    module_name = _COMMAND_TO_MODULE.get(first) if first is not None else None
    if module_name is not None:
        module = _load_command_module(module_name)
        parser, subcommands = _new_root_parser()
        module.register(subcommands)
        args = parser.parse_args(arguments)
        try:
            result: int | None = module.dispatch(args)
            if result is not None:
                return result
        except TarelError as exc:
            print(f"error [{exc.code}]: {exc}", file=sys.stderr)
            return 2
        parser.print_help()
        return 0

    parser = build_parser()
    args = parser.parse_args(arguments)
    if args.command == "version":
        print(__version__)
        return 0
    parser.print_help()
    return 0
