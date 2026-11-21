"""``tarel.model`` and ``tarel.index``: embedding models and local retrieval indexes."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from tarel.retrieval.application import (
    build_retrieval_index_use_case,
    build_retrieval_workspace_indexes_use_case,
    download_embedding_model_use_case,
    embedding_model_status_use_case,
    retrieval_index_status_use_case,
    retrieval_workspace_status_use_case,
)
from tarel.retrieval.contracts import (
    IndexBuildResult,
    IndexStatus,
    ModelStatus,
    WorkspaceIndexBuild,
    WorkspaceIndexStatus,
)
from tarel.retrieval.local import DEFAULT_MODEL_NAME, ModelDownloadResult
from tarel.sdk._base import RuntimeAPI, optional_path


class ModelAPI(RuntimeAPI):
    """Download and inspect the optional local embedding model."""

    def download(
        self,
        *,
        name: str = DEFAULT_MODEL_NAME,
        target: str | Path | None = None,
        force: bool = False,
        progress: Callable[[int, int], None] | None = None,
    ) -> ModelDownloadResult:
        return download_embedding_model_use_case(
            name=name,
            target=optional_path(target),
            force=force,
            progress=progress,
        )

    def status(
        self,
        *,
        name: str = DEFAULT_MODEL_NAME,
        model_path: str | Path | None = None,
    ) -> ModelStatus:
        return embedding_model_status_use_case(
            name=name,
            model_path=optional_path(model_path),
        )


class IndexAPI(RuntimeAPI):
    """Build and inspect local retrieval indexes for graphs and workspaces."""

    def build(
        self,
        graph: str,
        *,
        model_path: str | Path | None = None,
        batch_size: int = 16,
        n_threads: int | None = None,
        resume: bool = False,
        progress: Callable[[int, int, str], None] | None = None,
        annotation_states: frozenset[str] | None = None,
        validated_only: bool = False,
    ) -> IndexBuildResult:
        return build_retrieval_index_use_case(
            graph,
            model_path=optional_path(model_path),
            batch_size=batch_size,
            n_threads=n_threads,
            resume=resume,
            progress=progress,
            annotation_states=annotation_states,
            validated_only=validated_only,
            runtime=self._runtime,
        )

    def status(
        self, graph: str, *, model_path: str | Path | None = None,
        annotation_states: frozenset[str] | None = None,
        validated_only: bool = False,
    ) -> IndexStatus:
        return retrieval_index_status_use_case(
            graph, model_path=optional_path(model_path),
            annotation_states=annotation_states, validated_only=validated_only,
            runtime=self._runtime,
        )

    def build_workspace(
        self,
        workspace: str,
        *,
        systems: tuple[str, ...] = (),
        graphs: tuple[str, ...] = (),
        areas: tuple[str, ...] = (),
        schemas: tuple[str, ...] = (),
        zones: tuple[str, ...] = (),
        model_path: str | Path | None = None,
        batch_size: int = 16,
        n_threads: int | None = None,
        resume: bool = False,
        max_graphs: int = 8,
        progress: Callable[[int, int, str], None] | None = None,
        annotation_states: frozenset[str] | None = None,
        validated_only: bool = False,
    ) -> WorkspaceIndexBuild:
        return build_retrieval_workspace_indexes_use_case(
            workspace, systems=systems, graphs=graphs, areas=areas,
            schemas=schemas, zones=zones, model_path=optional_path(model_path),
            batch_size=batch_size, n_threads=n_threads, resume=resume,
            max_graphs=max_graphs, progress=progress,
            annotation_states=annotation_states, validated_only=validated_only,
            runtime=self._runtime,
        )

    def status_workspace(
        self,
        workspace: str,
        *,
        systems: tuple[str, ...] = (),
        graphs: tuple[str, ...] = (),
        areas: tuple[str, ...] = (),
        schemas: tuple[str, ...] = (),
        zones: tuple[str, ...] = (),
        model_path: str | Path | None = None,
        annotation_states: frozenset[str] | None = None,
        validated_only: bool = False,
    ) -> WorkspaceIndexStatus:
        return retrieval_workspace_status_use_case(
            workspace, systems=systems, graphs=graphs, areas=areas,
            schemas=schemas, zones=zones, model_path=optional_path(model_path),
            annotation_states=annotation_states,
            validated_only=validated_only, runtime=self._runtime,
        )
