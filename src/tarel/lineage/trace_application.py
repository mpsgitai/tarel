"""Lineage trace use cases that choose their own sources: resolution, direction and batches.

Which documents a trace reads is decided once, in :func:`resolve_lineage_sources_use_case`:

1. Explicit sources always win. ``sources`` entries are classified as lineage or graph by name
   (``lineage:NAME`` / ``graph:NAME`` force a role); a name that is both fails as ambiguous.
2. ``workspace`` adds every graph of that workspace.
3. Without explicit lineages, every local lineage document is read. If no graph was named
   either, the graphs whose catalog those documents name in a fully qualified reference are
   added (``declared_catalogs``) - never all graphs blindly.

Naming only ``--lineage`` keeps its earlier meaning (no graphs), so existing calls and their full
output do not change. The result reports what was chosen and why, so nothing is implicit.
"""

from __future__ import annotations

from dataclasses import dataclass

from tarel.errors import unknown_name_error
from tarel.lineage.application import load_trace_sources, require_source_roles
from tarel.lineage.contracts import LineageFailure
from tarel.lineage.directions import LineageBatch, LineageTrace, trace_lineage, trace_lineage_batch
from tarel.lineage.resolution import declared_catalogs
from tarel.lineage.traversal import DEFAULT_LINEAGE_STATES
from tarel.runtime import TarelRuntime, resolve_runtime


@dataclass(frozen=True, slots=True)
class ResolvedLineageSources:
    lineage_names: tuple[str, ...]
    graph_names: tuple[str, ...]
    lineages_from: str = "explicit"
    graphs_from: str = "explicit"

    @property
    def auto(self) -> bool:
        return self.lineages_from != "explicit" or self.graphs_from != "explicit"

    def to_dict(self) -> dict[str, object]:
        return {
            "auto": self.auto,
            "graphs": list(self.graph_names),
            "graphs_from": self.graphs_from,
            "lineages": list(self.lineage_names),
            "lineages_from": self.lineages_from,
        }


def resolve_lineage_sources_use_case(
    *,
    sources: tuple[str, ...] = (),
    lineage_names: tuple[str, ...] = (),
    graph_names: tuple[str, ...] = (),
    workspace: str | None = None,
    auto_catalog: bool = True,
    runtime: TarelRuntime | None = None,
) -> ResolvedLineageSources:
    state = resolve_runtime(runtime)
    known_lineages = state.lineage_store().list()
    known_graphs = state.graph_store().list()
    named_lineages, named_graphs = _classify(sources, known_lineages, known_graphs)
    lineages = _unique((*lineage_names, *named_lineages))
    graphs = _unique((*graph_names, *named_graphs))
    try:
        require_source_roles(
            lineages, graphs, known_lineages=known_lineages, known_graphs=known_graphs,
        )
    except LineageFailure as exc:
        suggestion = exc.details.get("suggestion")
        if auto_catalog and isinstance(suggestion, dict) and not suggestion.get("graphs"):
            suggestion["graphs"] = list(
                catalog_graphs(tuple(suggestion["lineages"]), runtime=state)
            )
            suggestion["graphs_from"] = "declared_catalogs"
        raise
    graphs_from = "explicit"
    if workspace is not None:
        from tarel.workspaces.application import resolve_workspace_scope_use_case

        scope = resolve_workspace_scope_use_case(workspace, runtime=state)
        graphs = _unique((*graphs, *scope.graph_names))
        graphs_from = "explicit+workspace" if graph_names or named_graphs else "workspace"
    lineages_from = "explicit"
    if not lineages:
        if not known_lineages:
            raise LineageFailure(
                "lineage_not_found",
                "No local lineage documents are available.",
                hint="Build or import a lineage document first (tarel lineage build / import-dbt).",
            )
        lineages, lineages_from = known_lineages, "all_local"
    if not graphs and lineages_from == "all_local" and auto_catalog:
        graphs, graphs_from = catalog_graphs(lineages, runtime=state), "declared_catalogs"
    return ResolvedLineageSources(lineages, graphs, lineages_from, graphs_from)


def catalog_graphs(
    lineage_names: tuple[str, ...], *, runtime: TarelRuntime | None = None,
) -> tuple[str, ...]:
    """Local graphs whose catalog the named lineage documents reference by qualified name."""
    state = resolve_runtime(runtime)
    graph_store = state.graph_store()
    catalogs = {name: graph_store.header(name).catalog.casefold() for name in graph_store.list()}
    known = frozenset(catalogs.values())
    lineage_store = state.lineage_store()
    declared: set[str] = set()
    for name in lineage_names:
        declared |= declared_catalogs(lineage_store.load(name), known)
    return tuple(sorted(name for name, catalog in catalogs.items() if catalog in declared))


def trace_lineage_use_case(
    reference: str,
    *,
    lineage_names: tuple[str, ...],
    graph_names: tuple[str, ...] = (),
    direction: str = "up",
    max_hops: int = 12,
    states: frozenset[str] | None = None,
    runtime: TarelRuntime | None = None,
) -> LineageTrace:
    documents, graphs = load_trace_sources(lineage_names, graph_names, runtime=runtime)
    return trace_lineage(
        documents, graphs, reference, direction=direction, max_hops=max_hops,
        states=states if states is not None else DEFAULT_LINEAGE_STATES,
    )


def trace_lineage_batch_use_case(
    references: tuple[str, ...],
    *,
    lineage_names: tuple[str, ...],
    graph_names: tuple[str, ...] = (),
    direction: str = "up",
    max_hops: int = 12,
    states: frozenset[str] | None = None,
    runtime: TarelRuntime | None = None,
) -> LineageBatch:
    documents, graphs = load_trace_sources(lineage_names, graph_names, runtime=runtime)
    return trace_lineage_batch(
        documents, graphs, references, direction=direction, max_hops=max_hops,
        states=states if states is not None else DEFAULT_LINEAGE_STATES,
    )


def _classify(
    sources: tuple[str, ...],
    known_lineages: tuple[str, ...],
    known_graphs: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    lineage_set, graph_set = set(known_lineages), set(known_graphs)
    lineages: list[str] = []
    graphs: list[str] = []
    for item in sources:
        role, separator, name = item.partition(":")
        if separator and role in {"lineage", "graph"}:
            (lineages if role == "lineage" else graphs).append(name)
        elif item in lineage_set and item in graph_set:
            raise LineageFailure(
                "ambiguous_source",
                f"'{item}' names both a lineage document and a graph.",
                hint=f"Write 'lineage:{item}' or 'graph:{item}'.",
                retryable=True,
                details={
                    "param": "sources",
                    "suggestion": [f"lineage:{item}", f"graph:{item}"],
                    "value": item,
                },
            )
        elif item in lineage_set:
            lineages.append(item)
        elif item in graph_set:
            graphs.append(item)
        else:
            raise unknown_name_error(
                LineageFailure, "unknown_lineage_source", f"Unknown lineage source: {item}",
                param="sources", value=item, accepted=(*known_lineages, *known_graphs),
                noun="lineage or graph",
            )
    return tuple(lineages), tuple(graphs)


def _unique(names: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(names))

