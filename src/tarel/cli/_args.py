"""Argument groups shared by several command groups."""

from __future__ import annotations

import argparse
from typing import TypeAlias

from tarel.knowledge.contracts import DEFAULT_MAX_KNOWLEDGE_CHARACTERS
from tarel.search import SearchFailure
from tarel.workspaces.contracts import WorkspaceFailure

Subcommands: TypeAlias = "argparse._SubParsersAction[argparse.ArgumentParser]"
"""The object returned by ``ArgumentParser.add_subparsers``; every command group adds to it."""


def add_annotation_knowledge_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--knowledge",
        choices=("none", "scoped"),
        default="none",
        help="Include no automatic documents (default) or resolve matching scopes.",
    )
    parser.add_argument(
        "--knowledge-document",
        action="append",
        dest="knowledge_documents",
        help="Include one document explicitly; repeat for more.",
    )
    parser.add_argument(
        "--knowledge-workspace",
        help="Workspace used to resolve system-scoped documents.",
    )
    parser.add_argument(
        "--max-knowledge-characters",
        type=int,
        default=DEFAULT_MAX_KNOWLEDGE_CHARACTERS,
    )


def add_annotation_state_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--annotation-state",
        action="append",
        dest="annotation_states",
        choices=("draft", "validated", "rejected", "deferred", "review_required"),
        help="Include semantic annotations in one or more review states.",
    )
    parser.add_argument(
        "--validated-only",
        action="store_true",
        help="Include only human-validated semantic annotations.",
    )


def add_format_argument(parser: argparse.ArgumentParser, *, default: str = "text") -> None:
    """``--format text|json``. Workfile commands, whose output an agent reads, default to JSON."""
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default=default,
        help=f"Output format (default: {default}).",
    )


def add_logical_hint_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--logical-hints",
        choices=("confirmed_only", "confirmed_then_candidates", "include_candidates"),
        help="Include bounded logical hints for selected objects; disabled by default.",
    )


def add_refresh_annotation_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--annotate-new",
        metavar="PROVIDER",
        help="Annotate only object and field gaps introduced by this refresh.",
    )
    parser.add_argument(
        "--annotation-workers",
        type=int,
        default=1,
        help="Parallel provider requests for newly introduced annotation gaps.",
    )
    parser.add_argument(
        "--annotation-model",
        help="Optional model override for the delta annotation batch.",
    )
    parser.add_argument(
        "--annotation-timeout",
        type=float,
        default=120.0,
        help="Provider timeout in seconds for delta annotation requests.",
    )


def add_scope_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--system",
        action="append",
        dest="systems",
        help="Include a system; repeat to include multiple systems.",
    )
    parser.add_argument(
        "--graph",
        action="append",
        dest="graphs",
        help="Limit the scope to a graph; repeat to include multiple graphs.",
    )
    parser.add_argument(
        "--area",
        action="append",
        dest="areas",
        help="Limit to an area (NAME or SYSTEM:NAME); repeat for a union.",
    )
    parser.add_argument(
        "--schema",
        action="append",
        dest="schemas",
        help="Limit to a schema as GRAPH:NAMESPACE; repeat for a union.",
    )
    parser.add_argument(
        "--zone",
        action="append",
        dest="zones",
        help="Limit to a zone (NAME or SYSTEM:NAME); repeat for a union.",
    )


def add_workspace_retrieval_scope_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--workspace",
        metavar="NAME",
        help="Use this workspace's resolved scope instead of a single graph.",
    )
    parser.add_argument("--system", action="append", dest="systems")
    parser.add_argument("--graph", action="append", dest="graphs")
    parser.add_argument("--area", action="append", dest="areas")
    parser.add_argument(
        "--scope-schema",
        action="append",
        dest="schemas",
        help="Workspace schema as GRAPH:NAMESPACE; repeat for a union.",
    )
    parser.add_argument("--zone", action="append", dest="zones")
    parser.add_argument(
        "--scope-object", action="append", dest="scope_objects",
        help="Hard workspace boundary as GRAPH:OBJECT_ID; repeat for a union.",
    )
    parser.add_argument(
        "--focus", action="append", dest="focuses",
        help="Limit a workspace operation to a current saved focus; repeat for a union.",
    )


def graph_scope_object_ids(name: str, references: tuple[str, ...]) -> tuple[str, ...]:
    object_ids: list[str] = []
    for reference in references:
        graph_name, separator, object_id = reference.partition(":")
        if not separator or graph_name != name or not object_id:
            raise SearchFailure(
                "invalid_object_reference",
                f"Graph object scope must use {name}:OBJECT_ID: {reference}",
            )
        object_ids.append(object_id)
    return tuple(object_ids)


def require_graph_or_workspace(args: argparse.Namespace) -> None:
    """Exactly one of the positional graph name and ``--workspace NAME``.

    ``--namespace`` narrows a single graph; a workspace uses ``--scope-schema`` instead.
    """
    if bool(args.name) == bool(args.workspace):
        raise WorkspaceFailure(
            "invalid_scope_target", "Choose exactly one graph name or --workspace NAME."
        )
    if args.workspace and getattr(args, "namespace", None) is not None:
        raise WorkspaceFailure(
            "invalid_workspace_scope",
            "Use --scope-schema GRAPH:NAMESPACE instead of --namespace for a workspace.",
        )
