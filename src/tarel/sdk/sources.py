"""``tarel.source``: named logical sources with explicit read permissions."""

from __future__ import annotations

from tarel.connectors.contracts import CatalogResult, ProbeResult
from tarel.graph.application import GraphBuildResult, GraphRefreshResult
from tarel.sdk._base import RuntimeAPI
from tarel.sources.application import (
    SourceChangeResult,
    SourceCheck,
    SourceEnrichmentResult,
    build_source_graph_use_case,
    check_source_use_case,
    configure_source_use_case,
    discover_source_use_case,
    enrich_source_use_case,
    list_sources_use_case,
    load_source_use_case,
    probe_source_use_case,
    refresh_source_graph_use_case,
)
from tarel.sources.contracts import SourceProfile


class SourceAPI(RuntimeAPI):
    """Manage private logical sources without storing resolved credentials."""

    def configure(
        self,
        name: str,
        *,
        connector: str,
        config_reference: str | None = None,
        database: str | None = None,
        namespace: str | None = None,
        graphs: tuple[str, ...] = (),
        enrichment_permissions: tuple[str, ...] = (),
        replace: bool = False,
    ) -> SourceChangeResult:
        return configure_source_use_case(
            name,
            connector=connector,
            config_reference=config_reference,
            database=database,
            namespace=namespace,
            graphs=graphs,
            enrichment_permissions=enrichment_permissions,
            replace=replace,
            runtime=self._runtime,
        )

    def list(self) -> tuple[str, ...]:
        return list_sources_use_case(runtime=self._runtime)

    def load(self, name: str) -> SourceProfile:
        return load_source_use_case(name, runtime=self._runtime)

    def check(self, name: str) -> SourceCheck:
        return check_source_use_case(name, runtime=self._runtime)

    def probe(self, name: str, *, database: str | None = None) -> ProbeResult:
        return probe_source_use_case(
            name,
            database=database,
            runtime=self._runtime,
        )

    def discover(
        self,
        name: str,
        *,
        database: str | None = None,
        namespace: str | None = None,
    ) -> CatalogResult:
        return discover_source_use_case(
            name,
            database=database,
            namespace=namespace,
            runtime=self._runtime,
        )

    def build_graph(
        self,
        name: str,
        graph: str,
        *,
        database: str | None = None,
        namespace: str | None = None,
    ) -> GraphBuildResult:
        return build_source_graph_use_case(
            name,
            graph,
            database=database,
            namespace=namespace,
            runtime=self._runtime,
        )

    def refresh_graph(
        self,
        name: str,
        graph: str,
        *,
        namespace: str | None = None,
        annotate_new_provider: str | None = None,
        annotation_workers: int = 1,
        annotation_model: str | None = None,
        annotation_timeout: float = 120.0,
    ) -> GraphRefreshResult:
        return refresh_source_graph_use_case(
            name,
            graph,
            namespace=namespace,
            annotate_new_provider=annotate_new_provider,
            annotation_workers=annotation_workers,
            annotation_model=annotation_model,
            annotation_timeout=annotation_timeout,
            runtime=self._runtime,
        )

    def enrich(
        self,
        name: str,
        graph: str,
        *,
        profile_row_limit: int = 10_000,
        sample_limit: int = 10,
        persist_join_candidates: bool = False,
    ) -> SourceEnrichmentResult:
        return enrich_source_use_case(
            name,
            graph,
            profile_row_limit=profile_row_limit,
            sample_limit=sample_limit,
            persist_join_candidates=persist_join_candidates,
            runtime=self._runtime,
        )
