"""Lineage use cases: build, import, edit, review and trace static lineage documents."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tarel.errors import name_preview
from tarel.graph.contracts import GraphDocument
from tarel.lineage.contracts import (
    LineageDefinition,
    LineageDocument,
    LineageFailure,
    LineageWriteUnit,
)
from tarel.lineage.core import (
    ProcessStep,
    TableLineage,
    apply_lineage_proposal,
    build_lineage,
    process_view,
    table_lineage,
)
from tarel.lineage.manual import add_manual_hop, add_manual_job, create_manual_lineage
from tarel.lineage.refresh import LineageRefreshReport, refresh_lineage
from tarel.lineage.review import LineageReviewItem, decide_lineage_item, list_lineage_items
from tarel.lineage.revision import lineage_revision
from tarel.lineage.source import LineageInput, load_lineage_input
from tarel.lineage.status import LineageStatus, lineage_status
from tarel.lineage.tasks import LineageTask, plan_lineage_tasks
from tarel.lineage.traversal import (
    LineageReference,
    UpstreamTrace,
    find_lineage_references,
    trace_upstream,
)
from tarel.retrieval.local import resolve_model_path
from tarel.retrieval.plugins import load_local_embedding_plugin
from tarel.runtime import TarelRuntime, resolve_runtime


@dataclass(frozen=True, slots=True)
class LineageChangeResult:
    document: LineageDocument
    path: Path
    report: LineageRefreshReport | None = None
    report_path: Path | None = None


@dataclass(frozen=True, slots=True)
class LineageReviewResult:
    document: LineageDocument
    item: LineageReviewItem
    path: Path


@dataclass(frozen=True, slots=True)
class ManualJobResult:
    document: LineageDocument
    definition: LineageDefinition
    path: Path


@dataclass(frozen=True, slots=True)
class ManualHopResult:
    document: LineageDocument
    item: LineageWriteUnit
    path: Path


def build_lineage_use_case(
    name: str,
    *,
    source_path: Path,
    runtime: TarelRuntime | None = None,
) -> LineageChangeResult:
    return _build_from_input(name, load_lineage_input(source_path), runtime=runtime)


def import_dbt_lineage_use_case(
    name: str,
    *,
    manifest_path: Path,
    catalog_map: Mapping[str, str] | None = None,
    runtime: TarelRuntime | None = None,
) -> LineageChangeResult:
    from tarel.lineage.dbt import load_dbt_manifest

    source = load_dbt_manifest(manifest_path, catalog_map=catalog_map)
    return _build_from_input(name, source, runtime=runtime)


def _build_from_input(
    name: str,
    source: LineageInput,
    *,
    runtime: TarelRuntime | None,
) -> LineageChangeResult:
    store = resolve_runtime(runtime).lineage_store()
    if store.exists(name):
        document = store.load(name)
        if document.source_revision == source.revision:
            return LineageChangeResult(document, store.path(name))
        refreshed, report = refresh_lineage(document, source)
        report_path = resolve_runtime(runtime).lineage_change_store().save(name, report)
        return LineageChangeResult(
            refreshed,
            store.save(refreshed),
            report,
            report_path,
        )
    document = build_lineage(name, source)
    return LineageChangeResult(document, store.save(document))


def load_lineage_use_case(
    name: str,
    *,
    runtime: TarelRuntime | None = None,
) -> LineageDocument:
    return resolve_runtime(runtime).lineage_store().load(name)


def list_lineages_use_case(*, runtime: TarelRuntime | None = None) -> tuple[str, ...]:
    return resolve_runtime(runtime).lineage_store().list()


def add_manual_job_use_case(
    name: str,
    *,
    kind: str,
    job_name: str,
    qualified_name: str,
    language: str,
    source_reference: str,
    description: str,
    expected_revision: str | None = None,
    runtime: TarelRuntime | None = None,
) -> ManualJobResult:
    store = resolve_runtime(runtime).lineage_store()
    document = store.load(name) if store.exists(name) else create_manual_lineage(name)
    _require_expected_revision(document, expected_revision)
    updated, definition = add_manual_job(
        document,
        kind=kind,
        name=job_name,
        qualified_name=qualified_name,
        language=language,
        source_reference=source_reference,
        description=description,
    )
    return ManualJobResult(updated, definition, store.save(updated))


def add_manual_hop_use_case(
    name: str,
    *,
    job_reference: str,
    source: str,
    target: str,
    operation: str,
    role: str,
    evidence_reference: str,
    reason: str,
    line_start: int = 1,
    line_end: int = 1,
    expected_revision: str | None = None,
    runtime: TarelRuntime | None = None,
) -> ManualHopResult:
    store = resolve_runtime(runtime).lineage_store()
    document = store.load(name)
    _require_expected_revision(document, expected_revision)
    updated, item = add_manual_hop(
        document,
        job_reference=job_reference,
        source=source,
        target=target,
        operation=operation,
        role=role,
        evidence_reference=evidence_reference,
        reason=reason,
        line_start=line_start,
        line_end=line_end,
    )
    return ManualHopResult(updated, item, store.save(updated))


def next_lineage_task_use_case(
    name: str,
    *,
    source_path: Path,
    runtime: TarelRuntime | None = None,
) -> LineageTask | None:
    document = resolve_runtime(runtime).lineage_store().load(name)
    source = load_lineage_input(source_path)
    tasks = plan_lineage_tasks(document, source)
    return tasks[0] if tasks else None


def apply_lineage_proposal_use_case(
    name: str,
    *,
    source_path: Path,
    payload: dict[str, Any],
    runtime: TarelRuntime | None = None,
) -> LineageChangeResult:
    store = resolve_runtime(runtime).lineage_store()
    document = store.load(name)
    source = load_lineage_input(source_path)
    updated = apply_lineage_proposal(document, source, payload)
    return LineageChangeResult(updated, store.save(updated))


def list_lineage_items_use_case(
    name: str,
    *,
    states: frozenset[str] | None = None,
    runtime: TarelRuntime | None = None,
) -> tuple[LineageReviewItem, ...]:
    document = resolve_runtime(runtime).lineage_store().load(name)
    return list_lineage_items(document, states=states)


def decide_lineage_item_use_case(
    name: str,
    claim_id: str,
    *,
    decision: str,
    reason: str,
    expected_revision: str | None = None,
    runtime: TarelRuntime | None = None,
) -> LineageReviewResult:
    store = resolve_runtime(runtime).lineage_store()
    current = store.load(name)
    _require_expected_revision(current, expected_revision)
    document, item = decide_lineage_item(
        current,
        claim_id,
        decision=decision,
        reason=reason,
    )
    return LineageReviewResult(document, item, store.save(document))


def process_lineage_view_use_case(
    name: str,
    *,
    runtime: TarelRuntime | None = None,
) -> tuple[ProcessStep, ...]:
    return process_view(resolve_runtime(runtime).lineage_store().load(name))


def table_lineage_view_use_case(
    name: str,
    *,
    runtime: TarelRuntime | None = None,
) -> tuple[TableLineage, ...]:
    return table_lineage(resolve_runtime(runtime).lineage_store().load(name))


def lineage_status_use_case(
    name: str,
    *,
    runtime: TarelRuntime | None = None,
) -> LineageStatus:
    return lineage_status(resolve_runtime(runtime).lineage_store().load(name))


def find_lineage_references_use_case(
    query: str,
    *,
    lineage_names: tuple[str, ...],
    graph_names: tuple[str, ...] = (),
    limit: int = 20,
    mode: str = "lexical",
    model_path: Path | None = None,
    n_threads: int | None = None,
    runtime: TarelRuntime | None = None,
) -> tuple[LineageReference, ...]:
    documents, graphs = load_trace_sources(lineage_names, graph_names, runtime=runtime)
    embedder = None
    if mode in {"vector", "hybrid"}:
        embedder = load_local_embedding_plugin().create_embedder(
            resolve_model_path(model_path), n_threads=n_threads
        )
    return find_lineage_references(
        documents,
        graphs,
        query,
        limit=limit,
        mode=mode,
        embedder=embedder,
    )


def trace_upstream_use_case(
    reference: str,
    *,
    lineage_names: tuple[str, ...],
    graph_names: tuple[str, ...] = (),
    max_hops: int = 12,
    states: frozenset[str] | None = None,
    runtime: TarelRuntime | None = None,
) -> UpstreamTrace:
    documents, graphs = load_trace_sources(lineage_names, graph_names, runtime=runtime)
    selected = states if states is not None else None
    if selected is None:
        return trace_upstream(documents, graphs, reference, max_hops=max_hops)
    return trace_upstream(documents, graphs, reference, max_hops=max_hops, states=selected)


def _require_expected_revision(
    document: LineageDocument,
    expected_revision: str | None,
) -> None:
    if expected_revision is not None and lineage_revision(document) != expected_revision:
        raise LineageFailure(
            "stale_lineage",
            "The lineage document changed after it was loaded. Reload before saving.",
        )


def load_trace_sources(
    lineage_names: tuple[str, ...],
    graph_names: tuple[str, ...],
    *,
    runtime: TarelRuntime | None = None,
) -> tuple[tuple[LineageDocument, ...], tuple[GraphDocument, ...]]:
    state = resolve_runtime(runtime)
    lineage_store = state.lineage_store()
    graph_store = state.graph_store()
    if not lineage_names:
        raise LineageFailure("lineage_not_found", "No local lineage documents are available.")
    require_source_roles(
        lineage_names,
        graph_names,
        known_lineages=lineage_store.list(),
        known_graphs=graph_store.list(),
    )
    return (
        tuple(lineage_store.load(name) for name in lineage_names),
        tuple(graph_store.load(name) for name in graph_names),
    )


def require_source_roles(
    lineage_names: tuple[str, ...],
    graph_names: tuple[str, ...],
    *,
    known_lineages: tuple[str, ...],
    known_graphs: tuple[str, ...],
) -> None:
    """Reject a lineage name passed as a graph, or a graph name passed as a lineage.

    Both mistakes are common for agents because lineage documents and catalog graphs share one
    namespace of short names. The failure carries the corrected source lists in
    ``details["suggestion"]``, so one retry repairs every misplaced name at once.
    """
    lineage_set, graph_set = set(known_lineages), set(known_graphs)
    as_lineage = [item for item in graph_names if item not in graph_set and item in lineage_set]
    as_graph = [item for item in lineage_names if item not in lineage_set and item in graph_set]
    if not as_lineage and not as_graph:
        return
    kept_graphs = tuple(item for item in graph_names if item not in as_lineage)
    kept_lineages = tuple(item for item in lineage_names if item not in as_graph)
    suggestion = {
        "graphs": _unique((*kept_graphs, *as_graph)),
        "lineages": _unique((*kept_lineages, *as_lineage)),
    }
    if as_lineage:
        name, code, param, role = as_lineage[0], "invalid_graph_role", "graphs", "lineage"
        accepted = known_graphs
        message = f"'{name}' is a lineage document, not a catalog graph."
    else:
        name, code, param, role = as_graph[0], "invalid_lineage_role", "lineages", "graph"
        accepted = known_lineages
        message = f"'{name}' is a catalog graph, not a lineage document."
    raise LineageFailure(
        code,
        message,
        hint=f"Pass '{name}' as a {role} (--{role} / {role}s=) instead.",
        retryable=True,
        details={
            "accepted_count": len(accepted),
            "accepted_preview": name_preview(name, accepted),
            "param": param,
            "suggestion": suggestion,
            "value": name,
        },
    )


def _unique(names: tuple[str, ...]) -> list[str]:
    return list(dict.fromkeys(names))
