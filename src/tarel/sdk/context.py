"""``tarel.context``: compile, split, compare and expand context packets."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from tarel.context.application import (
    compare_context_use_case,
    compile_context_prefix_use_case,
    compile_context_use_case,
    compile_workspace_context_prefix_use_case,
    compile_workspace_context_use_case,
    context_packet_brief_use_case,
    context_packet_impact_use_case,
    describe_context_use_case,
    diff_context_packets_use_case,
)
from tarel.context.caching import ContextCacheParts, split_context_packet
from tarel.context.compiler import ContextResult
from tarel.context.guidance import ContextBrief, ContextDelta
from tarel.context.output import DEFAULT_MAX_CONTEXT_CHARACTERS
from tarel.context.packets import ContextPacketDiff, ContextPacketImpact, ContextPacketSnapshot
from tarel.expansion.application import expand_context_use_case
from tarel.expansion.contracts import ContextExpansion, ExpansionInput, ExpansionTarget
from tarel.sdk._base import RuntimeAPI, optional_path
from tarel.sdk._scope import workspace_focuses, workspace_objects, workspace_scope_arguments
from tarel.workspaces.scope import ScopeSelection


class ContextAPI(RuntimeAPI):
    """Compile, split, brief, compare and expand context packets for a harness."""

    def expand(
        self, packet: ContextResult | ContextPacketSnapshot | dict[str, object],
        targets: tuple[ExpansionTarget, ...], *, mode: str = "confirmed_only",
        inputs: Mapping[str, ExpansionInput] | None = None, max_characters: int = 24_000,
    ) -> ContextExpansion:
        return expand_context_use_case(
            packet, targets, mode=mode, inputs=inputs, max_characters=max_characters,
            runtime=self._runtime,
        )

    def prefix_graph(
        self,
        name: str,
        *,
        namespace: str | None = None,
        max_objects: int = 250,
        max_joins: int = 500,
        max_fields_per_object: int = 50,
        max_characters: int = 500_000,
        annotation_states: frozenset[str] | None = None,
        validated_only: bool = False,
        logical_hints: str | None = None,
        scope_object_ids: tuple[str, ...] = (),
        focuses: tuple[str, ...] = (),
    ) -> ContextResult:
        return compile_context_prefix_use_case(
            name,
            namespace=namespace,
            max_objects=max_objects,
            max_joins=max_joins,
            max_fields_per_object=max_fields_per_object,
            max_characters=max_characters,
            annotation_states=annotation_states,
            validated_only=validated_only,
            logical_hints=logical_hints,
            scope_object_ids=scope_object_ids,
            focuses=focuses,
            runtime=self._runtime,
        )

    def prefix_workspace(
        self,
        name: str,
        *,
        selection: ScopeSelection | None = None,
        systems: tuple[str, ...] = (),
        graphs: tuple[str, ...] = (),
        areas: tuple[str, ...] = (),
        schemas: tuple[str, ...] = (),
        zones: tuple[str, ...] = (),
        focuses: tuple[str, ...] = (),
        scope_objects: tuple[str, ...] = (),
        max_objects: int = 250,
        max_joins: int = 500,
        max_fields_per_object: int = 50,
        max_characters: int = 500_000,
        annotation_states: frozenset[str] | None = None,
        validated_only: bool = False,
        logical_hints: str | None = None,
    ) -> ContextResult:
        focus_names = workspace_focuses(selection, focuses)
        systems, graphs, areas, schemas, zones = workspace_scope_arguments(
            selection,
            systems=systems,
            graphs=graphs,
            areas=areas,
            schemas=schemas,
            zones=zones,
        )
        return compile_workspace_context_prefix_use_case(
            name,
            systems=systems,
            graphs=graphs,
            areas=areas,
            schemas=schemas,
            zones=zones,
            focuses=focus_names,
            scope_objects=workspace_objects(selection, scope_objects),
            max_objects=max_objects,
            max_joins=max_joins,
            max_fields_per_object=max_fields_per_object,
            max_characters=max_characters,
            annotation_states=annotation_states,
            validated_only=validated_only,
            logical_hints=logical_hints,
            runtime=self._runtime,
        )

    def split(self, packet: ContextResult) -> ContextCacheParts:
        return split_context_packet(packet)

    def brief(
        self,
        packet: ContextResult | ContextPacketSnapshot | dict[str, object] | str | Path,
    ) -> ContextBrief:
        """Summarize scope, size, coverage, gaps, and continuity identity."""
        if isinstance(packet, (str, Path)):
            return context_packet_brief_use_case(Path(packet))
        return describe_context_use_case(packet)

    def compare(
        self,
        previous: ContextResult | ContextPacketSnapshot | dict[str, object] | str | Path,
        current: ContextResult | ContextPacketSnapshot | dict[str, object] | str | Path,
    ) -> ContextDelta:
        """Describe context additions, removals, gap changes, and cache reuse."""
        left = Path(previous) if isinstance(previous, str) else previous
        right = Path(current) if isinstance(current, str) else current
        return compare_context_use_case(left, right)

    def diff(self, left: str | Path, right: str | Path) -> ContextPacketDiff:
        return diff_context_packets_use_case(Path(left), Path(right))

    def impact(self, packet: str | Path, *, graph: str) -> ContextPacketImpact:
        return context_packet_impact_use_case(
            Path(packet),
            graph,
            runtime=self._runtime,
        )

    def graph(
        self,
        name: str,
        query: str,
        *,
        namespace: str | None = None,
        seed_limit: int = 3,
        max_objects: int = 10,
        max_joins: int = 12,
        max_hops: int = 2,
        max_fields_per_object: int = 12,
        max_characters: int = DEFAULT_MAX_CONTEXT_CHARACTERS,
        mode: str = "lexical",
        model_path: str | Path | None = None,
        n_threads: int | None = None,
        bm25_weight: float | None = None,
        annotation_states: frozenset[str] | None = None,
        validated_only: bool = False,
        logical_hints: str | None = None,
        object_ids: tuple[str, ...] = (),
        scope_object_ids: tuple[str, ...] = (),
        focuses: tuple[str, ...] = (),
        include_anomaly: bool = False,
        anomaly_dir: str | Path | None = None,
    ) -> ContextResult:
        return compile_context_use_case(
            name,
            query,
            namespace=namespace,
            seed_limit=seed_limit,
            max_objects=max_objects,
            max_joins=max_joins,
            max_hops=max_hops,
            max_fields_per_object=max_fields_per_object,
            max_characters=max_characters,
            mode=mode,
            model_path=optional_path(model_path),
            n_threads=n_threads,
            bm25_weight=bm25_weight,
            annotation_states=annotation_states,
            validated_only=validated_only,
            logical_hints=logical_hints,
            object_ids=object_ids,
            scope_object_ids=scope_object_ids,
            focuses=focuses,
            include_anomaly=include_anomaly,
            anomaly_dir=optional_path(anomaly_dir),
            runtime=self._runtime,
        )

    def workspace(
        self,
        name: str,
        query: str,
        *,
        selection: ScopeSelection | None = None,
        systems: tuple[str, ...] = (),
        graphs: tuple[str, ...] = (),
        areas: tuple[str, ...] = (),
        schemas: tuple[str, ...] = (),
        zones: tuple[str, ...] = (),
        focuses: tuple[str, ...] = (),
        scope_objects: tuple[str, ...] = (),
        seed_limit: int = 3,
        max_objects: int = 10,
        max_joins: int = 12,
        max_hops: int = 2,
        max_fields_per_object: int = 12,
        max_characters: int = DEFAULT_MAX_CONTEXT_CHARACTERS,
        mode: str = "lexical",
        model_path: str | Path | None = None,
        n_threads: int | None = None,
        bm25_weight: float | None = None,
        annotation_states: frozenset[str] | None = None,
        validated_only: bool = False,
        logical_hints: str | None = None,
        object_ids: tuple[str, ...] = (),
        include_anomaly: bool = False,
        anomaly_dir: str | Path | None = None,
    ) -> ContextResult:
        focus_names = workspace_focuses(selection, focuses)
        systems, graphs, areas, schemas, zones = workspace_scope_arguments(
            selection,
            systems=systems,
            graphs=graphs,
            areas=areas,
            schemas=schemas,
            zones=zones,
        )
        return compile_workspace_context_use_case(
            name,
            query,
            systems=systems,
            graphs=graphs,
            areas=areas,
            schemas=schemas,
            zones=zones,
            focuses=focus_names,
            scope_objects=workspace_objects(selection, scope_objects),
            seed_limit=seed_limit,
            max_objects=max_objects,
            max_joins=max_joins,
            max_hops=max_hops,
            max_fields_per_object=max_fields_per_object,
            max_characters=max_characters,
            mode=mode,
            model_path=optional_path(model_path),
            n_threads=n_threads,
            bm25_weight=bm25_weight,
            annotation_states=annotation_states,
            validated_only=validated_only,
            logical_hints=logical_hints,
            object_ids=object_ids,
            include_anomaly=include_anomaly,
            anomaly_dir=optional_path(anomaly_dir),
            runtime=self._runtime,
        )
