"""`tarel index`: build and inspect local retrieval indexes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tarel.cli._args import (
    Subcommands,
    add_annotation_state_arguments,
    add_format_argument,
    add_scope_arguments,
    require_graph_or_workspace,
)
from tarel.cli._output import print_json
from tarel.retrieval.application import (
    build_retrieval_index_use_case,
    build_retrieval_workspace_indexes_use_case,
    retrieval_index_status_use_case,
    retrieval_workspace_status_use_case,
)


def register(subcommands: Subcommands) -> None:
    """Add the `index` command group to the top-level parser."""
    index = subcommands.add_parser("index", help="Build and inspect local retrieval indexes.")
    index_commands = index.add_subparsers(dest="index_command")

    index_build = index_commands.add_parser(
        "build",
        help="Embed safe graph metadata into a rebuildable local SQLite index.",
    )
    index_build.add_argument("name", nargs="?", help="Local graph name.")
    index_build.add_argument("--workspace", help="Build pending graph indexes in a workspace.")
    add_scope_arguments(index_build)
    index_build.add_argument("--model", type=Path, dest="model_path")
    index_build.add_argument(
        "--batch-size",
        type=int,
        default=16,
        help="Documents per index progress batch; llama.cpp decodes each document separately.",
    )
    index_build.add_argument("--threads", type=int, dest="n_threads")
    index_build.add_argument(
        "--max-graphs", type=int, default=8,
        help="Maximum pending workspace graphs to update in one run (default: 8).",
    )
    index_build.add_argument(
        "--resume",
        action="store_true",
        help="Checkpoint completed embedding batches and resume a matching interrupted build.",
    )
    add_annotation_state_arguments(index_build)
    add_format_argument(index_build)

    index_status = index_commands.add_parser("status", help="Inspect one retrieval index.")
    index_status.add_argument("name", nargs="?", help="Local graph name.")
    index_status.add_argument("--workspace", help="Inspect index coverage for a workspace.")
    add_scope_arguments(index_status)
    add_annotation_state_arguments(index_status)
    add_format_argument(index_status)



def dispatch(args: argparse.Namespace) -> int | None:
    """Run a parsed `index` command; return ``None`` for other commands."""
    if args.command != "index":
        return None
    command = args.index_command
    handler = _HANDLERS.get(command)
    if handler is not None:
        return handler(args)
    return None


def _index_build_progress(completed: int, total: int, phase: str) -> None:
    if phase == "embedding":
        print(f"Indexing embeddings: {completed}/{total}", file=sys.stderr)
    elif phase == "writing":
        print("Writing retrieval index...", file=sys.stderr)
    elif phase == "ready":
        print("Retrieval index ready.", file=sys.stderr)
    elif phase == "resuming":
        print(f"Resuming retrieval index: {completed}/{total} already embedded", file=sys.stderr)
    elif phase == "reusing":
        print(f"Reusing {total} unchanged retrieval documents.", file=sys.stderr)



def _run_build(args: argparse.Namespace) -> int:
    require_graph_or_workspace(args)
    selected_states = (
        frozenset(args.annotation_states) if args.annotation_states else None
    )
    if args.workspace:
        build = build_retrieval_workspace_indexes_use_case(
            args.workspace, systems=tuple(args.systems or ()),
            graphs=tuple(args.graphs or ()), areas=tuple(args.areas or ()),
            schemas=tuple(args.schemas or ()), zones=tuple(args.zones or ()),
            model_path=args.model_path, batch_size=args.batch_size,
            n_threads=args.n_threads, resume=args.resume,
            max_graphs=args.max_graphs, progress=_index_build_progress,
            annotation_states=selected_states, validated_only=args.validated_only,
        )
        if args.format == "json":
            print_json(build)
            return 0
        print(f"Workspace: {args.workspace}")
        print(f"Updated graphs: {build['built_graphs']}")
        print(f"Remaining graphs: {build['remaining_graphs']}")
        for built in build["built"]:
            print(
                f"  {built['graph']}: {built['embedded_documents']} embedded, "
                f"{built['reused_documents']} reused, "
                f"{built['unverified_documents']} unverified, "
                f"{built['truncated_documents']} shortened"
            )
        return 0
    result = build_retrieval_index_use_case(
        args.name, model_path=args.model_path, batch_size=args.batch_size,
        n_threads=args.n_threads, resume=args.resume,
        progress=_index_build_progress, annotation_states=selected_states,
        validated_only=args.validated_only,
    )
    if args.format == "json":
        print_json({
            "index": result.metadata.to_dict(), "path": str(result.path),
            "resumed_documents": result.resumed_documents,
            "reused_documents": result.reused_documents,
            "embedded_documents": result.embedded_documents,
            "removed_documents": result.removed_documents,
        })
        return 0
    print(f"Index: {result.metadata.graph}")
    print(f"Documents: {result.metadata.document_count}")
    print(f"Dimensions: {result.metadata.dimensions}")
    print(f"Model: {result.metadata.model_id}")
    print(f"Resumed documents: {result.resumed_documents}")
    print(f"Embedded documents: {result.embedded_documents}")
    print(f"Reused documents: {result.reused_documents}")
    print(f"Unverified reused documents: {result.metadata.unverified_documents}")
    truncated = result.metadata.truncated_documents
    print(f"Shortened documents: {len(truncated)}")
    if truncated:
        print(f"First shortened document: {truncated[0]}")
    print(f"Removed documents: {result.removed_documents}")
    print(f"Path: {result.path}")
    return 0


def _run_status(args: argparse.Namespace) -> int:
    require_graph_or_workspace(args)
    selected_states = (
        frozenset(args.annotation_states) if args.annotation_states else None
    )
    if args.workspace:
        workspace_status = retrieval_workspace_status_use_case(
            args.workspace, systems=tuple(args.systems or ()),
            graphs=tuple(args.graphs or ()), areas=tuple(args.areas or ()),
            schemas=tuple(args.schemas or ()), zones=tuple(args.zones or ()),
            annotation_states=selected_states, validated_only=args.validated_only,
        )
        if args.format == "json":
            print_json(workspace_status)
            return 0 if workspace_status["ready"] else 1
        print(f"Workspace: {args.workspace}")
        print(f"Status: {workspace_status['state']}")
        print(
            f"Graphs: {workspace_status['ready_graphs']}/{workspace_status['graph_count']} ready"
        )
        print(f"Documents: {workspace_status['document_count']}")
        print(f"Vector backend: {workspace_status['vector_backend']}")
        for status in workspace_status["graphs"]:
            print(f"  {status['graph']}: {status['state']}")
        unverified = workspace_status["unverified_embedding_graphs"]
        if unverified:
            print(f"Unverified embedding settings: {', '.join(unverified)}")
        truncated = workspace_status["truncated_embedding_graphs"]
        if truncated:
            print(f"Shortened documents in: {', '.join(truncated)}")
        return 0 if workspace_status["ready"] else 1
    graph_status = retrieval_index_status_use_case(
        args.name, annotation_states=selected_states,
        validated_only=args.validated_only,
    )
    if args.format == "json":
        print_json(graph_status)
        return 0 if graph_status["ready"] else 1
    metadata = graph_status["index"]
    print(f"Index: {args.name}")
    print(f"Status: {graph_status['state']}")
    if metadata is not None:
        print(f"Documents: {metadata['document_count']}")
        print(f"Dimensions: {metadata['dimensions']}")
        print(f"Model: {metadata['model_id']}")
    embedding_input = graph_status["embedding_input"]
    if embedding_input is not None:
        print(f"Embedding input: {embedding_input['state']}. {embedding_input['detail']}")
    checkpoint = graph_status["checkpoint"]
    if checkpoint is not None:
        print(
            "Checkpoint: "
            f"{checkpoint['completed_documents']}/{checkpoint['document_count']}"
        )
    print(f"Path: {graph_status['path']}")
    return 0 if graph_status["ready"] else 1


_HANDLERS = {
    "build": _run_build,
    "status": _run_status,
}
