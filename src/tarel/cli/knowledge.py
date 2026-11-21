"""`tarel knowledge`: scoped business documents used as annotation evidence."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from tarel.cli._args import Subcommands, add_format_argument
from tarel.cli._output import print_json
from tarel.knowledge.application import (
    add_knowledge_document_use_case,
    list_knowledge_documents_use_case,
    load_knowledge_document_use_case,
    resolve_knowledge_use_case,
)
from tarel.knowledge.contracts import DEFAULT_MAX_KNOWLEDGE_CHARACTERS


def register(subcommands: Subcommands) -> None:
    """Add the `knowledge` command group to the top-level parser."""
    knowledge = subcommands.add_parser(
        "knowledge",
        help="Attach bounded Markdown or text references to annotation scopes.",
    )
    knowledge_commands = knowledge.add_subparsers(dest="knowledge_command")

    knowledge_add = knowledge_commands.add_parser(
        "add",
        help="Import one local reference document into private TAREL state.",
    )
    knowledge_add.add_argument("id")
    knowledge_add.add_argument("path", type=Path)
    knowledge_add.add_argument(
        "--scope",
        required=True,
        help=(
            "global, system:NAME, graph:NAME, schema:GRAPH:NAMESPACE, "
            "or object:GRAPH:OBJECT"
        ),
    )
    knowledge_add.add_argument("--title")
    knowledge_add.add_argument("--state", choices=("draft", "validated"), default="draft")
    knowledge_add.add_argument("--workspace", help="Validate a system scope.")
    knowledge_add.add_argument("--replace", action="store_true")
    add_format_argument(knowledge_add)

    knowledge_list = knowledge_commands.add_parser(
        "list",
        help="List registered knowledge without printing its content.",
    )
    add_format_argument(knowledge_list)

    knowledge_show = knowledge_commands.add_parser(
        "show",
        help="Show one registered document and its content.",
    )
    knowledge_show.add_argument("id")
    add_format_argument(knowledge_show)

    knowledge_resolve = knowledge_commands.add_parser(
        "resolve",
        help="Preview the exact bounded knowledge context for one object.",
    )
    knowledge_resolve.add_argument("graph")
    knowledge_resolve.add_argument("object")
    knowledge_resolve.add_argument("--workspace")
    knowledge_resolve.add_argument("--mode", choices=("none", "scoped"), default="scoped")
    knowledge_resolve.add_argument("--document", action="append", dest="documents")
    knowledge_resolve.add_argument(
        "--max-characters",
        type=int,
        default=DEFAULT_MAX_KNOWLEDGE_CHARACTERS,
    )
    add_format_argument(knowledge_resolve)



def dispatch(args: argparse.Namespace) -> int | None:
    """Run a parsed `knowledge` command; return ``None`` for other commands."""
    if args.command != "knowledge":
        return None
    command = args.knowledge_command
    handler = _HANDLERS.get(command)
    if handler is not None:
        return handler(args)
    return None


def _render_knowledge(payload: dict[str, Any], *, output_format: str) -> None:
    if output_format == "json":
        print_json(payload, ensure_ascii=False)
        return
    documents = payload.get("documents")
    if isinstance(documents, list):
        print(f"Knowledge documents: {len(documents)}")
        for item in documents:
            if not isinstance(item, dict):
                continue
            scope = item.get("scope")
            scope_label = _knowledge_scope_label(scope) if isinstance(scope, dict) else "unknown"
            print(
                f"- {item.get('id')} [{item.get('state')}; {scope_label}; "
                f"{item.get('characters', 0)} chars]"
            )
        omitted = payload.get("omitted")
        if isinstance(omitted, list) and omitted:
            print(f"Omitted by budget: {', '.join(str(item) for item in omitted)}")
        return
    scope = payload.get("scope")
    print(f"Knowledge: {payload.get('id', 'resolved context')}")
    if payload.get("title"):
        print(f"Title: {payload['title']}")
    if isinstance(scope, dict):
        print(f"Scope: {_knowledge_scope_label(scope)}")
    if payload.get("state"):
        print(f"State: {payload['state']}")
    if payload.get("revision"):
        print(f"Revision: {payload['revision']}")
    if payload.get("content"):
        print("\n" + str(payload["content"]))


def _knowledge_scope_label(scope: dict[str, object]) -> str:
    kind = str(scope.get("kind") or "unknown")
    graph = scope.get("graph")
    reference = scope.get("reference")
    workspace = scope.get("workspace")
    if kind == "global":
        return "global"
    if kind == "system" and workspace:
        return f"system:{workspace}:{reference}"
    return f"{kind}:{graph}:{reference}" if graph else f"{kind}:{reference}"


def _run_add(args: argparse.Namespace) -> int:
    result = add_knowledge_document_use_case(
        args.id,
        args.path,
        scope_reference=args.scope,
        title=args.title,
        state=args.state,
        workspace_name=args.workspace,
        replace_existing=args.replace,
    )
    payload = {**result.document.to_dict(include_content=False), "path": str(result.path)}
    _render_knowledge(payload, output_format=args.format)
    return 0


def _run_list(args: argparse.Namespace) -> int:
    documents = list_knowledge_documents_use_case()
    payload = {
        "count": len(documents),
        "documents": [item.to_dict(include_content=False) for item in documents],
    }
    _render_knowledge(payload, output_format=args.format)
    return 0


def _run_show(args: argparse.Namespace) -> int:
    document = load_knowledge_document_use_case(args.id)
    _render_knowledge(document.to_dict(), output_format=args.format)
    return 0


def _run_resolve(args: argparse.Namespace) -> int:
    context = resolve_knowledge_use_case(
        args.graph,
        args.object,
        mode=args.mode,
        document_ids=tuple(args.documents or ()),
        workspace_name=args.workspace,
        max_characters=args.max_characters,
    )
    _render_knowledge(context.to_dict(), output_format=args.format)
    return 0


_HANDLERS = {
    "add": _run_add,
    "list": _run_list,
    "show": _run_show,
    "resolve": _run_resolve,
}
