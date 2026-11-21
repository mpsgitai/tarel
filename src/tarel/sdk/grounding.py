"""``tarel.grounding``: harness grounding bundles and their assets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tarel.context.grounding import GroundingAsset, GroundingBundle
from tarel.context.grounding_application import (
    compile_graph_grounding_use_case,
    compile_workspace_grounding_use_case,
    describe_grounding_asset_use_case,
)
from tarel.context.output import DEFAULT_MAX_CONTEXT_CHARACTERS
from tarel.lineage.application import (
    trace_upstream_use_case,
)
from tarel.lineage.traversal import UpstreamTrace
from tarel.sdk._base import RuntimeAPI, optional_path
from tarel.sdk._scope import resolve_workspace_scope, workspace_scope_arguments
from tarel.workspaces.contracts import WorkspaceFailure
from tarel.workspaces.scope import ScopeSelection


class GroundingAPI(RuntimeAPI):
    """Compile agent-ready semantic context with source and lineage identity."""

    def context(
        self,
        question: str,
        *,
        graph: str | None = None,
        workspace: str | None = None,
        namespace: str | None = None,
        selection: ScopeSelection | None = None,
        systems: tuple[str, ...] = (),
        graphs: tuple[str, ...] = (),
        areas: tuple[str, ...] = (),
        schemas: tuple[str, ...] = (),
        zones: tuple[str, ...] = (),
        lineages: tuple[str, ...] = (),
        sources: tuple[str, ...] = (),
        trace: str | None = None,
        lineage_limit: int = 8,
        lineage_mode: str = "bm25",
        lineage_states: frozenset[str] | None = None,
        seed_limit: int = 3,
        max_objects: int = 10,
        max_joins: int = 12,
        max_hops: int = 2,
        max_trace_hops: int = 12,
        max_fields_per_object: int = 12,
        max_characters: int = DEFAULT_MAX_CONTEXT_CHARACTERS,
        mode: str = "lexical",
        model_path: str | Path | None = None,
        n_threads: int | None = None,
        annotation_states: frozenset[str] | None = None,
        validated_only: bool = False,
        logical_hints: str | None = None,
    ) -> GroundingBundle:
        if (graph is None) == (workspace is None):
            raise WorkspaceFailure(
                "invalid_grounding_scope",
                "Grounding requires exactly one graph or workspace.",
            )
        common: dict[str, Any] = {
            "lineage_names": lineages,
            "source_names": sources,
            "trace_reference": trace,
            "lineage_limit": lineage_limit,
            "lineage_mode": lineage_mode,
            "lineage_states": lineage_states,
            "seed_limit": seed_limit,
            "max_objects": max_objects,
            "max_joins": max_joins,
            "max_hops": max_hops,
            "max_trace_hops": max_trace_hops,
            "max_fields_per_object": max_fields_per_object,
            "max_characters": max_characters,
            "mode": mode,
            "model_path": optional_path(model_path),
            "n_threads": n_threads,
            "annotation_states": annotation_states,
            "validated_only": validated_only,
            "logical_hints": logical_hints,
            "runtime": self._runtime,
        }
        if graph is not None:
            if selection is not None or any((systems, graphs, areas, schemas, zones)):
                raise WorkspaceFailure(
                    "invalid_grounding_scope",
                    "Workspace scope filters cannot be used with a graph.",
                )
            return compile_graph_grounding_use_case(
                graph,
                question,
                namespace=namespace,
                **common,
            )
        if namespace is not None:
            raise WorkspaceFailure(
                "invalid_grounding_scope",
                "Use workspace schemas instead of namespace for workspace grounding.",
            )
        systems, graphs, areas, schemas, zones = workspace_scope_arguments(
            selection,
            systems=systems,
            graphs=graphs,
            areas=areas,
            schemas=schemas,
            zones=zones,
        )
        assert workspace is not None
        return compile_workspace_grounding_use_case(
            workspace,
            question,
            systems=systems,
            graphs=graphs,
            areas=areas,
            schemas=schemas,
            zones=zones,
            **common,
        )

    def find(
        self,
        query: str,
        *,
        graph: str | None = None,
        workspace: str | None = None,
        namespace: str | None = None,
        selection: ScopeSelection | None = None,
        systems: tuple[str, ...] = (),
        graphs: tuple[str, ...] = (),
        areas: tuple[str, ...] = (),
        schemas: tuple[str, ...] = (),
        zones: tuple[str, ...] = (),
        lineages: tuple[str, ...] = (),
        sources: tuple[str, ...] = (),
        limit: int = 10,
        lineage_mode: str = "bm25",
        mode: str = "lexical",
        model_path: str | Path | None = None,
        n_threads: int | None = None,
        annotation_states: frozenset[str] | None = None,
        validated_only: bool = False,
        logical_hints: str | None = None,
    ) -> GroundingBundle:
        """Return ranked semantic assets without relationship expansion."""
        if not 1 <= limit <= 20:
            raise WorkspaceFailure(
                "invalid_grounding_limit",
                "Grounding find limit must be between 1 and 20.",
            )
        return self.context(
            query,
            graph=graph,
            workspace=workspace,
            namespace=namespace,
            selection=selection,
            systems=systems,
            graphs=graphs,
            areas=areas,
            schemas=schemas,
            zones=zones,
            lineages=lineages,
            sources=sources,
            lineage_mode=lineage_mode,
            seed_limit=limit,
            max_objects=limit,
            max_joins=0,
            max_hops=0,
            mode=mode,
            model_path=model_path,
            n_threads=n_threads,
            annotation_states=annotation_states,
            validated_only=validated_only,
            logical_hints=logical_hints,
        )

    def describe(
        self,
        graph: str,
        reference: str,
        *,
        source: str | None = None,
    ) -> GroundingAsset:
        return describe_grounding_asset_use_case(
            graph,
            reference,
            source_name=source,
            runtime=self._runtime,
        )

    def upstream(
        self,
        reference: str,
        *,
        lineages: tuple[str, ...],
        graph: str | None = None,
        workspace: str | None = None,
        selection: ScopeSelection | None = None,
        systems: tuple[str, ...] = (),
        graphs: tuple[str, ...] = (),
        areas: tuple[str, ...] = (),
        schemas: tuple[str, ...] = (),
        zones: tuple[str, ...] = (),
        max_hops: int = 12,
        states: frozenset[str] | None = None,
    ) -> UpstreamTrace:
        if (graph is None) == (workspace is None):
            raise WorkspaceFailure(
                "invalid_grounding_scope",
                "Grounding requires exactly one graph or workspace.",
            )
        if graph is not None:
            if selection is not None or any((systems, graphs, areas, schemas, zones)):
                raise WorkspaceFailure(
                    "invalid_grounding_scope",
                    "Workspace scope filters cannot be used with a graph.",
                )
            graph_names: tuple[str, ...] = (graph,)
        else:
            assert workspace is not None
            resolved = resolve_workspace_scope(
                self._runtime,
                workspace,
                selection=selection,
                systems=systems,
                graphs=graphs,
                areas=areas,
                schemas=schemas,
                zones=zones,
            )
            graph_names = resolved.graph_names
        return trace_upstream_use_case(
            reference,
            lineage_names=lineages,
            graph_names=graph_names,
            max_hops=max_hops,
            states=states,
            runtime=self._runtime,
        )
