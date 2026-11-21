"""Focus use cases: build, load and list lineage-anchored working sets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tarel.focus.contracts import FocusDocument, FocusFailure
from tarel.focus.core import build_focus, graph_object_ids, require_current_focus
from tarel.graph.contracts import GraphDocument
from tarel.lineage.contracts import LineageDocument
from tarel.lineage.traversal import DEFAULT_LINEAGE_STATES, trace_upstream
from tarel.runtime import TarelRuntime, resolve_runtime


@dataclass(frozen=True, slots=True)
class FocusBuildResult:
    focus: FocusDocument
    path: Path


def build_focus_use_case(
    name: str,
    *,
    seed: str,
    lineage_names: tuple[str, ...],
    graph_names: tuple[str, ...],
    max_hops: int = 12,
    states: frozenset[str] | None = None,
    runtime: TarelRuntime | None = None,
) -> FocusBuildResult:
    if not lineage_names and not graph_names:
        raise FocusFailure(
            "missing_focus_sources",
            "Focus build requires at least one explicit --lineage or --graph source.",
        )
    _require_unique_names(lineage_names, "lineage")
    _require_unique_names(graph_names, "graph")
    lineage_store = resolve_runtime(runtime).lineage_store()
    graph_store = resolve_runtime(runtime).graph_store()
    lineages = tuple(lineage_store.load(item) for item in lineage_names)
    graphs = tuple(graph_store.load(item) for item in graph_names)
    selected_states = DEFAULT_LINEAGE_STATES if states is None else states
    trace = trace_upstream(
        lineages,
        graphs,
        seed,
        max_hops=max_hops,
        states=selected_states,
    )
    focus = build_focus(
        name,
        trace,
        lineages=lineages,
        graphs=graphs,
        states=selected_states,
        max_hops=max_hops,
    )
    return FocusBuildResult(focus, resolve_runtime(runtime).focus_store().save(focus))


def load_focus_use_case(
    name: str,
    *,
    runtime: TarelRuntime | None = None,
) -> FocusDocument:
    return resolve_runtime(runtime).focus_store().load(name)


def current_focus_use_case(
    name: str, *, runtime: TarelRuntime | None = None,
) -> FocusDocument:
    """Usable focus, checked against all source graph and lineage revisions."""
    return load_current_focus(name, runtime=runtime)[0]


def list_focuses_use_case(*, runtime: TarelRuntime | None = None) -> tuple[str, ...]:
    return resolve_runtime(runtime).focus_store().list()


def focus_object_allowlist(
    focuses: tuple[str, ...],
    *,
    graph_names: tuple[str, ...],
    runtime: TarelRuntime | None,
) -> tuple[dict[str, frozenset[str]], tuple[str, ...]]:
    allowed: dict[str, set[str]] = {name: set() for name in graph_names}
    warnings: list[str] = []
    for name in sorted(set(focuses)):
        focus, _lineages, _graphs = load_current_focus(name, runtime=runtime)
        for graph_name in graph_names:
            allowed[graph_name].update(graph_object_ids(focus, graph_name))
        warnings.extend(f"{name}: {warning}" for warning in focus.warnings)
        if focus.truncated:
            warnings.append(f"{name}: focus traversal was truncated")
    return (
        {name: frozenset(object_ids) for name, object_ids in allowed.items()},
        tuple(sorted(set(warnings))),
    )


def load_current_focus(
    name: str,
    *,
    runtime: TarelRuntime | None = None,
) -> tuple[FocusDocument, dict[str, LineageDocument], dict[str, GraphDocument]]:
    focus = resolve_runtime(runtime).focus_store().load(name)
    lineage_store = resolve_runtime(runtime).lineage_store()
    graph_store = resolve_runtime(runtime).graph_store()
    available_lineages = set(lineage_store.list())
    available_graphs = set(graph_store.list())
    missing = [
        item
        for item in focus.sources
        if (item.kind == "lineage" and item.name not in available_lineages)
        or (item.kind == "graph" and item.name not in available_graphs)
    ]
    if missing:
        rendered = ", ".join(f"{item.kind}:{item.name}" for item in missing)
        raise FocusFailure(
            "focus_stale",
            f"Focus {name} references missing sources: {rendered}",
        )
    lineages = {
        item.name: lineage_store.load(item.name) for item in focus.sources if item.kind == "lineage"
    }
    graphs = {
        item.name: graph_store.load(item.name) for item in focus.sources if item.kind == "graph"
    }
    require_current_focus(focus, lineages=lineages, graphs=graphs)
    return focus, lineages, graphs


def _require_unique_names(names: tuple[str, ...], label: str) -> None:
    if len(names) != len(set(names)):
        raise FocusFailure(
            "duplicate_focus_source",
            f"Focus {label} sources must not contain duplicates.",
        )
