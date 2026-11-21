"""``tarel.graph``: build, refresh, read and page through graphs."""

from __future__ import annotations

from pathlib import Path

from tarel.connectors.contracts import CatalogResult
from tarel.graph.application import (
    GraphBuildResult,
    GraphRefreshResult,
    build_graph_use_case,
    import_catalog_use_case,
    list_graphs_use_case,
    load_graph_use_case,
    refresh_graph_use_case,
)
from tarel.graph.contracts import GraphDocument
from tarel.graph.reads import (
    graph_header_use_case,
    graph_objects_use_case,
    graph_slice_use_case,
    rebuild_graph_index_use_case,
)
from tarel.graph.selective import GraphHeader, GraphObjectPage, GraphSlice
from tarel.sdk._base import RuntimeAPI, optional_path


class GraphAPI(RuntimeAPI):
    """Build, refresh and read graphs; paged reads avoid loading a whole graph."""

    def header(self, name: str) -> GraphHeader:
        return graph_header_use_case(name, runtime=self._runtime)

    def objects(
        self, name: str, *, object_ids: tuple[str, ...] | None = None,
        namespace: str | None = None, offset: int = 0, limit: int = 100,
        expected_revision: str | None = None,
    ) -> GraphObjectPage:
        return graph_objects_use_case(
            name, object_ids=object_ids, namespace=namespace, offset=offset, limit=limit,
            expected_revision=expected_revision, runtime=self._runtime,
        )

    def slice(
        self, name: str, object_ids: tuple[str, ...], *, namespace: str | None = None,
        expected_revision: str | None = None,
    ) -> GraphSlice:
        return graph_slice_use_case(
            name, object_ids, namespace=namespace, expected_revision=expected_revision,
            runtime=self._runtime,
        )

    def rebuild_index(self, name: str) -> GraphHeader:
        return rebuild_graph_index_use_case(name, runtime=self._runtime)

    def list(self) -> tuple[str, ...]:
        return list_graphs_use_case(runtime=self._runtime)

    def load(self, name: str) -> GraphDocument:
        return load_graph_use_case(name, runtime=self._runtime)

    def import_catalog(self, name: str, catalog: CatalogResult) -> GraphBuildResult:
        """Persist one already observed catalog without running discovery again."""
        return import_catalog_use_case(name, catalog, runtime=self._runtime)

    def build(
        self,
        name: str,
        *,
        connector: str,
        config: str | Path | None = None,
        database: str | None = None,
        namespace: str | None = None,
    ) -> GraphBuildResult:
        return build_graph_use_case(
            name,
            connector_name=connector,
            config_path=optional_path(config),
            database=database,
            namespace=namespace,
            runtime=self._runtime,
        )

    def refresh(
        self,
        name: str,
        *,
        config: str | Path | None = None,
        namespace: str | None = None,
        annotate_new_provider: str | None = None,
        annotation_workers: int = 1,
        annotation_model: str | None = None,
        annotation_timeout: float = 120.0,
    ) -> GraphRefreshResult:
        return refresh_graph_use_case(
            name,
            config_path=optional_path(config),
            namespace=namespace,
            annotate_new_provider=annotate_new_provider,
            annotation_workers=annotation_workers,
            annotation_model=annotation_model,
            annotation_timeout=annotation_timeout,
            runtime=self._runtime,
        )
