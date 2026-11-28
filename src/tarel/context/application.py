"""Context use cases: compile, prefix, describe, compare and assess context packets."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from tarel.annotations.states import selected_annotation_states
from tarel.anomaly_signals import load_anomaly_signals_for_graphs, resolve_anomaly_dir
from tarel.context.compiler import (
    DEFAULT_MAX_CONTEXT_CHARACTERS,
    ContextResult,
    compile_context,
    compile_context_from_objects,
    compile_context_from_search,
    compile_context_prefix,
)
from tarel.context.guidance import ContextBrief, ContextDelta, context_brief, context_delta
from tarel.context.hints_application import add_logical_context_hints_use_case
from tarel.context.output import SCOPED_CONTEXT_CONTRACT_VERSION, ContextScope
from tarel.context.packets import (
    ContextPacketDiff,
    ContextPacketImpact,
    ContextPacketSnapshot,
    context_packet_graph_identity,
    context_packet_impact,
    diff_context_packets,
    load_context_packet,
)
from tarel.graph.revision import graph_revision
from tarel.retrieval.ranking import (
    validate_bm25_weight,
)
from tarel.retrieval.search_application import (
    project_graph_scope,
    resolve_graph_object_scope,
    search_graph_use_case,
    search_workspace_use_case,
)
from tarel.runtime import TarelRuntime, resolve_runtime
from tarel.search import SearchFailure
from tarel.workspaces.application import load_workspace_scope
from tarel.workspaces.projection import project_workspace_scope
from tarel.workspaces.scope import ResolvedScope


def compile_context_use_case(
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
    model_path: Path | None = None,
    n_threads: int | None = None,
    bm25_weight: float | None = None,
    annotation_states: frozenset[str] | None = None,
    validated_only: bool = False,
    logical_hints: str | None = None,
    object_ids: tuple[str, ...] = (),
    scope_object_ids: tuple[str, ...] = (),
    focuses: tuple[str, ...] = (),
    include_anomaly: bool = False,
    anomaly_dir: Path | None = None,
    runtime: TarelRuntime | None = None,
) -> ContextResult:
    validate_bm25_weight(mode, bm25_weight)
    source_graph = resolve_runtime(runtime).graph_store().load(name)
    effective_scope, scoped, scope_warnings = resolve_graph_object_scope(
        source=source_graph, focuses=focuses, object_ids=scope_object_ids, runtime=runtime,
    )
    graph = (
        project_graph_scope(source_graph, effective_scope)
        if scoped else source_graph
    )
    context_scope = (
        ContextScope(
            mode="graph_scope", namespace=namespace,
            focuses=tuple(sorted(set(focuses))), objects=effective_scope,
            warnings=scope_warnings,
        )
        if scoped else None
    )
    selected_states = selected_annotation_states(
        annotation_states,
        validated_only=validated_only,
    )
    if object_ids:
        result = compile_context_from_objects(
            graph, object_ids, query=query, max_objects=max_objects,
            max_joins=max_joins, max_hops=max_hops,
            max_fields_per_object=max_fields_per_object,
            max_characters=max_characters, annotation_states=selected_states,
            scope=context_scope,
        )
    elif mode == "lexical":
        result = compile_context(
            graph,
            query,
            namespace=namespace,
            seed_limit=seed_limit,
            max_objects=max_objects,
            max_joins=max_joins,
            max_hops=max_hops,
            max_fields_per_object=max_fields_per_object,
            max_characters=max_characters,
            annotation_states=selected_states,
            scope=context_scope,
        )
    else:
        search = search_graph_use_case(
            name,
            query,
            limit=100,
            namespace=namespace,
            mode=mode,
            model_path=model_path,
            n_threads=n_threads,
            bm25_weight=bm25_weight,
            annotation_states=selected_states,
            family_mode=None,
            focuses=focuses,
            scope_object_ids=scope_object_ids,
            runtime=runtime,
        )
        result = compile_context_from_search(
            graph,
            search,
            namespace=namespace,
            seed_limit=seed_limit,
            max_objects=max_objects,
            max_joins=max_joins,
            max_hops=max_hops,
            max_fields_per_object=max_fields_per_object,
            max_characters=max_characters,
            annotation_states=selected_states,
            scope=context_scope,
        )
    result = add_logical_context_hints_use_case(
        result, (source_graph,), mode=logical_hints, runtime=runtime,
    )
    if scoped:
        result = replace(
            result, graph_revision=graph_revision(source_graph),
            contract_version=SCOPED_CONTEXT_CONTRACT_VERSION,
        )
    if include_anomaly or anomaly_dir is not None:
        result = _attach_anomaly_signals(
            result,
            (source_graph,),
            anomaly_dir=anomaly_dir,
            workspace_scoped=False,
            runtime=runtime,
        )
    return result


def compile_workspace_context_use_case(
    workspace_name: str,
    query: str,
    *,
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
    model_path: Path | None = None,
    n_threads: int | None = None,
    bm25_weight: float | None = None,
    annotation_states: frozenset[str] | None = None,
    validated_only: bool = False,
    logical_hints: str | None = None,
    object_ids: tuple[str, ...] = (),
    include_anomaly: bool = False,
    anomaly_dir: Path | None = None,
    runtime: TarelRuntime | None = None,
) -> ContextResult:
    validate_bm25_weight(mode, bm25_weight)
    workspace, loaded, scope = load_workspace_scope(
        workspace_name,
        systems=systems,
        graphs=graphs,
        areas=areas,
        schemas=schemas,
        zones=zones,
        focuses=focuses,
        objects=scope_objects,
        runtime=runtime,
    )
    selected_states = selected_annotation_states(
        annotation_states,
        validated_only=validated_only,
    )
    projection = project_workspace_scope(workspace, loaded, scope)
    selection = scope.selection
    context_scope = ContextScope(
        mode="workspace_retrieval",
        workspace=workspace_name,
        scope_hash=scope.scope_hash,
        systems=tuple(sorted(set(selection.systems))),
        graphs=scope.graph_names,
        areas=tuple(sorted(set(selection.areas))),
        schemas=tuple(sorted(set(selection.schemas))),
        zones=tuple(sorted(set(selection.zones))),
        focuses=tuple(sorted(set(selection.focuses))),
        objects=tuple(sorted(set(selection.objects))),
        warnings=scope.warnings,
    )
    if object_ids:
        selected = _workspace_context_object_ids(scope, object_ids)
        result = compile_context_from_objects(
            projection, selected, query=query, max_objects=max_objects,
            max_joins=max_joins, max_hops=max_hops,
            max_fields_per_object=max_fields_per_object,
            max_characters=max_characters, annotation_states=selected_states,
            scope=context_scope,
        )
    else:
        search = search_workspace_use_case(
            workspace_name, query, systems=systems, graphs=graphs, areas=areas,
            schemas=schemas, zones=zones, focuses=focuses, limit=100, mode=mode,
            scope_objects=scope_objects,
            model_path=model_path, n_threads=n_threads, bm25_weight=bm25_weight,
            annotation_states=selected_states, family_mode=None, runtime=runtime,
        )
        result = compile_context_from_search(
            projection, search, seed_limit=seed_limit, max_objects=max_objects,
            max_joins=max_joins, max_hops=max_hops,
            max_fields_per_object=max_fields_per_object,
            max_characters=max_characters, annotation_states=selected_states,
            scope=context_scope,
        )
    result = add_logical_context_hints_use_case(
        result, tuple(loaded.values()), mode=logical_hints,
        projection=projection, runtime=runtime,
    )
    if focuses or scope_objects:
        result = replace(result, contract_version=SCOPED_CONTEXT_CONTRACT_VERSION)
    if include_anomaly or anomaly_dir is not None:
        result = _attach_anomaly_signals(
            result,
            tuple(loaded[name] for name in scope.graph_names),
            anomaly_dir=anomaly_dir,
            workspace_scoped=True,
            runtime=runtime,
        )
    return result


def compile_context_prefix_use_case(
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
    runtime: TarelRuntime | None = None,
) -> ContextResult:
    source_graph = resolve_runtime(runtime).graph_store().load(name)
    effective_scope, scoped, scope_warnings = resolve_graph_object_scope(
        source=source_graph, focuses=focuses, object_ids=scope_object_ids, runtime=runtime,
    )
    graph = (
        project_graph_scope(source_graph, effective_scope)
        if scoped else source_graph
    )
    selected_states = selected_annotation_states(
        annotation_states,
        validated_only=validated_only,
    )
    result = compile_context_prefix(
        graph,
        namespace=namespace,
        max_objects=max_objects,
        max_joins=max_joins,
        max_fields_per_object=max_fields_per_object,
        max_characters=max_characters,
        annotation_states=selected_states,
        scope=(
            ContextScope(
                mode="graph_scope_prefix", namespace=namespace,
                focuses=tuple(sorted(set(focuses))), objects=effective_scope,
                warnings=scope_warnings,
            )
            if scoped else None
        ),
    )
    result = add_logical_context_hints_use_case(
        result, (source_graph,), mode=logical_hints, runtime=runtime,
    )
    if scoped:
        result = replace(
            result, graph_revision=graph_revision(source_graph),
            contract_version=SCOPED_CONTEXT_CONTRACT_VERSION,
        )
    return result


def compile_workspace_context_prefix_use_case(
    workspace_name: str,
    *,
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
    runtime: TarelRuntime | None = None,
) -> ContextResult:
    workspace, loaded, scope = load_workspace_scope(
        workspace_name,
        systems=systems,
        graphs=graphs,
        areas=areas,
        schemas=schemas,
        zones=zones,
        focuses=focuses,
        objects=scope_objects,
        runtime=runtime,
    )
    selected_states = selected_annotation_states(
        annotation_states,
        validated_only=validated_only,
    )
    projection = project_workspace_scope(workspace, loaded, scope)
    selection = scope.selection
    result = compile_context_prefix(
        projection,
        max_objects=max_objects,
        max_joins=max_joins,
        max_fields_per_object=max_fields_per_object,
        max_characters=max_characters,
        annotation_states=selected_states,
        scope=ContextScope(
            mode="workspace_prefix",
            workspace=workspace_name,
            scope_hash=scope.scope_hash,
            systems=tuple(sorted(set(selection.systems))),
            graphs=scope.graph_names,
            areas=tuple(sorted(set(selection.areas))),
            schemas=tuple(sorted(set(selection.schemas))),
            zones=tuple(sorted(set(selection.zones))),
            focuses=tuple(sorted(set(selection.focuses))),
            objects=tuple(sorted(set(selection.objects))),
            warnings=scope.warnings,
        ),
    )
    result = add_logical_context_hints_use_case(
        result, tuple(loaded.values()), mode=logical_hints,
        projection=projection, runtime=runtime,
    )
    return (
        replace(result, contract_version=SCOPED_CONTEXT_CONTRACT_VERSION)
        if focuses or scope_objects else result
    )


def _workspace_context_object_ids(
    scope: ResolvedScope,
    references: tuple[str, ...],
) -> tuple[str, ...]:
    from tarel.workspaces.projection import scoped_node_id

    allowed = {(item.graph, item.object_id) for item in scope.objects}
    selected: list[str] = []
    for reference in references:
        graph_name, separator, object_id = reference.partition(":")
        if not separator or not graph_name or not object_id:
            raise SearchFailure(
                "invalid_object_reference",
                f"Workspace object must use GRAPH:OBJECT_ID: {reference}",
            )
        if (graph_name, object_id) not in allowed:
            raise SearchFailure(
                "object_outside_scope", f"Object is outside the selected scope: {reference}"
            )
        selected.append(scoped_node_id(graph_name, object_id))
    return tuple(selected)


def _attach_anomaly_signals(
    result: ContextResult,
    graphs: tuple[object, ...],
    *,
    anomaly_dir: Path | None,
    workspace_scoped: bool,
    runtime: TarelRuntime | None,
) -> ContextResult:
    from tarel.graph.contracts import GraphDocument
    from tarel.workspaces.projection import scoped_node_id

    graph_docs = tuple(item for item in graphs if isinstance(item, GraphDocument))
    loaded = load_anomaly_signals_for_graphs(
        graph_docs,
        anomaly_dir=resolve_anomaly_dir(runtime, anomaly_dir),
    )
    packet_ids = {item.id for item in result.objects}
    objects: dict[str, object] = {}
    edge_shifts: list[dict[str, object]] = []

    def packet_id(graph_name: str, object_id: str) -> str:
        return scoped_node_id(graph_name, object_id) if workspace_scoped else object_id

    for graph_name in sorted(loaded.files):
        signal_file = loaded.files[graph_name]
        for raw_object_id in sorted(signal_file.objects):
            pid = packet_id(graph_name, raw_object_id)
            if pid not in packet_ids:
                continue
            objects[pid] = signal_file.objects[raw_object_id].to_context_dict(
                stale=signal_file.stale
            )
        for shift in signal_file.edge_shifts:
            up_id = packet_id(graph_name, shift.upstream_object_id)
            down_id = packet_id(graph_name, shift.downstream_object_id)
            if up_id in packet_ids and down_id in packet_ids:
                edge_shifts.append(
                    shift.to_dict(
                        upstream_id=up_id,
                        downstream_id=down_id,
                        graph=graph_name if workspace_scoped else None,
                    )
                )

    anomaly_payload: dict[str, object] = {
        "edge_shifts": edge_shifts,
        "missing_graphs": list(loaded.missing_graphs),
        "objects": objects,
        "observed_at": loaded.latest_observed_at,
        "stale_graphs": list(loaded.stale_graphs),
    }
    return replace(result, anomaly_signals=anomaly_payload)


def diff_context_packets_use_case(left: Path, right: Path) -> ContextPacketDiff:
    return diff_context_packets(load_context_packet(left), load_context_packet(right))


def context_packet_diff_views_use_case(
    left: Path, right: Path,
) -> tuple[ContextPacketDiff, ContextDelta]:
    """Load two packet files once and return their technical and guidance views."""
    left_packet = load_context_packet(left)
    right_packet = load_context_packet(right)
    return (
        diff_context_packets(left_packet, right_packet),
        context_delta(left_packet, right_packet),
    )


def describe_context_use_case(
    packet: ContextResult | ContextPacketSnapshot | dict[str, object],
) -> ContextBrief:
    return context_brief(packet)


def compare_context_use_case(
    previous: ContextResult | ContextPacketSnapshot | dict[str, object] | Path,
    current: ContextResult | ContextPacketSnapshot | dict[str, object] | Path,
) -> ContextDelta:
    left = load_context_packet(previous) if isinstance(previous, Path) else previous
    right = load_context_packet(current) if isinstance(current, Path) else current
    return context_delta(left, right)


def context_packet_brief_use_case(packet: Path) -> ContextBrief:
    return describe_context_use_case(load_context_packet(packet))


def compare_context_packets_use_case(left: Path, right: Path) -> ContextDelta:
    return compare_context_use_case(load_context_packet(left), load_context_packet(right))


def context_packet_impact_use_case(
    packet_path: Path,
    graph_name: str,
    *,
    runtime: TarelRuntime | None = None,
) -> ContextPacketImpact:
    graph = resolve_runtime(runtime).graph_store().load(graph_name)
    current_revision = graph_revision(graph)
    packet = load_context_packet(packet_path)
    _packet_graph, packet_revision = context_packet_graph_identity(packet)
    change_store = resolve_runtime(runtime).graph_change_store()
    report_path = change_store.path(graph_name, packet_revision, current_revision)
    report = (
        change_store.load(graph_name, packet_revision, current_revision)
        if report_path.exists()
        else None
    )
    return context_packet_impact(packet, graph, report)
