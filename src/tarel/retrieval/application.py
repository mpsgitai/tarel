"""Retrieval use cases: embedding models and the local search indexes built from graphs."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

from tarel.annotations.states import selected_annotation_states
from tarel.graph.revision import graph_revision
from tarel.retrieval.contracts import (
    EmbeddingBackend,
    GraphIndexStatus,
    IndexBuildResult,
    IndexBuildSummary,
    IndexStatus,
    ModelStatus,
    RetrievalFailure,
    WorkspaceIndexBuild,
    WorkspaceIndexStatus,
)
from tarel.retrieval.index import (
    embedding_input_status,
    sqlite_vec_available,
)
from tarel.retrieval.local import (
    DEFAULT_MODEL_NAME,
    ModelDownloadResult,
    default_model_path,
    download_model,
    model_spec,
    resolve_model_path,
    sha256_file,
)
from tarel.retrieval.plugins import (
    load_local_embedding_plugin,
    local_embedding_input_strategy,
)
from tarel.retrieval.remote import HTTP_EMBEDDING_INPUT, HTTPEmbedding, remote_identity
from tarel.retrieval.settings import (
    has_retrieval_selection,
    load_settings,
    selected_local_path,
    snapshot_runtime,
)
from tarel.runtime import TarelRuntime, resolve_runtime
from tarel.workspaces.application import resolve_workspace_scope_use_case


def download_embedding_model_use_case(
    *,
    name: str = DEFAULT_MODEL_NAME,
    target: Path | None = None,
    force: bool = False,
    progress: Callable[[int, int], None] | None = None,
) -> ModelDownloadResult:
    return download_model(name=name, target=target, force=force, progress=progress)


def embedding_model_status_use_case(
    *,
    name: str = DEFAULT_MODEL_NAME,
    model_path: Path | None = None,
) -> ModelStatus:
    spec = model_spec(name)
    path = (model_path or default_model_path(name)).expanduser().resolve()
    exists = path.is_file()
    return {
        "exists": exists,
        "model": name,
        "path": str(path),
        "sha256_valid": sha256_file(path) == spec.sha256 if exists else False,
        "size": path.stat().st_size if exists else None,
        "source": spec.source,
    }


def build_retrieval_index_use_case(
    name: str,
    *,
    model_path: Path | None = None,
    batch_size: int = 16,
    n_threads: int | None = None,
    resume: bool = False,
    progress: Callable[[int, int, str], None] | None = None,
    annotation_states: frozenset[str] | None = None,
    validated_only: bool = False,
    runtime: TarelRuntime | None = None,
) -> IndexBuildResult:
    runtime = snapshot_runtime(runtime, model_path=model_path)
    if not 1 <= batch_size <= 256:
        raise RetrievalFailure("invalid_batch_size", "Batch size must be between 1 and 256.")
    graph = resolve_runtime(runtime).graph_store().load(name)
    selected_states = selected_annotation_states(
        annotation_states, validated_only=validated_only,
    )
    store = resolve_runtime(runtime).retrieval_index()
    changes = store.changes(graph, annotation_states=selected_states)
    metadata = None
    try:
        metadata = store.metadata(name, annotation_states=selected_states)
    except RetrievalFailure as exc:
        if exc.code != "index_not_found":
            raise
    selected_model = _selected_retrieval_model(runtime, model_path)
    if (
        selected_model is None
        and metadata is not None
        and Path(metadata.model_path).is_file()
    ):
        resolved_model: Path | None = Path(metadata.model_path)
    else:
        resolved_model = (
            selected_model[0] if selected_model is not None
            else resolved_embedding_model(runtime, model_path)
        )
    model_sha256 = (
        selected_model[1] if selected_model is not None
        else embedding_model_sha256(runtime, resolved_model)
    )
    model_matches = metadata is not None and metadata.model_sha256 == model_sha256
    storage_complete = metadata is not None and store.storage_complete(
        name, metadata=metadata, annotation_states=selected_states,
    )
    selected_input = (
        HTTP_EMBEDDING_INPUT if resolved_model is None else local_embedding_input_strategy()
    )
    input_changed = (
        metadata is not None
        and (
            (bool(selected_input) and metadata.embedding_input != selected_input)
            or not metadata.embedding_input
        )
    )
    needs_embedding = (
        metadata is None
        or not model_matches
        or not storage_complete
        or changes.requires_embedding > 0
        or input_changed
    )
    embedder = (
        embedding_backend(
            runtime, resolved_model, model_sha256=model_sha256, n_threads=n_threads,
        )
        if needs_embedding else None
    )
    if embedder is None:
        # Embedding is skipped only when a complete index with the same model and embedding
        # settings already exists.
        assert metadata is not None
        model_id = metadata.model_id
    else:
        model_id = embedder.model_id
    return store.build(
        graph,
        embedder=embedder,
        model_path=resolved_model,
        model_id=model_id,
        model_sha256=model_sha256,
        batch_size=batch_size,
        resume=resume,
        progress=progress,
        annotation_states=selected_states,
    )


def retrieval_index_status_use_case(
    name: str,
    *,
    model_path: Path | None = None,
    runtime: TarelRuntime | None = None,
    annotation_states: frozenset[str] | None = None,
    validated_only: bool = False,
    _selection: _StatusSelection | None = None,
) -> IndexStatus:
    runtime = snapshot_runtime(runtime, model_path=model_path)
    graph = resolve_runtime(runtime).graph_store().load(name)
    store = resolve_runtime(runtime).retrieval_index()
    selected_states = selected_annotation_states(
        annotation_states, validated_only=validated_only,
    )
    selected_model, model_missing = _selection or _status_selection(runtime, model_path)
    checkpoint = store.checkpoint_status(name, annotation_states=selected_states)
    changes = store.changes(graph, annotation_states=selected_states)
    try:
        metadata = store.metadata(name, annotation_states=selected_states)
    except RetrievalFailure as exc:
        if exc.code != "index_not_found":
            raise
        return {
            "state": "building" if checkpoint else "missing",
            "checkpoint": checkpoint,
            "current": False,
            "ready": False,
            "changes": changes.to_dict(),
            "index": None,
            "model_available": None,
            "model_matches": None,
            "embedding_input": None,
            "path": str(store.path(name, annotation_states=selected_states)),
            "vector_backend": "sqlite-vec" if sqlite_vec_available() else "python",
        }
    current = (
        changes.current
        if metadata.documents_sha256
        else metadata.graph_hash == graph_revision(graph)
    )
    storage_complete = store.storage_complete(
        name, metadata=metadata, annotation_states=selected_states,
    )
    stored_model_available = Path(metadata.model_path).is_file()
    model_available = stored_model_available and not model_missing
    if selected_model is not None and selected_model[0] is None:
        model_available = True
    if selected_model is None and stored_model_available and not model_missing:
        stored_model = Path(metadata.model_path)
        selected_model = (stored_model, embedding_model_sha256(runtime, stored_model))
    model_matches = (
        None if model_missing
        else selected_model is None or metadata.model_sha256 == selected_model[1]
    )
    ready = current and storage_complete and model_available and model_matches is True
    return {
        "state": (
            "ready" if ready
            else "model_mismatch" if current and model_available and not model_matches
            else "model_missing" if current and not model_available
            else "update_required"
        ),
        "checkpoint": checkpoint,
        "current": current,
        "ready": ready,
        "changes": changes.to_dict(),
        "index": metadata.to_dict(),
        "model_available": model_available,
        "model_matches": model_matches,
        "embedding_input": embedding_input_status(metadata),
        "path": str(store.path(name, annotation_states=selected_states)),
        "vector_backend": "sqlite-vec" if sqlite_vec_available() else "python",
    }


def retrieval_workspace_status_use_case(
    workspace_name: str,
    *,
    systems: tuple[str, ...] = (),
    graphs: tuple[str, ...] = (),
    areas: tuple[str, ...] = (),
    schemas: tuple[str, ...] = (),
    zones: tuple[str, ...] = (),
    model_path: Path | None = None,
    annotation_states: frozenset[str] | None = None,
    validated_only: bool = False,
    runtime: TarelRuntime | None = None,
) -> WorkspaceIndexStatus:
    runtime = snapshot_runtime(runtime, model_path=model_path)
    runtime = runtime or TarelRuntime.local(Path.cwd() / ".tarel")
    selection = _status_selection(runtime, model_path)
    scope = resolve_workspace_scope_use_case(
        workspace_name, systems=systems, graphs=graphs, areas=areas,
        schemas=schemas, zones=zones, runtime=runtime,
    )
    graph_names = scope.graph_names
    if areas or schemas or zones:
        graph_names = tuple(sorted({item.graph for item in scope.objects}))
    statuses = tuple(
        GraphIndexStatus(
            **retrieval_index_status_use_case(
                name, annotation_states=annotation_states, validated_only=validated_only,
                runtime=runtime, _selection=selection,
            ),
            graph=name,
        )
        for name in graph_names
    )
    ready = sum(status["ready"] is True for status in statuses)
    missing = sum(status["state"] == "missing" for status in statuses)
    documents = sum(
        int(status["index"]["document_count"])
        for status in statuses if status["index"] is not None
    )
    pending = len(statuses) - ready
    state = (
        "ready" if pending == 0
        else "missing" if missing == len(statuses)
        else "update_required"
    )
    return {
        "workspace": workspace_name,
        "state": state,
        "current": pending == 0,
        "ready": pending == 0,
        "graph_count": len(statuses),
        "ready_graphs": ready,
        "pending_graphs": pending,
        "missing_graphs": missing,
        "document_count": documents,
        "unverified_embedding_graphs": sorted(
            status["graph"] for status in statuses
            if status["embedding_input"] is not None
            and status["embedding_input"]["unverified_documents"] > 0
        ),
        "truncated_embedding_graphs": sorted(
            status["graph"] for status in statuses
            if status["embedding_input"] is not None
            and status["embedding_input"]["truncated_documents"]
        ),
        "vector_backend": "sqlite-vec" if sqlite_vec_available() else "python",
        "graphs": list(statuses),
    }


def build_retrieval_workspace_indexes_use_case(
    workspace_name: str,
    *,
    systems: tuple[str, ...] = (),
    graphs: tuple[str, ...] = (),
    areas: tuple[str, ...] = (),
    schemas: tuple[str, ...] = (),
    zones: tuple[str, ...] = (),
    model_path: Path | None = None,
    batch_size: int = 16,
    n_threads: int | None = None,
    resume: bool = False,
    max_graphs: int = 8,
    progress: Callable[[int, int, str], None] | None = None,
    annotation_states: frozenset[str] | None = None,
    validated_only: bool = False,
    runtime: TarelRuntime | None = None,
) -> WorkspaceIndexBuild:
    runtime = snapshot_runtime(runtime, model_path=model_path)
    if not 1 <= max_graphs <= 100:
        raise RetrievalFailure("invalid_graph_limit", "Graph limit must be between 1 and 100.")
    runtime = runtime or TarelRuntime.local(Path.cwd() / ".tarel")
    before = retrieval_workspace_status_use_case(
        workspace_name, systems=systems, graphs=graphs, areas=areas,
        schemas=schemas, zones=zones, model_path=model_path,
        annotation_states=annotation_states,
        validated_only=validated_only, runtime=runtime,
    )
    # A ready graph with unrecorded embedding settings still works, but only a build can settle it.
    pending = [
        str(status["graph"]) for status in before["graphs"]
        if not status["ready"] or _embedding_input_state(status) == "unverified"
    ]
    builds: list[IndexBuildSummary] = []
    for name in pending[:max_graphs]:
        result = build_retrieval_index_use_case(
            name, model_path=model_path, batch_size=batch_size, n_threads=n_threads,
            resume=resume, progress=progress, annotation_states=annotation_states,
            validated_only=validated_only, runtime=runtime,
        )
        builds.append({
            "graph": name,
            "documents": result.metadata.document_count,
            "embedded_documents": result.embedded_documents,
            "reused_documents": result.reused_documents,
            "removed_documents": result.removed_documents,
            "unverified_documents": result.metadata.unverified_documents,
            "truncated_documents": len(result.metadata.truncated_documents),
            "path": str(result.path),
        })
    after = retrieval_workspace_status_use_case(
        workspace_name, systems=systems, graphs=graphs, areas=areas,
        schemas=schemas, zones=zones, model_path=model_path,
        annotation_states=annotation_states,
        validated_only=validated_only, runtime=runtime,
    )
    return {
        "workspace": workspace_name,
        "built": builds,
        "built_graphs": len(builds),
        "remaining_graphs": after["pending_graphs"],
        "status": after,
    }


def _embedding_input_state(status: GraphIndexStatus) -> str | None:
    embedding_input = status["embedding_input"]
    return embedding_input["state"] if embedding_input is not None else None


def _create_local_embedder(
    model_path: Path,
    *,
    n_threads: int | None = None,
) -> EmbeddingBackend:
    return load_local_embedding_plugin().create_embedder(model_path, n_threads=n_threads)


def embedding_backend(
    runtime: TarelRuntime | None,
    model_path: Path | None,
    *,
    model_sha256: str,
    n_threads: int | None,
) -> EmbeddingBackend:
    if model_path is None:
        choice = load_settings(runtime).embedding
        if remote_identity(choice) != model_sha256:
            raise RetrievalFailure(
                "model_changed_during_load", "Provider profile changed during selection.",
            )
        return HTTPEmbedding(choice)
    if runtime is None:
        if sha256_file(model_path) != model_sha256:
            raise RetrievalFailure(
                "model_changed_during_load",
                "Embedding model changed before it could be loaded.",
            )
        backend = _create_local_embedder(model_path, n_threads=n_threads)
        if sha256_file(model_path) != model_sha256:
            raise RetrievalFailure(
                "model_changed_during_load",
                "Embedding model changed while it was being loaded.",
            )
        return backend
    return cast(
        EmbeddingBackend,
        runtime.embedding_backend(
            model_path,
            n_threads,
            model_sha256,
            lambda: _create_local_embedder(model_path, n_threads=n_threads),
        ),
    )


def embedding_model_sha256(runtime: TarelRuntime | None, model_path: Path | None) -> str:
    if model_path is None:
        return remote_identity(load_settings(runtime).embedding)
    return runtime.model_sha256(model_path) if runtime is not None else sha256_file(model_path)


def resolved_embedding_model(runtime: TarelRuntime | None, model_path: Path | None) -> Path | None:
    choice = load_settings(runtime).embedding
    path = selected_local_path(runtime, model_path)
    return resolve_model_path(path) if choice.provider == "local" else None


_StatusSelection = tuple[tuple[Path | None, str] | None, bool]
"""The selected embedding model (as for a build) and whether its local file is missing."""


def _status_selection(runtime: TarelRuntime | None, model_path: Path | None) -> _StatusSelection:
    """Like _selected_retrieval_model, but a missing model is a status, not an error."""
    try:
        return _selected_retrieval_model(runtime, model_path), False
    except RetrievalFailure as exc:
        if exc.code != "model_not_found":
            raise
        return None, True


def _selected_retrieval_model(
    runtime: TarelRuntime | None,
    model_path: Path | None,
) -> tuple[Path | None, str] | None:
    choice = load_settings(runtime).embedding
    selected_path = selected_local_path(runtime, model_path)
    if choice.provider != "local":
        return None, remote_identity(choice)
    if selected_path is None and not has_retrieval_selection(runtime):
        return None
    resolved = resolve_model_path(selected_path)
    return resolved, embedding_model_sha256(runtime, resolved)
